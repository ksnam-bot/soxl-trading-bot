from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


def _d(s: str | None) -> dt.date | None:
    return dt.date.fromisoformat(s) if s else None


def _s(d: dt.date | None) -> str | None:
    return d.isoformat() if d else None


@dataclass
class TierPosition:
    slot: int
    buy_date: dt.date
    buy_price: float
    qty: float
    cost: float  # buy_price * qty
    buy_fee: float
    target_price: float
    cutoff_date: dt.date

    def to_json(self) -> dict:
        d = asdict(self)
        d["buy_date"] = _s(self.buy_date)
        d["cutoff_date"] = _s(self.cutoff_date)
        return d

    @classmethod
    def from_json(cls, d: dict) -> "TierPosition":
        d = dict(d)
        d["buy_date"] = _d(d["buy_date"])
        d["cutoff_date"] = _d(d["cutoff_date"])
        return cls(**d)


@dataclass
class PendingOrder:
    slot: int
    order_price: float
    seed: float
    for_date: dt.date

    def to_json(self) -> dict:
        d = asdict(self)
        d["for_date"] = _s(self.for_date)
        return d

    @classmethod
    def from_json(cls, d: dict) -> "PendingOrder":
        d = dict(d)
        d["for_date"] = _d(d["for_date"])
        return cls(**d)


@dataclass
class PortfolioState:
    portfolio_id: str
    as_of_date: dt.date | None  # last trading date whose close has been processed
    cash: float
    total_shares: float = 0.0
    open_positions: list[TierPosition] = field(default_factory=list)
    pending_order: PendingOrder | None = None
    # seed_mode == "global" (안정형)
    compounded_principal: float | None = None
    # seed_mode == "per_slot" (공격형): last seed used per slot / last realized profit per slot
    slot_seed: dict[int, float] = field(default_factory=dict)
    slot_profit: dict[int, float] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)  # append-only daily log for auditing

    def to_json(self) -> dict:
        return {
            "portfolio_id": self.portfolio_id,
            "as_of_date": _s(self.as_of_date),
            "cash": self.cash,
            "total_shares": self.total_shares,
            "open_positions": [p.to_json() for p in self.open_positions],
            "pending_order": self.pending_order.to_json() if self.pending_order else None,
            "compounded_principal": self.compounded_principal,
            "slot_seed": {str(k): v for k, v in self.slot_seed.items()},
            "slot_profit": {str(k): v for k, v in self.slot_profit.items()},
            "history": self.history,
        }

    @classmethod
    def from_json(cls, d: dict) -> "PortfolioState":
        return cls(
            portfolio_id=d["portfolio_id"],
            as_of_date=_d(d.get("as_of_date")),
            cash=d["cash"],
            total_shares=d.get("total_shares", 0.0),
            open_positions=[TierPosition.from_json(p) for p in d.get("open_positions", [])],
            pending_order=PendingOrder.from_json(d["pending_order"]) if d.get("pending_order") else None,
            compounded_principal=d.get("compounded_principal"),
            slot_seed={int(k): v for k, v in d.get("slot_seed", {}).items()},
            slot_profit={int(k): v for k, v in d.get("slot_profit", {}).items()},
            history=d.get("history", []),
        )


def load_state(path: Path) -> PortfolioState:
    return PortfolioState.from_json(json.loads(path.read_text(encoding="utf-8")))


def save_state(state: PortfolioState, path: Path) -> None:
    path.write_text(json.dumps(state.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
