"""Builds the small JSON snapshots published under docs/ for the mobile
dashboard (GitHub Pages). At the user's request this now includes account
value / return % — be aware this lands on a public (if unlisted) URL on the
free GitHub Pages tier.
"""
from __future__ import annotations

import datetime as dt

from .config import PortfolioConfig
from .engine import DayReport
from .state import PortfolioState


def _return_pct(total_value: float, principal: float) -> float:
    if principal <= 0:
        return 0.0
    return (total_value - principal) / principal


def portfolio_summary(cfg: PortfolioConfig, state: PortfolioState, report: DayReport) -> dict:
    shares = sum(p.qty for p in state.open_positions)
    holding_value = sum(p.qty * report.close for p in state.open_positions)
    total_value = state.cash + holding_value
    principal = cfg.preset.principal

    return {
        "id": cfg.id,
        "name": cfg.name,
        "short_label": cfg.short_label,
        "trading_date": report.trading_date.isoformat(),
        "close": report.close,
        "shares": shares,
        "cash": state.cash,
        "holding_value": holding_value,
        "total_value": total_value,
        "principal": principal,
        "return_pct": _return_pct(total_value, principal),
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
                "buy_price": s.buy_price,
                "profit": s.profit,
                "profit_pct": (s.sell_price / s.buy_price - 1) if s.buy_price else 0.0,
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


def build_snapshot(portfolio_summaries: list[dict], fx: dict | None = None) -> dict:
    total_cash = sum(p["cash"] for p in portfolio_summaries)
    total_value = sum(p["total_value"] for p in portfolio_summaries)
    total_principal = sum(p["principal"] for p in portfolio_summaries)
    total_shares = sum(p["shares"] for p in portfolio_summaries)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "fx_usdkrw": fx,
        "combined": {
            "cash": total_cash,
            "shares": total_shares,
            "total_value": total_value,
            "principal": total_principal,
            "return_pct": _return_pct(total_value, total_principal),
        },
        "portfolios": portfolio_summaries,
    }


def equity_snapshot(portfolio_states: list[tuple[PortfolioConfig, PortfolioState]]) -> dict:
    """일별 총자산/수익률 흐름 — 거래 이력 페이지의 그래프용. 계좌별 시리즈 + 날짜별 합산 시리즈."""
    series = {}
    for pf, state in portfolio_states:
        label = pf.short_label or pf.name
        series[pf.id] = {
            "label": label,
            "principal": pf.preset.principal,
            "points": [
                {"date": e["date"], "total_value": e["total_value"], "return_pct": e["return_pct"]}
                for e in state.equity_log
            ],
        }

    by_date: dict[str, float] = {}
    principal_sum = sum(pf.preset.principal for pf, _ in portfolio_states)
    for pid, s in series.items():
        for pt in s["points"]:
            by_date[pt["date"]] = by_date.get(pt["date"], 0.0) + pt["total_value"]
    combined_points = [
        {
            "date": d,
            "total_value": round(v, 2),
            "return_pct": round((v - principal_sum) / principal_sum, 6) if principal_sum > 0 else 0.0,
        }
        for d, v in sorted(by_date.items())
    ]

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "combined": {"principal": principal_sum, "points": combined_points},
        "portfolios": series,
    }


def history_snapshot(portfolio_states: list[tuple[PortfolioConfig, PortfolioState]]) -> dict:
    """모든 계좌의 매수/매도 체결 이력을 하나로 합쳐서 최신순으로 정렬 — 거래 이력 페이지용."""
    entries = []
    for pf, state in portfolio_states:
        label = pf.short_label or pf.name
        for h in state.history:
            if h.get("type") not in ("buy", "sell"):
                continue
            entries.append({**h, "portfolio_id": pf.id, "portfolio_label": label})
    entries.sort(key=lambda e: (e["date"], e["portfolio_id"]), reverse=True)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "entries": entries,
    }


def config_snapshot(portfolios: list[PortfolioConfig]) -> dict:
    """Strategy parameters, for the mobile '설정값' 보기/편집 page."""
    out = []
    for pf in portfolios:
        cfg = pf.preset
        out.append(
            {
                "id": pf.id,
                "name": pf.name,
                "short_label": pf.short_label,
                "ticker": pf.ticker,
                "active": pf.active,
                "kakao_enabled": pf.kakao_enabled,
                "preset_name": cfg.name,
                "principal": cfg.principal,
                "split": cfg.split,
                "weights": cfg.weights,
                "odgap": cfg.odgap,
                "target": cfg.target,
                "loss_days": cfg.loss_days,
                "extrange": cfg.extrange,
                "comp": cfg.comp,
                "fee": cfg.fee,
                "sec": cfg.sec,
                "order_type": cfg.order_type,
                "odcount": cfg.odcount,
                "step": cfg.step,
                "mocbuy": cfg.mocbuy,
                "seed_mode": cfg.seed_mode,
            }
        )
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "portfolios": out,
    }
