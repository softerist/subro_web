# backend/app/scripts/sub_downloader.py
import argparse
import random
import sys
import time
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description="Placeholder Subtitle Downloader Script")
    parser.add_argument("--folder-path", required=True, help="Path to the media folder")
    parser.add_argument("--language", help="Language code for subtitles (e.g., 'en', 'es')")
    parser.add_argument("--simulate-error", action="store_true", help="Simulate a script error")
    parser.add_argument(
        "--simulate-long-run", action="store_true", help="Simulate a longer running task"
    )

    args = parser.parse_args()

    print(f"[{datetime.now()}] Placeholder script started.", flush=True)
    print(f"  Folder Path: {args.folder_path}", flush=True)
    if args.language:
        print(f"  Language: {args.language}", flush=True)

    if args.simulate_long_run:
        print("Simulating a longer task (10 seconds)...", flush=True)
        time.sleep(10)
    else:
        print("Simulating work (2 seconds)...", flush=True)
        time.sleep(2)

    if args.simulate_error:
        print("Simulating an error condition...", file=sys.stderr, flush=True)
        print(
            f"Error: Failed to download subtitles for {args.folder_path} in language {args.language or 'any'}.",
            file=sys.stderr,
            flush=True,
        )
        print("This is a simulated error log line 1.", file=sys.stderr, flush=True)
        print("This is a simulated error log line 2.", file=sys.stderr, flush=True)
        sys.exit(1)
    else:
        # Simulate some successful output
        for i in range(3):
            print(f"Processing file {i+1}/3 in {args.folder_path}...", flush=True)
            time.sleep(random.uniform(0.2, 0.5))
        print("Subtitles 'downloaded' successfully.", flush=True)
        print(f"[{datetime.now()}] Placeholder script finished successfully.", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
