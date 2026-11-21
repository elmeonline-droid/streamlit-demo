"""Feed dashboard: mirrors the charts on the Google Sheet's Dashboard tab.

Reads the sheet's tabs live (public CSV export) and refreshes every 5 minutes.
"""
import io
import json
import time
import urllib.request

import altair as alt
import pandas as pd
import streamlit as st

# ---------- Sheet location ----------
SHEET_ID = "1WoOOJKbGkDWi8ojDmfiGe-Ntkc1HFzyorQa1X3MQOM0"
TABS = {"dash": 1479309119, "fr": 1017175221, "calc": 1118299510}  # Dashboard, FR Data, Calc Data
REFRESH_SECONDS = 300  # poll every 5 minutes

# ---------- Google Sheets chart colors ----------
BLUE, RED, GREEN = "#4285F4", "#EA4335", "#34A853"
LIGHT_BLUE, ORANGE, BLACK = "#8AB4F8", "#F29900", "#000000"
GROUP_COLORS = {1: BLUE, 2: RED, 3: GREEN}

st.set_page_config(page_title="Feed Dashboard", page_icon="🌾", layout="wide")


# ---------- Data access ----------
@st.cache_data(ttl=REFRESH_SECONDS, show_spinner="Reading Google Sheet…")
def load_tabs() -> tuple[dict, float]:
    tabs = {}
    for key, gid in TABS.items():
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            text = resp.read().decode("utf-8")
        tabs[key] = pd.read_csv(io.StringIO(text), header=None, dtype=str, keep_default_na=False)
    return tabs, time.time()


def col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def col_letters(index: int) -> str:
    s, n = "", index + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def cell(df: pd.DataFrame, col: str, row: int) -> str:
    """One cell by sheet address (e.g. 'B', 5). Blank if outside the exported area."""
    r, c = row - 1, col_index(col)
    return df.iat[r, c].strip() if r < df.shape[0] and c < df.shape[1] else ""


def cells(df: pd.DataFrame, col: str, r1: int, r2: int) -> list[str]:
    return [cell(df, col, r) for r in range(r1, r2 + 1)]


def nums(values: list[str]) -> pd.Series:
    """Numbers; #N/A, #REF!, blanks -> NaN."""
    return pd.to_numeric(pd.Series(values), errors="coerce")


def shift(col: str, k: int) -> str:
    return col_letters(col_index(col) + k)


# ---------- Chart helpers ----------
def slot_x(labels: list[str], every: int | None = None) -> alt.X:
    """Category axis over slot index 0..n-1, labelled like the sheet (every Nth label, or all non-blank)."""
    n = len(labels)
    if every:
        ticks = [i for i in range(0, n, every) if labels[i]]
    else:
        ticks = [i for i, lab in enumerate(labels) if lab]
    return alt.X(
        "i:O",
        title=None,
        scale=alt.Scale(domain=list(range(n)), paddingInner=0.15),
        axis=alt.Axis(values=ticks, labelExpr=f"{json.dumps(labels)}[datum.value]",
                      labelAngle=0, grid=False, ticks=False, labelOverlap=True),
    )


def mid(x: alt.X) -> alt.X:
    """Same axis, but marks sit in the middle of each slot (so lines line up with bars)."""
    x = x.copy()
    x.bandPosition = 0.5
    return x


def finish(chart: alt.Chart, title: str, height: int) -> alt.Chart:
    return chart.properties(
        title=alt.TitleParams(title, anchor="start", fontSize=15, fontWeight="normal", color="#202124"),
        height=height,
    )


def show(chart: alt.Chart) -> None:
    st.altair_chart(
        chart.configure(background="white", font="Roboto, Arial, sans-serif")
        .configure_view(stroke=None)
        .configure_axis(labelColor="#5f6368", titleColor="#5f6368", gridColor="#e8eaed", domainColor="#bdc1c6")
        .configure_legend(orient="bottom", title=None, labelColor="#202124"),
        use_container_width=True,
        theme=None,
    )


def line_layer(df: pd.DataFrame, x: alt.X, color: str, points: bool = True, width: float = 2) -> alt.Chart:
    return alt.Chart(df).mark_line(color=color, strokeWidth=width, point=points and alt.OverlayMarkDef(
        color=color, size=30, filled=True)).encode(
        x=mid(x),
        y=alt.Y("value:Q", title=None),
        detail="series:N",
        tooltip=[alt.Tooltip("series:N", title="Series"), alt.Tooltip("label:N", title="Time"),
                 alt.Tooltip("value:Q", title="Value", format=".2f")],
    )


