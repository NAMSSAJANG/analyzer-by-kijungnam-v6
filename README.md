# Stock Analyzer V6.0

**Multi-Lens Setup & Decision System**

V6 rebuilds the V5-a0.1 stable base around a clearer decision architecture. The central change is that **stock quality, price leadership, entry setup, and risk are no longer collapsed into one score**.

## V6 decision architecture

1. **Company Quality V2**
   - Growth, profitability, balance sheet, cash flow, valuation
   - Missing fields are excluded instead of silently treated as bad data
   - Data coverage / confidence is shown separately
   - When a peer set is available, absolute scores are blended with peer-relative percentiles

2. **Opportunity Engine**
   - Company Quality 30%
   - Trend / Leadership 25%
   - Relative Strength 15%
   - Momentum / Demand 15%
   - Market Regime 15%
   - Risk is intentionally excluded from Opportunity and displayed separately

3. **Entry Engine V3**
   - **Pullback Entry**: asks whether a strong stock has reset into a favorable support/EMA zone
   - **Momentum Entry**: asks whether trend, breakout, volume, and relative strength justify following strength
   - A stock can therefore be `NOT IN ZONE` for Pullback while still being `CONFIRMED` or `EXTENDED` for Momentum

4. **Risk Engine**
   - Extension, volatility, earnings/event risk, liquidity, market risk
   - Produces a separate overall risk state and a starter-size multiplier
   - High volatility no longer automatically makes a strong stock a low-quality stock

5. **US / KR Market Regime**
   - US: broad market, growth/tech, sector, volatility, credit, dollar/liquidity
   - KR: KOSPI/KOSDAQ, USD/KRW, global risk, US tech lead, global sector driver
   - Korean stocks therefore use both local market context and relevant global drivers

6. **Support / Resistance Zone Engine**
   - Swing highs/lows, EMA20/50/200, prior breakouts, volume nodes, 52-week extremes
   - Optional Put/Call Walls are included when U.S. options data is available
   - Nearby levels are clustered into confluence **zones**, not treated as exact single-price lines

7. **Consensus V2**
   - Company / Trend / Setup / Market / Options
   - `Signal Agreement` and `Data Confidence` are separated

8. **V6 Scanner**
   - Opportunity Leaders
   - Momentum Setups
   - Pullback Setups
   - Scanner Opportunity is a price-based pre-screen for speed; full individual analysis adds Company Quality

9. **History Database**
   - SQLite by default via `.data/stock_analyzer_v6.sqlite`
   - Stores Opportunity, Company, Trend, Momentum, Relative Strength, Pullback, Momentum Entry, Market, Risk, Preferred Setup
   - JSON export/import is included
   - On Streamlit Community Cloud, local disk may still reset on redeploy; set `ANALYZER_DB_FILE` to a durable mounted path or replace the isolated adapter with an external DB later

10. **Calibration**
   - Reconstructs historical Pullback / Momentum signals and evaluates 5D / 10D / 20D / 60D forward returns and 20D drawdown
   - Fundamental data is deliberately excluded from V6.0 historical calibration to avoid point-in-time look-ahead bias
   - Market Regime is neutral in the local calibration engine; a future version can inject historical regime snapshots

## Run locally

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

## Optional history path

```bash
# Windows PowerShell example
$env:ANALYZER_DB_FILE="C:\\StockAnalyzerData\\v6.sqlite"
streamlit run app.py
```

## Main files

- `app.py` — Streamlit UI and orchestration
- `company_engine.py` — Company Quality V2 and peer-relative scoring
- `technical_engine.py` — Trend, momentum, demand, relative strength metrics
- `market_regime.py` — US/KR market context
- `opportunity_engine.py` — Stock Opportunity score
- `sr_engine.py` — confluence support/resistance zones
- `setup_engine.py` — Pullback / Momentum Entry Engine V3
- `risk_engine.py` — separate risk state
- `consensus_engine.py` — independent-lens consensus
- `scanner_engine.py` — Opportunity/Momentum/Pullback scanner
- `history_store.py` — SQLite score trajectory
- `calibration_engine.py` — price-only historical setup validation
- `options_analyzer.py` — V5 options module retained as a secondary confirmation lens
- `korean_stock_search.py`, `sitecustomize.py` — resilient Korean ticker search

## Important limitations

- Yahoo Finance and free public sources can be delayed, incomplete, or temporarily unavailable.
- Sector peer lists are pragmatic candidates, not a perfect industry classification database.
- Korean individual-stock options are not provided by the current free data source.
- V6 Calibration is not a full point-in-time fundamental backtest.
- Support/resistance zones are model-derived references, not guaranteed reaction prices.
- The application is for research and educational use and is not investment advice.
