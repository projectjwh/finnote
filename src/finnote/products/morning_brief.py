"""Morning Brief -- single-page intelligence dashboard.

Generates a self-contained HTML file (no iframes, no external JS, works at
file://) with Bloomberg dark-theme styling.  Sections: market scoreboard,
LIVE stories, top stories with news-data pairing, delta analysis, z-score
anomaly table, open research calls, and footer.
"""

from __future__ import annotations

import html
import math
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Lazy-init database helpers
# ---------------------------------------------------------------------------

_db_instance = None


def _get_db():
    global _db_instance
    if _db_instance is None:
        try:
            from finnote.datastore.timeseries_db import TimeSeriesDB
            _db_instance = TimeSeriesDB()
        except Exception:
            return None
    return _db_instance


_ledger_instance = None


def _get_ledger():
    global _ledger_instance
    if _ledger_instance is None:
        try:
            from finnote.track_record.ledger import TrackRecordLedger
            _ledger_instance = TrackRecordLedger()
        except Exception:
            return None
    return _ledger_instance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _color_change(val: float) -> str:
    """Return CSS color class name for a price change value."""
    return "green" if val >= 0 else "red"


def _format_number(val: float, decimals: int = 2) -> str:
    """Format a number with thousands separator and fixed decimals."""
    if abs(val) >= 1_000:
        return f"{val:,.{decimals}f}"
    return f"{val:.{decimals}f}"


def _relative_time(published_str: str) -> str:
    """Convert an ISO/RFC date string to a human-friendly relative time."""
    if not published_str:
        return ""
    try:
        # Try ISO format first
        dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        try:
            # Try common RSS date formats
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(published_str)
        except Exception:
            return published_str[:16] if len(published_str) > 16 else published_str

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = now - dt

    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins}m ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    days = seconds // 86400
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days}d ago"
    return dt.strftime("%b %d")


def _z_score(current: float, history: list[float]) -> float:
    """Standard deviations from mean. Requires >= 10 observations."""
    if len(history) < 10:
        return 0.0
    mean = sum(history) / len(history)
    var = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    return (current - mean) / std if std > 0 else 0.0


