"""Resumable parallel job runner. Every call is one JSONL row; re-running skips finished jobs."""

import contextlib
import hashlib
import itertools
import json
import random
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from . import models

KEY_FIELDS = ("model", "prompt", "system", "params", "rep")
_NOLIMIT = contextlib.nullcontext()


def job_key(job: dict) -> str:
    return hashlib.sha1(json.dumps([job.get(k) for k in KEY_FIELDS], sort_keys=True).encode()).hexdigest()[
        :16
    ]


def load(path: Path) -> list[dict]:
    """All rows; a truncated last line (a crash mid-write) is skipped, a broken earlier line raises."""
    lines = path.read_text().splitlines() if path.exists() else []
    rows = []
    for i, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i < len(lines) - 1:
                raise
    return rows


def run_jobs(
    jobs: list[dict], out: Path, workers: int = 4, ask=models.ask, limits: dict | None = None
) -> list[dict]:
    """jobs: {model, prompt, system?, params?, rep?, **meta}. Returns one row per job, in job order.

    Failed calls are logged with `error` and retried on the next run. `limits` caps concurrent calls per model
    ({model: n}) below `workers`, e.g. for a pinned host that rate-limits.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {r["key"]: r for r in load(out) if "error" not in r}
    lock = threading.Lock()
    slots = {m: threading.Semaphore(n) for m, n in (limits or {}).items()}

    def one(job):
        key = job_key(job)
        if key in done:
            return done[key]
        with slots.get(job["model"], _NOLIMIT):
            row = {"key": key, **job, "ts": datetime.now(UTC).isoformat(timespec="seconds")}
            try:
                row |= asdict(ask(job["model"], job["prompt"], job.get("system"), **job.get("params", {})))
            except Exception as e:  # noqa: BLE001 - keep the run alive; the row records why
                row["error"] = f"{type(e).__name__}: {e}"
        with lock, out.open("a") as f:
            f.write(json.dumps(row) + "\n")
        return row

    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, jobs))


def conditions(cfg: dict) -> list[dict]:
    """A list of conditions, or {factor: [levels]} crossed into every combination (a factorial design)."""
    c = cfg["conditions"]
    if isinstance(c, list):
        return c
    return [{k: v for level in combo for k, v in level.items()} for combo in itertools.product(*c.values())]


def experiment_jobs(cfg: dict) -> list[dict]:
    """models x conditions x repeats; `prompt` is a str.format template over each condition's fields.

    `params` maps a backend or a full model id (which wins) to call params; a condition's own `params`
    (same shape) overrides them, so one config can run the same model with thinking off and on."""

    def params(m, c):  # backend, then the full model id; the config, then the condition
        p = [cfg.get("params", {}), c.get("params", {})]
        return {k: v for d in p for key in (m.split(":")[0], m) for k, v in d.get(key, {}).items()}

    jobs = [
        {
            "model": m,
            "prompt": cfg["prompt"].format(**c),
            "system": cfg.get("system"),
            "params": params(m, c),
            "rep": r,
            "condition": c,
        }
        for m in cfg["models"]
        for c in conditions(cfg)
        for r in range(cfg.get("repeats", 1))
    ]
    dup = len(jobs) - len({job_key(j) for j in jobs})
    if dup:  # two conditions that make the same call share one log row, so one would vanish from the report
        raise ValueError(f"{dup} jobs are identical calls; make their prompt or params differ")
    return jobs


def _version(cmd: list[str]) -> str | None:
    try:
        return (
            subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=30).stdout.strip()
            or None
        )
    except (OSError, subprocess.SubprocessError):
        return None


def plan(cfg: dict, out: Path, seed: int = 0) -> list[dict]:
    """The config's jobs, pinned to the run folder `out` and shuffled with a recorded seed (so modes don't
    run in blocks that line up with rate limits or provider drift).

    `manifest.json` keeps the planned job keys and the config: a config that plans new or changed calls is
    refused (use a new name); one that drops calls (a model, a condition) or only changes scoring fields
    (answer keys, human rates) replaces the snapshot, so `load_run` uses the current plan and rubric. Each call appends the date, git
    revision and CLI versions to `invocations.jsonl`."""
    jobs = experiment_jobs(cfg)
    keys = sorted(job_key(j) for j in jobs)
    manifest = out / "manifest.json"
    old = set(json.loads(manifest.read_text())["keys"]) if manifest.exists() else set(keys)
    if set(keys) - old:  # a plan may shrink (dropped calls stay in the log, out of the analysis), not change
        raise ValueError(f"{out} was planned with different calls; give the changed config a new name")
    dropped = len(old - set(keys))
    out.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"config": cfg, "keys": keys}, indent=1))
    versions = {
        b: _version([b, "--version"])
        for b in sorted({m.split(":")[0] for m in cfg["models"]})
        if b in models.CLI_PARAMS
    }
    with (out / "invocations.jsonl").open("a") as f:
        f.write(json.dumps({"ts": datetime.now(UTC).isoformat(timespec="seconds"), "seed": seed, "dropped": dropped,
                            "git": _version(["git", "rev-parse", "--short", "HEAD"]), "cli": versions}) + "\n")  # fmt: skip
    random.Random(seed).shuffle(jobs)
    return jobs


def load_run(run_dir: Path) -> list[dict]:
    """A run's rows in its current plan, with each condition taken from the run's config snapshot (see
    `plan`). Rows of calls the plan has since dropped stay on disk but are left out here."""
    rows = load(run_dir / "results.jsonl")
    manifest = run_dir / "manifest.json"
    if manifest.exists():
        cond = {
            job_key(j): j["condition"] for j in experiment_jobs(json.loads(manifest.read_text())["config"])
        }
        rows = [r | {"condition": cond[r["key"]]} for r in rows if r.get("key") in cond]
    return rows
