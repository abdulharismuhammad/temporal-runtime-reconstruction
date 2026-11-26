import argparse
import csv
import gzip
import json
import random
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil


ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

OUTPUT_ROOT = (
    ROOT
    / "experiments"
    / "V2E34_sampling_phase_sweep"
    / "collection_process_start"
    / "output"
)


def telemetry_worker(
    pid,
    run_dir,
    stop_event,
    sample_ms,
):

    cpu_path = (
        run_dir
        / "cpu_telemetry.csv"
    )

    child_path = (
        run_dir
        / "child_process_events.csv"
    )

    poll_path = (
        run_dir
        / "poll_trace.csv"
    )

    try:
        process = psutil.Process(
            pid
        )

        process.cpu_percent(
            interval=None
        )

    except psutil.Error:
        return

    known_children = {}

    poll_index = 0

    sample_s = (
        sample_ms
        / 1000.0
    )

    next_deadline = (
        time.monotonic()
    )

    with (
        cpu_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as cpu_handle,

        child_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as child_handle,

        poll_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as poll_handle,
    ):

        cpu_writer = csv.writer(
            cpu_handle
        )

        child_writer = csv.writer(
            child_handle
        )

        poll_writer = csv.writer(
            poll_handle
        )

        cpu_writer.writerow([
            "poll_index",
            "timestamp_monotonic_ns",
            "cpu_percent",
            "rss_bytes",
            "num_threads",
            "child_count",
        ])

        child_writer.writerow([
            "poll_index",
            "timestamp_monotonic_ns",
            "event",
            "parent_pid",
            "child_pid",
            "child_name",
            "child_status",
        ])

        poll_writer.writerow([
            "poll_index",
            "timestamp_monotonic_ns",
            "sample_interval_ms",
            "visible_child_count",
            "visible_child_pids",
        ])

        while not (
            stop_event.is_set()
        ):

            poll_index += 1

            now_ns = (
                time.monotonic_ns()
            )

            try:

                cpu_percent = (
                    process.cpu_percent(
                        interval=None
                    )
                )

                memory = (
                    process
                    .memory_info()
                    .rss
                )

                num_threads = (
                    process
                    .num_threads()
                )

                children = (
                    process.children(
                        recursive=True
                    )
                )

            except psutil.NoSuchProcess:
                break

            except psutil.Error:

                next_deadline += (
                    sample_s
                )

                sleep_for = (
                    next_deadline
                    - time.monotonic()
                )

                if sleep_for > 0:
                    time.sleep(
                        sleep_for
                    )

                continue

            current_children = {}

            for child in children:

                try:

                    current_children[
                        child.pid
                    ] = {
                        "name":
                            child.name(),

                        "status":
                            child.status(),
                    }

                except psutil.Error:

                    current_children[
                        child.pid
                    ] = {
                        "name": "",
                        "status": "",
                    }

            cpu_writer.writerow([
                poll_index,
                now_ns,
                f"{cpu_percent:.4f}",
                memory,
                num_threads,
                len(
                    current_children
                ),
            ])

            cpu_handle.flush()

            visible_pids = sorted(
                current_children.keys()
            )

            poll_writer.writerow([
                poll_index,
                now_ns,
                sample_ms,
                len(
                    visible_pids
                ),
                ";".join(
                    str(pid_value)
                    for pid_value
                    in visible_pids
                ),
            ])

            poll_handle.flush()

            # ------------------------------------------
            # OBSERVED PROCESS START
            # ------------------------------------------

            for (
                child_pid,
                info,
            ) in current_children.items():

                if (
                    child_pid
                    not in known_children
                ):

                    child_writer.writerow([
                        poll_index,
                        now_ns,
                        "OBSERVED_START",
                        pid,
                        child_pid,
                        info["name"],
                        info["status"],
                    ])

                    child_handle.flush()

            # ------------------------------------------
            # OBSERVED PROCESS END
            # ------------------------------------------

            for (
                child_pid,
                info,
            ) in known_children.items():

                if (
                    child_pid
                    not in current_children
                ):

                    child_writer.writerow([
                        poll_index,
                        now_ns,
                        "OBSERVED_END",
                        pid,
                        child_pid,
                        info["name"],
                        info["status"],
                    ])

                    child_handle.flush()

            known_children = (
                current_children
            )

            next_deadline += (
                sample_s
            )

            sleep_for = (
                next_deadline
                - time.monotonic()
            )

            if sleep_for > 0:

                time.sleep(
                    sleep_for
                )

            else:

                next_deadline = (
                    time.monotonic()
                )


