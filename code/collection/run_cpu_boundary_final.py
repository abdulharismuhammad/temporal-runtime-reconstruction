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
    / "collection_cpu_boundary"
    / "run_experiment.py"
)

SAMPLE_INTERVALS = [
    10,
    25,
    50,
    100,
    250,
]

MARGIN_MS = 20
REPETITIONS = 10
BASE_SEED = 20261201


def build_conditions():

    conditions = []

    for sample_ms in SAMPLE_INTERVALS:

        for rep in range(
            1,
            REPETITIONS + 1,
        ):

            seed = (
                BASE_SEED
                + sample_ms * 100000
                + MARGIN_MS * 100
                + rep
            )

            conditions.append({
                "sample_ms": sample_ms,
                "rep": rep,
                "seed": seed,
            })

    return conditions


def main():

    conditions = build_conditions()

    rng = random.Random(
        BASE_SEED
    )

    rng.shuffle(
        conditions
    )

    print("=" * 90)

    print(
        "IBSTER V2E34-R - "
        "CPU-BOUNDARY FINAL EXPERIMENT"
    )

    print("=" * 90)

    print(
        f"Intervals   : "
        f"{SAMPLE_INTERVALS}"
    )

    print(
        f"Margin      : "
        f"{MARGIN_MS} ms"
    )

    print(
        f"Repetitions : "
        f"{REPETITIONS}"
    )

    print(
        f"Total runs  : "
        f"{len(conditions)}"
    )

    print("=" * 90)

    successful = 0
    failed = []

    for index, condition in enumerate(
        conditions,
        start=1,
    ):

        sample_ms = (
            condition[
                "sample_ms"
            ]
        )

        rep = (
            condition[
                "rep"
            ]
        )

        seed = (
            condition[
                "seed"
            ]
        )

        print()
        print("=" * 90)

        print(
            f"RUN {index}/"
            f"{len(conditions)}"
        )

        print(
            f"T      : "
            f"{sample_ms} ms"
        )

        print(
            f"Margin : "
            f"{MARGIN_MS} ms"
        )

        print(
            f"Rep    : "
            f"{rep}"
        )

        print(
            f"Seed   : "
            f"{seed}"
        )

        print("=" * 90)

        command = [
            sys.executable,
            str(RUNNER),

            "--mode",
            "before_gap",

            "--sample-ms",
            str(sample_ms),

            "--margin-ms",
            str(MARGIN_MS),

            "--rep",
            str(rep),

            "--seed",
            str(seed),
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

            failed.append(
                condition
            )

            print(
                "RUN STATUS: FAILED"
            )

        time.sleep(
            1.0
        )

    print()
    print("=" * 90)

    print(
        "CPU-BOUNDARY FINAL SUMMARY"
    )

    print("=" * 90)

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

        for condition in failed:

            print(
                f"T="
                f"{condition['sample_ms']} "
                f"| rep="
                f"{condition['rep']} "
                f"| seed="
                f"{condition['seed']}"
            )


if __name__ == "__main__":
    main()
