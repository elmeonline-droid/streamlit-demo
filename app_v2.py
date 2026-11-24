"""Feed dashboard v2: status-first layout.

Top:   what needs feed next (group runout countdowns, fence heights, heifer pen tiles)
Below: tabs with the supporting charts (milking groups, fences, heifers, raw data)
All numbers come from feed.py (computed from the raw scans + feed rounds).
"""
import html
import io
import time
import urllib.request

import altair as alt
import pandas as pd
import streamlit as st

import feed

DEFAULT_SOURCE = {"sheet_id": "1A8St9uqgQuXdHCgqqdRpxnTni-b0KymqyD_Hez5I64w",
                  "scans_gid": 1376488958, "rounds_gid": 1926467524}
TIMEZONE = "America/New_York"
REFRESH_SECONDS = 300
STALE_MINUTES = 60          # warn when the newest scan is older than this
SOON_HOURS = 2              # runout within this many hours = "soon"

PALETTES = {
    "light": dict(bg="#FFFFFF", card="#FFFFFF", border="#DADCE0", text="#202124", muted="#5F6368",
                  grid="#E8EAED", prior="#BDC1C6", ok="#188038", warn="#E37400", bad="#D93025",
                  g1="#4285F4", g2="#EA4335", g3="#34A853", dosing="#F29900", delivered="#202124", scan="#34A853"),
    "dark": dict(bg="#1E1F20", card="#1E1F20", border="#3C4043", text="#E8EAED", muted="#9AA0A6",
                 grid="#3C4043", prior="#5F6368", ok="#81C995", warn="#FDD663", bad="#F28B82",
                 g1="#8AB4F8", g2="#F28B82", g3="#81C995", dosing="#FDD663", delivered="#E8EAED", scan="#81C995"),
}

st.set_page_config(page_title="Feed Status", page_icon="🌾", layout="wide", initial_sidebar_state="collapsed")


# ---------- Data ----------
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
def load():
    src = source()
    scans = feed.clean_scans(fetch_csv(src["sheet_id"], src["scans_gid"], "A:E"))
    rounds = feed.clean_rounds(fetch_csv(src["sheet_id"], src["rounds_gid"], "A:I"))
    return scans, rounds, time.time()


def now_local() -> pd.Timestamp:
    return pd.Timestamp.now(tz=TIMEZONE).tz_localize(None)


# ---------- Formatting ----------
def clock(t) -> str:
    return "—" if t is None or pd.isna(t) else t.strftime("%I:%M %p").lstrip("0")


def day_clock(t, now) -> str:
    if t is None or pd.isna(t):
        return "—"
    if t.date() == now.date():
        return clock(t)
    if t.date() == (now + pd.Timedelta(days=1)).date():
        return f"{clock(t)} tomorrow"
    return f"{t.strftime('%a')} {clock(t)}"


