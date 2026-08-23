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
from plotly.subplots import make_subplots

from calibration_engine import run_setup_calibration
from company_engine import build_company_snapshot
from consensus_engine import build_consensus_v2
from history_store import SQLiteHistoryStore
from korean_stock_search import contains_hangul, load_krx_listing, search_krx_listing
from market_regime import build_market_regime, market_for_symbol
from opportunity_engine import build_opportunity
from quant_engine import build_quant_snapshot, financial_rows
from risk_engine import build_risk_snapshot
from scanner_engine import scan_market, top_views
from setup_engine import build_setups
from sr_engine import build_zones
from technical_engine import build_technical_snapshot

st.set_page_config(page_title="Stock Analyzer V6.0.1", page_icon="📈", layout="wide")

DB_FILE = Path(os.getenv("ANALYZER_DB_FILE", ".data/stock_analyzer_v6.sqlite"))
HISTORY = SQLiteHistoryStore(DB_FILE)

PULSE = {
    "S&P 500": "^GSPC", "Nasdaq 100": "^NDX", "SOX": "^SOX", "VIX": "^VIX",
    "Gold": "GC=F", "Silver": "SI=F", "WTI": "CL=F", "Copper": "HG=F",
    "USD/KRW": "KRW=X", "DXY": "DX-Y.NYB", "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD",
}

st.markdown("""
<style>
.stApp{background:linear-gradient(180deg,#07111f 0%,#081525 100%)}
.block-container{padding-top:1.1rem;max-width:1480px;padding-bottom:4rem}
h1,h2,h3{letter-spacing:-.025em}
.v6-section{margin-top:34px;margin-bottom:15px}
.v6-card{box-sizing:border-box;border:1px solid #29415e;border-radius:16px;padding:18px;background:#0d1b2d;height:100%;min-height:154px}
.v6-card.compact{min-height:132px}.v6-card.risk{min-height:182px}.v6-card.entry{min-height:155px}
.v6-kicker{font-size:.72rem;font-weight:850;letter-spacing:.14em;color:#38bdf8;margin-bottom:9px}
.v6-value{font-size:2rem;font-weight:900;color:#f8fafc;line-height:1.15;margin:4px 0 8px}.v6-sub{color:#94a3b8;line-height:1.65;font-size:.88rem}
.v6-pill{display:inline-block;border-radius:99px;padding:4px 9px;background:#102c46;color:#7dd3fc;font-weight:750;margin:3px 4px 3px 0}
.decision{border:1px solid #315272;border-radius:18px;padding:22px;background:linear-gradient(135deg,#0d1b2d,#10243a);margin:15px 0 24px}
.decision h2{margin:.2rem 0 .8rem}.decision p{color:#dbeafe;line-height:1.78;margin:.42rem 0}
.brief-card{box-sizing:border-box;border:1px solid #29415e;border-radius:15px;padding:19px;background:#0d1b2d;min-height:194px;height:100%;color:#dbeafe;margin-bottom:10px}
.brief-card.wide{min-height:165px}.brief-card h3{color:#f8fafc;margin:.1rem 0 1rem;font-size:1.28rem}.brief-card p{line-height:1.78;margin:0;color:#dbeafe}
.status-green{color:#34d399}.status-yellow{color:#fbbf24}.status-orange{color:#fb923c}.status-red{color:#fb7185}.status-muted{color:#94a3b8}
.zone{border-left:4px solid #38bdf8;background:#0d1b2d;border-radius:10px;padding:13px;margin:7px 0}.zone.r{border-left-color:#fb7185}
.explain{border:1px solid #29415e;border-radius:14px;padding:14px 16px;background:#0a1728;color:#cbd5e1;line-height:1.68;min-height:112px}
.indicator-row{border:1px solid #29415e;border-left:3px solid #64748b;border-radius:11px;padding:13px 15px;margin:9px 0;background:#0d1b2d;display:flex;justify-content:space-between;gap:20px;align-items:center}
.indicator-row.good{border-left-color:#10b981}.indicator-row.bad{border-left-color:#ef4444}.indicator-row small{display:block;color:#8292a8;margin-top:5px;line-height:1.55}.indicator-row strong{text-align:right;white-space:nowrap}
.scenario{box-sizing:border-box;border-radius:13px;padding:17px;min-height:160px;height:100%}.scenario h4{margin:0 0 15px;font-size:1.1rem}.scenario p{margin:0;line-height:1.72}.up{background:#103c30;color:#6ee7b7}.mid{background:#102d4d;color:#7dd3fc}.down{background:#451d28;color:#fda4af}
.pulse-shell{border:1px solid #29415e;border-radius:13px;padding:12px 12px 3px;background:#0d1b2d;min-height:142px}
.pulse-head{display:flex;justify-content:space-between;gap:8px;align-items:baseline}.pulse-head b{color:#f8fafc}.pulse-up{color:#34d399}.pulse-down{color:#fb7185}
.cal-help{border:1px solid #315272;background:#0d1b2d;border-radius:14px;padding:15px 17px;line-height:1.72;color:#cbd5e1;margin:8px 0 15px}
[data-testid="stMetricValue"]{font-size:clamp(1.4rem,2.5vw,2.1rem)}
[data-testid="stDataFrame"]{border:1px solid #29415e;border-radius:10px;overflow:hidden}
div[data-testid="stHorizontalBlock"]{gap:1rem}
hr{margin:1.5rem 0 1.8rem!important}
@media(max-width:700px){.block-container{padding-left:.8rem;padding-right:.8rem}.v6-card,.brief-card,.scenario{height:auto;min-height:0}.indicator-row{align-items:flex-start}}
</style>
""", unsafe_allow_html=True)


def money(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:,.2f}" if abs(value) < 10000 else f"{value:,.0f}"


def pct(value: float | None, digits: int = 2) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:+.{digits}f}%"


def score_color(value: float) -> str:
    return "#22c55e" if value >= 80 else "#34d399" if value >= 65 else "#94a3b8" if value >= 50 else "#fb923c" if value >= 35 else "#fb7185"


def grade_ko(value: float) -> str:
    if value >= 85: return "매우 강함"
    if value >= 75: return "강함"
    if value >= 65: return "양호"
    if value >= 50: return "중립"
    if value >= 35: return "약함"
    return "매우 약함"


def status_class(text: str) -> str:
    t = text.upper()
    if any(x in t for x in ("READY", "CONFIRMED", "PREFERRED", "RISK-ON", "STRONG", "LOW")):
        return "status-green"
    if any(x in t for x in ("DEVELOPING", "WATCH", "MIXED", "NEUTRAL", "MODERATE", "SELECTIVE")):
        return "status-yellow"
    if any(x in t for x in ("EXTENDED", "WARNING", "ELEVATED", "UPCOMING", "HIGH")):
        return "status-orange"
    return "status-red"


PULLBACK_STATUS = {
    "READY": "진입 유리",
    "DEVELOPING": "진입 검토",
    "NOT IN ZONE": "관망 · 눌림 대기",
    "STRUCTURE WARNING": "주의 · 구조 확인",
}
MOMENTUM_STATUS = {
    "CONFIRMED": "진입 유리",
    "EARLY BREAKOUT": "초기 돌파 확인",
    "WATCH": "관망 · 돌파 확인",
    "EXTENDED": "과열 주의 · 소규모 접근",
    "FAILED BREAKOUT": "진입 보류 · 돌파 실패",
}
PREFERRED_STATUS = {
    "Momentum Preferred": "Momentum 우세",
    "Pullback Preferred": "Pullback 우세",
    "Both Valid": "두 Setup 모두 유효",
    "No Clear Setup": "명확한 Setup 없음",
}


