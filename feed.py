"""Feed calculations from the raw scan and feed-round data.

Mirrors the logic of the Google Sheets dashboard (Calculations / FR Data tabs),
but computed directly from the two raw tables:

  scans  - one row per bunk-scanner log entry:  Timestamp, Fence Name, Last Scanned, Minimum, Scanned (mm)
  rounds - one row per feed delivery:           VfrId, DateTime, Date, Location, Fence Name, Interval, Ration, MFR, Total Fed (lb)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

MM_PER_IN = 25.4
LB_PER_UNIT = 36.04          # "36.04-lb units" used by the delivery charts
SCAN_TO_LB = 12.5            # heifer charts: scan inches x 12.5 = approx lb in the bunk
SLOT = pd.Timedelta(minutes=20)

MILKING_FENCES = {g: [f"{g}{c}" for c in "ABCD"] for g in (1, 2, 3)}
HEIFER_PENS = ["Big Hfr 10", "Big Hfr 11", "Big Hfr 12", "Big Hfr 13", "Hfr 14", "Hfr 15", "Hfr 16", "Hfr 17"]
DOSING_LB = {"Hfr 14": 399, "Hfr 15": 320, "Hfr 16": 351, "Hfr 17": 161,
             "Big Hfr 10": 399, "Big Hfr 11": 379, "Big Hfr 12": 269, "Big Hfr 13": 170}

# Raw fence labels -> canonical pen (from the sheet's Pen Map). Matching is case-insensitive.
PEN_ALIASES = {"1d gimpy heifers": "1D", "hfr 18": "Hfr 14", "heifer 15": "Hfr 15"}

# Deliveries logged in kg instead of lb during this window (sheet column 'Total Fed corr (lb)')
KG_WINDOW = (pd.Timestamp("2026-11-16 10:42"), pd.Timestamp("2026-11-18 08:47"))


def canonical_pen(label: str) -> str | None:
    first = str(label).split("\n")[0].strip()
    low = first.lower()
    if low in PEN_ALIASES:
        return PEN_ALIASES[low]
    if re.fullmatch(r"[123][a-d]", low):
        return first.upper()
    for pen in HEIFER_PENS:
        if low == pen.lower():
            return pen
    return None


def milking_group(pen: str | None) -> int | None:
    return int(pen[0]) if pen and re.fullmatch(r"[123][A-D]", pen) else None


# ---------- Cleaning ----------
def clean_scans(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per real reading: pen, group, scan time (t), height (inches)."""
    df = raw.iloc[:, :5].copy()
    df.columns = ["ts", "fence", "scanned", "minimum", "mm"]
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df["mm"] = pd.to_numeric(df["mm"], errors="coerce")
    df["scanned"] = df["scanned"].astype(str).str.strip()
    df = df[df["ts"].notna() & df["mm"].notna() & df["scanned"].str.fullmatch(r"\d{1,2}:\d{2}")]
    df["pen"] = df["fence"].map(canonical_pen)
    df = df[df["pen"].notna()]
    scan_td = pd.to_timedelta(df["scanned"] + ":00")
    # The log time can be just after midnight for a scan taken late the previous day
    day = df["ts"].dt.normalize() - pd.to_timedelta((df["ts"].dt.hour < scan_td.dt.components.hours).astype(int), unit="D")
    df["t"] = day + scan_td
    df["inches"] = df["mm"] / MM_PER_IN
    df["group"] = df["pen"].map(milking_group).astype("Int64")
    # The logger repeats the latest reading every cycle; keep each reading once
    df = df.sort_values("ts").drop_duplicates(["pen", "t"], keep="last")
    return df[["t", "pen", "group", "inches", "mm"]].sort_values("t").reset_index(drop=True)


