import argparse
import csv
from pathlib import Path


def read_single_row(path):
    with path.open(
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != 1:
        raise RuntimeError(
            f"Expected exactly one row in {path}"
        )

    return rows[0]


def read_ground_truth(path):
    result = {}

    with path.open(
        newline="",
        encoding="utf-8",
    ) as handle:

        reader = csv.DictReader(handle)

        for row in reader:
            result[row["activity"]] = {
                "start_ns": int(
                    row["start_monotonic_ns"]
                ),
                "end_ns": int(
                    row["end_monotonic_ns"]
                ),
            }

    return result


def temporal_relation(a, b):

    a_start = a["start_ns"]
    a_end = a["end_ns"]

    b_start = b["start_ns"]
    b_end = b["end_ns"]

    if a_end < b_start:
        return "BEFORE"

    if a_start > b_end:
        return "AFTER"

    if (
        a_start <= b_start
        and a_end >= b_end
    ):
        return "CONTAINS"

    if (
        a_start >= b_start
        and a_end <= b_end
    ):
        return "DURING"

    if (
        a_start
        < b_start
        < a_end
        < b_end
    ):
        return "OVERLAPS"

    if (
        b_start
        < a_start
        < b_end
        < a_end
    ):
        return "OVERLAPPED_BY"

    return "INTERSECTS"


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--capture-root",
        required=True,
    )

    parser.add_argument(
        "--bracket-analysis",
        required=True,
    )

    args = parser.parse_args()

    capture_root = Path(
        args.capture_root
    ).resolve()

    bracket_analysis = Path(
        args.bracket_analysis
    ).resolve()

    # --------------------------------------------------
    # Load polling-analysis rows
    # --------------------------------------------------

    polling_rows = {}

    with bracket_analysis.open(
        newline="",
        encoding="utf-8",
    ) as handle:

        reader = csv.DictReader(handle)

        for row in reader:
            polling_rows[
                row["run_id"]
            ] = row

    results = []

    # --------------------------------------------------
    # Iterate run directories
    # --------------------------------------------------

    for run_dir in sorted(
        path
        for path in capture_root.iterdir()
        if path.is_dir()
    ):

        run_id = run_dir.name

        if run_id not in polling_rows:
            continue

        event_file = (
            run_dir
            / "child_exit_event.csv"
        )

        gt_file = (
            run_dir
            / "ground_truth.csv"
        )

        condition_file = (
            run_dir
            / "condition.csv"
        )

        if not (
            event_file.exists()
            and gt_file.exists()
            and condition_file.exists()
        ):
            continue

        polling = polling_rows[
            run_id
        ]

        event = read_single_row(
            event_file
        )

        condition = read_single_row(
            condition_file
        )

        gt = read_ground_truth(
            gt_file
        )

        # --------------------------------------------------
        # Event-driven child interval
        # --------------------------------------------------

        event_child = {
            "start_ns":
                gt["child_B"]["start_ns"],

            "end_ns":
                int(
                    event[
                        "exit_observed_monotonic_ns"
                    ]
                ),
        }

        file_read = {
            "start_ns":
                gt["file_read"]["start_ns"],

            "end_ns":
                gt["file_read"]["end_ns"],
        }

        event_relation = (
            temporal_relation(
                event_child,
                file_read,
            )
        )

        event_boundary_ms = (
            file_read["start_ns"]
            - event_child["end_ns"]
        ) / 1e6

        polling_relation = (
            polling[
                "observed_relation"
            ]
        )

        gt_relation = (
            polling[
                "gt_relation"
            ]
        )

        polling_correct = (
            polling_relation
            == gt_relation
        )

        event_correct = (
            event_relation
            == gt_relation
        )

        results.append({
            "run_id":
                run_id,

            "sample_interval_ms":
                float(
                    polling[
                        "sample_interval_ms"
                    ]
                ),

            "margin_ms":
                float(
                    condition[
                        "margin_ms"
                    ]
                ),

            "gt_relation":
                gt_relation,

            "polling_relation":
                polling_relation,

            "event_relation":
                event_relation,

            "polling_correct":
                int(
                    polling_correct
                ),

            "event_correct":
                int(
                    event_correct
                ),

            "event_boundary_ms":
                event_boundary_ms,

            "event_vs_pre_exit_ms":
                float(
                    event[
                        "event_vs_pre_exit_ms"
                    ]
                ),

            "event_vs_wait_return_ms":
                float(
                    event[
                        "event_vs_wait_return_ms"
                    ]
                ),

            "event_position":
                event[
                    "event_position"
                ],

            "event_delivered":
                int(
                    event[
                        "event_delivered"
                    ]
                ),
        })

    # --------------------------------------------------
    # Sort
    # --------------------------------------------------

    results.sort(
        key=lambda row:
            row["sample_interval_ms"]
    )

    # --------------------------------------------------
    # Print
    # --------------------------------------------------

    print(
        "=" * 125
    )

    print(
        "IBSTER V2E34-R - "
        "POLLING VS EVENT-DRIVEN EXIT"
    )

    print(
        "=" * 125
    )

    print(
        "T(ms) | GT     | Polling   | Event     | "
        "Poll OK | Event OK | Event boundary | "
        "Event position"
    )

    print(
        "-" * 125
    )

    for row in results:

        print(
            f"{row['sample_interval_ms']:5.0f} | "
            f"{row['gt_relation']:6s} | "
            f"{row['polling_relation']:9s} | "
            f"{row['event_relation']:9s} | "
            f"{row['polling_correct']:7d} | "
            f"{row['event_correct']:8d} | "
            f"{row['event_boundary_ms']:13.3f} | "
            f"{row['event_position']}"
        )

    total = len(results)

    polling_correct = sum(
        row["polling_correct"]
        for row in results
    )

    event_correct = sum(
        row["event_correct"]
        for row in results
    )

    delivered = sum(
        row["event_delivered"]
        for row in results
    )

    print()
    print(
        "=" * 125
    )

    print(
        f"Runs analysed       : {total}"
    )

    print(
        f"Polling correct     : "
        f"{polling_correct}/{total}"
    )

    print(
        f"Event-driven correct: "
        f"{event_correct}/{total}"
    )

    print(
        f"Events delivered    : "
        f"{delivered}/{total}"
    )

    print(
        "=" * 125
    )

    # --------------------------------------------------
    # Save CSV
    # --------------------------------------------------

    output_file = (
        bracket_analysis.parent
        / "polling_vs_event_exit.csv"
    )

    fields = [
        "run_id",
        "sample_interval_ms",
        "margin_ms",
        "gt_relation",
        "polling_relation",
        "event_relation",
        "polling_correct",
        "event_correct",
        "event_boundary_ms",
        "event_vs_pre_exit_ms",
        "event_vs_wait_return_ms",
        "event_position",
        "event_delivered",
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
