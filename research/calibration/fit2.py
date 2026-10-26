import warnings; warnings.filterwarnings("ignore")
import numpy as np
from scipy.special import betaln
from scipy.optimize import least_squares
N=10
rows={"MATH R1-Distill":(3489,3122,889,7500),"MATH R1-Preview":(5354,1424,722,7500),"GSM8K R1-Distill":(2118,4967,388,7473),"GSM8K R1-Preview":(4809,2377,287,7473)}
for nm,(e,m,h,t) in rows.items():
    pe,ph=e/t,h/t
    for d in [0.0]:
        def res(x):
            a,b=np.exp(x)
            p0=d+(1-d)*np.exp(betaln(a,b+N)-betaln(a,b))
            p1=(1-d)*np.exp(betaln(a+N,b)-betaln(a,b))
            return [p0-ph,p1-pe]
        r=least_squares(res,[0,0]); a,b=np.exp(r.x)
        print(f"{nm}: P(all10)={pe:.3f} P(none)={ph:.3f} -> d={d} alpha={a:.3f} beta={b:.3f} mean={a/(a+b):.3f} res={np.abs(r.fun).max():.4f}")
