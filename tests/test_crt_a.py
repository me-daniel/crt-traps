"""Study A analysis on fake rows: forced-on rule and the A1 trap vs matched-plain gain."""

import importlib.util
import math

import pytest

spec = importlib.util.spec_from_file_location("crt_a", "experiments/crt-a.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def row(cond, arm, rep, right, tokens):
    c = {"answer": "5", "arm": arm, **cond}
    return {"key": f"{c['id']}{arm}{rep}", "model": "x", "condition": c, "rep": rep,
            "text": f"Answer: {5 if right else 7}", "thinking_tokens": tokens, "usage": {}}  # fmt: skip


def test_forced_on_and_a1():
    out, plain = [], []
    for fam in ("bat_ball", "snail", "sheep"):
        for k in (1, 2):
            for edit in ("trap", "control"):
                for w in ("famous", "neutral"):
                    c = {
                        "id": f"{fam}{k}{edit}{w}",
                        "pair": f"{fam}{k}",
                        "family": fam,
                        "edit": edit,
                        "wording": w,
                    }
                    out.append(row(c, "off", 0, edit == "control" or k == 1, 0))  # traps off: half right
                    out.append(row(c, "on", 0, True, 50))
    for i in range(4):
        c = {"id": f"p{i}", "family": "plain", "edit": "plain"}
        plain += [row(c, "off", r, i < 2, 0) for r in (0, 1)]  # off: 2 of 4 right, both draws
        plain += [row(c, "on", r, i < 3, 50) for r in (0, 1)]  # on: 3 of 4
    m = "granite-4.2-8b"
    df = a.pd.concat([a.frame(out, m, "outcome"), a.frame(plain, m, "plain")], ignore_index=True)
    a.PLANNED = {"outcome": {m: 24}, "plain": 8}
    assert set(a.forced_on(df).status) == {"on"}
    a.BOOT = 20
    r = a.analyse(df, a.forced_on(df))["a1"].set_index(["model", "stat"])
    # trap: off 0.5 -> on 1 (clipped at 1 - 0.5/12); matched plain: off 0.5 -> on 0.75
    assert r.loc[(m, "A1"), "estimate"] == pytest.approx(math.log(23) - math.log(3))


def test_a2_residual_inside_and_outside_range():
    # off line through (0.2, 0.8) and (0.6, 0.4): y = 1 - x; on point at x=0.4 with error 0.3 -> residual -0.3
    per = {
        "p": {"hard_off": 0.2, "trap_off": 0.2},
        "q": {"hard_off": 0.6, "trap_off": 0.6},
        "m": {"hard_off": 0.4, "trap_off": 0.4, "hard_on": 0.4, "trap_on": 0.7},
        "n": {"hard_off": 0.3, "trap_off": 0.3, "hard_on": 0.9, "trap_on": 1.0},
    }
    out = a.a2(per, {"m", "n"}, "hard", "A2b")
    assert out["m|A2b_resid"] == pytest.approx(0.3 - (1 - 0.4), abs=0.05)
    assert out["n|A2b_outside_by"] == pytest.approx(0.3)
    assert out["inside|A2b_models"] == 1
