"""Feed dashboard computed straight from the raw scan + feed-round data (no dashboard sheet).

Polls the source Google Sheet every 5 minutes; all calculations live in feed.py.
"""
import io
import json
import time
import urllib.request

import altair as alt
import pandas as pd
import streamlit as st

import feed

# ---------- Data source ----------
# Override in Streamlit secrets with a [source] table (sheet_id, scans_gid, rounds_gid) to point elsewhere,
# e.g. at the scanner's own spreadsheet once it is shared.
DEFAULT_SOURCE = {"sheet_id": "1A8St9uqgQuXdHCgqqdRpxnTni-b0KymqyD_Hez5I64w",
                  "scans_gid": 1376488958, "rounds_gid": 1926467524}
TIMEZONE = "America/New_York"
REFRESH_SECONDS = 300

# Chart colors per mode (Google Sheets light chart colors / Google dark-theme equivalents)
PALETTES = {
    "light": dict(BLUE="#4285F4", RED="#EA4335", GREEN="#34A853", LIGHT_BLUE="#8AB4F8", ORANGE="#F29900",
                  BLACK="#000000", BG="#FFFFFF", TEXT="#202124", MUTED="#5F6368", GRID="#E8EAED", DOMAIN="#BDC1C6"),
    "dark": dict(BLUE="#8AB4F8", RED="#F28B82", GREEN="#81C995", LIGHT_BLUE="#4A6A9C", ORANGE="#FDD663",
                 BLACK="#E8EAED", BG="#1E1F20", TEXT="#E8EAED", MUTED="#9AA0A6", GRID="#3C4043", DOMAIN="#5F6368"),
}
BLUE = RED = GREEN = LIGHT_BLUE = ORANGE = BLACK = BG = TEXT = MUTED = GRID = DOMAIN = ""
GROUP_COLORS: dict = {}


def apply_palette(mode: str) -> None:
    global BLUE, RED, GREEN, LIGHT_BLUE, ORANGE, BLACK, BG, TEXT, MUTED, GRID, DOMAIN, GROUP_COLORS
    p = PALETTES[mode]
    BLUE, RED, GREEN, LIGHT_BLUE, ORANGE, BLACK = p["BLUE"], p["RED"], p["GREEN"], p["LIGHT_BLUE"], p["ORANGE"], p["BLACK"]
    BG, TEXT, MUTED, GRID, DOMAIN = p["BG"], p["TEXT"], p["MUTED"], p["GRID"], p["DOMAIN"]
    GROUP_COLORS = {1: BLUE, 2: RED, 3: GREEN}


# Page restyle for dark mode (Streamlit's own theme can't be switched from code)
DARK_CSS = """
<style>
.stApp, [data-testid="stHeader"] { background: #131314; color: #E8EAED; }
[data-testid="stSidebar"] { background: #1E1F20; }
.stApp h1, .stApp h2, .stApp h3, .stApp p, .stApp label, .stApp li,
[data-testid="stMetricValue"], [data-testid="stMetricLabel"] p, [data-testid="stWidgetLabel"] p { color: #E8EAED; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: #9AA0A6; }
[data-testid="stVerticalBlockBorderWrapper"], div[data-testid="stVerticalBlock"][height] { border-color: #3C4043 !important; }
.stApp hr { border-color: #3C4043; }
.stApp input, [data-baseweb="input"], [data-baseweb="base-input"] { background: #2A2B2D !important; color: #E8EAED !important; }
.stApp button { background: #2A2B2D; color: #E8EAED; border-color: #5F6368; }
.stApp button:hover { border-color: #8AB4F8; color: #8AB4F8; }
[data-testid="stToolbar"] button, [data-testid="stHeader"] svg { color: #E8EAED; fill: #E8EAED; }
</style>
"""

st.set_page_config(page_title="Feed Dashboard", page_icon="🌾", layout="wide")


def default_dark() -> bool:
    if "theme" in st.query_params:
        return st.query_params["theme"] == "dark"
    try:
        return st.context.theme.type == "dark"   # follow the viewer's system/browser setting
    except Exception:
        return False


def source() -> dict:
    try:
        return {**DEFAULT_SOURCE, **dict(st.secrets["source"])}
    except Exception:
        return DEFAULT_SOURCE


