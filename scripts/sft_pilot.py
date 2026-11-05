#!/usr/bin/env python3
"""Capped SFT feasibility pilot (spec/sft-pilot.md). Does a small LoRA adapter, trained on execution labels, make
Gemma 4 31B separate failing from passing patches better than the same loaded model with the adapter switched off?

  prepare  (Mac, CPU)   labelled rows, issue-disjoint split, training selection        -> data/sft-pilot/
  smoke    (lab A100)   load, 4 training steps, 8 scored rows, memory, throughput, time projection -> OUT/smoke.json
  train    (lab A100)   one epoch of LoRA on the dequantized deployed checkpoint       -> OUT/adapter-<name>/
  score    (lab A100)   every dev and eval row, adapter off and each adapter on        -> OUT/scores.jsonl
  run      (lab A100)   train, then score, in one model load
  analyze  (Mac, CPU)   measures and the reading fixed in the spec                     -> stdout JSON

The answer format is the project's answer-only rating (Q_P0: "Answer with exactly one word: PASS or FAIL"), thinking
off. Score of a row = logit(PASS) - logit(FAIL) at the first answer token. Training loss (spec addendum 1) = binary
cross-entropy on that margin taken before Gemma's final logit cap (prompt tokens carry no loss). GPU subcommands read
only data/sft-pilot/rows.jsonl and the training file (--train), so the lab needs no other file from this repo.

  prepare-pool (Mac, CPU)  addendum 1: every training-pool row within the token limit   -> data/sft-pilot/train_pool.jsonl
"""
import argparse, hashlib, json, math, os, random, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "sft-pilot")
SALT = "sft-pilot-2026-11-04"
FRACTIONS = (("train", 0.40), ("dev", 0.20), ("eval", 0.40))
N_TRAIN_ISSUES = 64           # two rows per issue (one passing, one failing): 128 training rows
TRAIN_MAX_TOKENS = 6144       # training rows only; dev and eval rows are never filtered or truncated
ANSWER = {1: "PASS", 0: "FAIL"}
LORA = dict(r=16, lora_alpha=32, lora_dropout=0.05,
            target_modules=r".*language_model.*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)")
OPT = dict(lr=2e-5, grad_accum=4, warmup_steps=10, max_grad_norm=1.0, weight_decay=0.0, seed=0, epochs=2)  # addendum 1
# Run 1 (data/lab-runs/sft-pilot/run1): full-run tokens/s over the smoke test's tokens/s on its longest rows. The smoke
# test's time projection is multiplied by these, since the longest rows understate the speed of the whole set.
SPEED_RATIO = dict(train=451 / 406.1, score=1865 / 1406.8)
RETENTION = 0.90              # threshold keeps this share of dev passing patches
BOOT = 2000


def h(s):
    return hashlib.md5(f"{SALT}|{s}".encode()).hexdigest()