def setup_status_ko(setup) -> str:
    table = PULLBACK_STATUS if setup.name == "Pullback" else MOMENTUM_STATUS
    return table.get(setup.status, setup.status)


def preferred_ko(value: str) -> str:
    return PREFERRED_STATUS.get(value, value)


def risk_ko(value: str) -> str:
    return {"LOW":"낮음", "MODERATE":"보통", "HIGH":"높음", "EXTREME":"매우 높음"}.get(value, value)


def score_card(label: str, value: float | None, subtitle: str = "", compact: bool = False):
    if value is None:
        shown, color, state = "N/A", "#94a3b8", "데이터 부족"
    else:
        shown, color, state = f"{value:.1f}", score_color(value), grade_ko(value)
    cls = "v6-card compact" if compact else "v6-card"
    st.markdown(f"<div class='{cls}'><div class='v6-kicker'>{label}</div><div class='v6-value' style='color:{color}'>{shown}</div><div style='color:{color};font-weight:800;margin-bottom:6px'>{state}</div><div class='v6-sub'>{subtitle}</div></div>", unsafe_allow_html=True)


def briefing(title: str, body: str, kicker: str = "AI BRIEF", wide: bool = False):
    cls = "brief-card wide" if wide else "brief-card"
    st.markdown(f"<div class='{cls}'><div class='v6-kicker'>{kicker}</div><h3>{title}</h3><p>{body}</p></div>", unsafe_allow_html=True)


def indicator_row(label: str, value: str, guide: str, tone: str = "neutral"):
    cls = "indicator-row" + (" good" if tone == "good" else " bad" if tone == "bad" else "")
    st.markdown(f"<div class='{cls}'><div><b>{label}</b><small>{guide}</small></div><strong>{value}</strong></div>", unsafe_allow_html=True)


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
        data = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": q, "quotesCount": 10, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=8,
        ).json()
        merged.extend({
            "symbol": x.get("symbol"),
            "name": x.get("longname") or x.get("shortname") or x.get("symbol"),
            "exchange": x.get("exchDisp", ""), "type": x.get("quoteType", ""),
        } for x in data.get("quotes", []) if x.get("symbol"))
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
    "technology": ["MSFT", "AAPL", "NVDA", "AVGO", "ORCL", "AMD", "QCOM", "MU"],
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
    good_symbols = []
    for ticker in symbols:
        try:
            payload = yf.Ticker(ticker).get_info() or {}
            if payload:
                out.append(payload); good_symbols.append(ticker)
        except Exception:
            continue
    return out, good_symbols


@st.cache_data(ttl=3600, show_spinner=False)
def earnings_days(symbol: str) -> int | None:
    try:
        cal = yf.Ticker(symbol).calendar
        if isinstance(cal, dict):
            raw = cal.get("Earnings Date") or cal.get("EarningsDate")
            if isinstance(raw, (list, tuple)) and raw: raw = raw[0]
            if raw is not None:
                dt = pd.Timestamp(raw)
                if dt.tzinfo is not None: dt = dt.tz_localize(None)
                return (dt.normalize() - pd.Timestamp.now().normalize()).days
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

    zones = build_zones(
        frame, tech,
        option_put_wall=option_view.put_wall if option_view else None,
        option_call_wall=option_view.call_wall if option_view else None,
    )
    risk = build_risk_snapshot(tech, market, earnings_days(symbol))
    now = float(frame.Close.iloc[-1])
    setups = build_setups(now, tech, market, zones, risk)
    opportunity = build_opportunity(company, tech, market)
    consensus = build_consensus_v2(company, tech, setups, market, option_label, option_view.data_quality if option_view else None)
    quant = build_quant_snapshot(frame, company, tech, market, zones.supports, zones.resistances)
    return dict(
        frame=frame, info=inf, region=region, sector=sector, benchmark=benchmark, tech=tech, market=market,
        company=company, zones=zones, risk=risk, setups=setups, opportunity=opportunity,
        consensus=consensus, option=option_view, option_label=option_label, peer_symbols=peer_symbols,
        peers=peers, now=now, quant=quant,
    )


