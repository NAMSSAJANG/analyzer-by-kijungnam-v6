from __future__ import annotations

import numpy as np
import pandas as pd

from core_models import MarketRegimeSnapshot
from risk_engine import build_risk_snapshot
from setup_engine import build_setups
from sr_engine import build_zones
from technical_engine import build_technical_snapshot


def run_setup_calibration(frame: pd.DataFrame, benchmark: pd.DataFrame | None = None, threshold: float = 75.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Price-only historical validation for Entry Engine V3.

    Fundamental data is intentionally excluded to avoid point-in-time leakage.
    Market is held neutral in this local calibration; production-grade market
    calibration can later inject historical regime snapshots.
    """
    d = frame.dropna(subset=["Close"]).copy()
    if len(d) < 330:
        raise ValueError("Calibration requires at least ~330 trading days.")
    rows = []
    neutral_market = MarketRegimeSnapshot("CAL", 50.0, "Neutral", {"Calibration": 50.0}, {"Regime": "Neutral"}, 1.0, "Calibration neutral market")
    start = max(230, len(d) - 420)
    end = len(d) - 61
    for i in range(start, end):
        hist = d.iloc[: i + 1]
        bench_hist = None
        if benchmark is not None and not benchmark.empty:
            bench_hist = benchmark.loc[benchmark.index <= hist.index[-1]]
        try:
            tech = build_technical_snapshot(hist, bench_hist)
            risk = build_risk_snapshot(tech, neutral_market, None)
            zones = build_zones(hist, tech)
            now = float(hist["Close"].iloc[-1])
            setups = build_setups(now, tech, neutral_market, zones, risk)
        except Exception:
            continue
        forward = {}
        for horizon in (5, 10, 20, 60):
            if i + horizon < len(d):
                forward[horizon] = (float(d["Close"].iloc[i + horizon]) / now - 1) * 100
            else:
                forward[horizon] = np.nan
        future20 = d["Close"].iloc[i + 1 : i + 21].astype(float)
        mdd20 = ((future20 / now) - 1).min() * 100 if not future20.empty else np.nan
        rows.append({
            "date": pd.Timestamp(hist.index[-1]).date().isoformat(),
            "pullback": setups.pullback.score,
            "momentum": setups.momentum.score,
            "pullback_status": setups.pullback.status,
            "momentum_status": setups.momentum.status,
            "fwd_5d": forward[5], "fwd_10d": forward[10], "fwd_20d": forward[20], "fwd_60d": forward[60],
            "mdd_20d": mdd20,
        })
    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, pd.DataFrame()
    summary_rows = []
    for name, col in (("Pullback", "pullback"), ("Momentum", "momentum")):
        sig = detail[detail[col] >= threshold]
        if sig.empty:
            summary_rows.append({"Setup": name, "Signals": 0, "Hit 20D": np.nan, "Avg 5D": np.nan, "Avg 10D": np.nan, "Avg 20D": np.nan, "Avg 60D": np.nan, "Avg MDD20": np.nan})
            continue
        summary_rows.append({
            "Setup": name,
            "Signals": int(len(sig)),
            "Hit 20D": float((sig["fwd_20d"] > 0).mean() * 100),
            "Avg 5D": float(sig["fwd_5d"].mean()),
            "Avg 10D": float(sig["fwd_10d"].mean()),
            "Avg 20D": float(sig["fwd_20d"].mean()),
            "Avg 60D": float(sig["fwd_60d"].mean()),
            "Avg MDD20": float(sig["mdd_20d"].mean()),
        })
    return detail, pd.DataFrame(summary_rows)
