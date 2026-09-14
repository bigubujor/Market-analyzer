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
    # 1y = bare zilnice, mai multe puncte
    m = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
         "1d": "1day", "1wk": "1week", "1y": "1day"}
    outputsize = 500 if interval == "1y" else 200
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={"symbol": ticker, "interval": m.get(interval, "1day"),
                "outputsize": outputsize, "apikey": key},
        timeout=20
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
    res = {"1m": "1", "5m": "5", "15m": "15", "30m": "30",
           "1d": "D", "1wk": "W", "1y": "D"}.get(interval, "D")
    now = int(datetime.now().timestamp())
    days_map = {"1m": 5, "5m": 15, "15m": 30, "30m": 60, "1d": 365, "1wk": 1825, "1y": 365}
    days = days_map.get(interval, 365)
    r = requests.get(
        "https://finnhub.io/api/v1/stock/candle",
        params={"symbol": ticker, "resolution": res,
                "from": now - days * 86400, "to": now, "token": key},
        timeout=20
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

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    gain = d.clip(lower=0).rolling(n).mean()
    loss = (-d.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def macd(s, fast=12, slow=26, signal=9):
    ef, es = ema(s, fast), ema(s, slow)
    line = ef - es
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist

def bollinger(s, n=20, k=2):
    mid = s.rolling(n).mean()
    std = s.rolling(n).std()
    return mid + k * std, mid, mid - k * std

def stoch(high, low, close, k=14, d=3):
    lowest = low.rolling(k).min()
    highest = high.rolling(k).max()
    k_line = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    d_line = k_line.rolling(d).mean()
    return k_line, d_line

def atr(high, low, close, n=14):
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def fibonacci_levels(df):
    """Swing high/low pe tot setul de date afișat"""
    if df is None or len(df) < 10:
        return {}
    hi = df["High"].max()
    lo = df["Low"].min()
    diff = hi - lo
    return {
        "0% (High)": hi,
        "23.6%": hi - 0.236 * diff,
        "38.2%": hi - 0.382 * diff,
        "50%": hi - 0.5 * diff,
        "61.8%": hi - 0.618 * diff,
        "78.6%": hi - 0.786 * diff,
        "100% (Low)": lo,
    }

def add_indicators(df):
    if df is None or len(df) < 35:
        return df
    df = df.copy()
    df["EMA9"] = ema(df["Close"], 9)
    df["EMA21"] = ema(df["Close"], 21)
    df["EMA50"] = ema(df["Close"], 50)
    df["RSI"] = rsi(df["Close"], 14)
    macd_line, macd_sig, macd_hist = macd(df["Close"])
    df["MACD"] = macd_line
    df["MACD_sig"] = macd_sig
    df["MACD_hist"] = macd_hist
    bb_u, bb_m, bb_l = bollinger(df["Close"])
    df["BB_upper"] = bb_u
    df["BB_mid"] = bb_m
    df["BB_lower"] = bb_l
    k, d = stoch(df["High"], df["Low"], df["Close"])
    df["Stoch_K"] = k
    df["Stoch_D"] = d
    df["ATR"] = atr(df["High"], df["Low"], df["Close"])
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
    macd_h = row.get("MACD_hist")
    if pd.notna(macd_h):
        score += 1 if macd_h > 0 else -1
    stoch_k = row.get("Stoch_K")
    if pd.notna(stoch_k):
        if stoch_k < 20:
            score += 1
            details.append("Stoch oversold")
        elif stoch_k > 80:
            score -= 1
            details.append("Stoch overbought")
    close, bbl, bbu = row.get("Close"), row.get("BB_lower"), row.get("BB_upper")
    if pd.notna(close) and pd.notna(bbl) and close <= bbl:
        score += 1
        details.append("La BB lower")
    if pd.notna(close) and pd.notna(bbu) and close >= bbu:
        score -= 1
        details.append("La BB upper")
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

def entry_exit_levels(df, fib):
    """Propune zone de intrare / ieșire pe baza pretului, ATR, Fib, BB"""
    if df is None or len(df) < 20:
        return {}
    last = df.iloc[-1]
    price = float(last["Close"])
    atr_v = float(last["ATR"]) if pd.notna(last.get("ATR")) else price * 0.02
    bb_l = last.get("BB_lower")
    bb_u = last.get("BB_upper")

    entry_buy = []
    entry_sell = []
    targets = []
    stop_long = price - 1.5 * atr_v
    stop_short = price + 1.5 * atr_v

    # Intrari long: BB lower, Fib 61.8 / 50, -1 ATR
    if pd.notna(bb_l):
        entry_buy.append(("BB Lower", float(bb_l)))
    if fib:
        entry_buy.append(("Fib 61.8%", fib["61.8%"]))
        entry_buy.append(("Fib 50%", fib["50%"]))
    entry_buy.append(("–1 ATR", price - atr_v))

    # Targete long
    if fib:
        targets.append(("Fib 38.2%", fib["38.2%"]))
        targets.append(("Fib 23.6%", fib["23.6%"]))
        targets.append(("Fib 0% (High)", fib["0% (High)"]))
    if pd.notna(bb_u):
        targets.append(("BB Upper", float(bb_u)))
    targets.append(("+1.5 ATR", price + 1.5 * atr_v))
    targets.append(("+2.5 ATR", price + 2.5 * atr_v))

    # Sortare
    entry_buy = sorted(set([(n, round(v, 2)) for n, v in entry_buy if v < price]), key=lambda x: -x[1])
    targets = sorted(set([(n, round(v, 2)) for n, v in targets if v > price]), key=lambda x: x[1])

    return {
        "pret_curent": round(price, 2),
        "atr": round(atr_v, 2),
        "intrari_long": entry_buy[:4],
        "targete_long": targets[:4],
        "stop_long": round(stop_long, 2),
        "stop_short": round(stop_short, 2),
    }

# ====================== UI ======================
st.title("Market Analyzer – Portfolio")
st.caption("15m · 30m · 1zi · 1sapt · 1an | RSI MACD BB Stoch ATR Fib | Entry/Exit")

st.sidebar.header("Setari")
selected = st.sidebar.selectbox("Actiune", list(PORTFOLIO.keys()),
                                format_func=lambda x: f"{x} – {PORTFOLIO[x]}")
interval = st.sidebar.radio(
    "Timeframe",
    ["1m", "5m", "15m", "30m", "1d", "1wk", "1y"],
    index=4,
    format_func=lambda x: {
        "1m": "1 minut", "5m": "5 minute", "15m": "15 minute", "30m": "30 minute",
        "1d": "1 zi", "1wk": "1 saptamana", "1y": "1 an (zilnic)"
    }[x]
)
source = st.sidebar.radio("Sursa", ["twelvedata", "finnhub"],
                          format_func=lambda x: "Twelve Data" if x == "twelvedata" else "Finnhub")
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
    st.caption(f"Sursa: **{used}** | Bare: {len(df)}")
    df = add_indicators(df)
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    sig, score, details = generate_signal(last, prev)
    fib = fibonacci_levels(df)
    levels = entry_exit_levels(df, fib)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Pret", f"{last['Close']:.2f} $")
    c2.metric("RSI", f"{last.get('RSI', 0):.1f}")
    c3.metric("Semnal", sig)
    c4.metric("Scor", score)
    c5.metric("ATR", f"{last.get('ATR', 0):.2f}" if pd.notna(last.get("ATR")) else "-")

    if details:
        st.info(" | ".join(details))

    # Fibonacci
    st.subheader("Fibonacci (swing high/low pe perioada incarcata)")
    fib_cols = st.columns(4)
    items = list(fib.items())
    for i, (name, val) in enumerate(items):
        fib_cols[i % 4].metric(name, f"{val:.2f} $")

    # Entry / Exit
    st.subheader("Puncte propuse Intrare / Iesire")
    if levels:
        st.write(f"**Pret curent:** {levels['pret_curent']} $ | **ATR:** {levels['atr']} $")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Zone INTRARE LONG** (sub pret)")
            for name, val in levels["intrari_long"]:
                st.write(f"- {name}: **{val} $**")
            st.write(f"- Stop loss orientativ: **{levels['stop_long']} $**")
        with col_b:
            st.markdown("**TARGET / IESIRE LONG** (peste pret)")
            for name, val in levels["targete_long"]:
                st.write(f"- {name}: **{val} $**")

    # Tabel
    st.subheader("Ultimele bare + indicatori")
    tail = df.tail(15).copy()
    sigs = []
    for i in range(len(tail)):
        r = tail.iloc[i]
        p = tail.iloc[i - 1] if i > 0 else None
        s, _, _ = generate_signal(r, p)
        sigs.append(s)
    tail["Semnal"] = sigs
    cols = [c for c in ["Close", "RSI", "EMA9", "EMA21", "MACD_hist", "Stoch_K", "ATR", "Semnal"] if c in tail.columns]
    st.dataframe(tail[cols], use_container_width=True)

    st.line_chart(df[["Close"]].tail(80))
else:
    st.info("Introdu API Key in sidebar.")

st.sidebar.caption(f"Actualizat: {datetime.now().strftime('%H:%M:%S')}")
