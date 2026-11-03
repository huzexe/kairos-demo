"""The chart library. Each tag takes plain data and draws inline HTML or SVG; no chart library, no network."""

from django import template

register = template.Library()


def _empty(label, action="", url=""):
    return {"label": label, "action": action, "url": url}


@register.inclusion_tag("charts/bar_chart.html")
def bar_chart(rows, label, accent=False, action="", url=""):
    """rows: [{label, count, pct, tip, current}]. Marks the current bar, in acid when accent is on."""
    has_data = any(r["count"] for r in rows)
    peak = max(rows, key=lambda r: r["count"]) if has_data else None
    return {**_empty(label, action, url), "rows": rows, "has_data": has_data, "accent": accent, "peak": peak}


@register.inclusion_tag("charts/paired_bar_chart.html")
def paired_bar_chart(panel, label, action="", url=""):
    """One currency's months: billed beside collected. Never takes more than one currency."""
    return {**_empty(label, action, url), "panel": panel, "months": panel["months"], "ticks": panel["ticks"],
            "code": panel["code"], "has_data": panel["has_money"]}


@register.inclusion_tag("charts/hbar_ranked.html")
def hbar_ranked(rows, label, icons=False, action="", url=""):
    """rows: [{label, count, pct}], biggest first."""
    return {**_empty(label, action, url), "rows": rows, "icons": icons, "has_data": bool(rows)}


@register.inclusion_tag("charts/stacked_hbar.html")
def stacked_hbar(parts, label, action="", url=""):
    """parts: [{label, text, pct, tone}]. Tone is neutral, ok, warn, serious or danger."""
    return {**_empty(label, action, url), "parts": parts, "has_data": bool(parts)}


@register.inclusion_tag("charts/funnel.html")
def funnel(data, label, accent=False, action="", url=""):
    """data from insights.funnel(). The stage that loses the most is marked: in acid only when accent is on."""
    rows = data["rows"]
    top = max((r["count"] for r in rows), default=0)
    drawn = [{**r, "height": round(r["count"] * 100 / top) if top else 0, "is_worst": r["key"] == data["worst_key"],
              "drop": 100 - r["share"] if r["share"] is not None else None} for r in rows]
    return {**_empty(label, action, url), "rows": drawn, "note": data["note"], "accent": accent, "has_data": bool(top),
            "stages": len(rows)}


def _line_points(values, width=600, height=160, pad=8):
    """Scale values into the chart: [(x, y)], with the highest value near the top."""
    top = max(values) or 1
    step = width / max(len(values) - 1, 1)
    return [(round(i * step, 1), round(height - (float(v) / float(top)) * (height - pad), 1))
            for i, v in enumerate(values)]


def _smooth_path(points):
    """A curve through the points that never swings above or below them, so it can't invent a peak."""
    x, y = points[0]
    parts = [f"M{x},{y}"]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        mid = round((x0 + x1) / 2, 1)
        parts.append(f"C{mid},{y0} {mid},{y1} {x1},{y1}")
    return " ".join(parts)


@register.inclusion_tag("charts/area_line.html")
def area_line(rows, field, label, action="", url=""):
    """rows: [{label, tip, <field>}]. One line, one currency."""
    values = [r[field] for r in rows]
    has_data = any(values)
    context = {**_empty(label, action, url), "rows": rows, "has_data": has_data}
    if has_data:
        points = _line_points(values)
        line = _smooth_path(points)
        context.update(line=line, area=f"{line} L600,160 L0,160 Z", first=rows[0]["label"], last=rows[-1]["label"],
                       end_x=round(points[-1][0] / 6, 1), end_y=round(points[-1][1] / 1.6, 1))
    return context


@register.inclusion_tag("charts/ring.html")
def ring(pct, label, text=""):
    """A single share out of 100, such as win rate or checklist progress. pct may be None."""
    return {"pct": pct, "label": label, "text": text or ("—" if pct is None else f"{pct}%")}


@register.inclusion_tag("charts/heat_grid.html")
def heat_grid(calendar, label, action="", url=""):
    """Data from insights.activity_calendar(): twelve week columns of seven day cells."""
    return {**_empty(label, action, url), "columns": calendar["columns"], "note": calendar["note"],
            "has_data": bool(calendar["total"]), "days": ["M", "", "W", "", "F", "", "S"]}


def _layout(tiles, x, y, w, h):
    """Split the tiles into two groups of nearly equal value, along the longer side, until each stands alone."""
    if not tiles:
        return []
    if len(tiles) == 1:
        return [{**tiles[0], "x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2)}]
    total = sum(t["value"] for t in tiles)
    running, cut = 0, 1
    for i, tile in enumerate(tiles[:-1], start=1):
        running += tile["value"]
        cut = i
        if running >= total / 2:
            break
    share = sum(t["value"] for t in tiles[:cut]) / total
    if w * 2 >= h:  # the chart is about twice as wide as it is tall
        return _layout(tiles[:cut], x, y, w * share, h) + _layout(tiles[cut:], x + w * share, y, w * (1 - share), h)
    return _layout(tiles[:cut], x, y, w, h * share) + _layout(tiles[cut:], x, y + h * share, w, h * (1 - share))


@register.inclusion_tag("charts/treemap.html")
def treemap(tiles, label, action="", url=""):
    """tiles: [{label, url, text, value, share}], biggest first. Area follows value."""
    return {**_empty(label, action, url), "tiles": _layout(list(tiles), 0, 0, 100, 100), "has_data": bool(tiles)}


@register.inclusion_tag("charts/segments.html")
def segments(done, total, label):
    """16 posts promised → 16 segments, with the delivered ones filled."""
    return {"label": label, "done": done, "total": total,
            "cells": [i < done for i in range(total)]}


@register.inclusion_tag("charts/meter.html")
def meter(pct, label, warn_at=50):
    """A share with a warning line, such as how much income rests on the three biggest clients."""
    return {"pct": pct, "label": label, "warn_at": warn_at, "is_warn": pct > warn_at}


@register.inclusion_tag("charts/sparkline.html")
def sparkline(values, label):
    """A small inline trend for tables and tiles."""
    values = list(values)
    points = _smooth_path(_line_points(values, 100, 24, 2)) if any(values) else ""
    return {"points": points, "label": label}
