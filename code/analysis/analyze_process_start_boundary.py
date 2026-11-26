import argparse
import csv
import json
from pathlib import Path


def read_gt(path):

    data = {}

    with path.open(
        newline="",
        encoding="utf-8",
    ) as handle:

        for row in csv.DictReader(handle):

            data[
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

    return data


def read_single(path):

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

        gt_file = (
            run_dir
            / "ground_truth.csv"
        )

        events_file = (
            run_dir
            / "child_process_events.csv"
        )

        ref_file = (
            run_dir
            / "child_start_reference.csv"
        )

        manifest_file = (
            run_dir
            / "manifest.json"
        )

        if not all(
            p.exists()
            for p in [
                gt_file,
                events_file,
                ref_file,
                manifest_file,
            ]
        ):
            continue

        gt = read_gt(
            gt_file
        )

        ref = read_single(
            ref_file
        )

        manifest = json.loads(
            manifest_file.read_text(
                encoding="utf-8"
            )
        )

        target_child_pid = int(
            ref["pid"]
        )

        observed_start_ns = None
        observed_end_ns = None

        with events_file.open(
            newline="",
            encoding="utf-8",
        ) as handle:

            for event in csv.DictReader(
                handle
            ):

                if (
                    int(
                        event[
                            "child_pid"
                        ]
                    )
                    != target_child_pid
                ):
                    continue

                timestamp_ns = int(
                    event[
                        "timestamp_monotonic_ns"
                    ]
                )

                if (
                    event["event"]
                    == "OBSERVED_START"
                ):

                    observed_start_ns = (
                        timestamp_ns
                    )

                elif (
                    event["event"]
                    == "OBSERVED_END"
                ):

                    observed_end_ns = (
                        timestamp_ns
                    )

        if (
            observed_start_ns
            is None
            or observed_end_ns
            is None
        ):

            continue

        pre_spawn_ns = int(
            ref[
                "parent_pre_spawn_ns"
            ]
        )

        post_spawn_ns = int(
            ref[
                "parent_post_spawn_ns"
            ]
        )

        file_read = (
            gt["file_read"]
        )

        conservative_child = (
            gt["child_B"]
        )

        observed_child = {
            "start_ns":
                observed_start_ns,

            "end_ns":
                observed_end_ns,
        }

        gt_relation = (
            temporal_relation(
                conservative_child,
                file_read,
            )
        )

        observed_relation = (
            temporal_relation(
                observed_child,
                file_read,
            )
        )

        observed_vs_post_ms = (
            observed_start_ns
            - post_spawn_ns
        ) / 1e6

        observed_vs_file_ms = (
            observed_start_ns
            - file_read["start_ns"]
        ) / 1e6

        safe_gap_ms = (
            file_read["start_ns"]
            - post_spawn_ns
        ) / 1e6

        if (
            observed_start_ns
            < pre_spawn_ns
        ):

            position = (
                "BEFORE_BRACKET"
            )

        elif (
            observed_start_ns
            <= post_spawn_ns
        ):

            position = (
                "INSIDE_BRACKET"
            )

        else:

            position = (
                "AFTER_BRACKET"
            )

        results.append({
            "run_id":
                run_dir.name,

            "sample_interval_ms":
                manifest[
                    "sample_interval_ms"
                ],

            "margin_ms":
                manifest[
                    "margin_ms"
                ],

            "child_pid":
                target_child_pid,

            "gt_relation":
                gt_relation,

            "observed_relation":
                observed_relation,

            "correct":
                int(
                    gt_relation
                    == observed_relation
                ),

            "parent_pre_spawn_ns":
                pre_spawn_ns,

            "parent_post_spawn_ns":
                post_spawn_ns,

            "observed_start_ns":
                observed_start_ns,

            "file_read_start_ns":
                file_read["start_ns"],

            "start_bracket_width_ms":
                (
                    post_spawn_ns
                    - pre_spawn_ns
                ) / 1e6,

            "observed_vs_post_spawn_ms":
                observed_vs_post_ms,

            "safe_gap_ms":
                safe_gap_ms,

            "observed_start_vs_file_ms":
                observed_vs_file_ms,

            "observed_start_position":
                position,
        })

    results.sort(
        key=lambda x: (
            x["sample_interval_ms"],
            x["run_id"],
        )
    )

    print("=" * 125)

    print(
        "IBSTER V2E34-R - "
        "PROCESS-START BRACKET ANALYSIS"
    )

    print("=" * 125)

    for row in results:

        print(
            f"{row['run_id']} | "
            f"T={row['sample_interval_ms']:3d} ms | "
            f"GT={row['gt_relation']:9s} | "
            f"OBS={row['observed_relation']:9s} | "
            f"post→obs="
            f"{row['observed_vs_post_spawn_ms']:8.3f} ms | "
            f"safe gap="
            f"{row['safe_gap_ms']:7.3f} ms | "
            f"obs-file="
            f"{row['observed_start_vs_file_ms']:+8.3f} ms | "
            f"{row['observed_start_position']}"
        )

    print()

    total = len(
        results
    )

    correct = sum(
        row["correct"]
        for row in results
    )

    before = sum(
        row[
            "observed_start_position"
        ]
        == "BEFORE_BRACKET"
        for row in results
    )

    inside = sum(
        row[
            "observed_start_position"
        ]
        == "INSIDE_BRACKET"
        for row in results
    )

    after = sum(
        row[
            "observed_start_position"
        ]
        == "AFTER_BRACKET"
        for row in results
    )

    print(
        f"Runs analysed : "
        f"{total}"
    )

    if total:

        print(
            f"Agreement     : "
            f"{correct}/{total} "
            f"({correct / total:.3f})"
        )

    print()
    print(
        "START OBSERVATION POSITION"
    )

    print(
        f"BEFORE_BRACKET : {before}"
    )

    print(
        f"INSIDE_BRACKET : {inside}"
    )

    print(
        f"AFTER_BRACKET  : {after}"
    )

    output_file = (
        root
        / "process_start_boundary_analysis.csv"
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