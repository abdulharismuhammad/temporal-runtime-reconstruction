import argparse
from pathlib import Path
import sys
import time


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--start-timestamp-file",
        required=True,
    )

    args = parser.parse_args()

    timestamp_file = Path(
        args.start_timestamp_file
    ).resolve()

    timestamp_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Earliest user-space timestamp available
    # from inside the child after Python startup.
    child_user_start_ns = (
        time.monotonic_ns()
    )

    timestamp_file.write_text(
        str(child_user_start_ns),
        encoding="utf-8",
    )

    print(
        "READY",
        flush=True,
    )

    while True:

        line = (
            sys.stdin.readline()
        )

        if not line:
            break

        if (
            line.strip()
            == "EXIT"
        ):
            break


if __name__ == "__main__":
    main()
