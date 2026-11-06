#!/usr/bin/env python3
"""Gemma 4 agent runs in mini-SWE-agent 2.0.0 on SWE-bench Multilingual issues (spec/multilingual-replication.md).

Runs mini-SWE-agent 2.0.0's own SWE-bench runner with the config saved by the public Multilingual runs
(data/public/swe-bench-multilingual/control_config.json). Two parts are replaced because the lab server has no Docker:
the environment is a writable Apptainer sandbox of the same image (ApptainerEnvironment, which keeps the saved
config's shell, `bash -lc`), and the model is Gemma 4 served by vLLM with tool calling (no API cost).

  python3 run_gemma_multilingual.py --issues smoke --out runs/ml-smoke --workers 3 [--thinking]
  python3 run_gemma_multilingual.py --issues order:0-300 --out runs/ml-main --workers 6

Output: mini-SWE-agent's own (<out>/preds.json, <out>/<iid>/<iid>.traj.json with the model-call count,
<out>/exit_statuses_*.yaml, <out>/minisweagent.log), plus <out>/config.yaml and <out>/run.json (one record per job
start: host, time, package versions, model revision, issues). Restarting with the same --out skips finished issues.
Environment: APPTAINER, WORK (sandbox scratch), VLLM_BASE (default http://127.0.0.1:18000/v1), MODEL_REVISION,
APPTAINER_EXEC_FLAGS (default "--fakeroot --ignore-subuid --no-home", the lab server), SIF_DIR (as in
eval_apptainer.py).
"""
import argparse, json, os, re, shlex, socket, subprocess, tempfile, time, urllib.request
import importlib.metadata as md

import yaml

WORK = os.environ.get("WORK", os.path.abspath("work"))
os.makedirs(WORK, exist_ok=True)
tempfile.tempdir = WORK  # mini-SWE-agent builds its sandboxes in the temp dir; keep them on the data disk

import minisweagent.environments as envs  # noqa: E402
from minisweagent.environments.singularity import SingularityEnvironment, SingularityEnvironmentConfig  # noqa: E402
from minisweagent.run.benchmarks import swebench  # noqa: E402

from eval_apptainer import local_image  # noqa: E402

APPTAINER = os.environ.get("APPTAINER", "apptainer")
# --no-home: --contain otherwise hides the image's /root, where Maven's and Go's caches are (as Docker does not)
EXEC_FLAGS = os.environ.get("APPTAINER_EXEC_FLAGS", "--fakeroot --ignore-subuid --no-home").split()
VLLM_BASE = os.environ.get("VLLM_BASE", "http://127.0.0.1:18000/v1")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "public", "swe-bench-multilingual")


class ApptainerEnvironmentConfig(SingularityEnvironmentConfig):
    interpreter: list[str] = ["bash", "-lc"]


class ApptainerEnvironment(SingularityEnvironment):
    """mini-SWE-agent's Singularity environment, running each command with the saved config's shell."""

    def __init__(self, **kwargs):
        # each image is pulled once into SIF_DIR (Docker Hub allows the lab server 100 pulls an hour)
        kwargs["image"] = local_image(kwargs["image"])
        super().__init__(config_class=ApptainerEnvironmentConfig, **kwargs)
        # Today's images source a conda script they do not contain from /root/.bashrc, so under `bash -lc` every output
        # starts with an error. The public runs' outputs never show it (smoke test, 2026-10-23), so drop such lines.
        rc = self.sandbox_dir / "root" / ".bashrc"
        if rc.exists():
            lines = rc.read_text().splitlines(keepends=True)
            keep = [l for l in lines if not ((m := re.match(r"\s*(?:source|\.)\s+(/\S+)", l))
                                             and not (self.sandbox_dir / m.group(1).lstrip("/")).exists())]
            if keep != lines:
                rc.write_text("".join(keep))

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict:
        # the parent runs `bash -c <command>`; the trajectory keeps the model's command unchanged
        command = shlex.join(self.config.interpreter) + " " + shlex.quote(action.get("command", ""))
        return super().execute(action | {"command": command}, cwd, timeout=timeout)

    def _check_finished(self, output: dict):
        # Images without /etc/localtime make Apptainer print this first in every output. Docker does not, and it hides
        # the submit marker, which mini-SWE-agent reads from the first line (pilot, 2026-11-06, terraform-34580). The
        # parent checks inside execute, so the line must go here, before the check.
        output["output"] = re.sub(r"(?m)^WARNING: Skipping mount .*\n", "", output.get("output", ""))
        super()._check_finished(output)

    def cleanup(self):
        if not hasattr(self, "sandbox_dir"):  # the build failed
            return
        # Go's module cache is read-only, so the parent's rmtree would leave the sandbox behind
        subprocess.run(["chmod", "-R", "u+rwX", str(self.sandbox_dir)], capture_output=True)
        super().cleanup()


