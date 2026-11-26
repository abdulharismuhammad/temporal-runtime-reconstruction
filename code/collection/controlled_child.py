import argparse
import sys
import time
from pathlib import Path


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--timestamp-file",
        required=True,
    )

    args = parser.parse_args()

    timestamp_file = Path(
        args.timestamp_file
    ).resolve()

    # Inform parent that interpreter initialization is complete.
    print(
        "READY",
        flush=True,
    )

    command = sys.stdin.readline()

    if command.strip() != "EXIT":
        raise SystemExit(2)

    # Record the last user-space timestamp immediately
    # before process termination.
    pre_exit_ns = time.monotonic_ns()

    timestamp_file.write_text(
        f"{pre_exit_ns}\n",
        encoding="utf-8",
    )

    # Exit immediately after recording the timestamp.
    raise SystemExit(0)


if __name__ == "__main__":
    main()
