import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python<3.9 fallback
    from pytz import timezone as ZoneInfo

from utils import fetch_json_from_url

st.set_page_config(layout="wide", page_title="Crypto Market Pulse Dashboard")

# --- GitHub config ---
GH_USER = "topvlad"
GH_REPO = "market-pulse"
GH_BRANCH = "data-history"
DATA_DIR = "data"
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

# Optional threshold configuration
DEFAULT_THRESHOLDS = st.secrets.get("thresholds", {})
ASSET_MULTIPLIERS = st.secrets.get("asset_multipliers", {})

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
pulse_files = sorted([
    f["name"]
    for f in files_info
    if f["name"].startswith("pulse_") and f["name"].endswith(".json")
])
if not pulse_files:
    st.error("No pulse_*.json files found in remote data folder!")
    st.stop()

# --- Snapshot selection ---
user_tz = datetime.now().astimezone().tzinfo
pulse_labels = []
file_for_label = {}
date_str_for_label = {}
for fname in pulse_files:
    date_str = fname.replace("pulse_", "").replace(".json", "")
    dt = datetime.strptime(date_str, "%Y%m%d_%H%M").replace(tzinfo=timezone.utc)
    dt_local = dt.astimezone(user_tz)
    label = dt_local.strftime("%Y-%m-%d %H:%M %Z")
    pulse_labels.append(label)
    file_for_label[label] = fname
    date_str_for_label[label] = date_str

date_label = st.selectbox("Оберіть дату/час snapshot:", list(reversed(pulse_labels)))
date_idx = date_str_for_label[date_label]
sel_file = file_for_label[date_label]
sel_info = next(f for f in files_info if f["name"] == sel_file)

@st.cache_data(ttl=60*5)
def fetch_cached_json(url, timeout=None):
    """Cached wrapper around :func:`utils.fetch_json_from_url`."""
    return fetch_json_from_url(
        url,
        timeout=timeout,
        headers=headers,
        on_error=st.error,
    )

data = fetch_cached_json(sel_info['download_url'])

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

# Sidebar controls for alert thresholds
liq_pct = st.sidebar.slider(
    "Liquidation spike percentile",
    min_value=50,
    max_value=100,
    value=int(DEFAULT_THRESHOLDS.get("liquidation_percentile", 95)),
)
funding_rate_threshold = st.sidebar.number_input(
    "Funding rate alert threshold",
    min_value=0.0,
    value=float(DEFAULT_THRESHOLDS.get("funding_rate", 0.01)),
    step=0.001,
)

asset_multiplier = ASSET_MULTIPLIERS.get(asset_selected, 1.0)

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

digest_files = sorted(
    [f['name'] for f in files_info if f['name'].startswith("gpt_digest_") and f['name'].endswith(".txt")],
    reverse=True,
)
if digest_files:
    # Combine the most recent digests into a brief summary
    latest = digest_files[:3]
    combined = []
    for name in latest:
        info = next(f for f in files_info if f['name'] == name)
        combined.append(requests.get(info['download_url'], headers=headers).text.strip())
    summary = "\n\n".join(combined)
    st.code("\n".join(summary.splitlines()[:10]), language="text")

    with st.expander("Вибрати дайджест"):
        sel_digest = st.selectbox("Оберіть файл:", digest_files)
        info = next(f for f in files_info if f['name'] == sel_digest)
        text = requests.get(info['download_url'], headers=headers).text
        st.code(text, language="text")
else:
    st.info("Немає GPT дайджесту у data/")

# --- Alerts block (liq/funding extremes) ---
st.header("🚨 Алерти та екстремуми")
alerts = []
if not oi.empty and not liq.empty and 'total' in liq.columns:
    liq_plot = liq.copy()
    liq_plot['total'] = liq_plot['l'].astype(float) + liq_plot['s'].astype(float)
    base_threshold = liq_plot['total'].quantile(liq_pct / 100.0)
    threshold = base_threshold * asset_multiplier
    spikes = liq_plot[liq_plot['total'] > threshold]
    if not spikes.empty:
        alerts.append(
            f"⚡ Можливий розворот після сплеску ліквідацій: {list(spikes.index.strftime('%Y-%m-%d %H:%M'))}"
        )
if not fr.empty and 'c' in fr.columns:
    if fr['c'].abs().max() > funding_rate_threshold:
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

    change_24h, vol_24h, oi_delta = None, None, None
    if not ohlcv.empty and 't' in ohlcv.columns and 'c' in ohlcv.columns:
        ohlcv_temp = ohlcv.copy()
        ohlcv_temp['t'] = pd.to_datetime(ohlcv_temp['t'], unit='s', errors='coerce')
        ohlcv_temp.set_index('t', inplace=True)
        ts_last = ohlcv_temp.index[-1]
        win = ohlcv_temp.loc[ohlcv_temp.index >= ts_last - pd.Timedelta(hours=24)]
        if not win.empty:
            first_close = win['c'].iloc[0]
            last_close = win['c'].iloc[-1]
            if first_close:
                change_24h = (last_close - first_close) / first_close * 100
            vol_24h = win['v'].sum() if 'v' in win.columns else None
    if not oi.empty and 't' in oi.columns and 'c' in oi.columns:
        oi_temp = oi.copy()
        oi_temp['t'] = pd.to_datetime(oi_temp['t'], unit='s', errors='coerce')
        oi_temp.set_index('t', inplace=True)
        ts_last = oi_temp.index[-1]
        win = oi_temp.loc[oi_temp.index >= ts_last - pd.Timedelta(hours=24)]
        if not win.empty:
            oi_delta = win['c'].iloc[-1] - win['c'].iloc[0]

    summary.append({
        "symbol": sym,
        "close": close,
        "change_24h": change_24h,
        "volume_24h": vol_24h,
        "oi_last": oi_last,
        "oi_delta": oi_delta,
        "fr_last": fr_last,
        "liq_sum": liq_sum,
    })

summary_df = pd.DataFrame(summary)
sort_col = st.selectbox("Sort by:", summary_df.columns, index=0)
st.data_editor(summary_df.sort_values(sort_col, ascending=False), use_container_width=True)

# --- Show plots (trend images) ---
st.header("OI & Funding Trend Plots (PNG, live from repo)")
plots_url = f"https://api.github.com/repos/{GH_USER}/{GH_REPO}/contents/{DATA_DIR}/plots?ref={GH_BRANCH}"
plots_info = requests.get(plots_url, headers=headers).json()
if isinstance(plots_info, list):
    plot_names = [f['name'] for f in plots_info if f['name'].endswith(".png")]
    for p in plot_names:
        if asset_selected.replace("/", "_") in p:
            plot_info = next(f for f in plots_info if f['name'] == p)
            st.image(plot_info['download_url'], caption=p)
else:
    st.info("No plots found in plots/ subfolder.")

st.write("---")
st.info("Dashboard MVP by [your team]. Звʼяжись з @topvlad або @lostframe_404 для вдосконалення/розширення!")
