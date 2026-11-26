import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


def read_csv(path):
    with path.open(
        newline="",
        encoding="utf-8",
    ) as source:
        return list(csv.DictReader(source))


def mean(values):
    if not values:
        return float("nan")

    return sum(values) / len(values)


def stddev(values):
    if len(values) < 2:
        return float("nan")

    avg = mean(values)

    variance = (
        sum(
            (value - avg) ** 2
            for value in values
        )
        / (len(values) - 1)
    )

    return math.sqrt(variance)


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
        + (z * z / total)
    )

    centre = (
        p
        + (
            z * z
            / (2 * total)
        )
    ) / denominator

    half_width = (
        z
        * math.sqrt(
            (
                p
                * (1 - p)
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
    if value is None:
        return ""

    if (
        isinstance(value, float)
        and math.isnan(value)
    ):
        return ""

    return f"{value:.6f}"


def read_ground_truth(run_dir):
    rows = read_csv(
        run_dir
        / "ground_truth.csv"
    )

    result = {}

    for row in rows:
        result[
            row["activity"]
        ] = {
            "start_ns":
                int(
                    row[
                        "start_monotonic_ns"
                    ]
                ),

            "end_ns":
                int(
                    row[
                        "end_monotonic_ns"
                    ]
                ),
        }

    return result


def read_ground_truth_relation(
    run_dir,
):
    rows = read_csv(
        run_dir
        / "ground_truth_relations.csv"
    )

    for row in rows:
        if (
            row["activity_a"]
            == "child_B"
            and
            row["activity_b"]
            == "file_read"
        ):
            return row["relation"]

    raise RuntimeError(
        "Relation child_B -> file_read "
        f"tidak ditemukan pada {run_dir}"
    )


def read_termination_reference(
    run_dir,
):
    path = (
        run_dir
        / "child_termination_reference.csv"
    )

    rows = read_csv(path)

    if len(rows) != 1:
        raise RuntimeError(
            "child_termination_reference.csv "
            f"tidak valid pada {run_dir}"
        )

    row = rows[0]

    return {
        "pre_exit_ns":
            int(
                row[
                    "child_pre_exit_ns"
                ]
            ),

        "wait_return_ns":
            int(
                row[
                    "child_wait_return_ns"
                ]
            ),

        "bracket_width_ms":
            float(
                row[
                    "exit_bracket_width_ms"
                ]
            ),
    }


def read_child_events(
    run_dir,
):
    rows = read_csv(
        run_dir
        / "child_process_events.csv"
    )

    start_events = [
        row
        for row in rows
        if row["event"]
        == "OBSERVED_START"
    ]

    end_events = [
        row
        for row in rows
        if row["event"]
        == "OBSERVED_END"
    ]

    start_event = None
    end_event = None

    if len(start_events) == 1:
        row = start_events[0]

        start_event = {
            "poll_index":
                int(
                    row[
                        "poll_index"
                    ]
                ),

            "timestamp_ns":
                int(
                    row[
                        "timestamp_monotonic_ns"
                    ]
                ),

            "child_pid":
                int(
                    row[
                        "child_pid"
                    ]
                ),
        }

    if len(end_events) == 1:
        row = end_events[0]

        end_event = {
            "poll_index":
                int(
                    row[
                        "poll_index"
                    ]
                ),

            "timestamp_ns":
                int(
                    row[
                        "timestamp_monotonic_ns"
                    ]
                ),

            "child_pid":
                int(
                    row[
                        "child_pid"
                    ]
                ),
        }

    return (
        start_event,
        end_event,
    )


def read_poll_trace(
    run_dir,
):
    rows = read_csv(
        run_dir
        / "poll_trace.csv"
    )

    result = []

    for row in rows:
        visible = (
            row[
                "visible_child_pids"
            ]
            .strip()
        )

        pids = set()

        if visible:
            for item in visible.split(";"):
                item = item.strip()

                if item:
                    pids.add(
                        int(item)
                    )

        result.append({
            "poll_index":
                int(
                    row[
                        "poll_index"
                    ]
                ),

            "timestamp_ns":
                int(
                    row[
                        "timestamp_monotonic_ns"
                    ]
                ),

            "sample_interval_ms":
                float(
                    row[
                        "sample_interval_ms"
                    ]
                ),

            "visible_pids":
                pids,
        })

    return result


def classify_bracket_position(
    observed_end_ns,
    pre_exit_ns,
    wait_return_ns,
):
    if observed_end_ns < pre_exit_ns:
        return "BEFORE_BRACKET"

    if observed_end_ns <= wait_return_ns:
        return "INSIDE_BRACKET"

    return "AFTER_BRACKET"


def classify_relation(
    child_end_ns,
    file_read_start_ns,
):
    if child_end_ns < file_read_start_ns:
        return "BEFORE"

    return "OVERLAPS"


def analyze_polling(
    poll_rows,
    child_pid,
    pre_exit_ns,
):
    poll_times = [
        row[
            "timestamp_ns"
        ]
        for row in poll_rows
    ]

    intervals_ms = [
        (
            poll_times[index]
            - poll_times[index - 1]
        ) / 1e6
        for index
        in range(
            1,
            len(poll_times)
        )
    ]

    previous_poll = None
    next_poll = None

    for row in poll_rows:

        timestamp_ns = (
            row[
                "timestamp_ns"
            ]
        )

        if timestamp_ns <= pre_exit_ns:
            previous_poll = row

        elif (
            timestamp_ns > pre_exit_ns
            and next_poll is None
        ):
            next_poll = row
            break

    measured_phase_ms = (
        float("nan")
    )

    time_to_next_poll_ms = (
        float("nan")
    )

    actual_bracketing_period_ms = (
        float("nan")
    )

    if previous_poll is not None:
        measured_phase_ms = (
            pre_exit_ns
            - previous_poll[
                "timestamp_ns"
            ]
        ) / 1e6

    if next_poll is not None:
        time_to_next_poll_ms = (
            next_poll[
                "timestamp_ns"
            ]
            - pre_exit_ns
        ) / 1e6

    if (
        previous_poll is not None
        and next_poll is not None
    ):
        actual_bracketing_period_ms = (
            next_poll[
                "timestamp_ns"
            ]
            - previous_poll[
                "timestamp_ns"
            ]
        ) / 1e6

    previous_child_visible = None
    first_child_absent = None

    for row in poll_rows:
        if child_pid in row["visible_pids"]:
            previous_child_visible = row

        elif (
            previous_child_visible is not None
            and row["poll_index"]
            > previous_child_visible[
                "poll_index"
            ]
        ):
            first_child_absent = row
            break

    return {
        "poll_count":
            len(poll_rows),

        "mean_poll_interval_ms":
            mean(intervals_ms),

        "std_poll_interval_ms":
            stddev(intervals_ms),

        "min_poll_interval_ms":
            min(intervals_ms)
            if intervals_ms
            else float("nan"),

        "max_poll_interval_ms":
            max(intervals_ms)
            if intervals_ms
            else float("nan"),

        "measured_pre_exit_phase_ms":
            measured_phase_ms,

        "time_to_next_poll_ms":
            time_to_next_poll_ms,

        "actual_bracketing_period_ms":
            actual_bracketing_period_ms,

        "previous_poll_ns":
            (
                previous_poll[
                    "timestamp_ns"
                ]
                if previous_poll
                else None
            ),

        "next_poll_ns":
            (
                next_poll[
                    "timestamp_ns"
                ]
                if next_poll
                else None
            ),

        "previous_child_visible_poll_ns":
            (
                previous_child_visible[
                    "timestamp_ns"
                ]
                if previous_child_visible
                else None
            ),

        "first_child_absent_poll_ns":
            (
                first_child_absent[
                    "timestamp_ns"
                ]
                if first_child_absent
                else None
            ),
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--capture-root",
        required=True,
    )

    args = parser.parse_args()

    capture_root = Path(
        args.capture_root
    ).resolve()

    results = []
    skipped = []

    for run_dir in sorted(
        capture_root.iterdir()
    ):
        if not run_dir.is_dir():
            continue

        required = [
            run_dir
            / "manifest.json",

            run_dir
            / "ground_truth.csv",

            run_dir
            / "ground_truth_relations.csv",

            run_dir
            / "child_termination_reference.csv",

            run_dir
            / "child_process_events.csv",

            run_dir
            / "poll_trace.csv",
        ]

        if not all(
            path.exists()
            for path in required
        ):
            skipped.append(
                run_dir.name
            )
            continue

        manifest = json.loads(
            (
                run_dir
                / "manifest.json"
            ).read_text(
                encoding="utf-8",
            )
        )

        ground_truth = (
            read_ground_truth(
                run_dir
            )
        )

        gt_relation = (
            read_ground_truth_relation(
                run_dir
            )
        )

        termination = (
            read_termination_reference(
                run_dir
            )
        )

        (
            observed_start,
            observed_end,
        ) = read_child_events(
            run_dir
        )

        if (
            observed_start is None
            or observed_end is None
        ):
            skipped.append(
                run_dir.name
            )
            continue

        poll_rows = (
            read_poll_trace(
                run_dir
            )
        )

        child_pid = (
            observed_end[
                "child_pid"
            ]
        )

        pre_exit_ns = (
            termination[
                "pre_exit_ns"
            ]
        )

        wait_return_ns = (
            termination[
                "wait_return_ns"
            ]
        )

        observed_end_ns = (
            observed_end[
                "timestamp_ns"
            ]
        )

        child_start_ns = (
            ground_truth[
                "child_B"
            ][
                "start_ns"
            ]
        )

        file_read_start_ns = (
            ground_truth[
                "file_read"
            ][
                "start_ns"
            ]
        )

        poll_stats = (
            analyze_polling(
                poll_rows,
                child_pid,
                pre_exit_ns,
            )
        )

        bracket_position = (
            classify_bracket_position(
                observed_end_ns,
                pre_exit_ns,
                wait_return_ns,
            )
        )

        observed_from_pre_exit_ms = (
            observed_end_ns
            - pre_exit_ns
        ) / 1e6

        observed_from_wait_ms = (
            observed_end_ns
            - wait_return_ns
        ) / 1e6

        start_lag_ms = (
            observed_start[
                "timestamp_ns"
            ]
            - child_start_ns
        ) / 1e6

        gt_boundary_wait_ms = (
            file_read_start_ns
            - wait_return_ns
        ) / 1e6

        gt_boundary_pre_exit_ms = (
            file_read_start_ns
            - pre_exit_ns
        ) / 1e6

        observed_boundary_ms = (
            file_read_start_ns
            - observed_end_ns
        ) / 1e6

        observed_relation = (
            classify_relation(
                observed_end_ns,
                file_read_start_ns,
            )
        )

        relation_match = int(
            observed_relation
            == gt_relation
        )

        relation_error = ""

        if not relation_match:
            relation_error = (
                f"{gt_relation}"
                "->"
                f"{observed_relation}"
            )

        sample_interval_ms = float(
            manifest[
                "sample_interval_ms"
            ]
        )

        analytical_error_probability = (
            float("nan")
        )

        if gt_relation == "BEFORE":

            measured_gap = max(
                gt_boundary_wait_ms,
                0.0,
            )

            analytical_error_probability = (
                max(
                    0.0,
                    1.0
                    - (
                        measured_gap
                        / sample_interval_ms
                    ),
                )
            )

        result = {
            "run_id":
                run_dir.name,

            "mode":
                manifest.get(
                    "mode",
                    "",
                ),

            "margin_ms":
                manifest.get(
                    "margin_ms",
                    "",
                ),

            "sample_interval_ms":
                sample_interval_ms,

            "workload_offset_ms":
                manifest.get(
                    "workload_offset_ms",
                    "",
                ),

            "workload_offset_source":
                manifest.get(
                    "workload_offset_source",
                    "",
                ),

            "rep":
                manifest.get(
                    "rep",
                    "",
                ),

            "seed":
                manifest.get(
                    "seed",
                    "",
                ),

            "gt_relation":
                gt_relation,

            "observed_relation":
                observed_relation,

            "relation_match":
                relation_match,

            "relation_error":
                relation_error,

            "termination_bracket_width_ms":
                termination[
                    "bracket_width_ms"
                ],

            "observed_end_from_pre_exit_ms":
                observed_from_pre_exit_ms,

            "observed_end_from_wait_return_ms":
                observed_from_wait_ms,

            "observed_end_bracket_position":
                bracket_position,

            "observed_start_lag_ms":
                start_lag_ms,

            "gt_boundary_wait_return_ms":
                gt_boundary_wait_ms,

            "gt_boundary_pre_exit_ms":
                gt_boundary_pre_exit_ms,

            "observed_boundary_ms":
                observed_boundary_ms,

            "measured_pre_exit_phase_ms":
                poll_stats[
                    "measured_pre_exit_phase_ms"
                ],

            "time_to_next_poll_ms":
                poll_stats[
                    "time_to_next_poll_ms"
                ],

            "actual_bracketing_period_ms":
                poll_stats[
                    "actual_bracketing_period_ms"
                ],

            "poll_count":
                poll_stats[
                    "poll_count"
                ],

            "mean_poll_interval_ms":
                poll_stats[
                    "mean_poll_interval_ms"
                ],

            "std_poll_interval_ms":
                poll_stats[
                    "std_poll_interval_ms"
                ],

            "min_poll_interval_ms":
                poll_stats[
                    "min_poll_interval_ms"
                ],

            "max_poll_interval_ms":
                poll_stats[
                    "max_poll_interval_ms"
                ],

            "analytical_error_probability":
                analytical_error_probability,
        }

        results.append(result)

    output_dir = (
        capture_root.parent
        / "analysis_bracket"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        output_dir
        / "termination_bracket_analysis.csv"
    )

    fields = [
        "run_id",
        "mode",
        "margin_ms",
        "sample_interval_ms",
        "workload_offset_ms",
        "workload_offset_source",
        "rep",
        "seed",

        "gt_relation",
        "observed_relation",
        "relation_match",
        "relation_error",

        "termination_bracket_width_ms",

        "observed_end_from_pre_exit_ms",
        "observed_end_from_wait_return_ms",
        "observed_end_bracket_position",

        "observed_start_lag_ms",

        "gt_boundary_wait_return_ms",
        "gt_boundary_pre_exit_ms",
        "observed_boundary_ms",

        "measured_pre_exit_phase_ms",
        "time_to_next_poll_ms",
        "actual_bracketing_period_ms",

        "poll_count",
        "mean_poll_interval_ms",
        "std_poll_interval_ms",
        "min_poll_interval_ms",
        "max_poll_interval_ms",

        "analytical_error_probability",
    ]

    numeric_fields = {
        "termination_bracket_width_ms",
        "observed_end_from_pre_exit_ms",
        "observed_end_from_wait_return_ms",
        "observed_start_lag_ms",
        "gt_boundary_wait_return_ms",
        "gt_boundary_pre_exit_ms",
        "observed_boundary_ms",
        "measured_pre_exit_phase_ms",
        "time_to_next_poll_ms",
        "actual_bracketing_period_ms",
        "mean_poll_interval_ms",
        "std_poll_interval_ms",
        "min_poll_interval_ms",
        "max_poll_interval_ms",
        "analytical_error_probability",
    }

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

        for row in results:
            output = dict(row)

            for field in numeric_fields:
                output[field] = (
                    safe_float(
                        row[field]
                    )
                )

            writer.writerow(output)

    print("=" * 110)

    print(
        "IBSTER V2E34-R - "
        "TERMINATION-BRACKET ANALYSIS"
    )

    print("=" * 110)

    print()

    print(
        f"Runs analysed : "
        f"{len(results)}"
    )

    print(
        f"Runs skipped  : "
        f"{len(skipped)}"
    )

    if skipped:
        print(
            "Skipped:"
        )

        for name in skipped:
            print(
                f"  - {name}"
            )

    if not results:
        print(
            "\nTidak ada run baru yang "
            "memiliki termination bracket."
        )
        return

    matched = sum(
        row[
            "relation_match"
        ]
        for row in results
    )

    lower_ci, upper_ci = (
        wilson_interval(
            matched,
            len(results),
        )
    )

    print()

    print(
        f"Relation agreement : "
        f"{matched}/{len(results)} "
        f"({matched / len(results):.3f})"
    )

    print(
        f"95% Wilson CI      : "
        f"[{lower_ci:.3f}, "
        f"{upper_ci:.3f}]"
    )

    print()

    print(
        "RUN DETAILS"
    )

    print(
        "-" * 110
    )

    for row in results:

        print(
            f"{row['run_id']} | "
            f"T={row['sample_interval_ms']:.0f} ms | "
            f"GT={row['gt_relation']:<8} | "
            f"OBS={row['observed_relation']:<8} | "
            f"bracket="
            f"{row['termination_bracket_width_ms']:7.3f} ms | "
            f"pre→obs="
            f"{row['observed_end_from_pre_exit_ms']:8.3f} ms | "
            f"wait→obs="
            f"{row['observed_end_from_wait_return_ms']:8.3f} ms | "
            f"{row['observed_end_bracket_position']}"
        )

    print()

    print(
        "BRACKET POSITION COUNTS"
    )

    print(
        "-" * 110
    )

    position_counts = defaultdict(int)

    for row in results:
        position_counts[
            row[
                "observed_end_bracket_position"
            ]
        ] += 1

    for label in [
        "BEFORE_BRACKET",
        "INSIDE_BRACKET",
        "AFTER_BRACKET",
    ]:
        print(
            f"{label:<16}: "
            f"{position_counts[label]}"
        )

    print()

    print(
        "SAMPLING-INTERVAL SUMMARY"
    )

    print(
        "-" * 110
    )

    grouped = defaultdict(list)

    for row in results:
        grouped[
            row[
                "sample_interval_ms"
            ]
        ].append(row)

    for sample_interval in sorted(
        grouped
    ):

        rows = grouped[
            sample_interval
        ]

        poll_means = [
            row[
                "mean_poll_interval_ms"
            ]
            for row in rows
        ]

        poll_jitters = [
            row[
                "std_poll_interval_ms"
            ]
            for row in rows
            if not math.isnan(
                row[
                    "std_poll_interval_ms"
                ]
            )
        ]

        brackets = [
            row[
                "termination_bracket_width_ms"
            ]
            for row in rows
        ]

        pre_lags = [
            row[
                "observed_end_from_pre_exit_ms"
            ]
            for row in rows
        ]

        wait_lags = [
            row[
                "observed_end_from_wait_return_ms"
            ]
            for row in rows
        ]

        correct = sum(
            row[
                "relation_match"
            ]
            for row in rows
        )

        print(
            f"T={sample_interval:.0f} ms | "
            f"n={len(rows):3d} | "
            f"agreement="
            f"{correct}/{len(rows)} | "
            f"poll mean="
            f"{mean(poll_means):8.3f} ms | "
            f"poll jitter="
            f"{mean(poll_jitters):7.3f} ms | "
            f"bracket mean="
            f"{mean(brackets):7.3f} ms | "
            f"pre→obs mean="
            f"{mean(pre_lags):8.3f} ms | "
            f"wait→obs mean="
            f"{mean(wait_lags):8.3f} ms"
        )

    print()

    print(
        f"Output: {output_file}"
    )


if __name__ == "__main__":
    main()