def reconstructed_trajectory(a: dict, count: int = 10) -> pd.DataFrame:
    """Price-history reconstruction for immediate 10D visualization.

    Current company quality and current Market Regime are held fixed. The chart is
    therefore an explainability/history aid, not point-in-time fundamental backtest.
    """
    d = a["frame"]
    rows = []
    dates = list(d.index[-count:])
    for date_value in dates:
        hist = d.loc[d.index <= date_value]
        if len(hist) < 210:
            continue
        bench_hist = a["benchmark"].loc[a["benchmark"].index <= date_value] if not a["benchmark"].empty else None
        try:
            tech = build_technical_snapshot(hist, bench_hist)
            zones = build_zones(hist, tech)
            risk = build_risk_snapshot(tech, a["market"], None)
            setups = build_setups(float(hist.Close.iloc[-1]), tech, a["market"], zones, risk)
            opp = build_opportunity(a["company"], tech, a["market"])
            quant = build_quant_snapshot(hist, a["company"], tech, a["market"], zones.supports, zones.resistances)
            rows.append({
                "date": pd.Timestamp(date_value), "Opportunity": opp.score, "Quant": quant["score"],
                "Trend": tech.trend, "Momentum": tech.momentum,
                "Pullback": setups.pullback.score, "Momentum Entry": setups.momentum.score,
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


def trajectory_chart(frame: pd.DataFrame, columns: list[str], key: str, title: str):
    if frame.empty or len(frame) < 2:
        st.info("최근 거래일 변화 차트를 계산할 데이터가 충분하지 않습니다.")
        return
    st.markdown(f"### {title}")
    fig = go.Figure()
    for col in columns:
        if col not in frame: continue
        fig.add_trace(go.Scatter(x=frame["date"], y=frame[col], mode="lines+markers", name=col, line=dict(width=2.4), marker=dict(size=7)))
    fig.update_layout(
        height=270, margin=dict(l=20, r=20, t=25, b=25),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0a1728",
        font=dict(color="#cbd5e1"), legend=dict(orientation="h", y=1.12),
        yaxis=dict(range=[0,100], gridcolor="#20344d"), xaxis=dict(gridcolor="#20344d"),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False}, key=key)
    st.caption("가격 기반 역산 참고 차트 · 현재 Company Quality와 Market Regime을 고정하고 각 거래일의 가격·거래량·기술 구조를 재계산합니다.")


def build_briefings(a: dict) -> dict[str, str]:
    tech, company, market, risk, setups, opp = a["tech"], a["company"], a["market"], a["risk"], a["setups"], a["opportunity"]
    q = a["quant"]
    company_text = (
        f"Company Quality는 {company.score:.0f}점이며 데이터 커버리지는 {company.coverage*100:.0f}%입니다. " if company.score is not None
        else "Company Quality는 공개 데이터 부족으로 제한적으로 계산됐습니다. "
    )
    strongest = max(((k,v) for k,v in company.factors.items() if v is not None), key=lambda x:x[1], default=("N/A",0))
    weakest = min(((k,v) for k,v in company.factors.items() if v is not None), key=lambda x:x[1], default=("N/A",0))
    company_text += f"현재 강점은 {strongest[0]}({strongest[1]:.0f}), 상대적으로 확인이 필요한 축은 {weakest[0]}({weakest[1]:.0f})입니다. 결측값은 0점으로 간주하지 않고 제외·재가중합니다."

    quant_text = (
        f"Quant Composite는 {q['score']:.0f}점입니다. Trend {tech.trend:.0f}, Momentum {tech.momentum:.0f}, "
        f"Relative Strength {tech.relative_strength:.0f}, Demand {tech.demand:.0f}입니다. RSI {tech.rsi:.1f}, "
        f"거래량 {tech.volume_ratio:.2f}배를 함께 보면 {'가격 리더십이 강합니다.' if tech.trend>=75 else '추세 확인이 더 필요합니다.'}"
    )
    pull_label, mom_label = setup_status_ko(setups.pullback), setup_status_ko(setups.momentum)
    entry_text = (
        f"Pullback {setups.pullback.score:.0f}점({pull_label}), Momentum {setups.momentum.score:.0f}점({mom_label})으로 "
        f"현재 Preferred Setup은 {preferred_ko(setups.preferred)}입니다. {setups.summary} "
        f"신규 진입 시 무효화선과 거래량 확인을 우선하세요."
    )
    market_text = (
        f"{market.market} Market Regime은 {market.score:.0f}점 · {market.label}입니다. Overall Risk는 {risk.score:.0f}점({risk_ko(risk.level)})이며 "
        f"Extension {risk.extension}, Volatility {risk.volatility}, Liquidity {risk.liquidity} 상태입니다. 위험이 높을수록 종목 매력도를 깎기보다 초기 비중을 줄이는 방식으로 해석합니다."
    )
    overall_text = (
        f"종목 매력도는 {opp.score:.0f}점({grade_ko(opp.score)})입니다. {opp.interpretation} "
        f"현재는 {preferred_ko(setups.preferred)}로 해석되며 Risk는 {risk_ko(risk.level)}입니다. "
        f"좋은 종목과 좋은 매수 가격을 분리해서 보고, Entry Engine의 Setup과 Risk 패널을 함께 확인하는 것이 핵심입니다."
    )
    return {"overall":overall_text, "company":company_text, "quant":quant_text, "entry":entry_text, "market":market_text}


def render_ai_briefings(a: dict):
    texts = build_briefings(a)
    st.markdown("<div class='v6-section'></div>", unsafe_allow_html=True)
    st.subheader("AI 종합 브리핑")
    briefing("종합 AI 브리핑", texts["overall"], "DECISION BRIEF", wide=True)
    c1, c2 = st.columns(2)
    with c1: briefing("기업 브리핑", texts["company"], "COMPANY")
    with c2: briefing("추세·퀀트 브리핑", texts["quant"], "QUANT / TREND")
    c3, c4 = st.columns(2)
    with c3: briefing("진입 브리핑", texts["entry"], "ENTRY SETUP")
    with c4: briefing("시장·리스크 브리핑", texts["market"], "MARKET / RISK")


def render_entry_engine(a: dict):
    setups = a["setups"]
    st.markdown("<div class='v6-section'></div>", unsafe_allow_html=True)
    st.subheader("Entry Engine V3")
    e1, e2 = st.columns(2)
    with e1:
        st.markdown("<div class='explain'><b>🎯 Pullback Entry · 눌림목 진입</b><br>상승 추세 종목이 EMA·지지 Zone 부근으로 조정받았을 때 가격 메리트와 지지 가능성을 평가합니다. 거래량 감소는 건강한 조정으로 긍정적일 수 있습니다.</div>", unsafe_allow_html=True)
    with e2:
        st.markdown("<div class='explain'><b>🚀 Momentum Entry · 추세 추종 진입</b><br>저항 돌파·신고가 접근·상대강도·거래량 확대로 상승 흐름을 따라갈 수 있는지 평가합니다. RSI가 높아도 강한 추세라면 단순 감점하지 않습니다.</div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    for col, setup, icon in ((c1, setups.pullback, "🎯"), (c2, setups.momentum, "🚀")):
        with col:
            cls = status_class(setup.status)
            display = setup_status_ko(setup)
            st.markdown(f"<div class='v6-card entry'><div class='v6-kicker'>{icon} {setup.name.upper()} ENTRY</div><div class='v6-value'>{setup.score:.1f}</div><div class='{cls}' style='font-size:1.03rem;font-weight:850'>{display} <span class='v6-sub'>· {setup.status}</span></div></div>", unsafe_allow_html=True)
            rows = [{"요소": k, "점수": round(v,1), "해석": setup.details[k]} for k,v in setup.factors.items()]
            st.dataframe(
                pd.DataFrame(rows), hide_index=True, use_container_width=True, height=300,
                column_config={"점수": st.column_config.ProgressColumn("점수", min_value=0, max_value=100, format="%.1f")},
                key=f"entry_{setup.name}_{a['now']}",
            )
            zone = f"참고 Zone {money(setup.zone[0])} ~ {money(setup.zone[1])}" if setup.zone else "참고 Zone · 현재 명확한 Zone 없음"
            trigger = f"Trigger {money(setup.trigger)}" if setup.trigger else "Trigger · 해당 없음"
            invalid = f"Invalidation {money(setup.invalidation)}" if setup.invalidation else "Invalidation · N/A"
            st.caption(f"{zone}  ·  {trigger}  ·  {invalid}")


def render_risk_engine(a: dict):
    risk = a["risk"]
    st.markdown("<div class='v6-section'></div>", unsafe_allow_html=True)
    st.subheader("Risk Engine")
    rcols = st.columns(5)
    items = [
        ("Extension", risk.extension, risk.details["Extension"]), ("Volatility", risk.volatility, risk.details["Volatility"]),
        ("Earnings", risk.earnings, risk.details["Earnings"]), ("Liquidity", risk.liquidity, risk.details["Liquidity"]),
        ("Market Risk", risk.market, risk.details["Market"]),
    ]
    for col, (label, value, detail) in zip(rcols, items):
        with col:
            st.markdown(f"<div class='v6-card risk'><div class='v6-kicker'>{label}</div><div style='font-size:1.18rem;font-weight:850;margin:7px 0 8px'>{value}</div><div class='v6-sub'>{detail}</div></div>", unsafe_allow_html=True)
    st.caption(f"Overall Risk {risk.score:.1f} · {risk_ko(risk.level)} ({risk.level}) · Starter-size multiplier {risk.position_size_multiplier:.2f}x · 위험은 Opportunity를 직접 깎기보다 초기 비중 조정에 사용합니다.")


def render_company_summary(a: dict):
    company = a["company"]
    st.markdown("<div class='v6-section'></div>", unsafe_allow_html=True)
    st.subheader("Company Quality V2")
    if company.notes: st.info(" ".join(company.notes))
    fcols = st.columns(5)
    for col, (label, value) in zip(fcols, company.factors.items()):
        with col: score_card(label.upper(), value, "결측 항목 제외 · 상대평가 가능 시 혼합", compact=True)
    if company.relative:
        rel = pd.DataFrame([{"지표": k, "업종 상대점수": v} for k,v in company.relative.items() if v is not None])
        if not rel.empty:
            with st.expander("업종 상대평가 상세"):
                st.dataframe(rel, hide_index=True, use_container_width=True,
                             column_config={"업종 상대점수": st.column_config.ProgressColumn("업종 상대점수", min_value=0,max_value=100,format="%.1f")})
                st.caption("자동 동종업종 후보: " + (", ".join(a["peer_symbols"]) if a["peer_symbols"] else "후보가 충분하지 않습니다."))


def render_consensus(a: dict):
    cons = a["consensus"]
    st.markdown("<div class='v6-section'></div>", unsafe_allow_html=True)
    st.subheader("Multi-Lens Consensus V2")
    c1,c2,c3 = st.columns(3)
    c1.metric("Supportive Lenses", f"{cons.supportive} / {cons.available}")
    c2.metric("Signal Agreement", f"{cons.signal_agreement}%")
    c3.metric("Data Confidence", f"{cons.data_confidence}%")
    st.info(f"**{cons.headline} · {cons.pattern}**  \n{cons.interpretation}")
    with st.expander("Consensus 렌즈 상세"):
        st.dataframe(pd.DataFrame([{"Lens":k,"판단":v} for k,v in cons.lenses.items()]), hide_index=True, use_container_width=True)
        st.caption("Signal Agreement는 렌즈 방향의 일치도, Data Confidence는 원자료 충실도입니다. 상승 확률이 아닙니다.")


def render_scenarios(a: dict):
    setups, zones, tech = a["setups"], a["zones"], a["tech"]
    support = zones.supports[0] if zones.supports else None
    resistance = zones.resistances[0] if zones.resistances else None
    pull_zone = setups.pullback.zone or ((support.low,support.high) if support else None)
    trigger = setups.momentum.trigger or (resistance.center if resistance else tech.prior_high20)
    invalid = min(x for x in [setups.pullback.invalidation, setups.momentum.invalidation] if x is not None) if any(x is not None for x in [setups.pullback.invalidation,setups.momentum.invalidation]) else None
    st.markdown("<div class='v6-section'></div>", unsafe_allow_html=True)
    st.subheader("대응 시나리오")
    c1,c2,c3=st.columns(3)
    with c1:
        st.markdown(f"<div class='scenario up'><h4>🟢 Bull · 돌파 지속</h4><p><b>조건</b> {money(trigger)} 상향 돌파/지지 + 거래량 확인<br><b>대응</b> Momentum 점수가 유지될 때 소규모 분할 접근<br><b>확인</b> 상대강도와 거래량 동반 여부</p></div>", unsafe_allow_html=True)
    with c2:
        zone_txt = f"{money(pull_zone[0])} ~ {money(pull_zone[1])}" if pull_zone else "새 지지 Zone"
        st.markdown(f"<div class='scenario mid'><h4>🟡 Base · 눌림/지지</h4><p><b>조건</b> {zone_txt} 부근 안정화<br><b>대응</b> 지지 반응 확인 시 Pullback 분할 접근<br><b>주의</b> 지지 확인 전 박스 중앙 추격 자제</p></div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div class='scenario down'><h4>🔴 Bear · 무효화</h4><p><b>조건</b> {money(invalid)} 종가 이탈 또는 돌파 실패<br><b>대응</b> 신규 진입 중단·비중 축소 검토<br><b>재평가</b> 다음 Support Zone과 Market Regime 확인</p></div>", unsafe_allow_html=True)


def render_sr_and_chart(a: dict):
    tech,zones = a["tech"],a["zones"]
    st.markdown("<div class='v6-section'></div>", unsafe_allow_html=True)
    st.subheader("Support / Resistance Zones")
    left,right=st.columns(2)
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

    st.subheader("가격 차트 · 지지와 저항")
    d=a["frame"].tail(252)
    fig=go.Figure(go.Candlestick(x=d.index,open=d.Open,high=d.High,low=d.Low,close=d.Close,name="Price"))
    for value,name_,color in ((tech.ema20,"EMA20","#38bdf8"),(tech.ema50,"EMA50","#f59e0b"),(tech.ema200,"EMA200","#a855f7")):
        fig.add_hline(y=value,line_dash="dot",line_color=color,annotation_text=name_)
    for z in zones.supports[:3]: fig.add_hrect(y0=z.low,y1=z.high,fillcolor="rgba(56,189,248,.08)",line_width=0)
    for z in zones.resistances[:3]: fig.add_hrect(y0=z.low,y1=z.high,fillcolor="rgba(251,113,133,.08)",line_width=0)
    fig.update_layout(height=550,xaxis_rangeslider_visible=False,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="#0a1728",font=dict(color="#cbd5e1"),xaxis=dict(gridcolor="#20344d"),yaxis=dict(gridcolor="#20344d"))
    st.plotly_chart(fig,use_container_width=True)


def render_analysis(a: dict, symbol: str):
    inf,tech,market,company,risk,setups,opp = a["info"],a["tech"],a["market"],a["company"],a["risk"],a["setups"],a["opportunity"]
    name=inf.get("longName") or inf.get("shortName") or symbol
    st.header(f"{name} · {symbol}")
    st.caption(f"V6.0.1 종합분석 · 데이터 기준 {pd.Timestamp(a['frame'].index[-1]).date()} · {a['region']} Market · Sector {a['sector'] or 'N/A'}")

    pcls=status_class(setups.preferred); rcls=status_class(risk.level)
    st.markdown(f"""<div class='decision'><div class='v6-kicker'>V6 MULTI-LENS DECISION</div>
    <h2>Opportunity {opp.score:.1f} · {grade_ko(opp.score)}</h2>
    <p><b>Preferred Setup</b> · <span class='{pcls}'>{preferred_ko(setups.preferred)}</span> &nbsp; | &nbsp; <b>Risk</b> · <span class='{rcls}'>{risk_ko(risk.level)}</span> &nbsp; | &nbsp; <b>Market</b> · {market.label}</p>
    <p>{opp.interpretation} {setups.summary}</p></div>""", unsafe_allow_html=True)

    cols=st.columns(5)
    items=[
        ("OPPORTUNITY",opp.score,"종목 매력도 · Entry/Risk 별도"),
        ("COMPANY QUALITY",company.score,f"Coverage {company.coverage*100:.0f}% · {company.confidence}"),
        ("TREND / LEADERSHIP",tech.trend,f"12M {tech.ret_12m:+.1f}%"),
        ("RELATIVE STRENGTH",tech.relative_strength,"시장 벤치마크 대비"),
        ("MOMENTUM / DEMAND",.60*tech.momentum+.40*tech.demand,f"RSI {tech.rsi:.1f} · Vol {tech.volume_ratio:.2f}x"),
    ]
    for col,item in zip(cols,items):
        with col: score_card(*item)

    render_ai_briefings(a)
    render_entry_engine(a)
    render_risk_engine(a)
    render_company_summary(a)

    st.markdown("<div class='v6-section'></div>", unsafe_allow_html=True)
    st.subheader("Market Regime")
    m1,m2=st.columns([1,2])
    with m1: score_card(f"{market.market} MARKET",market.score,f"{market.label} · Data quality {market.data_quality*100:.0f}%")
    with m2:
        st.dataframe(pd.DataFrame([{"구성요소":k,"점수":v} for k,v in market.components.items()]),hide_index=True,use_container_width=True,height=190,column_config={"점수":st.column_config.ProgressColumn("점수", min_value=0, max_value=100, format="%.1f")})
    st.caption(market.interpretation)

    render_consensus(a)
    traj=reconstructed_trajectory(a,10)
    st.markdown("<div class='v6-section'></div>", unsafe_allow_html=True)
    trajectory_chart(traj,["Opportunity","Pullback","Momentum Entry"],f"overall_traj_{symbol}","최근 10영업일 · Opportunity & Entry 변화")

    render_scenarios(a)
    render_sr_and_chart(a)

    data_date=pd.Timestamp(a["frame"].index[-1]).date()
    HISTORY.record(symbol,{"opportunity":opp.score,"company":company.score,"trend":tech.trend,"momentum":tech.momentum,"relative_strength":tech.relative_strength,"pullback":setups.pullback.score,"momentum_entry":setups.momentum.score,"market":market.score,"risk":risk.score,"preferred_setup":setups.preferred},data_date,{"version":"6.0.1","source":"recorded"})

    with st.expander("최근 뉴스"):
        rows=news(symbol)
        if not rows: st.info("현재 불러온 뉴스가 없습니다.")
        for title,summary,url in rows:
            st.markdown(f"**[{title}]({url})**" if url else f"**{title}**")
            st.caption((summary or "제목 기반 참고 뉴스")[:260])


def render_quant_chart(a: dict):
    q=a["quant"]; d=a["frame"].tail(130); idx=d.index; chart=q["chart"]
    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[.72,.28],vertical_spacing=.04,specs=[[{}],[{"secondary_y":True}]])
    fig.add_trace(go.Scatter(x=idx,y=d.Close,line=dict(color="#f8fafc",width=2.5),name="Close"),row=1,col=1)
    for srs,n,c,ds in [(chart["ema20"],"EMA20","#3b82f6",None),(chart["ema50"],"EMA50","#f59e0b",None),(chart["ema200"],"EMA200","#a855f7","dash")]:
        fig.add_trace(go.Scatter(x=idx,y=srs.reindex(idx),line=dict(color=c,width=1.6,dash=ds),name=n),row=1,col=1)
    fig.add_trace(go.Scatter(x=idx,y=chart["bb_upper"].reindex(idx),line=dict(color="#64748b",width=1,dash="dot"),name="BB Upper"),row=1,col=1)
    fig.add_trace(go.Scatter(x=idx,y=chart["bb_lower"].reindex(idx),line=dict(color="#64748b",width=1,dash="dot"),fill="tonexty",fillcolor="rgba(100,116,139,.08)",name="BB Lower"),row=1,col=1)
    colors=np.where(d.Close>=d.Open,"#38bdf8","#fb7185")
    fig.add_trace(go.Bar(x=idx,y=d.Volume,marker_color=colors,name="Volume"),row=2,col=1)
    fig.add_trace(go.Scatter(x=idx,y=chart["obv"].reindex(idx),line=dict(color="#f59e0b",width=1.5),name="OBV"),row=2,col=1,secondary_y=True)
    fig.update_layout(height=590,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="#0a1728",font=dict(color="#cbd5e1"),legend=dict(orientation="h"),margin=dict(l=30,r=25,t=55,b=25))
    fig.update_xaxes(gridcolor="#20344d"); fig.update_yaxes(gridcolor="#20344d")
    st.plotly_chart(fig,use_container_width=True)


def render_can_slim(a: dict):
    q=a["quant"]; can=q["can_slim"]
    desc={"C":"최근 이익·매출 성장","A":"연간 수익성·ROE","N":"신고가·새로운 모멘텀","S":"거래량 수급","L":"시장 주도력","I":"기관 수급 대용","M":"시장 방향"}
    guide={
        "C":"최근 EPS/매출 성장률을 결합합니다. 극단값은 기저효과·일회성 이익을 확인해야 합니다.",
        "A":"ROE와 Profitability를 중심으로 장기 수익성을 봅니다.",
        "N":"추세와 52주 가격 위치를 결합해 새로운 모멘텀 여부를 봅니다.",
        "S":"최근 거래량과 Demand를 결합합니다. Pullback과 Momentum에서는 거래량 의미가 다를 수 있습니다.",
        "L":"시장 대비 Relative Strength와 추세 리더십을 봅니다.",
        "I":"OBV·거래량 기반 Demand 대용지표이며 실제 기관 보유자료는 아닙니다.",
        "M":"현재 US/KR Market Regime 점수입니다.",
    }
    st.subheader("CAN SLIM 분석")
    st.caption("V6의 Opportunity 점수와 별개의 보조 프레임워크입니다. 원형 CAN SLIM의 공개 데이터 대용지표를 사용하며 결측값은 임의 0점 처리하지 않습니다.")
    cols=st.columns(4)
    for i,(k,v) in enumerate(can.items()):
        with cols[i%4]: score_card(f"{k} · {desc[k]}",v,guide[k],compact=True)
    with st.expander("CAN SLIM 점수 읽는 법"):
        st.markdown("**공통 기준** · 50점은 중립, 65점 이상은 우호적, 80점 이상은 강한 신호로 봅니다. 한 항목의 고득점보다 여러 항목이 함께 개선되는지가 중요합니다.\n\nCAN SLIM은 V6의 주 점수에 중복 합산하지 않고, 다른 관점에서 현재 상태를 읽는 보조 렌즈로 사용합니다.")


def render_aux_quant(a: dict):
    aux=a["quant"]["aux"]
    guides={
        "평균회귀":"최근 평균에서 벗어난 정도입니다. 50은 중립, 높을수록 평균 아래에서 반등 여지가 커질 수 있습니다.",
        "모멘텀":"RSI·최근 수익률·MACD·ADX를 결합한 상승 추진력입니다.",
        "다중 시간대":"중기·장기 이동평균과 수익률 정렬 정도입니다.",
        "낙폭 위치":"최근 고점 대비 낙폭을 상태 점수로 변환합니다. 미래 하락 위험을 보장하지 않습니다.",
        "수급 흐름":"거래량·OBV·상승/하락 거래량을 이용한 Demand 대용지표입니다.",
        "Target Price Factor":"현재가에서 가장 가까운 상단 Resistance Zone까지의 여유를 단순 참고점수로 변환합니다. 공식 목표주가가 아닙니다.",
        "통계적 Z-Score":"최근 60일 평균에서 가격이 얼마나 벗어났는지 변환한 상태점수입니다.",
        "Relative Strength":"시장 벤치마크보다 얼마나 강한 흐름인지 보여줍니다.",
        "Extension Balance":"EMA20 이격과 RSI를 이용해 추격 부담을 봅니다. Momentum 자체의 강도와는 별도입니다.",
    }
    with st.expander("보조 퀀트 지표",expanded=False):
        st.caption("보조 점수는 50을 중립으로 읽습니다. 방향 확인용이며 단독 매수·매도 신호로 사용하지 않습니다.")
        cols=st.columns(2)
        for i,(k,v) in enumerate(aux.items()):
            with cols[i%2]: score_card(k,v,guides[k],compact=True)


def render_peer_comparison(a: dict, symbol: str):
    st.subheader("동일/유사 업종 경쟁사 비교")
    defaults=[symbol]+list(a["peer_symbols"])
    raw=st.text_input("비교 티커 · 쉼표로 수정",value=", ".join(defaults),key=f"peer_edit_{symbol}")
    symbols=list(dict.fromkeys([x.strip().upper() for x in raw.split(",") if x.strip()]))[:6]
    rows=[]
    for ticker in symbols:
        payload=info(ticker)
        try:
            d=prices(ticker,"1y"); c=d.Close.dropna(); ret=(c.iloc[-1]/c.iloc[0]-1)*100 if len(c)>1 else np.nan
        except Exception: ret=np.nan
        rows.append({
            "종목":payload.get("shortName") or payload.get("longName") or ticker,"티커":ticker,
            "시가총액":(payload.get("marketCap") or np.nan)/1e9,"PER":payload.get("trailingPE",np.nan),"PBR":payload.get("priceToBook",np.nan),
            "ROE":(payload.get("returnOnEquity") or np.nan)*100,"영업이익률":(payload.get("operatingMargins") or np.nan)*100,"12M":ret,
        })
    pf=pd.DataFrame(rows)
    if pf.empty:
        st.info("비교 가능한 경쟁사 데이터가 없습니다.")
    else:
        st.dataframe(pf.style.format({"시가총액":"{:,.1f}B","PER":"{:.1f}","PBR":"{:.2f}","ROE":"{:.1f}%","영업이익률":"{:.1f}%","12M":"{:+.1f}%"},na_rep="—"),hide_index=True,use_container_width=True)
    st.caption("자동 후보군은 참고용이며 직접 티커를 수정할 수 있습니다. 사업구조가 다른 기업이 섞일 수 있으므로 단순 수치 비교보다 업종·성장단계 차이를 함께 확인하세요.")


def render_quant_analysis(a: dict, symbol: str):
    inf,tech,company,q=a["info"],a["tech"],a["company"],a["quant"]
    name=inf.get("longName") or inf.get("shortName") or symbol
    st.header(f"퀀트분석 · {name} ({symbol})")
    st.caption("V6 Quant Composite는 Company Quality + Trend + Momentum + Demand + Relative Strength를 묶은 설명용 정량 점수입니다. Market Regime과 Entry는 중복을 피하기 위해 별도로 봅니다.")
    c1,c2,c3,c4,c5=st.columns(5)
    for col,(label,value,sub) in zip([c1,c2,c3,c4,c5],[
        ("QUANT COMPOSITE",q["score"],"시장환경·Entry 제외"),("TREND",tech.trend,"중장기 구조"),("MOMENTUM",tech.momentum,f"RSI {tech.rsi:.1f}"),("DEMAND",tech.demand,f"Vol {tech.volume_ratio:.2f}x"),("RELATIVE STRENGTH",tech.relative_strength,"시장 대비"),
    ]):
        with col: score_card(label,value,sub)

    traj=reconstructed_trajectory(a,10)
    st.markdown("<div class='v6-section'></div>",unsafe_allow_html=True)
    trajectory_chart(traj,["Quant","Trend","Momentum"],f"quant_traj_{symbol}","QUANT SCORE · 최근 10영업일 변화")
    if not traj.empty:
        first,last=traj.iloc[0],traj.iloc[-1]
        st.info(f"최근 10영업일 참고 흐름 · Quant {first['Quant']:.0f} → {last['Quant']:.0f}, Trend {first['Trend']:.0f} → {last['Trend']:.0f}, Momentum {first['Momentum']:.0f} → {last['Momentum']:.0f}")

    st.markdown("<div class='v6-section'></div>",unsafe_allow_html=True)
    st.subheader("가격 · 추세 · 거래량")
    render_quant_chart(a)
    st.info(f"핵심 관찰 · 현재 52주 범위의 {q['position52']:.1f}% 위치 · Trend {tech.trend:.1f} · RSI {tech.rsi:.1f} · 거래량 {tech.volume_ratio:.2f}x · Relative Strength {tech.relative_strength:.1f}")

    st.markdown("<div class='v6-section'></div>",unsafe_allow_html=True)
    render_can_slim(a)
    render_aux_quant(a)

    st.markdown("<div class='v6-section'></div>",unsafe_allow_html=True)
    st.subheader("기술 지표")
    for label,value,guide in q["technical_rows"]:
        tone="bad" if label=="ATR%" and tech.atr_pct>=6 else "good" if label in ("12M 수익률","3M 수익률") and not value.startswith("-") else "neutral"
        indicator_row(label,value,guide,tone)

    st.markdown("<div class='v6-section'></div>",unsafe_allow_html=True)
    st.subheader("재무 지표")
    for label,value,guide in financial_rows(company,inf): indicator_row(label,value,guide,"neutral")

    render_peer_comparison(a,symbol)


def pulse_card(name: str, ticker: str, key: str):
    try:
        daily=prices(ticker,"1mo","1d"); c=daily.Close.dropna()
        if len(c)<2: raise ValueError
        current=float(c.iloc[-1]); change=(current/float(c.iloc[-2])-1)*100
        try:
            intraday=prices(ticker,"5d","15m"); s=intraday.Close.dropna().tail(40)
            y=(s/s.iloc[0]-1)*100 if len(s)>2 else (c.tail(20)/c.tail(20).iloc[0]-1)*100
            x=s.index if len(s)>2 else c.tail(20).index
        except Exception:
            y=(c.tail(20)/c.tail(20).iloc[0]-1)*100; x=c.tail(20).index
        cls="pulse-up" if change>=0 else "pulse-down"
        st.markdown(f"<div class='pulse-shell'><div class='pulse-head'><b>{name}</b><span class='{cls}'>{change:+.2f}%</span></div><div class='v6-sub'>{money(current)}</div>",unsafe_allow_html=True)
        fig=go.Figure(go.Scatter(x=x,y=y,mode="lines",line=dict(width=2),fill="tozeroy"))
        fig.add_hline(y=0,line_width=1,line_color="#64748b")
        fig.update_layout(height=78,margin=dict(l=0,r=0,t=3,b=0),showlegend=False,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",xaxis_visible=False,yaxis_visible=False)
        st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False},key=key)
        st.markdown("</div>",unsafe_allow_html=True)
    except Exception:
        st.markdown(f"<div class='pulse-shell'><b>{name}</b><div class='v6-sub'>데이터 없음</div></div>",unsafe_allow_html=True)


