import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
import time

st.set_page_config(layout="wide", page_title="Crypto Market Pulse Dashboard")

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

st.title("🚦 Crypto Market Pulse Dashboard")
st.write("Live & historical analytics from Coinalyze, GPT digests, and technicals for your main marketmakers.")

@st.cache_data(ttl=60*5)
def get_data_file_list():
    api_url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{DATA_DIR}?ref={GH_BRANCH}"
    r = requests.get(api_url, headers=headers)
    r.raise_for_status()
    return r.json()

files_info = get_data_file_list()
pulse_files = sorted([f['name'] for f in files_info if f['name'].startswith("pulse_") and f['name'].endswith(".json")])
if not pulse_files:
    st.error("No pulse_*.json files found in remote data folder!")
    st.stop()

# --- Snapshot selection ---
pulse_dates = [f.replace("pulse_", "").replace(".json", "") for f in pulse_files]
date_idx = st.selectbox("Оберіть дату/час snapshot:", list(reversed(pulse_dates)))
sel_file = pulse_files[pulse_dates.index(date_idx)]
sel_info = next(f for f in files_info if f['name'] == sel_file)

@st.cache_data(ttl=60*5)
def fetch_json_from_url(url, timeout=None):
    """Fetch JSON data from a URL with optional timeout.

    On network or decoding errors an empty dict is returned and the error is
    shown via ``st.error``.
    """
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        st.error(f"Request failed: {exc}")
    except ValueError as exc:
        st.error(f"JSON decode failed: {exc}")
    return {}

data = fetch_json_from_url(sel_info['download_url'])

# --- Prepare asset DataFrames ---
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

symbols = list(assets.keys())
st.sidebar.title("Вибір активу")
asset_selected = st.sidebar.selectbox("Актив:", symbols)

st.header(f"Market Pulse for {asset_selected}")

tabs = assets[asset_selected]
ohlcv, oi, fr, liq = tabs["ohlcv"], tabs["oi"], tabs["fr"], tabs["liq"]

col1, col2 = st.columns([2,2])

# --- OI & Funding graph ---
with col1:
    st.subheader("Open Interest (OI) & Funding Rate")
    if not oi.empty and 't' in oi.columns and 'c' in oi.columns and not fr.empty and 'c' in fr.columns:
        oi_plot = oi.copy()
        oi_plot['t'] = pd.to_datetime(oi_plot['t'], unit='s')
        oi_plot.set_index('t', inplace=True)
        fr_plot = fr.copy()
        fr_plot['t'] = pd.to_datetime(fr_plot['t'], unit='s')
        fr_plot.set_index('t', inplace=True)
        fig, ax1 = plt.subplots(figsize=(8, 3))
        ax1.plot(oi_plot.index, oi_plot['c'], color="blue", label="OI")
        ax1.set_ylabel("OI", color="blue")
        ax2 = ax1.twinx()
        ax2.plot(fr_plot.index, fr_plot['c'], color="orange", label="Funding")
        ax2.set_ylabel("Funding", color="orange")
        plt.title(f"{asset_selected} OI & Funding Rate")
        st.pyplot(fig)
    else:
        st.warning("Недостатньо даних для графіка OI/Funding.")

# --- Liquidations graph ---
with col2:
    st.subheader("Ліквідації")
    if not liq.empty and 't' in liq.columns and 'l' in liq.columns and 's' in liq.columns:
        liq_plot = liq.copy()
        liq_plot['t'] = pd.to_datetime(liq_plot['t'], unit='s')
        liq_plot.set_index('t', inplace=True)
        liq_plot['long'] = liq_plot['l'].astype(float)
        liq_plot['short'] = liq_plot['s'].astype(float)
        liq_plot['total'] = liq_plot['long'] + liq_plot['short']
        fig2, ax = plt.subplots(figsize=(8, 3))
        ax.bar(liq_plot.index, liq_plot['total'], color="red", width=0.03)
        ax.set_ylabel("Σ Ліквідацій (total)")
        plt.title(f"{asset_selected} Liquidations")
        st.pyplot(fig2)
    else:
        st.warning("Недостатньо даних для графіка ліквідацій.")

st.subheader("Таблиця OHLCV")
if not ohlcv.empty:
    st.dataframe(ohlcv.tail(20))
else:
    st.warning("OHLCV data missing.")

# --- GPT Digest Block (remote fetch) ---
st.header("GPT-дайджест трейдера (по snapshot)")

digest_files = sorted([f['name'] for f in files_info if f['name'].startswith("gpt_digest_") and f['name'].endswith(".txt")])
if digest_files:
    dates_d = [f.replace("gpt_digest_", "").replace(".txt", "") for f in digest_files]
    idx = min(range(len(dates_d)), key=lambda i: abs(pd.to_datetime(dates_d[i], format="%Y%m%d_%H%M") - pd.to_datetime(date_idx, format="%Y%m%d_%H%M")))
    digest_file = digest_files[idx]
    digest_info = next(f for f in files_info if f['name'] == digest_file)
    digest_text = requests.get(digest_info['download_url'], headers=headers).text
    st.code(digest_text, language="text")
else:
    st.info("Немає GPT дайджесту у data/")

# --- Alerts block (liq/funding extremes) ---
st.header("🚨 Алерти та екстремуми")
alerts = []
if not oi.empty and not liq.empty and 'total' in liq.columns:
    liq_plot = liq.copy()
    liq_plot['total'] = liq_plot['l'].astype(float) + liq_plot['s'].astype(float)
    threshold = liq_plot['total'].mean() + 3 * liq_plot['total'].std()
    spikes = liq_plot[liq_plot['total'] > threshold]
    if not spikes.empty:
        alerts.append(f"⚡ Можливий розворот після сплеску ліквідацій: {list(spikes.index.strftime('%Y-%m-%d %H:%M'))}")
if not fr.empty and 'c' in fr.columns:
    if fr['c'].abs().max() > 0.01:
        alerts.append(f"⚡ Екстрим у funding rate ({fr['c'].max():.4f})")
if alerts:
    for alert in alerts:
        st.warning(alert)
else:
    st.success("Аномалій не знайдено.")

# --- Master table for all assets in snapshot ---
st.header("Master table for snapshot")
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
st.dataframe(pd.DataFrame(summary))

# --- Show plots (trend images) ---
st.header("OI & Funding Trend Plots (PNG, live from repo)")
plots_url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{DATA_DIR}/plots?ref={GH_BRANCH}"
plots_info = requests.get(plots_url, headers=headers).json()
if isinstance(plots_info, list):
    matched = [f for f in plots_info
               if f['name'].endswith('.png') and asset_selected.replace('/', '_') in f['name']]
    if matched:
        matched = sorted(matched, key=lambda x: x['name'])
        urls = [f['download_url'] for f in matched]
        names = [f['name'] for f in matched]
        idx = st.slider('Frame', 0, len(urls) - 1, 0)
        if st.checkbox('Auto play'):
            placeholder = st.empty()
            for i in range(len(urls)):
                placeholder.image(urls[i], caption=names[i])
                time.sleep(0.3)
        else:
            st.image(urls[idx], caption=names[idx])
    else:
        st.info("No plots found for asset.")
else:
    st.info("No plots found in plots/ subfolder.")

st.write("---")
st.info("Dashboard MVP by [your team]. Звʼяжись з @topvlad або @lostframe_404 для вдосконалення/розширення!")