def clean_rounds(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per delivery: time (t), pen, group, lb (unit-corrected)."""
    df = raw.iloc[:, :9].copy()
    df.columns = ["id", "dt", "date", "location", "fence", "interval", "ration", "mfr", "lb"]
    df["t"] = pd.to_datetime(df["dt"], errors="coerce")
    df["lb"] = pd.to_numeric(df["lb"], errors="coerce")
    df = df[df["t"].notna() & df["lb"].notna()]
    kg = (df["t"] >= KG_WINDOW[0]) & (df["t"] < KG_WINDOW[1])
    df.loc[kg, "lb"] = df.loc[kg, "lb"] / 2.20462
    df["pen"] = df["fence"].map(canonical_pen)
    df["group"] = df["pen"].map(milking_group).astype("Int64")   # whole numbers; heifer rows stay empty
    return df[["t", "pen", "group", "lb"]].sort_values("t").reset_index(drop=True)


# ---------- Milking group heights ----------
def group_heights(scans: pd.DataFrame, g: int) -> pd.DataFrame:
    """Per scan time with all 4 fences read: sum and max of the fence heights (inches)."""
    fences = MILKING_FENCES[g]
    wide = scans[scans["pen"].isin(fences)].pivot_table(index="t", columns="pen", values="inches", aggfunc="last")
    wide = wide.reindex(columns=fences).dropna()
    return pd.DataFrame({"t": wide.index, "sum": wide.sum(axis=1).values, "max": wide.max(axis=1).values})


@dataclass
class Runout:
    group: int
    height: float | None          # current highest-fence height (in)
    height_time: pd.Timestamp | None
    rate: float | None             # typical drawdown (in/hr) after deliveries, last 7 days
    runout: pd.Timestamp | None    # when the highest fence drops below threshold
    already_below: bool
    fence_min_24h: dict


def runout(scans: pd.DataFrame, rounds: pd.DataFrame, g: int, threshold: float, now: pd.Timestamp) -> Runout:
    week = scans[scans["t"] >= now.normalize() - pd.Timedelta(days=6)]
    h = group_heights(week, g)
    deliveries = np.sort(rounds.loc[rounds["group"] == g, "t"].unique())
    rates = []
    for a, b in zip(deliveries[:-1], deliveries[1:]):
        seg = h[(h["t"] >= a) & (h["t"] < b)]
        if len(seg) < 3:
            continue
        hours = (seg["t"] - seg["t"].iloc[0]).dt.total_seconds() / 3600
        if hours.iloc[-1] < 0.75:
            continue
        rate = -np.polyfit(hours, seg["max"], 1)[0]
        if rate > 0.02:
            rates.append(rate)
    rate = float(np.median(rates)) if rates else None

    fence_min = {}
    day = scans[scans["t"] >= now - pd.Timedelta(hours=24)]
    for f in MILKING_FENCES[g]:
        v = day.loc[day["pen"] == f, "inches"]
        fence_min[f] = float(v.min()) if len(v) else None

    if h.empty:
        return Runout(g, None, None, rate, None, False, fence_min)
    cur, cur_t = float(h["max"].iloc[-1]), h["t"].iloc[-1]
    if cur <= threshold:
        # interpolate when it crossed below the threshold
        above = h.index[h["max"] > threshold]
        when = cur_t
        if len(above):
            ia = above[-1]
            after = h.loc[ia + 1:]
            ib = after.index[after["max"] <= threshold]
            if len(ib):
                ha, hb = h.loc[ia, "max"], h.loc[ib[0], "max"]
                ta, tb = h.loc[ia, "t"], h.loc[ib[0], "t"]
                when = ta + (ha - threshold) / (ha - hb) * (tb - ta)
        return Runout(g, cur, cur_t, rate, when, True, fence_min)
    proj = cur_t + pd.Timedelta(hours=(cur - threshold) / rate) if rate else None
    return Runout(g, cur, cur_t, rate, proj, False, fence_min)


def slot_labels(start: pd.Timestamp, n: int, fmt: str) -> list[str]:
    return [(start + i * SLOT).strftime(fmt).lstrip("0").replace(" 0", " ") for i in range(n)]


def day_overlay(scans: pd.DataFrame, g: int, now: pd.Timestamp, days: int = 7) -> tuple[pd.DataFrame, list[str]]:
    """Group height (sum of 4 fences) in 20-min slots over the last 24 h, plus the same window on each prior day."""
    start = (now - pd.Timedelta(hours=24)).floor("20min")
    h = group_heights(scans, g)
    rows = []
    for k in range(days):
        s = start - pd.Timedelta(days=k)
        seg = h[(h["t"] >= s) & (h["t"] < s + pd.Timedelta(hours=24))]
        slots = ((seg["t"] - s) / SLOT).astype(int)
        for slot, v in seg.groupby(slots)["sum"].mean().items():
            rows.append({"i": int(slot), "series": "last 24h" if k == 0 else f"-{k}d", "value": float(v), "days_ago": k})
    labels = slot_labels(start, 72, "%I:%M %p")
    df = pd.DataFrame(rows, columns=["i", "series", "value", "days_ago"])
    df["label"] = df["i"].map(lambda i: labels[i])
    return df, labels


def delivered_slots(rounds: pd.DataFrame, start: pd.Timestamp, n: int, groups=(1, 2, 3)) -> pd.DataFrame:
    """Feed delivered per 20-min slot per milking group, in 36.04-lb units."""
    seg = rounds[(rounds["t"] >= start) & (rounds["t"] < start + n * SLOT) & rounds["group"].isin(groups)]
    slot = ((seg["t"] - start) / SLOT).astype(int)
    units = (seg.groupby([slot, seg["group"]])["lb"].sum() / LB_PER_UNIT).round()
    out = units.rename("value").reset_index()
    out.columns = ["i", "group", "value"]
    return out[out["value"] > 0]


# ---------- Heifers ----------
def heifer_events(scans: pd.DataFrame, rounds: pd.DataFrame, pen: str, now: pd.Timestamp, days: int = 3) -> pd.DataFrame:
    """Deliveries (dosing, delivered, the scan right after) and stand-alone scans, last `days` days."""
    since = now.normalize() - pd.Timedelta(days=days)
    sc = scans[(scans["pen"] == pen) & (scans["t"] >= since)][["t", "inches"]].copy()
    sc["lb"] = sc["inches"] * SCAN_TO_LB
    dl = rounds[(rounds["pen"] == pen) & (rounds["t"] >= since)].copy()
    dl["t"] = dl["t"].dt.floor("min")
    dl = dl.groupby("t", as_index=False)["lb"].sum()
    half = pd.Timedelta(minutes=30)
    rows = []
    for _, d in dl.iterrows():
        after = sc[(sc["t"] >= d["t"]) & (sc["t"] <= d["t"] + half)]
        rows.append({"t": d["t"], "dosing": DOSING_LB.get(pen), "delivered": round(d["lb"]),
                     "scan": float(after["lb"].iloc[0]) if len(after) else np.nan})
    for _, s in sc.iterrows():
        if not ((dl["t"] <= s["t"]) & (dl["t"] >= s["t"] - half)).any():
            rows.append({"t": s["t"], "dosing": np.nan, "delivered": np.nan, "scan": float(s["lb"])})
    ev = pd.DataFrame(rows, columns=["t", "dosing", "delivered", "scan"]).sort_values("t").reset_index(drop=True)
    ev["empty"] = np.where(ev["scan"] == 0, 0.0, np.nan)
    return ev
