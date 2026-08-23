from __future__ import annotations

import numpy as np
import pandas as pd

from core_models import MarketRegimeSnapshot
from risk_engine import build_risk_snapshot
from setup_engine import build_setups
from sr_engine import build_zones
from technical_engine import build_technical_snapshot


EPISODE_RESET_DAYS = 3
PRIMARY_HORIZON = 20
MAX_CALIBRATION_WINDOW = 420
MIN_TECH_HISTORY = 230
FORWARD_BUFFER = 60


def _episode_start_indices(mask: pd.Series, reset_days: int = EPISODE_RESET_DAYS) -> list[int]:
    """Group nearby qualifying days into one setup episode.

    A new episode starts only after the score has remained below the threshold
    for `reset_days` consecutive calibration rows.  This avoids counting one
    multi-day setup as many separate cases while still allowing a genuinely new
    setup to begin after the prior signal has cooled off.
    """
    values = mask.fillna(False).to_numpy(dtype=bool)
    starts: list[int] = []
    in_episode = False
    below_run = reset_days

    for idx, is_signal in enumerate(values):
        if is_signal:
            if not in_episode and below_run >= reset_days:
                starts.append(idx)
                in_episode = True
            below_run = 0
        else:
            if in_episode:
                below_run += 1
                if below_run >= reset_days:
                    in_episode = False
            else:
                below_run = min(reset_days, below_run + 1)
    return starts


def _spaced_indices(indexes: list[int], min_gap: int = PRIMARY_HORIZON) -> list[int]:
    """Keep episode anchors far enough apart to reduce overlapping outcome windows."""
    if not indexes:
        return []
    selected = [int(indexes[0])]
    last = selected[0]
    for idx in indexes[1:]:
        idx = int(idx)
        if idx - last >= min_gap:
            selected.append(idx)
            last = idx
    return selected


def run_setup_calibration(
    frame: pd.DataFrame,
    benchmark: pd.DataFrame | None = None,
    threshold: float = 75.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Price-only historical validation for Entry Engine V3.

    Fundamental data is intentionally excluded to avoid point-in-time leakage.
    Market is held neutral in this local calibration; production-grade market
    calibration can later inject historical regime snapshots.

    `threshold` means: only historical dates whose Pullback or Momentum Entry
    score is >= threshold are treated as qualifying setup days.

    Case counting used by the primary 20D validation:
    1) Consecutive/nearby qualifying days are grouped into one Setup Episode.
       A new episode requires at least 3 consecutive below-threshold rows.
    2) For the main 20D outcome statistics, episode starts are additionally
       spaced by at least 20 trading rows so the forward-return windows overlap
       less.  These rows are called 20D validation cases in the UI.
    """
    d = frame.dropna(subset=["Close"]).copy()
    if len(d) < 330:
        raise ValueError("Calibration requires at least ~330 trading days.")

    rows = []
    neutral_market = MarketRegimeSnapshot(
        "CAL", 50.0, "Neutral", {"Calibration": 50.0}, {"Regime": "Neutral"},
        1.0, "Calibration neutral market"
    )
    start = max(MIN_TECH_HISTORY, len(d) - MAX_CALIBRATION_WINDOW)
    end = len(d) - FORWARD_BUFFER - 1

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
            "fwd_5d": forward[5],
            "fwd_10d": forward[10],
            "fwd_20d": forward[20],
            "fwd_60d": forward[60],
            "mdd_20d": mdd20,
        })

    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, pd.DataFrame()

    summary_rows = []
    for name, col in (("Pullback", "pullback"), ("Momentum", "momentum")):
        mask = detail[col] >= threshold
        daily_sig = detail.loc[mask]
        episode_positions = _episode_start_indices(mask, reset_days=EPISODE_RESET_DAYS)
        validation_positions = _spaced_indices(episode_positions, min_gap=PRIMARY_HORIZON)
        sig = detail.iloc[validation_positions] if validation_positions else detail.iloc[0:0]

        # Keep only rows whose 20D outcome actually exists.
        valid_sig = sig.loc[sig["fwd_20d"].notna()].copy()
        validation_n = int(len(valid_sig))
        positive20 = int((valid_sig["fwd_20d"] > 0).sum()) if validation_n else 0

        if validation_n == 0:
            summary_rows.append({
                "Setup": name,
                "Signals": int(len(daily_sig)),
                "Episodes": int(len(episode_positions)),
                "Validation 20D": 0,
                "Positive 20D": 0,
                "Hit 20D": np.nan,
                "Median 20D": np.nan,
                "Avg 5D": np.nan,
                "Avg 10D": np.nan,
                "Avg 20D": np.nan,
                "Avg 60D": np.nan,
                "Avg MDD20": np.nan,
                "Episode Reset Days": EPISODE_RESET_DAYS,
                "Outcome Gap Days": PRIMARY_HORIZON,
            })
            continue

        summary_rows.append({
            "Setup": name,
            "Signals": int(len(daily_sig)),
            "Episodes": int(len(episode_positions)),
            "Validation 20D": validation_n,
            "Positive 20D": positive20,
            "Hit 20D": float(positive20 / validation_n * 100),
            "Median 20D": float(valid_sig["fwd_20d"].median()),
            "Avg 5D": float(valid_sig["fwd_5d"].mean()),
            "Avg 10D": float(valid_sig["fwd_10d"].mean()),
            "Avg 20D": float(valid_sig["fwd_20d"].mean()),
            "Avg 60D": float(valid_sig["fwd_60d"].mean()),
            "Avg MDD20": float(valid_sig["mdd_20d"].mean()),
            "Episode Reset Days": EPISODE_RESET_DAYS,
            "Outcome Gap Days": PRIMARY_HORIZON,
        })

    return detail, pd.DataFrame(summary_rows)
