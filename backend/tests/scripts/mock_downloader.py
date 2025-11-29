#!/usr/bin/env python3
import argparse
import sys
import time

# This is the script that the Celery Worker will execute as a subprocess.
# It simulates a real downloader by printing to stdout/stderr.


def main():
    # 1. Parse arguments exactly like the real sub_downloader.py would
    parser = argparse.ArgumentParser(description="Mock Subtitle Downloader")
    parser.add_argument("--folder-path", required=True, help="Path to media folder")
    parser.add_argument("--language", default="en", help="Language code")

    # 2. Add "Mock Control" arguments
    # These let our tests control the script's behavior via the command line
    parser.add_argument(
        "--mock-duration", type=float, default=0.5, help="How long to run (seconds)"
    )
    parser.add_argument("--mock-exit-code", type=int, default=0, help="Exit code to return")
    parser.add_argument("--mock-stdout-lines", type=int, default=3, help="Lines to print to stdout")
    parser.add_argument("--mock-stderr-lines", type=int, default=0, help="Lines to print to stderr")

    args, unknown = parser.parse_known_args()

    # 3. Simulate initialization
    print(f"[MOCK] Starting subtitle download for: {args.folder_path}")
    print(f"[MOCK] Language: {args.language}")
    sys.stdout.flush()  # Important: Flush immediately so Celery picks it up in real-time

    # 4. Simulate work loop
    interval = args.mock_duration / (max(args.mock_stdout_lines, 1) + 1)

    for i in range(args.mock_stdout_lines):
        time.sleep(interval)
        print(f"[MOCK] Processing file {i+1}/{args.mock_stdout_lines}...")
        sys.stdout.flush()

    # 5. Simulate errors if requested
    for i in range(args.mock_stderr_lines):
        print(f"[MOCK ERROR] Simulated error message {i+1}", file=sys.stderr)
        sys.stderr.flush()

    time.sleep(interval)

    # 6. Final output and exit
    if args.mock_exit_code == 0:
        print("[MOCK] Download complete.")
    else:
        print(f"[MOCK] Failed with exit code {args.mock_exit_code}")

    sys.exit(args.mock_exit_code)


if __name__ == "__main__":
    main()
