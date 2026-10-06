#!/usr/bin/env python3
"""Gemma 4 agent runs in mini-SWE-agent 1.7.0 on SWE-bench Verified issues (spec/fresh-replication.md).

Uses mini-SWE-agent 1.7.0's DefaultAgent and its SWE-bench config (extra/swebench.yaml) unchanged. Two parts are
replaced because the lab server has no Docker: the environment is a writable Apptainer sandbox built from the same
SWE-bench image, and the model is Gemma 4 served by vLLM (no API cost, so cost tracking is off).

  python3 run_gemma_mini.py --issues pilot --out runs/pilot --workers 5
  python3 run_gemma_mini.py --issues order:200 --out runs/main --workers 8

Output (append-only, so a restarted job resumes and skips finished issues):
  <out>/run.json       one record per job start: job id, host, time, package versions, model revision, config, issues
  <out>/preds.jsonl    one row per finished issue (instance_id, model_patch, exit_status, n_calls, tokens, seconds)
  <out>/trajs/<iid>.json  full message history of that issue
  <out>/progress.json  done / remaining after each issue
Environment: APPTAINER, WORK (sandbox scratch), HF_HOME, VLLM_BASE (default http://127.0.0.1:18000/v1),
APPTAINER_EXEC_FLAGS (default "--fakeroot --ignore-subuid", the lab server; "" on MCSR Magnolia, whose fakeroot needs a
newer glibc than the images), APPTAINER_MOUNT_DIRS (comma-separated host paths the site binds into every container;
created inside each sandbox, e.g. "/ddnlus" on Magnolia).
"""
import argparse, concurrent.futures as cf, json, os, shutil, subprocess, threading, time, uuid
from dataclasses import dataclass, field

import yaml
from datasets import load_dataset
from minisweagent.agents.default import DefaultAgent
from minisweagent.config import builtin_config_dir
from minisweagent.models.litellm_model import LitellmModel

APPTAINER = os.environ.get("APPTAINER", "apptainer")
WORK = os.environ.get("WORK", os.path.abspath("work"))
EXEC_FLAGS = os.environ.get("APPTAINER_EXEC_FLAGS", "--fakeroot --ignore-subuid").split()
MOUNT_DIRS = [d for d in os.environ.get("APPTAINER_MOUNT_DIRS", "").split(",") if d]
HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "..", "data", "public", "swe-bench-verified-control-fresh", "sample.json")
LOCK = threading.Lock()


@dataclass
class SandboxConfig:
    image: str
    cwd: str = "/testbed"
    env: dict = field(default_factory=dict)
    timeout: int = 60


