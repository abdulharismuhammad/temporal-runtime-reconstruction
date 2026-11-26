import argparse
import csv
import hashlib
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import time


BLOCK = (
    b"IBSTER_V2_SYMMETRIC_BOUNDARY"
    * 512
)


# ============================================================
# BASIC WORKLOADS
# ============================================================

def cpu_work(duration):
    end_time = (
        time.monotonic()
        + duration
    )

    counter = 0

    while time.monotonic() < end_time:
        hashlib.sha256(
            BLOCK
            + str(counter).encode()
        ).digest()

        counter += 1


def file_create(path, duration):
    end_time = (
        time.monotonic()
        + duration
    )

    with path.open("wb") as handle:
        while (
            time.monotonic()
            < end_time
        ):
            handle.seek(0)

            handle.write(
                BLOCK
            )

            handle.flush()

            os.fsync(
                handle.fileno()
            )


def file_read(path, duration):
    end_time = (
        time.monotonic()
        + duration
    )

    with path.open("rb") as handle:
        while (
            time.monotonic()
            < end_time
        ):
            handle.seek(0)

            while handle.read(4096):
                pass


# ============================================================
# TEMPORAL RELATION
# ============================================================

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


# ============================================================
# EVENT-DRIVEN EXIT OBSERVER
# ============================================================

