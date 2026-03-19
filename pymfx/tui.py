"""
pymfx.tui - Textual TUI for exploring .mfx flight files.

Usage:
    pymfx flight.mfx --tui
    python -m pymfx.tui flight.mfx

Requires: pip install pymfx[tui]
"""
from __future__ import annotations

from pathlib import Path

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, ScrollableContainer
    from textual.screen import ModalScreen
    from textual.widgets import (
        DataTable,
        Footer,
        Header,
        Label,
        ListItem,
        ListView,
        Sparkline,
        Static,
        TabbedContent,
        TabPane,
        TextArea,
    )
except ImportError as _err:
    raise ImportError(
        "The TUI requires the 'textual' package.\n"
        "Install it with:  pip install pymfx[tui]"
    ) from _err

from .anomaly import detect_anomalies
from .checksum import compute_checksum
from .convert import to_csv, to_geojson, to_gpx, to_kml
from .fair import fair_score
from .models import MfxFile
from .parser import parse
from .stats import flight_stats
from .validator import validate

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
Screen {
    background: $surface;
}

#overview-left {
    width: 1fr;
    border: round $primary;
    margin: 0 1 0 0;
    height: 1fr;
}

#overview-right {
    width: 1fr;
    border: round $primary;
    height: 1fr;
}

#overview-row {
    height: 1fr;
}

#meta-content {
    padding: 1 2;
}

#stats-content {
    padding: 1 2;
}

#sparkline-section {
    padding: 0 2 1 2;
    height: auto;
}

.spark-label {
    color: $text-muted;
    padding: 1 0 0 0;
    height: 1;
}

Sparkline {
    height: 4;
    margin: 0 0 1 0;
}

Sparkline > .sparkline--max-color {
    color: $error;
}

Sparkline > .sparkline--min-color {
    color: $success;
}

#validation-bar {
    height: auto;
    max-height: 8;
    border: round $primary;
    margin-top: 1;
    padding: 0 2;
    overflow-y: auto;
}

#anomaly-header {
    padding: 0 1 1 1;
    height: auto;
}

#fair-breakdown {
    padding: 1 2;
    height: auto;
    color: $text;
}

.section-title {
    color: $primary;
    text-style: bold;
    padding: 1 2 0 2;
}

DataTable {
    height: 1fr;
}

TabbedContent {
    height: 1fr;
}

TabPane {
    padding: 1;
}

/* Export modal */
ExportModal {
    align: center middle;
}

#export-dialog {
    background: $surface;
    border: double $accent;
    padding: 1 2;
    width: 40;
    height: auto;
}

#export-title {
    text-style: bold;
    color: $accent;
    margin-bottom: 1;
}

#export-list {
    height: auto;
    max-height: 12;
    border: round $primary;
}

#export-status {
    margin-top: 1;
    color: $success;
    text-style: bold;
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kv(label: str, value: str, width: int = 14) -> str:
    return f"[dim]{label:<{width}}[/dim]  {value}"


def _badge(value: float, thresholds: tuple[float, float] = (0.75, 0.90)) -> str:
    if value >= thresholds[1]:
        return f"[green]{value:.2f}[/green]"
    if value >= thresholds[0]:
        return f"[yellow]{value:.2f}[/yellow]"
    return f"[red]{value:.2f}[/red]"


def _speed_colour(speed: float | None, vmin: float, vmax: float) -> str:
    """Return a Rich colour for a speed value on a green→yellow→red gradient."""
    if speed is None or vmax <= vmin:
        return "white"
    ratio = (speed - vmin) / (vmax - vmin)
    if ratio < 0.33:
        return "green"
    if ratio < 0.66:
        return "yellow"
    return "red"


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class MetaPanel(Static):
    def __init__(self, mfx: MfxFile) -> None:
        super().__init__()
        self._mfx = mfx

    def compose(self) -> ComposeResult:
        m = self._mfx.meta
        sensors = ", ".join(m.sensors) if m.sensors else "—"
        lines = [
            "[bold $primary]META[/bold $primary]",
            "",
            _kv("id",          str(m.id or "—")),
            _kv("drone",       str(m.drone_id or "—")),
            _kv("type",        str(m.drone_type or "—")),
            _kv("pilot",       str(m.pilot_id or "—")),
            _kv("date start",  str(m.date_start or "—")),
            _kv("date end",    str(m.date_end or "—")),
            _kv("status",      f"[cyan]{m.status or '—'}[/cyan]"),
            _kv("application", str(m.application or "—")),
            _kv("location",    str(m.location or "—")),
            _kv("sensors",     f"[cyan]{sensors}[/cyan]"),
            _kv("license",     str(m.license or "—")),
            _kv("data level",  str(m.data_level or "—")),
            _kv("contact",     str(m.contact or "—")),
        ]
        if m.manufacturer:
            lines.append(_kv("manufacturer", str(m.manufacturer)))
        if m.crs:
            lines.append(_kv("crs", str(m.crs)))
        if m.altitude_ref:
            lines.append(_kv("alt ref", str(m.altitude_ref)))
        yield Label("\n".join(lines), id="meta-content")


