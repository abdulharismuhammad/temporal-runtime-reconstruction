import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


def wilson_interval(successes, n, z=1.959963984540054):

    if n == 0:
        return float("nan"), float("nan")

    p = successes / n

    denominator = 1.0 + z * z / n

    center = (
        p
        + z * z / (2 * n)
    ) / denominator

    half = (
        z
        * math.sqrt(
            p * (1 - p) / n
            + z * z / (4 * n * n)
        )
        / denominator
    )

    return (
        center - half,
        center + half,
    )


def exact_mcnemar_p(b, c):

    """
    Exact two-sided McNemar test.

    b:
        naive wrong, window correct

    c:
        naive correct, window wrong
    """

    n = b + c

    if n == 0:
        return 1.0

    k = min(b, c)

    cumulative = 0.0

    for i in range(
        0,
        k + 1,
    ):

        cumulative += (
            math.comb(n, i)
            * (0.5 ** n)
        )

    return min(
        1.0,
        2.0 * cumulative,
    )


def mean(values):

    if not values:
        return float("nan")

    return (
        sum(values)
        / len(values)
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

    grouped = defaultdict(list)

    for row in rows:

        t = int(
            float(
                row[
                    "sample_interval_ms"
                ]
            )
        )

        grouped[t].append(row)

    print("=" * 140)

    print(
        "IBSTER V2E34-R - "
        "CPU-BOUNDARY FINAL STATISTICS"
    )

    print("=" * 140)

    print(
        "T(ms) | n | Naive | 95% CI          | "
        "Window | 95% CI          | "
        "Discordant N→W | W→N | McNemar p"
    )

    print("-" * 140)

    summary = []

    for t in sorted(grouped):

        group = grouped[t]

        n = len(group)

        naive_correct = sum(
            int(
                row[
                    "naive_correct"
                ]
            )
            for row in group
        )

        window_correct = sum(
            int(
                row[
                    "window_correct"
                ]
            )
            for row in group
        )

        naive_ci = wilson_interval(
            naive_correct,
            n,
        )

        window_ci = wilson_interval(
            window_correct,
            n,
        )

        # naive wrong, window right
        b = sum(
            (
                int(
                    row[
                        "naive_correct"
                    ]
                )
                == 0
            )
            and
            (
                int(
                    row[
                        "window_correct"
                    ]
                )
                == 1
            )
            for row in group
        )

        # naive right, window wrong
        c = sum(
            (
                int(
                    row[
                        "naive_correct"
                    ]
                )
                == 1
            )
            and
            (
                int(
                    row[
                        "window_correct"
                    ]
                )
                == 0
            )
            for row in group
        )

        p_value = (
            exact_mcnemar_p(
                b,
                c,
            )
        )

        naive_errors = [
            float(
                row[
                    "naive_start_error_ms"
                ]
            )
            for row in group
        ]

        window_errors = [
            float(
                row[
                    "window_start_error_ms"
                ]
            )
            for row in group
        ]

        summary.append({
            "sample_interval_ms":
                t,

            "n":
                n,

            "naive_correct":
                naive_correct,

            "naive_accuracy":
                naive_correct / n,

            "naive_ci_low":
                naive_ci[0],

            "naive_ci_high":
                naive_ci[1],

            "window_correct":
                window_correct,

            "window_accuracy":
                window_correct / n,

            "window_ci_low":
                window_ci[0],

            "window_ci_high":
                window_ci[1],

            "discordant_naive_wrong_window_right":
                b,

            "discordant_naive_right_window_wrong":
                c,

            "mcnemar_exact_p":
                p_value,

            "mean_naive_start_error_ms":
                mean(
                    naive_errors
                ),

            "mean_window_start_error_ms":
                mean(
                    window_errors
                ),

            "mean_abs_naive_start_error_ms":
                mean(
                    [
                        abs(x)
                        for x
                        in naive_errors
                    ]
                ),

            "mean_abs_window_start_error_ms":
                mean(
                    [
                        abs(x)
                        for x
                        in window_errors
                    ]
                ),
        })

        print(
            f"{t:5d} | "
            f"{n:2d} | "
            f"{naive_correct:2d}/{n:<2d} | "
            f"[{naive_ci[0]:.3f}, "
            f"{naive_ci[1]:.3f}] | "
            f"{window_correct:2d}/{n:<2d} | "
            f"[{window_ci[0]:.3f}, "
            f"{window_ci[1]:.3f}] | "
            f"{b:14d} | "
            f"{c:3d} | "
            f"{p_value:.9g}"
        )

    total = len(rows)

    total_naive = sum(
        int(
            row[
                "naive_correct"
            ]
        )
        for row in rows
    )

    total_window = sum(
        int(
            row[
                "window_correct"
            ]
        )
        for row in rows
    )

    naive_ci = wilson_interval(
        total_naive,
        total,
    )

    window_ci = wilson_interval(
        total_window,
        total,
    )

    b_total = sum(
        (
            int(
                row[
                    "naive_correct"
                ]
            )
            == 0
        )
        and
        (
            int(
                row[
                    "window_correct"
                ]
            )
            == 1
        )
        for row in rows
    )

    c_total = sum(
        (
            int(
                row[
                    "naive_correct"
                ]
            )
            == 1
        )
        and
        (
            int(
                row[
                    "window_correct"
                ]
            )
            == 0
        )
        for row in rows
    )

    overall_p = exact_mcnemar_p(
        b_total,
        c_total,
    )

    naive_start_errors = [
        float(
            row[
                "naive_start_error_ms"
            ]
        )
        for row in rows
    ]

    window_start_errors = [
        float(
            row[
                "window_start_error_ms"
            ]
        )
        for row in rows
    ]

    print()
    print("=" * 140)

    print(
        "OVERALL"
    )

    print("-" * 140)

    print(
        f"Runs                    : "
        f"{total}"
    )

    print(
        f"Naive correct           : "
        f"{total_naive}/{total} "
        f"({total_naive / total:.3f})"
    )

    print(
        f"Naive 95% Wilson CI     : "
        f"[{naive_ci[0]:.3f}, "
        f"{naive_ci[1]:.3f}]"
    )

    print()

    print(
        f"Window-aware correct    : "
        f"{total_window}/{total} "
        f"({total_window / total:.3f})"
    )

    print(
        f"Window 95% Wilson CI    : "
        f"[{window_ci[0]:.3f}, "
        f"{window_ci[1]:.3f}]"
    )

    print()

    print(
        f"Absolute accuracy gain  : "
        f"{(
            total_window
            - total_naive
        ) / total:.3f}"
    )

    print()

    print(
        "PAIRED COMPARISON"
    )

    print("-" * 140)

    print(
        f"Naive wrong / Window right : "
        f"{b_total}"
    )

    print(
        f"Naive right / Window wrong : "
        f"{c_total}"
    )

    print(
        f"Exact McNemar p             : "
        f"{overall_p:.12g}"
    )

    print()

    print(
        "START-BOUNDARY ERROR"
    )

    print("-" * 140)

    print(
        f"Mean naive error       : "
        f"{mean(naive_start_errors):+.3f} ms"
    )

    print(
        f"Mean window error      : "
        f"{mean(window_start_errors):+.3f} ms"
    )

    print(
        f"Mean |naive error|     : "
        f"{mean([abs(x) for x in naive_start_errors]):.3f} ms"
    )

    print(
        f"Mean |window error|    : "
        f"{mean([abs(x) for x in window_start_errors]):.3f} ms"
    )

    print("=" * 140)

    output_file = (
        input_file.parent
        / "cpu_boundary_statistical_summary.csv"
    )

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=list(
                summary[0].keys()
            ),
        )

        writer.writeheader()

        writer.writerows(
            summary
        )

    print()
    print(
        f"Output: {output_file}"
    )


if __name__ == "__main__":
    main()
