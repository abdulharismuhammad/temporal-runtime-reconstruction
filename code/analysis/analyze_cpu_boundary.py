import argparse
import csv
import json
from pathlib import Path


def read_single_row(path):

    with path.open(
        newline="",
        encoding="utf-8",
    ) as handle:

        rows = list(
            csv.DictReader(handle)
        )

    if len(rows) != 1:
        raise RuntimeError(
            f"Expected one row: {path}"
        )

    return rows[0]


def read_ground_truth(path):

    result = {}

    with path.open(
        newline="",
        encoding="utf-8",
    ) as handle:

        for row in csv.DictReader(handle):

            result[row["activity"]] = {
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


def read_telemetry(path):

    rows = []

    with path.open(
        newline="",
        encoding="utf-8",
    ) as handle:

        for row in csv.DictReader(handle):

            rows.append({
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

                "cpu_percent":
                    float(
                        row[
                            "cpu_percent"
                        ]
                    ),
            })

    return rows


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
        and
        a_end >= b_end
    ):
        return "CONTAINS"

    if (
        a_start >= b_start
        and
        a_end <= b_end
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


def find_active_segments(
    telemetry,
    threshold,
    analysis_start_ns,
    analysis_end_ns,
):

    active_indices = []

    for index, sample in enumerate(
        telemetry
    ):

        timestamp = (
            sample[
                "timestamp_ns"
            ]
        )

        if timestamp < analysis_start_ns:
            continue

        if timestamp > analysis_end_ns:
            continue

        if (
            sample[
                "cpu_percent"
            ]
            >= threshold
        ):
            active_indices.append(
                index
            )

    if not active_indices:
        return []

    segments = []

    current = [
        active_indices[0]
    ]

    for index in active_indices[1:]:

        if (
            index
            == current[-1] + 1
        ):

            current.append(
                index
            )

        else:

            segments.append(
                current
            )

            current = [
                index
            ]

    segments.append(
        current
    )

    return segments


def choose_longest_segment(
    segments,
    telemetry,
):

    if not segments:
        return None

    def segment_score(segment):

        first = (
            telemetry[
                segment[0]
            ]
        )

        last = (
            telemetry[
                segment[-1]
            ]
        )

        duration_ns = (
            last[
                "timestamp_ns"
            ]
            - first[
                "timestamp_ns"
            ]
        )

        peak_cpu = max(
            telemetry[index][
                "cpu_percent"
            ]
            for index in segment
        )

        return (
            len(segment),
            duration_ns,
            peak_cpu,
        )

    return max(
        segments,
        key=segment_score,
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--capture-root",
        required=True,
    )

    args = parser.parse_args()

    root = Path(
        args.capture_root
    ).resolve()

    results = []

    for run_dir in sorted(
        p
        for p in root.iterdir()
        if p.is_dir()
    ):

        telemetry_file = (
            run_dir
            / "cpu_telemetry.csv"
        )

        gt_file = (
            run_dir
            / "ground_truth.csv"
        )

        analysis_file = (
            run_dir
            / "cpu_analysis_window.csv"
        )

        manifest_file = (
            run_dir
            / "manifest.json"
        )

        if not all(
            path.exists()
            for path in [
                telemetry_file,
                gt_file,
                analysis_file,
                manifest_file,
            ]
        ):
            continue

        telemetry = read_telemetry(
            telemetry_file
        )

        gt = read_ground_truth(
            gt_file
        )

        analysis = read_single_row(
            analysis_file
        )

        manifest = json.loads(
            manifest_file.read_text(
                encoding="utf-8"
            )
        )

        threshold = float(
            analysis[
                "cpu_threshold_percent"
            ]
        )

        analysis_start_ns = int(
            analysis[
                "analysis_start_ns"
            ]
        )

        analysis_end_ns = int(
            analysis[
                "analysis_end_ns"
            ]
        )

        segments = find_active_segments(
            telemetry,
            threshold,
            analysis_start_ns,
            analysis_end_ns,
        )

        selected = (
            choose_longest_segment(
                segments,
                telemetry,
            )
        )

        if selected is None:

            print(
                f"SKIP {run_dir.name}: "
                "no active CPU segment."
            )

            continue

        first_index = (
            selected[0]
        )

        last_index = (
            selected[-1]
        )

        first_active = (
            telemetry[
                first_index
            ]
        )

        last_active = (
            telemetry[
                last_index
            ]
        )

        # ==================================================
        # NAIVE POINT RECONSTRUCTION
        # ==================================================

        naive_cpu = {
            "start_ns":
                first_active[
                    "timestamp_ns"
                ],

            "end_ns":
                last_active[
                    "timestamp_ns"
                ],
        }

        # ==================================================
        # WINDOW-AWARE RECONSTRUCTION
        #
        # cpu_percent(t_i) summarizes CPU activity since
        # the previous observation t_(i-1).
        # ==================================================

        if first_index > 0:

            previous_timestamp = (
                telemetry[
                    first_index - 1
                ][
                    "timestamp_ns"
                ]
            )

        else:

            previous_timestamp = (
                analysis_start_ns
            )

        window_cpu = {
            "start_ns":
                max(
                    previous_timestamp,
                    analysis_start_ns,
                ),

            "end_ns":
                last_active[
                    "timestamp_ns"
                ],
        }

        gt_cpu = (
            gt["cpu_burst"]
        )

        child = (
            gt["child_B"]
        )

        gt_relation = (
            temporal_relation(
                gt_cpu,
                child,
            )
        )

        naive_relation = (
            temporal_relation(
                naive_cpu,
                child,
            )
        )

        window_relation = (
            temporal_relation(
                window_cpu,
                child,
            )
        )

        naive_start_error_ms = (
            naive_cpu["start_ns"]
            - gt_cpu["start_ns"]
        ) / 1e6

        naive_end_error_ms = (
            naive_cpu["end_ns"]
            - gt_cpu["end_ns"]
        ) / 1e6

        window_start_error_ms = (
            window_cpu["start_ns"]
            - gt_cpu["start_ns"]
        ) / 1e6

        window_end_error_ms = (
            window_cpu["end_ns"]
            - gt_cpu["end_ns"]
        ) / 1e6

        selected_cpu_values = [
            telemetry[index][
                "cpu_percent"
            ]
            for index in selected
        ]

        results.append({
            "run_id":
                run_dir.name,

            "sample_interval_ms":
                int(
                    manifest[
                        "sample_interval_ms"
                    ]
                ),

            "threshold_percent":
                threshold,

            "gt_relation":
                gt_relation,

            "naive_relation":
                naive_relation,

            "window_relation":
                window_relation,

            "naive_correct":
                int(
                    naive_relation
                    == gt_relation
                ),

            "window_correct":
                int(
                    window_relation
                    == gt_relation
                ),

            "active_segment_count":
                len(
                    segments
                ),

            "selected_segment_samples":
                len(
                    selected
                ),

            "first_active_poll":
                first_active[
                    "poll_index"
                ],

            "last_active_poll":
                last_active[
                    "poll_index"
                ],

            "selected_peak_cpu":
                max(
                    selected_cpu_values
                ),

            "selected_mean_cpu":
                sum(
                    selected_cpu_values
                )
                / len(
                    selected_cpu_values
                ),

            "naive_start_error_ms":
                naive_start_error_ms,

            "naive_end_error_ms":
                naive_end_error_ms,

            "window_start_error_ms":
                window_start_error_ms,

            "window_end_error_ms":
                window_end_error_ms,
        })

    results.sort(
        key=lambda row: (
            row[
                "sample_interval_ms"
            ],
            row["run_id"],
        )
    )

    print("=" * 155)

    print(
        "IBSTER V2E34-R - "
        "CPU-BOUNDARY CONTIGUOUS-SEGMENT ANALYSIS"
    )

    print("=" * 155)

    print(
        "T(ms) | GT       | Naive      | Window     | "
        "N.OK | W.OK | Segments | Samples | "
        "Naive start err | Window start err | "
        "Selected polls"
    )

    print("-" * 155)

    for row in results:

        print(
            f"{row['sample_interval_ms']:5d} | "
            f"{row['gt_relation']:8s} | "
            f"{row['naive_relation']:10s} | "
            f"{row['window_relation']:10s} | "
            f"{row['naive_correct']:4d} | "
            f"{row['window_correct']:4d} | "
            f"{row['active_segment_count']:8d} | "
            f"{row['selected_segment_samples']:7d} | "
            f"{row['naive_start_error_ms']:+15.3f} | "
            f"{row['window_start_error_ms']:+16.3f} | "
            f"{row['first_active_poll']}-"
            f"{row['last_active_poll']}"
        )

    total = len(
        results
    )

    naive_correct = sum(
        row["naive_correct"]
        for row in results
    )

    window_correct = sum(
        row["window_correct"]
        for row in results
    )

    print()
    print("=" * 155)

    print(
        f"Runs analysed        : "
        f"{total}"
    )

    if total:

        print(
            f"Naive correct        : "
            f"{naive_correct}/{total}"
        )

        print(
            f"Window-aware correct : "
            f"{window_correct}/{total}"
        )

    print("=" * 155)

    output_file = (
        root
        / "cpu_boundary_analysis.csv"
    )

    if results:

        with output_file.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:

            writer = csv.DictWriter(
                handle,
                fieldnames=list(
                    results[0].keys()
                ),
            )

            writer.writeheader()

            writer.writerows(
                results
            )

    print()
    print(
        f"Output: {output_file}"
    )


if __name__ == "__main__":
    main()