def regime_history(symbol: str, sector: str, count: int = 10) -> pd.DataFrame:
    try:
        ref=prices("^GSPC" if market_for_symbol(symbol)=="US" else "^KS11","2mo")
        dates=list(ref.index[-count:])
        rows=[]
        for dt in dates:
            snap=build_market_regime(symbol,sector,prices,as_of=pd.Timestamp(dt).date())
            rows.append({"date":pd.Timestamp(dt),"Market Regime":snap.score})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def render_market_dashboard():
    st.header("시장환경 · Market Dashboard")
    st.caption("V6 Market Regime의 구조적 판단과 V5에서 유용했던 Market Pulse를 함께 보여줍니다. 상승/하락 색상은 단기 변화이며 Regime 점수와 동일한 의미는 아닙니다.")
    left,right=st.columns(2)
    with left:
        us=build_market_regime("SPY","technology",prices)
        score_card("US MARKET REGIME",us.score,f"{us.label} · Data quality {us.data_quality*100:.0f}%")
        st.dataframe(pd.DataFrame([{"요소":k,"점수":v} for k,v in us.components.items()]),hide_index=True,use_container_width=True,height=250,column_config={"점수":st.column_config.ProgressColumn("점수", min_value=0, max_value=100, format="%.1f")})
        st.caption(us.interpretation)
    with right:
        kr=build_market_regime("005930.KS","technology",prices)
        score_card("KR MARKET REGIME",kr.score,f"{kr.label} · Data quality {kr.data_quality*100:.0f}%")
        st.dataframe(pd.DataFrame([{"요소":k,"점수":v} for k,v in kr.components.items()]),hide_index=True,use_container_width=True,height=250,column_config={"점수":st.column_config.ProgressColumn("점수", min_value=0, max_value=100, format="%.1f")})
        st.caption(kr.interpretation)

    st.markdown("<div class='v6-section'></div>",unsafe_allow_html=True)
    st.subheader("Market Pulse · 주요 자산")
    items=list(PULSE.items())
    for i in range(0,len(items),4):
        cols=st.columns(4)
        for j,(name,ticker) in enumerate(items[i:i+4]):
            with cols[j]: pulse_card(name,ticker,f"pulse_{ticker}_{i+j}")

    st.markdown("<div class='v6-section'></div>",unsafe_allow_html=True)
    st.subheader("금리 · 신용시장 보조 패널")
    cols=st.columns(4)
    for col,(name,ticker) in zip(cols,[("US 10Y","^TNX"),("HYG","HYG"),("LQD","LQD"),("USD/KRW","KRW=X")]):
        try:
            c=prices(ticker,"1mo").Close.dropna(); val=float(c.iloc[-1]); ch=(val/c.iloc[-2]-1)*100
            col.metric(name,money(val),pct(ch))
        except Exception: col.metric(name,"N/A")
    st.caption("US 10Y는 Yahoo의 ^TNX 표시값, HYG/LQD는 신용 위험선호 참고 ETF입니다. 개별 지표는 Regime의 보조 확인값으로 해석하세요.")

    with st.expander("Market Regime · 최근 10영업일 변화"):
        a,b=st.columns(2)
        with a: trajectory_chart(regime_history("SPY","technology"),["Market Regime"],"us_market_traj","US Market Regime")
        with b: trajectory_chart(regime_history("005930.KS","technology"),["Market Regime"],"kr_market_traj","KR Market Regime")


