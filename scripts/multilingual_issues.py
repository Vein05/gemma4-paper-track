#!/usr/bin/env python3
"""SWE-bench Multilingual issues and public control patches for spec/multilingual-replication.md. No model calls.

  issues: language per issue, the smoke-test issues (one per language, random.Random(0) over sorted ids) and a fixed
          random order of all issues (seed 0) -> data/public/swe-bench-multilingual/issues.json
  controls: patch.diff and report.json of the four open-weight mini-SWE-agent 2.0.0 entries for every issue (public
          swe-bench-submissions bucket), with the model-call count from each entry's per_instance_details.json
          -> data/public/swe-bench-multilingual/attempts.jsonl; the saved config of GLM-5's run -> control_config.json
"""
import argparse, concurrent.futures as cf, json, os, random, urllib.request

import numpy as np
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "public", "swe-bench-multilingual")
DATA = os.path.join(OUT, "data", "test-00000-of-00001.parquet")
REVISION = "846e647b9f33c0b51b739d005d13d85493c9af09"
BUCKET = "https://swe-bench-submissions.s3.amazonaws.com/multilingual"
EXPERIMENTS = "https://raw.githubusercontent.com/SWE-bench/experiments/main/evaluation/multilingual"
ENTRIES = ["20260213_mini-v2.0.0a0_glm-5", "20260213_mini-v2.0.0a0_kimi-k2-5", "20260213_mini-v2.0.0a0_deepseek-3-2",
           "20260216_mini-v2.0.0a0_minimax-2-5"]
# repositories per language; the counts match the dataset card (Ruby 44, Rust 43, PHP 43, Java 43, Go 42, C 30,
# JavaScript 26, TypeScript 17, C++ 12)
LANGUAGE = {r: lang for lang, repos in {
    "C": ["jqlang/jq", "micropython/micropython", "redis/redis", "valkey-io/valkey"],
    "C++": ["fmtlib/fmt", "nlohmann/json"],
    "Go": ["caddyserver/caddy", "gin-gonic/gin", "gohugoio/hugo", "hashicorp/terraform", "prometheus/prometheus"],
    "Java": ["apache/druid", "apache/lucene", "google/gson", "javaparser/javaparser", "projectlombok/lombok",
             "reactivex/rxjava"],
    "JavaScript": ["axios/axios", "preactjs/preact", "mrdoob/three.js"],
    "TypeScript": ["babel/babel", "facebook/docusaurus", "immutable-js/immutable-js", "vuejs/core"],
    "PHP": ["briannesbitt/carbon", "laravel/framework", "php-cs-fixer/php-cs-fixer", "phpoffice/phpspreadsheet"],
    "Ruby": ["faker-ruby/faker", "fastlane/fastlane", "fluent/fluentd", "jekyll/jekyll", "jordansissel/fpm",
             "rubocop/rubocop"],
    "Rust": ["astral-sh/ruff", "burntsushi/ripgrep", "nushell/nushell", "sharkdp/bat", "tokio-rs/axum",
             "tokio-rs/tokio", "uutils/coreutils"],
}.items() for r in repos}


def get(url):
    for _ in range(3):
        try:
            return urllib.request.urlopen(url, timeout=60).read().decode()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):  # the bucket answers 403 for a missing file
                return None
        except Exception:
            pass
    return None


def download(_):
    """The dataset file at the pinned revision."""
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    url = (f"https://huggingface.co/datasets/SWE-bench/SWE-bench_Multilingual/resolve/{REVISION}/data/"
           "test-00000-of-00001.parquet")
    urllib.request.urlretrieve(url, DATA)
    print(DATA)


def issues(_):
    t = pq.read_table(DATA, columns=["instance_id", "repo"]).to_pylist()
    lang = {r["instance_id"]: LANGUAGE[r["repo"]] for r in t}
    by_lang = {}
    for i in sorted(lang):
        by_lang.setdefault(lang[i], []).append(i)
    rng = random.Random(0)
    smoke = [rng.choice(by_lang[l]) for l in sorted(by_lang)]
    ids = sorted(lang)
    order = [ids[k] for k in np.random.default_rng(0).permutation(len(ids))]
    json.dump(dict(dataset="SWE-bench/SWE-bench_Multilingual", revision=REVISION, language=lang, smoke=smoke,
                   order=order), open(os.path.join(OUT, "issues.json"), "w"), indent=1)
    print({l: len(v) for l, v in by_lang.items()}, "smoke", smoke)


def controls(_):
    ids = sorted(json.load(open(os.path.join(OUT, "issues.json")))["language"])
    calls = {e: json.loads(get(f"{EXPERIMENTS}/{e}/per_instance_details.json")) for e in ENTRIES}

    def one(job):
        e, iid = job
        patch, rep = get(f"{BUCKET}/{e}/logs/{iid}/patch.diff"), get(f"{BUCKET}/{e}/logs/{iid}/report.json")
        source = "patch.diff"
        if patch is None:  # most GLM-5 logs have no patch.diff (403); the run's submission equals it where both exist
            t = get(f"{BUCKET}/{e}/trajs/{iid}/{iid}.traj.json")
            patch, source = (json.loads(t)["info"].get("submission"), "traj submission") if t else (None, None)
        r = json.loads(rep) if rep else {}
        d = calls[e].get(iid, {})
        return dict(writer=e, instance_id=iid, patch=patch, patch_source=source, resolved=r.get(iid, r).get("resolved"),
                    resolved_details=d.get("resolved"), api_calls=d.get("api_calls"))

    with cf.ThreadPoolExecutor(32) as pool, open(os.path.join(OUT, "attempts.jsonl"), "w") as f:
        rows = list(pool.map(one, [(e, i) for e in ENTRIES for i in ids]))
        for r in rows:
            f.write(json.dumps(r) + "\n")
    t = json.loads(get(f"{BUCKET}/{ENTRIES[0]}/trajs/{ids[0]}/{ids[0]}.traj.json"))
    json.dump(t["info"]["config"], open(os.path.join(OUT, "control_config.json"), "w"), indent=1)
    for e in ENTRIES:
        rs = [r for r in rows if r["writer"] == e]
        print(e, "patches", sum(bool(r["patch"]) for r in rs), "pass", sum(r["resolved"] is True for r in rs),
              "fail", sum(r["resolved"] is False for r in rs),
              "label disagrees with details", sum(r["resolved"] != r["resolved_details"] for r in rs))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["download", "issues", "controls"])
    a = ap.parse_args()
    {"download": download, "issues": issues, "controls": controls}[a.cmd](a)
