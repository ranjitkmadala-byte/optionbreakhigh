# OPTION BREAK — Day High Version

Strict setup:

1. Use completed market-aligned 1-hour SPOT candles:
   09:15-10:15, 10:15-11:15, ..., 14:15-15:15.

2. Candle must be bearish:
   close < open.

3. The HIGH of that bearish 1-hour candle must equal the full-session SPOT DAY HIGH.
   Other bearish 1-hour candles are ignored.

4. Example:
   full-day high = 1000
   qualifying bearish 1H candle high = 1000
   candle low = 990

5. Select the nearest available CE strike to 1000, e.g. 1000 CE.

6. Find that CE's HIGH during the same qualifying falling 1-hour candle.
   Example: CE high = Rs 35.

7. After the 1-hour candle completes, check whether the SAME CE reaches/reclaims Rs 35 before EOD.

8. Store first trigger time, minutes to trigger, max option price after the candle, and EOD option price.

Important:
This is a historical backtest rule using the eventual full-session day high. It therefore uses end-of-day information and is not directly a live-entry rule unless you later redefine "day high" as "high-so-far".

Neon tables:
- public.option_break_day_high_backtest
- public.option_break_day_high_summary

Railway Start Command:
python option_break_day_high_backtest.py