# the runner sets the image ("docker://" + the Docker Hub name) only for the class it knows as "singularity"
envs._ENVIRONMENT_MAPPING["singularity"] = f"{__name__}.ApptainerEnvironment"


def build_config(thinking=False):
    saved = json.load(open(os.path.join(DATA, "control_config.json")))
    agent = {k: v for k, v in saved["agent"].items() if k != "output_path"}
    model = {k: v for k, v in saved["model"].items() if k not in ("model_name", "model_kwargs")}
    model |= dict(model_name="hosted_vllm/gemma4-qat", model_class="litellm",
                  model_kwargs=dict(drop_params=True, temperature=0.0, parallel_tool_calls=True, api_base=VLLM_BASE,
                                    api_key="none"))
    if thinking:  # Gemma 4's chat-template switch; with tools and thinking off it writes no text before a call
        model["model_kwargs"]["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}}
    env = {k: saved["environment"][k] for k in ("cwd", "env", "forward_env", "timeout", "interpreter")}
    env |= dict(environment_class="singularity", executable=APPTAINER, exec_args=["--contain", "--cleanenv", *EXEC_FLAGS])
    return dict(agent=agent, model=model, environment=env)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issues", required=True, help="'smoke', 'order:A-B' (positions A..B-1 of the fixed order) or 'ids:a,b'")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--thinking", action="store_true", help="switch on Gemma's thinking")
    a = ap.parse_args()
    iss = json.load(open(os.path.join(DATA, "issues.json")))
    if a.issues == "smoke":
        ids = iss["smoke"]
    elif a.issues.startswith("ids:"):
        ids = a.issues[4:].split(",")
    else:
        lo, hi = map(int, a.issues.split(":")[1].split("-"))
        ids = iss["order"][lo:hi]
    os.makedirs(a.out, exist_ok=True)
    cfg = build_config(a.thinking)
    cfg_path = os.path.join(a.out, "config.yaml")
    yaml.safe_dump(cfg, open(cfg_path, "w"), sort_keys=False)
    try:
        vllm = urllib.request.urlopen(VLLM_BASE.rsplit("/v1", 1)[0] + "/version", timeout=10).read().decode()
    except Exception as e:
        vllm = f"unavailable: {e}"
    start = dict(started=time.strftime("%Y-%m-%dT%H:%M:%S%z"), host=socket.gethostname(), args=vars(a), issues=ids,
                 dataset=dict(name=iss["dataset"], revision=iss["revision"]),
                 model=dict(name="google/gemma-4-31B-it-qat-w4a16-ct", revision=os.environ.get("MODEL_REVISION")),
                 vllm=vllm, versions={p: md.version(p) for p in ["mini-swe-agent", "litellm", "swebench"]},
                 env={k: os.environ.get(k) for k in ["APPTAINER", "APPTAINER_EXEC_FLAGS", "VLLM_BASE", "WORK"]})
    with open(os.path.join(a.out, "run.json"), "a") as f:
        f.write(json.dumps(start) + "\n")
    swebench.main(subset=os.path.join(DATA, "data"), split="test", slice_spec="",
                  filter_spec="^(" + "|".join(map(re.escape, ids)) + ")$", shuffle=False, output=a.out,
                  workers=a.workers, model=None, model_class=None, redo_existing=False, config_spec=[cfg_path],
                  environment_class=None)


if __name__ == "__main__":
    main()
