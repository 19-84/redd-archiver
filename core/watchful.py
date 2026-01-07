"""
ABOUTME: Streaming utilities for memory-efficient .zst decompression and JSON parsing
ABOUTME: Processes compressed Pushshift data dumps line-by-line with minimal memory usage
"""
import zstandard
import os
import json
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional, Iterator, Tuple, Set, List
import logging.handlers

from .postgres_database import PostgresDatabase, PostgresDatabaseError, get_postgres_connection_string
from utils.console_output import print_info, print_success, print_error, print_warning


log = logging.getLogger("bot")
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())


def read_and_decode(reader: Any, chunk_size: int, max_window_size: int, previous_chunk: Optional[bytes] = None, bytes_read: int = 0) -> str:
	chunk = reader.read(chunk_size)
	bytes_read += chunk_size
	if previous_chunk is not None:
		chunk = previous_chunk + chunk
	try:
		return chunk.decode()
	except UnicodeDecodeError:
		if bytes_read > max_window_size:
			raise UnicodeError(f"Unable to decode frame after reading {bytes_read:,} bytes")
		log.info(f"Decoding error with {bytes_read:,} bytes, reading another chunk")
		return read_and_decode(reader, chunk_size, max_window_size, chunk, bytes_read)


def read_lines_zst(file_name: str) -> Iterator[Tuple[str, int]]:
	with open(file_name, 'rb') as file_handle:
		buffer = ''
		reader = zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(file_handle)
		while True:
			chunk = read_and_decode(reader, 2**27, (2**29) * 2)

			if not chunk:
				break
			lines = (buffer + chunk).split("\n")

			for line in lines[:-1]:
				yield line, file_handle.tell()

			buffer = lines[-1]

		reader.close()

def return_redd_objects(path: str) -> List[Dict[str, Any]]:
	"""
	DEPRECATED: Load entire .zst file into memory.

	This function loads all Pushshift data into memory, which is inefficient
	for large datasets (>1GB compressed, >10GB uncompressed).

	Use stream_to_database() instead for memory-efficient PostgreSQL streaming.

	Migration path:
		OLD: objects = return_redd_objects('/path/to/file.zst')
		NEW: result = stream_to_database('/path/to/file.zst', connection_string, 'posts')

	This function will be removed in a future phase after all callers are migrated.
	"""
	print_warning("return_redd_objects() is deprecated - use stream_to_database() for PostgreSQL streaming")

	file_path = path
	file_size = os.stat(file_path).st_size
	file_lines = 0
	file_bytes_processed = 0
	created = None
	# field = "subreddit"
	# value = "example"
	bad_lines = 0
	objects = []
	authors = {}

	# try:
	for line, file_bytes_processed in read_lines_zst(file_path):
		try:
			obj = json.loads(line)
			created = datetime.utcfromtimestamp(int(obj['created_utc']))
			# temp = obj[field] == value
			objects.append(obj)

		except (KeyError, json.JSONDecodeError) as err:
			bad_lines += 1
		file_lines += 1

		if file_lines % 1000 == 0:
			progress_percent = (file_bytes_processed / file_size) * 100
			print(f"\rReading data: {progress_percent:.0f}% complete", end="")
	print(f"\rReading data: Complete - {file_lines:,} objects loaded ({bad_lines:,} errors)")
	return objects


def stream_to_database(
    zst_file_path: str,
    connection_string: str,
    record_type: str,
    filters: Optional[Dict[str, Any]] = None,
    batch_size: int = 10000,
    processor: Optional[Any] = None,
    db: Optional[PostgresDatabase] = None
) -> Dict[str, Any]:
    """
    Stream .zst file content directly to PostgreSQL database using COPY protocol.

    Replaces the memory-intensive return_redd_objects() with streaming database ingestion
    for memory-efficient processing of large Pushshift datasets.

    Args:
        zst_file_path: Path to the .zst file to process
        connection_string: PostgreSQL connection string (postgresql://user:pass@host:port/dbname)
        record_type: Type of records ('posts' or 'comments')
        filters: Optional filtering criteria (for future use)
        batch_size: Number of records to process per batch (default: 10,000)
        processor: Optional incremental_processor instance for memory monitoring
        db: Optional PostgresDatabase instance to reuse (avoids connection overhead)

    Returns:
        Dict with statistics: records_processed, records_filtered, database_size_mb, processing_time
    """
    start_time = time.time()

    # Validate inputs
    if not os.path.exists(zst_file_path):
        raise FileNotFoundError(f"Source file not found: {zst_file_path}")

    if record_type not in ['posts', 'comments']:
        raise ValueError(f"Invalid record_type: {record_type}. Must be 'posts' or 'comments'")

    # Initialize statistics
    file_size = os.stat(zst_file_path).st_size
    file_lines = 0
    file_bytes_processed = 0
    bad_lines = 0
    records_processed = 0
    records_filtered = 0
    batch_records = []
    last_progress_update = 0

    filters = filters or {}

    print_info(f"Streaming {record_type} from {os.path.basename(zst_file_path)} to database...")

    # PERFORMANCE FIX: Reuse existing database connection if provided
    # This eliminates 1-2s connection pool startup overhead per file
    should_close_db = False
    if db is None:
        should_close_db = True
        db = PostgresDatabase(connection_string, workload_type='batch_insert')

    try:
            
            # Process .zst file in streaming fashion
            for line, file_bytes_processed in read_lines_zst(zst_file_path):
                try:
                    # Parse JSON object
                    obj = json.loads(line)
                    
                    # Apply filtering if provided (preserves existing filtering patterns)
                    if _should_include_record(obj, filters, record_type):
                        batch_records.append(obj)
                        records_processed += 1
                    else:
                        records_filtered += 1
                        
                except (KeyError, json.JSONDecodeError) as err:
                    bad_lines += 1
                    
                file_lines += 1
                
                # Batch processing for performance
                if len(batch_records) >= batch_size:
                    _flush_batch_to_database(db, batch_records, record_type)
                    batch_records.clear()

                    # Memory monitoring integration
                    if processor:
                        processor.check_memory_usage()

                # Progress tracking (every 10,000 lines or 5% file progress)
                if (file_lines % 10000 == 0 or
                    time.time() - last_progress_update > 2.0):

                    progress_percent = (file_bytes_processed / file_size) * 100
                    records_rate = records_processed / (time.time() - start_time) if time.time() > start_time else 0

                    print(f"\rStreaming {record_type}: {progress_percent:.1f}% | "
                          f"{records_processed:,} processed | "
                          f"{records_rate:.0f} records/sec", end="")

                    last_progress_update = time.time()

            # Flush remaining batch
            if batch_records:
                _flush_batch_to_database(db, batch_records, record_type)
                batch_records.clear()

            # PERFORMANCE FIX: ANALYZE removed - will be called once at end of ALL imports
            # Running ANALYZE after every file was causing 50s waste per subreddit
            # ANALYZE is now called once after index creation in redarch.py

            # Final statistics
            processing_time = time.time() - start_time
            db_info = db.get_database_info()
            
            print(f"\rStreaming {record_type}: Complete - "
                  f"{records_processed:,} records processed "
                  f"({records_filtered:,} filtered, {bad_lines:,} errors) "
                  f"in {processing_time:.1f}s")

            return {
                'records_processed': records_processed,
                'records_filtered': records_filtered,
                'bad_lines': bad_lines,
                'total_lines': file_lines,
                'database_size_mb': db_info['db_size_mb'],
                'processing_time': processing_time,
                'records_per_second': records_processed / processing_time if processing_time > 0 else 0
            }

    except Exception as e:
        print_error(f"Failed to stream {record_type} to database: {e}")
        raise PostgresDatabaseError(f"Streaming failed: {e}") from e
    finally:
        # Only close database if we created it in this function
        if should_close_db and db:
            db.cleanup()


