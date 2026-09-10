"""Builds the small, non-sensitive JSON snapshot published to docs/latest.json
for the mobile dashboard (GitHub Pages). Deliberately excludes cash/holding
value/total account value — only trade signals (prices, quantities, dates),
since this file ends up on a public (if unlisted) URL on the free GitHub
Pages tier.
"""
from __future__ import annotations

import datetime as dt

from .config import PortfolioConfig
from .engine import DayReport
from .state import PortfolioState


def portfolio_summary(cfg: PortfolioConfig, state: PortfolioState, report: DayReport) -> dict:
    return {
        "id": cfg.id,
        "name": cfg.name,
        "trading_date": report.trading_date.isoformat(),
        "close": report.close,
        "filled_buy": (
            {
                "slot": report.filled_buy.slot,
                "buy_price": report.filled_buy.buy_price,
                "qty": report.filled_buy.qty,
            }
            if report.filled_buy
            else None
        ),
        "unfilled_buy_price": report.unfilled_buy_price,
        "sells": [
            {
                "slot": s.slot,
                "sell_price": s.sell_price,
                "qty": s.qty,
                "reason": s.reason,
            }
            for s in report.sells
        ],
        "no_open_slot_today": report.no_open_slot_today,
        "pending_order": (
            {
                "slot": report.new_pending_order.slot,
                "for_date": report.new_pending_order.for_date.isoformat(),
                "ladder": [{"price": l.price, "qty": l.qty} for l in report.new_pending_ladder],
            }
            if report.new_pending_order
            else None
        ),
        "open_positions": [
            {
                "slot": p.slot,
                "buy_date": p.buy_date.isoformat(),
                "buy_price": p.buy_price,
                "qty": p.qty,
                "target_price": p.target_price,
                "cutoff_date": p.cutoff_date.isoformat(),
            }
            for p in state.open_positions
        ],
    }


def build_snapshot(portfolio_summaries: list[dict]) -> dict:
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "portfolios": portfolio_summaries,
    }
