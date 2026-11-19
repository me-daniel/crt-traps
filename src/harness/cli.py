"""crt run EXP.yaml [--batch N] | ask MODEL PROMPT [--effort E] | report RUN_DIR [--by FIELD ...]"""

import argparse
from pathlib import Path

import yaml
from dotenv import load_dotenv


def main():
    p = argparse.ArgumentParser(prog="crt")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run an experiment (resumes if runs/<name> exists)")
    r.add_argument("config")
    r.add_argument("--name", help="run folder under runs/ (default: config 'name')")
    r.add_argument(
        "--batch", type=int, help="run only conditions with this `batch` value (the plan stays whole)"
    )
    a = sub.add_parser("ask", help="one call, e.g. crt ask claude:opus 'hi'")
    a.add_argument("model")
    a.add_argument("prompt")
    a.add_argument("--system")
    a.add_argument("--effort", help="reasoning effort, e.g. low, medium, high (claude, codex)")
    rp = sub.add_parser("report", help="runs/<name> -> paper/generated/<name>.tex")
    rp.add_argument("run_dir")
    rp.add_argument("--by", nargs="+", default=[], help="condition fields to split rows by, e.g. mode")
    args = p.parse_args()
    load_dotenv()

    if args.cmd == "ask":
        from .models import ask

        params = {"effort": args.effort} if args.effort else {}
        print(ask(args.model, args.prompt, args.system, **params).text)
    elif args.cmd == "report":
        from .report import write

        print(f"-> {write(Path(args.run_dir), by=tuple(args.by))}")
    else:
        cfg = yaml.safe_load(Path(args.config).read_text())
        out = Path("runs") / (args.name or cfg.get("name") or Path(args.config).stem)
        from .runner import plan, run_jobs

        jobs = plan(cfg, out)
        if args.batch is not None:
            jobs = [j for j in jobs if j["condition"].get("batch") == args.batch]
            if not jobs:
                raise SystemExit(f"no conditions with batch: {args.batch}")
        rows = run_jobs(jobs, out / "results.jsonl", cfg.get("workers", 4), limits=cfg.get("limits"))
        print(f"{len(rows)} calls, {sum('error' in r for r in rows)} failed")
        print(f"-> {out}")
