import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple


@dataclass(frozen=True)
class GameWorkflow:
    code: str
    csv_name: str
    extra: Tuple[str, ...] = ()


GAMES: Tuple[GameWorkflow, ...] = (
    GameWorkflow("3d", "fucai3d.csv"),
    GameWorkflow("pl3", "pl3.csv"),
    GameWorkflow("pl5", "pl5.csv"),
    GameWorkflow("qxc", "qxc.csv"),
    GameWorkflow("qlc", "qlc.csv"),
    GameWorkflow("kl8", "kl8.csv", ("--pick-size", "10")),
    GameWorkflow("ssq", "ssq.csv"),
    GameWorkflow("dlt", "dlt.csv"),
)

POSITION_LENGTHS = {"3d": 3, "pl3": 3, "pl5": 5, "qxc": 7}


class WorkflowError(RuntimeError):
    pass


def run_update_workflow(
    game: str,
    data_dir: Path,
    report_dir: Path,
    recommendation_dir: Path,
    dry_run: bool = False,
) -> None:
    config = _game_config(game)
    if not dry_run:
        for path in (data_dir, report_dir, recommendation_dir):
            path.mkdir(parents=True, exist_ok=True)

    csv_path = data_dir / config.csv_name
    _run_lottery_command(
        f"update-{config.code}",
        ["update-" + config.code, "--csv", str(csv_path)],
        dry_run=dry_run,
    )

    game_dir = recommendation_dir / config.code
    records = _record_files(game_dir)
    if dry_run and not records:
        records = [game_dir / "<issue>.csv"]
    for record in records:
        _verify_record(config, csv_path, record, dry_run)

    summary_path = report_dir / "recommendation-summary.txt"
    summary_records = _record_files(recommendation_dir)
    if dry_run and not summary_records:
        summary_records = [recommendation_dir / "*" / "*.csv"]
    _summarize(summary_records, summary_path, dry_run)
    print(f"Update workflow finished for: {config.code}")


def run_daily_workflow(
    game: str,
    data_dir: Path,
    report_dir: Path,
    recommendation_dir: Path,
    model_dir: Path,
    seed: int = 20260505,
    seeds: str = "1,2,3,4,5",
    window: int = 30,
    count: int = 10,
    position_counts: str = "",
    combination_mode: str = "top",
    ml_min_history: int = 30,
    ml_min_train: int = 200,
    ml_train_epochs: int = 8,
    ml_backtest_epochs: int = 3,
    ml_backtest_limit: int = 30,
    ml_retrain_every: int = 10,
    skip_update: bool = False,
    dry_run: bool = False,
) -> None:
    config = _game_config(game)
    if not 1 <= count <= 1000:
        raise ValueError("Count must be between 1 and 1000.")
    position_args = _position_arguments(game, position_counts, combination_mode, count)

    if not dry_run:
        for path in (data_dir, report_dir, recommendation_dir, model_dir):
            path.mkdir(parents=True, exist_ok=True)

    csv_path = data_dir / config.csv_name
    if not skip_update:
        _run_lottery_command(
            f"update-{config.code}",
            ["update-" + config.code, "--csv", str(csv_path)],
            dry_run=dry_run,
        )
    elif not dry_run and not csv_path.exists():
        raise WorkflowError(f"Data file not found: {csv_path}. Run without --skip-update first.")

    extra = list(config.extra)
    _run_lottery_command(
        f"backtest-{config.code}",
        ["backtest-" + config.code, "--csv", str(csv_path), *extra, "--seed", str(seed)],
        report_dir / f"backtest-{config.code}.txt",
        dry_run,
    )
    _run_lottery_command(
        f"compare-{config.code}",
        [
            "compare-" + config.code,
            "--csv",
            str(csv_path),
            *extra,
            "--seed",
            str(seed),
            "--window",
            str(window),
        ],
        report_dir / f"compare-{config.code}.txt",
        dry_run,
    )
    _run_lottery_command(
        f"stability-{config.code}",
        [
            "stability-" + config.code,
            "--csv",
            str(csv_path),
            *extra,
            "--seeds",
            seeds,
            "--window",
            str(window),
        ],
        report_dir / f"stability-{config.code}.txt",
        dry_run,
    )

    stat_report = report_dir / f"recommend-{config.code}.txt"
    if position_counts:
        if not dry_run:
            stat_report.write_text(
                "Position mode: recommendations are in the ML report.",
                encoding="utf-8",
            )
    else:
        _run_lottery_command(
            f"recommend-{config.code}",
            [
                "recommend-" + config.code,
                "--csv",
                str(csv_path),
                *extra,
                "--seed",
                str(seed),
                "--window",
                str(window),
                "--count",
                str(count),
            ],
            stat_report,
            dry_run,
        )

    model_path = model_dir / f"{config.code}-ml.json"
    _run_lottery_command(
        f"train-ml-{config.code}",
        [
            f"train-ml-{config.code}",
            "--csv",
            str(csv_path),
            "--model",
            str(model_path),
            "--min-history",
            str(ml_min_history),
            "--epochs",
            str(ml_train_epochs),
            *extra,
        ],
        dry_run=dry_run,
    )
    _run_lottery_command(
        f"backtest-ml-{config.code}",
        [
            f"backtest-ml-{config.code}",
            "--csv",
            str(csv_path),
            "--min-train",
            str(ml_min_train),
            "--min-history",
            str(ml_min_history),
            "--limit",
            str(ml_backtest_limit),
            "--retrain-every",
            str(ml_retrain_every),
            "--epochs",
            str(ml_backtest_epochs),
            *extra,
        ],
        report_dir / f"backtest-ml-{config.code}.txt",
        dry_run,
    )
    _run_lottery_command(
        f"recommend-ml-{config.code}",
        [
            f"recommend-ml-{config.code}",
            "--csv",
            str(csv_path),
            "--model",
            str(model_path),
            "--count",
            str(count),
            "--min-history",
            str(ml_min_history),
            "--epochs",
            str(ml_train_epochs),
            *extra,
            *position_args,
        ],
        report_dir / f"recommend-ml-{config.code}.txt",
        dry_run,
    )
    _run_lottery_command(
        f"record-ml-{config.code}",
        [
            f"record-recommend-ml-{config.code}",
            "--csv",
            str(csv_path),
            "--model",
            str(model_path),
            "--store",
            str(recommendation_dir),
            "--count",
            str(count),
            "--min-history",
            str(ml_min_history),
            "--epochs",
            str(ml_train_epochs),
            *extra,
            *position_args,
        ],
        dry_run=dry_run,
    )

    records = _record_files(recommendation_dir / config.code)
    if dry_run and not records:
        records = [recommendation_dir / config.code / "<issue>.csv"]
    for record in records:
        _verify_record(config, csv_path, record, dry_run)

    if not position_counts:
        _run_lottery_command(
            f"record-{config.code}",
            [
                "record-recommend-" + config.code,
                "--csv",
                str(csv_path),
                "--store",
                str(recommendation_dir),
                "--seed",
                str(seed),
                "--window",
                str(window),
                "--count",
                str(count),
                *extra,
            ],
            dry_run=dry_run,
        )

    summary_path = report_dir / "recommendation-summary.txt"
    summary_records = _record_files(recommendation_dir)
    if dry_run and not summary_records:
        summary_records = [recommendation_dir / "*" / "*.csv"]
    _summarize(summary_records, summary_path, dry_run)
    print(f"Daily workflow finished for: {config.code}")