class StatsPanel(Static):
    def __init__(self, mfx: MfxFile) -> None:
        super().__init__()
        self._mfx = mfx

    def compose(self) -> ComposeResult:
        stats = flight_stats(self._mfx)
        score = fair_score(self._mfx)
        pts   = self._mfx.trajectory.points

        # Stats block
        stats_lines = [
            "[bold $primary]FLIGHT STATISTICS[/bold $primary]",
            "",
            _kv("points",     f"[cyan]{stats.point_count}[/cyan]"),
            _kv("duration",   f"[cyan]{stats.duration_s:.1f} s[/cyan]"),
            _kv("distance",   f"[cyan]{stats.total_distance_m:.1f} m[/cyan]"),
            _kv("alt max",    f"[cyan]{stats.alt_max_m:.1f} m[/cyan]"   if stats.alt_max_m   is not None else "—"),
            _kv("alt min",    f"[cyan]{stats.alt_min_m:.1f} m[/cyan]"   if stats.alt_min_m   is not None else "—"),
            _kv("alt mean",   f"[cyan]{stats.alt_mean_m:.1f} m[/cyan]"  if stats.alt_mean_m  is not None else "—"),
            _kv("speed max",  f"[cyan]{stats.speed_max_ms:.1f} m/s[/cyan]" if stats.speed_max_ms is not None else "—"),
            _kv("speed mean", f"[cyan]{stats.speed_mean_ms:.1f} m/s[/cyan]" if stats.speed_mean_ms is not None else "—"),
            _kv("freq",       f"[cyan]{self._mfx.trajectory.frequency_hz or '—'} Hz[/cyan]"),
            "",
            "[bold $primary]FAIR SCORE[/bold $primary]",
            "",
            f"  S = {_badge(score.S)}   "
            f"F={_badge(score.F)}  A={_badge(score.A)}  "
            f"I={_badge(score.interop)}  R={_badge(score.R)}",
        ]
        yield Label("\n".join(stats_lines), id="stats-content")

        # Sparklines
        with Vertical(id="sparkline-section"):
            alts   = [p.alt_m   for p in pts if p.alt_m   is not None]
            speeds = [p.speed_ms for p in pts if p.speed_ms is not None]

            if alts:
                yield Label("▲ altitude (m)", classes="spark-label")
                yield Sparkline(alts,   summary_function=max)
            if speeds:
                yield Label("⚡ speed (m/s)", classes="spark-label")
                yield Sparkline(speeds, summary_function=max)

        # Full FAIR breakdown
        yield Label("[bold $primary]FAIR BREAKDOWN[/bold $primary]", classes="section-title")
        yield Static(score.breakdown(), id="fair-breakdown")


class ValidationBar(Static):
    def __init__(self, mfx: MfxFile, raw_text: str) -> None:
        super().__init__()
        self._mfx = mfx
        self._raw = raw_text

    def compose(self) -> ComposeResult:
        result   = validate(self._mfx, raw_text=self._raw)
        errors   = [i for i in result.issues if i.level == "error"]
        warnings = [i for i in result.issues if i.level == "warning"]

        # Checksum status
        traj = self._mfx.trajectory
        if traj.checksum:
            actual = compute_checksum(traj.raw_lines)
            cs_ok  = traj.checksum == actual
            cs_tag = "[green]✓ checksum[/green]" if cs_ok else "[red]✗ checksum mismatch[/red]"
        else:
            cs_tag = "[dim]— no checksum[/dim]"

        if result.is_valid and not warnings:
            summary = "[green bold]✓  Valid[/green bold]"
        else:
            parts = []
            if errors:
                parts.append(f"[red bold]✗ {len(errors)} error(s)[/red bold]")
            if warnings:
                parts.append(f"[yellow bold]⚠ {len(warnings)} warning(s)[/yellow bold]")
            summary = "  ".join(parts)

        lines = [f"{summary}   {cs_tag}"]
        for issue in errors + warnings:
            icon = "[red]✗[/red]" if issue.level == "error" else "[yellow]⚠[/yellow]"
            lines.append(f"  {icon} [dim]{issue.code}[/dim]  {issue.message}")

        yield Label("\n".join(lines), id="validation-bar")


# ---------------------------------------------------------------------------
# Export modal
# ---------------------------------------------------------------------------

