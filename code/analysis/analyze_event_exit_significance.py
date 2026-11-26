import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


def exact_mcnemar(b, c):
    """
    Exact two-sided McNemar test.

    b = polling wrong, event correct
    c = polling correct, event wrong
    """

    n = b + c

    if n == 0:
        return 1.0

    k = min(b, c)

    probability = 0.0

    for i in range(
        0,
        k + 1,
    ):
        probability += (
            math.comb(n, i)
            * (0.5 ** n)
        )

    return min(
        1.0,
        2.0 * probability,
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

    print("=" * 100)

    print(
        "IBSTER V2E34-R - "
        "POLLING VS EVENT-DRIVEN "
        "PAIRED SIGNIFICANCE"
    )

    print("=" * 100)

    print(
        "T(ms) | n | Poll correct | Event correct | "
        "Poll wrong/Event right | "
        "Poll right/Event wrong | McNemar p"
    )

    print("-" * 100)

    total_b = 0
    total_c = 0

    for sample_ms in sorted(
        grouped
    ):

        group = (
            grouped[
                sample_ms
            ]
        )

        polling_correct = sum(
            int(
                row[
                    "polling_correct"
                ]
            )
            for row in group
        )

        event_correct = sum(
            int(
                row[
                    "event_correct"
                ]
            )
            for row in group
        )

        b = sum(
            (
                int(
                    row[
                        "polling_correct"
                    ]
                ) == 0
                and
                int(
                    row[
                        "event_correct"
                    ]
                ) == 1
            )
            for row in group
        )

        c = sum(
            (
                int(
                    row[
                        "polling_correct"
                    ]
                ) == 1
                and
                int(
                    row[
                        "event_correct"
                    ]
                ) == 0
            )
            for row in group
        )

        p_value = (
            exact_mcnemar(
                b,
                c,
            )
        )

        total_b += b
        total_c += c

        print(
            f"{sample_ms:5d} | "
            f"{len(group):2d} | "
            f"{polling_correct:12d} | "
            f"{event_correct:13d} | "
            f"{b:22d} | "
            f"{c:22d} | "
            f"{p_value:.8g}"
        )

    overall_p = (
        exact_mcnemar(
            total_b,
            total_c,
        )
    )

    polling_total = sum(
        int(
            row[
                "polling_correct"
            ]
        )
        for row in rows
    )

    event_total = sum(
        int(
            row[
                "event_correct"
            ]
        )
        for row in rows
    )

    print()
    print("=" * 100)

    print("OVERALL")

    print("-" * 100)

    print(
        f"Runs                    : "
        f"{len(rows)}"
    )

    print(
        f"Polling correct         : "
        f"{polling_total}/{len(rows)}"
    )

    print(
        f"Event-driven correct    : "
        f"{event_total}/{len(rows)}"
    )

    print(
        f"Polling wrong/Event right: "
        f"{total_b}"
    )

    print(
        f"Polling right/Event wrong: "
        f"{total_c}"
    )

    print(
        f"Exact McNemar p         : "
        f"{overall_p:.12g}"
    )

    print("=" * 100)


if __name__ == "__main__":
    main()
