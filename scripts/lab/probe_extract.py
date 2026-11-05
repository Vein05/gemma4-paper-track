#!/usr/bin/env python3
"""Activation and issue-likelihood features for spec/judge-probe.md. Runs on the lab A100.

feats: for every judging prompt in heldout_p1.jsonl, one forward pass (no generation) over the chat-templated prompt
  with the generation prompt added; saves the hidden state at the last prompt token for hidden_states indices
  4, 8, ..., 60 (index i = output of layer i; the last one is after the final norm) as float16.
ll: mean log-probability per token of the issue text (first 1,500 tokens), teacher-forced as the assistant reply to
  "Here is a patch ... Write the GitHub issue that this patch fixes.", with the patch and with "(no patch)".

Usage: python probe_extract.py feats|ll --model DIR --prompts heldout_p1.jsonl --out DIR [--limit N]
Resumes: items already in the output are skipped.
"""
import argparse, json, os, re, time

import numpy as np
import torch
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, AutoModelForImageTextToText, CompressedTensorsConfig

LAYERS = list(range(4, 61, 4))
ISSUE_MAX = 1500


def parts(prompt):
    repo = re.search(r"for the repository (\S+?)\.\n", prompt).group(1)
    issue = re.search(r"<issue>\n(.*?)\n</issue>", prompt, re.S).group(1)
    patch = re.search(r"<patch>\n(.*?)\n</patch>", prompt, re.S).group(1)
    return repo, issue, patch


def load(model_dir):
    tok = AutoTokenizer.from_pretrained(model_dir)
    cfg = AutoConfig.from_pretrained(model_dir)
    if any("ConditionalGeneration" in a for a in (cfg.architectures or [])):  # Gemma 4
        q = {"quantization_config": CompressedTensorsConfig(run_compressed=False)} \
            if getattr(cfg, "quantization_config", None) else {}  # the 4-bit checkpoints; 26B-A4B is bf16
        model = AutoModelForImageTextToText.from_pretrained(model_dir, dtype=torch.bfloat16, device_map="cuda",
                                                            attn_implementation="sdpa", **q)
    else:  # plain causal LM in bf16 (Qwen3-32B, addendum 4)
        model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.bfloat16, device_map="cuda",
                                                     attn_implementation="sdpa")
    model.eval()
    return tok, model


def chat_ids(tok, messages):
    text = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False, enable_thinking=False)
    return tok(text, add_special_tokens=False, return_tensors="pt").input_ids


def text_model(model):
    """The decoder stack (module with .layers and .norm) inside the multimodal wrapper."""
    for m in model.modules():
        if hasattr(m, "layers") and hasattr(m, "norm") and isinstance(m.layers, torch.nn.ModuleList):
            return m
    raise RuntimeError("decoder stack not found")


def layers_of(model):
    """Every 4th layer up to the last but the final one, then the final norm (index = number of layers)."""
    n = len(text_model(model).layers)
    return list(range(4, n, 4)) + [n]


def last_states(model, ids):
    """Hidden state at the last token after layers 4, 8, ... and after the final norm (= hidden_states index n),
    captured with hooks so that only the last position is kept (output_hidden_states ran out of memory on long
    prompts)."""
    lm = text_model(model); L = layers_of(model); n = len(lm.layers)
    got, hooks = {}, []
    for i in L[:-1]:
        hooks.append(lm.layers[i - 1].register_forward_hook(
            lambda m, inp, out, i=i: got.__setitem__(i, (out[0] if isinstance(out, tuple) else out)[0, -1].float().cpu())))
    hooks.append(lm.norm.register_forward_hook(lambda m, inp, out: got.__setitem__(n, out[0, -1].float().cpu())))
    try:
        with torch.no_grad():
            model.model(input_ids=ids, use_cache=False)
    finally:
        for h in hooks:
            h.remove()
    return torch.stack([got[i] for i in L]).numpy().astype(np.float16)


