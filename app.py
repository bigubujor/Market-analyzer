from flask import Flask, jsonify, render_template, request
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime
import json, os, math

BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / "v34_web_cache.json"
STATE_FILE = BASE_DIR / "portfolio_state.json"
ENV_FILE = BASE_DIR / ".env"

def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k,v=line.split("=",1)
            os.environ.setdefault(k.strip(), v.strip())

load_env()
API_KEY = os.environ.get("TWELVE_DATA_API_KEY","")

app = Flask(__name__)

SYMBOLS = {
 "MSFT":{"exchange":"NASDAQ","type":"Common Stock","currency":"USD"},
 "NOW":{"exchange":"NYSE","type":"Common Stock","currency":"USD"},
 "ORCL":{"exchange":"NYSE","type":"Common Stock","currency":"USD"},
 "SPCX":{"exchange":"","type":"Common Stock","currency":"USD"},
 "INTU":{"exchange":"NASDAQ","type":"Common Stock","currency":"USD"},
 "LULU":{"exchange":"NASDAQ","type":"Common Stock","currency":"USD"},
 "TTD":{"exchange":"NASDAQ","type":"Common Stock","currency":"USD"},
 "OKLO":{"exchange":"NYSE","type":"Common Stock","currency":"USD"},
 "HWM":{"exchange":"NYSE","type":"Common Stock","currency":"USD"},
 "NVDA":{"exchange":"NASDAQ","type":"Common Stock","currency":"USD"},
 "V":{"exchange":"NYSE","type":"Common Stock","currency":"USD"},
 "VRTX":{"exchange":"NASDAQ","type":"Common Stock","currency":"USD"},
 "ARGX":{"exchange":"NASDAQ","type":"American Depositary Receipt","currency":"USD"},
 "NXE":{"exchange":"NYSE","type":"Common Stock","currency":"USD"},
 "IUHC":{"exchange":"LSE","type":"ETF","currency":"USD","ric":"IUHC.L","isin":"IE00B43HR379"},
}

def get_json(path, params):
    if not API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY is not configured")
    q=dict(params)
    q["apikey"]=API_KEY
    url="https://api.twelvedata.com"+path+"?"+urlencode({k:v for k,v in q.items() if v not in ("",None)})
    with urlopen(url, timeout=25) as r:
        data=json.loads(r.read().decode("utf-8"))
    if isinstance(data,dict) and data.get("status")=="error":
        raise RuntimeError(data.get("message") or str(data))
    return data

def sma(xs,n):
    return sum(xs[-n:])/n if len(xs)>=n else None

def ema_series(xs,n):
    if len(xs)<n: return []
    k=2/(n+1)
    out=[sum(xs[:n])/n]
    for x in xs[n:]:
        out.append(x*k+out[-1]*(1-k))
    return out

def rsi14(closes):
    if len(closes)<15: return None
    gains=[]; losses=[]
    for a,b in zip(closes[-15:-1],closes[-14:]):
        d=b-a
        gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains)/14; al=sum(losses)/14
    if al==0: return 100.0
    return 100-(100/(1+ag/al))

def macd(closes):
    if len(closes)<35: return (None,None,None)
    e12=ema_series(closes,12); e26=ema_series(closes,26)
    n=min(len(e12),len(e26))
    line=[a-b for a,b in zip(e12[-n:],e26[-n:])]
    sig=ema_series(line,9)
    return (line[-1], sig[-1] if sig else None, line[-1]-sig[-1] if sig else None)

def atr14(highs,lows,closes):
    if len(closes)<15: return None
    trs=[]
    for i in range(1,len(closes)):
        trs.append(max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1])))
    return sum(trs[-14:])/14 if len(trs)>=14 else None

def trend_score(price,s20,s50,s200):
    if None in (price,s20,s50,s200): return 0
    if price>s20>s50>s200: return 25
    if price>s50 and price>s200: return 20
    if price>s20 and price>s50 and price<s200: return 15
    if price>s20: return 8
    return 0

def momentum_score(rsi,macd_v):
    if rsi is None or macd_v is None: return 0
    if rsi>=55 and macd_v>0: return 20
    if rsi>=50 and macd_v>0: return 16
    if rsi>=45 and macd_v>=0: return 12
    if rsi>=40 and macd_v<0: return 6
    return 0

def volume_score(ratio):
    if ratio is None: return 0
    if ratio>=1.5: return 10
    if ratio>=1.2: return 8
    if ratio>=1.0: return 6
    if ratio>=0.8: return 4
    return 2

