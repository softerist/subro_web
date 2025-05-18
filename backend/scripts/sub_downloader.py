# backend/app/scripts/sub_downloader.py
import argparse
import random
import sys
import time
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description="Placeholder Subtitle Downloader Script")
    # Consistent with Celery task's _run_script_and_get_output call
    parser.add_argument("--folder-path", required=True, help="Path to the media folder")
    parser.add_argument(
        "--language", help="Language code for subtitles (e.g., 'en', 'es')"
    )  # Consistent
    parser.add_argument("--simulate-error", action="store_true", help="Simulate a script error")
    parser.add_argument(
        "--simulate-long-run", action="store_true", help="Simulate a longer running task"
    )
    parser.add_argument(
        "--simulate-no-output",
        action="store_true",
        help="Simulate a script that produces no stdout/stderr",
    )

    args = parser.parse_args()

    if args.simulate_no_output:
        # This block is for testing how the system handles scripts with no output
        if args.simulate_error:
            sys.exit(77)  # Arbitrary non-zero exit code for no-output error
        else:
            sys.exit(0)  # Exit successfully with no output

    print(
        f"[{datetime.now().isoformat()}] SCRIPT_LOG: Placeholder script starting execution.",
        flush=True,
    )
    print(f"SCRIPT_LOG: Target Folder Path: {args.folder_path}", flush=True)  # Use args.folder_path
    if args.language:  # Use args.language
        print(f"SCRIPT_LOG: Requested Language: {args.language}", flush=True)
    else:
        print("SCRIPT_LOG: No specific language requested (will attempt all/default).", flush=True)

    if args.simulate_long_run:
        print("SCRIPT_LOG: Simulating a longer task (10 seconds)...", flush=True)
        for i in range(10):
            print(f"SCRIPT_LOG: Long run progress - {i+1}/10", flush=True)
            time.sleep(1)
        print("SCRIPT_LOG: Long task simulation complete.", flush=True)
    else:
        print("SCRIPT_LOG: Simulating standard work (2 seconds)...", flush=True)
        time.sleep(1)
        print("SCRIPT_LOG: Standard work half-way point.", flush=True)
        time.sleep(1)
        print("SCRIPT_LOG: Standard work simulation complete.", flush=True)

    if args.simulate_error:
        print("SCRIPT_ERROR: Simulating an error condition...", file=sys.stderr, flush=True)
        print(
            f"SCRIPT_ERROR: Failed to download subtitles for '{args.folder_path}' "  # Use args.folder_path
            f"(Language: {args.language or 'any'}).",  # Use args.language
            file=sys.stderr,
            flush=True,
        )
        print("SCRIPT_ERROR: This is a simulated error log line 1.", file=sys.stderr, flush=True)
        print(
            "SCRIPT_ERROR: This is a detailed error message that might span multiple lines.",
            file=sys.stderr,
            flush=True,
        )
        print("SCRIPT_ERROR: Another simulated error log line 2.", file=sys.stderr, flush=True)
        print(
            f"[{datetime.now().isoformat()}] SCRIPT_LOG: Placeholder script finished with SIMULATED ERROR.",
            flush=True,
        )
        sys.exit(1)  # Standard error exit code
    else:
        # Simulate some successful output
        print("SCRIPT_LOG: Beginning simulated file processing loop.", flush=True)
        for i in range(3):
            print(
                f"SCRIPT_LOG: Processing file {i+1}/3 in '{args.folder_path}'...", flush=True
            )  # Use args.folder_path
            time.sleep(random.uniform(0.2, 0.5))
            print(f"SCRIPT_LOG: Subtitle found for file {i+1} (simulated).", flush=True)

        print("SCRIPT_LOG: All files processed. Subtitles 'downloaded' successfully.", flush=True)
        print(
            f"[{datetime.now().isoformat()}] SCRIPT_LOG: Placeholder script finished successfully.",
            flush=True,
        )
        sys.exit(0)  # Standard success exit code


if __name__ == "__main__":
    main()
