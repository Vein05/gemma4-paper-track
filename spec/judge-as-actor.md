# Spec: does Gemma stop rubber-stamping when it judges by running code instead of reading the diff?

Written 2026-11-03, before any judging run with a shell. Exploratory, one set (the held-out issues). Proposed in the
main session on 2026-11-03 after the fix list (`notes/fix-attempts-2026-11-03.md`) showed that every fix tried puts
the judge in a reading seat; none lets it act. Approved by the user for the lab A100 ("please update or make the
spec for it").

## Why

The paper measures the "is this patch done?" step as a reading step: the judge sees the issue and the diff and gives
0 to 100. In that seat Gemma 4 31B gives 100 to 52 of its 85 own failing held-out patches (61%), against 35% of other
writers' failing patches; leniency +16.6 [10.3, 23.1]. Every signal taken from the reading seat (written score, token
probability, hidden state, thinking mode, the agent's own reproduction script, a sibling, a jury) failed to separate
Gemma's failing from its passing patch on the same issue.

Two facts say the acting seat is the open question. Gemma solved 98 of 193 issues when it could act. And 17 of the 52
stamped failures break an existing test, while 11 of the 31 hand-coded defects are crashes, un-updated callers or
over-broad changes (`data/hand-codes/defect-type.csv`), which an actor with a shell can meet and a reader endorses
(18 of 18 coded cases). Against it: when Gemma acted as the writer, its own reproduction script ended without error
in 63 of 79 failing runs, and 81% of its scripts only print. So the actor may write the same empty check and approve.

The run is a two by two: reader against actor, Gemma against an outside family (Qwen3-32B). The reader cells are the
paper's existing scores. The question is whether moving the judge from reading to acting removes the extra trust,
and whether that needs the other family.

## Data

- Gemma 4 31B's 180 own held-out patches scored by all nine judges (`fresh_judging.load`, the paper's analysis set):
  95 pass, 85 fail; 133 scored 100 by Gemma as reader, of which 81 pass and 52 fail. Writer-run model calls from
  `data/mcsr-runs/main-a/` and `main-b/` (`n_calls`).
- Other writers' held-out patches on the same issues (public mini-SWE-agent runs, official labels): for each of the
  180 issues, one failing patch by another writer where one exists, drawn with seed 0 from the patches all nine judges
  scored. Needed for leniency. One passing patch per issue by another writer, same draw, is the extension set (run
  only if the core set finishes by 2026-11-06); it gives the self-judging gap in the actor cell.
- Patches are shown as in the paper: test files removed, patches over 30,000 characters dropped (already applied to
  this set).
- Reader scores for the comparison cells: Gemma's written scores (`derived/fresh_gemma4-31b.jsonl`), Qwen3-32B's
  written scores (`fresh_qwen3-32b-local.jsonl`), the paper's outside panel.

## Runs (lab A100, one GPU; Apptainer sandboxes on the same machine)

Judges: Gemma 4 31B, the 4-bit competition checkpoint (`gemma-4-31B-it-qat-w4a16-ct`, served as before by vLLM,
thinking off, temperature 0, context 131,072); Qwen3-32B (bf16, snapshot 9216db57, served alone, thinking off,
temperature 0, context 32,768 as in the check run). Served one at a time.

One run per patch and judge:

1. Build a writable sandbox from the issue's SWE-bench image (`eval_apptainer.image`, `.sif` cache in
   `swe-env/sif`). Apply the patch with the SWE-bench harness's fallbacks (`git apply`, then `--reject`, then
   `patch --fuzz=5`); a patch that does not apply is "not applied" and dropped from the actor cell with a count.
   The patch is applied, not committed, so `git diff` shows it.
2. Start the judge in mini-SWE-agent 1.7.0 (`DefaultAgent`, the SWE-bench config with the templates below), with the
   sandbox as its environment. Step limit 15. The judge is not told who wrote the patch.
3. Task text (instance template; the exact file is `scripts/judge_actor.yaml`, committed before the first run):
   the issue text; the patch as a diff; then: "This patch has been applied to the repository in /testbed. Decide
   whether it resolves the issue. First write a test that fails on the original code and passes with the patch
   applied; `git stash` and `git stash pop` switch between the two. Then try at least one case the issue implies but
   does not show. Use the shell; do not decide from reading alone. When done, end your answer with two lines:
   `TEST: <one shell command that runs your test>` and `SCORE: <0 to 100, the chance the patch passes the
   maintainers' hidden tests>`."