def _game_config(game: str) -> GameWorkflow:
    for config in GAMES:
        if config.code == game:
            return config
    allowed = ", ".join(config.code for config in GAMES)
    raise ValueError(f"Unsupported game '{game}'. Allowed: {allowed}")


def _position_arguments(
    game: str,
    position_counts: str,
    combination_mode: str,
    count: int,
) -> list[str]:
    if combination_mode not in {"top", "full"}:
        raise ValueError("Combination mode must be top or full.")
    if not position_counts:
        if combination_mode == "full":
            raise ValueError("Full combinations require position counts.")
        return []
    if game not in POSITION_LENGTHS:
        raise ValueError("Position counts require one of 3d, pl3, pl5 or qxc.")

    parts = [part.strip() for part in position_counts.split(",")]
    expected = POSITION_LENGTHS[game]
    if len(parts) != expected:
        raise ValueError(f"Position counts must contain {expected} integers.")

    values = []
    product = 1
    for index, part in enumerate(parts):
        if not part.isascii() or not part.isdigit():
            raise ValueError("Position counts must be positive integers.")
        value = int(part)
        maximum = 15 if game == "qxc" and index == expected - 1 else 10
        if not 1 <= value <= maximum:
            raise ValueError("Position counts value is outside the allowed range.")
        values.append(value)
        product *= value
    if combination_mode == "full" and product > 1000:
        raise ValueError("Full combinations cannot exceed 1000.")
    if combination_mode == "top" and count > product:
        raise ValueError("Candidate count exceeds the combination pool.")
    return ["--position-counts", position_counts, "--combination-mode", combination_mode]


def _record_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    if path.is_file():
        return [path]
    return sorted(item for item in path.rglob("*.csv") if item.is_file())


def _verify_record(
    config: GameWorkflow,
    csv_path: Path,
    record: Path,
    dry_run: bool,
) -> None:
    _run_lottery_command(
        f"verify-{config.code}-{record.stem}",
        [
            "verify-recommend-" + config.code,
            "--csv",
            str(csv_path),
            "--records",
            str(record),
            "--output",
            str(record),
            *config.extra,
        ],
        dry_run=dry_run,
    )


def _summarize(records: Sequence[Path], output_path: Path, dry_run: bool) -> None:
    if not records:
        print("[summarize-recommendations] no recommendation records found")
        return
    _run_lottery_command(
        "summarize-recommendations",
        [
            "summarize-recommendations",
            "--records",
            *(str(record) for record in records),
            "--output",
            str(output_path),
        ],
        dry_run=dry_run,
    )


def _lottery_cli_prefix() -> list[str]:
    cli_exe = os.environ.get("LOTTERY_CLI_EXE", "").strip()
    if cli_exe:
        return [cli_exe, "--cli"]
    python = os.environ.get("LOTTERY_PYTHON", "").strip() or sys.executable
    return [python, "-m", "lottery_sim.cli"]


def _run_lottery_command(
    name: str,
    arguments: Sequence[str],
    output_file: Optional[Path] = None,
    dry_run: bool = False,
) -> None:
    command = [*_lottery_cli_prefix(), *arguments]
    command_text = subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
    print(f"[{name}] {command_text}", flush=True)
    if dry_run:
        return

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if output_file is None:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            bufsize=1,
        )
        if process.stdout is not None:
            for line in process.stdout:
                print(line, end="", flush=True)
            process.stdout.close()
        exit_code = process.wait()
        if exit_code:
            raise WorkflowError(f"Command failed with exit code {exit_code}: {name}")
        return

    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(completed.stdout, encoding="utf-8")
    print(f"  -> {output_file}", flush=True)
    if completed.returncode:
        print(completed.stdout, end="", flush=True)
        raise WorkflowError(f"Command failed with exit code {completed.returncode}: {name}")
