"""Renders the bathroom-dashboard PNG shown on the Kindle screensaver.

Landscape, sized for a Kindle Paperwhite 3 (1072x1448 portrait panel, so
1448x1072 once rotated to landscape). Two stacked panels: weight (own
timestamped log -- multiple readings/day are expected) on top, night
mood on the bottom. Last 4 weeks, y-axis only, no x-axis labels.
"""

import json
import os
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import requests

INTERVALS_BASE_URL = "https://intervals.icu/api/v1"
PANEL_W, PANEL_H = 1448, 1072
DPI = 150
WINDOW_DAYS = 28


def load_kd_config():
    path = os.path.expanduser("~/.config/kindle_dashboard/config.json")
    with open(path) as f:
        return json.load(f)


def load_intervals_config():
    """Still needed for the /weight write-through to intervals.icu (kept
    for your other tools), even though rendering no longer reads from it."""
    path = os.path.expanduser("~/.config/intervals-icu/config.json")
    with open(path) as f:
        return json.load(f)


def _sleep_debt_hours(icu_cfg, target_hours=8, trailing_days=7):
    """Hours of deficit against `target_hours`/night, summed over the
    trailing week, from intervals.icu's raw sleepSecs field (there's no
    "sleep debt" field itself -- this is our own computation, surplus
    nights count as zero rather than offsetting debt)."""
    url = f"{INTERVALS_BASE_URL}/athlete/{icu_cfg['athlete_id']}/wellness"
    oldest = (datetime.now() - timedelta(days=trailing_days)).strftime("%Y-%m-%d")
    resp = requests.get(url, params={"oldest": oldest},
                         auth=("API_KEY", icu_cfg["api_key"]), timeout=10)
    resp.raise_for_status()
    debt = 0.0
    for w in resp.json():
        secs = w.get("sleepSecs")
        if secs is not None:
            debt += max(0.0, target_hours - secs / 3600)
    return debt


def _load_json_log(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _window_start():
    return datetime.now() - timedelta(days=WINDOW_DAYS)


def _rolling_band(xs, ys, window_days=3):
    """For each point, mean/SD of points within `window_days` of it
    (time-based, not index-based -- matters once multiple same-day
    readings exist). Returns (mean_ys, lo_ys, hi_ys)."""
    mean_ys, lo_ys, hi_ys = [], [], []
    for i, xi in enumerate(xs):
        nearby = [y for x, y in zip(xs, ys) if abs(x - xi) <= window_days]
        m = sum(nearby) / len(nearby)
        sd = (sum((v - m) ** 2 for v in nearby) / len(nearby)) ** 0.5
        mean_ys.append(m)
        lo_ys.append(m - sd)
        hi_ys.append(m + sd)
    return mean_ys, lo_ys, hi_ys


def _style(ax, title):
    ax.set_title(title, fontsize=15, color="black", fontweight="bold")
    ax.tick_params(axis="x", labelbottom=False, length=0)
    ax.tick_params(axis="y", colors="black", labelsize=10)
    for spine in ("top", "right", "bottom"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("black")
    ax.grid(True, axis="y", linewidth=0.3, color="gray", alpha=0.5)


def render_dashboard(out_path):
    kd_cfg = load_kd_config()
    start = _window_start()

    weight_entries = _load_json_log(kd_cfg["weight_log_path"])
    mood_entries = _load_json_log(kd_cfg["mood_log_path"])

    fig, (ax_weight, ax_mood) = plt.subplots(
        2, 1, figsize=(PANEL_W / DPI, PANEL_H / DPI), dpi=DPI)
    fig.patch.set_facecolor("white")

    # --- Weight: own timestamped log, multiple readings/day expected ---
    w_pts = [(datetime.fromisoformat(e["timestamp"]), e["value"])
             for e in weight_entries
             if datetime.fromisoformat(e["timestamp"]) >= start]
    w_pts.sort(key=lambda p: p[0])
    if w_pts:
        wx = [(t - start).total_seconds() / 86400 for t, _ in w_pts]
        wy = [v for _, v in w_pts]
        band_mean, band_lo, band_hi = _rolling_band(wx, wy, window_days=3)
        order = np.argsort(wx)
        wx_s = np.array(wx)[order]
        ax_weight.fill_between(
            wx_s, np.array(band_lo)[order], np.array(band_hi)[order],
            color="gray", alpha=0.25, label="daily variation band")
        ax_weight.plot(wx_s, np.array(band_mean)[order], "-",
                        color="black", linewidth=2, label="trend")
        ax_weight.plot(wx, wy, "o", color="black", markersize=4, alpha=0.6,
                        label="reading")
        ax_weight.legend(fontsize=8, loc="upper left")
    else:
        ax_weight.text(0.5, 0.5, "no weight data yet", ha="center",
                        va="center", color="gray", transform=ax_weight.transAxes)
    ax_weight.set_xlim(0, WINDOW_DAYS)
    _style(ax_weight, "Weight (kg) -- last 4 weeks")

    # --- Night mood: one reading/day, 0.5-5 stars ---
    m_pts = [(datetime.fromisoformat(e["date"]), e["value"])
              for e in mood_entries
              if datetime.fromisoformat(e["date"]) >= start]
    m_pts.sort(key=lambda p: p[0])
    if m_pts:
        mx = [(t - start).total_seconds() / 86400 for t, _ in m_pts]
        my = [v for _, v in m_pts]
        mean_y, lo_y, hi_y = _rolling_band(mx, my, window_days=3)
        order = np.argsort(mx)
        mx_s = np.array(mx)[order]
        ax_mood.plot(mx_s, np.array(mean_y)[order], "-", color="black",
                      linewidth=2, label="trend")
        ax_mood.plot(mx, my, "o", color="black", markersize=5, alpha=0.6,
                      label="night")
        ax_mood.legend(fontsize=8, loc="upper left")
    else:
        ax_mood.text(0.5, 0.5, "no mood data yet", ha="center", va="center",
                      color="gray", transform=ax_mood.transAxes)
    ax_mood.set_xlim(0, WINDOW_DAYS)
    ax_mood.set_ylim(0, 5.5)
    _style(ax_mood, "Night mood -- last 4 weeks")

    fig.suptitle(datetime.now().strftime("%A %d %B %Y"), fontsize=16,
                 color="black", fontweight="bold")

    # Top-left so it doesn't clash with the app's own top-right close
    # button, which overlays this same image when the app is open.
    try:
        icu_cfg = load_intervals_config()
        debt = _sleep_debt_hours(icu_cfg)
        fig.text(0.02, 0.97, f"Sleep debt: {debt:.1f}h", fontsize=13,
                  color="black", fontweight="bold", ha="left", va="top")
    except Exception as e:
        fig.text(0.02, 0.97, "Sleep debt: --", fontsize=13,
                  color="gray", ha="left", va="top")

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=DPI, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    render_dashboard("/tmp/dashboard_test.png")
    print("rendered /tmp/dashboard_test.png")