def render_scanner_section():
    st.markdown("### 🔥 V6 Setup Scanner")
    st.caption("시장 전체를 훑어 Opportunity / Momentum / Pullback 후보를 찾는 독립 Scanner입니다. 개별 종목 검색 메뉴와 분리되어 있습니다.")
    market_name=st.radio("시장",["NASDAQ 100","S&P 500","KOSPI","KOSDAQ"],horizontal=True,key="scanner_market")
    if st.button("Scanner 실행 / 갱신",type="primary",key="run_scanner"):
        with st.spinner(f"{market_name}의 후보를 계산하는 중입니다..."):
            region_symbol="005930.KS" if market_name in ("KOSPI","KOSDAQ") else "SPY"
            regime=build_market_regime(region_symbol,"technology",prices)
            bench=prices("^KS11" if market_name in ("KOSPI","KOSDAQ") else "^GSPC","18mo")
            scan,as_of=scan_market(market_name,regime,bench,universe_limit=220 if market_name!="S&P 500" else 320)
            st.session_state["scan_result"]=scan; st.session_state["scan_as_of"]=as_of; st.session_state["scan_market"]=market_name
    scan=st.session_state.get("scan_result",pd.DataFrame())
    if not scan.empty:
        st.caption(f"{st.session_state.get('scan_as_of','-')} 종가 기준 · {st.session_state.get('scan_market','')}")
        views=top_views(scan); tabs=st.tabs(["🔥 Opportunity Leaders","🚀 Momentum Setups","🎯 Pullback Setups"])
        for tab,key in zip(tabs,views):
            with tab:
                frame=views[key].copy()
                shown=frame[["Name","Symbol","Opportunity Proxy","Trend","RS","Momentum","Pullback","Pullback Status","Momentum Entry","Momentum Status","Risk"]].copy()
                shown["Pullback Status"]=shown["Pullback Status"].map(lambda x:PULLBACK_STATUS.get(x,x))
                shown["Momentum Status"]=shown["Momentum Status"].map(lambda x:MOMENTUM_STATUS.get(x,x))
                event=st.dataframe(shown,hide_index=True,use_container_width=True,on_select="rerun",selection_mode="single-row",key=f"scan_{key}")
                selected=event.selection.rows if event and hasattr(event,"selection") else []
                if selected:
                    row=frame.iloc[selected[0]]; st.session_state["symbol"]=row.Symbol
                    st.success(f"선택 종목: {row.Name} · {row.Symbol} — 아래 개별 종목 메뉴에서 분석할 수 있습니다.")
    else: st.info("Scanner 실행 버튼을 누르면 시장 후보를 계산합니다.")