_EXPORT_FORMATS = {
    "geojson": ("GeoJSON   (.geojson)", ".geojson", to_geojson),
    "gpx":     ("GPX 1.1   (.gpx)",    ".gpx",     to_gpx),
    "kml":     ("KML 2.2   (.kml)",    ".kml",     to_kml),
    "csv":     ("CSV       (.csv)",    ".csv",     to_csv),
    "json":    ("JSON      (.json)",   ".json",    None),
}


class ExportModal(ModalScreen):
    """Modal for choosing export format."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    def __init__(self, mfx: MfxFile, source_path: Path) -> None:
        super().__init__()
        self._mfx  = mfx
        self._path = source_path

    def compose(self) -> ComposeResult:
        with Vertical(id="export-dialog"):
            yield Label("⬇  Export as", id="export-title")
            items = [ListItem(Label(f"  {label}"), name=key)
                     for key, (label, _ext, _fn) in _EXPORT_FORMATS.items()]
            yield ListView(*items, id="export-list")
            yield Label("", id="export-status")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        fmt = event.item.name
        if fmt not in _EXPORT_FORMATS:
            return
        label, ext, fn = _EXPORT_FORMATS[fmt]
        out = self._path.with_suffix(ext)
        try:
            if fmt == "json":
                content = self._mfx.to_json()
            else:
                content = fn(self._mfx)
            out.write_text(content, encoding="utf-8")
            self.query_one("#export-status", Label).update(f"✓ Saved → {out.name}")
        except Exception as exc:
            self.query_one("#export-status", Label).update(f"[red]✗ {exc}[/red]")


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class MfxTui(App):
    """pymfx TUI — interactive viewer for .mfx flight files."""

    CSS = _CSS

    BINDINGS = [
        Binding("q",   "quit",                     "Quit"),
        Binding("1",   "show_tab('overview')",      "Overview"),
        Binding("2",   "show_tab('trajectory')",    "Trajectory"),
        Binding("3",   "show_tab('events')",        "Events"),
        Binding("4",   "show_tab('anomalies')",     "Anomalies"),
        Binding("5",   "show_tab('raw')",           "Raw"),
        Binding("e",   "export",                    "Export"),
    ]

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path    = path
        self._raw     = path.read_text(encoding="utf-8")
        self._mfx     = parse(self._raw)
        self._anomaly = detect_anomalies(self._mfx)

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        mfx = self._mfx
        yield Header(show_clock=True)

        with TabbedContent(initial="overview"):

            # ---- TAB 1: Overview ----
            with TabPane("Overview [1]", id="overview"):
                with Horizontal(id="overview-row"):
                    with ScrollableContainer(id="overview-left"):
                        yield MetaPanel(mfx)
                    with ScrollableContainer(id="overview-right"):
                        yield StatsPanel(mfx)
                yield ValidationBar(mfx, self._raw)

            # ---- TAB 2: Trajectory ----
            with TabPane("Trajectory [2]", id="trajectory"):
                yield DataTable(id="traj-table", zebra_stripes=True, cursor_type="row")

            # ---- TAB 3: Events ----
            with TabPane("Events [3]", id="events"):
                yield DataTable(id="ev-table", zebra_stripes=True, cursor_type="row")

            # ---- TAB 4: Anomalies ----
            with TabPane("Anomalies [4]", id="anomalies"):
                yield Static("", id="anomaly-header")
                yield DataTable(id="anomaly-table", zebra_stripes=True, cursor_type="row")

            # ---- TAB 5: Raw source ----
            with TabPane("Raw [5]", id="raw"):
                yield TextArea(
                    self._raw,
                    id="raw-view",
                    read_only=True,
                    theme="dracula",
                    show_line_numbers=True,
                )

        yield Footer()

    # ------------------------------------------------------------------
    # on_mount
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self.title = f"pymfx  ·  {self._path.name}"
        n_pts = len(self._mfx.trajectory.points)
        n_anom = self._anomaly.count
        anom_tag = f"  ·  [red]{n_anom} anomaly(ies)[/red]" if n_anom else ""
        self.sub_title = (
            f".mfx v{self._mfx.version}  ·  {n_pts} points{anom_tag}"
        )
        self._populate_trajectory()
        self._populate_events()
        self._populate_anomalies()

    def _populate_trajectory(self) -> None:
        table: DataTable = self.query_one("#traj-table", DataTable)
        pts = self._mfx.trajectory.points
        if not pts:
            table.add_column("(empty)")
            return

        schema_names = [sf.name for sf in self._mfx.trajectory.schema_fields] or \
                       ["t", "lat", "lon", "alt_m", "speed_ms"]

        for col in schema_names:
            table.add_column(col, key=col)

        # Speed range for colour gradient
        speeds = [p.speed_ms for p in pts if p.speed_ms is not None]
        vmin = min(speeds) if speeds else 0.0
        vmax = max(speeds) if speeds else 0.0

        for p in pts:
            colour = _speed_colour(p.speed_ms, vmin, vmax)
            row = []
            for name in schema_names:
                if name == "t":
                    row.append(f"[dim]{p.t:.3f}[/dim]")
                elif name == "lat":
                    row.append(f"{p.lat:.6f}" if p.lat is not None else "—")
                elif name == "lon":
                    row.append(f"{p.lon:.6f}" if p.lon is not None else "—")
                elif name == "alt_m":
                    row.append(f"[cyan]{p.alt_m:.1f}[/cyan]" if p.alt_m is not None else "—")
                elif name == "speed_ms":
                    if p.speed_ms is not None:
                        row.append(f"[{colour}]{p.speed_ms:.2f}[/{colour}]")
                    else:
                        row.append("—")
                elif name == "heading":
                    row.append(f"{p.heading:.1f}" if p.heading is not None else "—")
                elif name in ("roll", "pitch"):
                    val = getattr(p, name, None)
                    row.append(f"{val:.2f}" if val is not None else "—")
                else:
                    val = p.extra.get(name)
                    row.append(str(val) if val is not None else "—")
            table.add_row(*row)

    def _populate_events(self) -> None:
        table: DataTable = self.query_one("#ev-table", DataTable)
        if not self._mfx.events or not self._mfx.events.events:
            table.add_column("(no events)")
            return

        schema_names = [sf.name for sf in self._mfx.events.schema_fields] or \
                       ["t", "type", "severity", "detail"]

        for col in schema_names:
            table.add_column(col, key=col)

        _TYPE_COLOUR = {
            "takeoff": "green bold", "landing": "red bold",
            "waypoint": "cyan",      "photo": "yellow",
            "video_start": "bright_yellow", "video_stop": "orange1",
            "anomaly": "red bold",   "warning": "yellow",
            "rtl": "magenta",        "abort": "red bold",
        }
        _SEV_COLOUR = {
            "info": "dim", "warning": "yellow bold", "critical": "red bold",
        }

        for ev in self._mfx.events.events:
            row = []
            for name in schema_names:
                if name == "t":
                    row.append(f"[dim]{ev.t:.3f}[/dim]")
                elif name == "type":
                    c = _TYPE_COLOUR.get(str(ev.type), "white")
                    row.append(f"[{c}]{ev.type or '—'}[/{c}]")
                elif name == "severity":
                    c = _SEV_COLOUR.get(str(ev.severity), "dim")
                    row.append(f"[{c}]{ev.severity or '—'}[/{c}]")
                elif name == "detail":
                    row.append(str(ev.detail) if ev.detail is not None else "—")
                else:
                    val = ev.extra.get(name) if hasattr(ev, "extra") else None
                    row.append(str(val) if val is not None else "—")
            table.add_row(*row)

    def _populate_anomalies(self) -> None:
        report = self._anomaly
        header: Static   = self.query_one("#anomaly-header", Static)
        table:  DataTable = self.query_one("#anomaly-table", DataTable)

        if report.count == 0:
            header.update("[green bold]✓  No anomalies detected.[/green bold]")
            table.add_column("(no anomalies)")
            return

        # Summary line
        from collections import Counter
        kinds = Counter(a.kind for a in report.anomalies)
        summary = "  ·  ".join(f"{k} ×{v}" for k, v in kinds.items())
        header.update(
            f"[red bold]⚠  {report.count} anomaly(ies) found[/red bold]"
            f"  [dim]{summary}[/dim]"
        )

        table.add_column("t (s)",    key="t")
        table.add_column("type",     key="kind")
        table.add_column("severity", key="sev")
        table.add_column("detail",   key="detail")

        _KIND_C = {
            "speed_spike":     "yellow",
            "gps_jump":        "red bold",
            "altitude_cliff":  "orange1",
        }
        _SEV_C = {"warning": "yellow bold", "critical": "red bold"}

        for a in report.anomalies:
            kc  = _KIND_C.get(a.kind, "white")
            sc  = _SEV_C.get(a.severity, "dim")
            ico = "⚠" if a.severity == "warning" else "✗"
            table.add_row(
                f"[dim]{a.t:.3f}[/dim]",
                f"[{kc}]{a.kind}[/{kc}]",
                f"[{sc}]{ico} {a.severity}[/{sc}]",
                a.detail,
            )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_export(self) -> None:
        self.push_screen(ExportModal(self._mfx, self._path))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_tui(path: Path) -> None:
    """Launch the MfxTui app for the given .mfx file."""
    MfxTui(path).run()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m pymfx.tui <file.mfx>")
        sys.exit(1)
    run_tui(Path(sys.argv[1]))
