import json

import pytest

from harness import models
from harness.models import Reply
from harness.report import classify, summarize, to_latex
from harness.runner import experiment_jobs, load, load_run, plan, run_jobs

CFG = {
    "models": ["fake:a", "fake:b"],
    "prompt": "Q: {q}",
    "conditions": [{"q": "2+3", "answer": "5"}],
    "repeats": 2,
}


def test_resume_skips_done_and_retries_failed(tmp_path):
    calls = []

    def flaky(model, prompt, system=None, **_):
        calls.append(model)
        if model == "fake:b" and calls.count("fake:b") <= 2:
            raise RuntimeError("rate limited")
        return Reply("Answer: 5" if model == "fake:a" else "Answer: 4", model)

    out = tmp_path / "results.jsonl"
    rows = run_jobs(experiment_jobs(CFG), out, workers=1, ask=flaky)
    assert sum("error" in r for r in rows) == 2
    rows = run_jobs(experiment_jobs(CFG), out, workers=1, ask=flaky)
    assert len(calls) == 6 and not any("error" in r for r in rows)  # only the 2 failures re-ran
    df = summarize(load(out))  # the log still holds the 2 failed attempts; only the retries count
    assert df.set_index("model")[["n", "failed", "acc"]].to_dict() == {
        "n": {"fake:a": 2, "fake:b": 2},
        "failed": {"fake:a": 0, "fake:b": 0},
        "acc": {"fake:a": 1.0, "fake:b": 0.0},
    }
    assert r"\toprule" in to_latex(df, "x", "tab:x")


def test_cli_backends_reject_sampling_params():
    with pytest.raises(ValueError, match="API backend"):
        models.ask("claude:haiku", "hi", temperature=0.5)


def test_factorial_conditions_scored_by_final_answer(tmp_path):
    cfg = {
        "models": ["fake:m"],
        "prompt": "{q} {instruction}",
        "conditions": {
            "item": [{"q": "ball?", "answer": 5, "lure": 10}, {"q": "lid?", "answer": 125, "lure": 250}],
            "mode": [
                {"mode": "fast", "instruction": "Answer only."},
                {"mode": "deliberate", "instruction": "Think."},
            ],
        },
    }
    replies = {  # deliberate replies mention the lure before settling on the answer
        "ball? Answer only.": "Answer: 10",
        "ball? Think.": "Not 10 cents.\nAnswer: 5",
        "lid? Answer only.": "Answer: 125 grams",
        "lid? Think.": "1,250 - 1,000 = 250, halved.\nAnswer: 125, not 250",  # the committed answer comes first
    }
    jobs = experiment_jobs(cfg)
    assert len(jobs) == 4
    rows = run_jobs(jobs, tmp_path / "r.jsonl", workers=1, ask=lambda m, p, s=None, **_: Reply(replies[p], m))
    df = summarize(rows, by=("mode",)).set_index("mode")
    assert df.acc.to_dict() == {"deliberate": 1.0, "fast": 0.5}
    assert df.lure.to_dict() == {"deliberate": 0.0, "fast": 0.5}


def test_condition_params_and_recall_scoring(tmp_path):
    cfg = {
        "models": ["claude:x", "codex:y"],
        "prompt": "{q}",
        "params": {"claude": {"thinking": False}, "codex": {"effort": "none"}},
        "conditions": {
            "item": [
                {"q": "trap", "answer": 22, "lure": 10, "recalled": 5},
                {"q": "plain", "answer": ["second", "2nd"], "lure": "first"},  # no recalled answer
            ],
            "mode": [
                {"mode": "fast"},
                {"mode": "on", "params": {"claude": {"thinking": True}, "codex": {"effort": "low"}}},
            ],
        },
    }
    jobs = experiment_jobs(cfg)
    assert {(j["model"], j["condition"]["mode"]): j["params"] for j in jobs if j["prompt"] == "trap"} == {
        ("claude:x", "fast"): {"thinking": False},
        ("claude:x", "on"): {"thinking": True},  # the condition overrides the config
        ("codex:y", "fast"): {"effort": "none"},
        ("codex:y", "on"): {"effort": "low"},
    }
    replies = {"trap": "Answer: 5", "plain": "Answer: 2nd place"}
    rows = run_jobs(jobs, tmp_path / "r.jsonl", workers=1, ask=lambda m, p, s=None, **_: Reply(replies[p], m))
    df = summarize(rows).set_index("model")
    assert df.loc["claude:x", ["acc", "lure", "recall", "words"]].to_dict() == {
        "acc": 0.5,  # "2nd" counts as "second"
        "lure": 0.0,
        "recall": 1.0,  # scored only on the item that has a recalled answer
        "words": 2.5,
    }


