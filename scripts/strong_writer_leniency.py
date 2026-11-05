#!/usr/bin/env python3
"""Exploratory (2026-11-04, chosen after per_writer_leniency_2026-11-01.json was seen): is Gemma 4 31B lenient on its
own failing patches beyond writers at least as strong as it (pass rate >= Gemma's), and beyond other writers' failing
patches the outside judges score the same (panel-mean quintile bins among failing patches, weighted by own count)?
Held-out and SWE-bench Lite. 2,000 issue resamples, seed 0.

Usage: python3 strong_writer_leniency.py > derived/strong_writer_leniency_2026-11-04.txt
"""
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from per_writer_leniency import *
from fresh_judging import FAMILY, WRITER_FAMILY, load
H=os.path.dirname(os.path.abspath(__file__))
def run(name, X, y, wr, iss, judges, wfam):
    n=len(y)
    panel=np.array([np.mean([X[m][i] for m in judges if m!=G and FAMILY[m]!=wfam[wr[i]]]) for i in range(n)])
    D=X[G]-panel
    fail=y==0
    rate={v: y[wr==v].mean() for v in set(wr)}
    strong={v for v in rate if v!=GW and rate[v]>=rate[GW]}
    # matched: bins of panel mean among failing patches (quintiles over all failing)
    edges=np.quantile(panel[fail],[0,.2,.4,.6,.8,1]); edges[-1]+=1e-9
    b=np.digitize(panel,edges[1:-1])
    def stats(idx):
        f=idx[fail[idx]]
        own=f[wr[f]==GW]; oth=f[wr[f]!=GW]; st=f[np.isin(wr[f],list(strong))]
        r={}
        r['own_minus_strong']=D[own].mean()-D[st].mean()
        r['own_minus_others']=D[own].mean()-D[oth].mean()
        # matched by panel bin, weighted by own count; also 100-share
        num=den=num100=0
        for k in range(5):
            o=own[b[own]==k]; t=oth[b[oth]==k]
            if len(o) and len(t):
                num+=len(o)*(D[o].mean()-D[t].mean()); num100+=len(o)*((X[G][o]==100).mean()-(X[G][t]==100).mean()); den+=len(o)
        r['own_minus_others_matched_panel']=num/den
        r['share100_own_minus_others_matched_panel']=100*num100/den
        num=den=0
        for k in range(5):
            o=own[b[own]==k]; t=st[b[st]==k]
            if len(o) and len(t): num+=len(o)*(D[o].mean()-D[t].mean()); den+=len(o)
        r['own_minus_strong_matched_panel']=num/den
        return r
    issues=sorted(set(iss)); by={i:np.where(iss==i)[0] for i in issues}
    rng=np.random.default_rng(0); B=collections.defaultdict(list)
    for _ in range(2000):
        idx=np.concatenate([by[i] for i in rng.choice(issues,len(issues))])
        for k,v in stats(idx).items(): B[k].append(v)
    full=stats(np.arange(n))
    f=fail
    print(f'== {name}: strong writers (pass rate >= Gemma {rate[GW]:.2f}):', {v:round(rate[v],2) for v in strong})
    print(f'   failing: own {int((f&(wr==GW)).sum())}, strong {int((f&np.isin(wr,list(strong))).sum())}; panel mean own failing {panel[f&(wr==GW)].mean():.1f}, strong failing {panel[f&np.isin(wr,list(strong))].mean():.1f}, all other failing {panel[f&(wr!=GW)].mean():.1f}')
    for k,v in full.items():
        print(f'   {k}: {v:+.1f} [{np.percentile(B[k],2.5):.1f}, {np.percentile(B[k],97.5):.1f}]')
pids,X,y,wr,iss,_=load(J9,["main-a","main-b"]); run('held-out',X,y,wr,iss,J9,WRITER_FAMILY)
X,y,wr,iss=load_rows(os.path.join(H,"..","data","public","third-party-lite","patches.jsonl"),"lite",J7); run('lite',X,y,wr,iss,J7,LITE_WRITERS)