def bars(df: pd.DataFrame, x: alt.X, colors: dict, y_max: float | None = None, grouped: bool = True) -> alt.Chart:
    enc = dict(
        x=x,
        y=alt.Y("value:Q", title=None, scale=alt.Scale(domain=[0, y_max]) if y_max else alt.Undefined),
        color=alt.Color("series:N", scale=alt.Scale(domain=list(colors), range=list(colors.values())),
                        legend=alt.Legend() if len(colors) > 1 else None),
        tooltip=[alt.Tooltip("series:N", title="Series"), alt.Tooltip("label:N", title="Time"),
                 alt.Tooltip("value:Q", title="Value", format=".1f")],
    )
    if grouped and len(colors) > 1:
        enc["xOffset"] = alt.XOffset("series:N", sort=list(colors))
    return alt.Chart(df).mark_bar().encode(**enc)


def long_frame(labels: list[str], series: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for name, vals in series.items():
        for i, v in enumerate(vals):
            if pd.notna(v):
                rows.append({"i": i, "label": labels[i], "series": name, "value": float(v)})
    return pd.DataFrame(rows, columns=["i", "label", "series", "value"])


# ---------- Sections ----------
def runout_projection(dash: pd.DataFrame) -> None:
    st.subheader(cell(dash, "A", 1) or "Feed Runout Projection")
    cols = st.columns(3)
    for k, col in enumerate(cols):
        r = 2 + k
        with col, st.container(border=True):
            st.markdown(f"**<span style='color:{GROUP_COLORS[k + 1]}'>●</span> {cell(dash, 'A', r)}**",
                        unsafe_allow_html=True)
            a, b = st.columns(2)
            a.metric("Projected runout", cell(dash, "B", r) or "—")
            b.metric("Height (in)", cell(dash, "C", r) or "—")
            st.caption(f"24hr minimum heights: {cell(dash, 'D', r)}")
            st.caption(f"Runout target: {cell(dash, 'F', r)} hrs")
    st.caption(f"**{cell(dash, 'A', 5)}** {cell(dash, 'B', 5)}  ·  {cell(dash, 'A', 6)}")


def group_charts(fr: pd.DataFrame) -> None:
    slots = cells(fr, "AH", 2, 73)          # 20-minute slots over 24 h
    strip_labels = cells(fr, "AG", 2, 73)
    x = slot_x(slots, every=3)
    for g, first in [(1, "AI"), (2, "AP"), (3, "AW")]:
        letters = [shift(first, k) for k in range(7)]   # 6 prior days + last 24h
        series = {cell(fr, c, 1): nums(cells(fr, c, 2, 73)) for c in letters}
        names = list(series)
        prior = long_frame(slots, {n: series[n] for n in names[:6]})
        today = long_frame(slots, {names[6]: series[names[6]]})
        chart = alt.layer(line_layer(prior, x, LIGHT_BLUE, width=1.5), line_layer(today, x, RED, width=2.5))
        show(finish(chart, f"Group {g}", 300))

        dcol = {1: "EK", 2: "EL", 3: "EM"}[g]
        name = cell(fr, dcol, 1)
        strip = long_frame(strip_labels, {name: nums(cells(fr, dcol, 2, 73))})
        show(finish(bars(strip, slot_x(strip_labels, every=3), {name: GROUP_COLORS[g]}, y_max=60), "", 110))
    st.caption("Light blue = each of the previous 6 days · Red = last 24 hours · Bars = feed delivered per slot")


def milking_charts(fr: pd.DataFrame, calc: pd.DataFrame) -> None:
    labels = cells(calc, "GE", 2, 501)
    last = max((i for i, v in enumerate(labels) if v), default=-1)
    labels = labels[: last + 1]
    series = {cell(calc, c, 1): nums(cells(calc, c, 2, 1 + len(labels))) for c in ["GF", "GG", "GH"]}
    colors = dict(zip(series, [BLUE, RED, GREEN]))
    x = slot_x(labels, every=max(1, len(labels) // 12))
    layers = [line_layer(long_frame(labels, {n: s}), x, colors[n]) for n, s in series.items()]
    # invisible layer just to draw a legend
    legend = alt.Chart(pd.DataFrame({"series": list(colors)})).mark_point(opacity=0).encode(
        color=alt.Color("series:N", scale=alt.Scale(domain=list(colors), range=list(colors.values())),
                        legend=alt.Legend(symbolOpacity=1, symbolFillColor=None)))
    show(finish(alt.layer(*layers, legend), "Milking groups - feed height (last 2 days)", 320))

    for title, cols, label_col, r2, every in [
        ("Milking groups - feed delivered (36.04-lb units, last 2 days)", ["S", "T", "U"], "AB", 145, 9),
        ("Milking groups - feed delivered (36.04-lb units, last 16 hours)", ["X", "Y", "Z"], "BR", 49, 3),
    ]:
        labels = cells(fr, label_col, 2, r2)
        series = {cell(fr, c, 1): nums(cells(fr, c, 2, r2)) for c in cols}
        df = long_frame(labels, series)
        show(finish(bars(df, slot_x(labels, every=every), dict(zip(series, [BLUE, RED, GREEN]))), title, 200))


HEIFERS = [  # (name, event-time column); the next 5 columns are Event, Dosing, Delivered, Scan, Empty
    ("Big Hfr 10", "MV"), ("Big Hfr 11", "NG"), ("Big Hfr 12", "NR"), ("Big Hfr 13", "OC"),
    ("Hfr 14", "LD"), ("Hfr 15", "LO"), ("Hfr 16", "LZ"), ("Hfr 17", "MK"),
]


def heifer_chart(calc: pd.DataFrame, name: str, tcol: str) -> alt.Chart:
    times = nums(cells(calc, tcol, 2, 33))
    events = cells(calc, shift(tcol, 1), 2, 33)
    keep = [i for i, e in enumerate(events) if e]
    labels = []
    for i in keep:
        t = times[i]
        day = pd.to_datetime(t, unit="D", origin="1899-12-30").strftime("%a ") if pd.notna(t) else ""
        labels.append(f"{day}{events[i]}")
    series = {}
    for k, s in enumerate(["Dosing", "Delivered", "Scan", "Empty"], start=2):
        vals = nums(cells(calc, shift(tcol, k), 2, 33))
        series[s] = pd.Series([vals[i] for i in keep])
    x = slot_x(labels)
    bar_df = long_frame(labels, {s: series[s] for s in ["Dosing", "Delivered", "Scan"]})
    empty_df = long_frame(labels, {"Empty": series["Empty"]})
    b = bars(bar_df, x, {"Dosing": ORANGE, "Delivered": BLACK, "Scan": "#33A854"}, y_max=600)
    e = alt.Chart(empty_df).mark_point(shape="triangle-up", size=90, filled=True, color="#EA4235").encode(
        x=mid(x), y="value:Q",
        tooltip=[alt.Tooltip("label:N", title="Time"), alt.Tooltip("series:N", title="Event")])
    return finish(alt.layer(b, e), f"{name} - Dosing, delivered & scans (4 days)", 260)


def heifer_charts(calc: pd.DataFrame) -> None:
    st.caption("Orange = dosing · Black = delivered · Green = scan · Red ▲ at 0 = empty")
    for k in range(0, len(HEIFERS), 2):
        cols = st.columns(2)
        for col, (name, tcol) in zip(cols, HEIFERS[k:k + 2]):
            with col:
                show(heifer_chart(calc, name, tcol))


FENCES = [  # (fence, label column); the value column is the next one
    ("1A", "CD"), ("1B", "CI"), ("1C", "CN"), ("1D", "CS"),
    ("2A", "CX"), ("2B", "DC"), ("2C", "DH"), ("2D", "DM"),
    ("3A", "DR"), ("3B", "DW"), ("3C", "EB"), ("3D", "EG"),
]


def fence_charts(fr: pd.DataFrame) -> None:
    for k in range(0, len(FENCES), 2):
        cols = st.columns(2)
        for col, (fence, lcol) in zip(cols, FENCES[k:k + 2]):
            labels = cells(fr, lcol, 2, 61)
            vals = nums(cells(fr, shift(lcol, 1), 2, 61))
            df = long_frame(labels, {fence: vals})
            x = slot_x(labels)
            line = alt.Chart(df).mark_line(color=GROUP_COLORS[int(fence[0])], strokeWidth=2).encode(
                x=mid(x),
                y=alt.Y("value:Q", title=None, scale=alt.Scale(domain=[-1, 6])),
                tooltip=[alt.Tooltip("value:Q", title="Height (in)", format=".2f")],
            )
            with col:
                show(finish(line, f"{fence} - feed height (inches, last 24 hours)", 170))


# ---------- Page ----------
st.title("🌾 Feed Dashboard")


@st.fragment(run_every=REFRESH_SECONDS)
def dashboard() -> None:
    try:
        tabs, fetched = load_tabs()
    except Exception as exc:  # network / sharing problems
        st.error(f"Couldn't read the Google Sheet: {exc}")
        return

    top = st.columns([4, 1])
    top[0].caption(f"Live from Google Sheets · refreshes every {REFRESH_SECONDS // 60} min · "
                   f"last read {int((time.time() - fetched) // 60)} min ago")
    if top[1].button("Refresh now", use_container_width=True):
        load_tabs.clear()
        st.rerun(scope="fragment")

    runout_projection(tabs["dash"])
    st.divider()
    group_charts(tabs["fr"])
    st.divider()
    st.subheader("Milking groups")
    milking_charts(tabs["fr"], tabs["calc"])
    st.divider()
    st.subheader("Heifers")
    heifer_charts(tabs["calc"])
    st.divider()
    st.subheader("Fences")
    fence_charts(tabs["fr"])


dashboard()