def md5_file(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


# ----------------------------------------------------------------------------------------------------------- prepare
def prepare(a):
    import collections
    sys.path.insert(0, HERE)
    import fresh_judging as fj
    from selfjudge_matrix import Q_P0, Q_P1
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.tokenizer)

    def last_parsed(path):
        d = {}
        for l in open(path):
            r = json.loads(l)
            if r.get("err") is None and r.get("parsed") is not None:
                d[r["pid"]] = r["parsed"]
        return d

    def logp(path):
        return {r["pid"]: r["logp100"] for r in map(json.loads, open(path))} if os.path.exists(path) else {}

    # held-out issues: Gemma's labels from Magnolia, other writers' from the control attempts (as fresh_judging.load)
    lab = fj.labels(["main-a", "main-b"])
    ctrl = {}
    for l in open(fj.CONTROL):
        c = json.loads(l)
        if c["resolved"] is not None:
            w = next(k for k in fj.WRITERS if k in c["writer"].lower())
            ctrl[fj.pid_of(c["instance_id"], w, fj.strip_tests(c["patch"] or ""))] = int(c["resolved"])
    NINE = ["gemma4-31b", "gpt-oss-20b", "qwen35-9b", "glm47-flash", "qwen3-coder", "gpt-oss-120b", "glm-4.5",
            "kimi-k2", "llama-4-maverick"]
    in957 = set(fj.load(NINE, ["main-a", "main-b"])[0])
    lite_y = {r["pid"]: r["y"] for r in map(json.loads, open(os.path.join(HERE, "..", "data", "public",
                                                                          "third-party-lite", "patches.jsonl")))}
    src = {"heldout": dict(prompts="heldout_p1.jsonl", gemma=last_parsed(os.path.join(HERE, "derived", "fresh_gemma4-31b.jsonl")),
                           logp=logp(os.path.join(HERE, "..", "data", "lab-runs", "probe", "score_hosted", "score.jsonl"))),
           "lite": dict(prompts="lite_p1.jsonl", gemma=last_parsed(os.path.join(HERE, "derived", "lite_gemma4-31b.jsonl")),
                        logp=logp(os.path.join(HERE, "..", "data", "lab-runs", "probe", "score_lite", "score.jsonl")))}
    rows, skipped = [], collections.Counter()
    for s, cfg in src.items():
        for r in map(json.loads, open(os.path.join(HERE, "..", "data", "judge-prompts", cfg["prompts"]))):
            if s == "heldout":
                y = lab.get(r["iid"]) if r["writer"] == "gemma-4-31b" else ctrl.get(r["pid"])
            else:
                y = lite_y.get(r["pid"])
            if y is None:
                skipped[s, "no_label"] += 1
                continue
            assert r["prompt"].endswith(Q_P1) and r["prompt"].count(Q_P1) == 1, r["pid"]
            p0 = r["prompt"][: -len(Q_P1)] + Q_P0
            msgs = [{"role": "system", "content": r["system"]}, {"role": "user", "content": p0}]
            n = len(tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, enable_thinking=False,
                                            return_dict=True)["input_ids"])
            rows.append(dict(id=f"{s}:{r['pid']}", set=s, pid=r["pid"], iid=r["iid"], writer=r["writer"], y=int(y),
                             own=int(r["writer"] == "gemma-4-31b"), in957=int(s == "heldout" and r["pid"] in in957),
                             gemma_score=cfg["gemma"].get(r["pid"]), gemma_logp100=cfg["logp"].get(r["pid"]),
                             n_tokens=n, system=r["system"], prompt=p0))
    # issue-disjoint split over the union of both sets (37 issues are in both; they stay together)
    issues = sorted({r["iid"] for r in rows}, key=h)
    split, k0 = {}, 0
    for i, (name, f) in enumerate(FRACTIONS):
        k1 = len(issues) if i == len(FRACTIONS) - 1 else k0 + round(f * len(issues))
        for iid in issues[k0:k1]:
            split[iid] = name
        k0 = k1
    for r in rows:
        r["split"] = split[r["iid"]]
    # training selection: training issues with a passing and a failing row of at most TRAIN_MAX_TOKENS tokens, in hash
    # order; per issue the failing row Gemma scored highest (the confident near miss) and a passing row by hash
    by = collections.defaultdict(list)
    for r in rows:
        if r["split"] == "train" and r["n_tokens"] <= TRAIN_MAX_TOKENS:
            by[r["iid"]].append(r)
    eligible = [i for i in sorted(by, key=h) if {r["y"] for r in by[i]} == {0, 1}]
    pairs = []
    for iid in eligible:
        fail = sorted((r for r in by[iid] if r["y"] == 0),
                      key=lambda r: (-(r["gemma_score"] if r["gemma_score"] is not None else -1), h(r["id"])))[0]
        pas = sorted((r for r in by[iid] if r["y"] == 1), key=lambda r: h(r["id"]))[0]
        pairs.append((iid, pas["id"], fail["id"]))
    chosen = pairs[:N_TRAIN_ISSUES]
    train = [dict(id=x, iid=iid, y=y) for iid, p, f in chosen for x, y in ((p, 1), (f, 0))]
    random.Random(OPT["seed"]).shuffle(train)
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "rows.jsonl"), "w") as fh:
        for r in sorted(rows, key=lambda r: (r["split"], h(r["id"]))):
            fh.write(json.dumps(r) + "\n")
    with open(os.path.join(DATA, "train.jsonl"), "w") as fh:
        for i, t in enumerate(train):
            fh.write(json.dumps(dict(order=i, **t)) + "\n")
    R = {r["id"]: r for r in rows}

    def stats(sel):
        n = sorted(r["n_tokens"] for r in sel)
        return dict(rows=len(sel), issues=len({r["iid"] for r in sel}), passing=sum(r["y"] for r in sel),
                    failing=sum(1 - r["y"] for r in sel), own=sum(r["own"] for r in sel),
                    own_stamped_failing=sum(1 for r in sel if r["own"] and r["y"] == 0 and r["gemma_score"] == 100),
                    own_stamped_passing=sum(1 for r in sel if r["own"] and r["y"] == 1 and r["gemma_score"] == 100),
                    other_stamped_failing=sum(1 for r in sel if not r["own"] and r["y"] == 0 and r["gemma_score"] == 100),
                    heldout=sum(r["set"] == "heldout" for r in sel), lite=sum(r["set"] == "lite" for r in sel),
                    tokens_mean=round(sum(n) / len(n)), tokens_p95=n[int(0.95 * (len(n) - 1))], tokens_max=n[-1],
                    tokens_total=sum(n))
    tr = [R[t["id"]] for t in train]
    man = dict(salt=SALT, fractions=dict(FRACTIONS), n_train_issues=N_TRAIN_ISSUES, train_max_tokens=TRAIN_MAX_TOKENS,
               tokenizer=os.path.abspath(a.tokenizer), skipped={f"{s}:{k}": v for (s, k), v in skipped.items()},
               splits={s: stats([r for r in rows if r["split"] == s]) for s, _ in FRACTIONS},
               train_selected=dict(stats(tr), failing_gemma_score_100=sum(1 for r in tr if r["y"] == 0 and r["gemma_score"] == 100),
                                   writers=dict(collections.Counter(r["writer"] for r in tr))),
               train_eligible_issues=len(eligible),
               train_rows_over_token_limit=sum(1 for r in rows if r["split"] == "train" and r["n_tokens"] > TRAIN_MAX_TOKENS),
               files={f: md5_file(os.path.join(DATA, f)) for f in ("rows.jsonl", "train.jsonl")})
    json.dump(man, open(os.path.join(DATA, "manifest.json"), "w"), indent=1)
    print(json.dumps(man, indent=1))


