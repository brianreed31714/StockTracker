"""Research-only ZPTA daily swing portfolio and overnight-loss stress audit.

A completed day-t signal enters at day-(t+1) OPEN and exits at day-(t+h)
CLOSE, with fixed costs. Printed prices are not verified executable fills.
No broker calls, stop execution, trading orders, or runtime configuration.
"""
from __future__ import annotations

import math
from analysis.zpta_daily_swing_research import daily_signals
from analysis.zpta_daily_robustness import COHORTS


def loss_budget_stress(net_position_return_pct, starting_cash=1000.0,
                       max_position_dollars=150.0,
                       max_position_equity_pct=0.15,
                       daily_loss_limit_pct=0.03):
    """Translate a hypothetical net POSITION return into sleeve-dollar exposure.

    A daily loss threshold is a desired guard, NOT a guarantee against
    overnight gaps, illiquidity or failed exit orders.
    """
    vals = (net_position_return_pct, starting_cash, max_position_dollars,
            max_position_equity_pct, daily_loss_limit_pct)
    if any(not math.isfinite(x) for x in vals):
        raise ValueError("Nonfinite risk input")
    if starting_cash <= 0 or max_position_dollars <= 0 or not 0 < max_position_equity_pct <= 1:
        raise ValueError("Invalid portfolio sizing")
    if not 0 < daily_loss_limit_pct < 1 or net_position_return_pct < -100:
        raise ValueError("Invalid risk/return")
    position = min(max_position_dollars, starting_cash * max_position_equity_pct)
    dollars = position * net_position_return_pct / 100
    limit = starting_cash * daily_loss_limit_pct
    return {
        "position_dollars": round(position, 4),
        "net_sleeve_pnl_dollars": round(dollars, 4),
        "net_sleeve_return_pct": round(100 * dollars / starting_cash, 4),
        "daily_loss_budget_dollars": round(limit, 4),
        "loss_exceeds_one_day_budget": dollars < -limit,
        "warning": "ILLUSTRATIVE_STRESS_NOT_EXECUTABLE_FILL_OR_GUARANTEED_STOP",
    }