def feats(a, tok, model, rows):
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "feats.npz")
    done = dict(np.load(path)) if os.path.exists(path) else {}
    meta = open(os.path.join(a.out, "feats_meta.jsonl"), "a")
    t0, n = time.time(), 0
    for r in rows:
        if r["pid"] in done:
            continue
        ids = chat_ids(tok, [{"role": "system", "content": r["system"]}, {"role": "user", "content": r["prompt"]}]).cuda()
        done[r["pid"]] = last_states(model, ids)
        meta.write(json.dumps({"pid": r["pid"], "n_tokens": ids.shape[1]}) + "\n"); meta.flush()
        n += 1
        if n % 50 == 0:
            np.savez(path, **done)
            print(f"{n} done, {time.time() - t0:.0f}s, last {ids.shape[1]} tokens", flush=True)
        torch.cuda.empty_cache()
    np.savez(path, **done)
    print(f"feats finished: {len(done)} items, {time.time() - t0:.0f}s", flush=True)


def issue_ll(tok, model, repo, patch, issue_ids):
    msg = f"Here is a patch to the repository {repo}:\n\n{patch}\n\nWrite the GitHub issue that this patch fixes."
    prefix = chat_ids(tok, [{"role": "user", "content": msg}])
    ids = torch.cat([prefix, issue_ids], 1).cuda()
    k = issue_ids.shape[1]
    with torch.no_grad():
        logits = model(input_ids=ids, use_cache=False, logits_to_keep=k + 1).logits[0, :-1].float()
    lp = torch.log_softmax(logits, -1).gather(1, ids[0, -k:, None])[:, 0]
    return float(lp.mean()), prefix.shape[1] + k


def ll(a, tok, model, rows):
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "issue_ll.jsonl")
    done = {json.loads(l)["key"] for l in open(path)} if os.path.exists(path) else set()
    fh = open(path, "a")
    t0, n = time.time(), 0
    for r in rows:
        repo, issue, patch = parts(r["prompt"])
        issue_ids = tok(issue, add_special_tokens=False, return_tensors="pt").input_ids[:, :ISSUE_MAX]
        for key, p in ((r["pid"], patch), ("nopatch|" + r["iid"], "(no patch)")):
            if key in done:
                continue
            m, ntok = issue_ll(tok, model, repo, p, issue_ids)
            fh.write(json.dumps({"key": key, "iid": r["iid"], "ll": m, "n_issue_tokens": issue_ids.shape[1],
                                 "n_tokens": ntok}) + "\n"); fh.flush()
            done.add(key); n += 1
            if n % 50 == 0:
                print(f"{n} done, {time.time() - t0:.0f}s", flush=True)
    print(f"ll finished: {n} new rows, {time.time() - t0:.0f}s", flush=True)


def score(a, tok, model, rows):
    """Teacher-force a recorded answer up to its score digits: log P(score = 100), the ten digit probabilities at the
    first score position, and the hidden state at the token before the number (spec addendum 2)."""
    os.makedirs(a.out, exist_ok=True)
    ans = {json.loads(l)["pid"]: json.loads(l) for l in open(a.answers)}
    path = os.path.join(a.out, "score_feats.npz")
    done = dict(np.load(path)) if os.path.exists(path) else {}
    fh = open(os.path.join(a.out, "score.jsonl"), "a")
    digits = [tok.convert_tokens_to_ids(str(d)) for d in range(10)]
    t0, n = time.time(), 0
    lm = text_model(model); L = layers_of(model); nl = len(lm.layers)
    for r in rows:
        if r["pid"] in done or r["pid"] not in ans:
            continue
        head = tok.apply_chat_template([{"role": "system", "content": r["system"]}, {"role": "user", "content": r["prompt"]}],
                                       add_generation_prompt=True, tokenize=False) + ans[r["pid"]]["prefix"]
        pre = tok(head, add_special_tokens=False).input_ids
        full = tok(head + a.target, add_special_tokens=False).input_ids
        nt = len(a.target)
        assert full[:len(pre)] == pre and len(full) - len(pre) == nt, (r["pid"], full[len(pre) - 2:])
        ids = torch.tensor([full]).cuda()
        got, hooks = {}, []
        pos = len(pre) - 1
        for i in L[:-1]:
            hooks.append(lm.layers[i - 1].register_forward_hook(
                lambda m, inp, out, i=i: got.__setitem__(i, (out[0] if isinstance(out, tuple) else out)[0, pos].float().cpu())))
        hooks.append(lm.norm.register_forward_hook(lambda m, inp, out: got.__setitem__(nl, out[0, pos].float().cpu())))
        try:
            with torch.no_grad():
                logits = model(input_ids=ids, use_cache=False, logits_to_keep=nt + 1).logits[0].float()
        finally:
            for h in hooks:
                h.remove()
        lp = torch.log_softmax(logits, -1)  # rows: predictions after positions len-nt-1 .. len-1
        lp100 = float(sum(lp[k, full[len(pre) + k]] for k in range(nt)))  # log P(target); named for the default "100"
        pd = torch.softmax(logits[0], -1)[digits].tolist()
        done[r["pid"]] = torch.stack([got[i] for i in L]).numpy().astype(np.float16)
        fh.write(json.dumps({"pid": r["pid"], "logp100": lp100, "p_digit": pd, "recorded": ans[r["pid"]]["score"],
                             "n_tokens": len(full)}) + "\n"); fh.flush()
        n += 1
        if n % 50 == 0:
            np.savez(path, **done)
            print(f"{n} done, {time.time() - t0:.0f}s", flush=True)
        torch.cuda.empty_cache()
    np.savez(path, **done)
    print(f"score finished: {len(done)} items, {time.time() - t0:.0f}s", flush=True)