def start_fs_usage(
    pid,
    run_dir,
):

    archive_path = (
        run_dir
        / "fs_usage_target.txt.gz"
    )

    monitor_error_path = (
        run_dir
        / "fs_usage_stderr.txt"
    )

    gzip_error_path = (
        run_dir
        / "gzip_stderr.txt"
    )

    archive_handle = (
        archive_path.open(
            "wb"
        )
    )

    monitor_error = (
        monitor_error_path.open(
            "wb"
        )
    )

    gzip_error = (
        gzip_error_path.open(
            "wb"
        )
    )

    monitor = subprocess.Popen(
        [
            "sudo",
            "-n",
            "/usr/bin/fs_usage",
            "-w",
            "-f",
            "filesys",
            str(pid),
        ],
        stdout=subprocess.PIPE,
        stderr=monitor_error,
    )

    gzip_process = (
        subprocess.Popen(
            [
                "/usr/bin/gzip",
                "-1",
                "-c",
            ],
            stdin=monitor.stdout,
            stdout=archive_handle,
            stderr=gzip_error,
        )
    )

    if (
        monitor.stdout
        is not None
    ):
        monitor.stdout.close()

    return {
        "monitor":
            monitor,

        "gzip":
            gzip_process,

        "archive_handle":
            archive_handle,

        "monitor_error":
            monitor_error,

        "gzip_error":
            gzip_error,

        "archive_path":
            archive_path,
    }


def stop_fs_usage(
    capture,
):

    monitor = (
        capture["monitor"]
    )

    gzip_process = (
        capture["gzip"]
    )

    if (
        monitor.poll()
        is None
    ):

        try:

            monitor.send_signal(
                signal.SIGINT
            )

            monitor.wait(
                timeout=5
            )

        except subprocess.TimeoutExpired:

            monitor.terminate()

            try:

                monitor.wait(
                    timeout=3
                )

            except subprocess.TimeoutExpired:

                monitor.kill()

                monitor.wait()

    try:

        gzip_process.wait(
            timeout=10
        )

    except subprocess.TimeoutExpired:

        gzip_process.terminate()

        gzip_process.wait()

    capture[
        "archive_handle"
    ].close()

    capture[
        "monitor_error"
    ].close()

    capture[
        "gzip_error"
    ].close()


def inspect_archive(
    path,
):

    start_marker = False
    end_marker = False
    target_file = False

    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
        errors="replace",
    ) as source:

        for line in source:

            if (
                "v2e34r_capture_start.txt"
                in line
            ):
                start_marker = True

            if (
                "v2e34r_capture_end.txt"
                in line
            ):
                end_marker = True

            if (
                "behavior_target.bin"
                in line
            ):
                target_file = True

    return (
        start_marker,
        end_marker,
        target_file,
    )


