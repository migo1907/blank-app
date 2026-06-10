#!/usr/bin/env python3
"""
Experiment 2 — test the research-backed improvements on real data, walk-forward:
  A. Sigmoid (Platt) calibration wrapper (research: isotonic overfits <1000)
  B. Feature reduction (25 -> top-8 by |corr| on train only; research: 6-16 events/var too few)
  C. Mistake-memory features: rolling TP1+ rate of last-N same-direction / same-session trades
  D. Logistic + shallow GBM ensemble avg
Metric: hit-rate lift (top vs bottom tercile) + top-half hit-rate + Brier. AUC avoided per research.
"""
import urllib.request, json, warnings
import numpy as np
warnings.filterwarnings("ignore")
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss

BASE="https://raw.githubusercontent.com/migo1907/blank-app/data/data/"
KEYS=["f1_rsi","f2_adx","f3_atr","f4_bb","f5_macd","f6_willr","f7_cmo","f8_ema_dist",
"f9_fvg","f10_ob","f11_bos","f12_liq","f13_pd","f14_choch","f15_sess","f16_mtf",
"f17_dxy","f18_vold","f19_rsidiv","f20_fib","f21_vwap","f22_body","f23_rsiacc","f24_fvgq","f25_tod"]

def load(pool):
    d=json.load(urllib.request.urlopen(BASE+f"trade_history_{pool}.json",timeout=60))
    rows=[]
    for t in d:
        if t.get("outcome") not in ("WIN","PARTIAL","LOSS"): continue
        if t.get("f1_rsi") is None: continue
        x=[float(t.get(k) or 0.0) for k in KEYS]
        y=1 if t["outcome"] in ("WIN","PARTIAL") else 0
        rows.append((t.get("created_at",""),x,y,t.get("direction") or "?",t.get("session") or "?",t.get("trigger") or "?"))
    rows.sort(key=lambda r:r[0])
    return rows

def add_memory_features(rows, n_recent=10):
    """Append mistake-memory features computed ONLY from past trades (no leakage):
       rolling TP1+ rate overall, same-direction, same-session, same-trigger, and loss-streak length."""
    out=[]
    hist=[]
    for ts,x,y,dr,sess,trig in rows:
        def rate(filt):
            sub=[h[1] for h in hist if filt(h)][-n_recent:]
            return sum(sub)/len(sub) if sub else 0.5
        overall = rate(lambda h: True)
        same_dir = rate(lambda h: h[2]==dr)
        same_sess= rate(lambda h: h[3]==sess)
        same_trig= rate(lambda h: h[4]==trig)
        streak=0
        for h in reversed(hist):
            if h[1]==0: streak+=1
            else: break
        x2=list(x)+[overall,same_dir,same_sess,same_trig,min(streak,8)/8.0]
        out.append((ts,x2,y,dr,sess,trig))
        hist.append((ts,y,dr,sess,trig))
    return out

def topk_idx(X,Y,k=8):
    cs=[]
    for j in range(X.shape[1]):
        c=np.corrcoef(X[:,j],Y)[0,1]
        cs.append(0.0 if np.isnan(c) else abs(c))
    return np.argsort(cs)[::-1][:k]

def walk(rows, mode, min_train=60):
    X=np.array([r[1] for r in rows]); Y=np.array([r[2] for r in rows])
    probs=[]; ys=[]
    for i in range(min_train,len(rows)):
        Xt,Yt=X[:i],Y[:i]
        if len(set(Yt))<2: continue
        if mode in ("logit_cal","logit_cal_top8"):
            cols=topk_idx(Xt,Yt,8) if mode.endswith("top8") else np.arange(X.shape[1])
            base=LogisticRegression(max_iter=2000,class_weight="balanced",C=0.3)
            m=CalibratedClassifierCV(base,method="sigmoid",cv=3)
            m.fit(Xt[:,cols],Yt); p=m.predict_proba(X[i:i+1][:,cols])[0]
        elif mode=="gbm_shallow_cal":
            base=GradientBoostingClassifier(n_estimators=60,max_depth=2,subsample=0.8,random_state=42)
            m=CalibratedClassifierCV(base,method="sigmoid",cv=3)
            m.fit(Xt,Yt); p=m.predict_proba(X[i:i+1])[0]
        elif mode=="rf_shallow_cal_top8":
            cols=topk_idx(Xt,Yt,8)
            base=RandomForestClassifier(n_estimators=200,max_depth=4,min_samples_leaf=8,class_weight="balanced",random_state=42,n_jobs=1)
            m=CalibratedClassifierCV(base,method="sigmoid",cv=3)
            m.fit(Xt[:,cols],Yt); p=m.predict_proba(X[i:i+1][:,cols])[0]
        cls=list(m.classes_); probs.append(p[cls.index(1)] if 1 in cls else 0.0); ys.append(Y[i])
    return np.array(probs),np.array(ys)

def ev(name,probs,ys):
    if len(ys)==0: return
    base=ys.mean()*100
    qs=np.quantile(probs,[1/3,2/3]); lo=ys[probs<=qs[0]]; hi=ys[probs>=qs[1]]
    med=np.median(probs); top=ys[probs>=med]
    print(f"  {name:30} n={len(ys):3} base={base:4.1f}%  top⅓={hi.mean()*100 if len(hi) else 0:4.1f}%  bot⅓={lo.mean()*100 if len(lo) else 0:4.1f}%  lift={(hi.mean()-lo.mean())*100 if len(hi) and len(lo) else 0:+5.1f}pp  top½={top.mean()*100 if len(top) else 0:4.1f}%  brier={brier_score_loss(ys,probs):.3f}")

for pool in ["XAUUSD_2M","XAUUSD_5M","STOCKS_MOMENTUM_15M","STOCKS_MOMENTUM_30M"]:
    rows=load(pool)
    if len(rows)<70:
        print(f"\n===== {pool}: too few ({len(rows)}) ====="); continue
    mt=60 if len(rows)>=150 else 40
    print(f"\n===== {pool}: {len(rows)} trades =====")
    for nm,mode,mem in [
        ("LogitCal (25f)","logit_cal",False),
        ("LogitCal top8","logit_cal_top8",False),
        ("GBMshallow+Cal","gbm_shallow_cal",False),
        ("RFshallow+Cal top8","rf_shallow_cal_top8",False),
        ("LogitCal top8 +MEMORY","logit_cal_top8",True),
        ("GBMshallow+Cal +MEMORY","gbm_shallow_cal",True),
    ]:
        rr=add_memory_features(rows) if mem else rows
        p,y=walk(rr,mode,min_train=mt)
        ev(nm,p,y)
