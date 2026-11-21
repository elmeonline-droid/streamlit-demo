import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Streamlit Demo", page_icon="📊", layout="wide")

st.title("📊 Streamlit Demo")
st.write("A starter app. Edit `app.py` and push to GitHub to update it.")

with st.sidebar:
    st.header("Controls")
    points = st.slider("Number of points", 10, 500, 100)
    noise = st.slider("Noise", 0.0, 2.0, 0.5)
    seed = st.number_input("Random seed", value=42, step=1)

rng = np.random.default_rng(int(seed))
x = np.arange(points)
df = pd.DataFrame({
    "trend": np.cumsum(rng.normal(0, noise, points)),
    "sine": np.sin(x / 10) * 5 + rng.normal(0, noise, points),
})

col1, col2, col3 = st.columns(3)
col1.metric("Points", points)
col2.metric("Trend (last)", f"{df['trend'].iloc[-1]:.2f}")
col3.metric("Sine (mean)", f"{df['sine'].mean():.2f}")

st.subheader("Chart")
st.line_chart(df)

st.subheader("Data")
st.dataframe(df, use_container_width=True)

name = st.text_input("Your name")
if st.button("Say hello"):
    st.success(f"Hello, {name or 'world'}! 👋")