def main():

    parser = argparse.ArgumentParser()

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
        "--sample-ms",
        required=True,
        type=int,
        choices=[
            10,
            25,
            50,
            100,
            250,
        ],
    )

    parser.add_argument(
        "--phase-ms",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--rep",
        type=int,
        default=1,
    )

    args = (
        parser.parse_args()
    )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    rng = random.Random(
        args.seed
    )

    if (
        args.phase_ms
        is None
    ):

        phase_ms = (
            rng.uniform(
                0.0,
                float(
                    args.sample_ms
                ),
            )
        )

        phase_source = (
            "randomized"
        )

    else:

        phase_ms = float(
            args.phase_ms
        )

        phase_source = (
            "explicit"
        )

    run_id = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S_%f"
        )
    )

    run_dir = (
        OUTPUT_ROOT
        / run_id
    )

    run_dir.mkdir(
        parents=True
    )

    gate = (
        run_dir
        / "start_gate.signal"
    )

    runner = (
        Path(__file__)
        .resolve()
        .parent
        / "target_runner.py"
    )

    print("=" * 80)

    print(
        "IBSTER V2E34-R - "
        "PROCESS-START SAMPLING EXPERIMENT"
    )

    print("=" * 80)

    print(
        "Meminta izin administrator "
        "untuk fs_usage..."
    )

    subprocess.run(
        [
            "sudo",
            "-v",
        ],
        check=True,
    )

    target = (
        subprocess.Popen(
            [
                sys.executable,
                str(runner),

                "--output",
                str(run_dir),

                "--start-gate",
                str(gate),

                "--mode",
                args.mode,

                "--margin-ms",
                str(
                    args.margin_ms
                ),

                "--phase-ms",
                f"{phase_ms:.6f}",
            ]
        )
    )

    target_pid = (
        target.pid
    )

    print()

    print(
        f"Mode       : process_start"
    )

    print(
        f"Margin ms  : "
        f"{args.margin_ms}"
    )

    print(
        f"Sample ms  : "
        f"{args.sample_ms}"
    )

    print(
        f"Offset ms  : "
        f"{phase_ms:.6f} "
        f"({phase_source})"
    )

    print(
        f"Rep        : "
        f"{args.rep}"
    )

    print(
        f"Seed       : "
        f"{args.seed}"
    )

    print(
        f"Target PID : "
        f"{target_pid}"
    )

    print(
        f"Run ID     : "
        f"{run_id}"
    )

    print(
        f"Output     : "
        f"{run_dir}"
    )

    stop_event = (
        threading.Event()
    )

    telemetry_thread = (
        threading.Thread(
            target=telemetry_worker,
            args=(
                target_pid,
                run_dir,
                stop_event,
                args.sample_ms,
            ),
            daemon=True,
        )
    )

    telemetry_thread.start()

    capture = (
        start_fs_usage(
            target_pid,
            run_dir,
        )
    )

    time.sleep(
        0.6
    )

    if (
        capture[
            "monitor"
        ].poll()
        is not None
    ):

        stop_event.set()

        telemetry_thread.join(
            timeout=2
        )

        stop_fs_usage(
            capture
        )

        raise RuntimeError(
            "fs_usage berhenti "
            "sebelum workload dimulai."
        )

    # ----------------------------------------------
    # WALL / MONOTONIC MAPPING ANCHORS
    # ----------------------------------------------

    mapping_refs = []

    for _ in range(5):

        mapping_refs.append({
            "wall_ns":
                time.time_ns(),

            "monotonic_ns":
                time.monotonic_ns(),
        })

        time.sleep(
            0.005
        )

    print()
    print(
        "Collector aktif. "
        "Workload dimulai..."
    )

    gate.write_text(
        "START\n",
        encoding="utf-8",
    )

    returncode = (
        target.wait()
    )

    tail_wait_s = max(
        0.6,
        (
            args.sample_ms
            / 1000.0
        ) * 2.5,
    )

    time.sleep(
        tail_wait_s
    )

    stop_event.set()

    telemetry_thread.join(
        timeout=5
    )

    stop_fs_usage(
        capture
    )

    archive = (
        capture[
            "archive_path"
        ]
    )

    (
        start_ok,
        end_ok,
        target_ok,
    ) = inspect_archive(
        archive
    )

    cpu_ok = (
        run_dir
        / "cpu_telemetry.csv"
    ).exists()

    child_ok = (
        run_dir
        / "child_process_events.csv"
    ).exists()

    poll_ok = (
        run_dir
        / "poll_trace.csv"
    ).exists()

    gt_ok = (
        run_dir
        / "ground_truth.csv"
    ).exists()

    start_ref_ok = (
        run_dir
        / "child_start_reference.csv"
    ).exists()

    # ----------------------------------------------
    # MANIFEST
    # ----------------------------------------------

    manifest = {
        "experiment":
            "V2E34-R-process-start",

        "run_id":
            run_id,

        "mode":
            "process_start",

        "sample_interval_ms":
            args.sample_ms,

        "margin_ms":
            args.margin_ms,

        "phase_ms":
            phase_ms,

        "phase_source":
            phase_source,

        "seed":
            args.seed,

        "rep":
            args.rep,

        "target_pid":
            target_pid,

        "target_returncode":
            returncode,

        "python_version":
            sys.version,

        "psutil_version":
            psutil.__version__,

        "mapping_refs":
            mapping_refs,
    }

    (
        run_dir
        / "manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Keep disk usage controlled.
    behavior_target = (
        run_dir
        / "behavior_target.bin"
    )

    if (
        behavior_target.exists()
    ):

        try:

            behavior_target.unlink()

        except OSError as exc:

            print(
                "Warning: gagal "
                "menghapus behavior_target.bin: "
                f"{exc}"
            )

    archive_size = (
        archive.stat().st_size
        / (1024 * 1024)
    )

    print()
    print("=" * 80)

    print(
        "IBSTER V2E34-R - "
        "PROCESS-START CAPTURE CHECK"
    )

    print("=" * 80)

    print(
        f"Target return code : "
        f"{returncode}"
    )

    print(
        f"CPU telemetry      : "
        f"{cpu_ok}"
    )

    print(
        f"Child events       : "
        f"{child_ok}"
    )

    print(
        f"Poll trace         : "
        f"{poll_ok}"
    )

    print(
        f"Ground truth       : "
        f"{gt_ok}"
    )

    print(
        f"Start reference    : "
        f"{start_ref_ok}"
    )

    print(
        f"fs_usage gzip      : "
        f"{archive_size:.2f} MiB"
    )

    print(
        f"Start marker       : "
        f"{start_ok}"
    )

    print(
        f"End marker         : "
        f"{end_ok}"
    )

    print(
        f"Target file        : "
        f"{target_ok}"
    )

    complete = all([
        returncode == 0,
        cpu_ok,
        child_ok,
        poll_ok,
        gt_ok,
        start_ref_ok,
        start_ok,
        end_ok,
        target_ok,
    ])

    print()

    print(
        "CAPTURE STATUS: "
        + (
            "COMPLETE"
            if complete
            else "INCOMPLETE"
        )
    )

    if not complete:

        raise RuntimeError(
            "Process-start capture "
            "tidak lengkap."
        )

    print()
    print(
        "IBSTER V2E34-R - "
        "PROCESS-START EXPERIMENT COMPLETED"
    )


if __name__ == "__main__":
    main()