4. After the run, the harness (not the judge) reads the final message, parses `SCORE` and `TEST`, and runs the
   `TEST` command itself twice in the same sandbox: with the patch reverted (`git stash`, the judge's new files
   kept) and with the patch applied. A test run passes when the exit code is 0 and the output has no "Traceback" and
   no "AssertionError" (the rule of `spec/own-script-gate.md`); a 120 s limit fails it.
5. Saved per run: the full message history, the score, the `TEST` command, the judge's added or changed files
   (`git status` minus the patch's files), the two test outcomes, the number of model calls, the seconds, and the
   tokens. A run with no `SCORE` line after 15 steps is "unreadable", dropped and counted, as in the paper.

Order, with the pilot's stop rule:

1. Smoke: two pilot issues whose images were pulled first (`astropy__astropy-14508`, `astropy__astropy-7166`),
   Gemma actor. Pass = the judge takes steps, a `SCORE` line is written, the `TEST` command runs. Their rows are
   kept in the pilot (same settings).
2. **Pilot: Gemma actor on the 133 own patches it scored 100 as a reader.** This is the set where every reader
   signal failed. Stop rule, read before anything else runs: the Gemma actor cells of the full run are **not
   started** if its approval (score 100) on the 52 failing patches stays above 50% while its approval on the 81
   passing stays above 80%. Qwen3-32B then runs as actor on the same 133 only; its full cells start only if it
   separates them (within-133 AUROC interval above 0.5).
3. Full core set: the judge's remaining runs (Gemma: 47 own patches and up to 180 other writers' failing patches;
   Qwen3-32B: all 180 own and the same failing patches). Then the extension set if time allows.

Budget: about 12 to 15 A100-hours in total (writer runs took a median of 10 minutes with a 250-step budget; 15 steps
should take a few minutes; 6 workers). Image pulls (about 160, Docker Hub 100 an hour) run beforehand on CPU. No API
spend. The A100 is shared; runs are append-only and resume.

## Measures

Intervals: 95%, 2,000 issue resamples, seed 0. "Reader" numbers are the paper's existing scores on the same patches.

1. **Approval.** Share of patches scored 100 (and at least 90), by cell, for own failing, own passing, others'
   failing. Reader values: own failing 61%, others' failing 35%.
2. **Leniency, the paper's measure.** Judge's score minus the paper's outside panel's mean reader score on the same
   patch; own failing minus other writers' failing. The reference is kept as the reader panel so the actor cell is
   comparable with the reader's +16.6. Reported beside it: the same with Qwen3-32B's actor score as the reference.
3. **Ranking among own patches.** Top quarter of the 180 own patches by actor score, ties by the mechanical
   fail-then-pass flag (flagged first), then fewer writer-run model calls; share passing against 78% (fewer calls)
   and 84% (GLM-4.5). AUROC of the actor score on own patches, against the reader's 0.622. AUROC within the 133
   stamped patches, the pilot's primary.
4. **The actor's test.** Share of runs whose `TEST` fails with the patch reverted and passes with it applied (the
   mechanical flag); pass rate of own patches with and without the flag; share of tests with an `assert`, `raise`,
   `sys.exit` or `pytest` invocation; share that only print. Also: among the 52 stamped failures, how many the flag
   catches, and how many of those break an existing test (overlap with the existing-test flag, 17 of 52).
5. **Same model, both seats.** Qwen3-32B actor AUROC on Gemma's own patches minus Qwen3-32B reader AUROC (reader
   minus Gemma was +0.016 [−0.059, +0.089]). Gemma actor minus Gemma reader likewise.
6. **Cost.** Model calls and seconds per run per judge, for the paper's cost column.
7. Description: unreadable and not-applied counts; approval by defect type on the 31 coded cases.

## Reading, fixed now

