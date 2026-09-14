from __future__ import annotations

import os
import time
import uuid
from datetime import date, datetime, timedelta, time as dtime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import psycopg
import requests
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

IST = ZoneInfo("Asia/Kolkata")
DB = (os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
TOKEN = (os.getenv("UPSTOX_ACCESS_TOKEN") or os.getenv("UPSTOX_TOKEN") or "").strip()

START = date.fromisoformat(os.getenv("STUDY_START", "2026-08-26"))
END = date.fromisoformat(os.getenv("STUDY_END", "2026-09-11"))

# Market-aligned completed 1-hour candles:
# 09:15-10:15, 10:15-11:15, ... , 14:15-15:15
SESSION_START = dtime(9, 15)
LAST_COMPLETED_HOUR_END = dtime(15, 15)

# A "falling" 1H candle means close < open.
MIN_FALL_PCT = float(os.getenv("MIN_FALL_PCT", "0"))

# By default, the CE strike is the available strike nearest to the 1H SPOT HIGH.
STRIKE_MODE = os.getenv("STRIKE_MODE", "NEAREST_TO_CANDLE_HIGH").strip().upper()

RUN_ID = str(uuid.uuid4())
V3_HIST = "https://api.upstox.com/v3/historical-candle"
V2 = "https://api.upstox.com/v2"

def log(msg):
    print(f"{datetime.now(IST):%Y-%m-%d %H:%M:%S} IST | {msg}", flush=True)

def db():
    return psycopg.connect(DB, row_factory=dict_row, connect_timeout=20)

def headers():
    return {"Accept": "application/json", "Authorization": f"Bearer {TOKEN}"}

def get_json(url, params=None, tries=5):
    last = None
    for n in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers(), timeout=60)
            if r.status_code == 429:
                time.sleep(2 * (n + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            if n < tries - 1:
                time.sleep(1.5 * (n + 1))
    raise RuntimeError(str(last))

DDL = """
CREATE TABLE IF NOT EXISTS public.option_break_day_high_backtest (
    study_start DATE NOT NULL,
    study_end DATE NOT NULL,
    run_id UUID NOT NULL,

    trading_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    spot_instrument_key TEXT NOT NULL,

    candle_start TIMESTAMPTZ NOT NULL,
    candle_end TIMESTAMPTZ NOT NULL,
    spot_open NUMERIC,
    spot_high NUMERIC,
    spot_low NUMERIC,
    spot_close NUMERIC,
    spot_fall_pct NUMERIC,
    day_high NUMERIC,
    is_day_high_candle BOOLEAN NOT NULL DEFAULT FALSE,

    option_type TEXT NOT NULL DEFAULT 'CE',
    option_expiry DATE,
    option_strike NUMERIC,
    option_instrument_key TEXT,

    option_open NUMERIC,
    option_high NUMERIC,
    option_low NUMERIC,
    option_close NUMERIC,

    trigger_level NUMERIC,
    trigger_reached BOOLEAN NOT NULL DEFAULT FALSE,
    trigger_time TIMESTAMPTZ,
    option_price_at_trigger NUMERIC,

    minutes_to_trigger INTEGER,
    max_option_price_after_candle NUMERIC,
    eod_option_price NUMERIC,
    eod_return_from_candle_close_pct NUMERIC,

    data_status TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (
        study_start, study_end, trading_date, symbol, candle_start
    )
);

CREATE INDEX IF NOT EXISTS idx_option_break_result
    ON public.option_break_day_high_backtest
       (trading_date, trigger_reached, candle_start);

CREATE TABLE IF NOT EXISTS public.option_break_day_high_summary (
    study_start DATE NOT NULL,
    study_end DATE NOT NULL,
    run_id UUID NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),

    falling_1h_candles INTEGER NOT NULL,
    valid_option_cases INTEGER NOT NULL,
    trigger_reached INTEGER NOT NULL,
    trigger_not_reached INTEGER NOT NULL,
    failed INTEGER NOT NULL,

    summary JSONB NOT NULL,
    PRIMARY KEY (study_start, study_end)
);
"""

UPSERT = """
INSERT INTO public.option_break_day_high_backtest (
    study_start,study_end,run_id,trading_date,symbol,spot_instrument_key,
    candle_start,candle_end,spot_open,spot_high,spot_low,spot_close,spot_fall_pct,day_high,is_day_high_candle,
    option_type,option_expiry,option_strike,option_instrument_key,
    option_open,option_high,option_low,option_close,
    trigger_level,trigger_reached,trigger_time,option_price_at_trigger,
    minutes_to_trigger,max_option_price_after_candle,eod_option_price,
    eod_return_from_candle_close_pct,data_status,error_message
) VALUES (
    %(study_start)s,%(study_end)s,%(run_id)s,%(trading_date)s,%(symbol)s,%(spot_instrument_key)s,
    %(candle_start)s,%(candle_end)s,%(spot_open)s,%(spot_high)s,%(spot_low)s,%(spot_close)s,%(spot_fall_pct)s,%(day_high)s,%(is_day_high_candle)s,
    %(option_type)s,%(option_expiry)s,%(option_strike)s,%(option_instrument_key)s,
    %(option_open)s,%(option_high)s,%(option_low)s,%(option_close)s,
    %(trigger_level)s,%(trigger_reached)s,%(trigger_time)s,%(option_price_at_trigger)s,
    %(minutes_to_trigger)s,%(max_option_price_after_candle)s,%(eod_option_price)s,
    %(eod_return_from_candle_close_pct)s,%(data_status)s,%(error_message)s
)
ON CONFLICT(study_start,study_end,trading_date,symbol,candle_start)
DO UPDATE SET
    run_id=EXCLUDED.run_id,
    candle_end=EXCLUDED.candle_end,
    spot_open=EXCLUDED.spot_open,
    spot_high=EXCLUDED.spot_high,
    spot_low=EXCLUDED.spot_low,
    spot_close=EXCLUDED.spot_close,
    spot_fall_pct=EXCLUDED.spot_fall_pct,
    day_high=EXCLUDED.day_high,
    is_day_high_candle=EXCLUDED.is_day_high_candle,
    option_expiry=EXCLUDED.option_expiry,
    option_strike=EXCLUDED.option_strike,
    option_instrument_key=EXCLUDED.option_instrument_key,
    option_open=EXCLUDED.option_open,
    option_high=EXCLUDED.option_high,
    option_low=EXCLUDED.option_low,
    option_close=EXCLUDED.option_close,
    trigger_level=EXCLUDED.trigger_level,
    trigger_reached=EXCLUDED.trigger_reached,
    trigger_time=EXCLUDED.trigger_time,
    option_price_at_trigger=EXCLUDED.option_price_at_trigger,
    minutes_to_trigger=EXCLUDED.minutes_to_trigger,
    max_option_price_after_candle=EXCLUDED.max_option_price_after_candle,
    eod_option_price=EXCLUDED.eod_option_price,
    eod_return_from_candle_close_pct=EXCLUDED.eod_return_from_candle_close_pct,
    data_status=EXCLUDED.data_status,
    error_message=EXCLUDED.error_message,
    updated_at=NOW();
"""

def universe():
    # Reuse the known historical spot universe already present in Neon.
    q = """
    SELECT DISTINCT symbol, spot_instrument_key
    FROM public.spot_supply_1h_backtest_hourly
    WHERE trading_date BETWEEN %s AND %s
    ORDER BY symbol
    """
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(q, (START, END))
            return [dict(r) for r in cur.fetchall()]

def trading_dates():
    q = """
    SELECT DISTINCT trading_date
    FROM public.spot_supply_1h_backtest_hourly
    WHERE trading_date BETWEEN %s AND %s
    ORDER BY trading_date
    """
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(q, (START, END))
            return [r["trading_date"] for r in cur.fetchall()]

def fetch_1m(key, day, expired=False):
    enc = quote(key, safe="")
    if expired:
        url = f"{V2}/expired-instruments/historical-candle/{enc}/1minute/{day.isoformat()}/{day.isoformat()}"
    else:
        url = f"{V3_HIST}/{enc}/minutes/1/{day.isoformat()}/{day.isoformat()}"
    j = get_json(url)
    out = []
    for a in (j.get("data") or {}).get("candles") or []:
        if len(a) < 6:
            continue
        try:
            ts = datetime.fromisoformat(str(a[0]).replace("Z", "+00:00")).astimezone(IST)
            oi = int(float(a[6])) if len(a) > 6 and a[6] is not None else None
            out.append({
                "ts": ts,
                "open": float(a[1]),
                "high": float(a[2]),
                "low": float(a[3]),
                "close": float(a[4]),
                "volume": int(float(a[5] or 0)),
                "oi": oi,
            })
        except Exception:
            pass
    return sorted(out, key=lambda x: x["ts"])

def build_market_aligned_1h(rows):
    rows = [
        r for r in rows
        if dtime(9,15) <= r["ts"].time().replace(tzinfo=None) < dtime(15,30)
    ]
    buckets = {}
    for r in rows:
        ts = r["ts"]
        mins = (ts.hour * 60 + ts.minute) - (9 * 60 + 15)
        idx = mins // 60
        start = ts.replace(hour=9, minute=15, second=0, microsecond=0) + timedelta(hours=idx)
        end = start + timedelta(hours=1)

        if end.time().replace(tzinfo=None) > LAST_COMPLETED_HOUR_END:
            continue

        b = buckets.get(start)
        if b is None:
            buckets[start] = {
                "start": start,
                "end": end,
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
            }
        else:
            b["high"] = max(b["high"], r["high"])
            b["low"] = min(b["low"], r["low"])
            b["close"] = r["close"]

    return [buckets[k] for k in sorted(buckets)]

def option_expiries(spot_key):
    exps = set()
    try:
        j = get_json(f"{V2}/expired-instruments/expiries", params={"instrument_key": spot_key})
        for x in j.get("data") or []:
            v = x if isinstance(x, str) else (
                x.get("expiry") or x.get("expiry_date") if isinstance(x, dict) else None
            )
            if v:
                try:
                    exps.add(date.fromisoformat(str(v)[:10]))
                except Exception:
                    pass
    except Exception:
        pass

    try:
        j = get_json(f"{V2}/option/contract", params={"instrument_key": spot_key})
        for r in j.get("data") or []:
            if r.get("expiry"):
                try:
                    exps.add(date.fromisoformat(str(r["expiry"])[:10]))
                except Exception:
                    pass
    except Exception:
        pass

    return sorted(exps)

def option_contract_rows(spot_key, expiry):
    today = datetime.now(IST).date()
    if expiry < today:
        j = get_json(
            f"{V2}/expired-instruments/option/contract",
            params={"instrument_key": spot_key, "expiry_date": expiry.isoformat()},
        )
        src = "EXPIRED"
    else:
        j = get_json(
            f"{V2}/option/contract",
            params={"instrument_key": spot_key, "expiry_date": expiry.isoformat()},
        )
        src = "CURRENT"
    return src, j.get("data") or []

def pick_ce_near_candle_high(spot_key, trade_day, candle_high):
    exps = [e for e in option_expiries(spot_key) if e >= trade_day]
    if not exps:
        raise ValueError("no option expiry")

    expiry = exps[0]
    src, rows = option_contract_rows(spot_key, expiry)

    candidates = []
    for r in rows:
        typ = str(r.get("instrument_type") or r.get("option_type") or "").upper()
        if typ != "CE":
            continue
        strike = r.get("strike_price") if r.get("strike_price") is not None else r.get("strike")
        key = r.get("instrument_key")
        if strike is None or not key:
            continue
        strike = float(strike)
        candidates.append((abs(strike - candle_high), strike, str(key)))

    if not candidates:
        raise ValueError("no CE contracts")

    candidates.sort(key=lambda x: (x[0], x[1]))
    _, strike, key = candidates[0]
    return {
        "expiry": expiry,
        "src": src,
        "strike": strike,
        "key": key,
    }

def aggregate_option_hour(rows, start, end):
    w = [r for r in rows if start <= r["ts"] < end]
    if not w:
        return None
    return {
        "open": w[0]["open"],
        "high": max(r["high"] for r in w),
        "low": min(r["low"] for r in w),
        "close": w[-1]["close"],
    }

def blank(sym, key, day, candle, day_high=None):
    fall_pct = (candle["close"] / candle["open"] - 1) * 100 if candle["open"] else None
    return {
        "study_start": START,
        "study_end": END,
        "run_id": RUN_ID,
        "trading_date": day,
        "symbol": sym,
        "spot_instrument_key": key,
        "candle_start": candle["start"],
        "candle_end": candle["end"],
        "spot_open": candle["open"],
        "spot_high": candle["high"],
        "spot_low": candle["low"],
        "spot_close": candle["close"],
        "spot_fall_pct": fall_pct,
        "day_high": day_high,
        "is_day_high_candle": (day_high is not None and abs(candle["high"] - day_high) < 1e-9),
        "option_type": "CE",
        "option_expiry": None,
        "option_strike": None,
        "option_instrument_key": None,
        "option_open": None,
        "option_high": None,
        "option_low": None,
        "option_close": None,
        "trigger_level": None,
        "trigger_reached": False,
        "trigger_time": None,
        "option_price_at_trigger": None,
        "minutes_to_trigger": None,
        "max_option_price_after_candle": None,
        "eod_option_price": None,
        "eod_return_from_candle_close_pct": None,
        "data_status": "OK",
        "error_message": None,
    }

def process_candle(sym, spot_key, day, candle, day_high):
    z = blank(sym, spot_key, day, candle, day_high)

    fall_pct = -z["spot_fall_pct"] if z["spot_fall_pct"] is not None else 0
    if candle["close"] >= candle["open"] or fall_pct < MIN_FALL_PCT:
        return None  # not a falling 1H candle

    # Strict rule: this 1H candle's HIGH must be the full-session DAY HIGH.
    if abs(candle["high"] - day_high) > 1e-9:
        return None

    ce = pick_ce_near_candle_high(spot_key, day, candle["high"])
    z["option_expiry"] = ce["expiry"]
    z["option_strike"] = ce["strike"]
    z["option_instrument_key"] = ce["key"]

    option_rows = fetch_1m(ce["key"], day, expired=(ce["src"] == "EXPIRED"))
    if not option_rows:
        raise ValueError("option 1m history unavailable")

    hour = aggregate_option_hour(option_rows, candle["start"], candle["end"])
    if hour is None:
        raise ValueError("no option bars inside falling 1H candle")

    z["option_open"] = hour["open"]
    z["option_high"] = hour["high"]
    z["option_low"] = hour["low"]
    z["option_close"] = hour["close"]

    # Reverse-break trigger = reclaim/retest of the CE's own 1H high.
    trigger = hour["high"]
    z["trigger_level"] = trigger

    after = [
        r for r in option_rows
        if r["ts"] >= candle["end"]
        and r["ts"].time().replace(tzinfo=None) < dtime(15,30)
    ]

    if after:
        z["max_option_price_after_candle"] = max(r["high"] for r in after)
        z["eod_option_price"] = after[-1]["close"]

        if hour["close"]:
            z["eod_return_from_candle_close_pct"] = (
                z["eod_option_price"] / hour["close"] - 1
            ) * 100

        hit = next((r for r in after if r["high"] >= trigger), None)
        if hit:
            z["trigger_reached"] = True
            z["trigger_time"] = hit["ts"] + timedelta(minutes=1)
            z["option_price_at_trigger"] = trigger
            z["minutes_to_trigger"] = int(
                (z["trigger_time"] - candle["end"]).total_seconds() // 60
            )

    return z

def main():
    if not DB or not TOKEN:
        raise RuntimeError("NEON_DATABASE_URL and UPSTOX_TOKEN are required")

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()

    uni = universe()
    days = trading_dates()
    log(f"symbols={len(uni)} dates={len(days)}")

    rows = []
    falling = 0
    failed = 0

    for di, day in enumerate(days, 1):
        log(f"DATE {day} ({di}/{len(days)})")
        for i, u in enumerate(uni, 1):
            sym = u["symbol"]
            key = u["spot_instrument_key"]

            try:
                spot = fetch_1m(key, day)
                session_spot = [
                    r for r in spot
                    if dtime(9,15) <= r["ts"].time().replace(tzinfo=None) < dtime(15,30)
                ]
                if not session_spot:
                    continue

                day_high = max(r["high"] for r in session_spot)
                candles = build_market_aligned_1h(spot)

                for candle in candles:
                    if candle["close"] >= candle["open"]:
                        continue

                    fall_pct = (candle["open"] - candle["close"]) / candle["open"] * 100
                    if fall_pct < MIN_FALL_PCT:
                        continue

                    # Only the falling 1H candle that contains the full-session day high qualifies.
                    if abs(candle["high"] - day_high) > 1e-9:
                        continue

                    falling += 1
                    try:
                        r = process_candle(sym, key, day, candle, day_high)
                        if r:
                            rows.append(r)
                    except Exception as exc:
                        r = blank(sym, key, day, candle, day_high)
                        r["data_status"] = "ERROR"
                        r["error_message"] = str(exc)[:1000]
                        rows.append(r)
                        failed += 1

                    if len(rows) >= 50:
                        with db() as conn:
                            with conn.cursor() as cur:
                                cur.executemany(UPSERT, rows)
                            conn.commit()
                        rows = []

                if i % 25 == 0:
                    time.sleep(0.15)

            except Exception as exc:
                log(f"{day} {sym} spot error: {exc}")
                failed += 1

    if rows:
        with db() as conn:
            with conn.cursor() as cur:
                cur.executemany(UPSERT, rows)
            conn.commit()

    q = """
    SELECT
      COUNT(*) FILTER(WHERE data_status='OK') AS valid_option_cases,
      COUNT(*) FILTER(WHERE data_status='OK' AND trigger_reached) AS trigger_reached,
      COUNT(*) FILTER(WHERE data_status='OK' AND NOT trigger_reached) AS trigger_not_reached,
      ROUND(
        100.0 * COUNT(*) FILTER(WHERE data_status='OK' AND trigger_reached)
        / NULLIF(COUNT(*) FILTER(WHERE data_status='OK'),0), 1
      ) AS trigger_rate_pct,
      ROUND(AVG(minutes_to_trigger) FILTER(WHERE data_status='OK' AND trigger_reached),1)
        AS avg_minutes_to_trigger,
      ROUND(
        PERCENTILE_CONT(.5) WITHIN GROUP(ORDER BY minutes_to_trigger)
        FILTER(WHERE data_status='OK' AND trigger_reached)::numeric, 1
      ) AS median_minutes_to_trigger,
      ROUND(AVG(spot_fall_pct) FILTER(WHERE data_status='OK'),3) AS avg_spot_fall_pct
    FROM public.option_break_day_high_backtest
    WHERE study_start=%s AND study_end=%s
    """
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(q, (START, END))
            s = dict(cur.fetchone())

    safe = {}
    for k, v in s.items():
        if v is None or isinstance(v, (bool, int, float, str)):
            safe[k] = v
        else:
            try:
                safe[k] = float(v)
            except Exception:
                safe[k] = str(v)

    summary = {
        **safe,
        "falling_1h_candles_detected": falling,
        "failed": failed,
        "rule": {
            "spot_candle": "completed market-aligned 1H candle with close < open AND its high equals the full-session spot day high",
            "strike": "nearest available CE strike to the spot DAY HIGH / qualifying 1H candle HIGH",
            "reference": "CE high made during the same falling 1H candle",
            "success": "after the 1H candle ends, CE trades back to/reaches that reference high before EOD",
            "timing": "scenario may occur in any completed 1H candle from 09:15-15:15",
        },
    }

    qs = """
    INSERT INTO public.option_break_day_high_summary (
      study_start,study_end,run_id,falling_1h_candles,valid_option_cases,
      trigger_reached,trigger_not_reached,failed,summary
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT(study_start,study_end) DO UPDATE SET
      run_id=EXCLUDED.run_id,
      generated_at=NOW(),
      falling_1h_candles=EXCLUDED.falling_1h_candles,
      valid_option_cases=EXCLUDED.valid_option_cases,
      trigger_reached=EXCLUDED.trigger_reached,
      trigger_not_reached=EXCLUDED.trigger_not_reached,
      failed=EXCLUDED.failed,
      summary=EXCLUDED.summary
    """
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                qs,
                (
                    START, END, RUN_ID, falling,
                    s["valid_option_cases"],
                    s["trigger_reached"],
                    s["trigger_not_reached"],
                    failed,
                    Jsonb(summary),
                ),
            )
        conn.commit()

    log("COMPLETE")
    log(str(summary))

if __name__ == "__main__":
    main()
