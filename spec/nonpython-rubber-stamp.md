# Spec: does Gemma 4 rubber-stamp its own failing patches in Go, Ruby and PHP?

Written 2026-11-06, before any of these agents ran and before any Multilingual patch was scored. The user approved the
GPU run the same day ("over night your task is to look into them, and see if you can run these two sets of evals").
This spec freezes the parts of `spec/multilingual-replication.md` that the run uses and replaces its issue list. Terms
follow `GLOSSARY.md`.

## Why

The paper's agent experiments cover Python only. A review named this as its main limit. This run asks one question:
when Gemma 4 31B judges its own failing patches in three other languages, does it still trust them more than it trusts
other writers' failing patches?

## Issues (rule fixed now)

- SWE-bench Multilingual, revision `846e647b9f33c0b51b739d005d13d85493c9af09`. Go, Ruby and PHP.
- Walk the fixed random order saved in `data/public/swe-bench-multilingual/issues.json` and take up to 40 issues per
  language. Skip an issue if Gemma already ran on it (the 10 issues of the 2026-10-23 run and the 9 smoke-test issues,
  3 of them in these languages) or if its reference patch fails in our environment.
- The list is `data/nonpython/issues.json`. 25 reference checks were still open when this was written. If one fails
  after the list is used, the next issue in the order takes its place.
- Why these three: the sandboxes work for them, and the public control runs cover them. Rust's `bash -lc` lacks
  `cargo` on PATH, and the other languages have too few issues.

## Gemma's patches

As in `spec/multilingual-replication.md`, section "Gemma's patches": mini-SWE-agent 2.0.0's SWE-bench runner with the
public control runs' saved config, tool calling, `bash -lc`, step limit 250, one attempt per issue;
`google/gemma-4-31B-it-qat-w4a16-ct` revision `52f3f65b`; temperature 0; thinking off; context 131,072 tokens.

One operating change: the GPU is not shared with another job now, so vLLM gets 0.70 of its memory and 4 to 6 agents run
at a time. This changes speed only. The number is set from the pilot's prefix-cache hit rate.

## Pilot and stop rule

The first 3 issues per language of the list (9 issues), which also count in the full run. No labels are read.
Stop and report, without changing any condition, if fewer than 5 of the 9 end with a non-empty patch, or if tool calls
fail to parse on more than 1 issue. The earlier run saw 3 of 9 issues repeat one command until a limit, so such loops
alone do not stop the run; they are counted and reported.

If the run is cut short by time, the analysis uses the finished issues, which follow the fixed order.

## Other writers (controls)

The failing patches of the four public mini-SWE-agent 2.0.0 entries on the same issues: GLM-5, Kimi-K2.5, DeepSeek-V3.2,
MiniMax-M2.5, with their official labels. Only failing control patches are scored.

## Labels

`scripts/eval_apptainer.py`, SWE-bench 4.1.0's specs and grading. Issue kept only if its reference patch passes.

## Judges

Gemma 4 31B, GLM-4.5, Qwen3.5-9B, gpt-oss-20b, Llama-4-Maverick through OpenRouter from the Mac, prompt, parser and
re-ask as in the held-out run (`scripts/multilingual_judging.py`), one pinned provider per judge. Gemma 4 31B moves from
Novita to Crusoe, also bf16, because Novita's uptime read 70% on 2026-11-06. The others stay as written, unless the
provider is gone, in which case the replacement is recorded. Test files are removed as in
`scripts/multilingual_judging.py`. Budget: about $2 to $4.

## Measures and reading rules (fixed before any score)

95% intervals from 2,000 resamples of issues, seed 0. Analysis: `scripts/nonpython_analyze.py`.

