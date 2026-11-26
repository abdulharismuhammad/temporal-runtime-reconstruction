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


def mean(values):
    if not values:
        return float("nan")

    return sum(values) / len(values)


def stddev(values):
    if len(values) < 2:
        return float("nan")

    avg = mean(values)

    return math.sqrt(
        sum(
            (value - avg) ** 2
            for value in values
        )
        / (len(values) - 1)
    )


def wilson_interval(
    successes,
    total,
    z=1.959963984540054,
):
    if total == 0:
        return (
            float("nan"),
            float("nan"),
        )

    p = successes / total

    denominator = (
        1
        + z * z / total
    )

    centre = (
        p
        + z * z
        / (2 * total)
    ) / denominator

    half_width = (
        z
        * math.sqrt(
            (
                p * (1 - p)
                / total
            )
            + (
                z * z
                / (
                    4
                    * total
                    * total
                )
            )
        )
        / denominator
    )

    return (
        centre - half_width,
        centre + half_width,
    )


def safe_float(value):
    if (
        value is None
        or (
            isinstance(
                value,
                float,
            )
            and math.isnan(value)
        )
    ):
        return ""

    return f"{value:.6f}"


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--analysis-file",
        required=True,
    )

    args = parser.parse_args()

    analysis_file = Path(
        args.analysis_file
    ).resolve()

    rows = read_csv(
        analysis_file
    )

    if not rows:
        raise RuntimeError(
            "Analysis file kosong."
        )

    grouped = defaultdict(list)

    for row in rows:

        sample_ms = int(
            float(
                row[
                    "sample_interval_ms"
                ]
            )
        )

        margin_ms = int(
            float(
                row[
                    "margin_ms"
                ]
            )
        )

        grouped[
            (
                sample_ms,
                margin_ms,
            )
        ].append(row)

    output_rows = []

    for (
        sample_ms,
        margin_ms,
    ) in sorted(
        grouped
    ):

        group = grouped[
            (
                sample_ms,
                margin_ms,
            )
        ]

        n = len(group)

        correct = sum(
            int(
                row[
                    "relation_match"
                ]
            )
            for row in group
        )

        errors = (
            n - correct
        )

        before_to_overlaps = sum(
            1
            for row in group
            if (
                row[
                    "gt_relation"
                ]
                == "BEFORE"
                and
                row[
                    "observed_relation"
                ]
                == "OVERLAPS"
            )
        )

        accuracy = (
            correct / n
        )

        empirical_error = (
            before_to_overlaps
            / n
        )

        measured_gaps = [
            float(
                row[
                    "gt_boundary_wait_return_ms"
                ]
            )
            for row in group
        ]

        mean_gap = mean(
            measured_gaps
        )

        sd_gap = stddev(
            measured_gaps
        )

        analytic_per_run = [
            max(
                0.0,
                1.0
                - (
                    max(
                        float(
                            row[
                                "gt_boundary_wait_return_ms"
                            ]
                        ),
                        0.0,
                    )
                    / sample_ms
                ),
            )
            for row in group
        ]

        analytic_error = mean(
            analytic_per_run
        )

        absolute_difference = abs(
            empirical_error
            - analytic_error
        )

        bracket_widths = [
            float(
                row[
                    "termination_bracket_width_ms"
                ]
            )
            for row in group
        ]

        poll_periods = [
            float(
                row[
                    "mean_poll_interval_ms"
                ]
            )
            for row in group
        ]

        poll_jitters = [
            float(
                row[
                    "std_poll_interval_ms"
                ]
            )
            for row in group
        ]

        inside_bracket = sum(
            1
            for row in group
            if (
                row[
                    "observed_end_bracket_position"
                ]
                == "INSIDE_BRACKET"
            )
        )

        before_bracket = sum(
            1
            for row in group
            if (
                row[
                    "observed_end_bracket_position"
                ]
                == "BEFORE_BRACKET"
            )
        )

        after_bracket = sum(
            1
            for row in group
            if (
                row[
                    "observed_end_bracket_position"
                ]
                == "AFTER_BRACKET"
            )
        )

        accuracy_low, accuracy_high = (
            wilson_interval(
                correct,
                n,
            )
        )

        error_low, error_high = (
            wilson_interval(
                before_to_overlaps,
                n,
            )
        )

        output_rows.append({
            "sample_interval_ms":
                sample_ms,

            "nominal_margin_ms":
                margin_ms,

            "n":
                n,

            "correct":
                correct,

            "before_to_overlaps":
                before_to_overlaps,

            "accuracy":
                accuracy,

            "accuracy_ci_low":
                accuracy_low,

            "accuracy_ci_high":
                accuracy_high,

            "empirical_error_probability":
                empirical_error,

            "empirical_error_ci_low":
                error_low,

            "empirical_error_ci_high":
                error_high,

            "mean_measured_gap_ms":
                mean_gap,

            "sd_measured_gap_ms":
                sd_gap,

            "analytic_error_probability":
                analytic_error,

            "absolute_empirical_analytic_difference":
                absolute_difference,

            "mean_poll_interval_ms":
                mean(
                    poll_periods
                ),

            "mean_poll_jitter_ms":
                mean(
                    poll_jitters
                ),

            "mean_termination_bracket_ms":
                mean(
                    bracket_widths
                ),

            "before_bracket":
                before_bracket,

            "inside_bracket":
                inside_bracket,

            "after_bracket":
                after_bracket,
        })

    output_dir = (
        analysis_file
        .parent
    )

    output_file = (
        output_dir
        / "sampling_matrix_summary.csv"
    )

    fields = [
        "sample_interval_ms",
        "nominal_margin_ms",
        "n",
        "correct",
        "before_to_overlaps",
        "accuracy",
        "accuracy_ci_low",
        "accuracy_ci_high",
        "empirical_error_probability",
        "empirical_error_ci_low",
        "empirical_error_ci_high",
        "mean_measured_gap_ms",
        "sd_measured_gap_ms",
        "analytic_error_probability",
        "absolute_empirical_analytic_difference",
        "mean_poll_interval_ms",
        "mean_poll_jitter_ms",
        "mean_termination_bracket_ms",
        "before_bracket",
        "inside_bracket",
        "after_bracket",
    ]

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as destination:

        writer = csv.DictWriter(
            destination,
            fieldnames=fields,
        )

        writer.writeheader()

        for row in output_rows:

            formatted = dict(
                row
            )

            for field in [
                "accuracy",
                "accuracy_ci_low",
                "accuracy_ci_high",
                "empirical_error_probability",
                "empirical_error_ci_low",
                "empirical_error_ci_high",
                "mean_measured_gap_ms",
                "sd_measured_gap_ms",
                "analytic_error_probability",
                "absolute_empirical_analytic_difference",
                "mean_poll_interval_ms",
                "mean_poll_jitter_ms",
                "mean_termination_bracket_ms",
            ]:

                formatted[field] = (
                    safe_float(
                        row[field]
                    )
                )

            writer.writerow(
                formatted
            )

    print(
        "=" * 132
    )

    print(
        "IBSTER V2E34-R - "
        "SAMPLING INTERVAL × MARGIN MATRIX"
    )

    print(
        "=" * 132
    )

    print()

    print(
        " T(ms)  Margin   n   Correct   Errors   Emp.Err   Analytic   "
        "|Diff|    Mean gap   Poll mean   Jitter"
    )

    print(
        "-" * 132
    )

    for row in output_rows:

        print(
            f"{row['sample_interval_ms']:6d} "
            f"{row['nominal_margin_ms']:7d} "
            f"{row['n']:3d} "
            f"{row['correct']:9d} "
            f"{row['before_to_overlaps']:8d} "
            f"{row['empirical_error_probability']:9.3f} "
            f"{row['analytic_error_probability']:10.3f} "
            f"{row['absolute_empirical_analytic_difference']:8.3f} "
            f"{row['mean_measured_gap_ms']:11.3f} "
            f"{row['mean_poll_interval_ms']:11.3f} "
            f"{row['mean_poll_jitter_ms']:8.3f}"
        )

    print()
    print(
        "=" * 132
    )

    total_n = sum(
        row["n"]
        for row in output_rows
    )

    total_correct = sum(
        row["correct"]
        for row in output_rows
    )

    total_errors = sum(
        row["before_to_overlaps"]
        for row in output_rows
    )

    print(
        f"Total runs              : "
        f"{total_n}"
    )

    print(
        f"Total correct           : "
        f"{total_correct}"
    )

    print(
        f"Total BEFORE→OVERLAPS   : "
        f"{total_errors}"
    )

    print(
        f"Overall agreement       : "
        f"{total_correct / total_n:.3f}"
    )

    print()

    print(
        f"Output: {output_file}"
    )


if __name__ == "__main__":
    main()
