import argparse
import json
import math
from pathlib import Path


def percentile(values, p):

    if not values:
        return float("nan")

    values = sorted(values)

    if len(values) == 1:
        return values[0]

    position = (
        (len(values) - 1)
        * p
    )

    lower = math.floor(
        position
    )

    upper = math.ceil(
        position
    )

    if lower == upper:
        return values[lower]

    fraction = (
        position
        - lower
    )

    return (
        values[lower]
        * (1 - fraction)
        + values[upper]
        * fraction
    )


def analyse_root(root):

    results = []

    for manifest_file in sorted(
        root.rglob(
            "manifest.json"
        )
    ):

        manifest = json.loads(
            manifest_file.read_text(
                encoding="utf-8"
            )
        )

        refs = (
            manifest.get(
                "mapping_references"
            )
            or manifest.get(
                "mapping_refs"
            )
            or []
        )

        if len(refs) < 2:
            continue

        offsets_ns = []

        for ref in refs:

            wall_ns = int(
                ref["wall_ns"]
            )

            monotonic_ns = int(
                ref[
                    "monotonic_ns"
                ]
            )

            offsets_ns.append(
                wall_ns
                - monotonic_ns
            )

        minimum = min(
            offsets_ns
        )

        maximum = max(
            offsets_ns
        )

        spread_ns = (
            maximum
            - minimum
        )

        mean_offset = (
            sum(
                offsets_ns
            )
            / len(
                offsets_ns
            )
        )

        deviations_ns = [
            value
            - mean_offset
            for value
            in offsets_ns
        ]

        max_abs_dev_ns = max(
            abs(value)
            for value
            in deviations_ns
        )

        results.append({
            "run_id":
                manifest.get(
                    "run_id",
                    manifest_file.parent.name,
                ),

            "manifest":
                str(
                    manifest_file
                ),

            "n_refs":
                len(
                    refs
                ),

            "spread_ns":
                spread_ns,

            "spread_us":
                spread_ns
                / 1e3,

            "spread_ms":
                spread_ns
                / 1e6,

            "max_abs_dev_ns":
                max_abs_dev_ns,

            "max_abs_dev_us":
                max_abs_dev_ns
                / 1e3,
        })

    return results


def summarize(
    label,
    results,
):

    print()
    print("=" * 100)

    print(
        label
    )

    print("=" * 100)

    if not results:

        print(
            "No mapping references found."
        )

        return

    spreads_us = [
        row[
            "spread_us"
        ]
        for row in results
    ]

    max_devs_us = [
        row[
            "max_abs_dev_us"
        ]
        for row in results
    ]

    print(
        f"Runs analysed        : "
        f"{len(results)}"
    )

    print(
        f"Refs per run         : "
        f"{min(r['n_refs'] for r in results)}"
        f"–"
        f"{max(r['n_refs'] for r in results)}"
    )

    print()
    print(
        "OFFSET SPREAD WITHIN RUN"
    )

    print(
        f"Mean spread          : "
        f"{sum(spreads_us) / len(spreads_us):.3f} us"
    )

    print(
        f"Median spread        : "
        f"{percentile(spreads_us, 0.50):.3f} us"
    )

    print(
        f"95th percentile      : "
        f"{percentile(spreads_us, 0.95):.3f} us"
    )

    print(
        f"Maximum spread       : "
        f"{max(spreads_us):.3f} us"
    )

    print()
    print(
        "MAX ABSOLUTE DEVIATION FROM RUN MEAN"
    )

    print(
        f"Mean                 : "
        f"{sum(max_devs_us) / len(max_devs_us):.3f} us"
    )

    print(
        f"95th percentile      : "
        f"{percentile(max_devs_us, 0.95):.3f} us"
    )

    print(
        f"Maximum              : "
        f"{max(max_devs_us):.3f} us"
    )

    worst = max(
        results,
        key=lambda row:
            row[
                "spread_us"
            ],
    )

    print()
    print(
        "WORST RUN"
    )

    print(
        f"Run ID               : "
        f"{worst['run_id']}"
    )

    print(
        f"Spread               : "
        f"{worst['spread_us']:.3f} us"
    )

    print(
        f"Manifest             : "
        f"{worst['manifest']}"
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--process-end",
        required=True,
    )

    parser.add_argument(
        "--process-start",
        required=True,
    )

    args = parser.parse_args()

    process_end_root = Path(
        args.process_end
    ).resolve()

    process_start_root = Path(
        args.process_start
    ).resolve()

    process_end = analyse_root(
        process_end_root
    )

    process_start = analyse_root(
        process_start_root
    )

    print("=" * 100)

    print(
        "IBSTER V2E34-R - "
        "WALL-CLOCK / MONOTONIC CLOCK ALIGNMENT"
    )

    print("=" * 100)

    summarize(
        "PROCESS-END FINAL DATASET",
        process_end,
    )

    summarize(
        "PROCESS-START FINAL DATASET",
        process_start,
    )

    combined = (
        process_end
        + process_start
    )

    if combined:

        spreads_us = [
            row[
                "spread_us"
            ]
            for row in combined
        ]

        print()
        print("=" * 100)

        print(
            "COMBINED"
        )

        print("=" * 100)

        print(
            f"Runs analysed        : "
            f"{len(combined)}"
        )

        print(
            f"Mean spread          : "
            f"{sum(spreads_us) / len(spreads_us):.3f} us"
        )

        print(
            f"95th percentile      : "
            f"{percentile(spreads_us, 0.95):.3f} us"
        )

        print(
            f"Maximum spread       : "
            f"{max(spreads_us):.3f} us"
        )

        print()
        print(
            "Interpretation: smaller values indicate "
            "stable wall-clock to monotonic mapping "
            "within each capture."
        )


if __name__ == "__main__":
    main()
