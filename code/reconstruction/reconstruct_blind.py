import argparse
import csv
import gzip
import json
import re
from datetime import datetime, timedelta
from pathlib import Path


TARGET = "behavior_target.bin"

OPEN_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}\.\d+)\s+open\s+"
    r"F=(\d+)\s+\(([^)]*)\)"
)

EVENT_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}\.\d+)\s+"
    r"(read|write|close|unlink)\b"
)

FD_RE = re.compile(r"\bF=(\d+)\b")


def clock_to_monotonic_ns(clock_text, manifest):
    ref_wall_ns = int(manifest["reference_wall_ns"])
    ref_mono_ns = int(manifest["reference_monotonic_ns"])

    ref_dt = datetime.fromtimestamp(ref_wall_ns / 1e9)

    clock_dt = datetime.strptime(
        clock_text,
        "%H:%M:%S.%f",
    )

    event_dt = ref_dt.replace(
        hour=clock_dt.hour,
        minute=clock_dt.minute,
        second=clock_dt.second,
        microsecond=clock_dt.microsecond,
    )

    candidates = [
        event_dt - timedelta(days=1),
        event_dt,
        event_dt + timedelta(days=1),
    ]

    event_dt = min(
        candidates,
        key=lambda x: abs(
            (x - ref_dt).total_seconds()
        ),
    )

    event_wall_ns = int(
        event_dt.timestamp() * 1e9
    )

    return (
        ref_mono_ns
        + event_wall_ns
        - ref_wall_ns
    )


def classify_session(session, previous_sessions):
    flags = session["flags"]
    reads = session["read_count"]
    writes = session["write_count"]

    if (
        "W" in flags
        and "C" in flags
        and writes > 0
    ):
        return "file_create_write_observed"

    if (
        "W" in flags
        and writes > 0
        and previous_sessions
    ):
        return "existing_file_write_observed"

    if (
        "R" in flags
        and reads > 0
        and writes == 0
    ):
        return "file_read_observed"

    return "filesystem_session_observed"


def parse_filesystem(run_dir, manifest):
    log = run_dir / "fs_usage_target.txt.gz"

    sessions = []
    active = {}
    unlink_events = []

    with gzip.open(
        log,
        "rt",
        encoding="utf-8",
        errors="replace",
    ) as source:

        for line_number, line in enumerate(
            source,
            start=1,
        ):
            if TARGET in line and " open " in line:
                match = OPEN_RE.match(line)

                if not match:
                    continue

                clock, fd, flags = match.groups()

                session = {
                    "fd": fd,
                    "flags": flags,
                    "open_clock": clock,
                    "close_clock": None,
                    "open_ns":
                        clock_to_monotonic_ns(
                            clock,
                            manifest,
                        ),
                    "close_ns": None,
                    "read_count": 0,
                    "write_count": 0,
                    "open_line": line_number,
                    "close_line": None,
                }

                sessions.append(session)
                active[fd] = session
                continue

            if TARGET in line and " unlink " in line:
                match = EVENT_RE.match(line)

                if (
                    match
                    and match.group(2) == "unlink"
                ):
                    clock = match.group(1)

                    unlink_events.append({
                        "timestamp_ns":
                            clock_to_monotonic_ns(
                                clock,
                                manifest,
                            ),
                        "clock": clock,
                        "line": line_number,
                    })

                continue

            event_match = EVENT_RE.match(line)

            if not event_match:
                continue

            clock, operation = (
                event_match.groups()
            )

            fd_match = FD_RE.search(line)

            if not fd_match:
                continue

            fd = fd_match.group(1)

            if fd not in active:
                continue

            session = active[fd]

            if operation == "read":
                session["read_count"] += 1

            elif operation == "write":
                session["write_count"] += 1

            elif operation == "close":
                session["close_clock"] = clock
                session["close_ns"] = (
                    clock_to_monotonic_ns(
                        clock,
                        manifest,
                    )
                )
                session["close_line"] = (
                    line_number
                )

                del active[fd]

    return sessions, unlink_events


def read_child_intervals(run_dir):
    path = (
        run_dir
        / "child_process_events.csv"
    )

    starts = {}
    intervals = []

    with path.open(
        newline="",
        encoding="utf-8",
    ) as source:

        for row in csv.DictReader(source):
            pid = row["child_pid"]
            timestamp = int(
                row["timestamp_monotonic_ns"]
            )

            if row["event"] == "OBSERVED_START":
                starts[pid] = row

            elif (
                row["event"] == "OBSERVED_END"
                and pid in starts
            ):
                start = starts.pop(pid)

                intervals.append({
                    "pid": pid,
                    "name":
                        start["child_name"],
                    "start_ns": int(
                        start[
                            "timestamp_monotonic_ns"
                        ]
                    ),
                    "end_ns": timestamp,
                })

    return intervals


