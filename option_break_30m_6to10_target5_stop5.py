import os
from datetime import datetime,timedelta,time as T
from urllib.parse import quote
from zoneinfo import ZoneInfo
import requests,psycopg
from psycopg.rows import dict_row
I=ZoneInfo("Asia/Kolkata");D=(os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip();K=(os.getenv("UPSTOX_TOKEN") or os.getenv("UPSTOX_ACCESS_TOKEN") or "").strip()
def db():return psycopg.connect(D,row_factory=dict_row)
def bars(k,d,e):
 u=(f"https://api.upstox.com/v2/expired-instruments/historical-candle/{quote(k,safe='')}/1minute/{d}/{d}" if e<datetime.now(I).date() else f"https://api.upstox.com/v3/historical-candle/{quote(k,safe='')}/minutes/1/{d}/{d}")
 r=requests.get(u,headers={"Accept":"application/json","Authorization":f"Bearer {K}"},timeout=60);r.raise_for_status();o=[]
 for a in (r.json().get("data") or {}).get("candles") or []:
  try:o.append((datetime.fromisoformat(str(a[0]).replace("Z","+00:00")).astimezone(I),float(a[2]),float(a[3]),float(a[4])))
  except:pass
 return sorted(o)
DDL="""CREATE TABLE IF NOT EXISTS public.option_break_30m_6to10_target5_stop5(trading_date date,symbol text,option_strike numeric,trigger_time timestamptz,minutes_to_trigger int,entry_price numeric,target_price numeric,stop_price numeric,target_time timestamptz,stop_time timestamptz,first_outcome text,outcome_time timestamptz,exit_price numeric,strategy_return_pct numeric,max_favorable_pct numeric,max_adverse_pct numeric,eod_price numeric,data_status text,error_message text,updated_at timestamptz default now(),PRIMARY KEY(trading_date,symbol,trigger_time));"""
Q="""SELECT trading_date,symbol,option_strike,option_instrument_key,option_expiry,trigger_time,minutes_to_trigger,trigger_level FROM public.option_break_30m_day_high_backtest WHERE data_status='OK' AND trigger_reached AND TO_CHAR(candle_start AT TIME ZONE 'Asia/Kolkata','HH24:MI')='09:15' AND minutes_to_trigger BETWEEN 6 AND 10 ORDER BY trading_date,symbol"""
INS="""INSERT INTO public.option_break_30m_6to10_target5_stop5 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) ON CONFLICT(trading_date,symbol,trigger_time) DO UPDATE SET first_outcome=EXCLUDED.first_outcome,outcome_time=EXCLUDED.outcome_time,exit_price=EXCLUDED.exit_price,strategy_return_pct=EXCLUDED.strategy_return_pct,max_favorable_pct=EXCLUDED.max_favorable_pct,max_adverse_pct=EXCLUDED.max_adverse_pct,eod_price=EXCLUDED.eod_price,data_status=EXCLUDED.data_status,error_message=EXCLUDED.error_message,updated_at=NOW()"""
def main():
 if not D or not K:raise RuntimeError("NEON_DATABASE_URL and UPSTOX_TOKEN required")
 with db() as c:
  with c.cursor() as x:x.execute(DDL);x.execute(Q);cs=x.fetchall()
  c.commit()
 print("CASES",len(cs),flush=True)
 for i,a in enumerate(cs,1):
  e=float(a["trigger_level"]);tp=e*1.05;sp=e*.95;tr=a["trigger_time"].astimezone(I)
  try:
   r=[x for x in bars(a["option_instrument_key"],a["trading_date"],a["option_expiry"]) if x[0]>=tr and x[0].time().replace(tzinfo=None)<T(15,30)]
   if not r:raise ValueError("no post-trigger bars")
   out="NEITHER";ot=tt=st=None;ex=r[-1][3]
   for ts,h,l,cl in r:
    if h>=tp and l<=sp:out="AMBIGUOUS_SAME_1M_BAR";ot=tt=st=ts+timedelta(minutes=1);ex=cl;break
    if h>=tp:out="TARGET_FIRST";ot=tt=ts+timedelta(minutes=1);ex=tp;break
    if l<=sp:out="STOP_FIRST";ot=st=ts+timedelta(minutes=1);ex=sp;break
   v=(a["trading_date"],a["symbol"],a["option_strike"],a["trigger_time"],a["minutes_to_trigger"],e,tp,sp,tt,st,out,ot,ex,(ex/e-1)*100,(max(x[1] for x in r)/e-1)*100,(min(x[2] for x in r)/e-1)*100,r[-1][3],"OK",None)
  except Exception as q:v=(a["trading_date"],a["symbol"],a["option_strike"],a["trigger_time"],a["minutes_to_trigger"],e,tp,sp,None,None,"ERROR",None,None,None,None,None,None,"ERROR",str(q)[:500])
  with db() as c:
   with c.cursor() as x:x.execute(INS,v)
   c.commit()
  print(i,a["symbol"],v[10],flush=True)
 print("COMPLETE",flush=True)
if __name__=="__main__":main()