# --------------------------------------------------------------------------------------------------------- GPU side
def prepare_pool(a):
    """Addendum 1: train on the whole training pool. Every training-split row of at most TRAIN_MAX_TOKENS tokens,
    shuffled with the seed; reads only rows.jsonl."""
    rows = [json.loads(l) for l in open(os.path.join(a.data, "rows.jsonl"))]
    pool = sorted((r for r in rows if r["split"] == "train" and r["n_tokens"] <= TRAIN_MAX_TOKENS), key=lambda r: h(r["id"]))
    random.Random(OPT["seed"]).shuffle(pool)
    path = os.path.join(a.data, "train_pool.jsonl")
    with open(path, "w") as fh:
        for i, r in enumerate(pool):
            fh.write(json.dumps(dict(order=i, id=r["id"], iid=r["iid"], y=r["y"])) + "\n")
    print(json.dumps(dict(rows=len(pool), issues=len({r["iid"] for r in pool}), passing=sum(r["y"] for r in pool),
                          failing=sum(1 - r["y"] for r in pool), own=sum(r["own"] for r in pool),
                          tokens_total=sum(r["n_tokens"] for r in pool), tokens_max=max(r["n_tokens"] for r in pool),
                          dropped_over_limit=sum(1 for r in rows if r["split"] == "train" and r["n_tokens"] > TRAIN_MAX_TOKENS),
                          md5=md5_file(path)), indent=1))


def load_rows(data, train_file="train.jsonl"):
    rows = {r["id"]: r for r in map(json.loads, open(os.path.join(data, "rows.jsonl")))}
    train = [json.loads(l) for l in open(os.path.join(data, train_file))]
    return rows, train


def load_model(model_dir, device):
    import torch
    from transformers import (AutoConfig, AutoModelForCausalLM, AutoModelForImageTextToText, AutoTokenizer,
                              CompressedTensorsConfig)
    tok = AutoTokenizer.from_pretrained(model_dir)
    cfg = AutoConfig.from_pretrained(model_dir)
    q = {"quantization_config": CompressedTensorsConfig(run_compressed=False)} \
        if getattr(cfg, "quantization_config", None) else {}  # the 4-bit checkpoint, dequantized to bf16 weights
    cls = AutoModelForImageTextToText if any("ConditionalGeneration" in x for x in (cfg.architectures or [])) \
        else AutoModelForCausalLM
    model = cls.from_pretrained(model_dir, dtype=torch.bfloat16, device_map=device, attn_implementation="sdpa", **q)
    model.config.use_cache = False
    for p in model.parameters():
        p.requires_grad_(False)
    return tok, model, plain_linears(model)


