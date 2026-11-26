import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


def wilson_interval(
    successes,
    n,
    z=1.959963984540054,
):

    if n == 0:
        return (
            float("nan"),
            float("nan"),
        )

    p = (
        successes
        / n
    )

    denominator = (
        1.0
        + z * z / n
    )

    center = (
        p
        + z * z / (2 * n)
    ) / denominator

    half = (
        z
        * math.sqrt(
            (
                p * (1 - p) / n
                + z * z / (4 * n * n)
            )
        )
        / denominator
    )

    return (
        center - half,
        center + half,
    )


def pearson(
    x,
    y,
):

    if (
        len(x) != len(y)
        or len(x) < 2
    ):
        return float("nan")

    mean_x = (
        sum(x)
        / len(x)
    )

    mean_y = (
        sum(y)
        / len(y)
    )

    numerator = sum(
        (
            a - mean_x
        )
        * (
            b - mean_y
        )
        for a, b
        in zip(x, y)
    )

    denominator_x = math.sqrt(
        sum(
            (
                a - mean_x
            ) ** 2
            for a in x
        )
    )

    denominator_y = math.sqrt(
        sum(
            (
                b - mean_y
            ) ** 2
            for b in y
        )
    )

    if (
        denominator_x == 0
        or denominator_y == 0
    ):
        return float("nan")

    return (
        numerator
        / (
            denominator_x
            * denominator_y
        )
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        required=True,
    )

    args = parser.parse_args()

    input_file = Path(
        args.input
    ).resolve()

    with input_file.open(
        newline="",
        encoding="utf-8",
    ) as handle:

        rows = list(
            csv.DictReader(handle)
        )

    grouped = defaultdict(
        list
    )

    for row in rows:

        sample_ms = int(
            float(
                row[
                    "sample_interval_ms"
                ]
            )
        )

        safe_gap_ms = float(
            row[
                "safe_gap_ms"
            ]
        )

        correct = int(
            row[
                "correct"
            ]
        )

        empirical_error = (
            1 - correct
        )

        analytical_error = max(
            0.0,
            1.0
            - safe_gap_ms
            / sample_ms,
        )

        item = {
            "sample_ms":
                sample_ms,

            "safe_gap_ms":
                safe_gap_ms,

            "correct":
                correct,

            "empirical_error":
                empirical_error,

            "analytical_error":
                analytical_error,
        }

        grouped[
            sample_ms
        ].append(
            item
        )

    print("=" * 115)

    print(
        "IBSTER V2E34-R - "
        "PROCESS-START FINAL STATISTICS"
    )

    print("=" * 115)

    print(
        "T(ms) | n | Correct | Accuracy | "
        "95% CI              | Emp.Error | "
        "Analytic Error | Mean safe gap"
    )

    print("-" * 115)

    summary = []

    for sample_ms in sorted(
        grouped
    ):

        group = (
            grouped[
                sample_ms
            ]
        )

        n = len(
            group
        )

        correct = sum(
            row[
                "correct"
            ]
            for row in group
        )

        accuracy = (
            correct
            / n
        )

        empirical_error = (
            1.0
            - accuracy
        )

        analytical_error = (
            sum(
                row[
                    "analytical_error"
                ]
                for row in group
            )
            / n
        )

        safe_gap_mean = (
            sum(
                row[
                    "safe_gap_ms"
                ]
                for row in group
            )
            / n
        )

        ci_low, ci_high = (
            wilson_interval(
                correct,
                n,
            )
        )

        summary.append({
            "sample_ms":
                sample_ms,

            "n":
                n,

            "correct":
                correct,

            "accuracy":
                accuracy,

            "error":
                empirical_error,

            "analytic":
                analytical_error,

            "safe_gap":
                safe_gap_mean,

            "ci_low":
                ci_low,

            "ci_high":
                ci_high,
        })

        print(
            f"{sample_ms:5d} | "
            f"{n:2d} | "
            f"{correct:7d} | "
            f"{accuracy:8.3f} | "
            f"[{ci_low:.3f}, {ci_high:.3f}] | "
            f"{empirical_error:9.3f} | "
            f"{analytical_error:14.3f} | "
            f"{safe_gap_mean:12.3f}"
        )

    empirical = [
        row[
            "error"
        ]
        for row in summary
    ]

    analytical = [
        row[
            "analytic"
        ]
        for row in summary
    ]

    correlation = (
        pearson(
            empirical,
            analytical,
        )
    )

    mae = (
        sum(
            abs(
                a - b
            )
            for a, b
            in zip(
                empirical,
                analytical,
            )
        )
        / len(summary)
    )

    rmse = math.sqrt(
        sum(
            (
                a - b
            ) ** 2
            for a, b
            in zip(
                empirical,
                analytical,
            )
        )
        / len(summary)
    )

    total = len(
        rows
    )

    total_correct = sum(
        int(
            row[
                "correct"
            ]
        )
        for row in rows
    )

    total_error = (
        total
        - total_correct
    )

    overall_low, overall_high = (
        wilson_interval(
            total_correct,
            total,
        )
    )

    print()
    print("=" * 115)

    print(
        "OVERALL"
    )

    print("-" * 115)

    print(
        f"Runs              : "
        f"{total}"
    )

    print(
        f"Correct           : "
        f"{total_correct}/{total}"
    )

    print(
        f"Errors            : "
        f"{total_error}/{total}"
    )

    print(
        f"Accuracy          : "
        f"{total_correct / total:.3f}"
    )

    print(
        f"95% Wilson CI     : "
        f"[{overall_low:.3f}, "
        f"{overall_high:.3f}]"
    )

    print()

    print(
        "ANALYTICAL MODEL FIT"
    )

    print("-" * 115)

    print(
        f"Pearson r         : "
        f"{correlation:.6f}"
    )

    print(
        f"MAE               : "
        f"{mae:.6f}"
    )

    print(
        f"RMSE              : "
        f"{rmse:.6f}"
    )

    print("=" * 115)

    output_file = (
        input_file.parent
        / "process_start_statistical_summary.csv"
    )

    fields = [
        "sample_interval_ms",
        "n",
        "correct",
        "accuracy",
        "error_rate",
        "wilson_low",
        "wilson_high",
        "analytical_error_rate",
        "mean_safe_gap_ms",
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

        for row in summary:

            writer.writerow({
                "sample_interval_ms":
                    row[
                        "sample_ms"
                    ],

                "n":
                    row[
                        "n"
                    ],

                "correct":
                    row[
                        "correct"
                    ],

                "accuracy":
                    row[
                        "accuracy"
                    ],

                "error_rate":
                    row[
                        "error"
                    ],

                "wilson_low":
                    row[
                        "ci_low"
                    ],

                "wilson_high":
                    row[
                        "ci_high"
                    ],

                "analytical_error_rate":
                    row[
                        "analytic"
                    ],

                "mean_safe_gap_ms":
                    row[
                        "safe_gap"
                    ],
            })

    print()
    print(
        f"Output: {output_file}"
    )


if __name__ == "__main__":
    main()
