"""Core tiered LOC-ladder trading engine.

This is a faithful re-implementation of the buy/sell/seed-compounding logic
found in the user's two licensed trading-strategy spreadsheets (공격형/안정형).
It is a day-by-day state machine: given the portfolio's current state and a
freshly-fetched close price for "today", it

  1. resolves the BUY order that was placed for today (computed yesterday),
  2. resolves any SELL (target-hit or loss-cut/timeout) for currently open
     tiers,
  3. figures out which tier slot (if any) is free to open next, sizes its
     seed, and builds tomorrow's laddered LOC buy order.

Column-formula references in comments (e.g. "W6", "Q7") point back to the
RECORD sheet of the original spreadsheets for traceability.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from .calendar_utils import next_trading_day, workday
from .config import PresetConfig
from .state import PendingOrder, PortfolioState, TierPosition


def round_down(x: float, decimals: int = 2) -> float:
    """Excel ROUNDDOWN (toward zero)."""
    factor = 10**decimals
    return math.floor(x * factor + 1e-9) / factor


def round_up(x: float, decimals: int = 2) -> float:
    """Excel ROUNDUP (away from zero)."""
    factor = 10**decimals
    return math.ceil(x * factor - 1e-9) / factor


def floor_int(x: float) -> int:
    """Excel INT() for non-negative numbers."""
    return int(math.floor(x + 1e-9))


@dataclass
class LadderLine:
    price: float
    qty: int


@dataclass
class BuyFillResult:
    slot: int
    buy_price: float
    qty: int
    cost: float
    fee: float


@dataclass
class SellResult:
    slot: int
    buy_date: dt.date
    buy_price: float
    qty: int
    sell_price: float
    proceeds: float
    sell_fee: float
    profit: float
    reason: str  # "target" | "loss_cut"


@dataclass
class DayReport:
    trading_date: dt.date
    close: float
    filled_buy: BuyFillResult | None = None
    unfilled_buy_price: float | None = None
    sells: list[SellResult] = field(default_factory=list)
    new_pending_order: PendingOrder | None = None
    new_pending_ladder: list[LadderLine] = field(default_factory=list)
    no_open_slot_today: bool = False


def ladder_quantity(cfg: PresetConfig, slot: int, seed: float, order_price: float, close_price: float) -> int:
    """W-column formula: total shares filled today given the close price.

    Faithful port of the FIXODC (건수 고정) branch; FIXQN (수량 고정) is
    included for completeness but neither shipped preset currently uses it.
    """
    if order_price <= 0 or seed <= 0:
        return 0

    base_qty = floor_int(seed / order_price)
    bottom = round_down(order_price * (1 + cfg.extrange), 2)

    last_slot = slot == cfg.split
    fixodc_disabled = cfg.order_type == "FIXODC" and cfg.odcount == 0
    fixqn_disabled = cfg.order_type == "FIXQN" and not cfg.step
    if last_slot or fixodc_disabled or fixqn_disabled:
        return base_qty

    threshold = max(bottom, close_price)

    if cfg.order_type == "FIXODC":
        if bottom <= 0:
            return base_qty
        fixq = floor_int((seed / bottom - seed / order_price) / cfg.odcount)
        if fixq <= 0:
            return base_qty
        # ODCOUNT *extra* rungs beyond the base price (matches the EXTRA sheet's
        # preview table, which lays down ODCOUNT additional price levels).
        max_extra = min(50, cfg.odcount)
        best = base_qty
        for k in range(1, max_extra + 1):
            cum = base_qty + k * fixq
            if cum <= 0:
                continue
            implied_price = seed / cum
            if implied_price >= threshold:
                best = cum
            else:
                break  # implied price is monotonically decreasing in k
        return best

    # FIXQN (수량 고정 모드)
    step = cfg.step or 0
    if step <= 1:
        return floor_int(seed / close_price) if close_price > 0 else 0
    best = base_qty
    for k in range(1, 51):
        cum = base_qty + k * step
        if cum <= 0:
            continue
        implied_price = seed / cum
        if implied_price >= threshold:
            best = cum
        else:
            break
    return best


def ladder_breakdown(cfg: PresetConfig, slot: int, seed: float, order_price: float) -> list[LadderLine]:
    """Human-readable version of the same ladder, for the notification message.

    Mirrors the EXTRA sheet's Q7/R7 columns: one line at the base order price,
    then ODCOUNT extra lines at progressively lower prices with the
    incremental quantity per line.
    """
    if order_price <= 0 or seed <= 0:
        return []

    base_qty = floor_int(seed / order_price)
    lines = [LadderLine(price=order_price, qty=base_qty)]

    if slot == cfg.split:
        return lines  # last slot: lump-sum only, no laddering (matches W formula)

    bottom = round_down(order_price * (1 + cfg.extrange), 2)

    if cfg.order_type == "FIXODC" and cfg.odcount > 0 and bottom > 0:
        fixq = floor_int((seed / bottom - seed / order_price) / cfg.odcount)
        if fixq > 0:
            cum = base_qty
            for _ in range(cfg.odcount):
                cum += fixq
                price = round_down(seed / cum, 2)
                lines.append(LadderLine(price=price, qty=fixq))
    elif cfg.order_type == "FIXQN" and cfg.step and cfg.step > 1 and bottom > 0:
        cum = base_qty
        step = cfg.step
        while True:
            next_cum = cum + step
            price = round_down(seed / next_cum, 2)
            if price < bottom:
                break
            lines.append(LadderLine(price=price, qty=step))
            cum = next_cum
            if len(lines) > 50:
                break

    return lines


def _size_seed(cfg: PresetConfig, state: PortfolioState, slot: int) -> float:
    weight = cfg.weights[slot - 1]
    if cfg.seed_mode == "global":
        base = state.compounded_principal if state.compounded_principal is not None else cfg.principal
        target_seed = base * weight
    else:  # per_slot
        prev_seed = state.slot_seed.get(slot, cfg.principal * weight)
        prev_profit = state.slot_profit.get(slot, 0.0)
        if prev_profit >= 0:
            target_seed = prev_seed + prev_profit * cfg.comp / cfg.split
        else:
            target_seed = prev_seed
    return min(target_seed, state.cash)


def process_trading_day(
    cfg: PresetConfig,
    state: PortfolioState,
    trading_date: dt.date,
    close_price: float,
) -> DayReport:
    """Advance the portfolio state by exactly one trading day.

    `trading_date`/`close_price` must be the NEXT trading day after
    `state.as_of_date` (the caller is responsible for walking the calendar
    day by day if catching up after an outage).
    """
    report = DayReport(trading_date=trading_date, close=close_price)

    # --- Step 1: resolve yesterday's pending buy order against today's close ---
    po = state.pending_order
    if po is not None and po.for_date == trading_date:
        if close_price <= po.order_price:
            qty = ladder_quantity(cfg, po.slot, po.seed, po.order_price, close_price)
            if qty > 0:
                cost = round(close_price * qty, 2)
                fee = round(cost * cfg.fee, 2)
                state.cash -= cost + fee
                state.total_shares += qty
                target_price = round_up(close_price * (1 + cfg.target[po.slot - 1]), 2)
                cutoff_date = workday(trading_date, cfg.loss_days[po.slot - 1])
                state.open_positions.append(
                    TierPosition(
                        slot=po.slot,
                        buy_date=trading_date,
                        buy_price=close_price,
                        qty=qty,
                        cost=cost,
                        buy_fee=fee,
                        target_price=target_price,
                        cutoff_date=cutoff_date,
                    )
                )
                if cfg.seed_mode == "per_slot":
                    state.slot_seed[po.slot] = po.seed
                report.filled_buy = BuyFillResult(slot=po.slot, buy_price=close_price, qty=qty, cost=cost, fee=fee)
        else:
            report.unfilled_buy_price = po.order_price
        state.pending_order = None

    # --- Step 2: resolve sells (target hit, or loss-cut/timeout) ---
    still_open: list[TierPosition] = []
    realized_today = 0.0
    for pos in state.open_positions:
        reason = None
        if close_price >= pos.target_price:
            reason = "target"
        elif trading_date >= pos.cutoff_date:
            reason = "loss_cut"

        if reason is None:
            still_open.append(pos)
            continue

        proceeds = round(pos.qty * close_price, 2)
        sell_fee = round(proceeds * (cfg.fee + cfg.sec), 2)
        state.cash += proceeds - sell_fee
        state.total_shares -= pos.qty
        profit = round(proceeds - sell_fee - (pos.cost + pos.buy_fee), 2)
        realized_today += profit
        if cfg.seed_mode == "per_slot":
            state.slot_profit[pos.slot] = profit
        report.sells.append(
            SellResult(
                slot=pos.slot,
                buy_date=pos.buy_date,
                buy_price=pos.buy_price,
                qty=pos.qty,
                sell_price=close_price,
                proceeds=proceeds,
                sell_fee=sell_fee,
                profit=profit,
                reason=reason,
            )
        )
    state.open_positions = still_open

    if cfg.seed_mode == "global":
        base = state.compounded_principal if state.compounded_principal is not None else cfg.principal
        state.compounded_principal = base + realized_today * cfg.comp

    # --- Step 3: figure out tomorrow's order for the next free slot ---
    state.as_of_date = trading_date
    next_date = next_trading_day(trading_date)
    active_slot = len(state.open_positions) + 1

    if active_slot > cfg.split:
        report.no_open_slot_today = True
        return report

    seed = _size_seed(cfg, state, active_slot)
    odgap = cfg.odgap[active_slot - 1]
    odp = round_down(close_price * (1 + odgap), 2)

    pending_targets = [p.target_price for p in state.open_positions]
    mocd_count = sum(1 for p in state.open_positions if p.cutoff_date == next_date)

    if not pending_targets and mocd_count == 0:
        order_price: float | None = odp
    elif (pending_targets and mocd_count == 0) or (cfg.mocbuy and mocd_count > 0):
        order_price = min(odp, min(pending_targets) - 0.01) if pending_targets else odp
    elif (not cfg.mocbuy) and mocd_count > 0:
        order_price = None  # MOC매수 OFF: 오늘 정리되는 티어와 겹치는 매수는 건너뜀
    else:
        order_price = None

    if order_price is not None and order_price > 0:
        state.pending_order = PendingOrder(slot=active_slot, order_price=order_price, seed=seed, for_date=next_date)
        report.new_pending_order = state.pending_order
        report.new_pending_ladder = ladder_breakdown(cfg, active_slot, seed, order_price)
    else:
        state.pending_order = None

    return report
