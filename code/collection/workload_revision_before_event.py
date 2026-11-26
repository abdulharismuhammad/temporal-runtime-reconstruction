import argparse
import csv
import hashlib
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


# ============================================================
# IBSTER V2E34-R
# Revised workload for reviewer sampling experiments.
#
# Important:
# - --phase-ms is a workload offset, NOT the measured sampler
#   phase.
# - child_B termination is represented using two references:
#
#     child_pre_exit_ns
#         <= true process termination
#         <= child_wait_return_ns
#
# - child_wait_return_ns is therefore NOT claimed to be an
#   exact kernel termination timestamp.
# ============================================================


def parse_args():
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

    return parser.parse_args()


def write_ground_truth(
    output_dir,
    activities,
):
    path = (
        output_dir
        / "ground_truth.csv"
    )

    with path.open(
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

        for activity_name in [
            "file_create",
            "cpu_computation",
            "child_B",
            "file_read",
            "cleanup",
        ]:

            activity = activities[
                activity_name
            ]

            start_ns = activity[
                "start_monotonic_ns"
            ]

            end_ns = activity[
                "end_monotonic_ns"
            ]

            duration_s = (
                end_ns
                - start_ns
            ) / 1e9

            writer.writerow([
                activity_name,
                start_ns,
                end_ns,
                f"{duration_s:.6f}",
            ])

    return path


def write_relation_file(
    output_dir,
    relation,
):
    path = (
        output_dir
        / "ground_truth_relations.csv"
    )

    with path.open(
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
            "child_B",
            "file_read",
            relation,
        ])

    return path


def write_condition_file(
    output_dir,
    mode,
    margin_ms,
    phase_ms,
):
    path = (
        output_dir
        / "condition.csv"
    )

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(
            handle
        )

        writer.writerow([
            "mode",
            "nominal_margin_ms",
            "workload_offset_ms",
        ])

        writer.writerow([
            mode,
            margin_ms,
            f"{phase_ms:.6f}",
        ])

    return path


def write_termination_reference(
    output_dir,
    child_pre_exit_ns,
    child_wait_return_ns,
):
    path = (
        output_dir
        / "child_termination_reference.csv"
    )

    bracket_width_ms = (
        child_wait_return_ns
        - child_pre_exit_ns
    ) / 1e6

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(
            handle
        )

        writer.writerow([
            "child_pre_exit_ns",
            "child_wait_return_ns",
            "exit_bracket_width_ms",
        ])

        writer.writerow([
            child_pre_exit_ns,
            child_wait_return_ns,
            f"{bracket_width_ms:.6f}",
        ])

    return (
        path,
        bracket_width_ms,
    )


def busy_cpu(
    duration_s,
):
    deadline = (
        time.monotonic()
        + duration_s
    )

    payload = (
        b"IBSTER-runtime-reconstruction"
        * 64
    )

    digest = payload

    while (
        time.monotonic()
        < deadline
    ):
        digest = hashlib.sha256(
            digest
        ).digest()

    return digest


def relation_from_boundary(
    child_end_ns,
    read_start_ns,
):
    if (
        child_end_ns
        < read_start_ns
    ):
        return "BEFORE"

    return "OVERLAPS"


