import argparse
import random
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

RUNNER = (
    ROOT
    / "experiments"
    / "V2E34_sampling_phase_sweep"
    / "collection_revision"
    / "run_experiment.py"
)


SAMPLE_INTERVALS = [
    10,
    25,
    50,
    100,
    250,
]

MARGINS = [
    20,
    50,
    80,
    120,
    200,
]

MODE = "overlap_end"


def condition_seed(
    base_seed,
    sample_ms,
    margin_ms,
    rep,
):
    return (
        base_seed
        + sample_ms * 100000
        + margin_ms * 100
        + rep
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--base-seed",
        type=int,
        default=20261123,
    )

    parser.add_argument(
        "--pause-s",
        type=float,
        default=1.0,
    )

    args = parser.parse_args()

    conditions = []

    for sample_ms in SAMPLE_INTERVALS:

        for margin_ms in MARGINS:

            for rep in range(
                1,
                args.repetitions + 1,
            ):

                seed = condition_seed(
                    args.base_seed,
                    sample_ms,
                    margin_ms,
                    rep,
                )

                conditions.append({
                    "mode": MODE,
                    "sample_ms": sample_ms,
                    "margin_ms": margin_ms,
                    "rep": rep,
                    "seed": seed,
                })

    # Randomisasi urutan eksperimen
    # tetapi tetap reproducible.
    rng = random.Random(
        args.base_seed
    )

    rng.shuffle(
        conditions
    )

    print(
        "=" * 80
    )

    print(
        "IBSTER V2E34-R - "
        "OVERLAP ASYMMETRY CONTROL"
    )

    print(
        "=" * 80
    )

    print(
        f"Mode        : {MODE}"
    )

    print(
        f"Intervals   : {SAMPLE_INTERVALS}"
    )

    print(
        f"Margins     : {MARGINS}"
    )

    print(
        f"Repetitions : {args.repetitions}"
    )

    print(
        f"Total runs  : {len(conditions)}"
    )

    print(
        f"Base seed   : {args.base_seed}"
    )

    print(
        "=" * 80
    )

    successful = 0
    failed = []

    for index, condition in enumerate(
        conditions,
        start=1,
    ):

        print()
        print(
            "=" * 80
        )

        print(
            f"RUN {index}/{len(conditions)}"
        )

        print(
            f"Mode      : "
            f"{condition['mode']}"
        )

        print(
            f"Sample    : "
            f"{condition['sample_ms']} ms"
        )

        print(
            f"Margin    : "
            f"{condition['margin_ms']} ms"
        )

        print(
            f"Rep       : "
            f"{condition['rep']}"
        )

        print(
            f"Seed      : "
            f"{condition['seed']}"
        )

        print(
            "=" * 80
        )

        command = [
            sys.executable,
            str(RUNNER),

            "--mode",
            condition[
                "mode"
            ],

            "--sample-ms",
            str(
                condition[
                    "sample_ms"
                ]
            ),

            "--margin-ms",
            str(
                condition[
                    "margin_ms"
                ]
            ),

            "--rep",
            str(
                condition[
                    "rep"
                ]
            ),

            "--seed",
            str(
                condition[
                    "seed"
                ]
            ),
        ]

        result = subprocess.run(
            command
        )

        if result.returncode == 0:

            successful += 1

            print(
                "RUN STATUS: COMPLETE"
            )

        else:

            failed.append({
                **condition,
                "returncode":
                    result.returncode,
            })

            print(
                "RUN STATUS: FAILED"
            )

        time.sleep(
            args.pause_s
        )

    print()
    print(
        "=" * 80
    )

    print(
        "BATCH SUMMARY"
    )

    print(
        "=" * 80
    )

    print(
        f"Total runs : "
        f"{len(conditions)}"
    )

    print(
        f"Successful : "
        f"{successful}"
    )

    print(
        f"Failed     : "
        f"{len(failed)}"
    )

    if failed:

        print()
        print(
            "FAILED CONDITIONS"
        )

        for condition in failed:
            print(
                condition
            )


if __name__ == "__main__":
    main()
