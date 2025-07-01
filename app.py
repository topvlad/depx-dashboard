import streamlit as st
import pandas as pd
import requests, json, os, time
import matplotlib.pyplot as plt
import altair as alt

# --- Config ---
GH_USER, GH_REPO, GH_BRANCH = "topvlad", "market-pulse", "data-history"
DATA_DIR = "data"
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

st.set_page_config(layout="wide", page_title="🚦 Crypto Market Pulse Dashboard")

def spark(data):
    return alt.Chart(pd.DataFrame({'y': data})).mark_line().encode(y='y').properties(height=30, width=100)

def pretty(dtstr):
    return pd.to_datetime(dtstr, format="%Y%m%d_%H%M").strftime("%d %b %H:%M")

# --- 1. List files in /data remotely ---
@st.cache_data(ttl=300)
def get_files():
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{DATA_DIR}?ref={GH_BRANCH}"
    r = requests.get(url, headers=HEADERS); r.raise_for_status()
    return r.json()

files = get_files()
pulse_files = sorted([f for f in files if f['name'].startswith("pulse_") and f['name'].endswith(".json")], key=lambda x: x['name'])
digest_files = sorted([f for f in files if f['name'].startswith("gpt_digest_") and f['name'].endswith(".txt")], key=lambda x: x['name'])
plot_files = sorted([f for f in files if f['name'].endswith(".png")], key=lambda x: x['name'])

if not pulse_files:
    st.error("No pulse_*.json files found."); st.stop()

pulse_dt = [x['name'].replace("pulse_","").replace(".json","") for x in pulse_files]
sel_idx = st.select_slider(
    "Оберіть snapshot:",
    options=list(range(len(pulse_dt))),
    format_func=lambda i: pretty(pulse_dt[i]),
    value=len(pulse_dt)-1
)

# --- Load selected snapshot JSON remotely ---
sel_file = pulse_files[sel_idx]
data = json.loads(requests.get(sel_file['download_url'], headers=HEADERS).text)

assets = {a["symbol"]: a for a in data}
symbols = list(assets.keys())[:4]

# --- Crypto Square Grid ---
st.header("🔲 Crypto Square")
for r in range(2):
    cols = st.columns(2)
    for c in range(2):
        sym = symbols[r*2 + c]
        df = assets[sym]
        ohlcv, oi, fr, liq = map(pd.DataFrame, (df["ohlcv"], df["oi"], df["fr"], df["liq"]))
        cols[c].subheader(sym)

        # OI & FR plot
        if not oi.empty and not fr.empty:
            oi['t']=pd.to_datetime(oi['t'],unit='s'); fr['t']=pd.to_datetime(fr['t'],unit='s')
            fig, ax1 = plt.subplots(figsize=(4,2))
            ax1.plot(oi['t'],oi['c'],color="blue", label="OI")
            ax2=ax1.twinx(); ax2.plot(fr['t'],fr['c'],color="orange", label="Funding")
            ax1.set_ylabel("OI"); ax2.set_ylabel("Funding")
            cols[c].pyplot(fig)

        # Sparkline of Close
        if not ohlcv.empty:
            cols[c].altair_chart(spark(ohlcv['c'].tail(8)), use_container_width=True)

        # Alerts
        alerts = []
        if not oi.empty and not liq.empty and 'l' in liq.columns and 's' in liq.columns:
            liq['total'] = liq['l'].astype(float) + liq['s'].astype(float)
            threshold = liq['total'].mean() + 3 * liq['total'].std()
            spikes = liq[liq['total'] > threshold]
            if not spikes.empty:
                alerts.append(f"⚡ Ліквідації сплеск: {list(spikes['t'])}")
        if not fr.empty and 'c' in fr.columns:
            if fr['c'].abs().max() > 0.01:
                alerts.append(f"⚡ FR extreme ({fr['c'].max():.4f})")
        if alerts:
            for a in alerts: cols[c].warning(a)
        else:
            cols[c].success("No anomalies.")

        # GPT Digest (aggregate last 4 digests for this sym)
        def aggregate_digest(sym, dig_files, idx, n=4):
            picks = dig_files[max(0, idx-n+1):idx+1]
            parts = []
            for dig in picks:
                txt = requests.get(dig['download_url'], headers=HEADERS).text
                start = txt.find(f"=== {sym} ===")
                if start >= 0:
                    end = txt.find("===", start+1)
                    parts.append(txt[start:end].strip() if end>0 else txt[start:].strip())
            return "\n---\n".join(parts)
        dig = aggregate_digest(sym, digest_files, sel_idx)
        cols[c].code(dig if dig else "No GPT digest.")

# --- Merged PNG for snapshot (if present) ---
merged_png = next((f for f in plot_files if f['name']==f"snapshot_{pulse_dt[sel_idx]}.png"), None)
if merged_png:
    st.image(merged_png['download_url'], caption="Overview (merged)")
else:
    st.info("No merged overview image for this snapshot.")

# --- Master Table with Delta ---
st.header("📊 Master table for snapshot")
rows = []
prev = None
if sel_idx > 0:
    prev_file = pulse_files[sel_idx-1]
    prev = json.loads(requests.get(prev_file['download_url'], headers=HEADERS).text)
    prev_map = {a["symbol"]: a for a in prev}
for sym in symbols:
    df = assets[sym]; df_ohl=pd.DataFrame(df['ohlcv'])
    close = df_ohl['c'].iloc[-1] if not df_ohl.empty else None
    prev_close = None
    if prev:
        prev_ohl = pd.DataFrame(prev_map.get(sym, {}).get('ohlcv', []))
        prev_close = prev_ohl['c'].iloc[-1] if not prev_ohl.empty else None
    delta = f"{close-prev_close:+.2f}" if prev_close is not None else ""
    rows.append({"symbol": sym, "close": close, "Δclose": delta})
sty = pd.DataFrame(rows).style.applymap(
    lambda v: "color:green" if isinstance(v,str) and v.startswith("+")
    else ("color:red" if isinstance(v,str) and v.startswith("-") else ""), subset=["Δclose"])
st.dataframe(sty, use_container_width=True)

# --- Alerts Log ---
st.header("🚨 Alert Log")
alert_file = next((f for f in files if f['name']=="oi_fr_alerts.csv"), None)
if alert_file:
    log = pd.read_csv(alert_file['download_url'])
    st.dataframe(log.tail(20), use_container_width=True)
else:
    st.info("No alert log.")

st.info("Dashboard MVP by [your team]. Звʼяжись з @topvlad або @lostframe_404 для вдосконалення/розширення!")