def fetch_symbol(symbol,cfg):
    params={"symbol":symbol,"interval":"1day","outputsize":260,"format":"JSON"}
    if cfg.get("exchange"): params["exchange"]=cfg["exchange"]
    data=get_json("/time_series",params)
    meta=data.get("meta",{})
    vals=list(reversed(data.get("values",[])))
    if len(vals)<20:
        raise RuntimeError(f"insufficient bars: {len(vals)}")
    closes=[float(x["close"]) for x in vals]
    highs=[float(x["high"]) for x in vals]
    lows=[float(x["low"]) for x in vals]
    vols=[float(x.get("volume") or 0) for x in vals]
    m,ms,mh=macd(closes); atr=atr14(highs,lows,closes)
    latest=vals[-1]
    avgv=sum(vols[-20:])/20 if len(vols)>=20 else None
    ex=(meta.get("exchange") or "").upper()
    cur=(meta.get("currency") or "").upper()
    quality="OK"; notes=[]
    expected=(cfg.get("exchange") or "").upper()
    if expected and expected not in ex:
        quality="CONFLICT"; notes.append(f"exchange {ex or '?'} != {expected}")
    if cfg.get("currency") and cur and cur!=cfg["currency"]:
        quality="CONFLICT"; notes.append(f"currency {cur} != {cfg['currency']}")
    price=closes[-1]
    s20,s50,s200=sma(closes,20),sma(closes,50),sma(closes,200)
    rsi=rsi14(closes)
    vr=(vols[-1]/avgv) if avgv else None
    return {
      "ticker":symbol,"as_of":latest["datetime"],"price":price,
      "sma20":s20,"sma50":s50,"sma200":s200,
      "rsi14":rsi,"macd":m,"macd_signal":ms,"macd_hist":mh,
      "atr14":atr,"atr_pct":(atr/price if atr else None),
      "volume":vols[-1],"avg20_volume":avgv,"volume_ratio":vr,
      "trend":trend_score(price,s20,s50,s200),
      "momentum":momentum_score(rsi,m),
      "volume_score":volume_score(vr),
      "overextended": bool((rsi is not None and rsi>=70) or (s20 and price/s20-1>=0.08)),
      "quality":quality,"notes":"; ".join(notes),
      "meta":meta
    }

def fetch_earnings():
    wanted=set(SYMBOLS)-{"IUHC"}
    out={k:[] for k in wanted}
    today=date.today()
    for offset in range(0,120,30):
        start=today+timedelta(days=offset)
        end=start+timedelta(days=29)
        data=get_json("/earnings_calendar",{"start_date":start.isoformat(),"end_date":end.isoformat(),"format":"JSON"})
        rows=[]
        if isinstance(data,dict):
            rows=data.get("earnings") or data.get("data") or []
        if isinstance(rows,list):
            for row in rows:
                sym=(row.get("symbol") or "").upper()
                if sym in out:
                    out[sym].append(row)
    return out

def allocation_decision(ticker, state, md):
    # Current Stock Plan weights and targets are kept in state.
    cur=state.get("stock_plan_weight")
    target=state.get("target_stock_plan_weight")
    if cur is None or target is None:
        return None
    gap=target-cur
    if gap>0.05: drift=1.2
    elif gap>0.025: drift=1.1
    elif gap<-0.05: drift=0.0
    elif gap<-0.025: drift=0.5
    else: drift=1.0

    q=md.get("quality")
    if ticker=="IUHC" and cur>target+0.05:
        tech=0.0
    elif q!="OK":
        tech=0.75
    elif md.get("overextended"):
        tech=0.75
    elif md.get("trend",0)>=20 and md.get("momentum",0)>=16:
        tech=1.15
    elif md.get("trend",0)>=15 and md.get("momentum",0)>=12:
        tech=1.0
    elif md.get("trend",0)>=8:
        tech=0.75
    else:
        tech=0.5

    mult=drift*tech
    base=525*target
    amount=base*mult
    if mult==0: decision="PAUSE NEW DCA"
    elif mult>=1.15: decision="ABOVE-BASE DCA"
    elif mult>=0.8: decision="BASE DCA"
    elif mult>=0.5: decision="REDUCED DCA"
    else: decision="MINIMAL DCA"
    return {"decision":decision,"suggested_usd":round(amount,2),"multiplier":round(mult,2),"gap":gap}