def test_identical_calls_are_rejected():
    cfg = {
        "models": ["opencode:m"],
        "prompt": "{q}",
        "conditions": [{"q": "a", "mode": "fast"}, {"q": "a", "mode": "on"}],
    }
    with pytest.raises(ValueError, match="identical calls"):
        experiment_jobs(cfg)


def test_claude_thinking_off_fails_loudly_if_model_still_thinks(monkeypatch):
    seen = {}

    def fake_cli(cmd, strip_env=(), extra_env=None):
        seen["env"] = extra_env
        usage = {"output_tokens_details": {"thinking_tokens": 40}}
        return json.dumps({"result": "B", "usage": usage, "modelUsage": {"claude-haiku-5-5": {}}})

    monkeypatch.setattr(models, "_cli", fake_cli)
    assert models.ask("claude:haiku", "hi").thinking_tokens == 40
    with pytest.raises(RuntimeError, match="40 thinking tokens"):
        models.ask("claude:haiku", "hi", thinking=False)
    assert seen["env"] == {"MAX_THINKING_TOKENS": "0"}


BALL = {"answer": 22, "lure": 10, "recalled": 5}


@pytest.mark.parametrize(
    ("cond", "text", "kind"),
    [
        (BALL, "Answer: 22", "correct"),
        (BALL, "**Answer: 5**", "recalled"),
        (BALL, "Answer: 10 cents, not 22", "lure"),  # the first value committed to wins
        (BALL, "Answer: 22\nWrong answer: 10", "correct"),  # 'Wrong answer:' is not a marker
        (BALL, "So the ball is 22 cents.", "unparsed"),  # no marker: never guessed from the prose
        (BALL, "Answer: -22", "other"),
        (BALL, "Answer: $22.00", "correct"),
        ({"answer": 125, "lure": 250}, "Answer: 1,250", "other"),
        ({"answer": 0.2}, "Answer: $0.20", "correct"),
        ({"answer": ["second", "2nd"], "lure": "first"}, "Final answer: 2nd place", "correct"),
    ],
)
def test_classify_scores_the_committed_answer(cond, text, kind):
    assert classify(cond, text) == kind


def test_off_arms_require_a_reported_zero(monkeypatch):
    monkeypatch.setattr(models, "_cli", lambda *a, **k: json.dumps({"result": "B", "usage": {}}))
    with pytest.raises(RuntimeError, match="reported None"):  # no count is not a zero
        models.ask("claude:claude-haiku-4-5", "hi", thinking=False)
    events = [{"type": "item.completed", "item": {"type": "agent_message", "text": "B"}}]
    monkeypatch.setattr(models, "_cli", lambda *a, **k: "\n".join(map(json.dumps, events)))
    with pytest.raises(RuntimeError, match="no completed turn"):
        models.ask("codex:gpt-6-sol", "hi", effort="none")
    events.append({"type": "turn.completed", "usage": {"reasoning_output_tokens": 40}})
    with pytest.raises(RuntimeError, match="40 reasoning tokens"):
        models.ask("codex:gpt-6-sol", "hi", effort="none")
    assert models.ask("codex:gpt-6-sol", "hi", effort="low").thinking_tokens == 40


def test_cli_child_env_drops_leaky_variables(monkeypatch):
    monkeypatch.setenv("MAX_THINKING_TOKENS", "0")
    monkeypatch.setenv("CLAUDE_CODE_X", "1")
    out = models._cli(["env"], strip_env=("CLAUDE_CODE_", "MAX_THINKING_TOKENS"), extra_env={"KEEP": "1"})
    assert "MAX_THINKING_TOKENS" not in out and "CLAUDE_CODE_X" not in out and "KEEP=1" in out


def test_plan_pins_calls_and_rescores_with_the_current_rubric(tmp_path):
    cfg = {"models": ["fake:m"], "prompt": "{q}", "conditions": [{"q": "ball?", "answer": 5}]}
    out = tmp_path / "run"
    run_jobs(plan(cfg, out), out / "results.jsonl", ask=lambda m, p, s=None, **_: Reply("Answer: 50", m))
    assert summarize(load_run(out)).acc.tolist() == [0.0]
    cfg["conditions"][0]["answer"] = 50  # a corrected answer key: same call, rescored
    plan(cfg, out)
    assert summarize(load_run(out)).acc.tolist() == [1.0]
    cfg["conditions"][0]["q"] = "ball??"  # a changed prompt is a different run
    with pytest.raises(ValueError, match="new name"):
        plan(cfg, out)
    assert (out / "invocations.jsonl").read_text().count("\n") == 2


