import json, collections, numpy as np
J=['gemma4-31b','gpt-oss-20b','qwen35-9b','glm47-flash','gpt-oss-120b','llama-4-maverick']; O=J[1:]
P={r['pid']:r for r in map(json.loads, open('data/livecodebench-pilot/judging/programs.jsonl'))}
S=collections.defaultdict(dict)
for t in J:
    for r in map(json.loads, open(f'scripts/derived/lcb_{t}.jsonl')):
        if r.get('err') is None and r.get('parsed') is not None and r['pid'] in P: S[r['pid']][t]=r['parsed']
pids=[p for p,s in S.items() if len(s)==len(J)]
gfail={P[p]['iid'] for p in P if P[p]['writer']=='gemma-4-31b' and P[p]['y']==0}
def run(sel):
    d={p:S[p]['gemma4-31b']-np.mean([S[p][k] for k in O]) for p in sel}
    iss=sorted({P[p]['iid'] for p in sel}); by=collections.defaultdict(list)
    for p in sel: by[P[p]['iid']].append(p)
    def stat(ps):
        own=[d[p] for p in ps if P[p]['writer']=='gemma-4-31b']; oth=[d[p] for p in ps if P[p]['writer']!='gemma-4-31b']
        s100o=np.mean([S[p]['gemma4-31b']==100 for p in ps if P[p]['writer']=='gemma-4-31b']); s100c=np.mean([S[p]['gemma4-31b']==100 for p in ps if P[p]['writer']!='gemma-4-31b'])
        return np.mean(own)-np.mean(oth), s100o-s100c, len(own), len(oth), s100o, s100c
    pt=stat(sel); rng=np.random.default_rng(0); B=[]
    for _ in range(2000):
        ps=[p for i in rng.choice(iss,len(iss)) for p in by[i]]
        try: B.append(stat(ps)[:2])
        except Exception: pass
    B=np.array(B)
    return dict(leniency=round(pt[0],1), ci=np.nanpercentile(B[:,0],[2.5,97.5]).round(1).tolist(), s100_own=round(pt[4],3), s100_ctrl=round(pt[5],3), s100_diff_ci=np.nanpercentile(B[:,1],[2.5,97.5]).round(3).tolist(), n_own=pt[2], n_ctrl=pt[3])
fail=[p for p in pids if P[p]['y']==0 and P[p]['iid'] in gfail]
print('failing programs on problems Gemma failed:', run(fail))
for d in ['hard','medium']:
    print(d, run([p for p in fail if P[p]['difficulty']==d]))
