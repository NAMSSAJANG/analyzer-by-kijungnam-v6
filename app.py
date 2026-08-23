from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

from calibration_engine import run_setup_calibration
from company_engine import build_company_snapshot
from consensus_engine import build_consensus_v2
from history_store import SQLiteHistoryStore
from korean_stock_search import contains_hangul, load_krx_listing, search_krx_listing
from market_regime import build_market_regime, market_for_symbol
from opportunity_engine import build_opportunity
from risk_engine import build_risk_snapshot
from scanner_engine import scan_market, top_views
from setup_engine import build_setups
from sr_engine import build_zones
from technical_engine import build_technical_snapshot

st.set_page_config(page_title="Stock Analyzer V6", page_icon="📈", layout="wide")

DB_FILE = Path(os.getenv("ANALYZER_DB_FILE", ".data/stock_analyzer_v6.sqlite"))
HISTORY = SQLiteHistoryStore(DB_FILE)

st.markdown("""
<style>
.stApp{background:linear-gradient(180deg,#07111f 0%,#081525 100%)}
.block-container{padding-top:1.1rem;max-width:1480px}
.v6-card{border:1px solid #29415e;border-radius:16px;padding:16px;background:#0d1b2d;height:100%}
.v6-kicker{font-size:.72rem;font-weight:850;letter-spacing:.14em;color:#38bdf8;margin-bottom:8px}
.v6-value{font-size:2rem;font-weight:900;color:#f8fafc;line-height:1.15}.v6-sub{color:#94a3b8;line-height:1.6}
.v6-pill{display:inline-block;border-radius:99px;padding:4px 9px;background:#102c46;color:#7dd3fc;font-weight:750;margin:3px 4px 3px 0}
.decision{border:1px solid #315272;border-radius:18px;padding:20px;background:linear-gradient(135deg,#0d1b2d,#10243a);margin:14px 0}
.decision h2{margin:.2rem 0 .7rem}.decision p{color:#dbeafe;line-height:1.75;margin:.35rem 0}
.status-green{color:#34d399}.status-yellow{color:#fbbf24}.status-orange{color:#fb923c}.status-red{color:#fb7185}
.zone{border-left:4px solid #38bdf8;background:#0d1b2d;border-radius:10px;padding:12px;margin:6px 0}.zone.r{border-left-color:#fb7185}
[data-testid="stMetricValue"]{font-size:clamp(1.4rem,2.5vw,2.1rem)}
[data-testid="stDataFrame"]{border:1px solid #29415e;border-radius:10px;overflow:hidden}
@media(max-width:700px){.block-container{padding-left:.8rem;padding-right:.8rem}.v6-card{height:auto}}
</style>
""", unsafe_allow_html=True)


def money(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:,.2f}" if abs(value) < 10000 else f"{value:,.0f}"


def score_color(value: float) -> str:
    return "#22c55e" if value >= 80 else "#34d399" if value >= 65 else "#fbbf24" if value >= 50 else "#fb923c" if value >= 35 else "#fb7185"


def score_card(label: str, value: float | None, subtitle: str = ""):
    if value is None:
        shown, color = "N/A", "#94a3b8"
    else:
        shown, color = f"{value:.1f}", score_color(value)
    st.markdown(f"<div class='v6-card'><div class='v6-kicker'>{label}</div><div class='v6-value' style='color:{color}'>{shown}</div><div class='v6-sub'>{subtitle}</div></div>", unsafe_allow_html=True)


