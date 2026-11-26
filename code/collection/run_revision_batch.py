import argparse
import random
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(
    __file__
).resolve().parents[2]


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


MODES = [
    "before_gap",
]


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repetitions",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--base-seed",
        type=int,
        default=20261122,
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
            for mode in MODES:
                for rep in range(
                    1,
                    args.repetitions + 1,
                ):

                    seed = (
                        args.base_seed
                        + sample_ms * 100000
                        + margin_ms * 100
                        + rep
                    )

                    conditions.append({
                        "mode":
                            mode,

                        "sample_ms":
                            sample_ms,

                        "margin_ms":
                            margin_ms,

                        "rep":
                            rep,

                        "seed":
                            seed,
                    })

    # Randomise execution order while
    # preserving reproducibility.
    rng = random.Random(
        args.base_seed
    )

    rng.shuffle(
        conditions
    )

    total = len(
        conditions
    )

    print("=" * 80)

    print(
        "IBSTER V2E34-R - "
        "REVISION BATCH"
    )

    print("=" * 80)

    print(
        f"Conditions : {total}"
    )

    print(
        f"Repetitions per condition : "
        f"{args.repetitions}"
    )

    print(
        f"Base seed : "
        f"{args.base_seed}"
    )

    print()

    failures = []

    for index, condition in enumerate(
        conditions,
        start=1,
    ):

        print()
        print("=" * 80)

        print(
            f"RUN {index}/{total}"
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

        print("=" * 80)

        command = [
            sys.executable,
            str(RUNNER),

            "--mode",
            condition[
                "mode"
            ],

            "--margin-ms",
            str(
                condition[
                    "margin_ms"
                ]
            ),

            "--sample-ms",
            str(
                condition[
                    "sample_ms"
                ]
            ),

            "--seed",
            str(
                condition[
                    "seed"
                ]
            ),

            "--rep",
            str(
                condition[
                    "rep"
                ]
            ),
        ]

        result = subprocess.run(
            command
        )

        if (
            result.returncode
            != 0
        ):
            failures.append({
                **condition,
                "returncode":
                    result.returncode,
            })

            print(
                "RUN STATUS: FAILED"
            )

        else:
            print(
                "RUN STATUS: COMPLETE"
            )

        if (
            args.pause_s
            > 0
        ):
            time.sleep(
                args.pause_s
            )

    print()
    print("=" * 80)

    print(
        "BATCH SUMMARY"
    )

    print("=" * 80)

    print(
        f"Total runs : "
        f"{total}"
    )

    print(
        f"Successful : "
        f"{total - len(failures)}"
    )

    print(
        f"Failed     : "
        f"{len(failures)}"
    )

    if failures:
        print()
        print(
            "FAILED CONDITIONS"
        )

        for item in failures:
            print(
                item
            )


if __name__ == "__main__":
    main()
