import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import numpy as np
import requests

st.set_page_config(page_title="Market Analyzer", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.stButton > button { width: 100%; height: 3rem; font-size: 1.1rem; }
@media (max-width: 768px) {
  .block-container { padding-top: 1rem; padding-left: 0.7rem; padding-right: 0.7rem; }
  h1 { font-size: 1.45rem !important; }
}
</style>
""", unsafe_allow_html=True)

PORTFOLIO = {
    "MSFT": "Microsoft", "ORCL": "Oracle", "NOW": "ServiceNow", "INTU": "Intuit",
    "LULU": "Lululemon", "TTD": "Trade Desk", "SPCX": "SpaceX", "OKLO": "Oklo",
    "NVDA": "Nvidia", "HWM": "Howmet", "V": "Visa", "ARGX": "argenx",
    "VRTX": "Vertex", "NXE": "Nexgen Energy"
}

def load_yf(ticker, interval, period):
    try:
        df = yf.download(ticker, interval=interval, period=period, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except Exception as e:
        st.warning(f"yfinance: {e}")
        return None

def load_td(ticker, interval, key):
    m = {"1m":"1min","5m":"5min","1d":"1day","1wk":"1week"}
    url = "https://api.twelvedata.com/time_series"
    r = requests.get(url, params={"symbol":ticker,"interval":m.get(interval,"1day"),"outputsize":300,"apikey":key}, timeout=15)
    data = r.json()
    if "values" not in data:
        st.warning(f"Twelve Data: {data.get('message', data)}")
        return None
    df = pd.DataFrame(data["values"]).rename(columns={"datetime":"Date","open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    for c in ["Open","High","Low","Close","Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna()

def load_fh(ticker, interval, key):
    res = {"1m":"1","5m":"5","1d":"D","1wk":"W"}.get(interval, "D")
    now = int(datetime.now().timestamp())
    frm = now - (5*86400 if interval=="1m" else 30*86400 if interval=="5m" else 365*86400 if interval=="1d" else 5*365*86400)
    r = requests.get("https://finnhub.io/api/v1/stock/candle", params={"symbol":ticker,"resolution":res,"from":frm,"to":now,"token":key}, timeout=15)
    data = r.json()
    if data.get("s") != "ok":
        st.warning(f"Finnhub: {data}")
        return None
    df = pd.DataFrame({"Date": pd.to_datetime(data["t"], unit="s"), "Open": data["o"], "High": data["h"], "Low": data["l"], "Close": data["c"], "Volume": data["v"]})
    return df.set_index("Date").sort_index().dropna()

def load_data(ticker, interval, period, source, key):
    if source == "twelvedata" and key.strip():
        df = load_td(ticker, interval, key.strip())
        if df is not None and not df.empty: return df, "Twelve Data"
    if source == "finnhub" and key.strip():
        df = load_fh(ticker, interval, key.strip())
        if df is not None and not df.empty: return df, "Finnhub"
    df = load_yf(ticker, interval, period)
    return df, "yfinance"

def add_indicators(df):
    if df is None or len(df) < 30: return df
    df = df.copy()
    df["EMA9"] = ta.ema(df["Close"], length=9)
    df["EMA21"] = ta.ema(df["Close"], length=21)
    df["RSI"] = ta.rsi(df["Close"], length=14)
    macd = ta.macd(df["Close"])
    if macd is not None: df = pd.concat([df, macd], axis=1)
    bb = ta.bbands(df["Close"], length=20)
    if bb is not None: df = pd.concat([df, bb], axis=1)
    df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)
    df["Vol_SMA"] = df["Volume"].rolling(20).mean()
    return df
  def generate_signal(row, prev=None):
    score = 0
    details = []
    rsi = row.get("RSI")
    if pd.notna(rsi):
        if rsi < 30: score += 2; details.append("RSI oversold")
        elif rsi < 40: score += 1
        elif rsi > 70: score -= 2; details.append("RSI overbought")
        elif rsi > 60: score -= 1
    ema9, ema21 = row.get("EMA9"), row.get("EMA21")
    if pd.notna(ema9) and pd.notna(ema21):
        score += 1 if ema9 > ema21 else -1
        if prev is not None:
            p9, p21 = prev.get("EMA9"), prev.get("EMA21")
            if pd.notna(p9) and pd.notna(p21):
                if p9 <= p21 and ema9 > ema21: score += 2; details.append("EMA cross up")
                elif p9 >= p21 and ema9 < ema21: score -= 2; details.append("EMA cross down")
    macd_l, macd_s = row.get("MACD_12_26_9"), row.get("MACDs_12_26_9")
    if pd.notna(macd_l) and pd.notna(macd_s):
        score += 1 if macd_l > macd_s else -1
    close, bbl, bbu = row.get("Close"), row.get("BBL_20_2.0"), row.get("BBU_20_2.0")
    if pd.notna(close) and pd.notna(bbl) and pd.notna(bbu):
        if close <= bbl: score += 2; details.append("Lower BB")
        elif close >= bbu: score -= 2; details.append("Upper BB")
    if score >= 4: sig = "🟢 LONG"
    elif score >= 2: sig = "🟢 LONG (slab)"
    elif score <= -4: sig = "🔴 SHORT"
    elif score <= -2: sig = "🔴 SHORT (slab)"
    else: sig = "⚪ NEUTRU"
    return sig, score, details

def plot_chart(df, ticker, interval):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.55, 0.25, 0.2],
                        subplot_titles=(f"{ticker} – {interval}", "RSI", "Volume"))
    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"), row=1, col=1)
    if "EMA9" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA9"], name="EMA9", line=dict(color="orange", width=1)), row=1, col=1)
    if "EMA21" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["EMA21"], name="EMA21", line=dict(color="blue", width=1)), row=1, col=1)
    if "RSI" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI", line=dict(color="lime")), row=2, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    colors = ["red" if c < o else "green" for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=colors, name="Volume"), row=3, col=1)
    fig.update_layout(height=750, xaxis_rangeslider_visible=False, template="plotly_dark", showlegend=True)
    return fig# ====================== UI ======================
st.title("📈 Market Analyzer – Portfolio")
st.caption("1m · 5m · 1zi · 1săpt | yfinance + Twelve Data + Finnhub")

st.sidebar.header("Setări")
selected = st.sidebar.selectbox("Acțiune", list(PORTFOLIO.keys()), format_func=lambda x: f"{x} – {PORTFOLIO[x]}")
interval = st.sidebar.radio("Timeframe", ["1m","5m","1d","1wk"], index=2,
    format_func=lambda x: {"1m":"1 minut","5m":"5 minute","1d":"1 zi","1wk":"1 săptămână"}[x])

period = {"1m":"5d","5m":"1mo","1d":"1y","1wk":"5y"}[interval]

st.sidebar.markdown("---")
source = st.sidebar.radio("Sursă date", ["yfinance","twelvedata","finnhub"],
    format_func=lambda x: {"yfinance":"yfinance (fără key)","twelvedata":"Twelve Data","finnhub":"Finnhub"}[x])

api_key = ""
if source in ["twelvedata","finnhub"]:
    api_key = st.sidebar.text_input(f"{source} API Key", type="password")
    if not api_key:
        st.sidebar.warning("Fără key → se folosește yfinance")

st.sidebar.button("🔄 Refresh", use_container_width=True)

result = load_data(selected, interval, period, source, api_key)
df, used = result if isinstance(result, tuple) else (result, "unknown")

if df is not None and hasattr(df, "empty") and not df.empty:
    st.caption(f"Sursă: **{used}**")
    df = add_indicators(df)
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    sig, score, details = generate_signal(last, prev)

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Preț", f"{last['Close']:.2f} $")
    c2.metric("RSI", f"{last.get('RSI',0):.1f}")
    c3.metric("Semnal", sig)
    c4.metric("Scor", score)

    if details:
        st.info(" | ".join(details))

    fig = plot_chart(df, selected, interval)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Ultimele bare")
    tail = df.tail(12).copy()
    sigs = []
    for i in range(len(tail)):
        r = tail.iloc[i]
        p = tail.iloc[i-1] if i > 0 else None
        s,_,_ = generate_signal(r, p)
        sigs.append(s)
    tail["Semnal"] = sigs
    cols = [c for c in ["Close","RSI","EMA9","EMA21","Semnal"] if c in tail.columns]
    st.dataframe(tail[cols].style.format({"Close":"{:.2f}","RSI":"{:.1f}","EMA9":"{:.2f}","EMA21":"{:.2f}"}, na_rep="-"))
else:
    st.warning("Nu am putut încărca datele. Încearcă altă sursă sau ticker.")

st.sidebar.caption(f"Actualizat: {datetime.now().strftime('%H:%M:%S')}")
