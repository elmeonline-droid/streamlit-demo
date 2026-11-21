from datetime import datetime, timedelta

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Feed Levels", page_icon="🌾", layout="wide")

st.title("🌾 Feed Levels: Last 7 Days")


# ---------- Data ----------
INTERVAL = "10min"  # one data point per bin every 10 minutes


def to_interval(df: pd.DataFrame) -> pd.DataFrame:
    """Average readings into 10-minute slots per bin (empty slots are left out, not invented)."""
    return (
        df.set_index("timestamp")
        .groupby("bin")["level"]
        .resample(INTERVAL)
        .mean()
        .dropna()
        .round(1)
        .reset_index()
    )


def sample_data(seed: int = 7) -> pd.DataFrame:
    """Readings every 10 minutes for 3 bins over 7 days: steady draw-down with refills."""
    rng = np.random.default_rng(seed)
    now = datetime.now()
    end = now.replace(minute=now.minute - now.minute % 10, second=0, microsecond=0)
    times = pd.date_range(end=end, periods=7 * 24 * 6, freq=INTERVAL)
    rows = []
    for bin_name, start, use_per_hr in [("Bin 1", 85, 0.55), ("Bin 2", 60, 0.40), ("Bin 3", 95, 0.70)]:
        level = start
        for t in times:
            level -= use_per_hr / 6 * rng.uniform(0.6, 1.4)
            if level < 15 and rng.random() < 0.06:  # refill delivery
                level = rng.uniform(90, 100)
            level = max(level, 0)
            rows.append({"timestamp": t, "bin": bin_name, "level": round(level, 1)})
    return pd.DataFrame(rows)


def load_csv(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = {"timestamp", "bin", "level"} - set(df.columns)
    if missing:
        st.error(f"CSV is missing column(s): {', '.join(sorted(missing))}. "
                 "Expected columns: timestamp, bin, level")
        st.stop()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["bin"] = df["bin"].astype(str)
    df["level"] = pd.to_numeric(df["level"], errors="coerce")
    return to_interval(df.dropna(subset=["level"]))


with st.sidebar:
    st.header("Data")
    uploaded = st.file_uploader("Upload CSV (timestamp, bin, level)", type="csv")
    st.caption("No file? Sample data is shown. Readings are averaged into 10-minute points.")
    st.header("Settings")
    unit = st.text_input("Level unit", value="%")
    low_level = st.number_input(f"Low-level alarm ({unit})", value=20.0, step=5.0)

df = load_csv(uploaded) if uploaded else sample_data()
if not uploaded:
    st.info("Showing **sample data**. Upload a CSV in the sidebar to chart your real feed levels.")

# Keep only the 7 days ending at the latest reading
latest_time = df["timestamp"].max()
df = df[df["timestamp"] >= latest_time - timedelta(days=7)].sort_values("timestamp")

bins = sorted(df["bin"].unique())
selected = st.sidebar.multiselect("Bins", bins, default=bins)
df = df[df["bin"].isin(selected)]
if df.empty:
    st.warning("No data to show.")
    st.stop()

# ---------- Current status ----------
st.subheader("Current status")
cols = st.columns(len(selected))
for col, b in zip(cols, selected):
    d = df[df["bin"] == b]
    current = d["level"].iloc[-1]
    # Average usage per day from drops only (ignores refills)
    drops = -d["level"].diff().clip(upper=0)
    hours = (d["timestamp"].iloc[-1] - d["timestamp"].iloc[0]).total_seconds() / 3600
    per_day = drops.sum() / hours * 24 if hours > 0 else 0
    days_left = current / per_day if per_day > 0 else float("inf")
    col.metric(
        b,
        f"{current:.1f} {unit}",
        f"-{per_day:.1f} {unit}/day",
        delta_color="inverse",
    )
    if current <= low_level:
        col.error("Below alarm level")
    elif days_left < 2:
        col.warning(f"~{days_left:.1f} days until empty")
    else:
        col.caption(f"~{days_left:.1f} days until empty")

# ---------- Chart ----------
st.subheader("Feed level: 7-day trend")
lines = (
    alt.Chart(df)
    .mark_line()
    .encode(
        x=alt.X("timestamp:T", title=None, axis=alt.Axis(format="%a %b %d")),
        y=alt.Y("level:Q", title=f"Level ({unit})"),
        color=alt.Color("bin:N", title="Bin"),
        tooltip=[
            alt.Tooltip("bin:N", title="Bin"),
            alt.Tooltip("timestamp:T", title="Time", format="%a %b %d %H:%M"),
            alt.Tooltip("level:Q", title=f"Level ({unit})", format=".1f"),
        ],
    )
)
alarm = (
    alt.Chart(pd.DataFrame({"y": [low_level]}))
    .mark_rule(strokeDash=[6, 4], color="red")
    .encode(y="y:Q")
)
st.altair_chart((lines + alarm).properties(height=420).interactive(), use_container_width=True)
st.caption(f"Dashed red line = low-level alarm ({low_level:g} {unit}). Scroll to zoom, drag to pan.")

# ---------- Daily summary ----------
st.subheader("Daily summary")
daily = (
    df.assign(day=df["timestamp"].dt.date)
    .groupby(["day", "bin"])["level"]
    .agg(min="min", max="max", end="last")
    .round(1)
    .unstack("bin")
)
st.dataframe(daily, use_container_width=True)

with st.expander("Raw data"):
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("Download CSV", df.to_csv(index=False), "feed_levels.csv", "text/csv")