- **Acting removes the extra trust:** Gemma actor's own-failing approval is within 5 points of its others'-failing
  approval in the same cell, its leniency interval includes 0, and its AUROC within the 133 stamped patches has a
  lower bound above 0.5. The paper reports it as a method for agents (one set, exploratory): spend the last steps
  trying to break the patch, not reading it. The top quarter and its interval against 78% are reported whatever
  they are.
- **Only the other family's actor removes it:** Gemma actor fails the rule above, and Qwen3-32B actor's AUROC on
  Gemma's own patches minus its reader AUROC has an interval above 0. The paper says a shell does not rescue
  self-verification (with the share of Gemma's own tests that pass its own failing patch) and that a model of
  another family with the same shell does.
- **Neither removes it:** otherwise. The paper adds one sentence: no signal from Gemma, including running its own
  tests with a shell, separates its stamped passes from its stamped failures; another model reading the diff does.
- Any other pattern (for example, leniency gone but ranking not improved): reported as described, no method claimed.
- The mechanical flag alone is reported in every reading; it is not the method unless the reading above holds.

## Logging

Outputs copied to `data/lab-runs/judge-as-actor/<judge>/` (runs, trajectories, test outcomes); analysis
`scripts/judge_actor.py analyze` → `scripts/derived/judge_as_actor_2026-11-0X.json`; W&B group `judge-as-actor`
(one run per judge and set); changelog entry with start, end and GPU-hours; `notes/compute-ledger.md` and
`notes/compute-ledger-table.md` updated.

## Addendum 1 (2026-11-03, after the Gemma pilot): gpt-oss-20b as a second outside actor

The Gemma pilot met the stop rule (approval 86% of 49 readable stamped failures, 94% of 77 stamped passes; 7 runs
unreadable), so Gemma's full cells do not start. Qwen3-32B in bf16 does not fit beside another user's 11 GB job on
the A100. gpt-oss-20b (OpenAI family; MXFP4, about 13 GB; snapshot 6cee5e81) is added as an outside-family actor
and runs first. Settings: served alone by vLLM as in the LiveCodeBench sweep, context 131,072, temperature 0,
default reasoning effort (medium, the same as its reader scores from OpenRouter, `fresh_gpt-oss-20b.jsonl`); same
templates, 15 steps, 6 workers. Order: smoke on the two smoke issues, then the 133 stamped own patches. Its full
cells start only if it separates them (within-133 AUROC interval above 0.5), as for Qwen3-32B. In the reading, "the
other family's actor" means either outside actor; each is reported on its own, actor AUROC minus its own reader
AUROC. Qwen3-32B runs on the same 133 once the GPU memory is free.

Addendum 1, harness change for gpt-oss-20b (2026-11-03, before its pilot). In the first smoke test 20 of 23 replies
were empty: gpt-oss ends its turn in the reasoning channel with a call to a shell tool in its own format (or with no
command), which vLLM does not return as text. A line in the system prompt asking for a bash block changed nothing (3
issues). With one declared tool, `bash(command)`, and vLLM's `--tool-call-parser openai`, 8 of 8 first replies were
tool calls with a command. So gpt-oss runs with that tool (`TOOL_MODE=bash`): `judge_actor.py` writes the first call
back as the `THOUGHT` plus bash block that mini-SWE-agent parses and runs. Prompts, step limit, scoring and the
harness's own test runs are unchanged. The failed smoke rows are kept apart in `judge-as-actor/gptoss-textmode-failed/`.

## Addendum 2 (2026-11-04, before rerunning one gpt-oss pilot issue): a reply cap for gpt-oss-20b

The gpt-oss-20b pilot finished 132 of 133 runs. The last one (`pylint-dev__pylint-8898|gemma-4-31b|7e48b0b1`) got
no finished reply from 02:17 UTC on: one reply ran to the 1,800 s request timeout, and at temperature 0 each retry
produced the same reply again. It was stopped at 04:22 UTC. That issue alone is rerun with a reply cap,
`MAX_TOKENS=32768` (reasoning plus answer), passed as `max_tokens` by `judge_actor.py`. The longest of the 1,350
finished gpt-oss replies in the pilot was 20,810 tokens, so the cap would have changed no other run. A reply cut by
the cap goes back to the agent like any reply without a command. Everything else is as in addendum 1. Any later
gpt-oss run (full cells) uses the same cap. The stopped attempt's server log is kept as
`judge-as-actor/gptoss/vllm-pilot-1.log`.

## Addendum 3 (2026-11-04, before any of these runs): complete the gpt-oss-20b comparison on the 133 patches

The pilot leaves the question "does the shell help the outside model?" open, for three reasons. (1) 41 of 133 gpt-oss
runs gave no score: 33 hit the 15-step limit, 4 got a vLLM 400 and 4 a vLLM 500. (2) The reading score it is compared
with came from OpenRouter, served by a mix of providers (Darkbloom, CoreWeave, Parasail and others), while the shell
score came from our local vLLM copy; the difference between the two scores mixes the shell with the serving. (3) On
the 92 scored patches the shell score minus the reading score is +0.069 AUROC [−0.068, +0.203].

The 400s are a harness bug, not the model: a command that timed out (`grep -R ... ..` from /testbed, which walks the
whole file system) returned its full output, about 138 million characters, because mini-SWE-agent's timeout message
is not truncated. At temperature 0 a plain rerun would repeat it. The 500s are vLLM failing to parse gpt-oss's reply
(Harmony tokens inside the text).

Analysis already done on existing data (this Mac, no new runs; exploratory, recorded here before the runs below):
on the 92 scored patches, gpt-oss reading AUROC 0.660 [0.556, 0.765], gpt-oss with a shell 0.729 [0.622, 0.822]; the
sum of the two scores' ranks 0.764, minus reading alone +0.104 [0.021, 0.188]. The 41 unscored patches have the same
mean reading score (62 against 64) but a reading AUROC of 0.52, so the 92 are the patches gpt-oss can separate more
easily by reading too.

Runs, one vLLM server for all three (gpt-oss-20b as in addendum 1, reply cap 32,768 tokens as in addendum 2), lab A100:

1. **gpt-oss-20b reading, local.** The paper's held-out reading prompt (`heldout_p1.jsonl`, `local_judging.py`, the
   same system and user text as the OpenRouter scores), on the 133 patches, temperature 0, default reasoning effort,
   `max_tokens` 3,000, then unparsed answers once more at 16,000 (the OpenRouter run used 3,000). Out:
   `judge-as-actor/gptoss-reader/`.
