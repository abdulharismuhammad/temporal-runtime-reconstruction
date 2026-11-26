import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


def read_csv(path):
    with path.open(
        newline="",
        encoding="utf-8",
    ) as handle:
        return list(
            csv.DictReader(handle)
        )


def wilson_interval(successes, total, z=1.959963984540054):
    if total == 0:
        return float("nan"), float("nan")

    p = successes / total

    denom = 1 + z * z / total

    centre = (
        p
        + z * z / (2 * total)
    ) / denom

    half = (
        z
        * math.sqrt(
            p * (1 - p) / total
            + z * z / (4 * total * total)
        )
        / denom
    )

    return (
        centre - half,
        centre + half,
    )


def group_by_interval(rows):
    grouped = defaultdict(list)

    for row in rows:
        sample_ms = int(
            float(
                row["sample_interval_ms"]
            )
        )

        grouped[
            sample_ms
        ].append(row)

    return grouped


def summarise(rows):
    n = len(rows)

    correct = sum(
        int(
            row["relation_match"]
        )
        for row in rows
    )

    errors = n - correct

    return {
        "n": n,
        "correct": correct,
        "errors": errors,
        "accuracy": correct / n,
        "error_rate": errors / n,
    }


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--before-file",
        required=True,
    )

    parser.add_argument(
        "--overlap-file",
        required=True,
    )

    args = parser.parse_args()

    before_file = Path(
        args.before_file
    ).resolve()

    overlap_file = Path(
        args.overlap_file
    ).resolve()

    before_rows = read_csv(
        before_file
    )

    overlap_rows = read_csv(
        overlap_file
    )

    before_grouped = group_by_interval(
        before_rows
    )

    overlap_grouped = group_by_interval(
        overlap_rows
    )

    intervals = sorted(
        set(before_grouped)
        | set(overlap_grouped)
    )

    results = []

    print(
        "=" * 118
    )

    print(
        "IBSTER V2E34-R - "
        "BOUNDARY ASYMMETRY ANALYSIS"
    )

    print(
        "=" * 118
    )

    print()

    print(
        " T(ms) | BEFORE n | BEFORE acc | B→O err | "
        "OVERLAP n | OVERLAP acc | O err | Asymmetry"
    )

    print(
        "-" * 118
    )

    for sample_ms in intervals:

        before = summarise(
            before_grouped[
                sample_ms
            ]
        )

        overlap = summarise(
            overlap_grouped[
                sample_ms
            ]
        )

        asymmetry = (
            before["error_rate"]
            - overlap["error_rate"]
        )

        before_ci = wilson_interval(
            before["correct"],
            before["n"],
        )

        overlap_ci = wilson_interval(
            overlap["correct"],
            overlap["n"],
        )

        results.append({
            "sample_interval_ms":
                sample_ms,

            "before_n":
                before["n"],

            "before_correct":
                before["correct"],

            "before_accuracy":
                before["accuracy"],

            "before_ci_low":
                before_ci[0],

            "before_ci_high":
                before_ci[1],

            "before_to_overlaps_errors":
                before["errors"],

            "before_error_rate":
                before["error_rate"],

            "overlap_n":
                overlap["n"],

            "overlap_correct":
                overlap["correct"],

            "overlap_accuracy":
                overlap["accuracy"],

            "overlap_ci_low":
                overlap_ci[0],

            "overlap_ci_high":
                overlap_ci[1],

            "overlap_errors":
                overlap["errors"],

            "overlap_error_rate":
                overlap["error_rate"],

            "asymmetry_difference":
                asymmetry,
        })

        print(
            f"{sample_ms:6d} | "
            f"{before['n']:8d} | "
            f"{before['accuracy']:10.3f} | "
            f"{before['errors']:7d} | "
            f"{overlap['n']:9d} | "
            f"{overlap['accuracy']:11.3f} | "
            f"{overlap['errors']:5d} | "
            f"{asymmetry:9.3f}"
        )

    print()

    print(
        "=" * 118
    )

    total_before = summarise(
        before_rows
    )

    total_overlap = summarise(
        overlap_rows
    )

    overall_asymmetry = (
        total_before["error_rate"]
        - total_overlap["error_rate"]
    )

    print(
        f"BEFORE agreement : "
        f"{total_before['correct']}/"
        f"{total_before['n']} "
        f"({total_before['accuracy']:.3f})"
    )

    print(
        f"BEFORE errors    : "
        f"{total_before['errors']}"
    )

    print()

    print(
        f"OVERLAP agreement: "
        f"{total_overlap['correct']}/"
        f"{total_overlap['n']} "
        f"({total_overlap['accuracy']:.3f})"
    )

    print(
        f"OVERLAP errors   : "
        f"{total_overlap['errors']}"
    )

    print()

    print(
        f"Overall asymmetry difference: "
        f"{overall_asymmetry:.3f}"
    )

    output_file = (
        before_file.parent
        / "boundary_asymmetry_summary.csv"
    )

    fields = [
        "sample_interval_ms",
        "before_n",
        "before_correct",
        "before_accuracy",
        "before_ci_low",
        "before_ci_high",
        "before_to_overlaps_errors",
        "before_error_rate",
        "overlap_n",
        "overlap_correct",
        "overlap_accuracy",
        "overlap_ci_low",
        "overlap_ci_high",
        "overlap_errors",
        "overlap_error_rate",
        "asymmetry_difference",
    ]

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        for row in results:
            writer.writerow(
                row
            )

    print()
    print(
        f"Output: {output_file}"
    )


if __name__ == "__main__":
    main()