def _percentile_rank(current: float, history: list[float]) -> float:
    """Position of current value in historical distribution (0-100)."""
    if not history:
        return 50.0
    below = sum(1 for h in history if h < current)
    return (below / len(history)) * 100


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text))


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """\
:root {
    --bg: #0A0E17;
    --surface: #0B1117;
    --border: #1E293B;
    --text-primary: #F9FAFB;
    --text-secondary: #E5E7EB;
    --text-tertiary: #9CA3AF;
    --green: #00D26A;
    --red: #FF3B3B;
    --amber: #FFB800;
    --blue: #00A3FF;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 14px; }
body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text-primary);
    line-height: 1.6;
    padding: 2rem 1rem;
}
.container { max-width: 1200px; margin: 0 auto; }
h1 { font-size: 1.75rem; font-weight: 700; margin-bottom: 0.25rem; }
h2 {
    font-size: 1.15rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-tertiary);
    margin: 2rem 0 1rem; padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
}
.accent { color: var(--blue); }
.date { color: var(--text-tertiary); font-size: 0.85rem; margin-bottom: 1.5rem; }
.green { color: var(--green); }
.red { color: var(--red); }
.amber { color: var(--amber); }
.blue { color: var(--blue); }
.muted { color: var(--text-tertiary); font-size: 0.8rem; }
.mono {
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-variant-numeric: tabular-nums;
}

/* Scoreboard table */
.scoreboard { width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; }
.scoreboard th {
    text-align: left; padding: 0.5rem 0.75rem;
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--text-tertiary); border-bottom: 2px solid var(--border);
}
.scoreboard td {
    padding: 0.35rem 0.75rem; border-bottom: 1px solid var(--border);
    font-size: 0.85rem;
}
.scoreboard td.name { color: var(--text-secondary); }
.scoreboard td.level { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }
.scoreboard td.change { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; font-weight: 600; }

/* Cards */
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
}
.story-card { border-left: 3px solid var(--blue); }
.story-card .headline { font-weight: 600; margin-bottom: 0.25rem; }
.story-card .source { color: var(--text-tertiary); font-size: 0.8rem; margin-bottom: 0.5rem; }
.story-card .data-row { display: flex; flex-wrap: wrap; gap: 0.75rem; }
.story-card .instrument {
    font-family: 'JetBrains Mono', monospace; font-size: 0.8rem;
    background: rgba(255,255,255,0.04); padding: 0.15rem 0.5rem;
    border-radius: 3px;
}

/* LIVE card */
.live-card { border-left: 3px solid var(--red); }
.live-card summary {
    cursor: pointer; font-weight: 600; padding: 0.25rem 0;
    display: flex; align-items: center; gap: 0.5rem;
}
.live-badge {
    background: var(--red); color: white; font-size: 0.65rem;
    font-weight: 700; padding: 0.1rem 0.4rem; border-radius: 3px;
    letter-spacing: 0.05em;
}
.live-card p { margin-top: 0.5rem; color: var(--text-secondary); font-size: 0.9rem; }

/* Delta cards */
.delta-new { border-left: 3px solid var(--green); }
.delta-escalating { border-left: 3px solid var(--amber); }
.delta-continuing { border-left: 3px solid var(--border); }
.delta-resolved { border-left: 3px solid var(--text-tertiary); opacity: 0.7; }
.delta-label {
    font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em;
    font-weight: 700; margin-bottom: 0.25rem;
}

/* Z-score table */
.ztable { width: 100%; border-collapse: collapse; }
.ztable th {
    text-align: left; padding: 0.5rem 0.75rem;
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--text-tertiary); border-bottom: 2px solid var(--border);
}
.ztable td {
    padding: 0.35rem 0.75rem; border-bottom: 1px solid var(--border);
    font-size: 0.85rem;
}
.ztable .bold { font-weight: 700; }

/* Calls table */
.calls-table { width: 100%; border-collapse: collapse; }
.calls-table th {
    text-align: left; padding: 0.5rem 0.75rem;
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--text-tertiary); border-bottom: 2px solid var(--border);
}
.calls-table td {
    padding: 0.35rem 0.75rem; border-bottom: 1px solid var(--border);
    font-size: 0.85rem;
}

/* Footer */
.footer {
    margin-top: 3rem; padding-top: 1rem;
    border-top: 1px solid var(--border);
    color: var(--text-tertiary); font-size: 0.75rem;
    line-height: 1.8;
}

/* Responsive */
@media (max-width: 768px) {
    .scoreboard-grid { display: block; }
    .scoreboard-grid > div { margin-bottom: 1.5rem; }
    .story-card .data-row { flex-direction: column; }
}

/* Print */
@media print {
    :root {
        --bg: #ffffff; --surface: #f8f9fa;
        --border: #dee2e6; --text-primary: #212529;
        --text-secondary: #495057; --text-tertiary: #6c757d;
    }
    body { padding: 0; font-size: 11px; }
    .card { break-inside: avoid; }
}
"""


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class MorningBriefGenerator:
    """Generates a single self-contained HTML Morning Brief page."""

    def __init__(
        self,
        market_data: dict[str, Any],
        messages: list[Any],  # AgentMessage list
        run_id: str,
        delta_results: list[Any] | None = None,
        live_coverages: list[Any] | None = None,
        news_articles: list[dict[str, Any]] | None = None,
    ):
        self.market_data = market_data
        self.messages = messages
        self.run_id = run_id
        self.delta_results = delta_results or []
        self.live_coverages = live_coverages or []
        # News articles: passed directly or pulled from market_data
        self.news_articles = news_articles or market_data.get("news_articles", [])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> str:
        """Return complete self-contained HTML string."""
        parts = [
            self._html_head(),
            '<body><div class="container">',
            self._section_header(),
            self._section_scoreboard(),
            self._section_live_stories(),
            self._section_top_stories(),
            self._section_delta(),
            self._section_key_indicators(),
            self._section_open_calls(),
            self._section_footer(),
            "</div></body></html>",
        ]
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # HTML scaffold
    # ------------------------------------------------------------------

    def _html_head(self) -> str:
        return (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n<head>\n'
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            "<title>finnote Morning Brief</title>\n"
            f"<style>\n{_CSS}\n</style>\n"
            "</head>"
        )

    # ------------------------------------------------------------------
    # Section 1: Header
    # ------------------------------------------------------------------

    def _section_header(self) -> str:
        now = datetime.now(timezone.utc)
        formatted_date = now.strftime("%A, %B %d, %Y &middot; %H:%M UTC")
        return (
            '<div class="header">'
            '<h1>finnote <span class="accent">Morning Brief</span></h1>'
            f'<div class="date">{formatted_date} &middot; Run {_esc(self.run_id)}</div>'
            "</div>"
        )

    # ------------------------------------------------------------------
    # Section 2: Market Scoreboard
    # ------------------------------------------------------------------

    def _section_scoreboard(self) -> str:
        lines: list[str] = ['<h2>Market Scoreboard</h2>']
        lines.append('<div class="scoreboard-grid" style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">')

        # Column definitions: (title, data_key, instruments)
        columns = [
            ("Equities", "equity_indices", ["S&P 500", "NASDAQ", "STOXX 600", "Nikkei 225", "Hang Seng"]),
            ("Rates", "treasury_yields", ["2Y", "10Y", "30Y"]),
            ("FX", "fx_rates", ["DXY", "EUR/USD", "USD/JPY", "GBP/USD"]),
            ("Commodities", "commodities", ["WTI Crude", "Gold", "Copper"]),
            ("Volatility", "volatility", ["VIX", "VIX3M"]),
        ]

        for title, data_key, instruments in columns:
            data = self.market_data.get(data_key, {})
            if isinstance(data, dict) and "error" in data:
                data = {}
            lines.append("<div>")
            lines.append('<table class="scoreboard">')
            lines.append(f'<thead><tr><th colspan="3">{_esc(title)}</th></tr></thead>')
            lines.append("<tbody>")

            for inst_name in instruments:
                inst_data = data.get(inst_name, {})
                if isinstance(inst_data, dict):
                    current = _safe_float(inst_data.get("current"))
                    chg = _safe_float(inst_data.get("prev_close_chg"))
                elif inst_data is not None:
                    # treasury_yields returns simple values like {"2Y": "4.25"}
                    current = _safe_float(inst_data)
                    chg = 0.0
                else:
                    current = 0.0
                    chg = 0.0

                color = _color_change(chg)
                chg_str = f"{chg:+.2f}%" if chg != 0 else "--"
                level_str = _format_number(current) if current != 0 else "--"

                lines.append(
                    f'<tr>'
                    f'<td class="name">{_esc(inst_name)}</td>'
                    f'<td class="level">{level_str}</td>'
                    f'<td class="change {color}">{chg_str}</td>'
                    f'</tr>'
                )

            # Special: 2s10s spread for Rates
            if data_key == "treasury_yields":
                y2 = _safe_float(data.get("2Y"))
                y10 = _safe_float(data.get("10Y"))
                if y2 and y10:
                    spread = (y10 - y2) * 100  # in bps
                    spread_color = _color_change(spread)
                    lines.append(
                        f'<tr>'
                        f'<td class="name">2s10s Spread</td>'
                        f'<td class="level">{spread:+.0f}bps</td>'
                        f'<td class="change {spread_color}">{"inverted" if spread < 0 else "normal"}</td>'
                        f'</tr>'
                    )

            # Special: VIX term structure for Volatility
            if data_key == "volatility":
                vix_data = data.get("VIX", {})
                vix3m_data = data.get("VIX3M", {})
                vix_val = _safe_float(vix_data.get("current") if isinstance(vix_data, dict) else vix_data)
                vix3m_val = _safe_float(vix3m_data.get("current") if isinstance(vix3m_data, dict) else vix3m_data)
                if vix_val and vix3m_val:
                    state = "Contango" if vix_val < vix3m_val else "Backwardation"
                    state_color = "green" if state == "Contango" else "amber"
                    lines.append(
                        f'<tr>'
                        f'<td class="name">Term Structure</td>'
                        f'<td class="level">{vix_val / vix3m_val:.2f} ratio</td>'
                        f'<td class="change {state_color}">{state}</td>'
                        f'</tr>'
                    )

            lines.append("</tbody></table></div>")

        lines.append("</div>")  # close scoreboard-grid
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Section 3: LIVE Stories
    # ------------------------------------------------------------------

    def _section_live_stories(self) -> str:
        if not self.live_coverages:
            return ""

        lines: list[str] = ['<h2>Live Coverage</h2>']
        for cov in self.live_coverages:
            # Support both dict and FeaturedCoverage objects
            if isinstance(cov, dict):
                title = cov.get("title", "Untitled")
                last_updated = cov.get("last_updated", "")
                assessment = cov.get("current_assessment", "")
            else:
                title = getattr(cov, "title", "Untitled")
                last_updated = getattr(cov, "last_updated", "")
                assessment = getattr(cov, "current_assessment", "")

            lines.append(
                f'<details class="card live-card" open>'
                f'<summary>'
                f'<span class="live-badge">LIVE</span> '
                f'{_esc(title)} '
                f'<span class="muted">Updated {_esc(str(last_updated))}</span>'
                f'</summary>'
                f'<p>{_esc(assessment)}</p>'
                f'</details>'
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Section 4: Top Stories (news + data cards)
    # ------------------------------------------------------------------

    def _section_top_stories(self) -> str:
        articles = self.news_articles[:5]
        if not articles:
            return '<h2>Top Stories</h2><p class="muted">No news articles available.</p>'

        lines: list[str] = ['<h2>Top Stories</h2>']
        for article in articles:
            title = article.get("title", "Untitled")
            source = article.get("source", "Unknown")
            published = article.get("published", "")
            rel_time = _relative_time(published)
            instruments = article.get("instruments", [])

            # Build data row with matched instrument levels
            inst_spans: list[str] = []
            for inst_name in instruments[:6]:  # cap at 6 instruments per card
                level_str, chg_str, z_str = self._lookup_instrument(inst_name)
                if level_str:
                    color = "green" if chg_str.startswith("+") else "red" if chg_str.startswith("-") else ""
                    z_part = f" z:{z_str}" if z_str else ""
                    inst_spans.append(
                        f'<span class="instrument">'
                        f'{_esc(inst_name)} {level_str} '
                        f'<span class="{color}">{chg_str}</span>'
                        f'{z_part}</span>'
                    )

            data_row = ""
            if inst_spans:
                data_row = f'<div class="data-row">{"".join(inst_spans)}</div>'

            lines.append(
                f'<div class="card story-card">'
                f'<div class="headline">{_esc(title)}</div>'
                f'<div class="source">{_esc(source)} &middot; {_esc(rel_time)}</div>'
                f'{data_row}'
                f'</div>'
            )

        return "\n".join(lines)

    def _lookup_instrument(self, inst_name: str) -> tuple[str, str, str]:
        """Look up an instrument's current level, change, and z-score.

        Returns (level_str, change_str, z_score_str) or ("", "", "") if not found.
        """
        # Search across all market data categories
        for category in ("equity_indices", "fx_rates", "commodities", "volatility", "treasury_yields"):
            data = self.market_data.get(category, {})
            if isinstance(data, dict) and inst_name in data:
                inst_data = data[inst_name]
                if isinstance(inst_data, dict):
                    current = _safe_float(inst_data.get("current"))
                    chg = _safe_float(inst_data.get("prev_close_chg"))

                    # Try z-score from history
                    z_str = ""
                    history_list = inst_data.get("history", [])
                    if history_list and len(history_list) >= 10:
                        hist_vals = [_safe_float(h.get("close", h) if isinstance(h, dict) else h) for h in history_list]
                        z = _z_score(current, hist_vals)
                        z_str = f"{z:+.1f}"

                    level_str = f"${_format_number(current)}" if current else ""
                    chg_str = f"{chg:+.1f}%" if chg != 0 else "--"
                    return level_str, chg_str, z_str
                else:
                    # Simple value (treasury yields)
                    val = _safe_float(inst_data)
                    return f"{val:.2f}%", "--", ""

        # Try TimeSeriesDB for FRED series
        db = _get_db()
        if db is not None:
            try:
                series = db.get_series(inst_name)
                if series and len(series) > 0:
                    current = _safe_float(series[-1].get("value", series[-1]) if isinstance(series[-1], dict) else series[-1])
                    vals = [_safe_float(s.get("value", s) if isinstance(s, dict) else s) for s in series]
                    z = _z_score(current, vals) if len(vals) >= 10 else 0.0
                    z_str = f"{z:+.1f}" if z else ""
                    return _format_number(current), "--", z_str
            except Exception:
                pass

        return "", "", ""

    # ------------------------------------------------------------------
    # Section 5: What Changed (delta section)
    # ------------------------------------------------------------------

    def _section_delta(self) -> str:
        lines: list[str] = ['<h2>What Changed</h2>']

        if not self.delta_results:
            lines.append(
                '<div class="card" style="border-left: 3px solid var(--text-tertiary);">'
                '<p class="muted">First run &mdash; no prior day comparison available.</p>'
                "</div>"
            )
            return "\n".join(lines)

        # Group by delta_type
        groups: dict[str, list[Any]] = {
            "new": [],
            "escalating": [],
            "continuing": [],
            "resolved": [],
        }
        for dr in self.delta_results:
            dtype = (
                dr.get("delta_type", "continuing") if isinstance(dr, dict)
                else getattr(dr, "delta_type", "continuing")
            )
            bucket = dtype if dtype in groups else "continuing"
            groups[bucket].append(dr)

        # New today (green)
        for dr in groups["new"]:
            subject = dr.get("subject", "") if isinstance(dr, dict) else getattr(dr, "subject", "")
            novelty = (
                dr.get("novelty_score", 0) if isinstance(dr, dict)
                else getattr(dr, "novelty_score", 0)
            )
            if _safe_float(novelty) > 0.7:
                lines.append(
                    f'<div class="card delta-new">'
                    f'<div class="delta-label green">New today</div>'
                    f'<div>{_esc(subject)}</div>'
                    f'<div class="muted">Novelty: {_safe_float(novelty):.1%}</div>'
                    f'</div>'
                )

        # Escalating (amber)
        for dr in groups["escalating"]:
            subject = dr.get("subject", "") if isinstance(dr, dict) else getattr(dr, "subject", "")
            lines.append(
                f'<div class="card delta-escalating">'
                f'<div class="delta-label amber">Escalating</div>'
                f'<div>{_esc(subject)}</div>'
                f'</div>'
            )

        # Continuing (muted)
        continuing_subjects = []
        for dr in groups["continuing"]:
            subject = dr.get("subject", "") if isinstance(dr, dict) else getattr(dr, "subject", "")
            if subject:
                continuing_subjects.append(subject)
        if continuing_subjects:
            items = "".join(f"<li>{_esc(s)}</li>" for s in continuing_subjects[:10])
            lines.append(
                f'<div class="card delta-continuing">'
                f'<div class="delta-label muted">Continuing</div>'
                f'<ul style="margin:0.25rem 0 0 1.25rem; color:var(--text-secondary);">{items}</ul>'
                f'</div>'
            )

        # Resolved
        for dr in groups["resolved"]:
            subject = dr.get("subject", "") if isinstance(dr, dict) else getattr(dr, "subject", "")
            lines.append(
                f'<div class="card delta-resolved">'
                f'<div class="delta-label muted">Resolved</div>'
                f'<div>{_esc(subject)}</div>'
                f'</div>'
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Section 6: Key Indicators (z-score anomaly table)
    # ------------------------------------------------------------------

    def _section_key_indicators(self) -> str:
        lines: list[str] = ['<h2>Key Indicators</h2>']

        # Collect all tracked series with z-scores
        indicators: list[dict[str, Any]] = []

        # Scan all market data categories for instruments with history
        for category in ("equity_indices", "fx_rates", "commodities", "volatility"):
            data = self.market_data.get(category, {})
            if not isinstance(data, dict):
                continue
            for name, inst_data in data.items():
                if name.startswith("_") or not isinstance(inst_data, dict):
                    continue
                history = inst_data.get("history", [])
                current = _safe_float(inst_data.get("current"))
                if not history or len(history) < 10 or current == 0:
                    continue

                hist_vals = [
                    _safe_float(h.get("close", h) if isinstance(h, dict) else h)
                    for h in history
                ]
                z = _z_score(current, hist_vals)
                pct = _percentile_rank(current, hist_vals)

                # Determine signal
                if abs(z) > 2:
                    signal = "EXTREME" if abs(z) > 3 else "ALERT"
                elif abs(z) > 1.5:
                    signal = "WATCH"
                else:
                    signal = "NORMAL"

                indicators.append({
                    "name": name,
                    "current": current,
                    "z": z,
                    "percentile": pct,
                    "signal": signal,
                })

        # Also try TimeSeriesDB for FRED series
        db = _get_db()
        if db is not None:
            try:
                fred_series = [
                    "T5YIE", "T10YIE", "CPIAUCSL", "UNRATE", "ICSA",
                    "BAMLC0A4CBBB", "BAMLH0A0HYM2", "MORTGAGE30US",
                    "HOUST", "RSXFS", "SAHMREALTIME",
                ]
                for series_id in fred_series:
                    try:
                        series_data = db.get_series(series_id)
                        if series_data and len(series_data) >= 10:
                            vals = [
                                _safe_float(s.get("value", s) if isinstance(s, dict) else s)
                                for s in series_data
                            ]
                            current = vals[-1]
                            z = _z_score(current, vals)
                            pct = _percentile_rank(current, vals)
                            signal = (
                                "EXTREME" if abs(z) > 3
                                else "ALERT" if abs(z) > 2
                                else "WATCH" if abs(z) > 1.5
                                else "NORMAL"
                            )
                            indicators.append({
                                "name": series_id,
                                "current": current,
                                "z": z,
                                "percentile": pct,
                                "signal": signal,
                            })
                    except Exception:
                        continue
            except Exception:
                pass

        if not indicators:
            lines.append('<p class="muted">No indicator data available for z-score analysis.</p>')
            return "\n".join(lines)

        # Sort by absolute z-score, show top 10
        indicators.sort(key=lambda x: abs(x["z"]), reverse=True)
        top = indicators[:10]

        lines.append('<table class="ztable">')
        lines.append(
            "<thead><tr>"
            "<th>Indicator</th><th>Current</th><th>Z-Score</th>"
            "<th>Percentile</th><th>Signal</th>"
            "</tr></thead><tbody>"
        )

        for ind in top:
            z_val = ind["z"]
            z_color = _color_change(z_val)
            bold_class = " bold" if abs(z_val) > 2 else ""
            signal = ind["signal"]
            signal_color = {
                "EXTREME": "red",
                "ALERT": "amber",
                "WATCH": "blue",
                "NORMAL": "muted",
            }.get(signal, "muted")

            lines.append(
                f'<tr>'
                f'<td>{_esc(ind["name"])}</td>'
                f'<td class="mono">{_format_number(ind["current"])}</td>'
                f'<td class="mono {z_color}{bold_class}">{z_val:+.2f}</td>'
                f'<td class="mono">{ind["percentile"]:.0f}th</td>'
                f'<td class="{signal_color}">{signal}</td>'
                f'</tr>'
            )

        lines.append("</tbody></table>")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Section 7: Open Research Calls
    # ------------------------------------------------------------------

    def _section_open_calls(self) -> str:
        lines: list[str] = ['<h2>Open Research Calls</h2>']

        open_calls = self.market_data.get("_open_calls", [])

        # Also try ledger directly
        if not open_calls:
            ledger = _get_ledger()
            if ledger is not None:
                try:
                    open_calls = ledger.get_open_calls()
                except Exception:
                    pass

        if not open_calls:
            lines.append('<p class="muted">No open research calls.</p>')
            return "\n".join(lines)

        lines.append('<table class="calls-table">')
        lines.append(
            "<thead><tr>"
            "<th>Instrument</th><th>Direction</th><th>Entry</th>"
            "<th>Target</th><th>Stop</th><th>Horizon</th><th>Status</th>"
            "</tr></thead><tbody>"
        )

        for call in open_calls:
            if isinstance(call, dict):
                instrument = call.get("instrument", "")
                direction = call.get("direction", "")
                entry = call.get("entry_level", "")
                target = call.get("target_level", "")
                stop = call.get("stop_level", "")
                horizon = call.get("time_horizon", "")
                status = call.get("status", "")
            else:
                instrument = getattr(call, "instrument", "")
                direction = getattr(call, "direction", "")
                entry = getattr(call, "entry_level", "")
                target = getattr(call, "target_level", "")
                stop = getattr(call, "stop_level", "")
                horizon = getattr(call, "time_horizon", "")
                status = getattr(call, "status", "")

            dir_color = "green" if direction == "bullish" else "red" if direction == "bearish" else ""

            lines.append(
                f'<tr>'
                f'<td>{_esc(str(instrument))}</td>'
                f'<td class="{dir_color}">{_esc(str(direction))}</td>'
                f'<td class="mono">{_esc(str(entry))}</td>'
                f'<td class="mono">{_esc(str(target))}</td>'
                f'<td class="mono">{_esc(str(stop))}</td>'
                f'<td>{_esc(str(horizon))}</td>'
                f'<td>{_esc(str(status))}</td>'
                f'</tr>'
            )

        lines.append("</tbody></table>")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Section 8: Footer
    # ------------------------------------------------------------------

    def _section_footer(self) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            '<div class="footer">'
            "<p><strong>Disclaimer:</strong> This Morning Brief is generated by the finnote "
            "multi-agent research system for informational and educational purposes only. "
            "It does not constitute investment advice or a recommendation to buy, sell, or "
            "hold any security. Past performance is not indicative of future results.</p>"
            "<p><strong>Methodology:</strong> Market data sourced from FRED, yfinance, and "
            "public RSS feeds. Z-scores computed against 2-year rolling history. News-data "
            "pairing uses keyword extraction to link headlines to tracked instruments. "
            "Agent debate summaries reflect AI-generated analysis.</p>"
            f"<p>Generated {now} &middot; Run <code>{_esc(self.run_id)}</code> &middot; "
            f"finnote v0.1</p>"
            "</div>"
        )
