import warnings; warnings.filterwarnings("ignore")
import numpy as np
from scipy.special import betaln, betainc
from scipy.optimize import least_squares, minimize

def cov(k, d, a, b):
    k = np.asarray(k, float)
    return (1-d)*(1-np.exp(betaln(a, b+k)-betaln(a, b)))

def fit(name, ks, ys, d_fixed=None):
    ks=np.array(ks,float); ys=np.array(ys,float)
    def res(x):
        la, lb = x[0], x[1]
        d = d_fixed if d_fixed is not None else 1/(1+np.exp(-x[2]))
        return cov(ks, d, np.exp(la), np.exp(lb)) - ys
    best=None
    for la in np.linspace(-3,2,11):
        for lb in np.linspace(-2,6,11):
            x0=[la,lb] + ([] if d_fixed is not None else [-1.0])
            try:
                r=least_squares(res,x0)
            except Exception: continue
            if best is None or r.cost<best.cost: best=r
    x=best.x; a,b=np.exp(x[0]),np.exp(x[1]); d=d_fixed if d_fixed is not None else 1/(1+np.exp(-x[2]))
    print(f"{name}: d={d:.3f} alpha={a:.3f} beta={b:.3f} mean_p_live={a/(a+b):.3f} maxres={np.abs(best.fun).max():.4f}")
    print("   fitted:", np.round(cov(ks,d,a,b),4), "obs:", ys, " pass@1e5:", round(float(cov([1e5],d,a,b)[0]),3))
    return d,a,b

print("== DeepSeek-Prover-V2 671B CoT miniF2F (Table 1): k=1,32,1024,8192")
fit("DSP2-671B-CoT", [1,32,1024,8192],[.619,.824,.866,.889])
for d in [0.0,0.05,0.10]:
    fit(f"  d fixed {d}", [1,32,1024,8192],[.619,.824,.866,.889], d_fixed=d)
print("== DeepSeek-Prover-V2 7B nonCoT miniF2F")
fit("DSP2-7B", [1,32,1024,8192],[.555,.680,.732,.750])
print("== Goedel-V2 32B miniF2F (Table 2) k=32,1024,8192 (no pass@1) -> fix d grid")
for d in [0.0,0.05,0.07]:
    fit(f"  Goedel32B d={d}", [32,1024,8192],[.881,.918,.922], d_fixed=d)
print("== DSP2-671B CoT PutnamBench (Table 4) k=32,128,1024")
for d in [0.0,0.5,0.8,0.9]:
    fit(f"  Putnam d={d}", [32,128,1024],[22/658,33/658,47/658], d_fixed=d)
print("== SWE-bench Lite DeepSeek-Coder-V2 (Monkeys abstract): k=1 .159, k=250 .56 ; d grid")
for d in [0.0,0.2,0.3,0.4]:
    fit(f"  SWE d={d}", [1,250],[.159,.56], d_fixed=d)
print("== CodeContests Gemma-2B: k=1 .0002, k=1e4 .071; d grid")
for d in [0.0,0.5,0.8,0.9]:
    fit(f"  CC d={d}", [1,10000],[.0002,.071], d_fixed=d)

print("== GSM8K Llama-3-8B per-problem pass@1 histogram (Monkeys Table 2), binned MLE")
edges=[0,.10,.25,.75,1.0]; counts=np.array([5,10,29,84])
def nll(x):
    a,b=np.exp(x)
    pr=np.diff([betainc(a,b,e) if 0<e<1 else float(e>=1) for e in edges])
    return -(counts*np.log(np.maximum(pr,1e-300))).sum()
r=minimize(nll,[0,0],method="Nelder-Mead")
a,b=np.exp(r.x); pr=np.diff([betainc(a,b,e) if 0<e<1 else float(e>=1) for e in edges])
print(f"  alpha={a:.3f} beta={b:.3f} mean={a/(a+b):.3f}; fitted counts={np.round(pr*128,1)} obs={counts}")
# method-of-moments illustration: from pass@1 and pass@k with d=0
print("== MoM illustration: m=pass@1, c_k; with d=0 solve alpha,beta s.t. a/(a+b)=m and 1-B(a,b+k)/B(a,b)=c_k")
from scipy.optimize import brentq
def mom(m,k,c,d=0.0):
    m_l=m/(1-d); c_l=c/(1-d)
    f=lambda s: (1-np.exp(betaln(m_l*s,(1-m_l)*s+k)-betaln(m_l*s,(1-m_l)*s)))-c_l
    s=brentq(f,1e-4,1e4); return m_l*s,(1-m_l)*s
for (nm,m,k,c,d) in [("SWE-Lite",.159,250,.56,0.0),("SWE-Lite d=.3",.159,250,.56,.3),("DSP2-671B k=32",.619,32,.824,0),("DSP2-671B k=8192",.619,8192,.889,0)]:
    try:
        a,b=mom(m,k,c,d); print(f"  {nm}: alpha={a:.3f} beta={b:.3f}")
    except Exception as e: print("  ",nm,"no solution",e)