def calibration_summary_text(summary: pd.DataFrame, threshold: int) -> str:
    if summary.empty: return "충분한 결과가 없습니다."
    rows={r["Setup"]:r for _,r in summary.iterrows()}
    p,m=rows.get("Pullback"),rows.get("Momentum")
    pieces=[f"현재 기준은 {threshold}점으로, 이 점수 이상이었던 과거 거래일만 진입 신호로 인정했습니다."]
    if p is not None: pieces.append(f"Pullback은 {int(p['Signals'])}개 일별 신호({int(p['Independent'])}개 독립 에피소드), 20D 양수 비율 {p['Hit 20D']:.1f}%였습니다.")
    if m is not None: pieces.append(f"Momentum은 {int(m['Signals'])}개 일별 신호({int(m['Independent'])}개 독립 에피소드), 20D 양수 비율 {m['Hit 20D']:.1f}%였습니다.")
    if p is not None and m is not None and np.isfinite(p["Avg 20D"]) and np.isfinite(m["Avg 20D"]):
        better="Pullback" if p["Avg 20D"]>m["Avg 20D"] else "Momentum"
        pieces.append(f"이 표본에서는 {better}의 20영업일 평균 성과가 상대적으로 높았습니다. 평균값은 일부 큰 상승 사례의 영향을 받을 수 있으므로 Median과 MDD도 함께 봐야 합니다.")
    return " ".join(pieces)