def plain_linears(model):
    """LoRA wraps torch.nn.Linear. If dequantization left a Linear subclass (compressed-tensors) in the language model,
    swap it for a plain nn.Linear holding the same dense bf16 weight, so the adapter sees exactly the deployed values.
    Returns counts by class name, before the swap."""
    import collections, re, torch
    pat = re.compile(LORA["target_modules"])
    seen, swaps = collections.Counter(), []
    for name, m in model.named_modules():
        if pat.fullmatch(name):
            seen[type(m).__name__] += 1
            if type(m) is not torch.nn.Linear:
                assert isinstance(m, torch.nn.Linear), f"{name}: {type(m)} is not a Linear"
                assert m.weight.dtype == torch.bfloat16 and m.weight.dim() == 2, f"{name}: weight {m.weight.dtype}"
                swaps.append(name)
    for name in swaps:
        parent, child = name.rsplit(".", 1)
        old = model.get_submodule(name)
        new = torch.nn.Linear(old.in_features, old.out_features, bias=old.bias is not None,
                              device=old.weight.device, dtype=old.weight.dtype)
        new.weight.data = old.weight.data
        if old.bias is not None:
            new.bias.data = old.bias.data
        new.requires_grad_(False)
        setattr(model.get_submodule(parent), child, new)
    assert sum(seen.values()) > 0, "no LoRA target module found"
    return dict(seen)


def chat_ids(tok, r):
    msgs = [{"role": "system", "content": r["system"]}, {"role": "user", "content": r["prompt"]}]
    return tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, enable_thinking=False,
                                   return_dict=True, return_tensors="pt")["input_ids"]


def answer_ids(tok):
    ids = {y: tok(w, add_special_tokens=False).input_ids for y, w in ANSWER.items()}
    assert all(len(v) == 1 for v in ids.values()) and ids[0] != ids[1], ids
    return {y: v[0] for y, v in ids.items()}


def last_logits(model, ids, ans):
    """Logits at the last position: (the model's own, after Gemma's final cap of 30; PASS and FAIL before the cap).
    The uncapped pair is computed in float32 from the output head's input and its two rows, so it has no bf16 steps
    and no saturation. `ans` is answer_ids(tok)."""
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    head = base.get_output_embeddings()
    seen = []
    hook = head.register_forward_hook(lambda m, inp, out: seen.append(inp[0]))
    try:
        capped = model(input_ids=ids, use_cache=False, logits_to_keep=1).logits[0, -1].float()
    finally:
        hook.remove()
    hid = seen[-1][0, -1].float()
    pre = hid @ head.weight[[ans[1], ans[0]]].float().T
    if head.bias is not None:
        pre = pre + head.bias[[ans[1], ans[0]]].float()
    return capped, pre  # pre[0] = PASS, pre[1] = FAIL


def wrap(model):
    from peft import LoraConfig, get_peft_model
    cfg = LoraConfig(task_type="CAUSAL_LM", bias="none", **LORA)
    pm = get_peft_model(model, cfg)
    n_train = sum(p.numel() for p in pm.parameters() if p.requires_grad)
    return pm, n_train


