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
        return list(csv.DictReader(handle))


def hypergeom_probability(
    x,
    row1_total,
    row2_total,
    error_total,
):
    total = row1_total + row2_total

    return (
        math.comb(
            error_total,
            x,
        )
        *
        math.comb(
            total - error_total,
            row1_total - x,
        )
        /
        math.comb(
            total,
            row1_total,
        )
    )


def fisher_exact_two_sided(
    a,
    b,
    c,
    d,
):
    # Table:
    #
    #           Error   Correct
    # BEFORE      a       b
    # OVERLAP     c       d

    row1 = a + b
    row2 = c + d

    error_total = a + c

    lower = max(
        0,
        row1 - (
            row1 + row2
            - error_total
        ),
    )

    upper = min(
        row1,
        error_total,
    )

    observed = (
        hypergeom_probability(
            a,
            row1,
            row2,
            error_total,
        )
    )

    p_value = 0.0

    for x in range(
        lower,
        upper + 1,
    ):
        probability = (
            hypergeom_probability(
                x,
                row1,
                row2,
                error_total,
            )
        )

        if probability <= (
            observed
            + 1e-15
        ):
            p_value += probability

    return min(
        1.0,
        p_value,
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

    half = (
        z
        * math.sqrt(
            p * (1 - p) / total
            + z * z
            / (
                4
                * total
                * total
            )
        )
        / denominator
    )

    return (
        centre - half,
        centre + half,
    )


def summarise(rows):
    total = len(rows)

    correct = sum(
        int(
            row[
                "relation_match"
            ]
        )
        for row in rows
    )

    errors = (
        total - correct
    )

    return {
        "total":
            total,

        "correct":
            correct,

        "errors":
            errors,

        "error_rate":
            errors / total,
    }


def group_by_interval(rows):
    grouped = defaultdict(list)

    for row in rows:

        sample_ms = int(
            float(
                row[
                    "sample_interval_ms"
                ]
            )
        )

        grouped[
            sample_ms
        ].append(row)

    return grouped


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

    before_grouped = (
        group_by_interval(
            before_rows
        )
    )

    overlap_grouped = (
        group_by_interval(
            overlap_rows
        )
    )

    intervals = sorted(
        set(before_grouped)
        | set(overlap_grouped)
    )

    output_rows = []

    print(
        "=" * 108
    )

    print(
        "IBSTER V2E34-R - "
        "ASYMMETRY SIGNIFICANCE ANALYSIS"
    )

    print(
        "=" * 108
    )

    print()

    print(
        " T(ms) | B errors | B total | "
        "O errors | O total | "
        "Risk diff | Fisher p"
    )

    print(
        "-" * 108
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

        risk_difference = (
            before[
                "error_rate"
            ]
            - overlap[
                "error_rate"
            ]
        )

        p_value = (
            fisher_exact_two_sided(
                before[
                    "errors"
                ],
                before[
                    "correct"
                ],
                overlap[
                    "errors"
                ],
                overlap[
                    "correct"
                ],
            )
        )

        before_error_ci = (
            wilson_interval(
                before[
                    "errors"
                ],
                before[
                    "total"
                ],
            )
        )

        overlap_error_ci = (
            wilson_interval(
                overlap[
                    "errors"
                ],
                overlap[
                    "total"
                ],
            )
        )

        output_rows.append({
            "sample_interval_ms":
                sample_ms,

            "before_errors":
                before[
                    "errors"
                ],

            "before_total":
                before[
                    "total"
                ],

            "before_error_rate":
                before[
                    "error_rate"
                ],

            "before_error_ci_low":
                before_error_ci[0],

            "before_error_ci_high":
                before_error_ci[1],

            "overlap_errors":
                overlap[
                    "errors"
                ],

            "overlap_total":
                overlap[
                    "total"
                ],

            "overlap_error_rate":
                overlap[
                    "error_rate"
                ],

            "overlap_error_ci_low":
                overlap_error_ci[0],

            "overlap_error_ci_high":
                overlap_error_ci[1],

            "risk_difference":
                risk_difference,

            "fisher_exact_p":
                p_value,
        })

        print(
            f"{sample_ms:6d} | "
            f"{before['errors']:8d} | "
            f"{before['total']:7d} | "
            f"{overlap['errors']:8d} | "
            f"{overlap['total']:7d} | "
            f"{risk_difference:9.3f} | "
            f"{p_value:.6g}"
        )

    before_total = summarise(
        before_rows
    )

    overlap_total = summarise(
        overlap_rows
    )

    overall_difference = (
        before_total[
            "error_rate"
        ]
        - overlap_total[
            "error_rate"
        ]
    )

    overall_p = (
        fisher_exact_two_sided(
            before_total[
                "errors"
            ],
            before_total[
                "correct"
            ],
            overlap_total[
                "errors"
            ],
            overlap_total[
                "correct"
            ],
        )
    )

    print()
    print(
        "=" * 108
    )

    print(
        "OVERALL"
    )

    print(
        "-" * 108
    )

    print(
        f"BEFORE errors      : "
        f"{before_total['errors']}/"
        f"{before_total['total']} "
        f"({before_total['error_rate']:.3f})"
    )

    print(
        f"OVERLAPS errors    : "
        f"{overlap_total['errors']}/"
        f"{overlap_total['total']} "
        f"({overlap_total['error_rate']:.3f})"
    )

    print(
        f"Risk difference    : "
        f"{overall_difference:.3f}"
    )

    print(
        f"Fisher exact p     : "
        f"{overall_p:.8g}"
    )

    output_file = (
        before_file.parent
        / "boundary_asymmetry_significance.csv"
    )

    fields = [
        "sample_interval_ms",
        "before_errors",
        "before_total",
        "before_error_rate",
        "before_error_ci_low",
        "before_error_ci_high",
        "overlap_errors",
        "overlap_total",
        "overlap_error_rate",
        "overlap_error_ci_low",
        "overlap_error_ci_high",
        "risk_difference",
        "fisher_exact_p",
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

        for row in output_rows:
            writer.writerow(
                row
            )

    print()
    print(
        f"Output: {output_file}"
    )


if __name__ == "__main__":
    main()
