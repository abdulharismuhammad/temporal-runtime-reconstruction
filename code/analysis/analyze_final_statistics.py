import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def read_csv(path):
    with path.open(
        newline="",
        encoding="utf-8",
    ) as handle:
        return list(csv.DictReader(handle))


def mean(values):
    if not values:
        return float("nan")
    return sum(values) / len(values)


def wilson_interval(
    successes,
    total,
    z=1.959963984540054,
):
    if total == 0:
        return float("nan"), float("nan")

    p = successes / total

    denominator = (
        1.0
        + z * z / total
    )

    centre = (
        p
        + z * z / (2 * total)
    ) / denominator

    half_width = (
        z
        * math.sqrt(
            p * (1 - p) / total
            + z * z / (
                4 * total * total
            )
        )
        / denominator
    )

    return (
        centre - half_width,
        centre + half_width,
    )


def correlation(xs, ys):
    if len(xs) != len(ys):
        raise ValueError(
            "Panjang data tidak sama."
        )

    if len(xs) < 2:
        return float("nan")

    mx = mean(xs)
    my = mean(ys)

    numerator = sum(
        (x - mx) * (y - my)
        for x, y in zip(xs, ys)
    )

    denominator_x = math.sqrt(
        sum(
            (x - mx) ** 2
            for x in xs
        )
    )

    denominator_y = math.sqrt(
        sum(
            (y - my) ** 2
            for y in ys
        )
    )

    denominator = (
        denominator_x
        * denominator_y
    )

    if denominator == 0:
        return float("nan")

    return numerator / denominator


def rmse(xs, ys):
    if not xs:
        return float("nan")

    return math.sqrt(
        mean(
            [
                (x - y) ** 2
                for x, y in zip(xs, ys)
            ]
        )
    )


