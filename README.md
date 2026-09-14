# OPTION BREAK — 30-Minute Day-High Backtest

Rule:
1. Use market-aligned 30-minute SPOT candles:
   09:15-09:45, 09:45-10:15, 10:15-10:45, ... , 14:45-15:15.
2. The 30m SPOT candle must be bearish: close < open.
3. Its high must equal the full-session SPOT day high.
4. Select the nearest CE strike to that day-high / candle-high.
5. Record that CE's high during the same falling 30-minute candle.
6. After the candle closes, the SAME CE must reclaim/reach that old CE high within the NEXT 30 minutes.
7. Store trigger reached, first trigger time, minutes to trigger, option levels and prices.

This is the requested 30-minute version. It does NOT use the prior <=5-minute filter.
It also does NOT run the aborted Fast-16 target/stop study.

Neon:
- public.option_break_30m_day_high_backtest
- public.option_break_30m_day_high_summary

Start:
python option_break_30m_day_high_backtest.py
