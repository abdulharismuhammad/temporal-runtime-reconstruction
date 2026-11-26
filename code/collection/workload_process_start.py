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
    b"IBSTER_PROCESS_START_BOUNDARY"
    * 512
)


def cpu_work(duration):

    deadline = (
        time.monotonic()
        + duration
    )

    counter = 0

    while time.monotonic() < deadline:

        hashlib.sha256(
            BLOCK
            + str(counter).encode()
        ).digest()

        counter += 1


def file_create(path, duration):

    deadline = (
        time.monotonic()
        + duration
    )

    with path.open("wb") as handle:

        while time.monotonic() < deadline:

            handle.seek(0)
            handle.write(BLOCK)
            handle.flush()

            os.fsync(
                handle.fileno()
            )


def file_read(path, duration):

    deadline = (
        time.monotonic()
        + duration
    )

    with path.open("rb") as handle:

        while time.monotonic() < deadline:

            handle.seek(0)

            while handle.read(4096):
                pass


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

    start_reference_file = (
        output_dir
        / "child_start_reference.csv"
    )

    child_user_start_file = (
        output_dir
        / "child_user_start_ns.txt"
    )

    child_script = (
        Path(__file__).resolve().parent
        / "controlled_child_start.py"
    )

    intervals = {}

    child_returncode = {
        "value": None,
    }

    child_wait_return = {
        "ns": None,
    }

    child_end_event = (
        threading.Event()
    )

    file_read_started = (
        threading.Event()
    )

    # ==================================================
    # COMMON PREFIX
    # ==================================================

    start_ns = (
        time.monotonic_ns()
    )

    file_create(
        target_file,
        0.40,
    )

    intervals["file_create"] = {
        "start_ns": start_ns,
        "end_ns": time.monotonic_ns(),
    }

    start_ns = (
        time.monotonic_ns()
    )

    cpu_work(
        0.60
    )

    intervals["cpu_computation"] = {
        "start_ns": start_ns,
        "end_ns": time.monotonic_ns(),
    }

    # ==================================================
    # RANDOMISE PROCESS CREATION RELATIVE TO POLLING
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
    # PROCESS-START BRACKET
    #
    # Actual OS process creation occurs between:
    #
    # parent_pre_spawn_ns
    #       <= true start <=
    # parent_post_spawn_ns
    #
    # We do NOT claim an exact kernel start timestamp.
    # ==================================================

    parent_pre_spawn_ns = (
        time.monotonic_ns()
    )

    child = subprocess.Popen(
        [
            sys.executable,
            str(child_script),

            "--start-timestamp-file",
            str(
                child_user_start_file
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    parent_post_spawn_ns = (
        time.monotonic_ns()
    )

    start_bracket_ns = (
        parent_post_spawn_ns
        - parent_pre_spawn_ns
    )

    # Conservative operational start reference:
    #
    # use the UPPER bound of the process-start bracket.
    #
    # Therefore if file_read starts after this timestamp,
    # the real process definitely started before file_read.

    intervals["child_B"] = {
        "start_ns":
            parent_post_spawn_ns,

        "end_ns":
            None,
    }

    with start_reference_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(
            handle
        )

        writer.writerow([
            "pid",
            "parent_pre_spawn_ns",
            "parent_post_spawn_ns",
            "start_bracket_width_ns",
            "start_bracket_width_ms",
        ])

        writer.writerow([
            child.pid,
            parent_pre_spawn_ns,
            parent_post_spawn_ns,
            start_bracket_ns,
            f"{start_bracket_ns / 1e6:.6f}",
        ])

    # ==================================================
    # CHILD END WATCHER
    # ==================================================

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

    # ==================================================
    # CRITICAL START BOUNDARY
    #
    # File read begins only margin_ms AFTER Popen
    # returned.
    #
    # Therefore actual child start is guaranteed to be
    # earlier than file_read start.
    # ==================================================

    margin_s = (
        args.margin_ms
        / 1000.0
    )

    time.sleep(
        margin_s
    )

    def run_read():

        intervals[
            "file_read"
        ] = {
            "start_ns":
                time.monotonic_ns(),

            "end_ns":
                None,
        }

        file_read_started.set()

        file_read(
            target_file,
            0.70,
        )

        intervals[
            "file_read"
        ][
            "end_ns"
        ] = (
            time.monotonic_ns()
        )

    read_thread = threading.Thread(
        target=run_read,
        daemon=False,
    )

    read_thread.start()

    file_read_started.wait()

    # Keep child alive well into file_read.
    time.sleep(
        0.30
    )

    # No need to wait for READY before defining
    # the start boundary. The process already exists.
    #
    # Verify READY before terminating it.

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

    if (
        child.stdin
        is None
    ):

        raise RuntimeError(
            "Child stdin unavailable."
        )

    child.stdin.write(
        "EXIT\n"
    )

    child.stdin.flush()
    child.stdin.close()

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

    watcher.join()
    read_thread.join()

    # ==================================================
    # OPTIONAL CHILD USER-SPACE REFERENCE
    #
    # Diagnostic only.
    # NOT used as exact process start.
    # ==================================================

    child_user_start_ns = None

    if (
        child_user_start_file.exists()
    ):

        try:

            child_user_start_ns = int(
                child_user_start_file
                .read_text(
                    encoding="utf-8"
                )
                .strip()
            )

        except ValueError:
            pass

    # ==================================================
    # CLEANUP
    # ==================================================

    cleanup_start_ns = (
        time.monotonic_ns()
    )

    if target_file.exists():

        target_file.unlink()

    time.sleep(
        0.15
    )

    intervals["cleanup"] = {
        "start_ns":
            cleanup_start_ns,

        "end_ns":
            time.monotonic_ns(),
    }

    activities = [
        "file_create",
        "cpu_computation",
        "child_B",
        "file_read",
        "cleanup",
    ]

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
        ])

        writer.writerow([
            "process_start",
            args.margin_ms,
            f"{args.phase_ms:.6f}",
            "child_start",
        ])

    gt_relation = (
        temporal_relation(
            intervals["child_B"],
            intervals["file_read"],
        )
    )

    measured_gap_ms = (
        intervals[
            "file_read"
        ][
            "start_ns"
        ]
        - parent_post_spawn_ns
    ) / 1e6

    print("=" * 90)

    print(
        "IBSTER V2E34-R - "
        "PROCESS-START BRACKET EXPERIMENT"
    )

    print("=" * 90)

    print(
        f"Child PID          : "
        f"{child.pid}"
    )

    print(
        f"Nominal margin     : "
        f"{args.margin_ms} ms"
    )

    print(
        f"Workload offset    : "
        f"{args.phase_ms:.6f} ms"
    )

    print(
        f"Start bracket      : "
        f"{start_bracket_ns / 1e6:.3f} ms"
    )

    print(
        f"Measured safe gap  : "
        f"{measured_gap_ms:+.3f} ms"
    )

    print(
        f"GT relation        : "
        f"{gt_relation}"
    )

    if (
        child_user_start_ns
        is not None
    ):

        user_delay_ms = (
            child_user_start_ns
            - parent_post_spawn_ns
        ) / 1e6

        print(
            f"Python startup     : "
            f"{user_delay_ms:+.3f} ms "
            f"(diagnostic only)"
        )

    print()
    print(
        "Start semantics    : "
        "true process start is bracketed by "
        "parent pre/post Popen timestamps"
    )

    print(
        "Operational GT     : "
        "post-Popen upper bound "
        "(conservative)"
    )

    print("=" * 90)


if __name__ == "__main__":
    main()