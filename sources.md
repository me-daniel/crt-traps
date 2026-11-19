# Sources

The paper's citation ledger, kept up to date with `/zoterofy`. One line per source:

`- [status] `citekey` id · Author Year, "Title" · for: the claim it supports`

The id is `doi:`, `arxiv:`, `isbn:` or `url:`. The statuses are:

- `[ ]` candidate.
- `[v]` verified: the id resolves, and its title, first author and year match this line.
- `[x]` in the Zotero collection, with the key pinned (`zotero:` gives the item).
- `[?]` doubtful, with the reason on the line. Never added.

`paper/refs.bib` comes only from Zotero (`make -C paper refs`).
The wider candidate pool from the literature search is `docs/citations-to-add.md`.

## Cognitive science

- [x] `frederick2005cognitive` doi:10.1257/089533005775196732 · Frederick 2005, "Cognitive Reflection and Decision Making" · for: the CRT and its three items (intro) · zotero:GZ6KF4FI
- [x] `kahneman2011thinking` isbn:9780374275631 · Kahneman 2011, "Thinking, Fast and Slow" · for: the dual-process account, popular statement (intro) · zotero:MUCRIR34
- [x] `evans2013dualprocess` doi:10.1177/1745691612460685 · Evans 2013, "Dual-Process Theories of Higher Cognition: Advancing the Debate" · for: Type 1 / Type 2 processing (intro) · zotero:M84E8J5U
- [x] `pennycook2015what` doi:10.1016/j.cogpsych.2015.05.001 · Pennycook 2015, "What Makes Us Think? A Three-Stage Dual-Process Model of Analytic Engagement" · for: conflict detection, then analytic engagement (intro) · zotero:C357KKF4
- [x] `thompson2011intuition` doi:10.1016/j.cogpsych.2011.06.001 · Thompson 2011, "Intuition, Reason, and Metacognition" · for: feeling of rightness predicts rethinking (intro) · zotero:WPN3XXWJ
- [x] `deneys2012bias` doi:10.1177/1745691611429354 · De Neys 2012, "Bias and Conflict: A Case for Logical Intuitions" · for: lure-givers still detect the conflict (intro, optional) · zotero:RHJ5K4SS
- [x] `deneys2019logic` doi:10.1177/0963721419855658 · De Neys 2019, "Logic, Fast and Slow: Advances in Dual-Process Theorizing" · for: short alternative to De Neys 2012 (optional) · zotero:2MBNVJE2

## LLMs on the CRT

- [x] `binz2025centaur` doi:10.1038/s41586-025-09215-4 · Binz 2025, "A foundation model to predict and capture human cognition" · for: running cognitive experiments with language models as participants (intro); the earlier refs.bib entry (no DOI) was not in this library; now added from the DOI record · zotero:K3TK3JWZ
- [x] `hagendorff2023humanlike` doi:10.1038/s43588-023-00527-x · Hagendorff 2023, "Human-like intuitive behavior and reasoning biases emerged in large language models but disappeared in ChatGPT" · for: CRT isomorphs on LLMs, lures in earlier models (intro) · zotero:7FM4H9TP
- [x] `binz2023using` doi:10.1073/pnas.2218523120 · Binz 2023, "Using cognitive psychology to understand GPT-3" · for: LLMs as participants on CRT items (intro) · zotero:UI3HKK5Z
- [x] `yax2024studying` doi:10.1038/s44271-024-00091-8 · Yax 2024, "Studying and improving reasoning in humans and machines" · for: modified CRT items because the famous ones are memorised (intro) · zotero:8PBV7NEJ
- [x] `yan2025recitation` doi:10.18653/v1/2025.ijcnlp-long.17 · Yan 2025, "Recitation over Reasoning: How Cutting-Edge Language Models Can Fail on Elementary School-Level Reasoning Problems?" · for: condition-changed familiar problems (intro) · zotero:QSZZU9M7
- [x] `xie2025grasp` arxiv:2410.14979 · Xie 2024, "Do Large Language Models Truly Grasp Mathematics? An Empirical Exploration From Cognitive Psychology" · for: principle-changed CRT items, closest precedent (intro); arXiv version, also CogSci 2025 · zotero:WPKSI2CJ

## Reasoning models

- [x] `fang2025thinkless` arxiv:2505.13379 · Fang 2025, "Thinkless: LLM Learns When to Think" · for: per-query choice of short or long reasoning (intro); NeurIPS 2025 · zotero:W3IDQFCP
- [x] `chen2025overthinking` arxiv:2412.21187 · Chen 2024, "Do NOT Think That Much for 2+3=? On the Overthinking of o1-Like LLMs" · for: overthinking on trivial questions (discussion); arXiv title, published at ICML 2025 as "...of Long Reasoning Models" · zotero:JSSIHGN2
- [x] `sui2025stop` arxiv:2503.16419 · Sui 2025, "Stop Overthinking: A Survey on Efficient Reasoning for Large Language Models" · for: overthinking and adaptive reasoning survey (discussion) · zotero:W5ZWVVR4
- [x] `wei2022chain` arxiv:2201.11903 · Wei 2022, "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models" · for: chain of thought (discussion); NeurIPS 2022 · zotero:KE8ZHW9V
- [x] `muennighoff2025s1` doi:10.18653/v1/2025.emnlp-main.1025 · Muennighoff 2025, "s1: Simple Test-Time Scaling" · for: reasoning length set from outside, budget forcing (discussion) · zotero:S2CIMCHJ
- [x] `turpin2023language` arxiv:2305.04388 · Turpin 2023, "Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting" · for: CoT text is not a transparent readout (intro); NeurIPS 2023 · zotero:TMCBKEVQ
- [x] `chen2025reasoning` arxiv:2505.05410 · Chen 2025, "Reasoning Models Don't Always Say What They Think" · for: the same caveat for reasoning models (intro) · zotero:VRR9CVP8