def render_calibration(a: dict, symbol: str):
    st.header(f"Entry Calibration · {symbol}")
    st.caption("Point-in-time 재무 데이터 누출을 피하기 위해 V6.0.1 Calibration은 가격 기반 Pullback/Momentum Engine만 검증합니다. 시장 Regime은 중립으로 고정합니다.")
    threshold=st.slider("Signal Threshold · 신호 인정 기준",60,90,75,help="과거 Pullback/Momentum Entry 점수가 이 값 이상인 거래일만 '신호 발생'으로 집계합니다.")
    if threshold<70: mode_txt="넓은 기준 · 신호 수가 많아지지만 약한 Setup도 포함될 수 있습니다."
    elif threshold<80: mode_txt="균형 기준 · 신호 수와 강도의 균형을 보는 구간입니다."
    else: mode_txt="엄격 기준 · 신호 수는 줄지만 강한 Setup만 검증합니다."
    st.markdown(f"<div class='cal-help'><b>현재 {threshold}점 기준</b><br>Entry Score가 <b>{threshold} 이상</b>이었던 과거 날짜만 Calibration 표에 포함합니다. 기준을 낮추면 신호 수가 늘고, 높이면 더 강한 Setup만 남습니다.<br><span class='status-yellow'>{mode_txt}</span></div>",unsafe_allow_html=True)
    with st.expander("Calibration은 무엇을 확인하나요?"):
        st.markdown("Pullback과 Momentum 점수가 특정 기준 이상이었던 과거 날짜를 찾아 그 뒤 **5·10·20·60영업일 수익률**과 **20영업일 최대 낙폭(MDD)**을 계산합니다. 이는 점수 기준을 조정하기 위한 검증 도구이며 미래 수익을 예측하거나 보장하는 확률값이 아닙니다.")
    if st.button("Calibration 실행",type="primary"):
        try:
            with st.spinner("과거 각 거래일의 Setup을 재구성하는 중입니다..."):
                detail,summary=run_setup_calibration(a["frame"],a["benchmark"],float(threshold))
            if summary.empty: st.info("충분한 Calibration 결과가 없습니다.")
            else:
                if not detail.empty: st.caption(f"검증 구간 · {detail['date'].iloc[0]} ~ {detail['date'].iloc[-1]} · Threshold {threshold}")
                shown=summary.rename(columns={"Setup":"Setup","Signals":"일별 신호","Independent":"독립 신호","Hit 20D":"20D 양수 비율","Median 20D":"20D 중앙값","Avg 5D":"평균 5D","Avg 10D":"평균 10D","Avg 20D":"평균 20D","Avg 60D":"평균 60D","Avg MDD20":"평균 MDD20"})
                fmt={"20D 양수 비율":"{:.1f}%","20D 중앙값":"{:+.2f}%","평균 5D":"{:+.2f}%","평균 10D":"{:+.2f}%","평균 20D":"{:+.2f}%","평균 60D":"{:+.2f}%","평균 MDD20":"{:+.2f}%"}
                st.dataframe(shown.style.format(fmt,na_rep="—"),hide_index=True,use_container_width=True)
                st.info("**Calibration 요약** · "+calibration_summary_text(summary,threshold))
                with st.expander("표 읽는 법",expanded=True):
                    st.markdown("""
- **일별 신호**: 점수가 Threshold 이상이었던 거래일 수입니다. 같은 상승 구간에서 여러 날 연속 발생할 수 있습니다.
- **독립 신호**: 연속 신호를 약 5영업일 간격의 하나의 에피소드로 묶은 참고 수입니다.
- **20D 양수 비율**: 신호 발생 20영업일 후 수익률이 플러스였던 비율입니다.
- **20D 중앙값**: 큰 급등 사례의 영향을 줄여 본 대표적인 20영업일 성과입니다.
- **평균 5D / 10D / 20D / 60D**: 신호 이후 각 기간 평균 수익률입니다.
- **평균 MDD20**: 신호 이후 20영업일 동안 겪은 평균 최대 하락폭입니다. 예: -6%면 중간에 평균 약 6%의 최대 낙폭을 경험했다는 뜻입니다.
                    """)
                if (summary["Independent"]<5).any(): st.warning("독립 신호가 5개 미만인 Setup이 있어 표본 신뢰도가 낮을 수 있습니다. Threshold를 낮춰 표본을 늘리거나 더 긴 과거 데이터를 확보해 비교하세요.")
                st.caption("과거 성과가 미래 성과를 보장하지 않습니다. 평균 수익률은 극단적 상승 사례에 민감하므로 중앙값·독립 신호 수·MDD를 함께 확인하세요.")
                with st.expander("Calibration 원자료"):
                    st.dataframe(detail.tail(250),hide_index=True,use_container_width=True)
        except Exception as exc: st.error(f"Calibration 실패: {exc}")


