import cProfile
import pstats
import io
import os
from functools import wraps
import time

PROFILER_ENABLED = True # Set to False to disable profiling globally
PROFILE_DIR = "profiles"

if not os.path.exists(PROFILE_DIR):
    try:
        os.makedirs(PROFILE_DIR)
    except OSError as e:
        print(f"Error creating profile directory {PROFILE_DIR}: {e}")
        # Fallback to current directory if creation fails
        PROFILE_DIR = "."


def profile_me(filename_prefix=None, sort_by='cumulative', top_n=15):
    """
    A decorator for profiling a function using cProfile.
    Saves profiling data to a .prof file and prints stats.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not PROFILER_ENABLED:
                return func(*args, **kwargs)

            prof = cProfile.Profile()
            start_time = time.time()

            # Profile the function execution
            result = prof.runcall(func, *args, **kwargs)

            end_time = time.time()
            duration = end_time - start_time

            # Create a unique filename for the profile data
            func_name = filename_prefix if filename_prefix else func.__name__
            # Sanitize func_name for filename
            safe_func_name = "".join(c if c.isalnum() else "_" for c in func_name)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            profile_filename = os.path.join(PROFILE_DIR, f"{safe_func_name}_{timestamp}.prof")

            try:
                prof.dump_stats(profile_filename)
            except Exception as e:
                print(f"Error dumping profile stats for {safe_func_name}: {e}")
                return result

            # Print stats to console (or log)
            s = io.StringIO()
            ps = pstats.Stats(prof, stream=s).sort_stats(sort_by)
            ps.print_stats(top_n)

            log_output_func = None
            # Try to find a logger or on_log callback on the instance if 'self' is an arg
            if args and hasattr(args[0], 'on_log'):
                log_output_func = args[0].on_log
            elif args and hasattr(args[0], 'log_message'): # For TradingBot
                 log_output_func = args[0].log_message

            log_message_content = f"\n--- Profiling Stats for {func_name} ({profile_filename}) ---\n"
            log_message_content += f"Total execution time: {duration:.4f} seconds\n"
            log_message_content += s.getvalue()
            log_message_content += "-------------------------------------------------------\n"

            if log_output_func:
                # Log output might be too verbose for UI log, consider logging to file or specific debug log
                # For now, print to console as well for visibility during development
                print(log_message_content)
                # log_output_func(log_message_content, "PROFILE") # Assuming a "PROFILE" level or similar
            else:
                print(log_message_content)

            s.close()
            return result
        return wrapper
    return decorator

# Example usage (can be removed or commented out)
# @profile_me(filename_prefix="my_function_profile", top_n=5)
# def my_function():
#     # Some time-consuming operations
#     time.sleep(0.1)
#     [x*x for x in range(100000)]

# if __name__ == '__main__':
#     if PROFILER_ENABLED:
#         print(f"Profiler enabled. Stats will be saved to '{PROFILE_DIR}' directory.")
#     my_function()
#     if PROFILER_ENABLED:
#         print("Profiling complete. Check the .prof file and console output.")

def print_profile_stats(profile_file_path, sort_by='cumulative', top_n=20):
    """Helper function to print stats from a .prof file."""
    s = io.StringIO()
    try:
        ps = pstats.Stats(profile_file_path, stream=s).sort_stats(sort_by)
        ps.print_stats(top_n)
        print(f"\n--- Stats from {profile_file_path} (sorted by {sort_by}, top {top_n}) ---")
        print(s.getvalue())
    except Exception as e:
        print(f"Error reading profile file {profile_file_path}: {e}")
    finally:
        s.close()
