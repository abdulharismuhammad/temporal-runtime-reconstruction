import csv
import select
import time
from pathlib import Path


def watch_process_exit_kqueue(
    pid,
    output_file,
):
    """
    Observe process termination using macOS/BSD kqueue.

    The timestamp represents the monotonic time at which
    NOTE_EXIT was delivered to this observer. It is an
    event-driven observation timestamp, not claimed to be
    the exact kernel termination instant.
    """

    output_file = Path(
        output_file
    )

    kq = select.kqueue()

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

    kq.control(
        [event],
        0,
        0,
    )

    events = kq.control(
        None,
        1,
        None,
    )

    observed_ns = (
        time.monotonic_ns()
    )

    kq.close()

    delivered = bool(
        events
    )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(
            handle
        )

        writer.writerow([
            "pid",
            "observer",
            "registered_monotonic_ns",
            "exit_observed_monotonic_ns",
            "event_delivered",
        ])

        writer.writerow([
            pid,
            "kqueue_NOTE_EXIT",
            registered_ns,
            observed_ns,
            int(delivered),
        ])