# -------------------- App shell --------------------
st.title("Stock Analyzer by Kijungnam")
st.caption("V6.0.1 · MULTI-LENS SETUP & DECISION SYSTEM · Explainability & UX Restoration")
st.warning("V6는 종목 품질·추세·진입 Setup·Risk를 분리해 해석합니다. V6.0.1은 V5에서 반응이 좋았던 브리핑·퀀트 상세·Market Pulse·10D 변화 표현을 V6 엔진 위에 복원했습니다.")

st.subheader("종목 검색")
query=st.text_input("티커 또는 회사명",placeholder="예: NVDA, Micron, 삼성전자, 005930")
results=search_symbol(query) if query else []
if results:
    labels=[f"{x['name']} · {x['symbol']} · {x.get('exchange','')}" for x in results]
    choice=st.selectbox("검색 후보",labels); selected_symbol=results[labels.index(choice)]["symbol"]
    if st.button("분석 시작",type="primary",use_container_width=True): st.session_state["symbol"]=selected_symbol
symbol=st.session_state.get("symbol","")
if symbol: st.caption(f"현재 선택 종목 · {info(symbol).get('longName') or info(symbol).get('shortName') or symbol} · {symbol}")

with st.expander("🔥 V6 Setup Scanner · 시장 전체 후보 찾기",expanded=False):
    render_scanner_section()

mode=st.radio("개별 분석 메뉴",["📊 종합분석","🎯 퀀트분석","🧩 옵션분석","🌎 시장환경","🧪 Calibration","💾 History"],horizontal=True,label_visibility="collapsed")
st.divider()

analysis=None
if symbol and mode in ("📊 종합분석","🎯 퀀트분석","🧩 옵션분석","🧪 Calibration"):
    try:
        with st.spinner(f"{symbol} · V6.0.1 엔진을 계산하는 중입니다..."): analysis=build_full_analysis(symbol)
    except Exception as exc: st.error(f"분석을 계산하지 못했습니다: {exc}")

if mode=="📊 종합분석":
    if not symbol: st.info("먼저 종목을 검색해 주세요.")
    elif analysis: render_analysis(analysis,symbol)

elif mode=="🎯 퀀트분석":
    if not symbol: st.info("먼저 종목을 검색해 주세요.")
    elif analysis: render_quant_analysis(analysis,symbol)

elif mode=="🧩 옵션분석":
    if not symbol: st.info("먼저 종목을 검색해 주세요.")
    else:
        try:
            from options_analyzer import render_options
            base=analysis or build_full_analysis(symbol)
            support=base["zones"].supports[0].center if base["zones"].supports else None
            resistance=base["zones"].resistances[0].center if base["zones"].resistances else None
            render_options(symbol,base["now"],money,support,resistance)
        except Exception as exc: st.warning(f"옵션분석을 표시할 수 없습니다: {exc}")

elif mode=="🌎 시장환경": render_market_dashboard()

elif mode=="🧪 Calibration":
    if not symbol or not analysis: st.info("먼저 종목을 검색한 뒤 Calibration을 실행해 주세요.")
    else: render_calibration(analysis,symbol)

elif mode=="💾 History":
    st.header("V6 History Database")
    st.caption(f"현재 DB: {DB_FILE}. 로컬/자체 서버에서는 SQLite로 저장됩니다. Streamlit Community Cloud는 재배포 시 로컬 디스크가 초기화될 수 있어 JSON 백업 기능을 함께 제공합니다.")
    st.download_button("전체 History JSON 내보내기",HISTORY.export_json(),"stock_analyzer_v6_history.json","application/json")
    uploaded=st.file_uploader("History JSON 가져오기",type="json")
    if uploaded and st.button("History 가져오기"):
        try: st.success(f"{HISTORY.import_json(uploaded.getvalue())}개 레코드를 가져왔습니다.")
        except Exception as exc: st.error(f"가져오기 실패: {exc}")
    if symbol:
        rows=HISTORY.rows(symbol,100)
        if rows: st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
        else: st.info("현재 선택 종목의 V6 저장 이력이 없습니다.")