def plain(a, tok, model, rows):
    """spec/base-vs-instruct.md: rows carry a plain-text prompt ending in "SCORE: " (no chat template); log P(target)
    teacher-forced after it, and the ten digit probabilities at the first score position. --pilot-only: pilot rows."""
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "plain.jsonl")
    done = {json.loads(l)["pid"] for l in open(path)} if os.path.exists(path) else set()
    fh = open(path, "a")
    digits = [tok.convert_tokens_to_ids(str(d)) for d in range(10)]
    nt = len(a.target)
    t0, n, skipped = time.time(), 0, 0
    for r in rows:
        if r["pid"] in done or (a.pilot_only and not r.get("pilot")):
            continue
        pre = tok(r["text"], add_special_tokens=False).input_ids
        full = tok(r["text"] + a.target, add_special_tokens=False).input_ids
        assert full[:len(pre)] == pre and len(full) - len(pre) == nt, (r["pid"], full[len(pre) - 2:])
        if tok.bos_token_id is not None:
            pre, full = [tok.bos_token_id] + pre, [tok.bos_token_id] + full
        if len(full) > 32768:
            fh.write(json.dumps({"pid": r["pid"], "skipped": "too_long", "n_tokens": len(full)}) + "\n"); fh.flush()
            skipped += 1
            continue
        ids = torch.tensor([full]).cuda()
        with torch.no_grad():
            logits = model(input_ids=ids, use_cache=False, logits_to_keep=nt + 1).logits[0].float()
        lp = torch.log_softmax(logits, -1)
        lpt = float(sum(lp[k, full[len(pre) + k]] for k in range(nt)))
        pd = torch.softmax(logits[0], -1)[digits].tolist()
        fh.write(json.dumps({"pid": r["pid"], "logp100": lpt, "p_digit": pd, "n_tokens": len(full)}) + "\n"); fh.flush()
        n += 1
        if n % 50 == 0:
            print(f"{n} done, {time.time() - t0:.0f}s", flush=True)
        torch.cuda.empty_cache()
    print(f"plain finished: {n} new rows, {skipped} too long, {time.time() - t0:.0f}s", flush=True)