def fetch_csv(sheet_id: str, gid: int, cols: str) -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}&range={cols}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return pd.read_csv(io.StringIO(resp.read().decode("utf-8")), dtype=str, keep_default_na=False)


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner="Reading scans and feed rounds…")
def load() -> tuple[pd.DataFrame, pd.DataFrame, float]:
    src = source()
    scans = feed.clean_scans(fetch_csv(src["sheet_id"], src["scans_gid"], "A:E"))
    rounds = feed.clean_rounds(fetch_csv(src["sheet_id"], src["rounds_gid"], "A:I"))
    return scans, rounds, time.time()


def now_local() -> pd.Timestamp:
    return pd.Timestamp.now(tz=TIMEZONE).tz_localize(None)


def fmt_time(t) -> str:
    return "—" if t is None or pd.isna(t) else t.strftime("%a %I:%M %p").replace(" 0", " ")


# ---------- Chart helpers (styled like Google Sheets charts) ----------
def slot_x(labels: list[str], every: int | None = None) -> alt.X:
    n = len(labels)
    ticks = [i for i in range(0, n, every)] if every else [i for i, lab in enumerate(labels) if lab]
    return alt.X("i:O", title=None, scale=alt.Scale(domain=list(range(n)), paddingInner=0.15),
                 axis=alt.Axis(values=ticks, labelExpr=f"{json.dumps(labels)}[datum.value]",
                               labelAngle=0, grid=False, ticks=False, labelOverlap=True))


def mid(x: alt.X) -> alt.X:
    """Same axis, marks centred in each slot (so lines line up with bars)."""
    x = x.copy()
    x.bandPosition = 0.5
    return x


def time_x(fmt: str = "%-I %p") -> alt.X:
    return alt.X("t:T", title=None, axis=alt.Axis(format=fmt, labelAngle=0, grid=False, labelOverlap=True))


def finish(chart, title: str, height: int):
    return chart.properties(title=alt.TitleParams(title, anchor="start", fontSize=15, fontWeight="normal",
                                                  color=TEXT), height=height)


def show(chart) -> None:
    st.altair_chart(
        chart.configure(background=BG, font="Roboto, Arial, sans-serif")
        .configure_view(stroke=None)
        .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor=GRID, domainColor=DOMAIN)
        .configure_legend(orient="bottom", title=None, labelColor=TEXT),
        use_container_width=True, theme=None)


def color_scale(colors: dict) -> alt.Scale:
    return alt.Scale(domain=list(colors), range=list(colors.values()))


def bars(df: pd.DataFrame, x: alt.X, colors: dict, y_max: float | None = None):
    enc = dict(
        x=x,
        y=alt.Y("value:Q", title=None, scale=alt.Scale(domain=[0, y_max]) if y_max else alt.Undefined),
        color=alt.Color("series:N", scale=color_scale(colors), legend=alt.Legend() if len(colors) > 1 else None),
        tooltip=[alt.Tooltip("series:N", title="Series"), alt.Tooltip("label:N", title="Time"),
                 alt.Tooltip("value:Q", title="Value", format=".1f")],
    )
    if len(colors) > 1:
        enc["xOffset"] = alt.XOffset("series:N", sort=list(colors))
    return alt.Chart(df).mark_bar().encode(**enc)


def delivery_frame(rounds, start, n, labels, groups=(1, 2, 3)) -> pd.DataFrame:
    df = feed.delivered_slots(rounds, start, n, groups)
    df["series"] = df["group"].map(lambda g: f"Milking {int(g)}")
    df["label"] = df["i"].map(lambda i: labels[i])
    return df