def role_decision(ticker, state, md):
    p=md.get("price") or state.get("price")
    q=md.get("quality")
    if ticker=="MSFT":
        return "TP REVIEW" if p>=550 else ("HOLD" if q=="OK" else "HOLD / REFRESH DATA")
    if ticker=="NOW":
        return "TP REVIEW" if p>=200 else ("HOLD" if q=="OK" else "HOLD / REFRESH DATA")
    if ticker=="ORCL":
        if q!="OK": return "HOLD CURRENT / REFRESH"
        return "OPTIONAL NEW LOT REVIEW" if 140<=p<=145 else "HOLD CURRENT LOT"
    if ticker=="SPCX":
        return "PARTIAL TP REVIEW" if p>=160 else ("HOLD" if q=="OK" else "HOLD / REFRESH DATA")
    if ticker=="INTU":
        if q!="OK": return "WAIT / REFRESH"
        if 300<=p<=305 or 285<=p<=290: return "RECOVERY ZONE — SET INVALIDATION/RR"
        return "WAIT"
    if ticker=="LULU":
        if p>=140: return "RECOVERY EXIT 2"
        if p>=120: return "RECOVERY EXIT 1"
        return "HOLD / TIME-STOP REVIEW"
    if ticker=="TTD":
        if p>=22: return "RECOVERY EXIT 2"
        if p>=20: return "RECOVERY EXIT 1"
        return "HOLD / TIME-STOP REVIEW"
    if ticker=="OKLO":
        if q!="OK": return "WAIT / REFRESH"
        if 33<=p<=35: return "SMALL LIMIT BUY REVIEW — SET INVALIDATION/RR"
        return "WAIT / NO CHASE"
    return None

def build_decisions(state, market):
    result={}
    for t,st in state["tickers"].items():
        md=market.get(t,{})
        alloc=allocation_decision(t,st,md)
        if alloc:
            decision=alloc["decision"]; size=alloc["suggested_usd"]
        else:
            decision=role_decision(t,st,md); size=None
        result[t]={
            "decision":decision,
            "suggested_usd":size,
            "role":st.get("role"),
            "direct_exposure":st.get("direct_exposure"),
            "price":md.get("price",st.get("price")),
            "quality":md.get("quality","NO LIVE DATA"),
            "trend":md.get("trend"),
            "momentum":md.get("momentum"),
            "volume_ratio":md.get("volume_ratio"),
            "overextended":md.get("overextended"),
            "context":st.get("context",""),
        }
    return result

def read_state():
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))

def read_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {"generated_at":None,"market":{},"earnings":{},"errors":{}}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def status():
    cache=read_cache()
    return jsonify({
        "api_configured":bool(API_KEY),
        "cache_generated_at":cache.get("generated_at"),
        "symbols":len(SYMBOLS),
        "iuHC":{"ticker":"IUHC","exchange":"LSE","currency":"USD","ric":"IUHC.L","isin":"IE00B43HR379"}
    })

@app.route("/api/data")
def data():
    state=read_state()
    cache=read_cache()
    return jsonify({
        "state":state,
        "market":cache.get("market",{}),
        "earnings":cache.get("earnings",{}),
        "errors":cache.get("errors",{}),
        "generated_at":cache.get("generated_at"),
        "decisions":build_decisions(state,cache.get("market",{}))
    })

@app.route("/api/refresh", methods=["POST"])
def refresh():
    state=read_state()
    market={}; errors={}
    workers=min(6,len(SYMBOLS))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs={pool.submit(fetch_symbol,t,cfg):t for t,cfg in SYMBOLS.items()}
        for fut in as_completed(futs):
            t=futs[fut]
            try:
                market[t]=fut.result()
            except Exception as e:
                errors[t]=str(e)
                market[t]={"ticker":t,"quality":"ERROR","notes":str(e)}
    try:
        earnings=fetch_earnings()
    except Exception as e:
        earnings={}
        errors["earnings_calendar"]=str(e)

    cache={
        "generated_at":datetime.now().isoformat(timespec="seconds"),
        "market":market,"earnings":earnings,"errors":errors
    }
    CACHE_FILE.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding="utf-8")
    return jsonify({
        **cache,
        "decisions":build_decisions(state,market)
    })

@app.route("/health")
def health():
    return jsonify({"ok":True,"api_configured":bool(API_KEY)})

if __name__=="__main__":
    host=os.environ.get("HOST","0.0.0.0")
    port=int(os.environ.get("PORT","8080"))
    app.run(host=host,port=port,debug=False)
