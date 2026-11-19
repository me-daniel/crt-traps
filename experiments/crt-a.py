"""Study A analysis, written before any outcome was looked at (concept: docs/study-a-concept.md v2, §1, §3 to §5).

Rows per model: outcome block (study B's 96 items; always-reasoners from crt-a-<m> with arms off, on, off_steps;
choosers from crt-b-<m>, effort off -> off and max -> on) and plain block (crt-a-<m>-plain, arms off and on, 2 draws).
Accuracy: kind == "correct"; unparsed replies count as wrong. Means weight families equally (items within family).
forced-on  an on block qualifies if >= 95% of its planned draws reasoned (explicit count > 0); "undecidable" if unknown
           (missing count or failed call) draws could flip it; else "mostly on". Shown per model and block.
A1  gain = logit(acc on) - logit(acc off). Traps: all outcome trap draws. Matched plain: plain items reweighted so their
    off draw-1 accuracy equals the traps' off accuracy (weights p/q for correct, (1-p)/(1-q) for wrong items), then
    evaluated on off draw 2 and the on draws. A1 = trap gain - matched plain gain. 95% bootstrap interval: numeric
    instances resampled within family (both trap wordings together) and plain items resampled, the same resamples for
    every model; matching is redone inside each resample. lo > 0 supports A1; otherwise falsified for that model.
    Summary: equal-weight mean over the six always-reasoners. Control items get the same gain, shown next to it.
A2  off points (all 10 models): x = plain accuracy off, y = trap error off; OLS with intercept. On points that qualify in
    both blocks and lie inside the off x-range get residual y_on - fit(x_on), also with the model's own off point left
    out. Bootstrap as in A1 (plain items carry the capability uncertainty).
A3  method answers per trap call and per wrong trap answer, by arm.  A4  trap accuracy off_steps vs on.
Every table also without sheep. logit uses p clipped to [0.5/n, 1 - 0.5/n].
Run: uv run python experiments/crt-a.py            -> paper/generated/crt-a-*.tex
     uv run python experiments/crt-a.py --checks   manipulation checks only (no outcomes)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from harness.report import scored, to_latex, to_macros
from harness.runner import load_run

ALWAYS = ["granite-4.2-8b", "nemotron-3.5-lightning", "mistral-small-4", "qwen3.8-27b", "deepseek-v4.1-flash",
          "haiku-4-5"]  # fmt: skip
CHOOSERS = ["gpt-6-luna", "gpt-5.6-luna", "gpt-5.6-terra", "sonnet-4-6"]
PLANNED = {"outcome": {m: 96 for m in ALWAYS} | {m: 288 for m in CHOOSERS}, "plain": 80, "hard": 80}  # on draws per block
BOOT, SEED = 2000, 20261118


def frame(rows: list[dict], model: str, block: str, arm_of=lambda c: c["arm"]) -> pd.DataFrame:
    extra = lambda c: tuple((k, c[k]) for k in ("method", "shortcut") if k in c)
    df = scored(rows, by=("id", "pair", "family", "edit", "wording", "steps"), extra=extra)
    df["arm"] = [arm_of(c) for c in df.condition]
    df = df[df.arm.notna()].copy()
    df["tokens"] = [r.get("thinking_tokens") for r in df.to_dict("records")]
    df["correct"] = (df.kind == "correct").astype(float).where(df.ok)
    return df.assign(model=model, block=block)


def load() -> pd.DataFrame:
    parts = []
    get = lambda name: load_run(Path("runs") / name) if (Path("runs") / name).exists() else []
    for m in ALWAYS:
        if rows := get(f"crt-a-{m}"):
            parts.append(frame(rows, m, "outcome"))
    for m in CHOOSERS:
        if rows := get(f"crt-b-{m}"):
            parts.append(frame(rows, m, "outcome", lambda c: {"off": "off", "max": "on"}.get(c["effort"])))
    for m in ALWAYS + CHOOSERS:
        if rows := get(f"crt-a-{m}-plain"):
            parts.append(frame(rows, m, "plain"))
        if rows := get(f"crt-a-{m}-hard"):  # A2b (concept v2.2 §8)
            parts.append(frame(rows, m, "hard"))
    return pd.concat(parts, ignore_index=True)


def forced_on(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (m, block), g in df[df.arm == "on"].groupby(["model", "block"]):
        n = PLANNED["outcome"][m] if block == "outcome" else PLANNED[block]
        ok = g[g.ok]
        r = int((ok.tokens.fillna(0) > 0).sum())
        unknown = n - r - int((ok.tokens == 0).sum())  # missing count or no completed call
        thr = int(np.ceil(0.95 * n))
        status = "on" if r >= thr else "undecidable" if r + unknown >= thr else "mostly on"
        out.append(
            {"model": m, "block": block, "planned": n, "reasoned": r, "unknown": unknown, "status": status}
        )
    return pd.DataFrame(out)


def logit(p: float, n: int) -> float:
    p = min(max(p, 0.5 / n), 1 - 0.5 / n)
    return float(np.log(p / (1 - p)))


def fam_acc(d: pd.DataFrame) -> float:
    """Accuracy with families weighted equally (items within family, draws within item)."""
    return d.groupby(["family", "id"]).correct.mean().groupby("family").mean().mean()


class Sample:
    """One bootstrap resample: multiplicities of outcome instances and plain items (identity = the point estimate)."""

    def __init__(self, pairs: pd.DataFrame, plain: list[str], hard: list[str], rng=None, rng_hard=None):
        self.hard_w = {i: 1 for i in hard}
        if rng_hard is not None:  # own stream, so adding A2b left the A1 and A2 resamples unchanged
            self.hard_w = {}
            for i in rng_hard.choice(np.array(hard), len(hard)):
                self.hard_w[i] = self.hard_w.get(i, 0) + 1
        if rng is None:
            self.pair_w = {p: 1 for p in pairs.pair}
            self.plain_w = {i: 1 for i in plain}
            return
        self.pair_w, self.plain_w = {}, {}
        for _, g in pairs.groupby("family"):
            for p in rng.choice(g.pair.to_numpy(), len(g)):
                self.pair_w[p] = self.pair_w.get(p, 0) + 1
        for i in rng.choice(np.array(plain), len(plain)):
            self.plain_w[i] = self.plain_w.get(i, 0) + 1

    def outcome(self, d: pd.DataFrame) -> pd.DataFrame:
        d = d[d.pair.isin(self.pair_w)]
        return d.loc[d.index.repeat(d.pair.map(self.pair_w))].assign(
            id=lambda x: x.id + "#" + x.groupby(level=0).cumcount().astype(str)
        )

    def plain(self, d: pd.DataFrame) -> pd.DataFrame:
        return d[d.id.isin(self.plain_w)].assign(w=lambda x: x.id.map(self.plain_w))

    def hard(self, d: pd.DataFrame) -> pd.DataFrame:
        return d[d.id.isin(self.hard_w)].assign(w=lambda x: x.id.map(self.hard_w))


def stats(df: pd.DataFrame, m: str, s: Sample) -> dict:
    """Point quantities for one model under one resample."""
    o, p = (
        df[(df.model == m) & (df.block == "outcome") & df.ok],
        df[(df.model == m) & (df.block == "plain") & df.ok],
    )
    o = s.outcome(o)
    res = {}
    for edit in ("trap", "control"):
        off, on = o[(o.edit == edit) & (o.arm == "off")], o[(o.edit == edit) & (o.arm == "on")]
        if len(off) and len(on):
            res[f"{edit}_off"], res[f"{edit}_on"] = fam_acc(off), fam_acc(on)
            res[f"{edit}_gain"] = logit(res[f"{edit}_on"], len(on)) - logit(res[f"{edit}_off"], len(off))
        steps = o[(o.edit == edit) & (o.arm == "off_steps")]
        if len(steps):
            res[f"{edit}_steps"] = fam_acc(steps)
    item = lambda d: (
        (d.groupby("id").correct.mean() * d.groupby("id").w.first()).sum() / d.groupby("id").w.first().sum()
    )
    h = s.hard(df[(df.model == m) & (df.block == "hard") & df.ok])
    if len(h[h.arm == "off"]) and len(h[h.arm == "on"]):
        res["hard_off"], res["hard_on"] = item(h[h.arm == "off"]), item(h[h.arm == "on"])
    p = s.plain(p)
    if len(p):
        res["plain_off"], res["plain_on"] = item(p[p.arm == "off"]), item(p[p.arm == "on"])
        d1 = p[(p.arm == "off") & (p.rep == 0)].groupby("id").agg(c=("correct", "mean"), w=("w", "first"))
        q, pt = np.average(d1.c, weights=d1.w), res.get("trap_off")
        if pt is not None and (0 < q < 1 or np.isclose(q, pt)):
            mw = d1.w * np.where(d1.c == 1, pt / q if q else 0, (1 - pt) / (1 - q) if q < 1 else 0)
            mw = mw[mw > 0]
            ev = lambda d: np.average(d.groupby("id").correct.mean().reindex(mw.index), weights=mw)
            off2, on = p[(p.arm == "off") & (p.rep == 1)], p[p.arm == "on"]
            if len(off2) and len(on):
                res["matched_off"], res["matched_on"] = ev(off2), ev(on)
                n = int(d1.w.sum())
                res["matched_gain"] = logit(res["matched_on"], 2 * n) - logit(res["matched_off"], n)
                if "trap_gain" in res:
                    res["A1"] = res["trap_gain"] - res["matched_gain"]
    return res


def resamples(df: pd.DataFrame) -> list[Sample]:
    pairs = df[df.block == "outcome"].drop_duplicates("pair")[["family", "pair"]]
    plain = sorted(df[df.block == "plain"].id.unique())
    hard = sorted(df[df.block == "hard"].id.unique())
    rng, rng_hard = np.random.default_rng(SEED), np.random.default_rng(SEED + 1)
    return [Sample(pairs, plain, hard)] + [Sample(pairs, plain, hard, rng, rng_hard if hard else None) for _ in range(BOOT)]


def a2(per: dict, on_ok: set, cap: str = "plain", tag: str = "A2") -> dict:
    """Fit on off points (x = accuracy on the `cap` set); residuals for qualifying on points inside the off range
    (and leave-one-model-out); plus their mean over models."""
    pts = {m: r for m, r in per.items() if {f"{cap}_off", "trap_off"} <= r.keys()}
    if len(pts) < 3:
        return {}
    x = np.array([r[f"{cap}_off"] for r in pts.values()])
    y = np.array([1 - r["trap_off"] for r in pts.values()])
    out = {}
    for i, (m, r) in enumerate(pts.items()):
        if m not in on_ok or f"{cap}_on" not in r or "trap_on" not in r:
            continue
        xo, yo = r[f"{cap}_on"], 1 - r["trap_on"]
        if (
            not x.min() <= xo <= x.max()
        ):  # A2 untested for this model; record how far outside the off range it lies
            out[f"{m}|{tag}_outside_by"] = xo - x.max() if xo > x.max() else xo - x.min()
            continue
        b, a = np.polyfit(x, y, 1)
        keep = np.arange(len(x)) != i
        bl, al = np.polyfit(x[keep], y[keep], 1)
        out[f"{m}|{tag}_resid"], out[f"{m}|{tag}_resid_loo"] = yo - (a + b * xo), yo - (al + bl * xo)
    res = [v for k, v in out.items() if k.endswith("_resid")]
    if res:
        out[f"inside|{tag}_resid_mean"], out[f"inside|{tag}_models"] = float(np.mean(res)), len(res)
    return out


def analyse(df: pd.DataFrame, fo: pd.DataFrame) -> dict[str, pd.DataFrame]:
    models = [m for m in ALWAYS + CHOOSERS if m in set(df.model)]
    qualifies = lambda blocks: {m for m, g in fo.groupby("model")
                                if all((g[g.block == b].status == "on").any() for b in blocks)}  # fmt: skip
    on_ok, on_ok_hard = qualifies(["outcome", "plain"]), qualifies(["outcome", "hard"])
    runs = []
    for s in resamples(df):
        per = {m: stats(df, m, s) for m in models}
        flat = {f"{m}|{k}": v for m, r in per.items() for k, v in r.items()}
        a1 = [per[m]["A1"] for m in ALWAYS if "A1" in per.get(m, {})]
        flat["always|A1"], flat["always|A1_models"] = (
            (np.mean(a1) if a1 else np.nan),
            len(a1),
        )  # unmatched models drop out
        flat |= a2(per, on_ok) | a2(per, on_ok_hard, "hard", "A2b")
        runs.append(flat)
    t = pd.DataFrame(runs)
    est, lo, hi = t.iloc[0], t.iloc[1:].quantile(0.025), t.iloc[1:].quantile(0.975)
    long = pd.DataFrame({"estimate": est, "lo": lo, "hi": hi})
    long[["model", "stat"]] = long.index.to_series().str.split("|", expand=True)
    tab = lambda keys: long[long.stat.isin(keys)].pivot(
        index="model", columns="stat", values=["estimate", "lo", "hi"]
    )
    a1 = long[long.stat.isin(["A1", "A1_models", "trap_gain", "matched_gain", "control_gain"])].reset_index(
        drop=True
    )
    a1["supports"] = np.where(a1.stat == "A1", a1.lo > 0, None)
    acc = long[long.stat.str.match(r"(trap|control|plain|matched|hard)_(off|on|steps)$")][
        ["model", "stat", "estimate"]
    ]
    a4 = long[long.stat.isin(["trap_steps", "trap_on"])][["model", "stat", "estimate", "lo", "hi"]]
    return {"a1": a1[["model", "stat", "estimate", "lo", "hi", "supports"]],
            "a2": long[long.stat.str.startswith("A2_")][["model", "stat", "estimate", "lo", "hi"]].reset_index(drop=True),
            "a2b": long[long.stat.str.startswith("A2b")][["model", "stat", "estimate", "lo", "hi"]].reset_index(drop=True),
            "accuracy": acc.pivot(index="model", columns="stat", values="estimate").reset_index(),
            "a4": a4.pivot(index="model", columns="stat", values="estimate").reset_index()}  # fmt: skip


def a3(df: pd.DataFrame) -> pd.DataFrame:
    t = df[(df.block == "outcome") & (df.edit == "trap") & df.ok]
    g = t.groupby(["model", "arm"])
    out = pd.DataFrame({"calls": g.size(), "wrong": g.correct.apply(lambda s: int((s == 0).sum())),
                        "method": g.kind.apply(lambda s: int((s == "method").sum())),
                        "shortcut": g.kind.apply(lambda s: int((s == "shortcut").sum())),
                        "unparsed": g.kind.apply(lambda s: int((s == "unparsed").sum()))})  # fmt: skip
    out["per_call"] = out.method / out.calls  # method answers per trap call
    # method answers per wrong trap answer; undefined ("--") without wrong answers
    out["per_wrong"] = (out.method / out.wrong).round(3).astype(object).where(out.wrong > 0, "--")
    return out.reset_index()


def checks(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["model", "block", "arm"])
    return pd.DataFrame({
        "draws": g.size(), "failed": g.ok.apply(lambda s: int((~s).sum())),
        "reasoned": g.tokens.apply(lambda t: int((t.fillna(0) > 0).sum())),
        "zero": g.tokens.apply(lambda t: int((t == 0).sum())), "missing": g.tokens.apply(lambda t: int(t.isna().sum())),
        "unparsed": g.kind.apply(lambda s: int((s == "unparsed").sum())),
        "long_answer_only": df.assign(l=(df.words > 5) & (df.arm != "off_steps")).groupby(["model", "block", "arm"]).l.sum(),
        "median_tokens": g.tokens.median(),
    }).reset_index()  # fmt: skip


def write(name: str, t: pd.DataFrame, caption: str, size: str = "small") -> None:
    print(f"== {name}\n{t.round(3).to_string(index=False)}\n")
    Path(f"paper/generated/crt-a-{name}.tex").write_text(to_latex(t.round(3), caption, f"tab:crt-a-{name}", size))


def wording(df: pd.DataFrame) -> pd.DataFrame:
    """Descriptive, post hoc: trap accuracy by wording and arm (families equal weight), famous minus neutral."""
    t = df[(df.block == "outcome") & (df.edit == "trap") & df.ok & df.arm.isin(["off", "on"])]
    acc = t.groupby(["model", "arm", "wording"]).apply(fam_acc).unstack("wording")
    acc["famous_minus_neutral"] = acc["famous"] - acc["neutral"]
    return acc.reset_index()


def hard_pilot() -> pd.DataFrame:
    """A2b calibration pilot (concept §8): accuracy, and replies longer than 5 words with their accuracy, per model."""
    rows = load_run(Path("runs/crt-a-hard-pilot2"))
    d = scored(rows)
    d["correct"] = (d.kind == "correct").astype(float)
    g = d[d.ok].groupby("model")
    d = d[d.ok].assign(long=lambda x: x.words > 5)
    out = pd.DataFrame({"calls": g.size(), "accuracy": g.correct.mean(),
                         "long_replies": g.words.apply(lambda w: int((w > 5).sum())),
                         "long_right": d[d.long].groupby("model").correct.sum(),
                         "short_right": d[~d.long].groupby("model").correct.sum(),
                         # written-out working: at least three arithmetic steps such as "+ 258" or "= 700"
                         # long replies that write out working: at least three arithmetic steps ("+ 258", "= 700")
                         "long_calc": d[d.long].groupby("model").text.apply(
                             lambda t: int(t.str.count(r"[=+×÷*-]\s*\d").ge(3).sum()))}).fillna(0)  # fmt: skip
    out = out.astype({"long_right": int, "short_right": int, "long_calc": int}).reset_index()
    out.insert(1, "setting", ["on" if m.startswith("openrouter") else "off" for m in out.model])
    out["model"] = [m.split(":")[-1].split("/")[-1] for m in out.model]  # bare model id, so the table fits
    return out


def pct(x: float) -> str:
    return f"{round(100 * x, 1) + 0:.1f}"  # round, then + 0, so -0.0 prints as 0.0


def macros(df: pd.DataFrame, res: dict, pilot: pd.DataFrame) -> dict[str, str]:
    """Numbers the paper quotes in prose (paper/generated/crt-a-numbers.tex)."""
    m = {}
    for tag, key in (("", "a1"), ("NoSheep", "a1-nosheep")):
        a = res[key].set_index(["model", "stat"]).loc[("always", "A1")]
        m |= {f"aAone{tag}": f"{a.estimate:.2f}", f"aAone{tag}Lo": f"{a.lo:.2f}", f"aAone{tag}Hi": f"{a.hi:.2f}"}
    acc = res["accuracy"].set_index("model")
    for model, n in {"mistral-small-4": "Mistral", "haiku-4-5": "Haiku", "gpt-5.6-luna": "LunaFive",
                     "gpt-5.6-terra": "Terra"}.items():  # fmt: skip
        m[f"aTrapOn{n}"], m[f"aMatchedOn{n}"] = pct(acc.loc[model, "trap_on"]), pct(acc.loc[model, "matched_on"])
    m["aPlainOnMin"] = pct(acc.plain_on.min())
    out = res["a2"][res["a2"].stat == "A2_outside_by"].estimate
    m["aOutsideMin"], m["aOutsideMax"] = pct(out.min()), pct(out.max())  # percentage points
    # sensitivity (not pre-registered): A1 with one common bound n = 48 on every logit, for the ceiling models
    for model, n in {"deepseek-v4.1-flash": "Deepseek", "qwen3.8-27b": "Qwen"}.items():
        r = acc.loc[model]
        gain = lambda on, off: logit(on, 48) - logit(off, 48)
        m[f"aAoneCommon{n}"] = f"{gain(r.trap_on, r.trap_off) - gain(r.matched_on, r.matched_off):.2f}"
    for model, n in {"granite-4.2-8b": "Granite"}.items():
        m[f"aTrapOff{n}"], m[f"aMatchedOff{n}"] = pct(acc.loc[model, "trap_off"]), pct(acc.loc[model, "matched_off"])
    m["aPlainOffMax"] = pct(acc.plain_off.max())
    t = res["a3"][res["a3"].arm == "on"]
    m["aOnMethod"], m["aOnWrong"] = str(int(t.method.sum())), str(int(t.wrong.sum()))
    g = df[(df.model == "granite-4.2-8b") & (df.block == "plain") & (df.arm == "off") & df.ok]
    long = g.words > 5
    m["aGraniteLongRight"], m["aGraniteLong"] = str(int(g.correct[long].sum())), str(int(long.sum()))
    m["aGraniteShortRight"], m["aGraniteShort"] = str(int(g.correct[~long].sum())), str(int((~long).sum()))
    fo = res["forced-on"].set_index(["model", "block"])
    for model, n in {"gpt-5.6-luna": "LunaFive", "gpt-5.6-terra": "Terra", "sonnet-4-6": "Sonnet", "gpt-6-luna": "LunaSix"}.items():
        m[f"aMaxReasoned{n}"] = str(int(fo.loc[(model, "outcome"), "reasoned"]))
    sp = pilot.set_index("model")
    m["aPilotSonnetCalc"] = str(int(sp.loc["claude-sonnet-4-6", "long_calc"]))
    m["aPilotSonnetLongRight"] = str(int(sp.loc["claude-sonnet-4-6", "long_right"]))
    m["aPilotSonnetShortRight"] = str(int(sp.loc["claude-sonnet-4-6", "short_right"]))
    m["aPilotSonnetShort"] = str(int(sp.loc["claude-sonnet-4-6", "calls"] - sp.loc["claude-sonnet-4-6", "long_replies"]))
    t = res["a3"]
    six = t[t.model.isin(ALWAYS)]
    m["aOnMethodSix"], m["aOnWrongSix"] = str(int(six[six.arm == "on"].method.sum())), str(int(six[six.arm == "on"].wrong.sum()))
    m["aTrapCallsSix"] = str(int(six[six.arm == "on"].calls.sum()))
    m["aOffMethodSix"] = str(int(six[six.arm == "off"].method.sum()))
    for model, n in {"gpt-5.6-luna": "LunaFive", "gpt-5.6-terra": "Terra", "sonnet-4-6": "Sonnet", "gpt-6-luna": "LunaSix"}.items():
        m[f"aMaxPlainReasoned{n}"] = str(int(fo.loc[(model, "plain"), "reasoned"]))
    m["aCalls"] = f"{int((~((df.block == 'outcome') & df.model.isin(CHOOSERS))).sum()):,}"
    gains = []
    for model in ALWAYS:  # sensitivity (not pre-registered): six-model mean A1 with one common bound n = 48
        r = acc.loc[model]
        g = lambda on, off: logit(on, 48) - logit(off, 48)
        gains.append(g(r.trap_on, r.trap_off) - g(r.matched_on, r.matched_off))
    m["aAoneCommonMean"] = f"{np.mean(gains):.2f}"
    for arm, n in (("off", "Off"), ("on", "On")):
        x = t[(t.arm == arm) & t.model.isin(["granite-4.2-8b", "nemotron-3.5-lightning", "mistral-small-4", "qwen3.8-27b", "deepseek-v4.1-flash", "haiku-4-5"])]
        m[f"aMethodPerCall{n}"] = pct(x.method.sum() / x.calls.sum())
    w = res["wording"]
    for arm, n in (("off", "Off"), ("on", "On")):
        x = w[w.arm == arm].famous_minus_neutral
        m[f"aWording{n}Mean"], m[f"aWording{n}Min"], m[f"aWording{n}Max"] = pct(x.mean()), pct(x.min()), pct(x.max())
        m[f"aWording{n}Pos"] = str(int((x.round(3) > 0).sum()))  # models better on famous wording
    m["aWordingModels"] = str(w.model.nunique())
    pl = pilot.set_index("model")
    m["aPilotTerraOff"] = pct(pl.loc["gpt-5.6-terra", "accuracy"])
    m["aPilotSonnetOff"] = pct(pl.loc["claude-sonnet-4-6", "accuracy"])
    m["aPilotSonnetLong"] = str(int(pl.loc["claude-sonnet-4-6", "long_replies"]))
    m["aPilotOnMin"] = pct(pl[pl.setting == "on"].accuracy.min())
    return m


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    df = load()
    write("checks", checks(df), "Study 2 manipulation checks per model, block and arm.")
    fo = forced_on(df)
    res = {"forced-on": fo}
    write("forced-on", fo, "Study 2 forced-on rule per model and block (95% of planned on draws reasoned).")
    if "--checks" in sys.argv:
        sys.exit(0)
    for tag, d in [("", df), ("-nosheep", df[df.family != "sheep"])]:
        r = analyse(d, fo)
        res[f"a1{tag}"], res[f"accuracy{tag}"], res[f"a2{tag}"], res[f"a3{tag}"] = r["a1"], r["accuracy"], r["a2"], a3(d)
        write(f"a1{tag}", r["a1"], f"A1: on minus off log-odds gain, traps vs matched plain items{tag}.")
        write(f"a2{tag}", r["a2"], f"A2: trap error of on points relative to the off-point capability line{tag}.")
        if len(r["a2b"]):
            write(f"a2b{tag}", r["a2b"], f"A2b: trap error of on points relative to the off-point line on the hard plain set{tag}.")
        write(f"accuracy{tag}", r["accuracy"], f"Study 2 accuracy per model and arm{tag}.")
        write(f"a4{tag}", r["a4"].astype(object).where(r["a4"].notna(), "not run"), f"A4: trap accuracy, off with visible steps vs hidden reasoning on{tag}.")
        write(f"a3{tag}", res[f"a3{tag}"], f"A3: method answers on traps per call and per wrong answer{tag}.", "footnotesize")
    res["wording"] = wording(df)
    write("wording", res["wording"], "Trap accuracy by wording, reasoning off and enabled (post hoc, descriptive).")
    pilot = hard_pilot()
    write("hard-pilot", pilot, "A2b pilot on the hard plain set: accuracy, answer-only replies longer than 5 words, and correct replies among long and short ones.", "footnotesize")
    Path("paper/generated/crt-a-numbers.tex").write_text(to_macros(macros(df, res, pilot)))
