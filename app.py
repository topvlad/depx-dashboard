import streamlit as st
import pandas as pd
import glob
import os
import json
import matplotlib.pyplot as plt
import altair as alt
from PIL import Image

st.set_page_config(layout="wide", page_title="Crypto Market Pulse Dashboard")
DATA_DIR = "data"

def combine_pngs(symbols, data_dir, out_file):
    imgs = []
    for sym in symbols:
        fname = os.path.join(data_dir, "plots", f"{sym}_trend.png")
        if os.path.isfile(fname):
            imgs.append(Image.open(fname))
        else:
            imgs.append(Image.new('RGB', (400,200), color=(240,240,240)))
    w, h = imgs[0].size
    grid = Image.new('RGB', (2*w, 2*h), color=(255,255,255))
    grid.paste(imgs[0], (0,0))
    grid.paste(imgs[1], (w,0))
    grid.paste(imgs[2], (0,h))
    grid.paste(imgs[3], (w,h))
    grid.save(out_file)

def sparkline(data):
    chart = alt.Chart(pd.DataFrame({'y': data})).mark_line().encode(
        y='y'
    ).properties(height=30, width=100)
    return chart

def pretty_label(dtstr):
    d = pd.to_datetime(dtstr, format="%Y%m%d_%H%M")
    return d.strftime("%d %b %H:%M")

def aggregate_gpt_digest(sym, digest_files, date_idx, n=4):
    idxs = list(range(max(0, date_idx-n+1), date_idx+1))
    digests = []
    for i in idxs:
        with open(digest_files[i], encoding="utf-8") as f:
            block = f.read()
            start = block.find(f"=== {sym} ===")
            if start != -1:
                end = block.find("===", start + 1)
                txt = block[start:end].strip() if end != -1 else block[start:].strip()
                digests.append(txt)
    return "\n---\n".join(digests)

# --- Load all available pulse files ---
pulse_files = sorted(glob.glob(os.path.join(DATA_DIR, "pulse_*.json")))
if not pulse_files:
    st.error("No pulse_*.json files found in data folder!")
    st.stop()

pulse_dates = [os.path.basename(f).replace("pulse_", "").replace(".json", "") for f in pulse_files]
pulse_labels = [pretty_label(d) for d in pulse_dates]

date_idx = st.select_slider("Оберіть дату/час snapshot:",
                           options=list(range(len(pulse_dates))),
                           format_func=lambda i: pulse_labels[i],
                           value=len(pulse_dates)-1)
sel_file = pulse_files[date_idx]

with open(sel_file) as f:
    data = json.load(f)

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

symbols = list(assets.keys())[:4]  # Restrict to top 4 (crypto square)
digest_files = sorted(glob.glob(os.path.join(DATA_DIR, "gpt_digest_*.txt")))

st.title("🚦 Crypto Market Pulse Dashboard")
st.write("Live & historical analytics from Coinalyze, GPT digests, and technicals for your main marketmakers.")

# ========== CRYPTO SQUARE GRID ==========
st.header("🔲 Crypto Market 'Square' — All Key Markets At A Glance")

rows, cols = 2, 2
symbols_grid = [symbols[i*cols:(i+1)*cols] for i in range(rows)]

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

# ========== MERGED PNG OVERVIEW ==========
merged_png = f"{DATA_DIR}/plots/snapshot_{pulse_dates[date_idx]}.png"
if os.path.isfile(merged_png):
    st.image(merged_png, caption="OI/Funding Overview")
else:
    # Try to generate on the fly if not present
    try:
        combine_pngs(symbols, DATA_DIR, merged_png)
        st.image(merged_png, caption="OI/Funding Overview")
    except Exception:
        st.info("No combined PNG available.")

# ========== MASTER TABLE WITH DELTA ==========
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
if len(pulse_files) > 1:
    with open(pulse_files[date_idx-1]) as f:
        prev_data = json.load(f)
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

# ========== OI/FUNDING ALERT LOG ==========
st.header("OI/Funding Alert History")
try:
    alert_log = pd.read_csv(os.path.join(DATA_DIR, "oi_fr_alerts.csv"))
    st.dataframe(alert_log.tail(50), use_container_width=True)
except Exception:
    st.info("No OI alert log found yet.")

st.write("---")
st.info("Dashboard MVP by [your team]. Звʼяжись з @topvlad або @lostframe_404 для вдосконалення/розширення!")
