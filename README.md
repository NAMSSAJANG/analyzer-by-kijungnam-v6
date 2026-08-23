# Stock Analyzer V6.0.1

**Multi-Lens Setup & Decision System · Explainability & UX Restoration**

V6.0.1 keeps the V6 decision architecture while restoring the parts of V5 that made the app easier to read and interpret: AI briefing cards, detailed quantitative analysis, CAN SLIM, auxiliary quant indicators, Market Pulse, 10-trading-day score trajectories, scenario cards, and richer calibration explanations.

## Core V6 architecture

- **Opportunity Engine** — Company Quality 30%, Trend / Leadership 25%, Relative Strength 15%, Momentum / Demand 15%, Market Regime 15%.
- **Entry Engine V3** — Pullback Entry and Momentum Entry are evaluated separately.
- **Risk Engine** — Extension, Volatility, Earnings, Liquidity, and Market Risk are separated from Opportunity.
- **US / KR Market Regime** — U.S. and Korean stocks use different market-context structures; Korean stocks also consider global drivers.
- **Support / Resistance Zone Engine** — uses swing structure, EMAs, price clusters and available option walls.
- **Consensus V2** — Company / Trend / Setup / Market / Options, with Signal Agreement and Data Confidence shown separately.
- **SQLite History** — stores Opportunity, Trend, Momentum, Relative Strength, Pullback, Momentum Entry, Market, Risk and Preferred Setup.
- **Calibration Engine** — price-only historical validation for Pullback / Momentum thresholds to avoid point-in-time fundamental leakage.

## V6.0.1 UX / explainability restoration

- Scanner removed from the individual-stock menu and moved to a separate market-wide Scanner section.
- Individual analysis menu now includes **Overall Analysis / Quant Analysis / Options / Market / Calibration / History**.
- Pullback and Momentum concepts are explained directly in the Entry section.
- Internal English states are paired with user-facing Korean labels such as **진입 유리 / 진입 검토 / 관망 / 과열 주의 / 진입 보류**.
- Entry, Risk and factor cards use more consistent spacing and minimum heights.
- **AI overall / company / quant / entry / market-risk briefings** are restored on top of the V6 engine outputs.
- **10-trading-day reconstructed charts** are restored for Opportunity / Entry and Quant / Trend / Momentum.
- **Detailed Quant tab** restored: trend-volume chart, CAN SLIM, CAN SLIM reading guide, auxiliary quant indicators, technical indicators, financial indicators, peer comparison.
- **Market Pulse** restored: S&P 500, Nasdaq 100, SOX, VIX, Gold, Silver, WTI, Copper, USD/KRW, DXY, Bitcoin and Ethereum, with short-term up/down changes.
- Calibration now explains what the threshold changes, adds **Independent Signals, Median 20D, validation period, table-reading guide and summary interpretation**.
- `.streamlit/config.toml` and `.gitignore` are included for deployment convenience.

## Important interpretation rules

### Opportunity is not Entry
A high Opportunity score means the stock is attractive across company quality, leadership, relative strength, momentum/demand and market context. It does **not** mean the current price is automatically a good entry.

### Pullback Entry
Evaluates whether a strong stock has pulled back toward a constructive support / EMA zone. Low-volume pullbacks can be constructive.

### Momentum Entry
Evaluates whether breakout strength, relative strength, trend and volume support following an active advance. A high RSI is not automatically treated as a negative when the broader momentum structure is strong.

### Risk is separate
Volatility and extension are primarily used for position-size / caution interpretation rather than automatically making a strong stock a weak stock.

## 10-day reconstructed charts

The immediate 10-trading-day charts reconstruct price/volume/technical conditions for prior trading days while holding the **current Company Quality and current Market Regime** fixed. They are an explainability aid, not a point-in-time fundamental backtest. Actual daily saved records are stored separately in History.

## Calibration caveat

Calibration intentionally excludes historical fundamentals because Yahoo's current company information cannot reliably reproduce point-in-time historical fundamentals. Market Regime is held neutral in V6.0.1 local calibration. Therefore the calibration is specifically for **Entry Engine V3 price/setup behavior**, not a complete historical V6 portfolio backtest.

## Run locally

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## GitHub / Streamlit structure

```text
stock-analyzer-v6/
├─ .streamlit/
│  └─ config.toml
├─ .gitignore
├─ app.py
├─ calibration_engine.py
├─ company_engine.py
├─ consensus_engine.py
├─ core_models.py
├─ history_store.py
├─ korean_stock_search.py
├─ market_regime.py
├─ opportunity_engine.py
├─ options_analyzer.py
├─ quant_engine.py
├─ risk_engine.py
├─ scanner_engine.py
├─ scoring_utils.py
├─ setup_engine.py
├─ sitecustomize.py
├─ smoke_test.py
├─ sr_engine.py
├─ technical_engine.py
├─ requirements.txt
├─ CHANGELOG.md
└─ README.md
```

## Offline validation

```bash
python smoke_test.py
```

The offline smoke test checks Momentum-vs-Pullback separation, Company missing-data handling, Opportunity, Quant / CAN SLIM, Calibration columns, and SQLite History without network calls.

## Disclaimer

This project is for informational and educational purposes only. Public market data may be delayed, missing, revised, affected by corporate actions, or inconsistent between markets. Scores and calibration statistics are not investment advice or probabilities of future returns.