@st.cache_data(ttl=900, show_spinner=False)
def prices(symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    d = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False, threads=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return d.dropna(how="all")


@st.cache_data(ttl=3600, show_spinner=False)
def info(symbol: str) -> dict:
    try:
        return yf.Ticker(symbol).get_info() or {}
    except Exception:
        return {}


@st.cache_data(ttl=1800, show_spinner=False)
def news(symbol: str) -> list[tuple[str, str, str]]:
    try:
        rows = yf.Ticker(symbol).news[:8]
        out = []
        for x in rows:
            c = x.get("content", x)
            title = c.get("title") or x.get("title")
            if title:
                out.append((title, c.get("summary", ""), (c.get("canonicalUrl") or {}).get("url") or x.get("link", "")))
        return out
    except Exception:
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def krx_listing():
    return load_krx_listing()


@st.cache_data(ttl=300, show_spinner=False)
def search_symbol(query: str):
    q = query.strip()
    if not q:
        return []
    merged = []
    is_hangul = contains_hangul(q)
    if is_hangul or re.fullmatch(r"\d{1,6}", q):
        try:
            merged.extend(search_krx_listing(q, krx_listing()))
        except Exception:
            pass
    try:
        data = requests.get("https://query2.finance.yahoo.com/v1/finance/search", params={"q": q, "quotesCount": 10, "newsCount": 0}, headers={"User-Agent": "Mozilla/5.0"}, timeout=8).json()
        merged.extend({"symbol": x.get("symbol"), "name": x.get("longname") or x.get("shortname") or x.get("symbol"), "exchange": x.get("exchDisp", ""), "type": x.get("quoteType", "")} for x in data.get("quotes", []) if x.get("symbol"))
    except Exception:
        pass
    if not merged and not is_hangul:
        merged = [{"symbol": q.upper(), "name": q.upper(), "exchange": "직접 입력", "type": ""}]
    unique, seen = [], set()
    for row in merged:
        if row["symbol"] not in seen:
            seen.add(row["symbol"]); unique.append(row)
    return unique[:10]


US_PEERS = {
    "technology": ["MSFT", "AAPL", "NVDA", "AVGO", "ORCL", "AMD", "QCOM"],
    "financial services": ["JPM", "BAC", "GS", "MS", "WFC"],
    "healthcare": ["LLY", "JNJ", "ABBV", "MRK", "UNH"],
    "consumer cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
    "communication services": ["META", "GOOGL", "NFLX", "TMUS", "DIS"],
    "energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
}
KR_PEERS = {
    "technology": ["005930.KS", "000660.KS", "066570.KS", "035420.KS"],
    "financial services": ["105560.KS", "055550.KS", "086790.KS", "316140.KS"],
    "consumer cyclical": ["005380.KS", "000270.KS", "012330.KS"],
    "healthcare": ["207940.KS", "068270.KS", "326030.KS"],
    "basic materials": ["005490.KS", "051910.KS", "011170.KS"],
}


@st.cache_data(ttl=21600, show_spinner=False)
def peer_infos(symbol: str, sector: str, region: str):
    pool = (KR_PEERS if region == "KR" else US_PEERS).get((sector or "").lower(), [])
    symbols = [x for x in pool if x != symbol][:5]
    out = []
    for ticker in symbols:
        try:
            payload = yf.Ticker(ticker).get_info() or {}
            if payload:
                out.append(payload)
        except Exception:
            continue
    return out, symbols


@st.cache_data(ttl=3600, show_spinner=False)
def earnings_days(symbol: str) -> int | None:
    try:
        cal = yf.Ticker(symbol).calendar
        if isinstance(cal, dict):
            raw = cal.get("Earnings Date") or cal.get("EarningsDate")
            if isinstance(raw, (list, tuple)) and raw:
                raw = raw[0]
            if raw is not None:
                return (pd.Timestamp(raw).tz_localize(None).normalize() - pd.Timestamp.now().normalize()).days
    except Exception:
        pass
    return None


def benchmark_symbol(symbol: str) -> str:
    return "^KS11" if market_for_symbol(symbol) == "KR" else "^GSPC"


def build_full_analysis(symbol: str):
    frame = prices(symbol, "2y")
    if len(frame) < 210:
        raise ValueError("최소 210거래일의 가격 데이터가 필요합니다.")
    inf = info(symbol)
    region = market_for_symbol(symbol)
    sector = inf.get("sector", "")
    benchmark = prices(benchmark_symbol(symbol), "2y")
    tech = build_technical_snapshot(frame, benchmark)
    market = build_market_regime(symbol, sector, prices)
    peers, peer_symbols = peer_infos(symbol, sector, region)
    company = build_company_snapshot(inf, peers)

    option_view = None
    option_label = "N/A"
    try:
        from options_analyzer import get_option_snapshot, option_bias
        option_view, _, _, _ = get_option_snapshot(symbol, float(frame.Close.iloc[-1]))
        if option_view:
            option_label = option_bias(option_view)
    except Exception:
        pass

    zones = build_zones(frame, tech,
                        option_put_wall=option_view.put_wall if option_view else None,
                        option_call_wall=option_view.call_wall if option_view else None)
    risk = build_risk_snapshot(tech, market, earnings_days(symbol))
    now = float(frame.Close.iloc[-1])
    setups = build_setups(now, tech, market, zones, risk)
    opportunity = build_opportunity(company, tech, market)
    consensus = build_consensus_v2(company, tech, setups, market, option_label, option_view.data_quality if option_view else None)
    return dict(frame=frame, info=inf, region=region, sector=sector, benchmark=benchmark, tech=tech, market=market,
                company=company, zones=zones, risk=risk, setups=setups, opportunity=opportunity,
                consensus=consensus, option=option_view, option_label=option_label, peer_symbols=peer_symbols, now=now)


def status_class(text: str) -> str:
    t = text.upper()
    if any(x in t for x in ("READY", "CONFIRMED", "PREFERRED", "RISK-ON", "STRONG")):
        return "status-green"
    if any(x in t for x in ("DEVELOPING", "WATCH", "MIXED", "NEUTRAL", "MODERATE")):
        return "status-yellow"
    if any(x in t for x in ("EXTENDED", "WARNING", "ELEVATED")):
        return "status-orange"
    return "status-red"


def render_analysis(a: dict, symbol: str):
    inf, tech, market, company, zones, risk, setups, opp, cons = a["info"], a["tech"], a["market"], a["company"], a["zones"], a["risk"], a["setups"], a["opportunity"], a["consensus"]
    name = inf.get("longName") or inf.get("shortName") or symbol
    st.header(f"{name} · {symbol}")
    st.caption(f"V6 분석 · 데이터 기준 {pd.Timestamp(a['frame'].index[-1]).date()} · {a['region']} Market · Sector {a['sector'] or 'N/A'}")

    preferred_cls = status_class(setups.preferred)
    risk_cls = status_class(risk.level)
    st.markdown(f"""<div class='decision'><div class='v6-kicker'>V6 MULTI-LENS DECISION</div>
    <h2>{opp.score:.1f} · {opp.grade}</h2>
    <p><b>Preferred Setup</b> · <span class='{preferred_cls}'>{setups.preferred}</span> &nbsp; | &nbsp; <b>Risk</b> · <span class='{risk_cls}'>{risk.level}</span> &nbsp; | &nbsp; <b>Market</b> · {market.label}</p>
    <p>{opp.interpretation} {setups.summary}</p>
    <p><b>Consensus</b> · {cons.headline} · Signal Agreement {cons.signal_agreement}% · Data Confidence {cons.data_confidence}%<br>{cons.interpretation}</p></div>""", unsafe_allow_html=True)

    cols = st.columns(5)
    items = [
        ("OPPORTUNITY", opp.score, "종목 매력도 · Entry와 Risk는 별도"),
        ("COMPANY QUALITY", company.score, f"Coverage {company.coverage*100:.0f}% · {company.confidence}"),
        ("TREND / LEADERSHIP", tech.trend, f"12M {tech.ret_12m:+.1f}%"),
        ("RELATIVE STRENGTH", tech.relative_strength, "시장 벤치마크 대비"),
        ("MOMENTUM / DEMAND", .60*tech.momentum+.40*tech.demand, f"RSI {tech.rsi:.1f} · Vol {tech.volume_ratio:.2f}x"),
    ]
    for col, item in zip(cols, items):
        with col: score_card(*item)

    st.subheader("Entry Engine V3")
    c1, c2 = st.columns(2)
    for col, setup, icon in ((c1, setups.pullback, "🎯"), (c2, setups.momentum, "🚀")):
        with col:
            cls = status_class(setup.status)
            st.markdown(f"<div class='v6-card'><div class='v6-kicker'>{icon} {setup.name.upper()} ENTRY</div><div class='v6-value'>{setup.score:.1f}</div><div class='{cls}'><b>{setup.status}</b></div></div>", unsafe_allow_html=True)
            rows = [{"요소": k, "점수": round(v,1), "해석": setup.details[k]} for k,v in setup.factors.items()]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                         column_config={"점수": st.column_config.ProgressColumn("점수", min_value=0, max_value=100, format="%.1f")})
            if setup.zone:
                st.caption(f"참고 Zone {money(setup.zone[0])} ~ {money(setup.zone[1])}")
            if setup.trigger:
                st.caption(f"Trigger {money(setup.trigger)}")
            if setup.invalidation:
                st.caption(f"Invalidation {money(setup.invalidation)}")

    st.subheader("Risk Engine")
    rcols = st.columns(5)
    for col, (label, value, detail) in zip(rcols, [
        ("Extension", risk.extension, risk.details["Extension"]), ("Volatility", risk.volatility, risk.details["Volatility"]),
        ("Earnings", risk.earnings, risk.details["Earnings"]), ("Liquidity", risk.liquidity, risk.details["Liquidity"]),
        ("Market Risk", risk.market, risk.details["Market"]),
    ]):
        with col:
            st.markdown(f"<div class='v6-card'><div class='v6-kicker'>{label}</div><div style='font-size:1.2rem;font-weight:850'>{value}</div><div class='v6-sub'>{detail}</div></div>", unsafe_allow_html=True)
    st.caption(f"Overall Risk {risk.score:.1f} · {risk.level} · Starter-size multiplier {risk.position_size_multiplier:.2f}x (비중 결정의 참고용 위험 조정치)")

    st.subheader("Company Quality V2")
    if company.notes:
        st.info(" ".join(company.notes))
    fcols = st.columns(5)
    for col, (label, value) in zip(fcols, company.factors.items()):
        with col: score_card(label.upper(), value, "결측 항목 제외 · 상대평가 가능 시 혼합")
    if company.relative:
        rel = pd.DataFrame([{"지표": k, "업종 상대점수": v} for k,v in company.relative.items() if v is not None])
        if not rel.empty:
            with st.expander("업종 상대평가 상세"):
                st.dataframe(rel, hide_index=True, use_container_width=True,
                             column_config={"업종 상대점수": st.column_config.ProgressColumn("업종 상대점수", min_value=0, max_value=100, format="%.1f")})
                st.caption("자동 동종업종 후보: " + ", ".join(a["peer_symbols"]) if a["peer_symbols"] else "자동 동종업종 후보가 충분하지 않습니다.")

    st.subheader("Market Regime")
    score_card(f"{market.market} MARKET", market.score, f"{market.label} · Data quality {market.data_quality*100:.0f}%")
    market_df = pd.DataFrame([{"구성요소": k, "점수": v} for k,v in market.components.items()])
    st.dataframe(market_df, hide_index=True, use_container_width=True,
                 column_config={"점수": st.column_config.ProgressColumn("점수", min_value=0, max_value=100, format="%.1f")})
    st.caption(market.interpretation)

    st.subheader("Support / Resistance Zones")
    left, right = st.columns(2)
    with left:
        st.markdown("**Support**")
        if not zones.supports: st.info("신뢰 가능한 Support Zone이 부족합니다.")
        for z in zones.supports:
            st.markdown(f"<div class='zone'><b>{money(z.low)} ~ {money(z.high)}</b> · {z.label} ({z.strength:.0f})<br><span class='v6-sub'>{' · '.join(z.sources)}</span></div>", unsafe_allow_html=True)
    with right:
        st.markdown("**Resistance**")
        if not zones.resistances: st.info("현재가 위의 명확한 Resistance Zone이 부족합니다.")
        for z in zones.resistances:
            st.markdown(f"<div class='zone r'><b>{money(z.low)} ~ {money(z.high)}</b> · {z.label} ({z.strength:.0f})<br><span class='v6-sub'>{' · '.join(z.sources)}</span></div>", unsafe_allow_html=True)

    st.subheader("Price / Trend Chart")
    d = a["frame"].tail(252)
    fig = go.Figure(go.Candlestick(x=d.index, open=d.Open, high=d.High, low=d.Low, close=d.Close, name="Price"))
    for value, name_, color in ((tech.ema20,"EMA20","#38bdf8"),(tech.ema50,"EMA50","#f59e0b"),(tech.ema200,"EMA200","#a855f7")):
        fig.add_hline(y=value, line_dash="dot", line_color=color, annotation_text=name_)
    for z in zones.supports[:3]:
        fig.add_hrect(y0=z.low, y1=z.high, fillcolor="rgba(56,189,248,.08)", line_width=0)
    for z in zones.resistances[:3]:
        fig.add_hrect(y0=z.low, y1=z.high, fillcolor="rgba(251,113,133,.08)", line_width=0)
    fig.update_layout(height=560, xaxis_rangeslider_visible=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0a1728", font=dict(color="#cbd5e1"), xaxis=dict(gridcolor="#20344d"), yaxis=dict(gridcolor="#20344d"))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Multi-Lens Consensus V2")
    cons_df = pd.DataFrame([{"Lens": k, "판단": v} for k,v in cons.lenses.items()])
    st.dataframe(cons_df, hide_index=True, use_container_width=True)
    st.caption("Signal Agreement는 렌즈 방향의 일치도, Data Confidence는 원자료 충실도입니다. 상승 확률이 아닙니다.")

    st.subheader("Score Trajectory")
    data_date = pd.Timestamp(a["frame"].index[-1]).date()
    HISTORY.record(symbol, {
        "opportunity": opp.score, "company": company.score, "trend": tech.trend, "momentum": tech.momentum,
        "relative_strength": tech.relative_strength, "pullback": setups.pullback.score, "momentum_entry": setups.momentum.score,
        "market": market.score, "risk": risk.score, "preferred_setup": setups.preferred,
    }, data_date, {"version": "6.0"})
    history = HISTORY.rows(symbol, 40)
    hf = pd.DataFrame(history)
    if len(hf) > 1:
        cols = [x for x in ("opportunity","trend","momentum","relative_strength","pullback","momentum_entry","market","risk") if x in hf]
        st.line_chart(hf.set_index("date")[cols])
        p = HISTORY.recent(symbol, "pullback"); m = HISTORY.recent(symbol, "momentum_entry")
        st.caption(f"5D Pullback: {p.label} ({'N/A' if p.change is None else f'{p.change:+.1f}'}) · Momentum Entry: {m.label} ({'N/A' if m.change is None else f'{m.change:+.1f}'})")
    else:
        st.info("V6 첫 저장입니다. 다음 영업일부터 Setup 변화가 누적됩니다.")

    with st.expander("최근 뉴스"):
        rows = news(symbol)
        if not rows: st.info("현재 불러온 뉴스가 없습니다.")
        for title, summary, url in rows:
            st.markdown(f"**[{title}]({url})**" if url else f"**{title}**")
            st.caption((summary or "제목 기반 참고 뉴스")[:260])


st.title("Stock Analyzer by Kijungnam")
st.caption("V6.0 · MULTI-LENS SETUP & DECISION SYSTEM")
st.warning("V6는 종목 품질·추세·진입 Setup·Risk를 분리해 해석합니다. 결과는 정량 참고자료이며 투자 권유가 아닙니다.")

st.subheader("종목 검색")
query = st.text_input("티커 또는 회사명", placeholder="예: NVDA, Micron, 삼성전자, 005930")
results = search_symbol(query) if query else []
if results:
    labels = [f"{x['name']} · {x['symbol']} · {x.get('exchange','')}" for x in results]
    choice = st.selectbox("검색 후보", labels)
    selected_symbol = results[labels.index(choice)]["symbol"]
    if st.button("분석 시작", type="primary", use_container_width=True):
        st.session_state["symbol"] = selected_symbol
symbol = st.session_state.get("symbol", "")

mode = st.radio("V6 메뉴", ["🔥 Scanner", "📊 종목분석", "🧩 옵션", "🌎 시장환경", "🧪 Calibration", "💾 History"], horizontal=True, label_visibility="collapsed")
st.divider()

analysis = None
if symbol and mode in ("📊 종목분석", "🧩 옵션", "🧪 Calibration"):
    try:
        with st.spinner(f"{symbol} · V6 엔진을 계산하는 중입니다..."):
            analysis = build_full_analysis(symbol)
    except Exception as exc:
        st.error(f"분석을 계산하지 못했습니다: {exc}")

if mode == "📊 종목분석":
    if not symbol:
        st.info("먼저 종목을 검색해 주세요.")
    elif analysis:
        render_analysis(analysis, symbol)

elif mode == "🧩 옵션":
    if not symbol:
        st.info("먼저 종목을 검색해 주세요.")
    else:
        try:
            from options_analyzer import render_options
            base = analysis or build_full_analysis(symbol)
            support = base["zones"].supports[0].center if base["zones"].supports else None
            resistance = base["zones"].resistances[0].center if base["zones"].resistances else None
            render_options(symbol, base["now"], money, support, resistance)
        except Exception as exc:
            st.warning(f"옵션분석을 표시할 수 없습니다: {exc}")

elif mode == "🌎 시장환경":
    st.subheader("US / KR Market Regime")
    left, right = st.columns(2)
    with left:
        us = build_market_regime("SPY", "technology", prices)
        score_card("US MARKET REGIME", us.score, us.label)
        st.dataframe(pd.DataFrame([{"요소": k, "점수": v} for k,v in us.components.items()]), hide_index=True, use_container_width=True)
        st.caption(us.interpretation)
    with right:
        kr = build_market_regime("005930.KS", "technology", prices)
        score_card("KR MARKET REGIME", kr.score, kr.label)
        st.dataframe(pd.DataFrame([{"요소": k, "점수": v} for k,v in kr.components.items()]), hide_index=True, use_container_width=True)
        st.caption(kr.interpretation)

elif mode == "🔥 Scanner":
    st.subheader("V6 Setup Scanner")
    market_name = st.radio("시장", ["NASDAQ 100", "S&P 500", "KOSPI", "KOSDAQ"], horizontal=True)
    st.caption("Scanner의 Opportunity는 가격·추세·상대강도 기반 사전선별 점수입니다. 개별 분석에서는 Company Quality를 추가해 최종 Opportunity를 다시 계산합니다.")
    if st.button("Scanner 실행 / 갱신", type="primary"):
        with st.spinner(f"{market_name}의 Opportunity · Momentum · Pullback 후보를 계산하는 중입니다..."):
            region_symbol = "005930.KS" if market_name in ("KOSPI","KOSDAQ") else "SPY"
            regime = build_market_regime(region_symbol, "technology", prices)
            bench = prices("^KS11" if market_name in ("KOSPI","KOSDAQ") else "^GSPC", "18mo")
            scan, as_of = scan_market(market_name, regime, bench, universe_limit=220 if market_name != "S&P 500" else 320)
            st.session_state["scan_result"] = scan
            st.session_state["scan_as_of"] = as_of
            st.session_state["scan_market"] = market_name
    scan = st.session_state.get("scan_result", pd.DataFrame())
    if not scan.empty:
        st.caption(f"{st.session_state.get('scan_as_of','-')} 종가 기준 · {st.session_state.get('scan_market','')}")
        views = top_views(scan)
        tabs = st.tabs(["🔥 Opportunity Leaders", "🚀 Momentum Setups", "🎯 Pullback Setups"])
        for tab, key in zip(tabs, views):
            with tab:
                frame = views[key].copy()
                shown = frame[["Name","Symbol","Opportunity Proxy","Trend","RS","Momentum","Pullback","Pullback Status","Momentum Entry","Momentum Status","Risk"]]
                event = st.dataframe(shown, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row", key=f"scan_{key}")
                selected = event.selection.rows if event and hasattr(event, "selection") else []
                if selected:
                    row = frame.iloc[selected[0]]
                    st.session_state["symbol"] = row.Symbol
                    st.success(f"선택 종목: {row.Name} · {row.Symbol} — 상단 메뉴에서 종합분석으로 이동하세요.")
    else:
        st.info("Scanner 실행 버튼을 눌러 후보를 계산하세요.")

elif mode == "🧪 Calibration":
    if not symbol or not analysis:
        st.info("먼저 종목을 검색한 뒤 Calibration을 실행해 주세요.")
    else:
        st.subheader(f"Entry Calibration · {symbol}")
        st.caption("Point-in-time 재무 데이터 누출을 피하기 위해 V6.0 Calibration은 가격 기반 Pullback/Momentum Engine만 검증합니다. 시장 Regime은 중립으로 고정합니다.")
        threshold = st.slider("Signal threshold", 60, 90, 75)
        if st.button("Calibration 실행", type="primary"):
            try:
                with st.spinner("과거 각 거래일의 Setup을 재구성하는 중입니다..."):
                    detail, summary = run_setup_calibration(analysis["frame"], analysis["benchmark"], float(threshold))
                if summary.empty:
                    st.info("충분한 Calibration 결과가 없습니다.")
                else:
                    fmt = {"Hit 20D":"{:.1f}%","Avg 5D":"{:+.2f}%","Avg 10D":"{:+.2f}%","Avg 20D":"{:+.2f}%","Avg 60D":"{:+.2f}%","Avg MDD20":"{:+.2f}%"}
                    st.dataframe(summary.style.format(fmt, na_rep="—"), hide_index=True, use_container_width=True)
                    st.caption("Hit 20D는 20영업일 후 수익률이 양수였던 비율입니다. 과거 성과가 미래 성과를 보장하지 않습니다.")
                    with st.expander("Calibration 원자료"):
                        st.dataframe(detail.tail(250), hide_index=True, use_container_width=True)
            except Exception as exc:
                st.error(f"Calibration 실패: {exc}")

elif mode == "💾 History":
    st.subheader("V6 History Database")
    st.caption(f"현재 DB: {DB_FILE}. 로컬/자체 서버에서는 SQLite로 지속 저장됩니다. Streamlit Community Cloud는 재배포 시 로컬 디스크가 초기화될 수 있으므로 JSON 백업을 함께 제공합니다.")
    st.download_button("전체 History JSON 내보내기", HISTORY.export_json(), "stock_analyzer_v6_history.json", "application/json")
    uploaded = st.file_uploader("History JSON 가져오기", type="json")
    if uploaded and st.button("History 가져오기"):
        try:
            count = HISTORY.import_json(uploaded.getvalue())
            st.success(f"{count}개 레코드를 가져왔습니다.")
        except Exception as exc:
            st.error(f"가져오기 실패: {exc}")
    if symbol:
        rows = HISTORY.rows(symbol, 100)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.info("현재 선택 종목의 V6 저장 이력이 없습니다.")
