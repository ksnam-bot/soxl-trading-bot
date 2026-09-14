from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PresetConfig:
    """One strategy preset (공격형/안정형/...). All per-tier arrays are indexed 0..split-1."""

    name: str
    principal: float
    split: int
    weights: list[float]  # 티어별 시드 비중, sums to ~1.0
    odgap: list[float]  # 티어별 매수 주문 상한 (전일 종가 대비 %, 음수 가능)
    target: list[float]  # 티어별 매도 목표 (+%)
    loss_days: list[int]  # 티어별 손절/정리 기준 영업일
    extrange: float  # 추가 매수 범위 (라더링 하단폭, 음수)
    comp: float  # 복리율
    fee: float  # 매매 수수료율
    sec: float  # 매도시 추가 세금율 (SEC 등)
    order_type: str  # "FIXODC" (건수 고정) | "FIXQN" (수량 고정)
    odcount: int  # 건수 고정 모드: 추가 매수 단계 수
    step: int | None  # 수량 고정 모드: 단계별 증가 수량
    mocbuy: bool  # 대기 물량 없는 날 시장가/종가 매수 허용 여부
    seed_mode: str  # "global" (안정형: 계좌 전체 복리) | "per_slot" (공격형: 슬롯별 복리)

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "PresetConfig":
        split = int(d["split"])

        def _arr(key, default=None):
            v = d.get(key, default)
            if isinstance(v, list):
                assert len(v) == split, f"{key} must have {split} entries"
                return list(v)
            return [v] * split

        return cls(
            name=name,
            principal=float(d["principal"]),
            split=split,
            weights=_arr("weights"),
            odgap=_arr("odgap"),
            target=_arr("target"),
            loss_days=[int(x) for x in _arr("loss_days")],
            extrange=float(d["extrange"]),
            comp=float(d["comp"]),
            fee=float(d["fee"]),
            sec=float(d["sec"]),
            order_type=d["order_type"],
            odcount=int(d["odcount"]),
            step=d.get("step"),
            mocbuy=bool(d["mocbuy"]),
            seed_mode=d["seed_mode"],
        )


@dataclass
class PortfolioConfig:
    id: str
    name: str
    ticker: str
    preset: PresetConfig
    state_file: Path
    active: bool = True
    kakao_enabled: bool = True
    short_label: str = ""  # 카카오 메시지에 쓰는 짧은 이름, 예: "공격형"


def load_presets(path: Path) -> dict[str, PresetConfig]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {name: PresetConfig.from_dict(name, cfg) for name, cfg in raw.items()}


def load_portfolios(path: Path, presets: dict[str, PresetConfig], base_dir: Path) -> list[PortfolioConfig]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for item in raw:
        preset = presets[item["preset"]]
        out.append(
            PortfolioConfig(
                id=item["id"],
                name=item["name"],
                ticker=item.get("ticker", "SOXL"),
                preset=preset,
                state_file=base_dir / item["state_file"],
                active=item.get("active", True),
                kakao_enabled=item.get("kakao_enabled", True),
                short_label=item.get("short_label", item["name"]),
            )
        )
    return out
