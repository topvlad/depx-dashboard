import streamlit as st
import pandas as pd
import requests, json, os
import matplotlib.pyplot as plt
import altair as alt
from PIL import Image
import io

# --- Config ---
GH_USER, GH_REPO, GH_BRANCH = "topvlad", "market-pulse", "data-history"
DATA_DIR = "data"
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]  # Add in .streamlit/secrets.toml
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

st.set_page_config(layout="wide", page_title="🚦 Crypto Market Pulse Dashboard")

def spark(data):
    # Mini price sparkline using Altair
    return alt.Chart(pd.DataFrame({'y': data})).mark_line().encode(y='y').properties(height=30, width=100)

def pretty(dtstr):
    # "20250630_1648" → "30 Jun 16:48"
    return pd.to_datetime(dtstr, format="%Y%m%d_%H%M").strftime("%d %b %H:%M")

def aggregate_digest(sym, digest_api_files, idx, n=4):
    picks = digest_api_files[max(0, idx-n+1):idx+1]
    parts = []
    for api_file in picks:
        r = requests.get(api_file['download_url'], headers=HEADERS)
        block = r.text
        start = block.find(f"=== {sym} ===")
        if start >= 0:
            end = block.find("===", start+1)
            txt = block[start:end].strip() if end>0 else block[start:].strip()
            parts.append(txt)
    return "\n---\n".join(parts)

# --- Remote Data Fetching ---
@st.cache_data(ttl=300)
def get_files():
    url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{DATA_DIR}?ref={GH_BRANCH}"
    r = requests.get(url, headers=HEADERS); r.raise_for_status()
    return r.json()

files = get_files()

# --- List & sort remote data ---
pulse_files = sorted([f for f in files if f['name'].startswith("pulse_") and f['name'].endswith(".json")], key=lambda x: x['name'])
if not pulse_files:
    st.error("No pulse_*.json files found in remote data folder!")
    st.stop()

pulse_dt = [f['name'].replace("pulse_","").replace(".json","") for f in pulse_files]
pulse_labels = [pretty(dt) for dt in pulse_dt]
sel_idx = st.select_slider("Оберіть snapshot:", options=list(range(len(pulse_dt))), format_func=lambda i: pulse_labels[i], value=len(pulse_dt)-1)

# --- Fetch selected pulse file (JSON) ---
sel_pulse_file = pulse_files[sel_idx]
pulse = json.loads(requests.get(sel_pulse_file['download_url'], headers=HEADERS).text)

# --- Fetch digests (API-based, remote) ---
digest_api_files = sorted([f for f in files if f['name'].startswith("gpt_digest_") and f['name'].endswith(".txt")], key=lambda x: x['name'])

# --- Fetch available plots (API) ---
plot_api_files = []
try:
    plots_url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{DATA_DIR}/plots?ref={GH_BRANCH}"
    plot_api_files = requests.get(plots_url, headers=HEADERS).json()
    if not isinstance(plot_api_files, list): plot_api_files = []
except Exception:
    plot_api_files = []

# --- Prepare assets
assets = {a["symbol"]: a for a in pulse}
symbols = list(assets.keys())[:4]  # limit to top 4 for 'crypto square'
N = len(symbols)
rows = (N + 1) // 2

# --- UI ---
st.title("🚦 Crypto Market Pulse Dashboard")
st.write("Live & historical analytics from Coinalyze, GPT digests, and technicals for your main marketmakers.")

# --- Replay last 4 snapshots ---
if st.button("▶️ Replay last 4 snapshots (auto)"):
    for idx in range(max(0, len(pulse_dt)-4), len(pulse_dt)):
        st.write(f"### Snapshot: {pretty(pulse_dt[idx])}")
        png = next((f for f in plot_api_files if f['name'] == f"snapshot_{pulse_dt[idx]}.png"), None)
        if png: st.image(png['download_url'], caption="Overview")
        st.info("← Scroll down for more details for each snapshot")
        st.divider()
    st.stop()

