import streamlit as st
import pandas as pd
import requests
import json
import matplotlib.pyplot as plt
import altair as alt
from PIL import Image
from io import BytesIO

# --- GitHub config ---
GH_USER = "topvlad"
GH_REPO = "market-pulse"
GH_BRANCH = "data-history"
DATA_DIR = "data"
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

st.set_page_config(layout="wide", page_title="Crypto Market Pulse Dashboard")
st.title("🚦 Crypto Market Pulse Dashboard")
st.write("Live & historical analytics from Coinalyze, GPT digests, and technicals for your main marketmakers.")

# -------- UTILS --------

def pretty_label(dtstr):
    d = pd.to_datetime(dtstr, format="%Y%m%d_%H%M")
    return d.strftime("%d %b %H:%M")

def sparkline(data):
    chart = alt.Chart(pd.DataFrame({'y': data})).mark_line().encode(
        y='y'
    ).properties(height=30, width=100)
    return chart

def download_github_file(download_url):
    r = requests.get(download_url, headers=headers)
    r.raise_for_status()
    return r.content

def load_json_from_github(download_url):
    content = download_github_file(download_url)
    return json.loads(content.decode('utf-8'))

def load_digest_section(digest_text, sym):
    start = digest_text.find(f"=== {sym} ===")
    if start != -1:
        end = digest_text.find("===", start + 1)
        txt = digest_text[start:end].strip() if end != -1 else digest_text[start:].strip()
        return txt
    return ""

def aggregate_gpt_digest(sym, digest_files, date_idx, n=4):
    # Take last n digests up to date_idx (indices are already in time order)
    idxs = list(range(max(0, date_idx-n+1), date_idx+1))
    digests = []
    for i in idxs:
        text = download_github_file(digest_files[i]['download_url']).decode("utf-8")
        txt = load_digest_section(text, sym)
        if txt: digests.append(txt)
    return "\n---\n".join(digests)

def combine_pngs(symbols, plots_info, out_file="snapshot_tmp.png"):
    imgs = []
    for sym in symbols:
        fname = f"{sym}_trend.png"
        match = next((f for f in plots_info if f['name'] == fname), None)
        if match:
            img_bytes = download_github_file(match['download_url'])
            imgs.append(Image.open(BytesIO(img_bytes)))
        else:
            imgs.append(Image.new('RGB', (400, 200), color=(240,240,240)))
    w, h = imgs[0].size
    grid = Image.new('RGB', (2*w, 2*h), color=(255,255,255))
    grid.paste(imgs[0], (0,0))
    grid.paste(imgs[1], (w,0))
    grid.paste(imgs[2], (0,h))
    grid.paste(imgs[3], (w,h))
    # return PIL Image for in-memory display
    return grid

# -------- 1. List remote files --------
@st.cache_data(ttl=60*5)
def get_data_file_list():
    api_url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{DATA_DIR}?ref={GH_BRANCH}"
    r = requests.get(api_url, headers=headers)
    r.raise_for_status()
    return r.json()

files_info = get_data_file_list()
pulse_files = sorted([f for f in files_info if f['name'].startswith("pulse_") and f['name'].endswith(".json")], key=lambda x: x['name'])
digest_files = sorted([f for f in files_info if f['name'].startswith("gpt_digest_") and f['name'].endswith(".txt")], key=lambda x: x['name'])
if not pulse_files:
    st.error("No pulse_*.json files found in remote data folder!")
    st.stop()

pulse_dates = [f['name'].replace("pulse_", "").replace(".json", "") for f in pulse_files]
pulse_labels = [pretty_label(d) for d in pulse_dates]

# -------- 2. Select snapshot --------
date_idx = st.select_slider("Оберіть дату/час snapshot:",
                           options=list(range(len(pulse_dates))),
                           format_func=lambda i: pulse_labels[i],
                           value=len(pulse_dates)-1)
sel_file_info = pulse_files[date_idx]
data = load_json_from_github(sel_file_info['download_url'])