# ---------- Sections ----------
def runout_section(scans, rounds, now, threshold) -> None:
    st.subheader("Feed Runout Projection")
    for col, g in zip(st.columns(3), (1, 2, 3)):
        r = feed.runout(scans, rounds, g, threshold, now)
        with col, st.container(border=True):
            st.markdown(f"**<span style='color:{GROUP_COLORS[g]}'>●</span> Group {g}**", unsafe_allow_html=True)
            a, b = st.columns(2)
            label = "Below since" if r.already_below else "Runout"
            if r.runout is None or pd.isna(r.runout):
                a.metric(label, "—")
            else:
                day = "today" if r.runout.date() == now.date() else r.runout.strftime("%a")
                a.metric(f"{label} ({day})", r.runout.strftime("%I:%M %p").lstrip("0"))
            b.metric("Height (in)", "—" if r.height is None else f"{r.height:.1f}")
            mins = "  ·  ".join(f"{f} {'—' if v is None else f'{v:.1f}'}" for f, v in r.fence_min_24h.items())
            st.caption(f"24hr minimum heights: {mins}")
            rate = "—" if r.rate is None else f"{r.rate:.2f} in/hr"
            st.caption(f"Typical drawdown: {rate} · last full scan {fmt_time(r.height_time)}")
    st.caption("Height = highest of the 4 fences (inches). Runout = when all 4 fences drop below the threshold, "
               "based on each group's typical drawdown after deliveries over the last 7 days.")


def group_section(scans, rounds, now) -> None:
    for g in (1, 2, 3):
        df, labels = feed.day_overlay(scans, g, now)
        x = slot_x(labels, every=3)
        layers = []
        for days_ago, color, width in [(None, LIGHT_BLUE, 1.5), (0, RED, 2.5)]:
            part = df[df["days_ago"] > 0] if days_ago is None else df[df["days_ago"] == 0]
            layers.append(alt.Chart(part).mark_line(color=color, strokeWidth=width, point=alt.OverlayMarkDef(
                color=color, size=30, filled=True)).encode(
                x=mid(x), y=alt.Y("value:Q", title=None), detail="series:N",
                tooltip=[alt.Tooltip("series:N", title="Day"), alt.Tooltip("label:N", title="Time"),
                         alt.Tooltip("value:Q", title="Height (in, 4 fences)", format=".1f")]))
        show(finish(alt.layer(*layers), f"Group {g}", 300))

        start = (now - pd.Timedelta(hours=24)).floor("20min")
        strip = delivery_frame(rounds, start, 72, labels, groups=(g,))
        top = max(60.0, float(strip["value"].max()) if len(strip) else 0.0)
        show(finish(bars(strip, slot_x(labels, every=3), {f"Milking {g}": GROUP_COLORS[g]}, y_max=top), "", 110))
    st.caption("Line = total feed height of the group's 4 fences. Red = last 24 hours · light blue = the same "
               "hours on each of the previous 6 days · bars = feed delivered (36.04-lb units) per 20 minutes")


def milking_section(scans, rounds, now) -> None:
    rows = []
    for g in (1, 2, 3):
        h = feed.group_heights(scans[scans["t"] >= now - pd.Timedelta(days=2)], g)
        rows.append(h.assign(series=f"Milking {g}"))
    df = pd.concat(rows)
    colors = {f"Milking {g}": GROUP_COLORS[g] for g in (1, 2, 3)}
    chart = alt.Chart(df).mark_line(point=alt.OverlayMarkDef(size=30, filled=True)).encode(
        x=time_x("%a %-I %p"), y=alt.Y("sum:Q", title=None),
        color=alt.Color("series:N", scale=color_scale(colors)),
        tooltip=[alt.Tooltip("series:N", title="Group"), alt.Tooltip("t:T", title="Scan", format="%a %-I:%M %p"),
                 alt.Tooltip("sum:Q", title="Height (in, 4 fences)", format=".1f")])
    show(finish(chart, "Milking groups - feed height (last 2 days)", 320))

    for title, span, n, every, fmt in [
        ("Milking groups - feed delivered (36.04-lb units, last 2 days)", pd.Timedelta(days=2), 144, 9, "%I:%M"),
        ("Milking groups - feed delivered (36.04-lb units, last 16 hours)", pd.Timedelta(hours=16), 48, 3, "%I:%M %p"),
    ]:
        start = (now - span).round("10min")
        labels = feed.slot_labels(start, n, fmt)
        show(finish(bars(delivery_frame(rounds, start, n, labels), slot_x(labels, every=every), colors), title, 200))


