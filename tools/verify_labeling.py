#!/usr/bin/env python3
"""
Verification harness for the WIN/PARTIAL/LOSS labeling + TP/SL geometry findings.
Read-only: pulls live trade history from the `data` branch and tests each claim.
"""
import urllib.request, json, statistics
from collections import defaultdict, Counter

BASE = "https://raw.githubusercontent.com/migo1907/blank-app/data/data/"
POOLS = ["XAUUSD_2M","XAUUSD_5M","XAUUSD_30M",
         "STOCKS_MOMENTUM_15M","STOCKS_MOMENTUM_30M","STOCKS_QUALITY_15M","STOCKS_QUALITY_30M"]

def load(pool):
    try:
        return json.load(urllib.request.urlopen(BASE+f"trade_history_{pool}.json",timeout=60))
    except Exception as e:
        return None

def signed_move(t):
    try:
        e=float(t["entry_price"]); x=float(t["exit_price"])
    except (TypeError,ValueError,KeyError):
        return None
    s = 1 if t.get("direction")=="LONG" else -1
    return (x-e)*s

def analyze(pool, rows):
    print(f"\n{'='*64}\n{pool}  (n={len(rows)})\n{'='*64}")
    n=len(rows)
    oc=Counter(t.get("outcome") for t in rows)
    win=oc.get("WIN",0); part=oc.get("PARTIAL",0); loss=oc.get("LOSS",0)

    # ---- FINDING 1: WIN defined as TP3-only ----
    tp3_wins=sum(1 for t in rows if t.get("outcome")=="WIN" and (t.get("tp_stage") or "")=="TP3")
    reached_tp1plus = part + win  # any PARTIAL hit >=TP1, plus WINs
    print(f"[F1] WIN-rate (TP3 def): {win}/{n} = {win/n*100:.1f}%   <-- headline metric")
    print(f"     Honest 'reached TP1+': {reached_tp1plus}/{n} = {reached_tp1plus/n*100:.1f}%")
    print(f"     Of {win} WINs, {tp3_wins} are genuine TP3 fills")

    # ---- FINDING 3: SL_TP1 net P&L (the leak) ----
    by=defaultdict(list)
    for t in rows:
        m=signed_move(t)
        if m is None: continue
        by[(t.get("outcome"),t.get("tp_stage") or "-")].append(m)
    def stat(key):
        v=by.get(key,[])
        if not v: return None
        pos=sum(1 for x in v if x>0)/len(v)*100
        return len(v),statistics.mean(v),statistics.median(v),pos
    print(f"[F3] SL_TP1 trail outcome (claim: exits at a LOSS, no breakeven stop):")
    for key in [("PARTIAL","SL_TP1"),("PARTIAL","SL_TP2"),("LOSS","SL")]:
        s=stat(key)
        if s: print(f"     {key[0]}/{key[1]:7} n={s[0]:3} avg={s[1]:+6.2f} median={s[2]:+6.2f} pos%={s[3]:.0f}")
    sl_tp1=stat(("PARTIAL","SL_TP1"))
    if sl_tp1:
        verdict = "CONFIRMED LEAK (net negative)" if sl_tp1[1] < 0 else "ok (net positive)"
        print(f"     -> SL_TP1 verdict: {verdict}")

    # ---- FINDING 2: TP3 reachability in R-multiples ----
    # SL distance proxy = avg |move| of pure-SL losses; TP3 distance = |move| of TP3 wins
    sld=[abs(signed_move(t)) for t in rows if (t.get("tp_stage")=="SL" and signed_move(t) is not None)]
    tp3d=[abs(signed_move(t)) for t in rows if (t.get("tp_stage")=="TP3" and signed_move(t) is not None)]
    if sld and tp3d:
        R=statistics.mean(tp3d)/statistics.mean(sld)
        print(f"[F2] TP3 dist {statistics.mean(tp3d):.1f} / SL dist {statistics.mean(sld):.1f} = {R:.1f}R to final target")
    elif sld:
        print(f"[F2] SL dist avg {statistics.mean(sld):.1f} pts; no TP3 fills to measure TP3 distance")

    # ---- FINDING 4: ML reward vs real PnL for SL_TP1 ----
    if sl_tp1:
        print(f"[F4] ml_model grades SL_TP1 as 0.4x WIN; real avg move={sl_tp1[1]:+.2f} "
              f"({'MISLABELED' if sl_tp1[1]<0 else 'consistent'})")

    # ---- Net expectancy on final-exit basis (caveat: ignores partial booking) ----
    allm=[signed_move(t) for t in rows if signed_move(t) is not None]
    if allm:
        print(f"[EXP] final-exit avg move/trade: {statistics.mean(allm):+.2f} pts "
              f"(caveat: whole position at final exit, ignores TP1/TP2 partial banking)")

print("LABELING & GEOMETRY VERIFICATION — live data from `data` branch")
for p in POOLS:
    r=load(p)
    if r is None or not isinstance(r,list) or not r:
        print(f"\n{p}: no/empty data — skipped"); continue
    analyze(p,r)