def fam(a, tok, model, rows):
    """spec/post-training-familiarity.md: one forward pass per plain-text prompt gives (1) log P(target) after
    "SCORE:" as in plain(), and (2) the summed log-likelihood of the scored patch's own tokens (the text between the
    last "<patch>\\n" and "\\n</patch>"), each token conditioned on everything before it. Works for tokenizers that
    attach the space to the next token (the space before the target is then moved into the target). Writes
    fam.jsonl; resumable; --pilot-only scores pilot rows only."""
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "fam.jsonl")
    done = {json.loads(l)["pid"] for l in open(path)} if os.path.exists(path) else set()
    fh = open(path, "a")
    head = model.get_output_embeddings()
    cap = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    V = head.weight.shape[0]
    num = torch.zeros(V, dtype=torch.bool)
    for i in range(min(V, len(tok))):
        s = tok.decode([i]).strip()
        num[i] = bool(s) and s[0].isdigit()
    num = num.cuda()
    norm = text_model(model).norm
    grab = {}
    hook = norm.register_forward_hook(lambda m, i, o: grab.__setitem__("h", o))
    bos = [tok.bos_token_id] if tok.bos_token_id is not None else []
    t0, n, skipped, checked = time.time(), 0, 0, False
    for r in rows:
        if r["pid"] in done or (a.pilot_only and not r.get("pilot")):
            continue
        text, target, moved = r["text"], a.target, False
        pre = tok(text, add_special_tokens=False).input_ids
        full = tok(text + target, add_special_tokens=False).input_ids
        if full[:len(pre)] != pre and text.endswith(" "):
            text, target, moved = text[:-1], " " + a.target, True
            pre = tok(text, add_special_tokens=False).input_ids
            full = tok(text + target, add_special_tokens=False).input_ids
        assert full[:len(pre)] == pre, (r["pid"], full[len(pre) - 2:])
        nt = len(full) - len(pre)
        enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
        assert enc.input_ids == pre
        s = text.rfind("<patch>\n") + len("<patch>\n")
        e = text.rfind("\n</patch>")
        pt = [k for k, (cs, ce) in enumerate(enc.offset_mapping) if cs >= s and ce <= e and ce > cs]
        assert pt and e > s, r["pid"]
        pre, full = bos + pre, bos + full
        pt = [k + len(bos) for k in pt]
        if len(full) > 32768:
            fh.write(json.dumps({"pid": r["pid"], "skipped": "too_long", "n_tokens": len(full)}) + "\n"); fh.flush()
            skipped += 1
            continue
        ids = torch.tensor([full]).cuda()
        with torch.no_grad():
            logits = model(input_ids=ids, use_cache=False, logits_to_keep=nt + 1).logits[0].float()
            h = grab.pop("h")[0]
            lp = torch.log_softmax(logits, -1)
            lpt = float(sum(lp[k, full[len(pre) + k]] for k in range(nt)))
            p1 = torch.softmax(logits[0], -1)
            pnum = float(p1[num[:p1.shape[0]]].sum())
            pos = torch.tensor([k - 1 for k in pt], device=ids.device)  # logits at k-1 predict token k
            tgt = torch.tensor([full[k] for k in pt], device=ids.device)
            tot = 0.0
            for c in range(0, len(pt), 1024):
                lg = head(h[pos[c:c + 1024]]).float()
                if cap:
                    lg = torch.tanh(lg / cap) * cap
                tot += float(torch.log_softmax(lg, -1).gather(1, tgt[c:c + 1024, None]).sum())
            if not checked:  # the hooked hidden state must reproduce the model's own logits
                lg = head(h[len(pre) - 1:len(pre)]).float()
                if cap:
                    lg = torch.tanh(lg / cap) * cap
                d = float((lg[0] - logits[0]).abs().max())
                print(f"hook check: max logit difference {d:.4f}", flush=True)
                assert d < 0.5, d
                checked = True
        fh.write(json.dumps({"pid": r["pid"], "logp100": lpt, "p_num": pnum, "patch_ll": tot, "n_patch": len(pt),
                             "n_tokens": len(full), "space_moved": moved}) + "\n"); fh.flush()
        n += 1
        if n % 50 == 0:
            print(f"{n} done, {time.time() - t0:.0f}s", flush=True)
        del h, logits
        torch.cuda.empty_cache()
    hook.remove()
    print(f"fam finished: {n} new rows, {skipped} too long, {time.time() - t0:.0f}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["feats", "ll", "score", "plain", "fam"])
    ap.add_argument("--pilot-only", action="store_true")
    ap.add_argument("--answers", default="")
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--target", default="100")  # score string to teacher-force (spec addendum 10)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.prompts)]
    if a.limit:
        rows = rows[:a.limit]
    tok, model = load(a.model)
    {"feats": feats, "ll": ll, "score": score, "plain": plain, "fam": fam}[a.what](a, tok, model, rows)


if __name__ == "__main__":
    main()
