import argparse
import csv
import json
import math
from pathlib import Path


def read_csv(path):
    with path.open(
        newline="",
        encoding="utf-8",
    ) as source:
        return list(
            csv.DictReader(source)
        )


def mean(values):
    if not values:
        return float("nan")

    return (
        sum(values)
        / len(values)
    )


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

    return math.sqrt(
        variance
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

    p = (
        successes
        / total
    )

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
                z
                * z
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


def read_ground_truth(
    run_dir,
):
    rows = read_csv(
        run_dir
        / "ground_truth.csv"
    )

    return {
        row["activity"]: {
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
        for row in rows
    }


def get_ground_truth_relation(
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
            return row[
                "relation"
            ]

    raise RuntimeError(
        "Target relation "
        "child_B -> file_read "
        f"tidak ditemukan: {run_dir}"
    )


def find_observed_end(
    run_dir,
):
    rows = read_csv(
        run_dir
        / "child_process_events.csv"
    )

    end_events = [
        row
        for row in rows
        if row["event"]
        == "OBSERVED_END"
    ]

    if len(end_events) != 1:
        return None

    row = end_events[0]

    return {
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


def find_observed_start(
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

    if len(start_events) != 1:
        return None

    row = start_events[0]

    return {
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


def analyze_poll_trace(
    run_dir,
    child_start_ns,
    child_end_ns,
):
    rows = read_csv(
        run_dir
        / "poll_trace.csv"
    )

    poll_times = [
        int(
            row[
                "timestamp_monotonic_ns"
            ]
        )
        for row in rows
    ]

    if len(poll_times) < 2:
        raise RuntimeError(
            f"Poll trace terlalu pendek: "
            f"{run_dir}"
        )

    poll_intervals_ms = [
        (
            poll_times[index]
            - poll_times[index - 1]
        )
        / 1e6
        for index
        in range(
            1,
            len(poll_times)
        )
    ]

    previous_end_polls = [
        value
        for value in poll_times
        if value <= child_end_ns
    ]

    next_end_polls = [
        value
        for value in poll_times
        if value > child_end_ns
    ]

    previous_start_polls = [
        value
        for value in poll_times
        if value <= child_start_ns
    ]

    next_start_polls = [
        value
        for value in poll_times
        if value > child_start_ns
    ]

    previous_end_poll_ns = (
        max(
            previous_end_polls
        )
        if previous_end_polls
        else None
    )

    next_end_poll_ns = (
        min(
            next_end_polls
        )
        if next_end_polls
        else None
    )

    previous_start_poll_ns = (
        max(
            previous_start_polls
        )
        if previous_start_polls
        else None
    )

    next_start_poll_ns = (
        min(
            next_start_polls
        )
        if next_start_polls
        else None
    )

    if (
        previous_end_poll_ns
        is not None
    ):
        end_phase_ms = (
            child_end_ns
            - previous_end_poll_ns
        ) / 1e6
    else:
        end_phase_ms = (
            float("nan")
        )

    if (
        next_end_poll_ns
        is not None
    ):
        time_to_next_end_poll_ms = (
            next_end_poll_ns
            - child_end_ns
        ) / 1e6
    else:
        time_to_next_end_poll_ms = (
            float("nan")
        )

    if (
        previous_start_poll_ns
        is not None
    ):
        start_phase_ms = (
            child_start_ns
            - previous_start_poll_ns
        ) / 1e6
    else:
        start_phase_ms = (
            float("nan")
        )

    if (
        next_start_poll_ns
        is not None
    ):
        time_to_next_start_poll_ms = (
            next_start_poll_ns
            - child_start_ns
        ) / 1e6
    else:
        time_to_next_start_poll_ms = (
            float("nan")
        )

    return {
        "poll_count":
            len(
                poll_times
            ),

        "mean_poll_interval_ms":
            mean(
                poll_intervals_ms
            ),

        "std_poll_interval_ms":
            stddev(
                poll_intervals_ms
            ),

        "min_poll_interval_ms":
            min(
                poll_intervals_ms
            ),

        "max_poll_interval_ms":
            max(
                poll_intervals_ms
            ),

        "previous_end_poll_ns":
            previous_end_poll_ns,

        "next_end_poll_ns":
            next_end_poll_ns,

        "true_end_sampler_phase_ms":
            end_phase_ms,

        "time_to_next_end_poll_ms":
            time_to_next_end_poll_ms,

        "previous_start_poll_ns":
            previous_start_poll_ns,

        "next_start_poll_ns":
            next_start_poll_ns,

        "true_start_sampler_phase_ms":
            start_phase_ms,

        "time_to_next_start_poll_ms":
            time_to_next_start_poll_ms,
    }


def classify_relation(
    child_end_ns,
    read_start_ns,
):
    if (
        child_end_ns
        < read_start_ns
    ):
        return "BEFORE"

    return "OVERLAPS"


def safe_float(
    value,
):
    if (
        value is None
        or (
            isinstance(
                value,
                float,
            )
            and math.isnan(
                value
            )
        )
    ):
        return ""

    return (
        f"{value:.6f}"
    )


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

        required_files = [
            run_dir
            / "manifest.json",

            run_dir
            / "ground_truth.csv",

            run_dir
            / "ground_truth_relations.csv",

            run_dir
            / "poll_trace.csv",

            run_dir
            / "child_process_events.csv",
        ]

        if not all(
            path.exists()
            for path
            in required_files
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

        gt = (
            read_ground_truth(
                run_dir
            )
        )

        gt_relation = (
            get_ground_truth_relation(
                run_dir
            )
        )

        child_start_ns = (
            gt[
                "child_B"
            ]["start_ns"]
        )

        child_end_ns = (
            gt[
                "child_B"
            ]["end_ns"]
        )

        read_start_ns = (
            gt[
                "file_read"
            ]["start_ns"]
        )

        gt_boundary_ms = (
            read_start_ns
            - child_end_ns
        ) / 1e6

        observed_end = (
            find_observed_end(
                run_dir
            )
        )

        observed_start = (
            find_observed_start(
                run_dir
            )
        )

        poll_stats = (
            analyze_poll_trace(
                run_dir,
                child_start_ns,
                child_end_ns,
            )
        )

        if (
            observed_end
            is not None
        ):
            observed_end_ns = (
                observed_end[
                    "timestamp_ns"
                ]
            )

            observed_end_lag_ms = (
                observed_end_ns
                - child_end_ns
            ) / 1e6

            observed_boundary_ms = (
                read_start_ns
                - observed_end_ns
            ) / 1e6

            observed_relation = (
                classify_relation(
                    observed_end_ns,
                    read_start_ns,
                )
            )

        else:
            observed_end_ns = None
            observed_end_lag_ms = (
                float("nan")
            )
            observed_boundary_ms = (
                float("nan")
            )
            observed_relation = (
                "NOT_AVAILABLE"
            )

        if (
            observed_start
            is not None
        ):
            observed_start_ns = (
                observed_start[
                    "timestamp_ns"
                ]
            )

            observed_start_lag_ms = (
                observed_start_ns
                - child_start_ns
            ) / 1e6

        else:
            observed_start_ns = None
            observed_start_lag_ms = (
                float("nan")
            )

        matched = int(
            observed_relation
            == gt_relation
        )

        relation_error = ""

        if (
            observed_relation
            != gt_relation
        ):
            relation_error = (
                f"{gt_relation}"
                "->"
                f"{observed_relation}"
            )

        analytical_error_probability = (
            float("nan")
        )

        if (
            gt_relation
            == "BEFORE"
        ):
            sample_ms = float(
                manifest[
                    "sample_interval_ms"
                ]
            )

            analytical_error_probability = (
                max(
                    0.0,
                    1.0
                    - (
                        max(
                            gt_boundary_ms,
                            0.0,
                        )
                        / sample_ms
                    ),
                )
            )

        phase_plus_lag_ms = (
            poll_stats[
                "true_end_sampler_phase_ms"
            ]
            + observed_end_lag_ms
        )

        phase_interval_error_ms = (
            phase_plus_lag_ms
            - poll_stats[
                "mean_poll_interval_ms"
            ]
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
                manifest.get(
                    "sample_interval_ms",
                    "",
                ),

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

            "matched":
                matched,

            "relation_error":
                relation_error,

            "gt_boundary_ms":
                gt_boundary_ms,

            "observed_boundary_ms":
                observed_boundary_ms,

            "observed_end_lag_ms":
                observed_end_lag_ms,

            "observed_start_lag_ms":
                observed_start_lag_ms,

            "true_end_sampler_phase_ms":
                poll_stats[
                    "true_end_sampler_phase_ms"
                ],

            "time_to_next_end_poll_ms":
                poll_stats[
                    "time_to_next_end_poll_ms"
                ],

            "true_start_sampler_phase_ms":
                poll_stats[
                    "true_start_sampler_phase_ms"
                ],

            "time_to_next_start_poll_ms":
                poll_stats[
                    "time_to_next_start_poll_ms"
                ],

            "phase_plus_end_lag_ms":
                phase_plus_lag_ms,

            "phase_interval_error_ms":
                phase_interval_error_ms,

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

        results.append(
            result
        )

    output_dir = (
        capture_root.parent
        / "analysis"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        output_dir
        / "measured_sampling_phase.csv"
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
        "matched",
        "relation_error",

        "gt_boundary_ms",
        "observed_boundary_ms",

        "observed_end_lag_ms",
        "observed_start_lag_ms",

        "true_end_sampler_phase_ms",
        "time_to_next_end_poll_ms",

        "true_start_sampler_phase_ms",
        "time_to_next_start_poll_ms",

        "phase_plus_end_lag_ms",
        "phase_interval_error_ms",

        "poll_count",
        "mean_poll_interval_ms",
        "std_poll_interval_ms",
        "min_poll_interval_ms",
        "max_poll_interval_ms",

        "analytical_error_probability",
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

        for row in results:

            output = dict(
                row
            )

            numeric_fields = [
                "gt_boundary_ms",
                "observed_boundary_ms",
                "observed_end_lag_ms",
                "observed_start_lag_ms",
                "true_end_sampler_phase_ms",
                "time_to_next_end_poll_ms",
                "true_start_sampler_phase_ms",
                "time_to_next_start_poll_ms",
                "phase_plus_end_lag_ms",
                "phase_interval_error_ms",
                "mean_poll_interval_ms",
                "std_poll_interval_ms",
                "min_poll_interval_ms",
                "max_poll_interval_ms",
                "analytical_error_probability",
            ]

            for field in numeric_fields:
                output[field] = (
                    safe_float(
                        row[field]
                    )
                )

            writer.writerow(
                output
            )

    # ==================================================
    # TERMINAL SUMMARY
    # ==================================================
    print(
        "=" * 100
    )

    print(
        "IBSTER V2E34-R - "
        "MEASURED SAMPLING-PHASE ANALYSIS"
    )

    print(
        "=" * 100
    )

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

        for item in skipped:
            print(
                f"  - {item}"
            )

    if not results:
        print(
            "Tidak ada run valid."
        )

        return

    matched = sum(
        row[
            "matched"
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
        "-" * 100
    )

    for row in results:

        print(
            f"{row['run_id']} | "
            f"T={row['sample_interval_ms']} ms | "
            f"GT={row['gt_relation']:<8} | "
            f"OBS={row['observed_relation']:<8} | "
            f"gap={row['gt_boundary_ms']:+8.3f} ms | "
            f"phase="
            f"{row['true_end_sampler_phase_ms']:8.3f} ms | "
            f"lag="
            f"{row['observed_end_lag_ms']:8.3f} ms | "
            f"poll mean="
            f"{row['mean_poll_interval_ms']:8.3f} ms"
        )

    print()

    print(
        "AGGREGATE TIMING"
    )

    print(
        "-" * 100
    )

    end_lags = [
        row[
            "observed_end_lag_ms"
        ]
        for row in results
        if not math.isnan(
            row[
                "observed_end_lag_ms"
            ]
        )
    ]

    end_phases = [
        row[
            "true_end_sampler_phase_ms"
        ]
        for row in results
        if not math.isnan(
            row[
                "true_end_sampler_phase_ms"
            ]
        )
    ]

    poll_means = [
        row[
            "mean_poll_interval_ms"
        ]
        for row in results
    ]

    poll_jitters = [
        row[
            "std_poll_interval_ms"
        ]
        for row in results
        if not math.isnan(
            row[
                "std_poll_interval_ms"
            ]
        )
    ]

    print(
        f"Mean end lag      : "
        f"{mean(end_lags):.3f} ms"
    )

    print(
        f"Mean end phase    : "
        f"{mean(end_phases):.3f} ms"
    )

    print(
        f"Mean poll period  : "
        f"{mean(poll_means):.3f} ms"
    )

    print(
        f"Mean poll jitter  : "
        f"{mean(poll_jitters):.3f} ms"
    )

    print()

    print(
        f"Output: {output_file}"
    )


if __name__ == "__main__":
    main()