def watch_exit_kqueue(
    pid,
    result,
    ready_event,
):

    kqueue = select.kqueue()

    event = select.kevent(
        pid,
        filter=select.KQ_FILTER_PROC,
        flags=(
            select.KQ_EV_ADD
            | select.KQ_EV_ENABLE
            | select.KQ_EV_ONESHOT
        ),
        fflags=select.KQ_NOTE_EXIT,
    )

    registered_ns = (
        time.monotonic_ns()
    )

    kqueue.control(
        [event],
        0,
        0,
    )

    result[
        "registered_ns"
    ] = registered_ns

    ready_event.set()

    events = kqueue.control(
        None,
        1,
        None,
    )

    observed_ns = (
        time.monotonic_ns()
    )

    result[
        "observed_ns"
    ] = observed_ns

    result[
        "event_delivered"
    ] = int(
        bool(events)
    )

    if events:
        result[
            "event_fflags"
        ] = int(
            events[0].fflags
        )
    else:
        result[
            "event_fflags"
        ] = 0

    kqueue.close()


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    parser.add_argument(
        "--mode",
        required=True,
        choices=[
            "before_gap",
            "overlap_end",
        ],
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

    # --------------------------------------------------------
    # OUTPUT FILES
    # --------------------------------------------------------

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

    pre_exit_file = (
        output_dir
        / "child_pre_exit_ns.txt"
    )

    termination_file = (
        output_dir
        / "child_termination_reference.csv"
    )

    event_exit_file = (
        output_dir
        / "child_exit_event.csv"
    )

    child_script = (
        Path(__file__).resolve().parent
        / "controlled_child.py"
    )

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    intervals = {}

    lock = threading.Lock()

    child_end_event = (
        threading.Event()
    )

    read_start_event = (
        threading.Event()
    )

    kqueue_ready_event = (
        threading.Event()
    )

    child_returncode = {
        "value": None,
    }

    child_wait_return = {
        "ns": None,
    }

    kqueue_result = {
        "registered_ns": None,
        "observed_ns": None,
        "event_delivered": 0,
        "event_fflags": 0,
    }

    # --------------------------------------------------------
    # ACTIVITY HELPERS
    # --------------------------------------------------------

    def start(activity):

        timestamp = (
            time.monotonic_ns()
        )

        with lock:
            intervals[
                activity
            ] = {
                "start_ns":
                    timestamp,

                "end_ns":
                    None,
            }

        return timestamp

    def end(activity):

        timestamp = (
            time.monotonic_ns()
        )

        with lock:
            intervals[
                activity
            ][
                "end_ns"
            ] = timestamp

        return timestamp

    # ========================================================
    # COMMON PREFIX
    # ========================================================

    start(
        "file_create"
    )

    file_create(
        target_file,
        0.40,
    )

    end(
        "file_create"
    )

    start(
        "cpu_computation"
    )

    cpu_work(
        0.60
    )

    end(
        "cpu_computation"
    )

    # ========================================================
    # CONTROLLED CHILD
    # ========================================================

    child = subprocess.Popen(
        [
            sys.executable,
            str(child_script),

            "--timestamp-file",
            str(pre_exit_file),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    start(
        "child_B"
    )

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

    # ========================================================
    # EVENT-DRIVEN KQUEUE OBSERVER
    # ========================================================

    event_thread = threading.Thread(
        target=watch_exit_kqueue,
        args=(
            child.pid,
            kqueue_result,
            kqueue_ready_event,
        ),
        daemon=False,
    )

    event_thread.start()

    if not kqueue_ready_event.wait(
        timeout=2.0
    ):
        raise RuntimeError(
            "kqueue observer gagal "
            "melakukan registrasi."
        )

    # ========================================================
    # WAIT()-BASED UPPER TERMINATION REFERENCE
    # ========================================================

    def child_watcher():

        returncode = (
            child.wait()
        )

        wait_return_ns = (
            time.monotonic_ns()
        )

        child_wait_return[
            "ns"
        ] = wait_return_ns

        # Compatibility endpoint.
        #
        # IMPORTANT:
        # this is NOT claimed to be exact
        # kernel termination time.
        with lock:
            intervals[
                "child_B"
            ][
                "end_ns"
            ] = wait_return_ns

        child_returncode[
            "value"
        ] = returncode

        child_end_event.set()

    watcher = threading.Thread(
        target=child_watcher,
        daemon=False,
    )

    watcher.start()

    # Let the process exist long enough
    # to be sampled repeatedly.
    time.sleep(
        0.35
    )

    # ========================================================
    # CHILD RELEASE
    # ========================================================

    def release_child():

        if child.stdin is None:
            raise RuntimeError(
                "Child stdin unavailable."
            )

        child.stdin.write(
            "EXIT\n"
        )

        child.stdin.flush()
        child.stdin.close()

    # ========================================================
    # FILE READ
    # ========================================================

    def run_read():

        start(
            "file_read"
        )

        read_start_event.set()

        file_read(
            target_file,
            0.70,
        )

        end(
            "file_read"
        )

    margin_s = (
        args.margin_ms
        / 1000.0
    )

    phase_s = (
        args.phase_ms
        / 1000.0
    )

    # ========================================================
    # RANDOMISED WORKLOAD OFFSET
    # ========================================================

    if phase_s > 0:
        time.sleep(
            phase_s
        )

    # ========================================================
    # MODE 1:
    # TRUE BEFORE
    # ========================================================

    if (
        args.mode
        == "before_gap"
    ):

        release_child()

        child_end_event.wait()

        if (
            child_returncode[
                "value"
            ]
            != 0
        ):
            raise RuntimeError(
                "Controlled child gagal."
            )

        time.sleep(
            margin_s
        )

        run_read()

    # ========================================================
    # MODE 2:
    # TRUE OVERLAPS
    # ========================================================

    elif (
        args.mode
        == "overlap_end"
    ):

        read_thread = threading.Thread(
            target=run_read
        )

        read_thread.start()

        read_start_event.wait()

        time.sleep(
            margin_s
        )

        release_child()

        child_end_event.wait()

        if (
            child_returncode[
                "value"
            ]
            != 0
        ):
            raise RuntimeError(
                "Controlled child gagal."
            )

        read_thread.join()

    # ========================================================
    # JOIN OBSERVERS
    # ========================================================

    watcher.join()

    event_thread.join(
        timeout=2.0
    )

    if event_thread.is_alive():
        raise RuntimeError(
            "kqueue exit observer "
            "tidak selesai."
        )

    # ========================================================
    # READ CHILD PRE-EXIT REFERENCE
    # ========================================================

    if not pre_exit_file.exists():
        raise RuntimeError(
            "child_pre_exit_ns.txt "
            "tidak ditemukan."
        )

    child_pre_exit_ns = int(
        pre_exit_file
        .read_text(
            encoding="utf-8"
        )
        .strip()
    )

    child_wait_return_ns = (
        child_wait_return[
            "ns"
        ]
    )

    if child_wait_return_ns is None:
        raise RuntimeError(
            "child wait-return timestamp "
            "tidak tersedia."
        )

    kqueue_observed_ns = (
        kqueue_result[
            "observed_ns"
        ]
    )

    if kqueue_observed_ns is None:
        raise RuntimeError(
            "kqueue NOTE_EXIT timestamp "
            "tidak tersedia."
        )

    # ========================================================
    # WRITE TERMINATION BRACKET
    # ========================================================

    termination_bracket_ns = (
        child_wait_return_ns
        - child_pre_exit_ns
    )

    with termination_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as destination:

        writer = csv.writer(
            destination
        )

        writer.writerow([
            "pid",
            "child_pre_exit_ns",
            "child_wait_return_ns",
            "exit_bracket_width_ns",
            "exit_bracket_width_ms",
        ])

        writer.writerow([
            child.pid,
            child_pre_exit_ns,
            child_wait_return_ns,
            termination_bracket_ns,
            (
                termination_bracket_ns
                / 1e6
            ),
        ])

    # ========================================================
    # WRITE EVENT-DRIVEN EXIT OBSERVATION
    # ========================================================

    event_vs_pre_exit_ms = (
        kqueue_observed_ns
        - child_pre_exit_ns
    ) / 1e6

    event_vs_wait_return_ms = (
        kqueue_observed_ns
        - child_wait_return_ns
    ) / 1e6

    event_registration_to_exit_ms = (
        kqueue_observed_ns
        - kqueue_result[
            "registered_ns"
        ]
    ) / 1e6

    if (
        child_pre_exit_ns
        <= kqueue_observed_ns
        <= child_wait_return_ns
    ):
        event_position = (
            "INSIDE_BRACKET"
        )

    elif (
        kqueue_observed_ns
        < child_pre_exit_ns
    ):
        event_position = (
            "BEFORE_BRACKET"
        )

    else:
        event_position = (
            "AFTER_BRACKET"
        )

    with event_exit_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as destination:

        writer = csv.writer(
            destination
        )

        writer.writerow([
            "pid",
            "observer",
            "registered_monotonic_ns",
            "exit_observed_monotonic_ns",
            "event_delivered",
            "event_fflags",
            "event_vs_pre_exit_ms",
            "event_vs_wait_return_ms",
            "event_position",
            "registration_to_exit_ms",
        ])

        writer.writerow([
            child.pid,
            "kqueue_NOTE_EXIT",
            kqueue_result[
                "registered_ns"
            ],
            kqueue_observed_ns,
            kqueue_result[
                "event_delivered"
            ],
            kqueue_result[
                "event_fflags"
            ],
            f"{event_vs_pre_exit_ms:.6f}",
            f"{event_vs_wait_return_ms:.6f}",
            event_position,
            (
                f"{event_registration_to_exit_ms:.6f}"
            ),
        ])

    # ========================================================
    # CLEANUP ACTIVITY
    # ========================================================

    start(
        "cleanup"
    )

    if target_file.exists():
        target_file.unlink()

    time.sleep(
        0.15
    )

    end(
        "cleanup"
    )

    activities = [
        "file_create",
        "cpu_computation",
        "child_B",
        "file_read",
        "cleanup",
    ]

    for activity in activities:

        if activity not in intervals:
            raise RuntimeError(
                "Missing interval: "
                f"{activity}"
            )

        if (
            intervals[
                activity
            ][
                "end_ns"
            ]
            is None
        ):
            raise RuntimeError(
                "Unclosed interval: "
                f"{activity}"
            )

    # ========================================================
    # GROUND TRUTH INTERVALS
    #
    # child_B.end uses wait-return for
    # backward compatibility only.
    #
    # Exact kernel termination is NOT claimed.
    # ========================================================

    with gt_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as destination:

        writer = csv.writer(
            destination
        )

        writer.writerow([
            "activity",
            "start_monotonic_ns",
            "end_monotonic_ns",
            "duration_s",
        ])

        for activity in activities:

            item = (
                intervals[
                    activity
                ]
            )

            duration_s = (
                item["end_ns"]
                - item["start_ns"]
            ) / 1e9

            writer.writerow([
                activity,
                item["start_ns"],
                item["end_ns"],
                f"{duration_s:.6f}",
            ])

    # ========================================================
    # GROUND TRUTH RELATIONS
    # ========================================================

    with relation_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as destination:

        writer = csv.writer(
            destination
        )

        writer.writerow([
            "activity_a",
            "activity_b",
            "relation",
        ])

        for index, a in enumerate(
            activities
        ):

            for b in activities[
                index + 1:
            ]:

                writer.writerow([
                    a,
                    b,
                    temporal_relation(
                        intervals[a],
                        intervals[b],
                    ),
                ])

    # ========================================================
    # CONDITION METADATA
    # ========================================================

    with condition_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as destination:

        writer = csv.writer(
            destination
        )

        writer.writerow([
            "mode",
            "margin_ms",
            "phase_ms",
            "event_exit_observer",
        ])

        writer.writerow([
            args.mode,
            args.margin_ms,
            f"{args.phase_ms:.6f}",
            "kqueue_NOTE_EXIT",
        ])

    # ========================================================
    # TARGET RELATIONS
    # ========================================================

    target_relation_wait = (
        temporal_relation(
            intervals[
                "child_B"
            ],
            intervals[
                "file_read"
            ],
        )
    )

    event_child_interval = {
        "start_ns":
            intervals[
                "child_B"
            ][
                "start_ns"
            ],

        "end_ns":
            kqueue_observed_ns,
    }

    target_relation_event = (
        temporal_relation(
            event_child_interval,
            intervals[
                "file_read"
            ],
        )
    )

    # ========================================================
    # BOUNDARY VALUES
    # ========================================================

    wait_boundary_ms = (
        intervals[
            "file_read"
        ][
            "start_ns"
        ]
        - child_wait_return_ns
    ) / 1e6

    pre_exit_boundary_ms = (
        intervals[
            "file_read"
        ][
            "start_ns"
        ]
        - child_pre_exit_ns
    ) / 1e6

    event_boundary_ms = (
        intervals[
            "file_read"
        ][
            "start_ns"
        ]
        - kqueue_observed_ns
    ) / 1e6

    # ========================================================
    # SUMMARY
    # ========================================================

    print(
        "=" * 90
    )

    print(
        "IBSTER V2E34-R - "
        "EVENT-DRIVEN EXIT EXPERIMENT"
    )

    print(
        "=" * 90
    )

    print(
        f"Mode                 : "
        f"{args.mode}"
    )

    print(
        f"Nominal margin       : "
        f"{args.margin_ms} ms"
    )

    print(
        f"Workload offset      : "
        f"{args.phase_ms:.6f} ms"
    )

    print()

    print(
        f"Child PID            : "
        f"{child.pid}"
    )

    print(
        f"Pre-exit reference   : "
        f"{child_pre_exit_ns}"
    )

    print(
        f"kqueue NOTE_EXIT     : "
        f"{kqueue_observed_ns}"
    )

    print(
        f"wait() return        : "
        f"{child_wait_return_ns}"
    )

    print()

    print(
        f"Termination bracket  : "
        f"{termination_bracket_ns / 1e6:.3f} ms"
    )

    print(
        f"kqueue vs pre-exit   : "
        f"{event_vs_pre_exit_ms:+.3f} ms"
    )

    print(
        f"kqueue vs wait       : "
        f"{event_vs_wait_return_ms:+.3f} ms"
    )

    print(
        f"kqueue position      : "
        f"{event_position}"
    )

    print()

    print(
        f"Boundary pre-exit    : "
        f"{pre_exit_boundary_ms:+.3f} ms"
    )

    print(
        f"Boundary event       : "
        f"{event_boundary_ms:+.3f} ms"
    )

    print(
        f"Boundary wait-return : "
        f"{wait_boundary_ms:+.3f} ms"
    )

    print()

    print(
        f"Relation wait-ref    : "
        f"{target_relation_wait}"
    )

    print(
        f"Relation event-ref   : "
        f"{target_relation_event}"
    )

    print()

    print(
        f"Termination ref file : "
        f"{termination_file}"
    )

    print(
        f"Event exit file      : "
        f"{event_exit_file}"
    )

    print(
        f"Ground truth file    : "
        f"{gt_file}"
    )

    print(
        "=" * 90
    )


if __name__ == "__main__":
    main()