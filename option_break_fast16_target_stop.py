import os,time
from datetime import datetime,timedelta,time as dtime
from urllib.parse import quote
from zoneinfo import ZoneInfo
import requests,psycopg
from psycopg.rows import dict_row
IST=ZoneInfo("Asia/Kolkata")
DB=(os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
TOKEN=(os.getenv("UPSTOX_TOKEN") or os.getenv("UPSTOX_ACCESS_TOKEN") or "").strip()
H={"Accept":"application/json","Authorization":f"Bearer {TOKEN}"}
def db():return psycopg.connect(DB,row_factory=dict_row)
def candles(k,day,exp):
 e=quote(k,safe="")
 u=(f"https://api.upstox.com/v2/expired-instruments/historical-candle/{e}/1minute/{day}/{day}" if exp<datetime.now(IST).date() else f"https://api.upstox.com/v3/historical-candle/{e}/minutes/1/{day}/{day}")
 r=requests.get(u,headers=H,timeout=60);r.raise_for_status();out=[]
 for a in (r.json().get("data") or {}).get("candles") or []:
  try:out.append((datetime.fromisoformat(str(a[0]).replace("Z","+00:00")).astimezone(IST),float(a[2]),float(a[3]),float(a[4])))
  except:pass
 return sorted(out)
DDL="""CREATE TABLE IF NOT EXISTS public.option_break_fast16_target_stop(
trading_date date,symbol text,option_strike numeric,trigger_time timestamptz,entry_price numeric,
target_pct numeric,stop_pct numeric,target_price numeric,stop_price numeric,target_time timestamptz,stop_time timestamptz,
first_outcome text,outcome_time timestamptz,exit_price numeric,strategy_return_pct numeric,max_favorable_pct numeric,
max_adverse_pct numeric,eod_price numeric,data_status text,error_message text,updated_at timestamptz default now(),
PRIMARY KEY(trading_date,symbol,trigger_time,target_pct,stop_pct));"""
Q="""SELECT trading_date,symbol,option_strike,option_instrument_key,option_expiry,trigger_time,trigger_level
FROM public.option_break_day_high_backtest WHERE data_status='OK' AND trigger_reached
AND TO_CHAR(candle_end AT TIME ZONE 'Asia/Kolkata','HH24:MI')='10:15' AND minutes_to_trigger<=5 ORDER BY trading_date,symbol"""
INS="""INSERT INTO public.option_break_fast16_target_stop VALUES
(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
ON CONFLICT(trading_date,symbol,trigger_time,target_pct,stop_pct) DO UPDATE SET
first_outcome=EXCLUDED.first_outcome,outcome_time=EXCLUDED.outcome_time,exit_price=EXCLUDED.exit_price,
strategy_return_pct=EXCLUDED.strategy_return_pct,max_favorable_pct=EXCLUDED.max_favorable_pct,
max_adverse_pct=EXCLUDED.max_adverse_pct,eod_price=EXCLUDED.eod_price,data_status=EXCLUDED.data_status,error_message=EXCLUDED.error_message,updated_at=NOW()"""
def main():
 if not DB or not TOKEN:raise RuntimeError("NEON_DATABASE_URL and UPSTOX_TOKEN required")
 with db() as c:
  with c.cursor() as x:x.execute(DDL);x.execute(Q);cases=x.fetchall()
  c.commit()
 print("FAST CASES",len(cases),flush=True)
 for n,a in enumerate(cases,1):
  day,sym,strike,key,exp,trig,entry=a["trading_date"],a["symbol"],a["option_strike"],a["option_instrument_key"],a["option_expiry"],a["trigger_time"],float(a["trigger_level"])
  try:
   rr=[r for r in candles(key,day,exp) if r[0]>=trig.astimezone(IST) and r[0].time().replace(tzinfo=None)<dtime(15,30)]
   if not rr:raise ValueError("no post-trigger option candles")
   mfe=(max(x[1] for x in rr)/entry-1)*100;mae=(min(x[2] for x in rr)/entry-1)*100;eod=rr[-1][3]
   vals=[]
   for t in (10.,20.,30.):
    for s in (5.,10.):
     tp=entry*(1+t/100);sp=entry*(1-s/100);tt=st=None
     for ts,hi,lo,cl in rr:
      ht=hi>=tp;hs=lo<=sp
      if ht or hs:
       if ht and hs:out="AMBIGUOUS_SAME_1M_BAR";ot=ts+timedelta(minutes=1);ex=cl;ret=(ex/entry-1)*100;tt=ot;st=ot
       elif ht:out="TARGET_FIRST";ot=ts+timedelta(minutes=1);ex=tp;ret=t;tt=ot
       else:out="STOP_FIRST";ot=ts+timedelta(minutes=1);ex=sp;ret=-s;st=ot
       break
     else:out="NEITHER";ot=None;ex=eod;ret=(eod/entry-1)*100
     vals.append((day,sym,strike,trig,entry,t,s,tp,sp,tt,st,out,ot,ex,ret,mfe,mae,eod,"OK",None))
   with db() as c:
    with c.cursor() as x:x.executemany(INS,vals)
    c.commit()
  except Exception as e:print("ERROR",sym,e,flush=True)
  print(n,sym,flush=True)
 print("COMPLETE",flush=True)
if __name__=="__main__":main()
