XTB MASTER SCANNER V3.4 WEB
===========================

CE ESTE
-------
Aplicație web responsive care rulează în browser și păstrează cheia Twelve Data
pe server, nu în JavaScript.

FUNCȚII
-------
- Dashboard Portfolio Decision Engine
- Refresh Twelve Data din browser
- OHLCV daily
- SMA20 / SMA50 / SMA200
- RSI14
- MACD / Signal / Histogram
- ATR14 / ATR%
- Volume / Avg20 / Volume Ratio
- Earnings calendar
- Data-quality validation per ticker
- IUHC exact: LSE / USD / RIC IUHC.L / ISIN IE00B43HR379
- Allocation drift pentru Stock Plan
- V3.4 role overrides: MSFT/NOW/ORCL/SPCX/INTU/LULU/TTD/OKLO

WINDOWS
-------
1. Dezarhivează.
2. Rulează run_web_windows.bat.
3. Deschide http://127.0.0.1:8080

ANDROID / TERMUX
----------------
1. Instalează Termux.
2. termux-setup-storage
3. Dezarhivează folderul în Downloads.
4. În Termux:
   cd ~/storage/downloads/XTB_V3_4_WEB
   chmod +x run_web_android.sh
   ./run_web_android.sh
5. În browser deschide:
   http://127.0.0.1:8080

MAC/LINUX
---------
chmod +x run_web_linux.sh
./run_web_linux.sh
Deschide http://127.0.0.1:8080

DEPLOY WEB PUBLIC/PRIVATE
------------------------
Pachetul conține Procfile și render.yaml.
Pe Render/Railway/Fly/etc. setează TWELVE_DATA_API_KEY ca variabilă de mediu.
NU urca fișierul .env într-un repository public.

SECURITATE
----------
- .env conține cheia în pachetul PRIVATE.
- Pachetul SAFE nu conține .env.
- Cheia nu este trimisă către browser; apelurile API se fac server-side.
- Pentru un site public recomand autentificare înainte de expunerea dashboard-ului.

NOTĂ
----
Aplicația este suport decizional. Nu plasează ordine.
