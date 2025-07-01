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

# --- Widgets & Helpers ---
def spark(data):
    return alt.Chart(pd.DataFrame({'y': data})).mark_line().encode(y='y').properties(height=30, width=100)

def pretty(dtstr):
    return pd.to_datetime(dtstr, format="%Y%m%d_%H%M").strftime("%d %b %H:%M")

def combine_pngs(symbols, out_file):
    imgs = [Image.open(f"{DATA_DIR}/plots/{sym}_trend.png") if os.path.isfile(f"{DATA_DIR}/plots/{sym}_trend.png")
            else Image.new('RGB',(400,200),(240,240,240)) for sym in symbols[:4]]
    w,h = imgs[0].size
    grid = Image.new('RGB',(2*w,2*h),(255,255,255))
    for idx, img in enumerate(imgs[:4]):
        grid.paste(img, ((idx%2)*w, (idx//2)*h))
    grid.save(out_file)

def aggregate_digest(sym, files, idx, n=4):
    picks = files[max(0, idx-n+1):idx+1]
    parts = []
    for fn in picks:
        block = open(fn, encoding="utf-8").read()
        start = block.find(f"=== {sym} ===")
        if start >= 0:
            end = block.find("===", start+1)
            parts.append(block[start:end].strip() if end>0 else block[start:].strip())
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
sel_idx = st.select_slider("Escolha snapshot:", options=list(range(len(pulse_dt))), format_func=lambda i: pretty(pulse_dt[i]), value=len(pulse_dt)-1)

# Load data & digest files
pulse = json.loads(requests.get(next(f['download_url'] for f in files if f['name']==pulse_files[sel_idx]), headers=HEADERS).text)
digest_files = sorted(glob.glob(f"{DATA_DIR}/gpt_digest_*.txt"))

# Prepare assets
assets = {a["symbol"]: a for a in pulse}
symbols = list(assets.keys())[:4]

# --- Replay button ---
if st.button("▶️ Replay last 4 snapshots"):
    for idx in range(max(0,len(pulse_dt)-4), len(pulse_dt)):
        st.write(f"## Snapshot: {pretty(pulse_dt[idx])}")
        st.image(f"{DATA_DIR}/plots/snapshot_{pulse_dt[idx]}.png", caption="Overview")
        time.sleep(1)
    st.stop()

# --- Crypto Square Grid ---
st.header("🔲 Crypto Square")
for r in range(2):
    cols = st.columns(2)
    for c in range(2):
        sym = symbols[r*2+c]
        df = assets[sym]
        ohlcv, oi, fr, liq = map(pd.DataFrame, (df["ohlcv"], df["oi"], df["fr"], df["liq"]))
        cols[c].subheader(sym)

        # OI & FR plot
        if not oi.empty and not fr.empty:
            oi['t']=pd.to_datetime(oi['t'],unit='s'); fr['t']=pd.to_datetime(fr['t'],unit='s')
            fig, ax1 = plt.subplots(figsize=(4,2))
            ax1.plot(oi['t'],oi['c'],color="blue"); ax2=ax1.twinx(); ax2.plot(fr['t'],fr['c'],color="orange")
            cols[c].pyplot(fig)

        # Sparkline
        if not ohlcv.empty:
            cols[c].altair_chart(spark(ohlcv['c'].tail(8)), use_container_width=True)

        # GPT digest
        dig = aggregate_digest(sym, digest_files, sel_idx)
        cols[c].code(dig if dig else "No GPT digest.")

# --- Overview Image ---
png = f"{DATA_DIR}/plots/snapshot_{pulse_dt[sel_idx]}.png"
if not os.path.isfile(png):
    combine_pngs(symbols, png)
st.image(png, caption="Combined Overview")

# --- Master table with delta ---
st.header("📊 Summary")
rows = []
prev = json.loads(requests.get(next(f['download_url'] for f in files if f['name']==pulse_files[max(0,sel_idx-1)]), headers=HEADERS).text) if sel_idx>0 else []
prev_map = {a["symbol"]:a for a in prev}
for sym in symbols:
    df = assets[sym]; df_ohl=pd.DataFrame(df['ohlcv'])
    close = df_ohl['c'].iloc[-1] if not df_ohl.empty else None
    prev_close = prev_map.get(sym, {}).get('ohlcv', [{}])[-1].get('c') if sel_idx>0 else None
    delta = f"{close-prev_close:+.2f}" if prev_close else ""
    rows.append({"symbol":sym,"close":close,"Δclose":delta})
sty = pd.DataFrame(rows).style.applymap(lambda v:"color:green" if isinstance(v,str) and v.startswith("+") else ("color:red" if isinstance(v,str) and v.startswith("-") else ""), subset=["Δclose"])
st.dataframe(sty, use_container_width=True)

# --- Alerts ---
st.header("🚨 Alert Log")
try:
    log = pd.read_csv(f"{DATA_DIR}/oi_fr_alerts.csv")
    st.dataframe(log.tail(20), use_container_width=True)
except:
    st.info("No alert log.")

st.info("Done.")
