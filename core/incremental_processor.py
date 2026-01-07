#!/usr/bin/env python
"""
Incremental processing system for Redd-Archiver archives.
Handles graceful shutdown, state management, and memory monitoring.

MIGRATION: Migrated from JSON-based state to PostgreSQL database storage.
JSON progress files (.archive-progress.json) are being deprecated in favor
of PostgreSQL processing_metadata table for better reliability and resume capability.
"""

import os
import json
import signal
import sys
import gc
import psutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from utils.simple_json_utils import save_user_activity, merge_and_write_json, merge_user_activity


def get_timestamp() -> str:
    """Generate timestamp for console output"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class IncrementalProcessor:
    """
    Manages incremental archive processing with robust error handling,
    progress tracking, and automatic resume functionality.
    """
    
    def __init__(self, output_dir: str, max_memory_gb: float = 0):
        # ✅ FIX: Always use absolute path to prevent issues when working directory changes
        self.output_dir = os.path.abspath(output_dir)
        
        # 🧠 MEMORY MANAGEMENT: 0 = unlimited, >0 = enable limits
        self.memory_monitoring_enabled = max_memory_gb > 0
        if self.memory_monitoring_enabled:
            self.max_memory_bytes = max_memory_gb * 1024 * 1024 * 1024
            # Enhanced thresholds for proactive cleanup
            self.info_threshold = 0.60      # 60% - log memory usage
            self.warning_threshold = 0.70   # 70% - trigger proactive cleanup
            self.critical_threshold = 0.85  # 85% - aggressive cleanup
            self.emergency_threshold = 0.95 # 95% - emergency shutdown
            print(f"Memory monitoring enabled with {max_memory_gb}GB limit")
        else:
            self.max_memory_bytes = float('inf')  # Unlimited
            print("Memory monitoring disabled (unlimited mode)")
        
        # Simple user activity tracking file path (using absolute path)
        self.user_activity_file = os.path.join(self.output_dir, '.archive-user-activity.json')
        
        # Processing state
        self.shutdown_requested = False
        self.current_subreddit = None
        self.current_phase = 'initialization'
        self.start_time = datetime.now()
        
        # Progress tracking
        self.completed_subreddits = []
        self.failed_subreddits = []
        self.remaining_subreddits = []
        self.total_subreddits = 0
        
        # User tracking (lightweight)
        self.user_activity = {
            'total_unique_users': set(),
            'users_by_subreddit': {},
            'high_activity_users': [],  # >100 posts/comments
            'user_pages_generated': False
        }
        
        # File paths (using absolute output_dir)
        self.progress_file = os.path.join(self.output_dir, '.archive-progress.json')
        self.user_activity_file = os.path.join(self.output_dir, '.archive-user-activity.json')
        self.completed_file = os.path.join(self.output_dir, '.archive-completed.json')
        self.emergency_file = os.path.join(self.output_dir, '.archive-emergency.json')
        
        # Register signal handlers
        self._setup_signal_handlers()
        
        timestamp = get_timestamp()
        print(f"[{timestamp}] Incremental processor initialized")
        print(f"[{timestamp}] Memory limit: {max_memory_gb}GB")
        print(f"[{timestamp}] Output directory: {output_dir}")

    def _setup_signal_handlers(self):
        """Register signal handlers for graceful shutdown"""
        signal.signal(signal.SIGINT, self._handle_shutdown)   # Ctrl+C
        signal.signal(signal.SIGTERM, self._handle_shutdown)  # Termination
        
        # Windows doesn't have SIGUSR1/SIGUSR2, so only register on Unix
        try:
            signal.signal(signal.SIGUSR1, self._handle_status_request)  # Status request
        except AttributeError:
            pass  # Windows compatibility
    
    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown on Ctrl+C or termination"""
        print(f"\nShutdown requested (signal {signum})")
        print("Saving current progress...")
        
        self.shutdown_requested = True
        
        # Save current state immediately
        self._save_progress_state('interrupted')
        
        # Check if current subreddit is nearly complete (>90%)
        if self.current_subreddit and self._subreddit_90_percent_complete():
            print(f"Finishing {self.current_subreddit} (>90% complete)...")
            try:
                # Allow current subreddit to finish (with timeout)
                return  # Let the main loop handle completion
            except Exception as e:
                print(f"Error finishing subreddit: {e}")
        
        print("Progress saved successfully")
        print(f"Resume with: python redarch.py [args] --resume")
        sys.exit(0)
    
    def _handle_status_request(self, signum, frame):
        """Handle status request signal (Unix only)"""
        self._print_status()
    
    def _subreddit_90_percent_complete(self) -> bool:
        """Check if current subreddit processing is >90% complete"""
        # This would be implemented based on the specific processing phase
        # For now, return False to save immediately
        return False
    
    def check_memory_usage(self) -> float:
        """Monitor memory usage with enhanced multi-tier management (PostgreSQL backend)"""
        # If memory monitoring is disabled, just return 0 and do nothing
        if not self.memory_monitoring_enabled:
            return 0.0

        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            current_memory = memory_info.rss

            memory_percent = current_memory / self.max_memory_bytes
            memory_gb = current_memory / (1024**3)

            # 🧠 MULTI-TIER MEMORY MANAGEMENT
            if memory_percent > self.emergency_threshold:
                # EMERGENCY: Immediate shutdown
                print(f"[EMERGENCY] {memory_percent:.1%} of limit ({memory_gb:.2f}GB) - EMERGENCY SHUTDOWN")
                self._emergency_save_and_exit()

            elif memory_percent > self.critical_threshold:
                # CRITICAL: Aggressive cleanup and potential emergency
                print(f"[CRITICAL] {memory_percent:.1%} of limit ({memory_gb:.2f}GB)")
                print("Triggering aggressive garbage collection...")

                # Multiple-stage garbage collection
                collected_1 = gc.collect()
                collected_2 = gc.collect()
                collected_3 = gc.collect()  # Third pass for stubborn cycles

                # Check again after aggressive cleanup
                new_memory = psutil.Process().memory_info().rss
                new_percent = new_memory / self.max_memory_bytes
                new_gb = new_memory / (1024**3)

                print(f"Post-cleanup memory: {new_percent:.1%} ({new_gb:.2f}GB), collected: {collected_1+collected_2+collected_3} objects")

                if new_percent > self.emergency_threshold:
                    print("[EMERGENCY SAVE] Memory still critical after aggressive GC")
                    self._emergency_save_and_exit()
                elif new_percent > self.critical_threshold:
                    print("[WARNING] Memory still high after GC - consider reducing processing scope")

                return new_percent

            elif memory_percent > self.warning_threshold:
                # WARNING: Proactive cleanup
                print(f"[WARNING] {memory_percent:.1%} of limit ({memory_gb:.2f}GB) - proactive cleanup")

                collected = gc.collect()

                # Check improvement
                new_memory = psutil.Process().memory_info().rss
                new_percent = new_memory / self.max_memory_bytes
                improvement = memory_percent - new_percent

                if improvement > 0.05:  # 5% improvement
                    print(f"Proactive cleanup successful: {new_percent:.1%} (freed {improvement:.1%})")
                else:
                    print(f"Limited improvement from cleanup: {new_percent:.1%} (freed {improvement:.1%})")

                return new_percent

            elif memory_percent > self.info_threshold:
                # INFO: Just log for monitoring
                print(f"[MEMORY] {memory_percent:.1%} of limit ({memory_gb:.2f}GB)")

            return memory_percent

        except Exception as e:
            print(f"[WARNING] Error checking memory usage: {e}")
            return 0.0
    
    def trigger_proactive_cleanup(self):
        """Trigger proactive cleanup operations when memory gets high (PostgreSQL backend)"""
        print("[PROACTIVE CLEANUP] Reducing memory footprint...")

        # Clear any accumulated data if we can access it
        # This is called from the main processing loop when needed
        collected = gc.collect()

        # Get memory status after cleanup
        try:
            process = psutil.Process()
            current_memory = process.memory_info().rss
            memory_after = current_memory / self.max_memory_bytes

            print(f"Proactive cleanup complete: {memory_after:.1%} memory usage, {collected} objects collected")

            return memory_after

        except Exception as e:
            print(f"Error in proactive cleanup: {e}")
            return 0.0
    
    def _emergency_save_and_exit(self):
        """Emergency save when OOM is imminent - saves to progress file"""
        print("[OUT OF MEMORY] Emergency shutdown")
        
        try:
            # Save emergency state to the main progress file
            self.current_phase = 'emergency_oom_shutdown'
            self._save_progress_state('emergency_oom_shutdown', is_emergency=True)
                
            print(f"Emergency state saved to {self.progress_file}")
            print("Resume with: python redarch.py [args] --resume")
            
        except Exception as e:
            print(f"[ERROR] Failed to save emergency state: {e}")
        
        sys.exit(1)
    
    def detect_processing_state(self) -> Tuple[str, Optional[Dict]]:
        """Auto-detect if processing was interrupted and where to resume"""
        
        # Check for progress file (now handles both normal and emergency states)
        if os.path.exists(self.progress_file):
            with open(self.progress_file) as f:
                state = json.load(f)
                
            current_phase = state.get('phase', 'unknown')
            is_emergency = state.get('is_emergency', False)

            if current_phase == 'emergency_oom_shutdown' or is_emergency:
                print("[EMERGENCY STATE] Detected from previous OOM shutdown")
                print(f"Previous failure: {state.get('timestamp')}")
                if 'memory_usage_at_failure' in state:
                    print(f"Memory at failure: {state.get('memory_usage_at_failure')}")
                return 'resume_from_emergency', state
                
            elif current_phase == 'subreddit_processing' or current_phase in ['interrupted', 'initialized']:
                print("Detected interrupted subreddit processing")
                print(f"Completed: {len(state.get('completed_subreddits', []))} subreddits")
                print(f"Remaining: {len(state.get('remaining_subreddits', []))} subreddits")
                return 'resume_subreddits', state
                
            elif current_phase == 'user_page_generation':
                print("Detected interrupted user page generation")
                return 'resume_users', state
                
            elif current_phase == 'complete':
                print("[SUCCESS] Previous processing completed successfully")
                return 'already_complete', state
        
        # Also check for legacy emergency file (backwards compatibility)
        if os.path.exists(self.emergency_file):
            print("[LEGACY EMERGENCY STATE] Found old emergency file")
            with open(self.emergency_file) as f:
                emergency_state = json.load(f)
            print(f"Previous failure: {emergency_state.get('timestamp')}")
            print(f"Memory at failure: {emergency_state.get('memory_usage_at_failure')}")
            
            # Move emergency file to backup
            backup_file = f"{self.emergency_file}.backup"
            os.rename(self.emergency_file, backup_file)
            print(f"Emergency file backed up to {backup_file}")
            
            return 'resume_from_emergency', emergency_state
        
        print("Starting fresh processing")
        return 'start_fresh', None
    
    def _validate_database_state(self, state: Dict) -> Dict[str, Any]:
        """
        PostgreSQL backend does not require SQLite database validation.

        This method checked for .archive-temp-posts.db, .archive-temp-comments.db,
        and .archive-users.db files which don't exist with PostgreSQL.

        For PostgreSQL health checking, use postgres_db.health_check() instead.
        """
        # Always return valid for PostgreSQL (no SQLite files to check)
        return {
            'valid': True,
            'message': 'PostgreSQL backend - no SQLite validation needed',
            'database_files': {}
        }
    
    def _collect_database_statistics(self) -> Optional[Dict[str, Any]]:
        """
        PostgreSQL backend uses database-backed statistics collection.

        This method collected statistics from .archive-temp-posts.db,
        .archive-temp-comments.db, and .archive-users.db files.

        For PostgreSQL statistics, use postgres_db.get_database_info() instead.
        """
        # Return minimal stats for PostgreSQL (statistics queried directly from database)
        return {
            'timestamp': datetime.now().isoformat(),
            'databases': {},
            'total_records': 0,
            'total_size_mb': 0.0,
            'note': 'PostgreSQL backend - use postgres_db.get_database_info()'
        }
    
    def detect_and_recover_database_cleanup(self) -> bool:
        """
        PostgreSQL backend does not require SQLite database cleanup detection.

        This method checked for missing .archive-temp-posts.db and .archive-temp-comments.db files.
        PostgreSQL doesn't use temporary database files, so no cleanup detection is needed.
        """
        # Always return True for PostgreSQL (no SQLite cleanup to detect)
        return True
    
    def _assess_database_recovery_options(self, state: Dict, missing_dbs: List[str]) -> Dict[str, Any]:
        """
        PostgreSQL backend does not require SQLite recovery assessment.

        This method assessed recovery options when SQLite database files were missing.
        PostgreSQL doesn't use temporary database files, so recovery assessment is not needed.
        """
        # Always return successful recovery for PostgreSQL (no temp databases to check)
        return {
            'can_recover': True,
            'recovery_method': 'PostgreSQL backend - no SQLite recovery needed',
            'reason': ''
        }
    
    def cleanup_corrupted_databases(self) -> bool:
        """
        PostgreSQL backend does not require SQLite database cleanup.

        This method cleaned up corrupted .archive-temp-posts.db and .archive-temp-comments.db files.
        PostgreSQL doesn't use temporary database files, so cleanup is not needed.

        For PostgreSQL health checking, use postgres_db.health_check() instead.
        """
        # Always return True for PostgreSQL (no SQLite databases to clean up)
        print("[INFO] PostgreSQL backend - no SQLite cleanup needed")
        return True
    
    def _get_current_progress_file_path(self):
        """Get the correct progress file path based on current working directory"""
        # If we're already in the output directory (after os.chdir), use relative path
        current_dir = os.getcwd()
        if current_dir.endswith(os.path.basename(self.output_dir.rstrip('/'))):
            return '.archive-progress.json'
        else:
            # We're still in the original directory, use full path
            return self.progress_file
    
    def _save_progress_state(self, phase: str, is_emergency: bool = False):
        """
        Save current progress state to JSON file.

        NOTE: This method uses PostgreSQL-based progress tracking
        in a future update using postgres_db.update_progress_status().
        """
        try:
            state = {
                'phase': phase,
                'timestamp': datetime.now().isoformat(),
                'start_time': self.start_time.isoformat(),
                'current_subreddit': self.current_subreddit,
                'completed_subreddits': self.completed_subreddits,
                'failed_subreddits': self.failed_subreddits,
                'remaining_subreddits': self.remaining_subreddits,
                'total_subreddits': self.total_subreddits,
                'memory_usage_mb': round(psutil.Process().memory_info().rss / (1024**2), 1)
            }

            # Add emergency-specific fields if this is an emergency save
            if is_emergency:
                state['is_emergency'] = True
                state['memory_usage_at_failure'] = f"{psutil.Process().memory_info().rss / (1024**3):.2f}GB"
                state['memory_limit'] = f"{self.max_memory_bytes / (1024**3):.2f}GB"
            
            # Calculate progress and ETA
            if self.total_subreddits > 0:
                progress_percent = len(self.completed_subreddits) / self.total_subreddits * 100
                state['progress_percent'] = round(progress_percent, 1)
                
                # Simple ETA calculation
                elapsed = datetime.now() - self.start_time
                if len(self.completed_subreddits) > 0:
                    avg_time_per_subreddit = elapsed.total_seconds() / len(self.completed_subreddits)
                    remaining_time = avg_time_per_subreddit * len(self.remaining_subreddits)
                    eta = datetime.now().timestamp() + remaining_time
                    state['estimated_completion'] = datetime.fromtimestamp(eta).isoformat()
            
            # ✅ FIXED: Handle working directory changes - use dynamic path calculation
            current_progress_file = self._get_current_progress_file_path()
            
            # Create directory if needed
            progress_dir = os.path.dirname(current_progress_file)
            if progress_dir:
                os.makedirs(progress_dir, exist_ok=True)
            
            # Save the file
            with open(current_progress_file, 'w') as f:
                json.dump(state, f, indent=2)
                
            print(f"Progress state saved to {current_progress_file}")
                
        except Exception as e:
            print(f"[WARNING] Error saving progress state: {e}")
            import traceback
            traceback.print_exc()
    
    def _save_user_activity(self):
        """Save lightweight user activity tracking using simple JSON operations"""
        try:
            # Convert set to list for JSON serialization
            activity_data = {
                'total_unique_users': len(self.user_activity['total_unique_users']),
                'users_by_subreddit': self.user_activity['users_by_subreddit'],
                'high_activity_users': self.user_activity['high_activity_users'],
                'user_pages_generated': self.user_activity['user_pages_generated'],
                'timestamp': datetime.now().isoformat()
            }
            
            print(f"[DEBUG] Saving user activity: {len(self.user_activity['users_by_subreddit'])} subreddits, {len(self.user_activity['total_unique_users'])} users")
            
            # Use simple save with merging - this ensures resume operations preserve existing data
            success = save_user_activity(self.output_dir, activity_data)
            
            if success:
                print(f"[DEBUG] User activity saved successfully")
            else:
                print(f"[ERROR] Failed to save user activity")
                
        except Exception as e:
            print(f"[WARNING] Error saving user activity: {e}")
            import traceback
            traceback.print_exc()
    
    def update_user_activity(self, subreddit: str, users: set):
        """Update lightweight user activity tracking"""
        # Track users for this subreddit
        self.user_activity['users_by_subreddit'][subreddit] = len(users)
        
        # Add to global user set
        self.user_activity['total_unique_users'].update(users)
        
        # ✅ RESUME FIX: Only save if this is new data, not during resume restore
        if not hasattr(self, '_restoring_from_resume') or not self._restoring_from_resume:
            self._save_user_activity()
    
    def _print_status(self):
        """Print current processing status"""
        print(f"\nRedd-Archiver Processing Status")
        print(f"Phase: {self.current_phase}")
        print(f"Current: {self.current_subreddit or 'None'}")
        print(f"Progress: {len(self.completed_subreddits)}/{self.total_subreddits} subreddits")
        
        if self.total_subreddits > 0:
            progress_percent = len(self.completed_subreddits) / self.total_subreddits * 100
            print(f"Completion: {progress_percent:.1f}%")
        
        # Memory status
        memory_percent = self.check_memory_usage()
        print(f"Memory usage: {memory_percent:.1%}")
        
        # Runtime
        elapsed = datetime.now() - self.start_time
        print(f"Runtime: {elapsed}")
        print()
    
    def initialize_subreddit_list(self, subreddit_files: Dict[str, Dict]):
        """Initialize the list of subreddits to process"""
        self.remaining_subreddits = list(subreddit_files.keys())
        self.total_subreddits = len(self.remaining_subreddits)
        self.current_phase = 'subreddit_processing'
        
        print(f"Initialized processing queue: {self.total_subreddits} subreddits")
        self._save_progress_state('initialized')
    
    def start_subreddit_processing(self, subreddit: str):
        """Mark start of subreddit processing"""
        self.current_subreddit = subreddit
        self.current_phase = 'subreddit_processing'
        
        print(f"\nProcessing r/{subreddit}...")
        self._save_progress_state('subreddit_processing')
    
    def complete_subreddit_processing(self, subreddit: str, users: set):
        """Mark completion of subreddit processing"""
        if subreddit in self.remaining_subreddits:
            self.remaining_subreddits.remove(subreddit)
        
        if subreddit not in self.completed_subreddits:
            self.completed_subreddits.append(subreddit)
        
        # Update user activity tracking
        self.update_user_activity(subreddit, users)
        
        # Print progress
        progress_percent = len(self.completed_subreddits) / self.total_subreddits * 100
        print(f"[SUCCESS] r/{subreddit} complete ({len(self.completed_subreddits)}/{self.total_subreddits}, {progress_percent:.1f}%)")
        
        # Save progress
        self._save_progress_state('subreddit_processing')
        
        # Check memory after each subreddit
        self.check_memory_usage()
    
    def fail_subreddit_processing(self, subreddit: str, error: str):
        """Mark failure of subreddit processing"""
        if subreddit in self.remaining_subreddits:
            self.remaining_subreddits.remove(subreddit)
        
        self.failed_subreddits.append({
            'subreddit': subreddit,
            'error': str(error),
            'timestamp': datetime.now().isoformat()
        })
        
        print(f"[ERROR] r/{subreddit} failed: {error}")
        self._save_progress_state('subreddit_processing')
    
    def start_user_page_generation(self):
        """Mark start of user page generation phase"""
        self.current_phase = 'user_page_generation'
        self.current_subreddit = None
        
        total_users = len(self.user_activity['total_unique_users'])
        print(f"\nStarting user page generation for {total_users:,} users...")
        self._save_progress_state('user_page_generation')
    
    def complete_processing(self):
        """Mark completion of all processing"""
        self.current_phase = 'complete'
        self.current_subreddit = None
        
        elapsed = datetime.now() - self.start_time
        print(f"\n[SUCCESS] Archive generation complete!")
        print(f"Total time: {elapsed}")
        print(f"Subreddits processed: {len(self.completed_subreddits)}")
        print(f"Failed subreddits: {len(self.failed_subreddits)}")
        print(f"Unique users: {len(self.user_activity['total_unique_users']):,}")
        
        self._save_progress_state('complete')
    
    def should_continue(self) -> bool:
        """Check if processing should continue"""
        return not self.shutdown_requested

    def cleanup(self):
        """Clean up progress files after successful completion"""
        try:
            files_to_remove = [
                self.progress_file,
                self.emergency_file,
                f"{self.emergency_file}.backup"
            ]
            
            for file_path in files_to_remove:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
            print("Cleaned up temporary progress files")
            
        except Exception as e:
            print(f"[WARNING] Error cleaning up progress files: {e}")