# --- Crypto Square Grid (robust) ---
st.header("🔲 Crypto Square (All key markets at a glance)")
for r in range(rows):
    cols = st.columns(2)
    for c in range(2):
        idx = r*2 + c
        if idx >= N: break
        sym = symbols[idx]
        df = assets[sym]
        ohlcv, oi, fr, liq = map(pd.DataFrame, (df["ohlcv"], df["oi"], df["fr"], df["liq"]))
        cols[c].subheader(sym)

        # OI & Funding Rate Plot
        if not oi.empty and not fr.empty:
            try:
                oi['t'] = pd.to_datetime(oi['t'], unit='s')
                fr['t'] = pd.to_datetime(fr['t'], unit='s')
                fig, ax1 = plt.subplots(figsize=(4,2))
                ax1.plot(oi['t'], oi['c'], color="blue", label="OI")
                ax1.set_ylabel("OI", color="blue")
                ax2 = ax1.twinx()
                ax2.plot(fr['t'], fr['c'], color="orange", label="Funding")
                ax2.set_ylabel("Funding", color="orange")
                plt.title(f"{sym} OI & Funding Rate")
                cols[c].pyplot(fig)
            except Exception as e:
                cols[c].warning(f"OI/Funding plot error: {e}")

        # Sparkline price (last 8 closes)
        if not ohlcv.empty and "c" in ohlcv.columns:
            cols[c].altair_chart(spark(ohlcv['c'].tail(8)), use_container_width=True)

        # GPT Digest (last 4)
        dig = aggregate_digest(sym, digest_api_files, sel_idx)
        cols[c].markdown("**GPT-дайджест (last 4)**")
        cols[c].code(dig if dig else "No GPT digest for this asset.")

        # Alerts (liq/funding extremes)
        alerts = []
        if not oi.empty and not liq.empty and 'l' in liq.columns and 's' in liq.columns:
            liq['total'] = liq['l'].astype(float) + liq['s'].astype(float)
            threshold = liq['total'].mean() + 3 * liq['total'].std()
            spikes = liq[liq['total'] > threshold]
            if not spikes.empty:
                alerts.append(f"⚡ Можливий розворот після сплеску ліквідацій: {list(spikes.index.strftime('%Y-%m-%d %H:%M'))}")
        if not fr.empty and 'c' in fr.columns and (fr['c'].abs().max() > 0.01):
            alerts.append(f"⚡ Екстрим у funding rate ({fr['c'].max():.4f})")
        if alerts:
            for alert in alerts: cols[c].warning(alert)
        else:
            cols[c].success("Аномалій не знайдено.")

# --- Merged PNG (overview) or fallbacks ---
merged_png = next((f for f in plot_api_files if f['name']==f"snapshot_{pulse_dt[sel_idx]}.png"), None)
if merged_png:
    st.image(merged_png['download_url'], caption="OI/Funding Combined Overview")
else:
    st.write("Combined PNG not found. Showing per-coin plots:")
    for sym in symbols:
        trend = next((f for f in plot_api_files if f['name']==f"{sym}_trend.png"), None)
        if trend: st.image(trend['download_url'], caption=f"{sym} trend")

# --- Master table with delta ---
st.header("📊 Master table for snapshot")
rows_summary = []
prev_pulse = None
if sel_idx > 0:
    prev_pulse_file = pulse_files[sel_idx-1]
    prev_pulse = json.loads(requests.get(prev_pulse_file['download_url'], headers=HEADERS).text)
    prev_map = {a["symbol"]: a for a in prev_pulse}
else:
    prev_map = {}

for sym in symbols:
    df = assets[sym]
    ohlcv = pd.DataFrame(df['ohlcv'])
    close = ohlcv['c'].iloc[-1] if not ohlcv.empty else None
    prev_close = prev_map.get(sym, {}).get('ohlcv', [{}])[-1].get('c') if sel_idx>0 else None
    delta = f"{close-prev_close:+.2f}" if close is not None and prev_close is not None else ""
    rows_summary.append({"symbol": sym, "close": close, "Δclose": delta})

df_sum = pd.DataFrame(rows_summary)
def color_delta(val):
    if isinstance(val, str) and val.startswith("+"): return "color: green"
    if isinstance(val, str) and val.startswith("-"): return "color: red"
    return ""
if "Δclose" in df_sum.columns:
    st.dataframe(df_sum.style.applymap(color_delta, subset=["Δclose"]), use_container_width=True)
else:
    st.dataframe(df_sum, use_container_width=True)

# --- Alert Log (csv, remote not supported directly) ---
st.header("OI/Funding Alert History")
# Alert log NOT available via API from private, unless you publish it to public!
try:
    alert_log = pd.read_csv(os.path.join(DATA_DIR, "oi_fr_alerts.csv"))
    st.dataframe(alert_log.tail(50), use_container_width=True)
except Exception:
    st.info("No OI alert log found yet. (Note: This works only if data/ is synced locally to your dashboard repo. If not, consider publishing this as a public CSV file or GitHub Gist!)")

st.write("---")
st.info("Dashboard MVP by [your team]. Contact @topvlad or @lostframe_404 for feedback/improvement!")