2. **Forced final answer for the 33 step-limit runs.** Each run's saved message history (the trailing empty message
   dropped) gets one more user message: "You have used all your commands. You cannot run any more commands. Decide
   now from what you have already seen. Reply with only the final command, with your own test command and score
   filled in:" followed by the submission command of the task template. One model call. SCORE and TEST are parsed
   from the reply. A fresh sandbox is built, the judge's saved files are put back, and the harness runs TEST with the
   patch reverted and applied as in step 4 of the runs. A reply with no SCORE stays unscored. Out:
   `judge-as-actor/gptoss-final/` (`score_source` = `forced_final`).
3. **Rerun of the 8 errored runs from the start**, same settings, with one harness fix in `judge_actor.yaml`: the
   timeout message is truncated like the ordinary observation (first and last 5,000 characters when the output has
   10,000 or more). Out: `judge-as-actor/gptoss-rerun/`. A run that errors again stays unscored.

Measures (all on the 133 stamped own patches, 2,000 issue resamples, seed 0):

- **Primary:** AUROC of gpt-oss with a shell minus AUROC of gpt-oss reading locally, on the patches both scored.
  Shell scores from the pilot, the rerun and the forced answers pooled.
- Reported beside it: the same without the forced answers; the same against the OpenRouter reading scores; the
  forced-answer rows alone (approval and AUROC); the rank-sum combination minus reading; the unscored count.

Reading, fixed now:

- Primary interval above 0: "a shell helps the outside judge". The paper may say that a judge from another family
  that runs code separates Gemma's stamped patches better than the same judge reading the diff (one set,
  exploratory).
- Otherwise: "no measurable gain from the shell". The paper says the outside judge separates the stamped patches
  about as well by reading, and the shell adds nothing measurable on these 133 patches. The full gpt-oss cells are
  not started.
- The rank-sum combination is reported in both cases as exploratory; it was computed after the scores were seen.
- If the forced answers alone carry the result (primary above 0 only with them), that is stated.