def simulate_shadow_sleeve(bars, signal_name, horizon=3, starting_cash=1000.0,
                           max_position_dollars=150.0,
                           max_position_equity_pct=0.15,
                           min_signal_dollar_volume=25000.0,
                           one_way_cost=0.01,
                           daily_loss_limit_pct=0.03,
                           max_drawdown_pct=0.08,
                           train_fraction=0.7):
    """Fixed-size, non-overlapping next-open/close-to-close paper scenario.

    Mark open positions to each session close at a hypothetical net exit
    price; intraday LOW marks are separate pessimistic price proxies.
    These marks do not assume a limit-order fill or an executable stop.
    """
    if signal_name not in COHORTS:
        raise ValueError("Unknown preregistered signal")
    if horizon not in (1, 3, 5):
        raise ValueError("Unsupported horizon")
    if not 0 <= one_way_cost < 0.5 or min_signal_dollar_volume < 0:
        raise ValueError("Invalid costs/liquidity")
    if not 0 < train_fraction < 1 or not 0 < max_drawdown_pct < 1:
        raise ValueError("Invalid split/drawdown threshold")
    loss_budget_stress(0, starting_cash, max_position_dollars,
                       max_position_equity_pct, daily_loss_limit_pct)
    cut = int(len(bars) * train_fraction)
    equity = starting_cash
    peak = starting_cash
    max_close_drawdown = 0.0
    max_low_proxy_drawdown = 0.0
    last_exit = -1
    trades = []
    day_loss_proxy_breaches = 0
    for i in range(max(10, cut), len(bars) - horizon):
        if i < last_exit:
            continue
        signal = bars[i]
        if signal["volume"] <= 0 or signal["close"] * signal["volume"] < min_signal_dollar_volume:
            continue
        if signal_name != "all_eligible_sessions" and signal_name not in daily_signals(bars, i):
            continue
        entry_i, exit_i = i + 1, i + horizon
        entry_open = bars[entry_i]["open"]
        exit_close = bars[exit_i]["close"]
        if min(entry_open, exit_close) <= 0:
            raise ValueError("Nonpositive prices")
        invested = min(max_position_dollars, equity * max_position_equity_pct)
        shares = invested / (entry_open * (1 + one_way_cost))
        uninvested = equity - invested
        before_equity = equity
        prior_close_mark = equity
        for j in range(entry_i, exit_i + 1):
            bar = bars[j]
            if min(bar["low"], bar["close"]) <= 0:
                raise ValueError("Nonpositive mark")
            close_mark = uninvested + shares * bar["close"] * (1 - one_way_cost)
            low_mark = uninvested + shares * bar["low"] * (1 - one_way_cost)
            peak = max(peak, close_mark)
            max_close_drawdown = min(max_close_drawdown, close_mark / peak - 1)
            max_low_proxy_drawdown = min(max_low_proxy_drawdown, low_mark / peak - 1)
            if low_mark < prior_close_mark * (1 - daily_loss_limit_pct):
                day_loss_proxy_breaches += 1
            prior_close_mark = close_mark
        equity = uninvested + shares * exit_close * (1 - one_way_cost)
        peak = max(peak, equity)
        position_return = (equity - before_equity) / invested * 100
        trades.append({
            "signal_date": signal["date"],
            "entry_date": bars[entry_i]["date"],
            "exit_date": bars[exit_i]["date"],
            "entry_index": entry_i,
            "exit_index": exit_i,
            "invested_dollars": round(invested, 4),
            "net_pnl_dollars": round(equity - before_equity, 4),
            "net_position_return_pct": round(position_return, 4),
            "sleeve_equity_after_exit": round(equity, 4),
        })
        last_exit = exit_i
    return {
        "signal": signal_name,
        "horizon_sessions": horizon,
        "train_cut_index": cut,
        "holdout_sessions": len(bars) - cut,
        "starting_cash": starting_cash,
        "position_cap_dollars": max_position_dollars,
        "position_cap_equity_fraction": max_position_equity_pct,
        "one_way_cost_fraction": one_way_cost,
        "nonoverlapping_trades": len(trades),
        "ending_equity": round(equity, 4),
        "total_sleeve_return_pct": round((equity / starting_cash - 1) * 100, 4),
        "max_daily_close_mark_drawdown_pct": round(max_close_drawdown * 100, 4),
        "max_intraday_low_proxy_drawdown_pct": round(max_low_proxy_drawdown * 100, 4),
        "intraday_low_proxy_daily_budget_breaches": day_loss_proxy_breaches,
        "max_drawdown_target_exceeded": max_close_drawdown < -max_drawdown_pct,
        "trades": trades,
        "warnings": [
            "UNVERIFIED_OHLCV_AND_CORPORATE_ACTIONS",
            "HOLDOUT_ALREADY_EXAMINED_NOT_PRISTINE",
            "PRINTED_OPEN_AND_CLOSE_NOT_GUARANTEED_EXECUTABLE_FILLS",
            "INTRADAY_LOW_MARK_NOT_STOP_EXECUTION_OR_KNOWN_SEQUENCE",
            "COST_ASSUMPTION_NOT_MEASURED_OTC_BID_ASK",
            "NO_OVERNIGHT_STOP_GUARANTEE_OR_BROKER_TRADE_ELIGIBILITY",
            "DAILY_LOSS_BUDGET_IS_MONITORING_PROXY_NOT_ENFORCED_KILL_SWITCH",
            "FULL_STRATEGY_RETURNS_IGNORE_DIVIDENDS_TAXES_AND_IDLE_CASH_YIELD",
        ],
        "eligible_for_live_trading": False,
    }
