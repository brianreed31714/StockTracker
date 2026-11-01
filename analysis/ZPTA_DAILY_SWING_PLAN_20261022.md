# ZPTA daily swing pivot — research scope (2026-10-22)

**User objective:** Find statistically favorable day-to-day ZPTA entry zones, buying near potential multi-day lows *before* a subsequent rebound, rather than focus on minute-scale trades. A low can only be identified definitively with hindsight; research must use signals observable before an order is placed.

## Key change

Prioritize end-of-day data and **next-session** decisions. A 15-minute delay is not by itself disqualifying for a next-day signal generated after complete official daily OHLCV settles, although timely quote/bid-ask data is still important before order execution. IBKR's proposed $8 OTC feed is not necessary merely to research completed daily closes. Do not require the user to subscribe or fund an account until a separate need for ZPTA-specific broker execution/quote access is verified.

## Prior data and uncertainty

- The 50-session exploratory intraday study found >=5% prior-close-to-low dips on 21 sessions, 14 (67%) recovered half the low-to-prior-close drop by close; **that is intraday recovery, not next-day profitable swing timing**.
- The earlier 50-session descriptive close-to-close review reported 8 >=5% down days, half followed by positive next-day returns, but mean next-day close-to-close return -2.44%. Public rounded OHLC and tiny cohorts make these preliminary, not a validated model.
- The existing 1,056 ZPTA 5/15/60-min predictions were delayed ~15.6 minutes at median, and 736 were created after horizon due; **do not use those accuracies**. Volume was zero for all 80 published observations, so the shadow liquidity gate correctly blocked trades.
- A daily swing strategy must additionally handle delisting risk, OTC spreads, corporate actions, trading halts, non-executable displayed lows, and overnight gaps.

## Fixed candidate daily setups (no parameter tuning on test set)

1. One completed session close >=5% below preceding close (falling-knife baseline).
2. Two consecutive declining closes totaling >=5%.
3. A declining close >=10% below the prior ten-session high (larger drawdown).
4. Three-session RSI <=25 (oversold).
5. First higher close with the close in the upper 35% of the daily range after a prior >=5% decline (reversal confirmation; may enter later but reduces falling-knife risk).

Compare each strategy with unconditional eligible next-session entries, as well as randomized matched-weekday or matched-volatility control entries in future work. Analyze buying at **next day's open** and exits at the close 1, 3, and 5 sessions later. Apply 1% assumed friction each side as a sensitivity scenario, including spread/slippage and missed fills once quotes become available. Use only **signal-day** volume to decide if research entry is even eligible.

## Next research iterations

- Source complete, precision-priced, split-adjusted daily ZPTA OHLCV back through earliest consistent symbol history, auditing reverse splits, adjusted volume, name changes, and data gaps. Public rounded tables are not enough for penny-stock parameter optimization.
- Use `analysis/zpta_daily_swing_research.py` for predeclared signal cohorts, 70/30 chronological train/test split, and purging of training positions whose exit overlaps the holdout.
- Record win percentage, mean/median return and worst holding-window excursion for 1/3/5 sessions, compared to unconditional-day baseline. **Do not treat overlap as independent or these averages as portfolio returns.**
- Test next-day **precommitted limit orders** at predicted support zones (e.g., below prior close), but mark as hypothetical unless fill/queue realism can be established. Daily lows alone cannot guarantee execution. Account for missed fills, overnight gaps, market halts, and conservative outcomes when stop/target order cannot be inferred.
- Require sufficiently many independent, non-overlapping instances, strong holdout results, positive net expected value, bounded adverse excursion, and verified current ZPTA broker quotes before proposing executable shadow entries. Reassess data subscription only if it helps validated execution studies.

## Reproducibility

```shell
python -m analysis.zpta_daily_swing_research validated_zpta_daily.csv --source "verified-provider-name" --split-adjustment-verified --output analysis/performance/zpta_daily_swing.json
python -m unittest tests.test_zpta_daily_swing_research
```

**Current status:** Research module and deterministic tests committed to PR #6; verified full-length daily dataset has **not** been ingested, so no strategy has demonstrated positive net expectancy. Existing paper/shadow code unchanged. November 2 remains a decision deadline, not permission or proof to route real-money orders.