def _should_include_record(obj: Dict[str, Any], filters: Dict[str, Any], record_type: str) -> bool:
    """
    Apply filtering criteria to determine if record should be included.
    
    Note: Currently filtering is done later in HTML generation stage,
    but this provides infrastructure for database-level filtering if needed.
    """
    # Future enhancement: Add min_score, min_comments filtering here if desired
    # For now, include all records to match existing behavior
    return True


def _flush_batch_to_database(db: PostgresDatabase, batch_records: List[Dict[str, Any]], record_type: str) -> None:
    """Flush accumulated records to PostgreSQL database with error handling.

    Args:
        db: PostgresDatabase instance
        batch_records: List of records to insert
        record_type: Either 'posts' or 'comments'
    """
    try:
        if record_type == 'posts':
            successful, failed, batch_failed_ids = db.insert_posts_batch(batch_records)
        elif record_type == 'comments':
            successful, failed = db.insert_comments_batch(batch_records)
        else:
            raise ValueError(f"Invalid record_type: {record_type}")

        # Log any insertion errors
        if failed > 0:
            print_warning(f"Database insertion: {failed} errors out of {successful + failed} records")

    except Exception as e:
        print_error(f"Failed to flush {len(batch_records)} {record_type} to database: {e}")
        raise


if __name__=="__main__":
	"""
	Example: Stream .zst file to PostgreSQL database.

	OLD (deprecated): python watchful.py input.zst output.json
	NEW (recommended): python watchful.py input.zst posts

	Usage:
		python watchful.py <input.zst> <record_type>

	Arguments:
		input.zst: Path to compressed Pushshift data file
		record_type: Either 'posts' or 'comments'

	Environment Variables:
		DATABASE_URL: PostgreSQL connection string (required)
			Example: postgresql://user:password@localhost:5432/archive_db
	"""
	if len(sys.argv) < 3:
		print("ERROR: Insufficient arguments")
		print()
		print("Usage: python watchful.py <input.zst> <record_type>")
		print("  record_type: 'posts' or 'comments'")
		print()
		print("Environment Variables:")
		print("  DATABASE_URL: PostgreSQL connection string (required)")
		print("    Example: postgresql://user:password@localhost:5432/archive_db")
		print()
		print("Example:")
		print("  export DATABASE_URL='postgresql://archiver:password@localhost:5432/archive_db'")
		print("  python watchful.py example_posts.zst posts")
		sys.exit(1)

	inpath = sys.argv[1]
	record_type = sys.argv[2]

	# Validate arguments
	if not os.path.exists(inpath):
		print_error(f"Input file not found: {inpath}")
		sys.exit(1)

	if record_type not in ['posts', 'comments']:
		print_error(f"Invalid record_type: {record_type}. Must be 'posts' or 'comments'")
		sys.exit(1)

	# Get PostgreSQL connection string
	connection_string = get_postgres_connection_string()

	# Stream to database
	print_info(f"Streaming {record_type} from {os.path.basename(inpath)} to PostgreSQL...")
	try:
		result = stream_to_database(inpath, connection_string, record_type)

		# Print results
		print()
		print_success("Streaming completed successfully!")
		print(f"  Records processed: {result['records_processed']:,}")
		print(f"  Records filtered: {result['records_filtered']:,}")
		print(f"  Bad lines: {result['bad_lines']:,}")
		print(f"  Database size: {result['database_size_mb']:.1f} MB")
		print(f"  Processing time: {result['processing_time']:.1f}s")
		print(f"  Records/sec: {result['records_per_second']:.0f}")

	except Exception as e:
		print_error(f"Streaming failed: {e}")
		sys.exit(1)