def heifer_chart(scans, rounds, pen, now):
    ev = feed.heifer_events(scans, rounds, pen, now)
    labels = [t.round("h").strftime("%a %I %p").replace(" 0", " ") for t in ev["t"]]
    ev = ev.assign(i=range(len(ev)), label=labels)
    long = ev.melt(id_vars=["i", "label"], value_vars=["dosing", "delivered", "scan"], var_name="series").dropna()
    long["series"] = long["series"].str.capitalize()
    x = slot_x(labels)
    b = bars(long, x, {"Dosing": ORANGE, "Delivered": BLACK, "Scan": GREEN}, y_max=600)
    empty = ev[ev["empty"].notna()]
    e = alt.Chart(empty).mark_point(shape="triangle-up", size=90, filled=True, color=RED).encode(
        x=mid(x), y="empty:Q", tooltip=[alt.Tooltip("label:N", title="Time"), alt.Tooltip("empty:Q", title="Empty")])
    return finish(alt.layer(b, e), f"{pen} - Dosing, delivered & scans (4 days)", 260)


def heifer_section(scans, rounds, now) -> None:
    delivered = "White" if BG != PALETTES["light"]["BG"] else "Black"
    dosing = "Yellow" if BG != PALETTES["light"]["BG"] else "Orange"
    st.caption(f"{dosing} = dosing · {delivered} = delivered · Green = scan (inches × 12.5 ≈ lb) · "
               "Red ▲ at 0 = empty")
    pens = feed.HEIFER_PENS
    for k in range(0, len(pens), 2):
        for col, pen in zip(st.columns(2), pens[k:k + 2]):
            with col:
                show(heifer_chart(scans, rounds, pen, now))


def fence_section(scans, now) -> None:
    day = scans[scans["t"] >= now - pd.Timedelta(hours=24)]
    fences = [f for g in (1, 2, 3) for f in feed.MILKING_FENCES[g]]
    for k in range(0, len(fences), 2):
        for col, fence in zip(st.columns(2), fences[k:k + 2]):
            d = day[day["pen"] == fence]
            top = max(6.0, float(d["inches"].max()) + 0.5) if len(d) else 6.0
            line = alt.Chart(d).mark_line(color=GROUP_COLORS[int(fence[0])], strokeWidth=2).encode(
                x=time_x(), y=alt.Y("inches:Q", title=None, scale=alt.Scale(domain=[-1, top])),
                tooltip=[alt.Tooltip("t:T", title="Scan", format="%a %-I:%M %p"),
                         alt.Tooltip("inches:Q", title="Height (in)", format=".2f")])
            with col:
                show(finish(line, f"{fence} - feed height (inches, last 24 hours)", 170))


# ---------- Page ----------
with st.sidebar:
    dark = st.toggle("🌙 Dark mode", value=default_dark())
    threshold = st.number_input("Runout threshold (in)", value=0.98, step=0.1, format="%.2f")
st.query_params["theme"] = "dark" if dark else "light"   # keep the choice in the link
apply_palette("dark" if dark else "light")
if dark:
    st.markdown(DARK_CSS, unsafe_allow_html=True)

st.title("🌾 Feed Dashboard")


@st.fragment(run_every=REFRESH_SECONDS)
def dashboard() -> None:
    try:
        scans, rounds, fetched = load()
    except Exception as exc:
        st.error(f"Couldn't read the source data: {exc}")
        return
    now = now_local()

    top = st.columns([4, 1])
    top[0].caption(
        f"Computed from raw scans and feed rounds · refreshes every {REFRESH_SECONDS // 60} min · "
        f"read {int((time.time() - fetched) // 60)} min ago · latest scan {fmt_time(scans['t'].max())} · "
        f"latest delivery {fmt_time(rounds['t'].max())}")
    if top[1].button("Refresh now", use_container_width=True):
        load.clear()
        st.rerun(scope="fragment")

    runout_section(scans, rounds, now, threshold)
    st.divider()
    group_section(scans, rounds, now)
    st.divider()
    st.subheader("Milking groups")
    milking_section(scans, rounds, now)
    st.divider()
    st.subheader("Heifers")
    heifer_section(scans, rounds, now)
    st.divider()
    st.subheader("Fences")
    fence_section(scans, now)


dashboard()
