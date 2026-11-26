import argparse
import runpy
import sys
import time
from pathlib import Path


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    parser.add_argument(
        "--start-gate",
        required=True,
    )

    parser.add_argument(
        "--mode",
        required=True,
    )

    parser.add_argument(
        "--margin-ms",
        required=True,
        type=int,
        choices=[
            20,
            50,
            80,
            120,
            200,
        ],
    )

    parser.add_argument(
        "--phase-ms",
        required=True,
        type=float,
    )

    args = parser.parse_args()

    output_dir = Path(
        args.output
    ).resolve()

    gate = Path(
        args.start_gate
    ).resolve()

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    workload = (
        Path(__file__)
        .resolve()
        .parents[1]
        / "workload_process_start.py"
    )

    deadline = (
        time.monotonic()
        + 20.0
    )

    while not (
        gate.exists()
    ):

        if (
            time.monotonic()
            > deadline
        ):

            raise TimeoutError(
                "Start gate tidak muncul: "
                f"{gate}"
            )

        time.sleep(
            0.01
        )

    (
        output_dir
        / "v2e34r_capture_start.txt"
    ).write_text(
        "IBSTER V2E34-R "
        "process-start capture start\n",
        encoding="utf-8",
    )

    old_argv = (
        sys.argv[:]
    )

    try:

        sys.argv = [
            str(workload),

            "--output",
            str(output_dir),

            "--mode",
            args.mode,

            "--margin-ms",
            str(args.margin_ms),

            "--phase-ms",
            str(args.phase_ms),
        ]

        runpy.run_path(
            str(workload),
            run_name="__main__",
        )

    finally:

        sys.argv = (
            old_argv
        )

    (
        output_dir
        / "v2e34r_capture_end.txt"
    ).write_text(
        "IBSTER V2E34-R "
        "process-start capture end\n",
        encoding="utf-8",
    )

    time.sleep(
        0.4
    )


if __name__ == "__main__":
    main()
