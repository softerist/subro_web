#!/usr/bin/env python3
import argparse
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock subtitle downloader script")
    parser.add_argument(
        "--duration",
        type=float,
        default=0.5,
        help="Approximate duration to run (seconds)",
    )
    parser.add_argument(
        "--stdout-lines",
        type=int,
        default=3,
        help="Number of lines to write to stdout",
    )
    parser.add_argument(
        "--stderr-lines",
        type=int,
        default=0,
        help="Number of lines to write to stderr",
    )
    parser.add_argument(
        "--exit-code",
        type=int,
        default=0,
        help="Exit code to return",
    )

    args = parser.parse_args()

    duration = max(args.duration, 0.0)
    total_steps = max(args.stdout_lines + args.stderr_lines, 1)
    interval = duration / total_steps if total_steps else 0.0

    print("Script Started")
    sys.stdout.flush()

    for idx in range(args.stdout_lines):
        if interval:
            time.sleep(interval)
        print(f"STDOUT Line {idx + 1}/{args.stdout_lines}")
        sys.stdout.flush()

    for idx in range(args.stderr_lines):
        if interval:
            time.sleep(interval)
        print(f"STDERR Line {idx + 1}/{args.stderr_lines}", file=sys.stderr)
        sys.stderr.flush()

    if interval:
        time.sleep(interval)

    print(f"Script Finished. Exiting with code {args.exit_code}")
    sys.stdout.flush()
    raise SystemExit(args.exit_code)


if __name__ == "__main__":
    main()
