import argparse
import csv
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


BLOCK = (
    b"IBSTER_CPU_BOUNDARY"
    * 1024
)


CPU_THRESHOLD_PERCENT = 30.0


def cpu_busy_worker(
    duration_s,
    state,
    started_event,
):

    state["start_ns"] = (
        time.monotonic_ns()
    )

    started_event.set()

    deadline = (
        time.monotonic()
        + duration_s
    )

    counter = 0

    while (
        time.monotonic()
        < deadline
    ):

        hashlib.sha256(
            BLOCK
            + str(counter).encode()
        ).digest()

        counter += 1

    state["end_ns"] = (
        time.monotonic_ns()
    )


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
        "--output",
        required=True,
    )

    parser.add_argument(
        "--mode",
        required=True,
    )

    parser.add_argument(
        "--margin-ms",
        required=True,
        type=int,
        choices=[
            20,
            50,
            80,
            120,
            200,
        ],
    )

    parser.add_argument(
        "--phase-ms",
        required=True,
        type=float,
    )

    args = parser.parse_args()

    output_dir = Path(
        args.output
    ).resolve()

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    target_file = (
        output_dir
        / "behavior_target.bin"
    )

    gt_file = (
        output_dir
        / "ground_truth.csv"
    )

    relation_file = (
        output_dir
        / "ground_truth_relations.csv"
    )

    condition_file = (
        output_dir
        / "condition.csv"
    )

    cpu_reference_file = (
        output_dir
        / "cpu_burst_reference.csv"
    )

    child_reference_file = (
        output_dir
        / "cpu_reference_child.csv"
    )

    analysis_window_file = (
        output_dir
        / "cpu_analysis_window.csv"
    )

    child_start_file = (
        output_dir
        / "cpu_child_user_start.txt"
    )

    child_script = (
        Path(__file__).resolve().parent
        / "controlled_child_start.py"
    )

    # ==================================================
    # TARGET FILE FOR FS_USAGE VISIBILITY
    # ==================================================

    with target_file.open(
        "wb"
    ) as handle:

        handle.write(
            BLOCK * 4
        )

        handle.flush()

        os.fsync(
            handle.fileno()
        )

    # ==================================================
    # CPU ANALYSIS WINDOW
    #
    # Startup telemetry before this timestamp is
    # excluded from CPU interval reconstruction.
    # ==================================================

    analysis_start_ns = (
        time.monotonic_ns()
    )

    # Provide clean idle baseline.
    # 0.80 s gives multiple samples even at T=250 ms.
    time.sleep(
        0.80
    )

    # ==================================================
    # RANDOMISED OFFSET
    # ==================================================

    phase_s = (
        args.phase_ms
        / 1000.0
    )

    if phase_s > 0:

        time.sleep(
            phase_s
        )

    # ==================================================
    # CONTROLLED CPU BURST
    # ==================================================

    cpu_state = {
        "start_ns": None,
        "end_ns": None,
    }

    cpu_started = (
        threading.Event()
    )

    cpu_thread = threading.Thread(
        target=cpu_busy_worker,
        args=(
            0.35,
            cpu_state,
            cpu_started,
        ),
        daemon=False,
    )

    cpu_thread.start()

    cpu_started.wait()

    # ==================================================
    # CHILD BEGINS AFTER CPU START
    # ==================================================

    time.sleep(
        args.margin_ms
        / 1000.0
    )

    child_pre_spawn_ns = (
        time.monotonic_ns()
    )

    child = subprocess.Popen(
        [
            sys.executable,
            str(child_script),

            "--start-timestamp-file",
            str(
                child_start_file
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    child_post_spawn_ns = (
        time.monotonic_ns()
    )

    # Conservative upper bound for child start.
    child_start_ns = (
        child_post_spawn_ns
    )

    # ==================================================
    # CHILD END WATCHER
    # ==================================================

    child_state = {
        "end_ns": None,
        "returncode": None,
    }

    child_end_event = (
        threading.Event()
    )

    def child_watcher():

        returncode = (
            child.wait()
        )

        child_state[
            "end_ns"
        ] = (
            time.monotonic_ns()
        )

        child_state[
            "returncode"
        ] = returncode

        child_end_event.set()

    watcher = threading.Thread(
        target=child_watcher,
        daemon=False,
    )

    watcher.start()

    # ==================================================
    # CPU END
    # ==================================================

    cpu_thread.join()

    if (
        cpu_state["start_ns"]
        is None
        or
        cpu_state["end_ns"]
        is None
    ):

        raise RuntimeError(
            "CPU burst timestamp missing."
        )

    # Keep child alive after CPU burst finishes.
    time.sleep(
        0.35
    )

    # ==================================================
    # TERMINATE CHILD
    # ==================================================

    ready = (
        child.stdout
        .readline()
        .strip()
    )

    if ready != "READY":

        stderr = (
            child.stderr.read()
        )

        raise RuntimeError(
            "Controlled child tidak READY: "
            f"{ready!r}; stderr={stderr!r}"
        )

    if child.stdin is None:

        raise RuntimeError(
            "Child stdin unavailable."
        )

    child.stdin.write(
        "EXIT\n"
    )

    child.stdin.flush()
    child.stdin.close()

    child_end_event.wait()

    watcher.join()

    if (
        child_state[
            "returncode"
        ]
        != 0
    ):

        raise RuntimeError(
            "Controlled child gagal."
        )

    child_end_ns = (
        child_state[
            "end_ns"
        ]
    )

    # ==================================================
    # ANALYSIS WINDOW END
    # ==================================================

    analysis_end_ns = (
        time.monotonic_ns()
    )

    with analysis_window_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(
            handle
        )

        writer.writerow([
            "analysis_start_ns",
            "analysis_end_ns",
            "cpu_threshold_percent",
            "threshold_source",
            "sample_semantics",
        ])

        writer.writerow([
            analysis_start_ns,
            analysis_end_ns,
            f"{CPU_THRESHOLD_PERCENT:.1f}",
            "frozen_from_independent_cpu_pilot",
            "cpu_percent_since_previous_poll",
        ])

    # ==================================================
    # INTERVALS
    # ==================================================

    cpu_interval = {
        "start_ns":
            cpu_state[
                "start_ns"
            ],

        "end_ns":
            cpu_state[
                "end_ns"
            ],
    }

    child_interval = {
        "start_ns":
            child_start_ns,

        "end_ns":
            child_end_ns,
    }

    gt_relation = (
        temporal_relation(
            cpu_interval,
            child_interval,
        )
    )

    # ==================================================
    # CPU REFERENCE
    # ==================================================

    with cpu_reference_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(
            handle
        )

        writer.writerow([
            "cpu_start_ns",
            "cpu_end_ns",
            "cpu_duration_ms",
        ])

        writer.writerow([
            cpu_interval[
                "start_ns"
            ],

            cpu_interval[
                "end_ns"
            ],

            (
                cpu_interval[
                    "end_ns"
                ]
                - cpu_interval[
                    "start_ns"
                ]
            ) / 1e6,
        ])

    # ==================================================
    # CHILD REFERENCE
    # ==================================================

    with child_reference_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(
            handle
        )

        writer.writerow([
            "pid",
            "child_pre_spawn_ns",
            "child_post_spawn_ns",
            "child_start_bracket_ms",
            "child_wait_return_ns",
        ])

        writer.writerow([
            child.pid,
            child_pre_spawn_ns,
            child_post_spawn_ns,
            (
                child_post_spawn_ns
                - child_pre_spawn_ns
            ) / 1e6,
            child_end_ns,
        ])

    # ==================================================
    # GROUND TRUTH
    # ==================================================

    with gt_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(
            handle
        )

        writer.writerow([
            "activity",
            "start_monotonic_ns",
            "end_monotonic_ns",
            "duration_s",
        ])

        for (
            name,
            item,
        ) in [
            (
                "cpu_burst",
                cpu_interval,
            ),
            (
                "child_B",
                child_interval,
            ),
        ]:

            writer.writerow([
                name,
                item[
                    "start_ns"
                ],
                item[
                    "end_ns"
                ],
                (
                    item[
                        "end_ns"
                    ]
                    - item[
                        "start_ns"
                    ]
                ) / 1e9,
            ])

    # ==================================================
    # RELATIONS
    # ==================================================

    with relation_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(
            handle
        )

        writer.writerow([
            "activity_a",
            "activity_b",
            "relation",
        ])

        writer.writerow([
            "cpu_burst",
            "child_B",
            gt_relation,
        ])

    # ==================================================
    # CONDITION
    # ==================================================

    with condition_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(
            handle
        )

        writer.writerow([
            "mode",
            "margin_ms",
            "phase_ms",
            "boundary_type",
            "cpu_threshold_percent",
        ])

        writer.writerow([
            "cpu_boundary",
            args.margin_ms,
            f"{args.phase_ms:.6f}",
            "cpu_start_end",
            f"{CPU_THRESHOLD_PERCENT:.1f}",
        ])

    # ==================================================
    # CLEANUP
    # ==================================================

    time.sleep(
        0.20
    )

    if target_file.exists():

        target_file.unlink()

    cpu_to_child_gap_ms = (
        child_start_ns
        - cpu_interval[
            "start_ns"
        ]
    ) / 1e6

    cpu_end_to_child_end_ms = (
        child_end_ns
        - cpu_interval[
            "end_ns"
        ]
    ) / 1e6

    analysis_duration_ms = (
        analysis_end_ns
        - analysis_start_ns
    ) / 1e6

    print("=" * 90)

    print(
        "IBSTER V2E34-R - "
        "CPU-BOUNDARY EXPERIMENT"
    )

    print("=" * 90)

    print(
        f"Nominal margin       : "
        f"{args.margin_ms} ms"
    )

    print(
        f"Workload offset      : "
        f"{args.phase_ms:.6f} ms"
    )

    print(
        f"CPU threshold        : "
        f"{CPU_THRESHOLD_PERCENT:.1f}%"
    )

    print(
        f"CPU duration         : "
        f"{(
            cpu_interval['end_ns']
            - cpu_interval['start_ns']
        ) / 1e6:.3f} ms"
    )

    print(
        f"CPU→child start gap  : "
        f"{cpu_to_child_gap_ms:+.3f} ms"
    )

    print(
        f"CPU end→child end    : "
        f"{cpu_end_to_child_end_ms:+.3f} ms"
    )

    print(
        f"Analysis window      : "
        f"{analysis_duration_ms:.3f} ms"
    )

    print(
        f"GT relation          : "
        f"{gt_relation}"
    )

    print(
        f"CPU reference        : "
        f"{cpu_reference_file}"
    )

    print(
        f"Analysis window file : "
        f"{analysis_window_file}"
    )

    print("=" * 90)


if __name__ == "__main__":
    main()