def duration(td: pd.Timedelta) -> str:
    mins = int(abs(td.total_seconds()) // 60)
    if mins < 60:
        return f"{mins}m"
    h, m = divmod(mins, 60)
    if h < 24:
        return f"{h}h {m:02d}m"
    return f"{h // 24}d {h % 24}h"


def ago(t, now) -> str:
    return "—" if t is None or pd.isna(t) else f"{duration(now - t)} ago"


# ---------- Theme ----------
def default_dark() -> bool:
    if "theme" in st.query_params:
        return st.query_params["theme"] == "dark"
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def page_css(p: dict, dark: bool) -> str:
    dark_rules = f"""
    .stApp, [data-testid="stHeader"] {{ background:#131314; color:{p['text']}; }}
    .stApp h1, .stApp h2, .stApp h3, .stApp p, .stApp label, .stApp li,
    [data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] {{ color:{p['text']}; }}
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ color:{p['muted']}; }}
    .stApp input, [data-baseweb="input"], [data-baseweb="base-input"] {{ background:#2A2B2D !important; color:{p['text']} !important; }}
    .stApp button {{ background:#2A2B2D; color:{p['text']}; border-color:{p['border']}; }}
    [data-baseweb="tab-list"] button {{ background:transparent; }}
    [data-baseweb="tab-list"] button p {{ color:{p['muted']}; }}
    [data-baseweb="tab-list"] button[aria-selected="true"] p {{ color:{p['text']}; }}
    [data-baseweb="tab-border"] {{ background:{p['border']}; }}
    [data-testid="stDataFrame"] {{ filter: invert(0.92) hue-rotate(180deg); }}
    [data-testid="stHeader"] svg {{ fill:{p['text']}; color:{p['text']}; }}
    """ if dark else ""
    return f"""<style>
    .block-container {{ padding-top: 2.2rem; }}
    .cards {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:12px; margin:4px 0 12px; }}
    .cards.small {{ grid-template-columns:repeat(4, 1fr); gap:10px; }}
    @media (max-width: 900px) {{ .cards {{ grid-template-columns:1fr; }} .cards.small {{ grid-template-columns:repeat(2, 1fr); }} }}
    .card {{ background:{p['card']}; border:1px solid {p['border']}; border-left:5px solid var(--accent);
             border-radius:10px; padding:12px 14px; color:{p['text']}; }}
    .card .head {{ display:flex; align-items:center; gap:8px; font-weight:600; font-size:0.95rem; }}
    .card .dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
    .card .badge {{ margin-left:auto; font-size:0.7rem; font-weight:700; letter-spacing:.04em; padding:2px 8px;
                    border-radius:999px; color:{p['bg']}; background:var(--accent); }}
    .card .big {{ font-size:1.9rem; font-weight:600; line-height:1.15; margin-top:6px; }}
    .card .mid {{ font-size:1.25rem; font-weight:600; margin-top:4px; }}
    .card .sub {{ color:{p['muted']}; font-size:0.85rem; }}
    .card .chips {{ display:flex; gap:6px; margin:10px 0 6px; flex-wrap:wrap; }}
    .card .chip {{ border:1px solid {p['border']}; border-radius:6px; padding:2px 7px; font-size:0.8rem;
                   font-variant-numeric:tabular-nums; }}
    .card .chip.low {{ border-color:{p['bad']}; color:{p['bad']}; font-weight:600; }}
    .card .foot {{ color:{p['muted']}; font-size:0.78rem; }}
    .ok {{ --accent:{p['ok']}; }} .warn {{ --accent:{p['warn']}; }} .bad {{ --accent:{p['bad']}; }}
    .none {{ --accent:{p['border']}; }}
    .fresh {{ color:{p['muted']}; font-size:0.85rem; margin-top:-6px; }}
    .fresh.stale {{ color:{p['bad']}; font-weight:600; }}
    {dark_rules}
    </style>"""


# ---------- Chart helpers ----------
def styled(chart, p: dict, height: int, title: str = ""):
    chart = chart.properties(height=height, title=alt.TitleParams(title, anchor="start", fontSize=14,
                                                                   fontWeight="normal", color=p["text"]))
    return (chart.configure(background=p["bg"], font="Roboto, Arial, sans-serif", padding=6)
            .configure_view(stroke=None)
            .configure_axis(labelColor=p["muted"], titleColor=p["muted"], gridColor=p["grid"],
                            domainColor=p["grid"], tickColor=p["grid"], labelFontSize=11, titleFontSize=11)
            .configure_legend(orient="bottom", title=None, labelColor=p["text"], symbolType="circle"))


def show(chart) -> None:
    st.altair_chart(chart, use_container_width=True, theme=None)


def gcolor(p, g) -> str:
    return p[f"g{g}"]


# ---------- Status section ----------
def group_cards(scans, rounds, now, threshold, p) -> str:
    latest = scans[scans["group"].notna()].groupby("pen").last()
    cards = []
    for g in (1, 2, 3):
        r = feed.runout(scans, rounds, g, threshold, now)
        if r.already_below:
            cls, badge, big = "bad", "BELOW", "Below threshold"
            sub = f"since {day_clock(r.runout, now)}"
        elif r.runout is None:
            cls, badge, big, sub = "none", "NO DATA", "No projection", "not enough recent scans"
        elif r.runout <= now:
            cls, badge, big = "bad", "OVERDUE", f"{duration(now - r.runout)} overdue"
            sub = f"projected {day_clock(r.runout, now)} · awaiting next scan"
        else:
            left = r.runout - now
            cls = "warn" if left <= pd.Timedelta(hours=SOON_HOURS) else "ok"
            badge = "SOON" if cls == "warn" else "OK"
            big, sub = f"in {duration(left)}", f"runs out ~{day_clock(r.runout, now)}"
        chips = []
        for f in feed.MILKING_FENCES[g]:
            v = latest["inches"].get(f)
            low = v is not None and not pd.isna(v) and v <= threshold
            chips.append(f'<span class="chip{" low" if low else ""}">{f} {"—" if v is None or pd.isna(v) else f"{v:.1f}"}</span>')
        rate = "—" if r.rate is None else f"{r.rate:.2f} in/hr"
        height = "—" if r.height is None else f"{r.height:.1f} in"
        cards.append(f"""
        <div class="card {cls}">
          <div class="head"><span class="dot" style="background:{gcolor(p, g)}"></span>Group {g}
               <span class="badge">{badge}</span></div>
          <div class="big">{big}</div>
          <div class="sub">{sub}</div>
          <div class="chips">{''.join(chips)}</div>
          <div class="foot">Highest fence {height} · drawdown {rate} · scanned {ago(r.height_time, now)}</div>
        </div>""")
    return f'<div class="cards">{"".join(cards)}</div>'


def heifer_cards(scans, rounds, now) -> str:
    cards = []
    for pen in feed.HEIFER_PENS:
        sc = scans[scans["pen"] == pen]
        dl = rounds[rounds["pen"] == pen]
        last_scan = sc.iloc[-1] if len(sc) else None
        last_del = dl.iloc[-1] if len(dl) else None
        if last_scan is None:
            cls, badge, level = "none", "NO DATA", "—"
        elif last_scan["inches"] == 0:
            cls, badge, level = "bad", "EMPTY", "Empty"
        else:
            cls, badge, level = "ok", "", f"~{last_scan['inches'] * feed.SCAN_TO_LB:.0f} lb"
        delivered = "no delivery in data" if last_del is None else \
            f"fed {last_del['lb']:.0f} lb {ago(last_del['t'], now)}"
        cards.append(f"""
        <div class="card {cls}">
          <div class="head">{html.escape(pen)}{f'<span class="badge">{badge}</span>' if badge else ''}</div>
          <div class="mid">{level}</div>
          <div class="sub">scanned {ago(None if last_scan is None else last_scan['t'], now)}</div>
          <div class="foot">{delivered} · dosing {feed.DOSING_LB.get(pen, '—')} lb</div>
        </div>""")
    return f'<div class="cards small">{"".join(cards)}</div>'


# ---------- Milking tab ----------
def group_day_chart(scans, rounds, g, now, p):
    df, _ = feed.day_overlay(scans, g, now)
    start = (now - pd.Timedelta(hours=24)).floor("20min")
    df["t"] = start + df["i"] * feed.SLOT + feed.SLOT / 2
    df["day"] = df["days_ago"].map(lambda k: "Last 24 h" if k == 0 else f"{k} day{'s' if k > 1 else ''} ago")
    x = alt.X("t:T", title=None, scale=alt.Scale(domain=[start, start + pd.Timedelta(hours=24)]),
              axis=alt.Axis(format="%-I %p", tickCount=8, grid=False, labelOverlap=True))
    y = alt.Y("value:Q", title="Height, 4 fences (in)", scale=alt.Scale(zero=True))
    tip = [alt.Tooltip("day:N", title="Day"), alt.Tooltip("t:T", title="Time of day", format="%-I:%M %p"),
           alt.Tooltip("value:Q", title="Height (in)", format=".1f")]
    prior = alt.Chart(df[df["days_ago"] > 0]).mark_circle(color=p["prior"], size=22, opacity=0.75).encode(
        x=x, y=y, tooltip=tip)
    today = alt.Chart(df[df["days_ago"] == 0]).mark_line(
        color=gcolor(p, g), strokeWidth=3, point=alt.OverlayMarkDef(color=gcolor(p, g), size=40, filled=True)
    ).encode(x=x, y=y, tooltip=tip)

    d = feed.delivered_slots(rounds, start, 72, groups=(g,))
    d["t0"] = start + d["i"] * feed.SLOT
    d["t1"] = d["t0"] + feed.SLOT
    top = max(60.0, float(d["value"].max()) if len(d) else 0.0) * 3.2   # bars use the bottom ~third
    bars = alt.Chart(d).mark_rect(color=gcolor(p, g), opacity=0.35).encode(
        x="t0:T", x2="t1:T",
        y=alt.Y("value:Q", scale=alt.Scale(domain=[0, top]), axis=None), y2=alt.datum(0),
        tooltip=[alt.Tooltip("t0:T", title="Delivered", format="%-I:%M %p"),
                 alt.Tooltip("value:Q", title="Units (36.04 lb)", format=".0f")])
    lines = alt.layer(prior, today)
    return alt.layer(bars, lines).resolve_scale(y="independent")


def all_groups_chart(scans, rounds, now, p):
    since = now - pd.Timedelta(days=2)
    heights = pd.concat([feed.group_heights(scans[scans["t"] >= since], g).assign(group=f"Group {g}") for g in (1, 2, 3)])
    colors = {f"Group {g}": gcolor(p, g) for g in (1, 2, 3)}
    cscale = alt.Scale(domain=list(colors), range=list(colors.values()))
    x = alt.X("t:T", title=None, scale=alt.Scale(domain=[since, now]),
              axis=alt.Axis(format="%a %-I %p", tickCount=12, grid=False, labelOverlap=True))
    lines = alt.Chart(heights).mark_line(strokeWidth=1.8, point=alt.OverlayMarkDef(size=16, filled=True)).encode(
        x=x, y=alt.Y("sum:Q", title="Height, 4 fences (in)"), color=alt.Color("group:N", scale=cscale),
        tooltip=[alt.Tooltip("group:N"), alt.Tooltip("t:T", title="Scan", format="%a %-I:%M %p"),
                 alt.Tooltip("sum:Q", title="Height (in)", format=".1f")])
    start = since.floor("20min")
    d = feed.delivered_slots(rounds, start, 144 + 1)
    d["t0"] = start + d["i"] * feed.SLOT
    d["t1"] = d["t0"] + feed.SLOT
    d["group"] = d["group"].map(lambda g: f"Group {int(g)}")
    d = d.sort_values(["i", "group"])
    d["y1"] = d.groupby("i")["value"].cumsum()      # stack groups within each slot
    d["y0"] = d["y1"] - d["value"]
    top = max(60.0, float(d["y1"].max()) if len(d) else 0.0) * 3.2
    bars = alt.Chart(d).mark_rect(opacity=0.45).encode(
        x="t0:T", x2="t1:T", y=alt.Y("y1:Q", scale=alt.Scale(domain=[0, top]), axis=None), y2="y0:Q",
        color=alt.Color("group:N", scale=cscale, legend=None),
        tooltip=[alt.Tooltip("group:N"), alt.Tooltip("t0:T", title="Delivered", format="%a %-I:%M %p"),
                 alt.Tooltip("value:Q", title="Units (36.04 lb)", format=".0f")])
    return alt.layer(bars, lines).resolve_scale(y="independent").interactive(bind_y=False)


# ---------- Fences tab ----------
def fence_chart(scans, fence, now, threshold, y_top, p):
    since = now - pd.Timedelta(hours=24)
    d = scans[(scans["pen"] == fence) & (scans["t"] >= since)]
    g = int(fence[0])
    x = alt.X("t:T", title=None, scale=alt.Scale(domain=[since, now]),
              axis=alt.Axis(format="%-I%p", tickCount=4, grid=False))
    y = alt.Y("inches:Q", title=None, scale=alt.Scale(domain=[0, y_top]), axis=alt.Axis(tickCount=4))
    area = alt.Chart(d).mark_area(color=gcolor(p, g), opacity=0.15, interpolate="step-after").encode(x=x, y=y)
    line = alt.Chart(d).mark_line(color=gcolor(p, g), strokeWidth=2, interpolate="step-after",
                                  point=alt.OverlayMarkDef(size=14, filled=True, color=gcolor(p, g))).encode(
        x=x, y=y, tooltip=[alt.Tooltip("t:T", title="Scan", format="%a %-I:%M %p"),
                           alt.Tooltip("inches:Q", title="Height (in)", format=".2f")])
    thr = alt.Chart(pd.DataFrame({"y": [threshold]})).mark_rule(color=p["bad"], strokeDash=[4, 3]).encode(y="y:Q")
    now_v = d["inches"].iloc[-1] if len(d) else None
    title = f"{fence} · now {now_v:.1f} in" if now_v is not None else f"{fence} · no scans"
    return alt.layer(area, line, thr), title


# ---------- Heifers tab ----------
def heifer_chart(scans, rounds, pen, now, y_top, p):
    ev = feed.heifer_events(scans, rounds, pen, now)
    since = now.normalize() - pd.Timedelta(days=3)
    x = alt.X("t:T", title=None, scale=alt.Scale(domain=[since, now]),
              axis=alt.Axis(format="%a %-I%p", tickCount=6, grid=False, labelOverlap=True))
    y_scale = alt.Scale(domain=[0, y_top])
    dl = ev[ev["delivered"].notna()].copy()
    dl["t0"] = dl["t"] - pd.Timedelta(minutes=50)
    dl["t1"] = dl["t"] + pd.Timedelta(minutes=50)
    bars = alt.Chart(dl).mark_rect(color=p["delivered"], opacity=0.85).encode(
        x=alt.X("t0:T", scale=alt.Scale(domain=[since, now])), x2="t1:T",
        y=alt.Y("delivered:Q", scale=y_scale, title="lb"), y2=alt.datum(0),
        tooltip=[alt.Tooltip("t:T", title="Delivered", format="%a %-I:%M %p"),
                 alt.Tooltip("delivered:Q", title="Delivered (lb)", format=".0f"),
                 alt.Tooltip("dosing:Q", title="Dosing (lb)", format=".0f")])
    dose = alt.Chart(dl).mark_tick(color=p["dosing"], thickness=3, size=16).encode(
        x=x, y=alt.Y("dosing:Q", scale=y_scale))
    sc = ev[ev["scan"].notna()]
    scan = alt.Chart(sc).mark_line(color=p["scan"], strokeWidth=2, point=alt.OverlayMarkDef(
        size=26, filled=True, color=p["scan"])).encode(
        x=x, y=alt.Y("scan:Q", scale=y_scale),
        tooltip=[alt.Tooltip("t:T", title="Scan", format="%a %-I:%M %p"),
                 alt.Tooltip("scan:Q", title="In bunk (≈lb)", format=".0f")])
    empty = alt.Chart(ev[ev["empty"].notna()]).mark_point(shape="triangle-up", size=110, filled=True,
                                                          color=p["bad"]).encode(x=x, y=alt.Y("empty:Q", scale=y_scale))
    return alt.layer(bars, dose, scan, empty)


# ---------- Page ----------
head = st.columns([5, 1.4, 1, 1], vertical_alignment="bottom")
head[0].markdown("## 🌾 Feed status")
st.session_state.setdefault("threshold", 0.98)
with head[1].popover(f"⚙ Threshold {st.session_state['threshold']:g} in", use_container_width=True):
    threshold = st.number_input("Runout threshold (in)", step=0.1, format="%.2f", key="threshold",
                                help="A group runs out when its highest fence drops below this height")
if head[2].button("↻ Refresh", use_container_width=True):
    load.clear()
dark = head[3].toggle("🌙 Dark", value=default_dark())
st.query_params["theme"] = "dark" if dark else "light"
P = PALETTES["dark" if dark else "light"]
st.markdown(page_css(P, dark), unsafe_allow_html=True)


@st.fragment(run_every=REFRESH_SECONDS)
def body() -> None:
    try:
        scans, rounds, fetched = load()
    except Exception as exc:
        st.error(f"Couldn't read the source data: {exc}")
        return
    now = now_local()
    last_scan = scans["t"].max()
    stale = pd.isna(last_scan) or (now - last_scan) > pd.Timedelta(minutes=STALE_MINUTES)
    st.markdown(
        f'<div class="fresh{" stale" if stale else ""}">{"⚠ Data may be stale · " if stale else ""}'
        f'Latest scan {ago(last_scan, now)} ({clock(last_scan)}) · latest delivery {ago(rounds["t"].max(), now)} · '
        f'updates every {REFRESH_SECONDS // 60} min</div>', unsafe_allow_html=True)

    st.markdown("#### Milking groups")
    st.markdown(group_cards(scans, rounds, now, threshold, P), unsafe_allow_html=True)
    st.markdown("#### Heifer pens")
    st.markdown(heifer_cards(scans, rounds, now), unsafe_allow_html=True)

    t_milk, t_fence, t_heifer, t_data = st.tabs(["📈 Milking groups", "🧱 Fences", "🐄 Heifers", "📋 Data"])

    with t_milk:
        st.caption("Bold line = last 24 h · grey dots = same hours on each of the previous 6 days · "
                   "shaded bars = feed delivered (36.04-lb units per 20 min)")
        for col, g in zip(st.columns(3), (1, 2, 3)):
            with col:
                show(styled(group_day_chart(scans, rounds, g, now, P), P, 260, f"Group {g} · last 24 hours"))
        show(styled(all_groups_chart(scans, rounds, now, P), P, 320,
                    "All groups · last 2 days (drag to pan, scroll to zoom)"))

    with t_fence:
        st.caption(f"Feed height per fence, last 24 hours · dashed line = runout threshold ({threshold:g} in)")
        day = scans[(scans["t"] >= now - pd.Timedelta(hours=24)) & scans["group"].notna()]
        y_top = max(6.0, float(day["inches"].max()) + 0.5) if len(day) else 6.0
        for g in (1, 2, 3):
            for col, fence in zip(st.columns(4), feed.MILKING_FENCES[g]):
                chart, title = fence_chart(scans, fence, now, threshold, y_top, P)
                with col:
                    show(styled(chart, P, 150, title))

    with t_heifer:
        st.caption("Bars = delivered (lb) · tick = dosing target · line = scan (in × 12.5 ≈ lb in bunk) · "
                   "▲ = empty · last 3 days + today")
        evs = [feed.heifer_events(scans, rounds, pen, now) for pen in feed.HEIFER_PENS]
        peak = max([float(e[["dosing", "delivered", "scan"]].max().max()) for e in evs if len(e)] + [100.0])
        y_top = peak * 1.1
        pens = feed.HEIFER_PENS
        for k in range(0, len(pens), 4):
            for col, pen in zip(st.columns(4), pens[k:k + 4]):
                with col:
                    show(styled(heifer_chart(scans, rounds, pen, now, y_top, P), P, 200, pen))

    with t_data:
        a, b = st.columns(2)
        with a:
            st.markdown("**Latest reading per fence / pen**")
            latest = scans.groupby("pen").last().reset_index()
            latest = latest.assign(**{"Height (in)": latest["inches"].round(2), "Scan": latest["t"].dt.strftime("%a %I:%M %p")})
            st.dataframe(latest[["pen", "Height (in)", "mm", "Scan"]].rename(columns={"pen": "Fence / pen", "mm": "mm"}),
                         hide_index=True, use_container_width=True, height=420)
        with b:
            st.markdown("**Recent deliveries**")
            recent = rounds.sort_values("t", ascending=False).head(60)
            st.dataframe(recent.assign(Time=recent["t"].dt.strftime("%a %I:%M %p"), lb=recent["lb"].round(1))
                         [["Time", "pen", "lb"]].rename(columns={"pen": "Fence / pen"}),
                         hide_index=True, use_container_width=True, height=420)
        st.download_button("Download scans (CSV)", scans.to_csv(index=False), "scans.csv", "text/csv")
        st.download_button("Download deliveries (CSV)", rounds.to_csv(index=False), "deliveries.csv", "text/csv")


body()