1. **Primary, extra trust.** Per patch, Gemma's score minus the mean of the outside judges not from the writer's family
   (GLM-4.5 is left out for GLM-5's patches and has no other exclusions here). Extra trust is the mean of this on
   Gemma's failing patches minus the mean on control failing patches.
   **The effect carries over if the interval's lower bound is above 0. It does not carry over if the interval includes
   0.** Either result is reported.
2. Rubber-stamp rate: share of Gemma's failing patches it scores 100, beside the share of control failing patches it
   scores 100, and the share of the same own patches the outside judges score 100.
3. Same-issue extra trust: per issue with both kinds of patch, own mean minus control mean, averaged over issues.
4. Descriptive only: extra trust per language and with each control writer alone; the Python held-out value with the
   same four outside judges beside it. The Python runs used mini-SWE-agent 1.7.0, so the difference between languages is
   not read as an effect of language.

## Predictions, written before the run (judgment, not evidence)

- Gemma solves about 25 to 40% of the issues.
- Extra trust has a lower bound above 0: about 70% likely. Point guess +10, lower than Python's +16.6.
- Gemma's rubber-stamp rate on its own failing patches is above the control rate: about 80% likely.

## Run and logging

`scripts/lab/nonpython_run.sh` on the lab A100, `ml/runs/nonpython/` on the server, copied to
`data/lab-runs/nonpython/`. W&B project `gemma4-paper-track`, group `nonpython-rubber-stamp`, logged from the Mac.
Changelog entry with start, end and GPU-hours; compute ledger updated.

## Addendum, 2026-11-06, 08:30 UTC: harness bug and what happens after the stop rule

Written after the pilot met its stop rule (5 of 9 finished, no patch) and before any patch was graded or scored. No label
or score has been read. The user: "please work on this overnight, do the best, if nothing works just work on the seed".

**Harness bug, fixed.** Images without `/etc/localtime` make Apptainer print `WARNING: Skipping mount /etc/localtime` first
in every command output. mini-SWE-agent reads its submit marker from the first line, so it did not see Gemma's submission
on hashicorp__terraform-34580 (112 attempts, one patch). Docker prints no such line. `scripts/run_gemma_multilingual.py`
now removes lines starting `WARNING: Skipping mount` from outputs. Issues whose outputs carried the warning are rerun from
the start; their earlier results are kept aside and not analysed. Other pilot issues stand.

**Thinking-on test.** The PHP and Ruby pilot issues that hit the step limit run once with thinking on, same config, on the
same server, for at most 75 minutes.

**Decision, fixed now, from patch counts only:**

1. If at least 3 of the 6 PHP and Ruby pilot issues and at least 2 of the 3 Go pilot issues end with a patch with thinking
   off: full run of all 120 issues, thinking off.
2. Otherwise, each language group is decided alone. Go with at least 2 of 3 patches: its 40 issues, thinking off. PHP and
   Ruby with at least 3 of 6: their 80 issues, thinking off.
3. A group that fails runs with thinking on only if at least half of its test issues end with a patch with thinking on. It
   is then a separate arm, compared only with the same control writers on the same issues, and read apart from thinking-off
   results. It runs after the Lite repair and the repair seeds, because it may be slow.
4. If no group qualifies, the Go, Ruby and PHP run ends here and the paper does not claim a result on them. The GPU goes to
   the Lite repair and `spec/repair-seeds.md`.

Any result names the languages it covers. A language left out because Gemma did not produce patches is reported as that:
the share of issues with no patch is itself a result, and it limits what extra trust can say about those issues.

## Second addendum, 2026-11-06, 10:30 UTC: the warning fix did not work

Written before any patch was graded or scored. No label or score has been read.

**What went wrong.** mini-SWE-agent checks for the submit marker inside its own `execute`. The first fix removed the warning
after that check, so Gemma saw clean outputs while its submissions were still missed. On the rerun, hashicorp__terraform-34580
sent the submit command 111 times and caddyserver__caddy-5626 98 times, and each output Gemma saw starts with the marker.
The Go count of 0 of 3 from that rerun therefore says nothing about Gemma. The fix now removes the warning before the check.
Tested in the terraform image with no model: a submit command now ends the run with the patch.

**What is rerun.** caddy-5626 and terraform-34580 run again from the start with thinking off, and their earlier results are set
aside. prometheus__prometheus-13845 stands: it never tried to submit in either run (237 of 250 calls in the rerun are one
command), so the bug did not touch it.

**Decision, unchanged rule.** Go with at least 2 of 3 patches, thinking off: its 40 issues, thinking off. If Go fails, its pilot
issues with no patch run once with thinking on, at most 45 minutes, and Go joins the thinking-on arm only if at least half of
them end with a patch.

**PHP and Ruby.** They failed with thinking off (1 of 6) and passed the thinking-on test (5 of 5 issues ended with a patch), so
rule 3 of the first addendum applies: their 80 issues run as a separate thinking-on arm. Those 5 results count in the arm.

**Order.** Repair seeds, Go test, Go if it qualifies, Lite repair, thinking-on arm.

## Third addendum, 2026-11-06, 13:15 UTC: Go's result and a change of order

Written before any patch was graded or scored. No label or score has been read.

**Go.** With the working fix and thinking off, 1 of 3 Go issues ended with a patch (terraform-34580), below the rule's 2 of 3. The Go issues
with no patch, caddy-5626 and prometheus-13845, both ended with a patch with thinking on, so Go joins the thinking-on arm under the second
addendum's rule. The arm is therefore all 120 issues, thinking on, and there is no thinking-off run. The 7 test results count in the arm.

**Order.** The first addendum put this arm after the Lite repair because it might be slow. The Lite repair is waiting for its gate's last two
issues and its CPU grading, which would leave the GPU idle for about two hours, and the test issues took 22 to 33 minutes per batch. So the arm
runs now and the Lite repair runs after it. The two share no patches, so the order changes neither result.

**Reading.** The arm is the only Go, Ruby and PHP result. It uses thinking on, unlike every Python run in the paper (thinking off), so any
comparison with Python is across a changed setting as well as a changed language, and it stays descriptive as section "Measures" already says.
The 7 test issues had no patch or a looping start with thinking off; their selection does not affect extra trust, which compares patches with
the control writers on the same issues.
