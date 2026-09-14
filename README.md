# Option Break — 16-case Futures OI Diagnostic

Purpose:
Compare the 5 +10%-target-first winners with the 11 -5%-stop-first cases.

For each fast first-hour Option Break:
- futures price/OI at 09:20 baseline
- futures price/OI at exact CE reclaim trigger
- cumulative futures price %
- cumulative futures OI %
- price/OI change over final 5 minutes before trigger
- price/OI change over final 10 minutes before trigger
- classify each window:
  LONG_BUILDUP
  SHORT_BUILDUP
  SHORT_COVERING
  LONG_UNWINDING

Neon output:
public.option_break_futures_oi_16

Required Railway variables:
NEON_DATABASE_URL
UPSTOX_TOKEN

Start command is embedded:
python option_break_futures_oi_16.py

Note:
Upstox V3 historical candle responses include Open Interest as candle element [6],
which is why this study can reconstruct historical futures OI alongside price.


FIX: explicit 21-column INSERT; corrected placeholder/value count mismatch.
