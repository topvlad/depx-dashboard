import streamlit as st
import pandas as pd
import requests, json, glob, os, time
import matplotlib.pyplot as plt
import altair as alt

from PIL import Image

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

def aggregate_digest(sym, files, idx, n=4):
    picks = files[max(0, idx-n+1):idx+1]
    parts = []
    for fn in picks:
        try:
            block = open(fn, encoding="utf-8").read()
            start = block.find(f"=== {sym} ===")
            if start >= 0:
                end = block.find("===", start+1)
                parts.append(block[start:end].strip() if end>0 else block[start:].strip())
        except Exception:
            continue
    return "\n---\n".join(parts)

# --- GitHub Data Fetching ---
@st.cache_data(ttl=300)
def get_files():
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{DATA_DIR}?ref={GH_BRANCH}"
    r = requests.get(url, headers=HEADERS); r.raise_for_status()
    return r.json()

files = get_files()
pulse_files = sorted([f['name'] for f in files if f['name'].startswith("pulse_")])
if not pulse_files:
    st.error("No pulse_*.json files found."); st.stop()

pulse_dt = [x.replace("pulse_","").replace(".json","") for x in pulse_files]
sel_idx = st.select_slider(
    "Select snapshot:",
    options=list(range(len(pulse_dt))),
    format_func=lambda i: pretty(pulse_dt[i]),
    value=len(pulse_dt)-1
)

# Load data
sel_file = pulse_files[sel_idx]
sel_info = next(f for f in files if f['name']==sel_file)
pulse = json.loads(requests.get(sel_info['download_url'], headers=HEADERS).text)

# Load digest files (local, in public repo's data/)
digest_files = sorted(glob.glob(f"{DATA_DIR}/gpt_digest_*.txt"))

# Prepare assets
assets = {a["symbol"]: a for a in pulse}

# --- Get top_symbols from exported ranking (preferred), else by OI ---
top_assets_file = f"{DATA_DIR}/top_assets.json"
try:
    with open(top_assets_file) as f:
        symbols = json.load(f)
except Exception:
    # fallback: rank by OI
    def rank_symbols(assets, by='oi', col='c', n=4):
        ranked = []
        for sym, tab in assets.items():
            df = pd.DataFrame(tab.get(by, []))
            if not df.empty and col in df.columns:
                val = df[col].iloc[-1]
            else:
                val = -float('inf')
            ranked.append((sym, val))
        return [x[0] for x in sorted(ranked, key=lambda x: -abs(x[1])) if x[1] != -float('inf')][:n]
    symbols = rank_symbols(assets)

symbols = symbols[:4]  # Only top 4

# --- Replay button ---
if st.button("▶️ Replay last 4 snapshots"):
    for idx in range(max(0, len(pulse_dt)-4), len(pulse_dt)):
        st.write(f"## Snapshot: {pretty(pulse_dt[idx])}")
        gif_path = f"{DATA_DIR}/plots/snapshot_{pulse_dt[idx]}.png"
        if os.path.isfile(gif_path):
            st.image(gif_path, caption="Overview")
        else:
            st.info(f"No PNG for snapshot {pretty(pulse_dt[idx])}")
        time.sleep(1)
    st.stop()

st.title("🚦 Crypto Market Pulse Dashboard")
st.write("Live & historical analytics from Coinalyze, GPT digests, and technicals for your main marketmakers.")

# --- Crypto Square Grid ---
st.header("🔲 Crypto Square")
for r in range(2):
    cols = st.columns(2)
    for c in range(2):
        if r*2 + c >= len(symbols): continue
        sym = symbols[r*2+c]
        df = assets.get(sym)
        if not df:
            cols[c].warning(f"No data for {sym}")
            continue
        ohlcv, oi, fr, liq = map(pd.DataFrame, (df["ohlcv"], df["oi"], df["fr"], df["liq"]))
        cols[c].subheader(sym)

        # OI & FR plot
        if not oi.empty and not fr.empty:
            oi['t']=pd.to_datetime(oi['t'],unit='s'); fr['t']=pd.to_datetime(fr['t'],unit='s')
            fig, ax1 = plt.subplots(figsize=(4,2))
            ax1.plot(oi['t'],oi['c'],color="blue"); ax2=ax1.twinx(); ax2.plot(fr['t'],fr['c'],color="orange")
            cols[c].pyplot(fig)

        # Sparkline for recent prices
        if not ohlcv.empty and 'c' in ohlcv.columns:
            cols[c].altair_chart(spark(ohlcv['c'].tail(8)), use_container_width=True)

        # GPT digest (aggregated last 4)
        dig = aggregate_digest(sym, digest_files, sel_idx)
        cols[c].code(dig if dig else "No GPT digest.")

# --- Animated GIF (if present) ---
gif_path = f"{DATA_DIR}/plots/square_latest.gif"
if os.path.isfile(gif_path):
    st.image(gif_path, caption="Crypto Market Square (Animated)")
else:
    st.info("No animation found yet.")

# --- Master table with delta ---
st.header("📊 Summary")
rows = []
prev = None
if sel_idx > 0:
    prev_file = pulse_files[sel_idx-1]
    prev_info = next(f for f in files if f['name']==prev_file)
    prev = json.loads(requests.get(prev_info['download_url'], headers=HEADERS).text)
    prev_map = {a["symbol"]: a for a in prev}
for sym in symbols:
    df = assets[sym]; df_ohl=pd.DataFrame(df['ohlcv'])
    close = df_ohl['c'].iloc[-1] if not df_ohl.empty else None
    prev_close = None
    if prev:
        prev_df = prev_map.get(sym, {}).get('ohlcv', [{}])
        prev_close = prev_df[-1]['c'] if prev_df and isinstance(prev_df, list) and 'c' in prev_df[-1] else None
    delta = f"{close-prev_close:+.2f}" if close is not None and prev_close is not None else ""
    rows.append({"symbol": sym, "close": close, "Δclose": delta})
sty = pd.DataFrame(rows).style.applymap(
    lambda v: "color:green" if isinstance(v, str) and v.startswith("+") else ("color:red" if isinstance(v, str) and v.startswith("-") else ""),
    subset=["Δclose"])
st.dataframe(sty, use_container_width=True)

# --- Alerts ---
st.header("🚨 Alert Log")
try:
    log_url = next(f['download_url'] for f in files if f['name'] == "oi_fr_alerts.csv")
    log = pd.read_csv(log_url)
    st.dataframe(log.tail(20), use_container_width=True)
except Exception:
    st.info("No alert log.")

st.info("Dashboard MVP by [your team]. Contact @topvlad / @lostframe_404 to collaborate.")