# -------- 3. Prepare Data --------
assets = {}
for asset in data:
    sym = asset["symbol"]
    assets[sym] = {
        "ohlcv": pd.DataFrame(asset["ohlcv"]),
        "oi": pd.DataFrame(asset["oi"]),
        "fr": pd.DataFrame(asset["fr"]),
        "liq": pd.DataFrame(asset["liq"]),
        "lsr": pd.DataFrame(asset["lsr"]),
    }

symbols = list(assets.keys())[:4]  # Restrict to top 4

# -------- 4. Crypto 'Square' Grid --------
st.header("🔲 Crypto Market 'Square' — All Key Markets At A Glance")
rows, cols = 2, 2
symbols_grid = [symbols[i*cols:(i+1)*cols] for i in range(rows)]

# Load plot PNGs metadata
plots_url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{DATA_DIR}/plots?ref={GH_BRANCH}"
plots_info = requests.get(plots_url, headers=headers).json() if isinstance(requests.get(plots_url, headers=headers).json(), list) else []

for symbol_row in symbols_grid:
    cols_st = st.columns(cols)
    for i, sym in enumerate(symbol_row):
        with cols_st[i]:
            st.subheader(f"**{sym}**")
            tabs = assets[sym]
            ohlcv, oi, fr, liq = tabs["ohlcv"], tabs["oi"], tabs["fr"], tabs["liq"]

            st.markdown("**Open Interest (OI) & Funding Rate**")
            if not oi.empty and 't' in oi.columns and 'c' in oi.columns and not fr.empty and 'c' in fr.columns:
                oi_plot = oi.copy()
                oi_plot['t'] = pd.to_datetime(oi_plot['t'], unit='s')
                oi_plot.set_index('t', inplace=True)
                fr_plot = fr.copy()
                fr_plot['t'] = pd.to_datetime(fr_plot['t'], unit='s')
                fr_plot.set_index('t', inplace=True)
                fig, ax1 = plt.subplots(figsize=(5, 2.3))
                ax1.plot(oi_plot.index, oi_plot['c'], color="blue", label="OI")
                ax1.set_ylabel("OI", color="blue")
                ax2 = ax1.twinx()
                ax2.plot(fr_plot.index, fr_plot['c'], color="orange", label="Funding")
                ax2.set_ylabel("Funding", color="orange")
                plt.title(f"{sym} OI & Funding Rate")
                st.pyplot(fig)
            else:
                st.info("Недостатньо даних для графіка OI/Funding.")

            st.markdown("**Ліквідації**")
            if not liq.empty and 't' in liq.columns and 'l' in liq.columns and 's' in liq.columns:
                liq_plot = liq.copy()
                liq_plot['t'] = pd.to_datetime(liq_plot['t'], unit='s')
                liq_plot.set_index('t', inplace=True)
                liq_plot['long'] = liq_plot['l'].astype(float)
                liq_plot['short'] = liq_plot['s'].astype(float)
                liq_plot['total'] = liq_plot['long'] + liq_plot['short']
                fig2, ax = plt.subplots(figsize=(5, 2.3))
                ax.bar(liq_plot.index, liq_plot['total'], color="red", width=0.03)
                ax.set_ylabel("Σ Ліквідацій (total)")
                plt.title(f"{sym} Liquidations")
                st.pyplot(fig2)
            else:
                st.info("Недостатньо даних для графіка ліквідацій.")

            st.markdown("**OHLCV (last 8)**")
            if not ohlcv.empty:
                st.altair_chart(sparkline(ohlcv['c'].tail(8)), use_container_width=True)
            else:
                st.info("OHLCV data missing.")

            alerts = []
            if not oi.empty and not liq.empty and 'l' in liq.columns and 's' in liq.columns:
                liq_plot = liq.copy()
                liq_plot['total'] = liq_plot['l'].astype(float) + liq_plot['s'].astype(float)
                threshold = liq_plot['total'].mean() + 3 * liq_plot['total'].std()
                spikes = liq_plot[liq_plot['total'] > threshold]
                if not spikes.empty:
                    alerts.append(f"⚡ Можливий розворот після сплеску ліквідацій: {list(spikes.index.strftime('%Y-%m-%d %H:%M'))}")
            if not fr.empty and 'c' in fr.columns:
                if fr['c'].abs().max() > 0.01:
                    alerts.append(f"⚡ Екстрим у funding rate ({fr['c'].max():.4f})")
            st.markdown("**Алерти та екстремуми**")
            if alerts:
                for alert in alerts:
                    st.warning(alert)
            else:
                st.success("Аномалій не знайдено.")

            st.markdown("**GPT-дайджест (last 4)**")
            if digest_files:
                agg_digest = aggregate_gpt_digest(sym, digest_files, date_idx)
                if agg_digest.strip():
                    st.code(agg_digest)
                else:
                    st.info("GPT digest not found for this asset.")
            else:
                st.info("GPT digest not found for this asset.")

            st.write("---")