def mae(xs, ys):
    if not xs:
        return float("nan")

    return mean(
        [
            abs(x - y)
            for x, y in zip(xs, ys)
        ]
    )


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

    parser.add_argument(
        "--matrix-file",
        required=True,
    )

    parser.add_argument(
        "--asymmetry-file",
        required=True,
    )

    args = parser.parse_args()

    before_file = Path(
        args.before_file
    ).resolve()

    overlap_file = Path(
        args.overlap_file
    ).resolve()

    matrix_file = Path(
        args.matrix_file
    ).resolve()

    asymmetry_file = Path(
        args.asymmetry_file
    ).resolve()

    before_rows = read_csv(
        before_file
    )

    overlap_rows = read_csv(
        overlap_file
    )

    matrix_rows = read_csv(
        matrix_file
    )

    asymmetry_rows = read_csv(
        asymmetry_file
    )

    output_dir = (
        before_file.parent
        / "final_statistics"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ==================================================
    # 1. BEFORE ACCURACY BY SAMPLING INTERVAL
    # ==================================================

    before_grouped = defaultdict(list)

    for row in before_rows:

        sample_ms = int(
            float(
                row[
                    "sample_interval_ms"
                ]
            )
        )

        before_grouped[
            sample_ms
        ].append(row)

    sampling_intervals = sorted(
        before_grouped
    )

    before_accuracy = []
    before_ci_low = []
    before_ci_high = []

    for sample_ms in sampling_intervals:

        group = before_grouped[
            sample_ms
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

        accuracy = (
            correct / n
        )

        low, high = (
            wilson_interval(
                correct,
                n,
            )
        )

        before_accuracy.append(
            accuracy
        )

        before_ci_low.append(
            accuracy - low
        )

        before_ci_high.append(
            high - accuracy
        )

    plt.figure(
        figsize=(8, 5)
    )

    plt.errorbar(
        sampling_intervals,
        before_accuracy,
        yerr=[
            before_ci_low,
            before_ci_high,
        ],
        marker="o",
        capsize=4,
    )

    plt.xlabel(
        "Sampling interval (ms)"
    )

    plt.ylabel(
        "BEFORE relation accuracy"
    )

    plt.title(
        "BEFORE Reconstruction Accuracy "
        "vs Sampling Interval"
    )

    plt.ylim(
        0,
        1.05,
    )

    plt.grid(
        True,
        alpha=0.25,
    )

    plt.tight_layout()

    figure1 = (
        output_dir
        / "before_accuracy_vs_sampling.png"
    )

    plt.savefig(
        figure1,
        dpi=300,
    )

    plt.close()

    # ==================================================
    # 2. EMPIRICAL VS ANALYTICAL ERROR
    # ==================================================

    empirical = [
        float(
            row[
                "empirical_error_probability"
            ]
        )
        for row in matrix_rows
    ]

    analytical = [
        float(
            row[
                "analytic_error_probability"
            ]
        )
        for row in matrix_rows
    ]

    correlation_value = correlation(
        analytical,
        empirical,
    )

    mae_value = mae(
        analytical,
        empirical,
    )

    rmse_value = rmse(
        analytical,
        empirical,
    )

    plt.figure(
        figsize=(6, 6)
    )

    plt.scatter(
        analytical,
        empirical,
        s=55,
    )

    plt.plot(
        [0, 1],
        [0, 1],
        linestyle="--",
    )

    plt.xlabel(
        "Analytical error probability"
    )

    plt.ylabel(
        "Empirical error probability"
    )

    plt.title(
        "Analytical vs Empirical "
        "BEFORE→OVERLAPS Error"
    )

    plt.xlim(
        -0.03,
        1.03,
    )

    plt.ylim(
        -0.03,
        1.03,
    )

    plt.grid(
        True,
        alpha=0.25,
    )

    plt.tight_layout()

    figure2 = (
        output_dir
        / "empirical_vs_analytical_error.png"
    )

    plt.savefig(
        figure2,
        dpi=300,
    )

    plt.close()

    # ==================================================
    # 3. ASYMMETRY PLOT
    # ==================================================

    asymmetry_intervals = [
        int(
            float(
                row[
                    "sample_interval_ms"
                ]
            )
        )
        for row in asymmetry_rows
    ]

    before_acc = [
        float(
            row[
                "before_accuracy"
            ]
        )
        for row in asymmetry_rows
    ]

    overlap_acc = [
        float(
            row[
                "overlap_accuracy"
            ]
        )
        for row in asymmetry_rows
    ]

    plt.figure(
        figsize=(8, 5)
    )

    plt.plot(
        asymmetry_intervals,
        before_acc,
        marker="o",
        label="BEFORE",
    )

    plt.plot(
        asymmetry_intervals,
        overlap_acc,
        marker="s",
        label="OVERLAPS",
    )

    plt.xlabel(
        "Sampling interval (ms)"
    )

    plt.ylabel(
        "Relation reconstruction accuracy"
    )

    plt.title(
        "Asymmetric Effect of Sampling "
        "Resolution on Temporal Relations"
    )

    plt.ylim(
        0,
        1.05,
    )

    plt.grid(
        True,
        alpha=0.25,
    )

    plt.legend()

    plt.tight_layout()

    figure3 = (
        output_dir
        / "before_vs_overlap_asymmetry.png"
    )

    plt.savefig(
        figure3,
        dpi=300,
    )

    plt.close()

    # ==================================================
    # 4. ERROR RATE BY SAMPLING INTERVAL
    # ==================================================

    before_error = [
        1.0 - value
        for value in before_acc
    ]

    overlap_error = [
        1.0 - value
        for value in overlap_acc
    ]

    plt.figure(
        figsize=(8, 5)
    )

    plt.plot(
        asymmetry_intervals,
        before_error,
        marker="o",
        label="BEFORE error",
    )

    plt.plot(
        asymmetry_intervals,
        overlap_error,
        marker="s",
        label="OVERLAPS error",
    )

    plt.xlabel(
        "Sampling interval (ms)"
    )

    plt.ylabel(
        "Relation error rate"
    )

    plt.title(
        "Directional Relation Error "
        "Across Sampling Intervals"
    )

    plt.ylim(
        -0.02,
        0.62,
    )

    plt.grid(
        True,
        alpha=0.25,
    )

    plt.legend()

    plt.tight_layout()

    figure4 = (
        output_dir
        / "relation_error_asymmetry.png"
    )

    plt.savefig(
        figure4,
        dpi=300,
    )

    plt.close()

    # ==================================================
    # 5. SUMMARY STATISTICS
    # ==================================================

    before_total = len(
        before_rows
    )

    before_correct = sum(
        int(
            row[
                "relation_match"
            ]
        )
        for row in before_rows
    )

    overlap_total = len(
        overlap_rows
    )

    overlap_correct = sum(
        int(
            row[
                "relation_match"
            ]
        )
        for row in overlap_rows
    )

    before_errors = (
        before_total
        - before_correct
    )

    overlap_errors = (
        overlap_total
        - overlap_correct
    )

    before_accuracy_total = (
        before_correct
        / before_total
    )

    overlap_accuracy_total = (
        overlap_correct
        / overlap_total
    )

    before_ci = wilson_interval(
        before_correct,
        before_total,
    )

    overlap_ci = wilson_interval(
        overlap_correct,
        overlap_total,
    )

    before_before_bracket = sum(
        1
        for row in before_rows
        if (
            row[
                "observed_end_bracket_position"
            ]
            == "BEFORE_BRACKET"
        )
    )

    overlap_before_bracket = sum(
        1
        for row in overlap_rows
        if (
            row[
                "observed_end_bracket_position"
            ]
            == "BEFORE_BRACKET"
        )
    )

    summary_file = (
        output_dir
        / "final_statistical_summary.txt"
    )

    summary_text = f"""
IBSTER V2E34-R - FINAL STATISTICAL SUMMARY
============================================================

BEFORE experiment
------------------------------------------------------------
Runs                 : {before_total}
Correct              : {before_correct}
Errors               : {before_errors}
Accuracy             : {before_accuracy_total:.6f}
95% Wilson CI        : [{before_ci[0]:.6f}, {before_ci[1]:.6f}]
BEFORE_BRACKET cases : {before_before_bracket}

OVERLAPS control
------------------------------------------------------------
Runs                 : {overlap_total}
Correct              : {overlap_correct}
Errors               : {overlap_errors}
Accuracy             : {overlap_accuracy_total:.6f}
95% Wilson CI        : [{overlap_ci[0]:.6f}, {overlap_ci[1]:.6f}]
BEFORE_BRACKET cases : {overlap_before_bracket}

Boundary asymmetry
------------------------------------------------------------
BEFORE error rate    : {before_errors / before_total:.6f}
OVERLAPS error rate  : {overlap_errors / overlap_total:.6f}
Difference           : {(before_errors / before_total) - (overlap_errors / overlap_total):.6f}

Analytical model agreement
------------------------------------------------------------
Pearson correlation  : {correlation_value:.6f}
MAE                  : {mae_value:.6f}
RMSE                 : {rmse_value:.6f}

Figures
------------------------------------------------------------
{figure1}
{figure2}
{figure3}
{figure4}
""".strip()

    summary_file.write_text(
        summary_text,
        encoding="utf-8",
    )

    # ==================================================
    # DISPLAY
    # ==================================================

    print(
        "=" * 90
    )

    print(
        "IBSTER V2E34-R - "
        "FINAL STATISTICAL ANALYSIS"
    )

    print(
        "=" * 90
    )

    print()

    print(
        "BEFORE"
    )

    print(
        f"  Runs       : "
        f"{before_total}"
    )

    print(
        f"  Correct    : "
        f"{before_correct}"
    )

    print(
        f"  Errors     : "
        f"{before_errors}"
    )

    print(
        f"  Accuracy   : "
        f"{before_accuracy_total:.3f}"
    )

    print(
        f"  95% CI     : "
        f"[{before_ci[0]:.3f}, "
        f"{before_ci[1]:.3f}]"
    )

    print()

    print(
        "OVERLAPS"
    )

    print(
        f"  Runs       : "
        f"{overlap_total}"
    )

    print(
        f"  Correct    : "
        f"{overlap_correct}"
    )

    print(
        f"  Errors     : "
        f"{overlap_errors}"
    )

    print(
        f"  Accuracy   : "
        f"{overlap_accuracy_total:.3f}"
    )

    print(
        f"  95% CI     : "
        f"[{overlap_ci[0]:.3f}, "
        f"{overlap_ci[1]:.3f}]"
    )

    print()

    print(
        "ANALYTICAL MODEL"
    )

    print(
        f"  Pearson r  : "
        f"{correlation_value:.3f}"
    )

    print(
        f"  MAE        : "
        f"{mae_value:.3f}"
    )

    print(
        f"  RMSE       : "
        f"{rmse_value:.3f}"
    )

    print()

    print(
        "ASYMMETRY"
    )

    print(
        f"  BEFORE error   : "
        f"{before_errors / before_total:.3f}"
    )

    print(
        f"  OVERLAPS error : "
        f"{overlap_errors / overlap_total:.3f}"
    )

    print(
        f"  Difference     : "
        f"{(before_errors / before_total) - (overlap_errors / overlap_total):.3f}"
    )

    print()

    print(
        "OUTPUT FILES"
    )

    print(
        f"  {figure1}"
    )

    print(
        f"  {figure2}"
    )

    print(
        f"  {figure3}"
    )

    print(
        f"  {figure4}"
    )

    print(
        f"  {summary_file}"
    )


if __name__ == "__main__":
    main()
