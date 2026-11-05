#!/usr/bin/env python3
"""Price each probe arm from rendered input sizes (derived/arm_chars_rishav.csv). No API calls.

Prices are USD per million tokens from the OpenRouter endpoint listings fetched 2026-10-04
(https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints and .../deepseek/deepseek-v4-flash/endpoints).
Output-token counts are assumptions (no measurement): 40 tokens for a JSON-only reply; 2500 (Gemma) / 3000 (DeepSeek)
when reasoning is on.
"""
import pandas as pd

d = pd.read_csv("derived/arm_chars_rishav.csv")
d = d[d.patch_nonempty == 1]
CPT = 3.5  # chars per token, calibrated on the traces (see report); 4.0 is the nominal alternative

PRICES = {  # name: (in $/M, out $/M)
    "Gemma4 31B CoreWeave fp4 (logprobs)": (0.10, 0.34),
    "Gemma4 31B Parasail fp8 (logprobs)": (0.15, 0.40),
    "Gemma4 31B Crusoe bf16 (no logprobs listed)": (0.14, 0.40),
    "Gemma4 31B DeepInfra fp8": (0.20, 0.40),
}
DS = {"DeepSeek V4 Flash Parasail fp8 (logprobs)": (0.14, 0.28), "DeepSeek V4 Flash Relace fp4": (0.0224, 1.28)}

ARMS = {  # arm: (chars column, model family)
    "a  full trajectory (agent view, obs cut at 5000)": ("chars_a_agentview", "gemma"),
    "a' full trajectory, obs cut at 2000 / args at 1000": ("chars_a_cap", "gemma"),
    "b  issue + patch + last test run": ("chars_b", "gemma"),
    "b+ b + agent final message": ("chars_bplus", "gemma"),
    "c  DeepSeek on b": ("chars_b", "ds"),
    "c2 DeepSeek on a": ("chars_a_agentview", "ds"),
}


def cost(col, out_tok, calls, price):
    tin = d[col].sum() / CPT * calls
    tout = out_tok * len(d) * calls
    return tin / 1e6 * price[0] + tout / 1e6 * price[1], tin, tout


print(f"traces priced: {len(d)} (non-empty patch). input tokens at {CPT} chars/token; plan = 1 call (T=0) and 5 calls (T=0.7)")
rows = []
for arm, (col, fam) in ARMS.items():
    plist = PRICES if fam == "gemma" else DS
    for pname, pr in plist.items():
        for calls, label in ((1, "x1"), (5, "x5")):
            for think in (False, True):
                out_tok = (2500 if fam == "gemma" else 3000) if think else 40
                c, tin, tout = cost(col, out_tok, calls, pr)
                rows.append(dict(arm=arm, provider=pname, calls=label, reasoning="on" if think else "off",
                                 input_Mtok=round(tin / 1e6, 2), output_Mtok=round(tout / 1e6, 3), usd=round(c, 3)))
r = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
print(r.to_string(index=False))
r.to_csv("derived/arm_costs_openrouter.csv", index=False)
print("\nRecommended bundle (Gemma CoreWeave fp4 for a, b; DeepSeek Parasail for c, c2; x1 and x5, reasoning off) total:")
sel = r[(r.reasoning == "off") & (((r.provider.str.contains("CoreWeave")) & r.arm.str[:2].isin(["a ", "b "])) | ((r.provider.str.contains("Parasail")) & r.provider.str.contains("DeepSeek") & r.arm.str[:2].isin(["c ", "c2"])))]
print(sel.groupby("calls").usd.sum())