def read_cpu_intervals(
    run_dir,
    excluded_intervals,
    threshold=50.0,
):
    path = run_dir / "cpu_telemetry.csv"

    candidates = []

    with path.open(
        newline="",
        encoding="utf-8",
    ) as source:

        for row in csv.DictReader(source):
            timestamp = int(
                row["timestamp_monotonic_ns"]
            )

            cpu = float(
                row["cpu_percent"]
            )

            child_count = int(
                row["child_count"]
            )

            excluded = any(
                start <= timestamp <= end
                for start, end
                in excluded_intervals
            )

            if (
                cpu >= threshold
                and child_count == 0
                and not excluded
            ):
                candidates.append({
                    "timestamp_ns": timestamp,
                    "cpu_percent": cpu,
                })

    if not candidates:
        return []

    groups = []
    current = [candidates[0]]

    max_gap_ns = 250_000_000

    for sample in candidates[1:]:
        gap = (
            sample["timestamp_ns"]
            - current[-1]["timestamp_ns"]
        )

        if gap <= max_gap_ns:
            current.append(sample)
        else:
            groups.append(current)
            current = [sample]

    groups.append(current)

    intervals = []

    for group in groups:
        if len(group) < 3:
            continue

        mean_cpu = sum(
            item["cpu_percent"]
            for item in group
        ) / len(group)

        intervals.append({
            "start_ns":
                group[0]["timestamp_ns"],
            "end_ns":
                group[-1]["timestamp_ns"],
            "samples": len(group),
            "mean_cpu": mean_cpu,
        })

    return intervals


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
        a_start < b_start
        < a_end < b_end
    ):
        return "OVERLAPS"

    if (
        b_start < a_start
        < b_end < a_end
    ):
        return "OVERLAPPED_BY"

    return "INTERSECTS"


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--run-dir",
        required=True,
    )

    args = parser.parse_args()

    run_dir = Path(
        args.run_dir
    ).resolve()

    manifest = json.loads(
        (
            run_dir / "manifest.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    reference_ns = int(
        manifest["reference_monotonic_ns"]
    )

    sessions, unlink_events = (
        parse_filesystem(
            run_dir,
            manifest,
        )
    )

    child_intervals = (
        read_child_intervals(
            run_dir
        )
    )

    behaviors = []
    fs_intervals = []
    previous_sessions = []

    # --------------------------------------------
    # FILESYSTEM BEHAVIORS
    # --------------------------------------------
    for session in sessions:
        if session["close_ns"] is None:
            continue

        behavior = classify_session(
            session,
            previous_sessions,
        )

        item = {
            "behavior": behavior,
            "start_ns":
                session["open_ns"],
            "end_ns":
                session["close_ns"],
            "source": "fs_usage",
            "evidence_strength":
                "direct",
            "details": (
                f"FD={session['fd']};"
                f"flags={session['flags']};"
                f"reads="
                f"{session['read_count']};"
                f"writes="
                f"{session['write_count']}"
            ),
        }

        behaviors.append(item)

        fs_intervals.append(
            (
                session["open_ns"],
                session["close_ns"],
            )
        )

        previous_sessions.append(
            session
        )

    # --------------------------------------------
    # CHILD BEHAVIOR
    # --------------------------------------------
    for child in child_intervals:
        behaviors.append({
            "behavior":
                "child_process_observed",
            "start_ns":
                child["start_ns"],
            "end_ns":
                child["end_ns"],
            "source":
                "psutil_process_tree",
            "evidence_strength":
                "direct_sampled",
            "details": (
                f"pid={child['pid']};"
                f"name={child['name']}"
            ),
        })

    # --------------------------------------------
    # CPU INFERENCE
    # --------------------------------------------
    excluded = (
        fs_intervals
        + [
            (
                item["start_ns"],
                item["end_ns"],
            )
            for item
            in child_intervals
        ]
    )

    cpu_intervals = (
        read_cpu_intervals(
            run_dir,
            excluded,
        )
    )

    for interval in cpu_intervals:
        behaviors.append({
            "behavior":
                "cpu_busy_without_direct_file_or_child_evidence",
            "start_ns":
                interval["start_ns"],
            "end_ns":
                interval["end_ns"],
            "source":
                "psutil_cpu",
            "evidence_strength":
                "inferred",
            "details": (
                f"samples="
                f"{interval['samples']};"
                f"mean_cpu="
                f"{interval['mean_cpu']:.2f};"
                "threshold=50.0"
            ),
        })

    # --------------------------------------------
    # UNLINK POINT EVENT
    # --------------------------------------------
    for unlink in unlink_events:
        behaviors.append({
            "behavior":
                "file_unlink_observed",
            "start_ns":
                unlink["timestamp_ns"],
            "end_ns":
                unlink["timestamp_ns"],
            "source":
                "fs_usage",
            "evidence_strength":
                "direct",
            "details":
                f"log_line={unlink['line']}",
        })

    behaviors.sort(
        key=lambda item: (
            item["start_ns"],
            item["end_ns"],
        )
    )

    for index, item in enumerate(
        behaviors,
        start=1,
    ):
        item["id"] = f"B{index:02d}"

    output_dir = (
        run_dir
        / "v2e11_blind_reconstruction"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    interval_file = (
        output_dir
        / "observed_behavior_intervals.csv"
    )

    fields = [
        "behavior_id",
        "behavior",
        "start_monotonic_ns",
        "end_monotonic_ns",
        "start_relative_s",
        "end_relative_s",
        "duration_s",
        "source",
        "evidence_strength",
        "details",
    ]

    with interval_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as destination:

        writer = csv.DictWriter(
            destination,
            fieldnames=fields,
        )

        writer.writeheader()

        for item in behaviors:
            start_relative = (
                item["start_ns"]
                - reference_ns
            ) / 1e9

            end_relative = (
                item["end_ns"]
                - reference_ns
            ) / 1e9

            writer.writerow({
                "behavior_id":
                    item["id"],
                "behavior":
                    item["behavior"],
                "start_monotonic_ns":
                    item["start_ns"],
                "end_monotonic_ns":
                    item["end_ns"],
                "start_relative_s":
                    f"{start_relative:.6f}",
                "end_relative_s":
                    f"{end_relative:.6f}",
                "duration_s":
                    f"{end_relative-start_relative:.6f}",
                "source":
                    item["source"],
                "evidence_strength":
                    item["evidence_strength"],
                "details":
                    item["details"],
            })

    # --------------------------------------------
    # TEMPORAL RELATIONS
    # Exclude zero-duration point events
    # from interval-to-interval relation graph.
    # --------------------------------------------
    interval_behaviors = [
        item
        for item in behaviors
        if item["end_ns"] > item["start_ns"]
    ]

    relations = []

    for i, a in enumerate(
        interval_behaviors
    ):
        for b in interval_behaviors[i + 1:]:
            relations.append({
                "source_id": a["id"],
                "source_behavior":
                    a["behavior"],
                "target_id": b["id"],
                "target_behavior":
                    b["behavior"],
                "relation":
                    temporal_relation(a, b),
            })

    relation_file = (
        output_dir
        / "observed_temporal_relations.csv"
    )

    relation_fields = [
        "source_id",
        "source_behavior",
        "target_id",
        "target_behavior",
        "relation",
    ]

    with relation_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as destination:

        writer = csv.DictWriter(
            destination,
            fieldnames=relation_fields,
        )

        writer.writeheader()
        writer.writerows(relations)

    # --------------------------------------------
    # SIMPLE JSON GRAPH
    # --------------------------------------------
    graph_file = (
        output_dir
        / "observed_behavior_graph.json"
    )

    graph = {
        "nodes": [
            {
                "id": item["id"],
                "behavior":
                    item["behavior"],
                "start_ns":
                    item["start_ns"],
                "end_ns":
                    item["end_ns"],
                "source":
                    item["source"],
                "evidence_strength":
                    item["evidence_strength"],
            }
            for item in behaviors
        ],
        "edges": relations,
    }

    graph_file.write_text(
        json.dumps(
            graph,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # --------------------------------------------
    # OUTPUT
    # --------------------------------------------
    print("=" * 78)
    print(
        "IBSTER V2E11 - BLIND TEMPORAL RELATION RECONSTRUCTION"
    )
    print("=" * 78)

    print(
        f"Run                 : "
        f"{run_dir.name}"
    )
    print(
        f"Observed behaviors  : "
        f"{len(behaviors)}"
    )
    print(
        f"Interval behaviors  : "
        f"{len(interval_behaviors)}"
    )
    print(
        f"Temporal relations  : "
        f"{len(relations)}"
    )

    print("\nOBSERVED BEHAVIORS")
    print("-" * 78)

    for item in behaviors:
        start = (
            item["start_ns"]
            - reference_ns
        ) / 1e9

        end = (
            item["end_ns"]
            - reference_ns
        ) / 1e9

        print(
            f"{item['id']} | "
            f"{start:7.3f}–{end:7.3f} s | "
            f"{item['behavior']:<48} | "
            f"{item['evidence_strength']}"
        )

    print("\nNON-BEFORE RELATIONS")
    print("-" * 78)

    interesting = [
        relation
        for relation in relations
        if relation["relation"]
        not in ("BEFORE", "AFTER")
    ]

    if not interesting:
        print("(tidak ada overlap/containment)")
    else:
        for relation in interesting:
            print(
                f"{relation['source_id']} "
                f"{relation['source_behavior']}"
                f"\n    {relation['relation']}\n"
                f"{relation['target_id']} "
                f"{relation['target_behavior']}"
                f"\n"
            )

    print("OUTPUT")
    print("-" * 78)
    print(interval_file)
    print(relation_file)
    print(graph_file)

    print()
    print(
        "Pattern, ground truth, dan ground-truth relations "
        "TIDAK digunakan pada V2E07."
    )


if __name__ == "__main__":
    main()
