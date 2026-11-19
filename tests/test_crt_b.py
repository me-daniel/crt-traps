"""Study B analysis on fake rows: allocation classes and the H1 trap - control contrast."""

import importlib.util

import pytest

spec = importlib.util.spec_from_file_location("crt_b", "experiments/crt-b.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def row(item, effort, tokens, out, text="Answer: 5"):
    c = {"id": f"{item['pair']}_{item['edit']}_{item['wording']}", "effort": effort, "answer": "5", **item}
    return {"key": f"{c['id']}{effort}{tokens}{out}", "model": "codex:x", "condition": c, "text": text,
            "usage": {"output_tokens": out}, "thinking_tokens": tokens, "question": "q"}  # fmt: skip


def test_allocation_classes_and_h1():
    rows = []
    for fam in ("bat_ball", "snail", "sheep"):
        for k in (1, 2):
            for w in ("famous", "neutral"):
                base = {"pair": f"b_{fam}_{k}", "family": fam, "wording": w}
                rows.append(row({**base, "edit": "trap"}, "high", 40, 50))  # reasoned
                rows.append(row({**base, "edit": "control"}, "high", 0, 8))  # skipped
    rows.append(row({"pair": "b_sheep_1", "family": "sheep", "wording": "famous", "edit": "control"}, "off", 0, 300))
    df = b.frame(rows).assign(arm="m")
    assert df.alloc.value_counts().to_dict() == {"reasoned": 12, "skipped": 12, "unknown": 1}
    im = b.item_means(df[df.effort == "high"], "reasoned")
    est = b.boot(b.h1_by_pair(im), "d", ["m"]).set_index("arm")
    assert est.loc["pooled", "estimate"] == pytest.approx(1.0)
    assert est.loc["pooled", "supports"]
