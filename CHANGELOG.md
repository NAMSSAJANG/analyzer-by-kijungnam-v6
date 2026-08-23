# Changelog

## V6.0.5
- Polished summary card labels with Korean-first / English-on-next-line formatting for aligned value rows.
- Increased Consensus lens card height so long notes (especially Entry Setup) remain fully visible.
- Refined 10-day chart label offsets so numeric tags stay closer to their own series.

# V6.0.4

- Renamed the top stock overview to **종합 판단 요약 (Decision Summary)** and standardized its five summary cards to the same height.
- Reordered the overall-analysis flow to Decision Summary → AI Briefing → Entry → Risk → Analysis Consensus → 10D trajectory → detailed Company/Market analysis.
- Added a dedicated **Analysis Consensus · 분석 관점 일치도** section with Company, Quant/Trend, Entry Setup, Market Regime, and Options lenses.
- Separated **Signal Agreement** from **Data Confidence** and added a plain-language consensus interpretation.
- Rewrote Company Quality factor descriptions so each card explains what Growth, Profitability, Balance Sheet, Cash Flow, and Valuation actually mean.
- Kept Opportunity / Entry / Risk scoring engines unchanged; this release focuses on information hierarchy, explainability, and layout consistency.

# V6.0.3

- Polished 10-trading-day charts with vertical trading-day guides, non-overlapping colored score labels, and per-series 5D change summaries.
- Added Korean + English naming for Opportunity, Pullback Entry, Momentum Entry, Company Quality factors, and key Quant factors.
- Added clearer Entry status color hierarchy and detailed status explanations.
- Added Risk Engine status colors and a clearer overall risk summary.
- Normalized auxiliary Quant and Company card heights.
- Replaced developer-oriented missing-data wording with user-friendly explanations.
- Expanded AI briefings for first-time users without changing V6 scoring logic.
- Kept the V6 engine logic unchanged; this release focuses on visual clarity and explainability.

# V6.0.2

- 스캐너를 종목 검색 위로 이동하고 주요 스캐너 탭을 한글화했습니다.
- 종목 매력도 / 모멘텀 진입 / 눌림목 진입 의미 설명을 추가했습니다.
- 상단 V6 안내 경고 배너를 제거했습니다.
- 카드 높이와 섹션 간격을 정리했습니다.
- Market Regime을 사용자 화면에서 '시장 국면'과 한글 상태명으로 표시합니다.
- 최근 10영업일 차트를 실제 거래일 기준 카테고리 축으로 변경하고 모든 마커와 색상 일치 숫자 라벨을 표시합니다.
- 퀀트 분석에 AI 퀀트 브리핑과 세부 점수를 추가했습니다.
- 시장환경을 V5 스타일의 시장 건강도 + 10D + Market Pulse + 금리/신용 패널 구조로 보강했습니다.
- Market Pulse 12와 금리/신용 지표에 해석 문구를 추가했습니다.

# Changelog

## V6.0.1 — Explainability & UX Restoration

- Preserved V6 Opportunity / Setup / Risk / Market / Consensus architecture.
- Removed Scanner from individual-stock radio navigation; Scanner is now an independent section.
- Added separate Quant Analysis menu.
- Restored AI Overall, Company, Quant, Entry and Market/Risk briefing cards.
- Added Korean-facing Entry state labels while preserving internal English states.
- Added direct explanations of Pullback Entry and Momentum Entry.
- Standardized Entry / Risk / factor card heights and increased section spacing.
- Restored 10-trading-day reconstructed score charts.
- Added Quant Composite explainability layer.
- Restored CAN SLIM analysis and CAN SLIM reading guide.
- Restored auxiliary quant indicators.
- Restored detailed technical and financial indicator rows and peer comparison.
- Restored V5-style Market Pulse with equities, volatility, commodities, FX and crypto.
- Added rate/credit helper panel.
- Expanded Calibration UX: threshold explanation, independent signals, median 20D, validation period, result summary, table guide and small-sample warning.
- Added `.streamlit/config.toml` and `.gitignore`.
- Expanded offline smoke tests to include Quant / CAN SLIM and Calibration outputs.

## V6.0

- Introduced Opportunity Engine, Entry Engine V3, Risk Engine, US/KR Market Regime, S/R Zones, Consensus V2, market scanners, SQLite history and price-only calibration foundation.
