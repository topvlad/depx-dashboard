# app.py
import streamlit as st
import pandas as pd
import glob
import os
import json
import matplotlib.pyplot as plt

st.set_page_config(layout="wide", page_title="Crypto Market Pulse Dashboard")

DATA_DIR = "data"  # або data-history/data якщо так підключиш

st.title("🚦 Crypto Market Pulse Dashboard")
st.write("Live & historical analytics from Coinalyze, GPT digests, and technicals for your main marketmakers.")

# --- Load all available pulse files ---
pulse_files = sorted(glob.glob(os.path.join(DATA_DIR, "pulse_*.json")))
if not pulse_files:
    st.error("No pulse_*.json files found in data folder!")
    st.stop()

# Select period to show
pulse_dates = [os.path.basename(f).replace("pulse_", "").replace(".json", "") for f in pulse_files]
date_idx = st.selectbox("Оберіть дату/час snapshot:", list(reversed(pulse_dates)))
sel_file = pulse_files[pulse_dates.index(date_idx)]

with open(sel_file) as f:
    data = json.load(f)

# --- Prepare Data ---
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

with col1:
    st.subheader("Open Interest (OI) & Funding Rate")
    if not oi.empty and 't' in oi.columns and 'c' in oi.columns and not fr.empty and 'c' in fr.columns:
        oi['t'] = pd.to_datetime(oi['t'], unit='s')
        oi.set_index('t', inplace=True)
        fr['t'] = pd.to_datetime(fr['t'], unit='s')
        fr.set_index('t', inplace=True)
        fig, ax1 = plt.subplots(figsize=(8, 3))
        ax1.plot(oi.index, oi['c'], color="blue", label="OI")
        ax1.set_ylabel("OI", color="blue")
        ax2 = ax1.twinx()
        ax2.plot(fr.index, fr['c'], color="orange", label="Funding")
        ax2.set_ylabel("Funding", color="orange")
        plt.title(f"{asset_selected} OI & Funding Rate")
        st.pyplot(fig)
    else:
        st.warning("Недостатньо даних для графіка OI/Funding.")

with col2:
    st.subheader("Ліквідації")
    if not liq.empty and 't' in liq.columns and 'l' in liq.columns and 's' in liq.columns:
        liq['t'] = pd.to_datetime(liq['t'], unit='s')
        liq.set_index('t', inplace=True)
        liq['long'] = liq['l'].astype(float)
        liq['short'] = liq['s'].astype(float)
        liq['total'] = liq['long'] + liq['short']
        fig2, ax = plt.subplots(figsize=(8, 3))
        ax.bar(liq.index, liq['total'], color="red", width=0.03)
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

# --- GPT Digsest block ---
st.header("GPT-дайджест трейдера (по snapshot)")
digest_files = sorted(glob.glob(os.path.join(DATA_DIR, "gpt_digest_*.txt")))
if digest_files:
    # знайти дайджест, найближчий до snapshot
    dates_d = [os.path.basename(f).replace("gpt_digest_", "").replace(".txt", "") for f in digest_files]
    idx = min(range(len(dates_d)), key=lambda i: abs(pd.to_datetime(dates_d[i], format="%Y%m%d_%H%M") - pd.to_datetime(date_idx, format="%Y%m%d_%H%M")))
    with open(digest_files[idx], encoding="utf-8") as f:
        gpt_digest = f.read()
    st.code(gpt_digest, language="text")
else:
    st.info("Немає GPT дайджесту у data/")

# --- Alerts block (liq/funding extremes) ---
st.header("🚨 Алерти та екстремуми")
alerts = []
if not oi.empty and not liq.empty and 'total' in liq.columns:
    threshold = liq['total'].mean() + 3 * liq['total'].std()
    spikes = liq[liq['total'] > threshold]
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

st.write("---")
st.info("Dashboard MVP by [your team]. Звʼяжись з @topvlad або @lostframe_404 для вдосконалення/розширення!")
