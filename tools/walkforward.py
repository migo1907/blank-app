#!/usr/bin/env python3
"""
Walk-forward evaluation of signal-quality models on REAL live trades.
Label = reached TP1+ (WIN/PARTIAL=1, LOSS=0). Chronological, no leakage:
train on trades [0:i], predict trade i, step forward (expanding window).
Compares: current-style RF/GBM, + candidate improvements.
"""
import urllib.request, json, statistics, warnings
import numpy as np
warnings.filterwarnings("ignore")
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
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
        rows.append((t.get("created_at",""),x,y,t.get("direction"),t.get("session"),t.get("regime")))
    rows.sort(key=lambda r:r[0])
    return rows

def walk_forward(rows, model_fn, min_train=60, weight_fn=None):
    """Expanding-window walk-forward. Returns (probs, ys) for all predicted trades."""
    X=np.array([r[1] for r in rows]); Y=np.array([r[2] for r in rows])
    probs=[]; ys=[]
    for i in range(min_train, len(rows)):
        Xt, Yt = X[:i], Y[:i]
        if len(set(Yt))<2: continue
        m=model_fn()
        sw = weight_fn(i) if weight_fn else None
        try:
            m.fit(Xt, Yt, sample_weight=sw)
        except TypeError:
            m.fit(Xt, Yt)
        p=m.predict_proba(X[i:i+1])[0]
        cls=list(m.classes_)
        probs.append(p[cls.index(1)] if 1 in cls else 0.0)
        ys.append(Y[i])
    return np.array(probs), np.array(ys)

def evaluate(name, probs, ys):
    if len(ys)==0: return
    base=ys.mean()*100
    # tercile lift: does the top third of scores beat the bottom third?
    qs=np.quantile(probs,[1/3,2/3])
    lo=ys[probs<=qs[0]]; hi=ys[probs>=qs[1]]
    brier=brier_score_loss(ys,probs)
    # actionable: hit-rate if you only take top-half scored trades
    med=np.median(probs); top=ys[probs>=med]
    print(f"  {name:34} n={len(ys):3} base={base:4.1f}%  top⅓={hi.mean()*100 if len(hi) else 0:4.1f}%  bot⅓={lo.mean()*100 if len(lo) else 0:4.1f}%  "
          f"lift={ (hi.mean()-lo.mean())*100 if len(hi) and len(lo) else 0:+5.1f}pp  top½={top.mean()*100 if len(top) else 0:4.1f}%  brier={brier:.3f}")

def rf_current():  # mirrors backend defaults style
    return RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=42, n_jobs=1)
def rf_shallow():
    return RandomForestClassifier(n_estimators=200, max_depth=4, min_samples_leaf=8, class_weight="balanced", random_state=42, n_jobs=1)
def gbm_current():
    return GradientBoostingClassifier(n_estimators=100, random_state=42)
def gbm_shallow():
    return GradientBoostingClassifier(n_estimators=60, max_depth=2, subsample=0.8, random_state=42)
def logit():
    return LogisticRegression(max_iter=2000, class_weight="balanced", C=0.3)

def recency_weights(half_life):
    def fn(i):
        ages=np.arange(i)[::-1]  # most recent age 0
        return 0.5**(ages/half_life)
    return fn

for pool in ["XAUUSD_2M","XAUUSD_5M","STOCKS_MOMENTUM_15M","STOCKS_MOMENTUM_30M"]:
    rows=load(pool)
    print(f"\n===== {pool}: {len(rows)} labeled trades, base TP1+ rate {sum(r[2] for r in rows)/len(rows)*100:.0f}% =====")
    if len(rows)<90:
        print("  (too few for walk-forward, skipped)"); continue
    mt=60 if len(rows)>=150 else 40
    for name,fn,wf in [
        ("RF current (deep, balanced)", rf_current, None),
        ("RF shallow (depth4, leaf8)",  rf_shallow, None),
        ("GBM current",                 gbm_current, None),
        ("GBM shallow (d2, sub0.8)",    gbm_shallow, None),
        ("Logistic L2 (C=0.3)",         logit, None),
        ("RF shallow + recency hl=100", rf_shallow, recency_weights(100)),
        ("RF shallow + recency hl=50",  rf_shallow, recency_weights(50)),
    ]:
        p,y=walk_forward(rows, fn, min_train=mt, weight_fn=wf)
        evaluate(name,p,y)
