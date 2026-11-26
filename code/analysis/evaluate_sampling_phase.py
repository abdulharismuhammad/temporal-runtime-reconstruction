import argparse
import csv
from collections import defaultdict
from pathlib import Path


def read_csv(path):
    with path.open(
        newline="",
        encoding="utf-8",
    ) as source:
        return list(csv.DictReader(source))


def mean(values):
    return (
        sum(values) / len(values)
        if values
        else 0.0
    )


def read_condition(run_dir):
    rows = read_csv(
        run_dir / "condition.csv"
    )

    if len(rows) != 1:
        raise RuntimeError(
            f"Invalid condition.csv: {run_dir}"
        )

    return {
        "mode":
            rows[0]["mode"],

        "margin_ms":
            int(rows[0]["margin_ms"]),

        "phase_ms":
            int(rows[0]["phase_ms"]),
    }


def read_gt(run_dir):
    rows = read_csv(
        run_dir / "ground_truth.csv"
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


def read_gt_relation(run_dir):
    rows = read_csv(
        run_dir
        / "ground_truth_relations.csv"
    )

    for row in rows:
        if (
            row["activity_a"]
            == "child_B"
            and row["activity_b"]
            == "file_read"
        ):
            return row["relation"]

    raise RuntimeError(
        f"GT target relation missing: {run_dir}"
    )


def read_observed_intervals(run_dir):
    path = (
        run_dir
        / "v2e15_complex_graph_reconstruction"
        / "observed_behavior_intervals.csv"
    )

    rows = read_csv(path)

    children = [
        row
        for row in rows
        if row["behavior"].startswith(
            "child_process_observed_pid_"
        )
    ]

    reads = [
        row
        for row in rows
        if row["behavior"]
        == "file_read_observed"
    ]

    if len(children) != 1:
        raise RuntimeError(
            f"Expected 1 child, got "
            f"{len(children)}: {run_dir}"
        )

    if len(reads) != 1:
        raise RuntimeError(
            f"Expected 1 read, got "
            f"{len(reads)}: {run_dir}"
        )

    return children[0], reads[0]


def summarize(rows):
    matched = sum(
        row["matched"]
        for row in rows
    )

    return {
        "runs":
            len(rows),

        "matched":
            matched,

        "agreement":
            (
                matched / len(rows)
                if rows
                else 0.0
            ),

        "mean_gt_boundary_ms":
            mean([
                row["gt_boundary_ms"]
                for row in rows
            ]),

        "mean_observed_boundary_ms":
            mean([
                row[
                    "observed_boundary_ms"
                ]
                for row in rows
            ]),

        "mean_boundary_error_ms":
            mean([
                row[
                    "boundary_error_ms"
                ]
                for row in rows
            ]),

        "mean_abs_boundary_error_ms":
            mean([
                abs(
                    row[
                        "boundary_error_ms"
                    ]
                )
                for row in rows
            ]),

        "mean_child_end_lag_ms":
            mean([
                row[
                    "child_end_lag_ms"
                ]
                for row in rows
            ]),

        "min_child_end_lag_ms":
            min([
                row[
                    "child_end_lag_ms"
                ]
                for row in rows
            ]),

        "max_child_end_lag_ms":
            max([
                row[
                    "child_end_lag_ms"
                ]
                for row in rows
            ]),

        "mean_abs_read_start_error_ms":
            mean([
                abs(
                    row[
                        "read_start_error_ms"
                    ]
                )
                for row in rows
            ]),
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--capture-root",
        required=True,
    )

    parser.add_argument(
        "--blind-summary",
        required=True,
    )

    args = parser.parse_args()

    root = Path(
        args.capture_root
    ).resolve()

    blind_rows = read_csv(
        Path(
            args.blind_summary
        ).resolve()
    )

    blind_by_run = {
        row["run_id"]: row
        for row in blind_rows
    }

    results = []

    confusion = defaultdict(
        lambda: defaultdict(int)
    )

    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir():
            continue

        if run_dir.name not in blind_by_run:
            continue

        condition = read_condition(
            run_dir
        )

        gt = read_gt(
            run_dir
        )

        gt_relation = (
            read_gt_relation(
                run_dir
            )
        )

        blind = (
            blind_by_run[
                run_dir.name
            ]
        )

        observed_relation = (
            blind[
                "observed_relation"
            ]
        )

        observed_boundary_ms = float(
            blind[
                "observed_boundary_ms"
            ]
        )

        gt_boundary_ms = (
            gt[
                "file_read"
            ]["start_ns"]
            - gt[
                "child_B"
            ]["end_ns"]
        ) / 1e6

        child_obs, read_obs = (
            read_observed_intervals(
                run_dir
            )
        )

        observed_child_end_ns = int(
            child_obs[
                "end_monotonic_ns"
            ]
        )

        observed_read_start_ns = int(
            read_obs[
                "start_monotonic_ns"
            ]
        )

        child_end_lag_ms = (
            observed_child_end_ns
            - gt[
                "child_B"
            ]["end_ns"]
        ) / 1e6

        read_start_error_ms = (
            observed_read_start_ns
            - gt[
                "file_read"
            ]["start_ns"]
        ) / 1e6

        boundary_error_ms = (
            observed_boundary_ms
            - gt_boundary_ms
        )

        matched = (
            observed_relation
            == gt_relation
        )

        row = {
            "run_id":
                run_dir.name,

            "mode":
                condition["mode"],

            "margin_ms":
                condition["margin_ms"],

            "phase_ms":
                condition["phase_ms"],

            "gt_relation":
                gt_relation,

            "observed_relation":
                observed_relation,

            "matched":
                int(matched),

            "gt_boundary_ms":
                gt_boundary_ms,

            "observed_boundary_ms":
                observed_boundary_ms,

            "boundary_error_ms":
                boundary_error_ms,

            "child_end_lag_ms":
                child_end_lag_ms,

            "read_start_error_ms":
                read_start_error_ms,
        }

        results.append(row)

        confusion[
            gt_relation
        ][
            observed_relation
        ] += 1

    if len(results) != 50:
        raise SystemExit(
            f"Expected 50 runs, got "
            f"{len(results)}"
        )

    output_dir = (
        Path(__file__)
        .resolve()
        .parent
        / "output"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ==================================================
    # PER-RUN OUTPUT
    # ==================================================
    run_file = (
        output_dir
        / "sampling_phase_run_evaluation.csv"
    )

    fields = [
        "run_id",
        "mode",
        "margin_ms",
        "phase_ms",
        "gt_relation",
        "observed_relation",
        "matched",
        "gt_boundary_ms",
        "observed_boundary_ms",
        "boundary_error_ms",
        "child_end_lag_ms",
        "read_start_error_ms",
    ]

    with run_file.open(
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
            writer.writerow({
                **row,

                "gt_boundary_ms":
                    f"{row['gt_boundary_ms']:.3f}",

                "observed_boundary_ms":
                    f"{row['observed_boundary_ms']:.3f}",

                "boundary_error_ms":
                    f"{row['boundary_error_ms']:.3f}",

                "child_end_lag_ms":
                    f"{row['child_end_lag_ms']:.3f}",

                "read_start_error_ms":
                    f"{row['read_start_error_ms']:.3f}",
            })

    # ==================================================
    # GROUP BY MODE + MARGIN
    # Each group contains five phase offsets.
    # ==================================================
    by_margin = defaultdict(list)

    for row in results:
        by_margin[
            (
                row["mode"],
                row["margin_ms"],
            )
        ].append(row)

    margin_rows = []

    for key in sorted(
        by_margin
    ):
        mode, margin = key

        stats = summarize(
            by_margin[key]
        )

        margin_rows.append({
            "mode":
                mode,

            "margin_ms":
                margin,

            **stats,
        })

    margin_file = (
        output_dir
        / "sampling_phase_by_margin.csv"
    )

    # ==================================================
    # GROUP BY MODE + PHASE
    # Each group contains five margins.
    # ==================================================
    by_phase_mode = defaultdict(list)

    for row in results:
        by_phase_mode[
            (
                row["mode"],
                row["phase_ms"],
            )
        ].append(row)

    phase_mode_rows = []

    for key in sorted(
        by_phase_mode
    ):
        mode, phase = key

        stats = summarize(
            by_phase_mode[key]
        )

        phase_mode_rows.append({
            "mode":
                mode,

            "phase_ms":
                phase,

            **stats,
        })

    phase_mode_file = (
        output_dir
        / "sampling_phase_by_mode_phase.csv"
    )

    # ==================================================
    # GROUP BY PHASE
    # 10 runs per phase:
    # 5 BEFORE + 5 OVERLAPS
    # ==================================================
    by_phase = defaultdict(list)

    for row in results:
        by_phase[
            row["phase_ms"]
        ].append(row)

    phase_rows = []

    for phase in sorted(
        by_phase
    ):
        stats = summarize(
            by_phase[phase]
        )

        phase_rows.append({
            "phase_ms":
                phase,

            **stats,
        })

    phase_file = (
        output_dir
        / "sampling_phase_summary.csv"
    )

    summary_fields = [
        "runs",
        "matched",
        "agreement",
        "mean_gt_boundary_ms",
        "mean_observed_boundary_ms",
        "mean_boundary_error_ms",
        "mean_abs_boundary_error_ms",
        "mean_child_end_lag_ms",
        "min_child_end_lag_ms",
        "max_child_end_lag_ms",
        "mean_abs_read_start_error_ms",
    ]

    def write_summary(
        path,
        prefix_fields,
        rows,
    ):
        with path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as destination:

            writer = csv.DictWriter(
                destination,
                fieldnames=(
                    prefix_fields
                    + summary_fields
                ),
            )

            writer.writeheader()

            for row in rows:
                output = dict(row)

                for field in [
                    "agreement",
                    "mean_gt_boundary_ms",
                    "mean_observed_boundary_ms",
                    "mean_boundary_error_ms",
                    "mean_abs_boundary_error_ms",
                    "mean_child_end_lag_ms",
                    "min_child_end_lag_ms",
                    "max_child_end_lag_ms",
                    "mean_abs_read_start_error_ms",
                ]:
                    output[field] = (
                        f"{row[field]:.6f}"
                    )

                writer.writerow(
                    output
                )

    write_summary(
        margin_file,
        [
            "mode",
            "margin_ms",
        ],
        margin_rows,
    )

    write_summary(
        phase_mode_file,
        [
            "mode",
            "phase_ms",
        ],
        phase_mode_rows,
    )

    write_summary(
        phase_file,
        [
            "phase_ms",
        ],
        phase_rows,
    )

    # ==================================================
    # TERMINAL REPORT
    # ==================================================
    print("=" * 116)
    print(
        "IBSTER V2E34-D - FINAL SAMPLING-PHASE EVALUATION"
    )
    print("=" * 116)

    print()
    print("BY MODE + MARGIN")
    print("-" * 116)

    for row in margin_rows:
        print(
            f"{row['mode']:<11} | "
            f"margin={row['margin_ms']:>3} ms | "
            f"matched="
            f"{row['matched']}/{row['runs']} | "
            f"agreement="
            f"{row['agreement']:.3f} | "
            f"child-end lag="
            f"{row['mean_child_end_lag_ms']:7.3f} ms | "
            f"lag range="
            f"[{row['min_child_end_lag_ms']:7.3f}, "
            f"{row['max_child_end_lag_ms']:7.3f}]"
        )

    print()
    print("BY MODE + PHASE")
    print("-" * 116)

    for row in phase_mode_rows:
        print(
            f"{row['mode']:<11} | "
            f"phase={row['phase_ms']:>2} ms | "
            f"matched="
            f"{row['matched']}/{row['runs']} | "
            f"agreement="
            f"{row['agreement']:.3f} | "
            f"mean child-end lag="
            f"{row['mean_child_end_lag_ms']:7.3f} ms | "
            f"boundary MAE="
            f"{row['mean_abs_boundary_error_ms']:7.3f} ms"
        )

    total = len(
        results
    )

    matched = sum(
        row["matched"]
        for row in results
    )

    mismatches = [
        row
        for row in results
        if not row["matched"]
    ]

    print()
    print("AGGREGATE")
    print("-" * 116)

    print(
        f"Runs evaluated             : {total}"
    )

    print(
        f"Relations matched          : "
        f"{matched}/{total}"
    )

    print(
        f"Overall relation agreement : "
        f"{matched / total:.6f}"
    )

    print(
        f"Mismatches                 : "
        f"{len(mismatches)}"
    )

    print(
        f"Mean abs boundary error    : "
        f"{mean([abs(r['boundary_error_ms']) for r in results]):.3f} ms"
    )

    print(
        f"Mean child-end lag         : "
        f"{mean([r['child_end_lag_ms'] for r in results]):.3f} ms"
    )

    print(
        f"Mean abs read-start error  : "
        f"{mean([abs(r['read_start_error_ms']) for r in results]):.3f} ms"
    )

    print()
    print("CONFUSION")
    print("-" * 116)

    classes = [
        "BEFORE",
        "OVERLAPS",
    ]

    print(
        "GT\\OBS".ljust(16)
        + "".join(
            item.ljust(16)
            for item in classes
        )
    )

    for gt_relation in classes:
        print(
            gt_relation.ljust(16)
            + "".join(
                str(
                    confusion[
                        gt_relation
                    ][observed]
                ).ljust(16)
                for observed
                in classes
            )
        )

    print()
    print("MISMATCHED RUNS")
    print("-" * 116)

    if not mismatches:
        print(
            "None"
        )

    for row in mismatches:
        print(
            f"{row['run_id']} | "
            f"{row['mode']:<11} | "
            f"margin={row['margin_ms']:>3} ms | "
            f"phase={row['phase_ms']:>2} ms | "
            f"GT={row['gt_relation']:<8} | "
            f"OBS={row['observed_relation']:<8} | "
            f"GT boundary="
            f"{row['gt_boundary_ms']:+8.3f} ms | "
            f"OBS boundary="
            f"{row['observed_boundary_ms']:+8.3f} ms | "
            f"child lag="
            f"{row['child_end_lag_ms']:7.3f} ms"
        )

    print()
    print(
        f"Run evaluation : {run_file}"
    )

    print(
        f"By margin      : {margin_file}"
    )

    print(
        f"By mode/phase  : {phase_mode_file}"
    )

    print(
        f"Phase summary  : {phase_file}"
    )

    print()
    print(
        "Condition and ground truth were opened only "
        "after the blind V2E34-C reconstruction was frozen."
    )


if __name__ == "__main__":
    main()