def main():
    args = parse_args()

    output_dir = Path(
        args.output
    ).resolve()

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    controlled_child = (
        Path(__file__)
        .resolve()
        .parent
        / "controlled_child.py"
    )

    if not controlled_child.exists():
        raise FileNotFoundError(
            f"controlled_child.py tidak ditemukan: "
            f"{controlled_child}"
        )

    target_file = (
        output_dir
        / "behavior_target.bin"
    )

    child_pre_exit_file = (
        output_dir
        / "child_pre_exit_ns.txt"
    )

    activities = {}

    child_end_event = (
        threading.Event()
    )

    child_wait_return_holder = {
        "timestamp_ns": None,
        "returncode": None,
    }

    # ========================================================
    # ACTIVITY 1 - FILE CREATE
    # ========================================================

    file_create_start = (
        time.monotonic_ns()
    )

    file_deadline = (
        time.monotonic()
        + 0.4
    )

    block = os.urandom(
        4096
    )

    with target_file.open(
        "wb"
    ) as handle:

        while (
            time.monotonic()
            < file_deadline
        ):
            handle.write(
                block
            )

            handle.flush()

    file_create_end = (
        time.monotonic_ns()
    )

    activities[
        "file_create"
    ] = {
        "start_monotonic_ns":
            file_create_start,

        "end_monotonic_ns":
            file_create_end,
    }

    # ========================================================
    # ACTIVITY 2 - CPU COMPUTATION
    # ========================================================

    cpu_start = (
        time.monotonic_ns()
    )

    busy_cpu(
        0.6
    )

    cpu_end = (
        time.monotonic_ns()
    )

    activities[
        "cpu_computation"
    ] = {
        "start_monotonic_ns":
            cpu_start,

        "end_monotonic_ns":
            cpu_end,
    }

    # ========================================================
    # ACTIVITY 3 - CHILD PROCESS
    # ========================================================

    child_start_ns = (
        time.monotonic_ns()
    )

    child = subprocess.Popen(
        [
            sys.executable,
            str(
                controlled_child
            ),

            "--timestamp-file",
            str(
                child_pre_exit_file
            ),
        ],

        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,

        text=True,
        bufsize=1,
    )

    if (
        child.stdout
        is None
        or child.stdin
        is None
    ):
        raise RuntimeError(
            "Pipe child tidak tersedia."
        )

    ready_line = (
        child.stdout
        .readline()
        .strip()
    )

    if ready_line != "READY":

        stderr_text = ""

        if (
            child.stderr
            is not None
        ):
            stderr_text = (
                child.stderr.read()
            )

        raise RuntimeError(
            "Child gagal mengirim READY. "
            f"stdout={ready_line!r}, "
            f"stderr={stderr_text!r}"
        )

    # Child is now active and waiting
    # for the EXIT command.
    #
    # Keep the same approximate workload
    # structure as the original experiment.
    time.sleep(
        0.35
    )

    # --------------------------------------------------------
    # Watcher thread.
    #
    # IMPORTANT:
    # This timestamp represents the moment the parent observes
    # child.wait() returning. It is NOT claimed to be the exact
    # kernel process termination time.
    # --------------------------------------------------------

    def watch_child():
        returncode = (
            child.wait()
        )

        wait_return_ns = (
            time.monotonic_ns()
        )

        child_wait_return_holder[
            "timestamp_ns"
        ] = wait_return_ns

        child_wait_return_holder[
            "returncode"
        ] = returncode

        child_end_event.set()

    watcher = threading.Thread(
        target=watch_child,
        daemon=True,
    )

    watcher.start()

    # ========================================================
    # WORKLOAD OFFSET
    #
    # This controls workload timing only.
    # The actual sampler phase is measured later from
    # poll_trace.csv.
    # ========================================================

    phase_s = (
        args.phase_ms
        / 1000.0
    )

    if phase_s > 0:
        time.sleep(
            phase_s
        )

    margin_s = (
        args.margin_ms
        / 1000.0
    )

    # ========================================================
    # MODE A - TRUE BEFORE
    #
    # child ends first, then after nominal margin file_read
    # begins.
    # ========================================================

    if (
        args.mode
        == "before_gap"
    ):

        child.stdin.write(
            "EXIT\n"
        )

        child.stdin.flush()

        child_end_event.wait(
            timeout=10
        )

        if not child_end_event.is_set():
            raise TimeoutError(
                "Timeout menunggu child termination."
            )

        time.sleep(
            margin_s
        )

        read_start_ns = (
            time.monotonic_ns()
        )

        read_deadline = (
            time.monotonic()
            + 0.7
        )

        with target_file.open(
            "rb"
        ) as handle:

            while (
                time.monotonic()
                < read_deadline
            ):
                handle.seek(
                    0
                )

                while (
                    handle.read(
                        4096
                    )
                ):
                    pass

        read_end_ns = (
            time.monotonic_ns()
        )

    # ========================================================
    # MODE B - TRUE OVERLAP
    #
    # file_read starts while child is still active.
    # After nominal margin the child is released.
    # ========================================================

    elif (
        args.mode
        == "overlap_end"
    ):

        read_start_ns = (
            time.monotonic_ns()
        )

        stop_read_event = (
            threading.Event()
        )

        read_end_holder = {
            "timestamp_ns": None
        }

        def read_worker():

            deadline = (
                time.monotonic()
                + 0.7
            )

            with target_file.open(
                "rb"
            ) as handle:

                while (
                    time.monotonic()
                    < deadline
                ):

                    handle.seek(
                        0
                    )

                    while (
                        handle.read(
                            4096
                        )
                    ):
                        pass

            read_end_holder[
                "timestamp_ns"
            ] = (
                time.monotonic_ns()
            )

            stop_read_event.set()

        reader = threading.Thread(
            target=read_worker,
            daemon=True,
        )

        reader.start()

        time.sleep(
            margin_s
        )

        child.stdin.write(
            "EXIT\n"
        )

        child.stdin.flush()

        child_end_event.wait(
            timeout=10
        )

        if not child_end_event.is_set():
            raise TimeoutError(
                "Timeout menunggu child termination."
            )

        stop_read_event.wait(
            timeout=10
        )

        if not stop_read_event.is_set():
            raise TimeoutError(
                "Timeout menunggu file_read."
            )

        reader.join(
            timeout=2
        )

        read_end_ns = (
            read_end_holder[
                "timestamp_ns"
            ]
        )

    else:
        raise RuntimeError(
            f"Mode tidak dikenal: "
            f"{args.mode}"
        )

    # ========================================================
    # CHILD TERMINATION REFERENCES
    # ========================================================

    watcher.join(
        timeout=2
    )

    child_wait_return_ns = (
        child_wait_return_holder[
            "timestamp_ns"
        ]
    )

    if child_wait_return_ns is None:
        raise RuntimeError(
            "child_wait_return_ns tidak tersedia."
        )

    if not child_pre_exit_file.exists():
        raise RuntimeError(
            "child_pre_exit_ns.txt tidak ditemukan."
        )

    child_pre_exit_text = (
        child_pre_exit_file
        .read_text(
            encoding="utf-8",
        )
        .strip()
    )

    if not child_pre_exit_text:
        raise RuntimeError(
            "child_pre_exit_ns.txt kosong."
        )

    child_pre_exit_ns = int(
        child_pre_exit_text
    )

    # For backward compatibility with the original evaluation,
    # child_B.end in ground_truth.csv remains the parent-side
    # wait-return reference.
    #
    # The new child_termination_reference.csv explicitly stores
    # the termination bracket and prevents this value from being
    # misinterpreted as exact kernel termination.
    activities[
        "child_B"
    ] = {
        "start_monotonic_ns":
            child_start_ns,

        "end_monotonic_ns":
            child_wait_return_ns,
    }

    activities[
        "file_read"
    ] = {
        "start_monotonic_ns":
            read_start_ns,

        "end_monotonic_ns":
            read_end_ns,
    }

    # ========================================================
    # CLEANUP
    # ========================================================

    cleanup_start_ns = (
        time.monotonic_ns()
    )

    cleanup_deadline = (
        time.monotonic()
        + 0.15
    )

    while (
        time.monotonic()
        < cleanup_deadline
    ):
        try:
            if target_file.exists():
                target_file.stat()
        except OSError:
            pass

        time.sleep(
            0.005
        )

    cleanup_end_ns = (
        time.monotonic_ns()
    )

    activities[
        "cleanup"
    ] = {
        "start_monotonic_ns":
            cleanup_start_ns,

        "end_monotonic_ns":
            cleanup_end_ns,
    }

    # ========================================================
    # GROUND-TRUTH RELATION
    # ========================================================

    relation = relation_from_boundary(
        child_wait_return_ns,
        read_start_ns,
    )

    signed_boundary_ms = (
        read_start_ns
        - child_wait_return_ns
    ) / 1e6

    # Additional boundary measured from the child-side
    # pre-exit reference.
    pre_exit_boundary_ms = (
        read_start_ns
        - child_pre_exit_ns
    ) / 1e6

    # ========================================================
    # OUTPUT FILES
    # ========================================================

    ground_truth_path = (
        write_ground_truth(
            output_dir,
            activities,
        )
    )

    relation_path = (
        write_relation_file(
            output_dir,
            relation,
        )
    )

    condition_path = (
        write_condition_file(
            output_dir,
            args.mode,
            args.margin_ms,
            args.phase_ms,
        )
    )

    (
        termination_path,
        bracket_width_ms,
    ) = write_termination_reference(
        output_dir,
        child_pre_exit_ns,
        child_wait_return_ns,
    )

    # ========================================================
    # TERMINAL SUMMARY
    # ========================================================

    print(
        "=" * 84
    )

    print(
        "IBSTER V2E34-R - "
        "REVIEWER SAMPLING EXPERIMENT"
    )

    print(
        "=" * 84
    )

    print(
        f"Mode              : "
        f"{args.mode}"
    )

    print(
        f"Nominal margin    : "
        f"{args.margin_ms} ms"
    )

    print(
        f"Workload offset   : "
        f"{args.phase_ms:.6f} ms"
    )

    print(
        f"GT relation       : "
        f"{relation}"
    )

    print(
        f"Signed boundary   : "
        f"{signed_boundary_ms:+.3f} ms "
        f"(wait-return ref)"
    )

    print(
        f"Pre-exit boundary : "
        f"{pre_exit_boundary_ms:+.3f} ms"
    )

    print()

    print(
        "Termination bracket:"
    )

    print(
        f"  child_pre_exit_ns   : "
        f"{child_pre_exit_ns}"
    )

    print(
        f"  child_wait_return_ns: "
        f"{child_wait_return_ns}"
    )

    print(
        f"  bracket width       : "
        f"{bracket_width_ms:.3f} ms"
    )

    print()

    print(
        "Termination reference:"
    )

    print(
        "  child_pre_exit_ns "
        "<= true termination "
        "<= child_wait_return_ns"
    )

    print(
        "  child.wait() completion "
        "is NOT treated as an exact "
        "kernel termination timestamp."
    )

    print()

    print(
        f"Ground truth      : "
        f"{ground_truth_path}"
    )

    print(
        f"Relations         : "
        f"{relation_path}"
    )

    print(
        f"Condition         : "
        f"{condition_path}"
    )

    print(
        f"Termination ref   : "
        f"{termination_path}"
    )


if __name__ == "__main__":
    main()