def train_loop(a, tok, model, rows, train, out, max_steps=None):
    """One epoch, batch of one row, gradient accumulation OPT['grad_accum']; returns the PEFT model and a summary."""
    import torch
    torch.manual_seed(OPT["seed"]); random.seed(OPT["seed"])
    pm, n_trainable = wrap(model)
    pm.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    pm.enable_input_require_grads()
    pm.train()
    params = [p for p in pm.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=OPT["lr"], weight_decay=OPT["weight_decay"])
    steps = math.ceil(len(train) * OPT["epochs"] / OPT["grad_accum"])
    w = OPT["warmup_steps"]  # linear warm-up, then linear decay to 0 at the last optimizer step
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / w if s < w else max(0.0, (steps - s) / max(1, steps - w)))
    ans = answer_ids(tok)
    labels = a.labels if getattr(a, "labels", None) else {t["id"]: t["y"] for t in train}
    log = open(os.path.join(out, f"train_log_{a.name}.jsonl"), "a")
    t0, toks, step = time.time(), 0, 0
    seq = [t for _ in range(OPT["epochs"]) for t in train]
    if max_steps:
        seq = seq[: max_steps * OPT["grad_accum"]]
    dev = next(pm.parameters()).device
    for i, t in enumerate(seq):
        r = rows[t["id"]]
        ids = chat_ids(tok, r).to(dev)
        y = labels[t["id"]]
        logits, pre = last_logits(pm, ids, ans)
        margin = pre[0] - pre[1]  # before the cap: raising both logits does not lower the loss (addendum 1)
        loss = torch.nn.functional.binary_cross_entropy_with_logits(margin[None], torch.tensor([float(y)], device=margin.device))
        (loss / OPT["grad_accum"]).backward()
        toks += ids.shape[1]
        rec = dict(i=i, id=t["id"], y=y, n_tokens=int(ids.shape[1]), loss=float(loss),
                   margin=float(logits[ans[1]] - logits[ans[0]]), margin_precap=float(margin),
                   logit_pass=float(logits[ans[1]]), logit_fail=float(logits[ans[0]]), sec=round(time.time() - t0, 2))
        if (i + 1) % OPT["grad_accum"] == 0 or i == len(seq) - 1:
            gn = torch.nn.utils.clip_grad_norm_(params, OPT["max_grad_norm"])
            opt.step(); sched.step(); opt.zero_grad(set_to_none=True); step += 1
            rec.update(step=step, grad_norm=float(gn), lr=sched.get_last_lr()[0])
        if torch.cuda.is_available():
            rec["max_mem_gb"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
        log.write(json.dumps(rec) + "\n"); log.flush()
        if i % 8 == 0:
            print(f"train {a.name} {i + 1}/{len(seq)} loss {loss.item():.3f} {time.time() - t0:.0f}s", flush=True)
    pm.eval()
    return pm, dict(rows=len(seq), optimizer_steps=step, tokens=toks, seconds=round(time.time() - t0, 1),
                    tokens_per_sec=round(toks / max(1e-9, time.time() - t0), 1), trainable_params=n_trainable)


def score_rows(tok, pm, rows, ids_, out, conditions, limit=None):
    """For every row: logits of PASS and FAIL under each condition, a (label, adapter name) pair; adapter name None
    means the adapter switched off (the untuned control, same loaded weights). Resumes from OUT/scores.jsonl."""
    import torch
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "scores.jsonl")
    done = {(r["id"], r["cond"]) for r in map(json.loads, open(path))} if os.path.exists(path) else set()
    ans = answer_ids(tok)
    fh = open(path, "a")
    t0, toks, n = time.time(), 0, 0
    dev = next(pm.parameters()).device
    for k, rid in enumerate(ids_[:limit] if limit else ids_):
        r = rows[rid]
        ids = None
        for cond, adapter in conditions:
            if (rid, cond) in done:
                continue
            if ids is None:
                ids = chat_ids(tok, r).to(dev)
            with torch.no_grad():
                if adapter is None:
                    with pm.disable_adapter():
                        lg, pre = last_logits(pm, ids, ans)
                else:
                    pm.set_adapter(adapter)
                    lg, pre = last_logits(pm, ids, ans)
            lp = torch.log_softmax(lg, -1)
            fh.write(json.dumps(dict(id=rid, cond=cond, logit_pass=float(lg[ans[1]]), logit_fail=float(lg[ans[0]]),
                                     logp_pass=float(lp[ans[1]]), logp_fail=float(lp[ans[0]]),
                                     pre_pass=float(pre[0]), pre_fail=float(pre[1]),
                                     top_token=int(lg.argmax()), n_tokens=int(ids.shape[1]))) + "\n")
            fh.flush(); toks += ids.shape[1]; n += 1
        if (k + 1) % 100 == 0:
            print(f"score {k + 1}/{len(ids_)} {time.time() - t0:.0f}s", flush=True)
    return dict(forward_passes=n, tokens=toks, seconds=round(time.time() - t0, 1),
                tokens_per_sec=round(toks / max(1e-9, time.time() - t0), 1))


def score_order(rows):
    return [rid for rid, r in sorted(rows.items(), key=lambda kv: (kv[1]["split"] != "dev", h(kv[0])))
            if r["split"] in ("dev", "eval")]