def test_load_skips_a_truncated_last_line(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_text('{"key": "a"}\n{"key": "b", "te')
    assert load(p) == [{"key": "a"}]
    p.write_text('{"key": "a"\n{"key": "b"}\n')
    with pytest.raises(json.JSONDecodeError):
        load(p)


def test_openrouter_thinking_off_is_sent_and_verified(monkeypatch):
    import sys
    import types

    from openai.types.chat import ChatCompletion

    sent, reply = {}, {"reasoning_tokens": 0, "reasoning": None}

    def create(**kw):
        sent.update(kw)
        msg = {"role": "assistant", "content": "Answer: 11", "reasoning": reply["reasoning"]}
        usage = {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12,
                 "completion_tokens_details": {"reasoning_tokens": reply["reasoning_tokens"]}}  # fmt: skip
        return ChatCompletion.model_validate({"id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "provider": "Host", "usage": usage, "choices": [{"index": 0, "finish_reason": "stop", "message": msg}]})  # fmt: skip

    fake = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=lambda **_: fake))
    r = models.ask("openrouter:q/m", "hi", thinking=False)
    assert sent["extra_body"] == {"reasoning": {"enabled": False}} and r.thinking_tokens == 0
    assert r.resolved == "m@Host"
    reply.update(reasoning_tokens=40)
    with pytest.raises(RuntimeError, match="40 reasoning tokens"):
        models.ask("openrouter:q/m", "hi", thinking=False)
    reply.update(reasoning_tokens=None)  # no count is not a zero
    with pytest.raises(RuntimeError, match="None reasoning tokens"):
        models.ask("openrouter:q/m", "hi", thinking=False)
    reply.update(reasoning_tokens=0, reasoning="let me think")  # reasoning text without a count
    with pytest.raises(RuntimeError, match="text: True"):
        models.ask("openrouter:q/m", "hi", thinking=False)
    with pytest.raises(ValueError, match="openrouter only"):
        models.ask("google:g", "hi", thinking=False)


def test_cli_runs_one_batch_of_a_pinned_plan(tmp_path, monkeypatch):
    import sys

    import yaml

    from harness import cli

    cfg = {"name": "b", "models": ["fake:m"], "prompt": "{q}",
           "conditions": [{"q": "a", "answer": 1, "batch": 1}, {"q": "b", "answer": 1, "batch": 2}]}  # fmt: skip
    (tmp_path / "b.yaml").write_text(yaml.safe_dump(cfg))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(models, "ask", lambda m, p, s=None, **_: Reply("Answer: 1", m))
    monkeypatch.setattr(sys, "argv", ["crt", "run", "b.yaml", "--batch", "1"])
    cli.main()
    assert [r["prompt"] for r in load(tmp_path / "runs/b/results.jsonl")] == ["a"]
    assert len(json.loads((tmp_path / "runs/b/manifest.json").read_text())["keys"]) == 2  # the whole plan


def test_params_per_model_and_a_plan_may_shrink(tmp_path):
    cfg = {"models": ["openrouter:a", "openrouter:b"], "prompt": "{q}", "conditions": [{"q": "x", "answer": 1}],
           "params": {"openrouter": {"thinking": False}, "openrouter:b": {"extra_body": {"provider": {"only": ["h"]}}}}}  # fmt: skip
    assert [j["params"] for j in experiment_jobs(cfg)] == [
        {"thinking": False},
        {"thinking": False, "extra_body": {"provider": {"only": ["h"]}}},
    ]
    out = tmp_path / "run"
    run_jobs(plan(cfg, out), out / "results.jsonl", ask=lambda m, p, s=None, **_: Reply("Answer: 1", m))
    plan(cfg | {"models": ["openrouter:a"]}, out)  # dropping a model is allowed
    assert [r["model"] for r in load_run(out)] == ["openrouter:a"]
    assert len(load(out / "results.jsonl")) == 2  # its rows stay on disk
    with pytest.raises(ValueError, match="new name"):  # adding one back is a new call
        plan(cfg | {"models": ["openrouter:a", "openrouter:c"]}, out)


def test_limits_cap_concurrent_calls_per_model(tmp_path):
    import threading
    import time

    now, peak, lock = {"g": 0, "x": 0}, {"g": 0, "x": 0}, threading.Lock()

    def slow(model, prompt, system=None, **_):
        m = model.split(":")[1]
        with lock:
            now[m] += 1
            peak[m] = max(peak[m], now[m])
        time.sleep(0.05)
        with lock:
            now[m] -= 1
        return Reply("Answer: 1", model)

    cfg = {"models": ["fake:g", "fake:x"], "prompt": "{q}", "conditions": [{"q": str(i)} for i in range(8)]}
    run_jobs(experiment_jobs(cfg), tmp_path / "r.jsonl", workers=8, ask=slow, limits={"fake:g": 1})
    assert peak["g"] == 1 and peak["x"] > 1