class ApptainerSandbox:
    """Writable Apptainer sandbox of a SWE-bench image; same execute() contract as mini-SWE-agent's environments."""

    def __init__(self, **kwargs):
        self.config = SandboxConfig(**kwargs)
        self.dir = os.path.join(WORK, f"agent-{uuid.uuid4().hex[:8]}")
        for attempt in range(3):  # builds from the shared image cache fail now and then when jobs build at once
            r = subprocess.run([APPTAINER, "build", "--sandbox", self.dir, self.config.image],
                               capture_output=True, text=True, timeout=1800)
            if not r.returncode:
                break
            shutil.rmtree(self.dir, ignore_errors=True)
            time.sleep(60)
        else:
            raise RuntimeError(f"sandbox build failed: {r.stderr[-500:]}")
        for m in MOUNT_DIRS:
            os.makedirs(os.path.join(self.dir, m.lstrip("/")), exist_ok=True)

    def execute(self, command: str, cwd: str = "") -> dict:
        cmd = [APPTAINER, "exec", *EXEC_FLAGS, "--contain", "--cleanenv", "--writable",
               "--pwd", cwd or self.config.cwd]
        for k, v in self.config.env.items():
            cmd += ["--env", f"{k}={v}"]
        cmd += [self.dir, "bash", "-c", command]
        r = subprocess.run(cmd, text=True, timeout=self.config.timeout, encoding="utf-8", errors="replace",
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = "\n".join(l for l in r.stdout.splitlines() if not l.startswith("INFO:    "))  # apptainer banner lines
        return {"output": out, "returncode": r.returncode}

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class VllmModel(LitellmModel):
    """LitellmModel without cost lookup (local model)."""

    def query(self, messages, **kwargs):
        response = self._query(messages, **kwargs)
        self.n_calls += 1
        u = getattr(response, "usage", None)
        self.tokens = getattr(self, "tokens", 0) + (getattr(u, "total_tokens", 0) or 0)
        return {"content": response.choices[0].message.content or ""}


def image(iid):
    return f"docker://swebench/sweb.eval.x86_64.{iid.replace('__', '_1776_')}:latest"


def run_one(inst, cfg, out):
    iid, t0 = inst["instance_id"], time.time()
    model = VllmModel(model_name="hosted_vllm/gemma4-qat",
                      model_kwargs={"api_base": os.environ.get("VLLM_BASE", "http://127.0.0.1:18000/v1"),
                                    "api_key": "none", **cfg.get("model", {}).get("model_kwargs", {})})
    env = agent = None
    try:
        env = ApptainerSandbox(**(cfg.get("environment", {}) | {"image": image(iid)}))
        agent = DefaultAgent(model, env, **cfg.get("agent", {}))
        status, result = agent.run(inst["problem_statement"])
    except Exception as e:  # recorded like mini-SWE-agent's own runner
        status, result = type(e).__name__, str(e)
    finally:
        if env:
            env.cleanup()
    row = dict(instance_id=iid, model_patch=result if status == "Submitted" else "", exit_status=status,
               n_calls=model.n_calls, tokens=getattr(model, "tokens", 0), seconds=round(time.time() - t0))
    if status != "Submitted":
        row["error"] = str(result)[-1000:]
    with LOCK:
        json.dump(dict(row, messages=agent.messages if agent else []), open(os.path.join(out, "trajs", f"{iid}.json"), "w"))
        with open(os.path.join(out, "preds.jsonl"), "a") as f:
            f.write(json.dumps(row) + "\n")
    print(iid, status, f"calls={model.n_calls}", f"{row['seconds']}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issues", required=True,
                    help="'pilot', 'order:N' (first N of the fixed order), 'order:A-B' (positions A..B-1, to split "
                         "one sample over several jobs), 'ids-file:path' (JSON list of ids) or 'ids:a,b' (smoke tests "
                         "only; sbatch --export splits on commas, so use ids-file in job variables)")
    ap.add_argument("--step-limit", type=int, help="smoke tests only; the spec's runs keep the config's 250")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    s = json.load(open(SAMPLE))
    if a.issues.startswith("ids-file:"):
        ids = json.load(open(a.issues[9:]))
    elif a.issues.startswith("ids:"):
        ids = a.issues[4:].split(",")
    else:
        rng = a.issues.split(":")[1] if a.issues != "pilot" else ""
        lo, hi = (map(int, rng.split("-")) if "-" in rng else (0, int(rng or 0)))
        ids = s["pilot"] if a.issues == "pilot" else s["order"][lo:hi]
    os.makedirs(os.path.join(a.out, "trajs"), exist_ok=True)
    done = set()
    if os.path.exists(os.path.join(a.out, "preds.jsonl")):
        done = {json.loads(l)["instance_id"] for l in open(os.path.join(a.out, "preds.jsonl"))}
    cfg = yaml.safe_load((builtin_config_dir / "extra" / "swebench.yaml").read_text())
    if a.step_limit:
        cfg.setdefault("agent", {})["step_limit"] = a.step_limit
    insts = {r["instance_id"]: r for r in load_dataset("princeton-nlp/SWE-bench_Verified", split="test")}
    todo = [insts[i] for i in ids if i not in done]
    print(f"{len(todo)} to run ({len(done)} already done)", flush=True)
    import importlib.metadata as md, socket
    start = dict(started=time.strftime("%Y-%m-%dT%H:%M:%S%z"), job=os.environ.get("SLURM_JOB_ID"), host=socket.gethostname(),
                 args=vars(a), issues=ids, already_done=sorted(done), config=cfg,
                 model=dict(name="google/gemma-4-31B-it-qat-w4a16-ct", revision=os.environ.get("MODEL_REVISION")),
                 versions={p: md.version(p) for p in ["mini-swe-agent", "litellm", "vllm", "swebench"] if _has(md, p)},
                 env={k: os.environ.get(k) for k in ["APPTAINER_EXEC_FLAGS", "APPTAINER_MOUNT_DIRS", "VLLM_BASE"]})
    with open(os.path.join(a.out, "run.json"), "a") as f:
        f.write(json.dumps(start) + "\n")

    def one(inst):
        run_one(inst, cfg, a.out)
        with LOCK:
            fin = {json.loads(l)["instance_id"] for l in open(os.path.join(a.out, "preds.jsonl"))}
            json.dump(dict(updated=time.strftime("%Y-%m-%dT%H:%M:%S%z"), done=len(fin & set(ids)), total=len(ids),
                           remaining=[i for i in ids if i not in fin]), open(os.path.join(a.out, "progress.json"), "w"))

    with cf.ThreadPoolExecutor(a.workers) as pool:
        list(pool.map(one, todo))


def _has(md, p):
    try:
        md.version(p)
        return True
    except md.PackageNotFoundError:
        return False


if __name__ == "__main__":
    main()
