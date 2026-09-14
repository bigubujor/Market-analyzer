import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
    r = requests.get("https://api.twelvedata.com/time_series",
        params={"symbol": ticker, "interval": m.get(interval, "1day"),
                "outputsize": 300, "apikey": key}, timeout=15)
    data = r.json()
    if "values" not in data:
        st.warning(f"Twelve Data: {data.get('message', data)}")
        return None
    df = pd.DataFrame(data["values"])
    df = df.rename(columns={"datetime": "Date", "open": "Open", "high": "High",
                            "low": "Low", "close": "Close", "volume": "Volume"})
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna()

def load_fh(ticker, interval, key):
    res = {"1m": "1", "5m": "5", "1d": "D", "1wk": "W"}.get(interval, "D")
    now = int(datetime.now().timestamp())
    days = 5 if interval == "1m" else 30 if interval == "5m" else 365 if interval == "1d" else 1825
    r = requests.get("https://finnhub.io/api/v1/stock/candle",
        params={"symbol": ticker, "resolution": res, "from": now - days*86400,
                "to": now, "token": key}, timeout=15)
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
        if rsi_v < 30: score += 2; details.append("RSI oversold")
        elif rsi_v < 40: score += 1
        elif rsi_v > 70: score -= 2; details.append("RSI overbought")
        elif rsi_v > 60: score -= 1
    e9, e21 = row.get("EMA9"), row.get("EMA21")
    if pd.notna(e9) and pd.notna(e21):
        score += 1 if e9 > e21 else -1
        if prev is not None:
            p9, p21 = prev.get("EMA9"), prev.get("EMA21")
            if pd.notna(p9) and pd.notna(p21):
                if p9 <= p21 and e9 > e21: score += 2; details.append("EMA cross up")
                elif p9 >= p21 and e9 < e21: score -= 2; details.append("EMA cross down")
    if score >= 4: sig = "🟢 LONG"
    elif score >= 2: sig = "🟢 LONG (slab)"
    elif score <= -4: sig = "🔴 SHORT"
    elif score <= -2: sig = "🔴 SHORT (slab)"
    else: sig = "⚪ NEUTRU"
    return sig, score, details

def plot_chart(df, ticker, interval):
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.55, 0.25, 0.2],
        subplot_titles=(f"{ticker} – {interval}", "RSI", "Volume")
    )
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price"
        ),
        row=1, col=1
    )
    if "EMA9" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["EMA9"], name="EMA9", line=dict(color="orange", width=1)),
            row=1, col=1
        )
    if "EMA21" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["EMA21"], name="EMA21", line=dict(color="blue", width=1)),
            row=1, col=1
        )
    if "RSI" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["RSI"], name="RSI", line=dict(color="lime")),
            row=2, col=1
        )
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    colors = ["red" if c < o else "green" for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(
        go.Bar(x=df.index, y=df["Volume"], marker_color=colors, name="Volume"),
        row=3, col=1
    )
    fig.update_layout(
        height=750,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        showlegend=True
    )
    return fig 
