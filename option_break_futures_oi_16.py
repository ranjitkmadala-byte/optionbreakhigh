from __future__ import annotations
import os,time
from datetime import datetime,timedelta,time as dtime
from urllib.parse import quote
from zoneinfo import ZoneInfo
import requests,psycopg
from psycopg.rows import dict_row

IST=ZoneInfo("Asia/Kolkata")
DB=(os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
TOKEN=(os.getenv("UPSTOX_TOKEN") or os.getenv("UPSTOX_ACCESS_TOKEN") or "").strip()
BASELINE=dtime(9,20)
V3="https://api.upstox.com/v3/historical-candle"

def db(): return psycopg.connect(DB,row_factory=dict_row,connect_timeout=20)
def head(): return {"Accept":"application/json","Authorization":f"Bearer {TOKEN}"}

def getj(url,tries=5):
    last=None
    for i in range(tries):
        try:
            r=requests.get(url,headers=head(),timeout=60)
            if r.status_code==429: time.sleep(2*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception as e:
            last=e
            if i<tries-1: time.sleep(1.5*(i+1))
    raise RuntimeError(str(last))

def candles(key,day):
    u=f"{V3}/{quote(key,safe='')}/minutes/1/{day}/{day}"
    j=getj(u); out=[]
    for a in (j.get("data") or {}).get("candles") or []:
        if len(a)<7: continue
        try:
            out.append(dict(
                ts=datetime.fromisoformat(str(a[0]).replace("Z","+00:00")).astimezone(IST),
                open=float(a[1]),high=float(a[2]),low=float(a[3]),close=float(a[4]),
                volume=int(float(a[5] or 0)),oi=float(a[6]) if a[6] is not None else None))
        except: pass
    return sorted(out,key=lambda r:r["ts"])

DDL="""
CREATE TABLE IF NOT EXISTS public.option_break_futures_oi_16 (
 trading_date DATE NOT NULL,symbol TEXT NOT NULL,
 option_trigger_time TIMESTAMPTZ NOT NULL,option_outcome TEXT,
 future_instrument_key TEXT,
 baseline_time TIMESTAMPTZ,baseline_future_price NUMERIC,baseline_future_oi NUMERIC,
 trigger_future_price NUMERIC,trigger_future_oi NUMERIC,
 cumulative_price_pct NUMERIC,cumulative_oi_pct NUMERIC,
 pre5_price_pct NUMERIC,pre5_oi_pct NUMERIC,
 pre10_price_pct NUMERIC,pre10_oi_pct NUMERIC,
 oi_state_baseline_to_trigger TEXT,oi_state_pre5 TEXT,oi_state_pre10 TEXT,
 data_status TEXT NOT NULL,error_message TEXT,updated_at TIMESTAMPTZ DEFAULT NOW(),
 PRIMARY KEY(trading_date,symbol,option_trigger_time)
);
"""

CASES="""
SELECT b.trading_date,b.symbol,b.trigger_time,t.first_outcome
FROM public.option_break_day_high_backtest b
JOIN public.option_break_fast16_target_stop t
 ON t.trading_date=b.trading_date AND t.symbol=b.symbol AND t.trigger_time=b.trigger_time
WHERE b.study_start=DATE '2026-08-26' AND b.study_end=DATE '2026-09-11'
 AND TO_CHAR(b.candle_end AT TIME ZONE 'Asia/Kolkata','HH24:MI')='10:15'
 AND b.minutes_to_trigger<=5 AND t.target_pct=10 AND t.stop_pct=5
ORDER BY b.trading_date,b.symbol
"""

def future_key(symbol,day):
    # Prefer exact historical key already stored in money-flow universe.
    with db() as c:
        with c.cursor() as x:
            x.execute("""SELECT future_instrument_key FROM public.money_flow_universe
            WHERE trading_date=%s AND symbol=%s AND future_instrument_key IS NOT NULL LIMIT 1""",(day,symbol))
            r=x.fetchone()
            if r:return r["future_instrument_key"]
    # Fall back to any known historical futures key for same symbol.
    with db() as c:
        with c.cursor() as x:
            x.execute("""SELECT future_instrument_key FROM public.money_flow_universe
            WHERE symbol=%s AND future_instrument_key IS NOT NULL
            ORDER BY trading_date DESC LIMIT 1""",(symbol,))
            r=x.fetchone()
            if r:return r["future_instrument_key"]
    raise ValueError("future instrument key unavailable in Neon")

def nearest(rows,ts):
    eligible=[r for r in rows if r["ts"]<=ts and r["oi"] is not None]
    return eligible[-1] if eligible else None

def pct(a,b):
    return None if a in (None,0) or b is None else (b/a-1)*100

def state(pp,op):
    if pp is None or op is None:return "UNKNOWN"
    if pp>0 and op>0:return "LONG_BUILDUP"
    if pp<0 and op>0:return "SHORT_BUILDUP"
    if pp>0 and op<0:return "SHORT_COVERING"
    if pp<0 and op<0:return "LONG_UNWINDING"
    return "FLAT/MIXED"

INS="""INSERT INTO public.option_break_futures_oi_16 VALUES
(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
ON CONFLICT(trading_date,symbol,option_trigger_time) DO UPDATE SET
 option_outcome=EXCLUDED.option_outcome,future_instrument_key=EXCLUDED.future_instrument_key,
 baseline_time=EXCLUDED.baseline_time,baseline_future_price=EXCLUDED.baseline_future_price,
 baseline_future_oi=EXCLUDED.baseline_future_oi,trigger_future_price=EXCLUDED.trigger_future_price,
 trigger_future_oi=EXCLUDED.trigger_future_oi,cumulative_price_pct=EXCLUDED.cumulative_price_pct,
 cumulative_oi_pct=EXCLUDED.cumulative_oi_pct,pre5_price_pct=EXCLUDED.pre5_price_pct,
 pre5_oi_pct=EXCLUDED.pre5_oi_pct,pre10_price_pct=EXCLUDED.pre10_price_pct,
 pre10_oi_pct=EXCLUDED.pre10_oi_pct,oi_state_baseline_to_trigger=EXCLUDED.oi_state_baseline_to_trigger,
 oi_state_pre5=EXCLUDED.oi_state_pre5,oi_state_pre10=EXCLUDED.oi_state_pre10,
 data_status=EXCLUDED.data_status,error_message=EXCLUDED.error_message,updated_at=NOW()"""

def main():
    if not DB or not TOKEN:raise RuntimeError("NEON_DATABASE_URL and UPSTOX_TOKEN required")
    with db() as c:
        with c.cursor() as x:x.execute(DDL);x.execute(CASES);cs=x.fetchall()
        c.commit()
    print("CASES",len(cs),flush=True)
    for i,a in enumerate(cs,1):
        try:
            key=future_key(a["symbol"],a["trading_date"])
            rr=candles(key,a["trading_date"])
            trig=a["trigger_time"].astimezone(IST)
            bt=datetime.combine(a["trading_date"],BASELINE,IST)
            b=nearest(rr,bt); t=nearest(rr,trig); p5=nearest(rr,trig-timedelta(minutes=5)); p10=nearest(rr,trig-timedelta(minutes=10))
            if not b or not t:raise ValueError("missing baseline/trigger futures candle")
            cpp=pct(b["close"],t["close"]);cop=pct(b["oi"],t["oi"])
            p5p=pct(p5["close"],t["close"]) if p5 else None;p5o=pct(p5["oi"],t["oi"]) if p5 else None
            p10p=pct(p10["close"],t["close"]) if p10 else None;p10o=pct(p10["oi"],t["oi"]) if p10 else None
            v=(a["trading_date"],a["symbol"],a["trigger_time"],a["first_outcome"],key,
               b["ts"],b["close"],b["oi"],t["close"],t["oi"],cpp,cop,p5p,p5o,p10p,p10o,
               state(cpp,cop),state(p5p,p5o),state(p10p,p10o),"OK",None)
        except Exception as e:
            v=(a["trading_date"],a["symbol"],a["trigger_time"],a["first_outcome"],None,
               None,None,None,None,None,None,None,None,None,None,None,
               "UNKNOWN","UNKNOWN","UNKNOWN","ERROR",str(e)[:1000])
        with db() as c:
            with c.cursor() as x:x.execute(INS,v)
            c.commit()
        print(i,a["symbol"],v[19],flush=True)
    print("COMPLETE",flush=True)
if __name__=="__main__":main()
