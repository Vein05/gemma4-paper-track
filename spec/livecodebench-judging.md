# Charter: does Gemma rubber-stamp its own failing programs on LiveCodeBench?

Written 2026-11-01, after the hand check of `spec/livecodebench-pilot.md` met its gate and before any judge call on
these programs, with the user's OK ("can we star that too for judging"). Terms follow `GLOSSARY.md`.

## Question

The paper's result is about patches to repositories. Does the same rubber stamp appear when Gemma judges its own
one-file programs for contest problems, where there is no agent loop, no harness and no repository?

## Programs

- Gemma 4 31B's programs from the pilot (one per problem, temperature 0, answers cut off at 2,000 tokens rerun at
  8,000), labels from LiveCodeBench's own grader (`data/livecodebench-pilot/gemma4-31b-merged_*`).
- Problems: all 146 problems where Gemma's program ran and failed, and 146 problems where it passed, drawn with
  `random.seed(0)` within each difficulty in the same numbers as the failing ones (easy 5, medium 43, hard 98).
- Other writers: the first released program per problem of DeepSeek-V3, GPT-4o (2024-08-06) and Claude 3.5 Sonnet
  (2024-10-22) from `LiveCodeBench/submissions` (commit `6ca212e9`), with their released grades. Empty programs are
  left out. (Qwen2.5-Coder-32B's file covers only 713 of the 1,055 problems, so it is not used.)
- Comments and docstrings are removed from every program (Python `ast`; the program is unchanged otherwise), because
  Gemma's long docstrings would tell a judge who wrote the program. Programs that do not parse are kept as written.

## Judging and measures

The seven judges of `spec/third-party-lite.md` (Gemma and six outside judges), temperature 0, 3,000 output tokens, the
same parser and one re-ask at 8,000 tokens. The prompt is the paper's, with the problem in place of the issue and the
program in place of the patch: "Question: will this program pass all of the problem's hidden tests, with correct output
within the time and memory limits? Explain briefly, then end your reply with a final line that is exactly SCORE: <n>,
where n is your probability from 0 to 100 that the hidden tests pass." System prompt: an expert competitive programmer
reviewing a program, who cannot run code.

Measures, rule and bootstrap (by problem) as in `spec/third-party-lite.md`: rubber-stamp rate on own vs other
writers' failing programs, leniency against the outside judges on the same program (failing and passing), and the
self-judging gap. The result holds if Gemma scores a larger share of its own failing programs 100 than of other
writers' failing programs and the failing-program leniency difference has a 95% interval above 0.

Known limit: the hand check found 3 of 20 failing programs that a fair grader would accept (two floats within the
stated tolerance, one valid answer among several). Such programs stay in as failing for every writer.

Budget: the OpenRouter credit left after the SWE-bench Lite judging (about $1.6). A per-judge spending limit stops a
judge before the credit runs out; judges that stop early are reported.

## How the paper would describe it, if it holds

> **The effect also holds outside patching.** To test whether the rubber stamp depends on agents and repositories, we
> asked Gemma 4 31B to solve LiveCodeBench contest problems in one answer, with no agent loop. We gave its failing and
> passing programs, and the published programs of three other models on the same problems, to the same judges, with
> comments removed so that style did not reveal the author. Gemma scored X% of its own failing programs 100, against Y%
> of other models' failing programs, and the outside judges scored the same programs lower (leniency +Z [a, b]).

If it does not hold, the same paragraph reports the numbers and says the effect did not appear on contest programs.

## Change, 2026-11-01, before judging (after an 8-call cost test per judge for four judges)

Calls cost more here than on SWE-bench Lite (Qwen3-Coder $0.00097, GLM-4.7-Flash $0.00062, Gemma $0.00048, Llama 4
Maverick $0.00039 per call), so the plan above needed about $2.9 against $1.8 of credit. To fit: GPT-4o's programs are
left out (two other writers remain, with 436 failing programs), and Qwen3-Coder is left out as a judge. Judges: Gemma
and five outside judges (gpt-oss-20b, gpt-oss-120b, Qwen3.5-9B, GLM-4.7-Flash, Llama 4 Maverick), each with a spending
limit. Unparsed answers are re-asked at 8,000 tokens only if credit remains; otherwise they are left out and counted.
The paragraph above then says "two other models". The rule is unchanged.
