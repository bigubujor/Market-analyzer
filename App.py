import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import requests

st.set_page_config(page_title="Market Analyzer", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

PORTFOLIO = {
    "MSFT": "Microsoft", "ORCL": "Oracle", "NOW": "ServiceNow", "INTU": "Intuit",
    "LULU": "Lululemon", "TTD": "Trade Desk", "SPCX": "SpaceX", "OKLO": "Oklo",
    "NVDA": "Nvidia", "HWM": "Howmet", "V": "Visa", "ARGX": "argenx",
    "VRTX": "Vertex", "NXE": "Nexgen Energy"
}

def load_td(ticker, interval, key):
    m = {"1m": "1min", "5m": "5min", "1d": "1day", "1wk": "1week"}
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={"symbol": ticker, "interval": m.get(interval, "1day"), "outputsize": 200, "apikey": key},
        timeout=15
    )
    data = r.json()
    if "values" not in data:
        st.warning(f"Twelve Data: {data.get('message', data)}")
        return None
    df = pd.DataFrame(data["values"])
    df = df.rename(columns={
        "datetime": "Date", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume"
    })
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna()

def load_fh(ticker, interval, key):
    res = {"1m": "1", "5m": "5", "1d": "D", "1wk": "W"}.get(interval, "D")
    now = int(datetime.now().timestamp())
    days = 5 if interval == "1m" else 30 if interval == "5m" else 365 if interval == "1d" else 1825
    r = requests.get(
        "https://finnhub.io/api/v1/stock/candle",
        params={"symbol": ticker, "resolution": res, "from": now - days * 86400, "to": now, "token": key},
        timeout=15
    )
    data = r.json()
    if data.get("s") != "ok":
        st.warning(f"Finnhub: {data}")
        return None
    df = pd.DataFrame({
        "Date": pd.to_datetime(data["t"], unit="s"),
        "Open": data["o"], "High": data["h"], "Low": data["l"],
        "Close": data["c"], "Volume": data["v"]
    })
    return df.set_index("Date").sort_index().dropna()

def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def rsi(series, length=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(length).mean()
    loss = (-delta.clip(upper=0)).rolling(length).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def add_indicators(df):
    if df is None or len(df) < 30:
        return df
    df = df.copy()
    df["EMA9"] = ema(df["Close"], 9)
    df["EMA21"] = ema(df["Close"], 21)
    df["RSI"] = rsi(df["Close"], 14)
    return df

def generate_signal(row, prev=None):
    score = 0
    details = []
    rsi_v = row.get("RSI")
    if pd.notna(rsi_v):
        if rsi_v < 30:
            score += 2
            details.append("RSI oversold")
        elif rsi_v < 40:
            score += 1
        elif rsi_v > 70:
            score -= 2
            details.append("RSI overbought")
        elif rsi_v > 60:
            score -= 1
    e9, e21 = row.get("EMA9"), row.get("EMA21")
    if pd.notna(e9) and pd.notna(e21):
        score += 1 if e9 > e21 else -1
        if prev is not None:
            p9, p21 = prev.get("EMA9"), prev.get("EMA21")
            if pd.notna(p9) and pd.notna(p21):
                if p9 <= p21 and e9 > e21:
                    score += 2
                    details.append("EMA cross up")
                elif p9 >= p21 and e9 < e21:
                    score -= 2
                    details.append("EMA cross down")
    if score >= 4:
        sig = "LONG"
    elif score >= 2:
        sig = "LONG (slab)"
    elif score <= -4:
        sig = "SHORT"
    elif score <= -2:
        sig = "SHORT (slab)"
    else:
        sig = "NEUTRU"
    return sig, score, details

st.title("Market Analyzer – Portfolio")
st.caption("Twelve Data + Finnhub | Fara grafice")

st.sidebar.header("Setari")
selected = st.sidebar.selectbox(
    "Actiune",
    list(PORTFOLIO.keys()),
    format_func=lambda x: f"{x} – {PORTFOLIO[x]}"
)
interval = st.sidebar.radio(
    "Timeframe",
    ["1m", "5m", "1d", "1wk"],
    index=2,
    format_func=lambda x: {"1m": "1 minut", "5m": "5 minute", "1d": "1 zi", "1wk": "1 saptamana"}[x]
)
source = st.sidebar.radio(
    "Sursa date",
    ["twelvedata", "finnhub"],
    format_func=lambda x: "Twelve Data" if x == "twelvedata" else "Finnhub"
)
api_key = st.sidebar.text_input("API Key", type="password")
if not api_key:
    st.sidebar.warning("Introdu API Key")

st.sidebar.button("Refresh", use_container_width=True)

df = None
used = "-"
if api_key and api_key.strip():
    if source == "twelvedata":
        df = load_td(selected, interval, api_key.strip())
        used = "Twelve Data"
    else:
        df = load_fh(selected, interval, api_key.strip())
        used = "Finnhub"

if df is not None and not df.empty:
    st.caption(f"Sursa: **{used}**")
    df = add_indicators(df)
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    sig, score, details = generate_signal(last, prev)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pret", f"{last['Close']:.2f} $")
    c2.metric("RSI", f"{last.get('RSI', 0):.1f}")
    c3.metric("Semnal", sig)
    c4.metric("Scor", score)

    if details:
        st.info(" | ".join(details))

    st.subheader("Ultimele 15 bare")
    tail = df.tail(15).copy()
    sigs = []
    for i in range(len(tail)):
        r = tail.iloc[i]
        p = tail.iloc[i - 1] if i > 0 else None
        s, _, _ = generate_signal(r, p)
        sigs.append(s)
    tail["Semnal"] = sigs
    cols = [c for c in ["Close", "RSI", "EMA9", "EMA21", "Volume", "Semnal"] if c in tail.columns]
    st.dataframe(tail[cols], use_container_width=True)

    st.line_chart(df[["Close"]].tail(60))
else:
    st.info("Introdu un API Key (Twelve Data sau Finnhub) in sidebar.")

st.sidebar.caption(f"Actualizat: {datetime.now().strftime('%H:%M:%S')}")
