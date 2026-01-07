"""
ABOUTME: Voat-specific SQL parser for MariaDB dump files
ABOUTME: Parses INSERT statements with proper escape handling, yields row dicts

Handles MariaDB-specific SQL syntax that PostgreSQL cannot parse directly:
- Backtick quoting for identifiers
- Backslash escaping in strings (\\, \', \r, \n, \t)
- Multi-row INSERT statements with VALUES tuples
- NULL values and numeric types
"""

import gzip
import logging
import re
from typing import Iterator, Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


class VoatSQLParser:
    """
    Parse MariaDB INSERT statements from Voat SQL dump files.

    Uses a state machine to correctly handle string escaping and extract
    VALUES tuples from multi-row INSERT statements.
    """

    # Hardcoded column mappings for Voat tables (from CREATE TABLE statements)
    COLUMN_MAPS = {
        'submission': [
            'submissionid', 'archiveDate', 'commentCount', 'content',
            'creationDate', 'domain', 'downCount', 'formattedContent',
            'isAdult', 'isAnonymized', 'isDeleted', 'lastEditDate',
            'subverse', 'sum', 'thumbnail', 'title', 'type', 'upCount',
            'url', 'userName', 'views', 'archivedLink', 'archivedDomain',
            'deletedMeaning', 'fetchCount', 'lastFetched', 'flags'
        ],
        'comment': [
            'commentid', 'content', 'creationDate', 'downCount',
            'formattedContent', 'isAnonymized', 'isCollapsed', 'isDeleted',
            'isDistinguished', 'isOwner', 'isSaved', 'isSubmitter',
            'lastEditDate', 'parentid', 'submissionid', 'subverse',
            'sum', 'upCount', 'userName', 'vote', 'fetchCount', 'lastFetched'
        ]
    }

    # MariaDB escape sequences
    ESCAPE_MAP = {
        "'": "'",
        "\\": "\\",
        "r": "\r",
        "n": "\n",
        "t": "\t",
        "0": "\x00",
        "b": "\b",
        "Z": "\x1a",
    }

    def stream_rows(self, file_path: str, table_name: str, filter_subverses: Optional[List[str]] = None) -> Iterator[Dict[str, Any]]:
        """
        Stream parsed rows from a Voat SQL dump file.

        Args:
            file_path: Path to .sql.gz file
            table_name: Table to extract ('submission' or 'comment')
            filter_subverses: Optional list of subverses to filter (case-insensitive, faster with early skip)

        Yields:
            dict: Row data with column names as keys
        """
        if table_name not in self.COLUMN_MAPS:
            raise ValueError(f"Unknown table: {table_name}. Expected: {list(self.COLUMN_MAPS.keys())}")

        columns = self.COLUMN_MAPS[table_name]
        insert_pattern = re.compile(rf"INSERT INTO `{table_name}` VALUES", re.IGNORECASE)

        # Find subverse column index for quick filtering
        subverse_idx = columns.index('subverse') if 'subverse' in columns else -1

        # Convert filter to lowercase for case-insensitive comparison
        filter_lower = [s.lower() for s in filter_subverses] if filter_subverses else None

        row_count = 0
        skipped_count = 0
        error_count = 0

        logger.info(f"Parsing {table_name} from {file_path}" +
                   (f" (filtering for: {', '.join(filter_subverses)})" if filter_subverses else ""))

        try:
            # Test if file can be opened (catches corrupted gzip files early)
            try:
                test_f = gzip.open(file_path, 'rt', encoding='utf-8', errors='replace')
                test_f.readline()
                test_f.close()
            except Exception as e:
                logger.error(f"Cannot read {file_path}: {e} (corrupted file)")
                return  # Exit generator early

            with gzip.open(file_path, 'rt', encoding='utf-8', errors='replace') as f:
                buffer = ""
                in_split_format = False  # Track if we're in split file format (tuples without INSERT)
                accumulating_tuple = False  # Track if we're accumulating a multi-line tuple

                for line in f:
                    # Skip comments and empty lines
                    stripped = line.strip()
                    if not stripped or stripped.startswith('--') or stripped.startswith('/*'):
                        continue

                    # Skip CREATE TABLE and other DDL statements
                    if stripped.upper().startswith(('CREATE ', 'DROP ', 'ALTER ', 'SET ', 'USE ')):
                        continue

                    # Look for INSERT statement (standard format)
                    if insert_pattern.search(line):
                        # Find VALUES position
                        values_pos = line.upper().find('VALUES')
                        if values_pos == -1:
                            continue

                        # Start parsing from after VALUES
                        buffer = line[values_pos + 6:]
                        in_split_format = False

                    # Split file format: lines starting with '(' are tuples (may span multiple lines)
                    elif stripped.startswith('('):
                        # New tuple starting
                        if accumulating_tuple:
                            # We were accumulating previous tuple but hit new one
                            # This means previous tuple was actually complete
                            # Reset and start new tuple
                            accumulating_tuple = False
                            in_split_format = False
                        buffer = line  # Start fresh buffer with new tuple
                        in_split_format = True
                    elif accumulating_tuple or in_split_format:
                        # Continuation of multi-line tuple
                        buffer += line
                        # Don't continue - let parser below attempt to parse

                    else:
                        # Not a recognized format, skip
                        continue

                    # Parse all tuples in buffer (works for both formats)
                    if buffer:
                        # Parse all tuples in this buffer
                        while True:
                            # Find start of tuple
                            paren_start = buffer.find('(')
                            if paren_start == -1:
                                break

                            # OPTIMIZATION: Quick filter check before full parse
                            if filter_lower and subverse_idx >= 0:
                                try:
                                    # Quick extract just the subverse field
                                    subverse_value = self._quick_extract_field(buffer, paren_start, subverse_idx)
                                    if subverse_value and str(subverse_value).lower() not in filter_lower:
                                        # Skip this row - find the end and move on
                                        _, end_pos = self._parse_values_tuple(buffer, paren_start)
                                        buffer = buffer[end_pos:]
                                        skipped_count += 1
                                        if not buffer.strip():
                                            if in_split_format:
                                                in_split_format = False
                                            break
                                        if not in_split_format and buffer.strip().startswith(';'):
                                            break
                                        if in_split_format:
                                            in_split_format = False
                                            break
                                        continue
                                except:
                                    pass  # Fall through to full parse if quick extract fails

                            # Parse the tuple (either no filter, or filter matched)
                            try:
                                values, end_pos = self._parse_values_tuple(buffer, paren_start)

                                # Check if tuple is incomplete (multi-line in split format)
                                if values and in_split_format and len(values) < len(columns):
                                    # Incomplete tuple - need more lines
                                    # Don't clear buffer, keep accumulating
                                    accumulating_tuple = True
                                    break  # Exit inner while, continue outer for loop to read more lines

                                if values and len(values) == len(columns):
                                    row_dict = dict(zip(columns, values))

                                    # Apply filter after full parse (in case quick extract failed)
                                    if filter_lower and subverse_idx >= 0:
                                        subverse_value = values[subverse_idx] if subverse_idx < len(values) else None
                                        if subverse_value and str(subverse_value).lower() not in filter_lower:
                                            skipped_count += 1
                                            buffer = buffer[end_pos:]
                                            if not buffer.strip():
                                                if in_split_format:
                                                    in_split_format = False
                                                break
                                            if not in_split_format and buffer.strip().startswith(';'):
                                                break
                                            if in_split_format:
                                                in_split_format = False
                                                break
                                            continue

                                    row_count += 1
                                    yield row_dict
                                    # Move past this tuple after successful parse
                                    buffer = buffer[end_pos:]
                                    # Reset accumulation flags after successful parse
                                    if accumulating_tuple:
                                        accumulating_tuple = False
                                    if in_split_format:
                                        in_split_format = False
                                elif values:
                                    # Column count mismatch for non-split format or wrong count
                                    error_count += 1
                                    if error_count <= 5:
                                        logger.warning(
                                            f"Column count mismatch: got {len(values)}, "
                                            f"expected {len(columns)} for {table_name}"
                                        )
                                    # Move past this tuple
                                    buffer = buffer[end_pos:]

                                # Check for more tuples or end of statement
                                # In split format, we process one tuple per line and continue to next line
                                # In standard format, we check for ';' to end the INSERT statement
                                if not buffer.strip():
                                    if in_split_format:
                                        in_split_format = False  # Reset for next tuple
                                    break
                                if not in_split_format and buffer.strip().startswith(';'):
                                    break
                                if in_split_format:
                                    # In split format, one tuple per multi-line block, reset after parsing
                                    in_split_format = False
                                    break

                            except Exception as e:
                                # In split format with incomplete tuple, keep accumulating
                                if in_split_format and 'find closing' in str(e).lower():
                                    # Tuple incomplete, need more lines
                                    break  # Exit inner while, continue reading lines

                                error_count += 1
                                if error_count <= 5:
                                    logger.warning(f"Parse error at row ~{row_count}: {e}")
                                elif error_count == 6:
                                    logger.warning(f"Suppressing further parse errors (total so far: {error_count})")

                                # Try to recover by finding next tuple
                                # Skip past the failed tuple to continue processing
                                try:
                                    # Try to find end of current tuple first
                                    next_comma = buffer.find('),', paren_start)
                                    next_semicolon = buffer.find(');', paren_start)

                                    if next_comma != -1 and (next_semicolon == -1 or next_comma < next_semicolon):
                                        # Found comma, skip past it
                                        buffer = buffer[next_comma + 2:]
                                    elif next_semicolon != -1:
                                        # Found semicolon, end of statement
                                        buffer = buffer[next_semicolon + 2:]
                                        if not buffer.strip():
                                            break
                                    else:
                                        # Can't find end, try to find next opening paren
                                        next_paren = buffer.find('(', paren_start + 1)
                                        if next_paren == -1:
                                            break
                                        buffer = buffer[next_paren:]
                                except:
                                    # Recovery failed, bail out
                                    break

        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            raise

        if filter_subverses:
            logger.info(f"Parsed {row_count} rows from {table_name} (skipped {skipped_count} filtered), {error_count} errors")
        else:
            logger.info(f"Parsed {row_count} rows from {table_name}, {error_count} errors")

    def _quick_extract_field(self, text: str, start: int, field_idx: int) -> Optional[Any]:
        """
        Quickly extract a single field from a VALUES tuple without full parsing.
        Used for pre-filtering to skip unwanted rows faster.

        Args:
            text: String containing the tuple
            start: Position of opening parenthesis
            field_idx: Index of field to extract (0-based)

        Returns:
            The field value, or None if extraction fails
        """
        i = start + 1  # Skip opening paren
        field_count = 0
        current = ""
        in_string = False
        paren_depth = 0

        while i < len(text) and field_count <= field_idx:
            char = text[i]

            # Handle string escaping
            if char == '\\' and in_string and i + 1 < len(text):
                i += 2  # Skip escape sequence
                if field_count == field_idx:
                    current += text[i-1]
                continue

            # Handle quotes
            if char == "'":
                if in_string:
                    # Check for doubled quote
                    if i + 1 < len(text) and text[i + 1] == "'":
                        if field_count == field_idx:
                            current += "'"
                        i += 2
                        continue
                    else:
                        in_string = False
                else:
                    in_string = True
                i += 1
                continue

            # Not in string - track structure
            if not in_string:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    if paren_depth == 0:
                        # End of tuple
                        if field_count == field_idx:
                            return self._convert_value(current.strip())
                        break
                    paren_depth -= 1
                elif char == ',' and paren_depth == 0:
                    # Field separator
                    if field_count == field_idx:
                        return self._convert_value(current.strip())
                    field_count += 1
                    current = ""
                    i += 1
                    continue

            # Collect characters for target field
            if field_count == field_idx:
                current += char

            i += 1

        return None

    def _parse_values_tuple(self, text: str, start: int) -> Tuple[List[Any], int]:
        """
        Parse a single VALUES tuple using state machine.

        Args:
            text: String containing the tuple
            start: Position of opening parenthesis

        Returns:
            Tuple of (list of values, end position after closing paren)
        """
        values = []
        current = ""
        state = "OUTSIDE"  # OUTSIDE, IN_STRING, ESCAPE
        was_quoted = False  # Track if current value was in quotes
        i = start + 1  # Skip opening paren

        while i < len(text):
            char = text[i]

            if state == "ESCAPE":
                # Handle escape sequences
                current += self.ESCAPE_MAP.get(char, char)
                state = "IN_STRING"

            elif state == "IN_STRING":
                if char == '\\':
                    state = "ESCAPE"
                elif char == "'":
                    # Check for doubled quote (MySQL escape)
                    if i + 1 < len(text) and text[i + 1] == "'":
                        current += "'"
                        i += 1
                    else:
                        state = "OUTSIDE"
                else:
                    current += char

            elif char == "'":
                state = "IN_STRING"
                was_quoted = True

            elif char == ',':
                values.append(self._parse_value(current.strip(), was_quoted))
                current = ""
                was_quoted = False

            elif char == ')':
                values.append(self._parse_value(current.strip(), was_quoted))
                return values, i + 1

            else:
                current += char

            i += 1

        # Shouldn't reach here for valid SQL
        return values, len(text)

    def _parse_value(self, value: str, was_quoted: bool = False) -> Any:
        """
        Convert a parsed string value to appropriate Python type.

        Args:
            value: Raw string value from SQL
            was_quoted: True if value was inside single quotes

        Returns:
            Converted value (None, int, float, or str)
        """
        # NULL keyword (unquoted) becomes None
        if value.upper() == 'NULL':
            return None

        # Empty unquoted value is None, but empty quoted string is ''
        if not value and not was_quoted:
            return None

        # Try integer
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        # Return as string
        return value