# -------- Merged Overview PNG (2x2 grid of OI/Funding) --------
if plots_info and len(plots_info) > 3:
    try:
        grid_img = combine_pngs(symbols, plots_info)
        st.image(grid_img, caption="OI/Funding Overview")
    except Exception:
        st.info("No combined PNG available.")
else:
    st.info("No trend plots found to merge.")

# -------- Master Table (with Δ) --------
st.header("📊 Master table for snapshot")
summary = []
for sym in symbols:
    tabs = assets[sym]
    ohlcv = tabs["ohlcv"]
    oi = tabs["oi"]
    fr = tabs["fr"]
    liq = tabs["liq"]
    close = ohlcv['c'].iloc[-1] if not ohlcv.empty and 'c' in ohlcv.columns else None
    oi_last = oi['c'].iloc[-1] if not oi.empty and 'c' in oi.columns else None
    fr_last = fr['c'].iloc[-1] if not fr.empty and 'c' in fr.columns else None
    liq_sum = liq['l'].sum() + liq['s'].sum() if not liq.empty and 'l' in liq.columns and 's' in liq.columns else 0
    summary.append({"symbol": sym, "close": close, "oi_last": oi_last, "fr_last": fr_last, "liq_sum": liq_sum})

df = pd.DataFrame(summary)
if date_idx > 0:
    prev_data = load_json_from_github(pulse_files[date_idx-1]['download_url'])
    prev_assets = {a["symbol"]: a for a in prev_data}
    for row in df.itertuples():
        sym = row.symbol
        try:
            prev_close = prev_assets[sym]["ohlcv"][-1]["c"]
            delta = row.close - prev_close
            df.loc[row.Index, "Δclose"] = f"{delta:+.2f}"
        except Exception:
            df.loc[row.Index, "Δclose"] = ""
    def color_delta(val):
        if isinstance(val, str) and val.startswith("+"):
            return "color: green"
        elif isinstance(val, str) and val.startswith("-"):
            return "color: red"
        return ""
    st.dataframe(df.style.applymap(color_delta, subset=["Δclose"]), use_container_width=True)
else:
    st.dataframe(df, use_container_width=True)

# -------- OI/FUNDING ALERT LOG --------
st.header("OI/Funding Alert History")
oi_fr_alert_csv = next((f for f in files_info if f['name'] == "oi_fr_alerts.csv"), None)
if oi_fr_alert_csv:
    import io
    csv_bytes = download_github_file(oi_fr_alert_csv['download_url'])
    alert_log = pd.read_csv(io.BytesIO(csv_bytes))
    st.dataframe(alert_log.tail(50), use_container_width=True)
else:
    st.info("No OI alert log found yet.")

st.write("---")
st.info("Dashboard MVP by [your team]. Звʼяжись з @topvlad або @lostframe_404 для вдосконалення/розширення!")