def env_info(a):
    import importlib.metadata as md, platform, torch
    v = {}
    for p in ("torch", "transformers", "peft", "compressed-tensors", "accelerate", "safetensors"):
        try:
            v[p] = md.version(p)
        except md.PackageNotFoundError:
            v[p] = None
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    return dict(versions=v, python=platform.python_version(), gpu=gpu, model=os.path.abspath(a.model),
                script_md5=md5_file(os.path.abspath(__file__)), rows_md5=md5_file(os.path.join(a.data, "rows.jsonl")),
                train_file=a.train, train_md5=md5_file(os.path.join(a.data, a.train)), lora=LORA, opt=OPT,
                started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


def write_json(path, obj):
    with open(path, "a") as fh:
        fh.write(json.dumps(obj) + "\n")


def gpu(a):
    import torch
    os.makedirs(a.out, exist_ok=True)
    info = env_info(a); info["cmd"] = a.cmd; info["argv"] = sys.argv
    t0 = time.time()
    tok, model, linears = load_model(a.model, a.device)
    info["load_seconds"] = round(time.time() - t0, 1); info["lora_target_classes"] = linears
    if torch.cuda.is_available():
        info["mem_after_load_gb"] = round(torch.cuda.memory_allocated() / 2**30, 2)
    print(f"loaded in {info['load_seconds']}s; targets {linears}", flush=True)
    rows, train = load_rows(a.data, a.train)
    order = score_order(rows)
    if a.cmd == "smoke":  # the longest rows, so peak memory and a conservative speed are what get measured
        a.name = "smoke"
        longest = sorted(train, key=lambda t: -rows[t["id"]]["n_tokens"])
        pm, tr = train_loop(a, tok, model, rows, longest, a.out, max_steps=4)
        sc = score_rows(tok, pm, rows, sorted(order, key=lambda i: -rows[i]["n_tokens"]),
                        os.path.join(a.out, "smoke-scores"), [("off", None), ("on", "default")], limit=8)
        ans = answer_ids(tok)
        sm = [json.loads(l) for l in open(os.path.join(a.out, "smoke-scores", "scores.jsonl"))]
        info["format_ok_off"] = sum(r["top_token"] in ans.values() for r in sm if r["cond"] == "off")
        info["finite_scores"] = all(math.isfinite(r["logit_pass"]) and math.isfinite(r["logit_fail"]) for r in sm)
        info["train_loss_finite"] = all(math.isfinite(json.loads(l)["loss"])
                                        for l in open(os.path.join(a.out, "train_log_smoke.jsonl")))
        # projection for the full run, from the measured throughput (spec: engineering stop if over the cap)
        tr_tokens = sum(rows[t["id"]]["n_tokens"] for t in train) * OPT["epochs"]
        sc_tokens = sum(rows[i]["n_tokens"] for i in order) * 2
        proj = info["load_seconds"] + tr_tokens / (tr["tokens_per_sec"] * SPEED_RATIO["train"]) \
            + sc_tokens / (sc["tokens_per_sec"] * SPEED_RATIO["score"])
        info.update(train=tr, score=sc, projected_run_hours=round(proj / 3600, 2),
                    max_mem_gb=round(torch.cuda.max_memory_allocated() / 2**30, 2) if torch.cuda.is_available() else None,
                    longest_eval_row_tokens=max(rows[i]["n_tokens"] for i in order))
        json.dump(info, open(os.path.join(a.out, "smoke.json"), "w"), indent=1)
        print("SMOKE " + json.dumps({k: info[k] for k in ("projected_run_hours", "max_mem_gb", "format_ok_off",
                                                           "finite_scores", "train_loss_finite")}), flush=True)
        return
    if a.cmd in ("train", "run"):
        if a.shuffled:  # label-shuffled control: same rows, labels permuted with a fixed seed (balance preserved)
            ys = [t["y"] for t in train]; random.Random(1).shuffle(ys)
            a.labels = {t["id"]: y for t, y in zip(train, ys)}
            info["shuffled_label_agreement"] = sum(y == t["y"] for t, y in zip(train, ys)) / len(train)
        pm, tr = train_loop(a, tok, model, rows, train, a.out)
        pm.save_pretrained(os.path.join(a.out, f"adapter-{a.name}"))  # PEFT's adapter name inside is "default"
        info["train"] = tr
        print(f"TRAIN_DONE {json.dumps(tr)}", flush=True)
        conds = [("off", None), ("on" if a.name == "default" else a.name, "default")]
    if a.cmd == "score":  # --adapter LABEL=DIR, repeatable; the score label is LABEL
        from peft import PeftModel
        pm, conds = None, [("off", None)]
        for label, d in (x.split("=", 1) for x in a.adapter):
            if pm is None:
                pm = PeftModel.from_pretrained(model, d, adapter_name=label)
            else:
                pm.load_adapter(d, adapter_name=label)
            conds.append((label, label))
        pm.eval()
    if a.cmd in ("score", "run"):
        info["score"] = score_rows(tok, pm, rows, order, a.out, conds)
        print(f"SCORE_DONE {json.dumps(info['score'])}", flush=True)
    info["ended_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_json(os.path.join(a.out, "run.json"), info)


# ----------------------------------------------------------------------------------------------------------- analyze
def analyze(a):
    import numpy as np
    from sklearn.metrics import roc_auc_score
    rows, _ = load_rows(a.data)
    S = {}
    for r in map(json.loads, open(a.scores)):
        S.setdefault(r["cond"], {})[r["id"]] = (r["pre_pass"] - r["pre_fail"]) if a.precap else (r["logit_pass"] - r["logit_fail"])
    conds = [c for c in S if c != "off"]
    ids = [i for i in score_order(rows) if all(i in S[c] for c in S)]
    missing = len(score_order(rows)) - len(ids)
    R = {i: rows[i] for i in ids}
    y = np.array([R[i]["y"] for i in ids]); g = np.array([R[i]["iid"] for i in ids])
    sp = np.array([R[i]["split"] for i in ids]); own = np.array([R[i]["own"] for i in ids], bool)
    gs = np.array([R[i]["gemma_score"] if R[i]["gemma_score"] is not None else np.nan for i in ids], float)
    lp = np.array([R[i]["gemma_logp100"] if R[i]["gemma_logp100"] is not None else np.nan for i in ids], float)
    stamped = gs == 100
    sets = np.array([R[i]["set"] for i in ids])
    scores = {c: np.array([S[c][i] for i in ids]) for c in S}
    scores["paper_written_score"] = gs
    scores["paper_logp100"] = lp
    dev, ev = sp == "dev", sp == "eval"

    def thr(s):  # dev threshold that keeps RETENTION of dev passing patches (accept if score >= t)
        m = dev & (y == 1) & ~np.isnan(s)
        return float(np.quantile(s[m], 1 - RETENTION, method="lower"))

    T = {c: thr(s) for c, s in scores.items()}

    def far(s, t, idx):
        f = idx & (y == 0) & ~np.isnan(s); p = idx & (y == 1) & ~np.isnan(s)
        return (float((s[f] >= t).mean()) if f.any() else np.nan, float((s[p] >= t).mean()) if p.any() else np.nan)

    def auroc(s, idx):
        m = idx & ~np.isnan(s)
        return float(roc_auc_score(y[m], s[m])) if len(set(y[m])) == 2 else np.nan

    def pairs(idx):
        P = []
        for k in np.unique(g[idx]):
            w = np.where(idx & (g == k))[0]
            P += [(i, j) for i in w[y[w] == 1] for j in w[y[w] == 0]]
        return np.array(P, int).reshape(-1, 2)

    def pair_acc(s, P):
        if len(P) == 0:
            return np.nan
        d = s[P[:, 0]] - s[P[:, 1]]
        return float(((d > 0) + 0.5 * (d == 0)).mean())

    def oracle_far(s, idx):  # threshold-free ROC point on the eval set itself, secondary
        m = idx & ~np.isnan(s)
        t = float(np.quantile(s[m & (y == 1)], 1 - RETENTION, method="lower"))
        return float((s[m & (y == 0)] >= t).mean())

    def measures(idx_mask, P):
        out = {}
        for c, s in scores.items():
            f, rt = far(s, T[c], idx_mask)
            out[c] = dict(false_accept=f, pass_retained=rt, auroc=auroc(s, idx_mask), pair_accuracy=pair_acc(s, P),
                          false_accept_at_eval_90=oracle_far(s, idx_mask) if not np.isnan(s[idx_mask]).all() else np.nan,
                          mean_p_pass_fail=float(np.nanmean(1 / (1 + np.exp(-s[idx_mask & (y == 0)])))) if c in S else None,
                          mean_p_pass_pass=float(np.nanmean(1 / (1 + np.exp(-s[idx_mask & (y == 1)])))) if c in S else None,
                          says_pass_fail=float(np.nanmean(s[idx_mask & (y == 0)] > 0)) if c in S else None,
                          says_pass_pass=float(np.nanmean(s[idx_mask & (y == 1)] > 0)) if c in S else None)
        return out

    rng = np.random.default_rng(0)
    iss = np.unique(g[ev]); pos = {k: np.where(ev & (g == k))[0] for k in iss}

    def boot(fn):
        vals = []
        for _ in range(BOOT):
            pick = rng.choice(iss, len(iss))
            idx = np.concatenate([pos[k] for k in pick])
            vals.append(fn(idx))
        v = np.array(vals, float)
        return [round(float(x), 3) for x in np.nanpercentile(v, [2.5, 97.5])]

    def diff_fns(c, base):
        s1, s0 = scores[c], scores[base]

        def dfar(idx, mask=None):
            f = idx[(y[idx] == 0) & (True if mask is None else mask[idx])]
            return float((s1[f] >= T[c]).mean() - (s0[f] >= T[base]).mean()) if len(f) else np.nan

        def dauc(idx):
            yy = y[idx]
            return float(roc_auc_score(yy, s1[idx]) - roc_auc_score(yy, s0[idx])) if len(set(yy)) == 2 else np.nan

        def dpair(idx):
            # pairs inside resampled issues; a duplicated issue contributes its pairs twice
            P = []
            for k in np.unique(g[idx]):
                w = np.where(ev & (g == k))[0]; m = int((g[idx] == k).sum() // max(1, len(w)))
                P += [(i, j) for i in w[y[w] == 1] for j in w[y[w] == 0]] * m
            P = np.array(P, int).reshape(-1, 2)
            return pair_acc(s1, P) - pair_acc(s0, P) if len(P) else np.nan
        return dfar, dauc, dpair

    Pev = pairs(ev)
    res = dict(n=dict(scored=len(ids), missing=missing, eval_rows=int(ev.sum()), eval_issues=len(iss),
                      eval_failing=int((ev & (y == 0)).sum()), eval_passing=int((ev & (y == 1)).sum()),
                      eval_pairs=len(Pev), eval_issues_with_pair=len({g[i] for i, _ in Pev}),
                      eval_own_stamped_failing=int((ev & own & stamped & (y == 0)).sum()),
                      eval_own_stamped_passing=int((ev & own & stamped & (y == 1)).sum())),
               thresholds=T, eval=measures(ev, Pev))
    res["primary"] = {}
    for c in conds:
        dfar, dauc, dpair = diff_fns(c, "off")
        e = res["eval"]
        d = dict(false_accept_diff=e[c]["false_accept"] - e["off"]["false_accept"], false_accept_diff_ci95=boot(dfar),
                 pair_accuracy_diff=e[c]["pair_accuracy"] - e["off"]["pair_accuracy"], pair_accuracy_diff_ci95=boot(dpair),
                 auroc_diff=e[c]["auroc"] - e["off"]["auroc"], auroc_diff_ci95=boot(dauc),
                 pass_retained_adapter=e[c]["pass_retained"],
                 # addendum 1, named secondary: Gemma's own failing patches that it scored 100 as reader
                 own_stamped_false_accept_diff=dfar(np.where(ev)[0], own & stamped),
                 own_stamped_false_accept_diff_ci95=boot(lambda idx: dfar(idx, own & stamped)),
                 distinct_scores={k: int(len(np.unique(scores[k][ev]))) for k in (c, "off")})
        improves = (d["false_accept_diff"] <= -0.10 and d["false_accept_diff_ci95"][1] < 0
                    and d["pass_retained_adapter"] >= 0.85 and d["pair_accuracy_diff_ci95"][0] > 0)
        null = d["false_accept_diff_ci95"][0] <= 0 <= d["false_accept_diff_ci95"][1] and \
            d["pair_accuracy_diff_ci95"][0] <= 0 <= d["pair_accuracy_diff_ci95"][1]
        d["reading"] = "improves verification" if improves else ("no measurable improvement" if null else "inconclusive")
        res["primary"][c] = d
    if "shuffled" in conds and "on" in conds:
        dfar, dauc, dpair = diff_fns("on", "shuffled")
        res["labels_vs_shuffled"] = dict(false_accept_diff_ci95=boot(dfar), pair_accuracy_diff_ci95=boot(dpair),
                                         auroc_diff_ci95=boot(dauc))
    slices = {"own": ev & own, "other_writers": ev & ~own, "heldout_set": ev & (sets == "heldout"),
              "lite_set": ev & (sets == "lite"), "stamped": ev & stamped, "own_stamped": ev & own & stamped}
    res["slices"] = {k: dict(rows=int(m.sum()), failing=int((m & (y == 0)).sum()), measures=measures(m, pairs(m)))
                     for k, m in slices.items()}
    res["dev"] = measures(dev, pairs(dev))

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [clean(v) for v in o]
        if isinstance(o, float):
            return None if math.isnan(o) else round(o, 4)
        return o
    print(json.dumps(clean(res), indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--tokenizer", required=True)
    for c in ("smoke", "train", "score", "run"):
        p = sub.add_parser(c)
        p.add_argument("--model", required=True); p.add_argument("--data", default=DATA); p.add_argument("--out", required=True)
        p.add_argument("--device", default="cuda"); p.add_argument("--name", default="default")
        p.add_argument("--train", default="train.jsonl", help="training file inside --data")
        p.add_argument("--shuffled", action="store_true", help="label-shuffled control adapter")
        p.add_argument("--adapter", action="append", default=[], help="score: name=dir (repeatable)")
    p = sub.add_parser("analyze"); p.add_argument("--data", default=DATA); p.add_argument("--scores", required=True)
    p.add_argument("--precap", action="store_true", help="score = margin before the logit cap (addendum 1, secondary)")
    p = sub.add_parser("prepare-pool"); p.add_argument("--data", default=DATA)
    a = ap.parse_args()
    {"prepare": prepare, "prepare-pool": prepare_pool, "analyze": analyze}.get(a.cmd, gpu)(a)


if __name__ == "__main__":
    main()
