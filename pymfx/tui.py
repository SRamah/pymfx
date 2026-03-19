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
    from textual.widgets import (
        DataTable,
        Footer,
        Header,
        Label,
        Static,
        TabbedContent,
        TabPane,
    )
except ImportError as _err:
    raise ImportError(
        "The TUI requires the 'textual' package.\n"
        "Install it with:  pip install pymfx[tui]"
    ) from _err

from .fair import fair_score
from .models import MfxFile
from .parser import parse
from .stats import flight_stats
from .validator import validate

# ---------------------------------------------------------------------------
# Colour palette (Textual CSS colours)
# ---------------------------------------------------------------------------

_CSS = """
Screen {
    background: $surface;
}

#title-bar {
    height: 1;
    background: $accent;
    color: $text;
    padding: 0 2;
    text-style: bold;
}

.panel-title {
    background: $primary;
    color: $text;
    text-style: bold;
    padding: 0 1;
    height: 1;
}

#overview-left {
    width: 1fr;
    border: round $primary;
    margin: 0 1 0 0;
}

#overview-right {
    width: 1fr;
    border: round $primary;
}

#meta-content {
    padding: 1 2;
}

#stats-content {
    padding: 1 2;
}

#fair-content {
    padding: 0 2 1 2;
}

#validation-bar {
    height: 3;
    border: round $primary;
    margin-top: 1;
    padding: 0 2;
    content-align: left middle;
}

.valid-ok {
    color: $success;
    text-style: bold;
}

.valid-err {
    color: $error;
    text-style: bold;
}

.valid-warn {
    color: $warning;
    text-style: bold;
}

.kv-label {
    color: $text-muted;
}

.kv-value {
    color: $text;
    text-style: bold;
}

.fair-score {
    color: $accent;
    text-style: bold;
}

.section-sep {
    color: $primary-darken-2;
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
"""


# ---------------------------------------------------------------------------
# Helper: key-value row markup
# ---------------------------------------------------------------------------

def _kv(label: str, value: str, width: int = 14) -> str:
    label_padded = f"{label:<{width}}"
    return f"[dim]{label_padded}[/dim]  {value}"


def _badge(value: float, thresholds: tuple[float, float] = (0.75, 0.90)) -> str:
    """Colour a 0-1 float value as green/yellow/red."""
    if value >= thresholds[1]:
        return f"[green]{value:.2f}[/green]"
    if value >= thresholds[0]:
        return f"[yellow]{value:.2f}[/yellow]"
    return f"[red]{value:.2f}[/red]"


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class MetaPanel(Static):
    """Displays [meta] fields."""

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
    """Displays flight statistics + FAIR score."""

    def __init__(self, mfx: MfxFile) -> None:
        super().__init__()
        self._mfx = mfx

    def compose(self) -> ComposeResult:
        stats = flight_stats(self._mfx)
        score = fair_score(self._mfx)

        stats_lines = [
            "[bold $primary]FLIGHT STATISTICS[/bold $primary]",
            "",
            _kv("points",       f"[cyan]{stats.point_count}[/cyan]"),
            _kv("duration",     f"[cyan]{stats.duration_s:.1f} s[/cyan]"),
            _kv("distance",     f"[cyan]{stats.total_distance_m:.1f} m[/cyan]"),
            _kv("alt max",      f"[cyan]{stats.alt_max_m:.1f} m[/cyan]" if stats.alt_max_m is not None else "—"),
            _kv("alt min",      f"[cyan]{stats.alt_min_m:.1f} m[/cyan]" if stats.alt_min_m is not None else "—"),
            _kv("alt mean",     f"[cyan]{stats.alt_mean_m:.1f} m[/cyan]" if stats.alt_mean_m is not None else "—"),
            _kv("speed max",    f"[cyan]{stats.speed_max_ms:.1f} m/s[/cyan]" if stats.speed_max_ms is not None else "—"),
            _kv("speed mean",   f"[cyan]{stats.speed_mean_ms:.1f} m/s[/cyan]" if stats.speed_mean_ms is not None else "—"),
            _kv("freq",         f"[cyan]{self._mfx.trajectory.frequency_hz or '—'} Hz[/cyan]"),
        ]

        fair_lines = [
            "",
            "[bold $primary]FAIR SCORE[/bold $primary]",
            "",
            f"  S = {_badge(score.S)}   "
            f"F={_badge(score.F)}  A={_badge(score.A)}  "
            f"I={_badge(score.interop)}  R={_badge(score.R)}",
        ]

        yield Label("\n".join(stats_lines + fair_lines), id="stats-content")


class ValidationBar(Static):
    """One-line validation result."""

    def __init__(self, mfx: MfxFile, raw_text: str) -> None:
        super().__init__()
        self._mfx = mfx
        self._raw = raw_text

    def compose(self) -> ComposeResult:
        result = validate(self._mfx, raw_text=self._raw)
        errors   = [i for i in result.issues if i.level == "error"]
        warnings = [i for i in result.issues if i.level == "warning"]
        if result.is_valid and not warnings:
            text = "[green bold]✓  Valid file — no issues found.[/green bold]"
        else:
            parts = []
            if errors:
                parts.append(f"[red bold]✗ {len(errors)} error(s)[/red bold]")
            if warnings:
                parts.append(f"[yellow bold]⚠ {len(warnings)} warning(s)[/yellow bold]")
            details = "  ·  ".join(
                f"{i.code}: {i.message}" for i in (errors + warnings)[:3]
            )
            text = "  ".join(parts) + f"  [dim]{details}[/dim]"
        yield Label(text, id="validation-bar")


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class MfxTui(App):
    """pymfx TUI — interactive viewer for .mfx flight files."""

    CSS = _CSS

    BINDINGS = [
        Binding("q",     "quit",        "Quit"),
        Binding("1",     "show_tab('overview')",    "Overview"),
        Binding("2",     "show_tab('trajectory')",  "Trajectory"),
        Binding("3",     "show_tab('events')",      "Events"),
    ]

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._raw  = path.read_text(encoding="utf-8")
        self._mfx  = parse(self._raw)

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        mfx = self._mfx
        yield Header(show_clock=True)

        with TabbedContent(initial="overview"):

            # ---- TAB 1: Overview ----
            with TabPane("Overview [1]", id="overview"):
                with Horizontal():
                    with ScrollableContainer(id="overview-left"):
                        yield MetaPanel(mfx)
                    with ScrollableContainer(id="overview-right"):
                        yield StatsPanel(mfx)
                yield ValidationBar(mfx, self._raw)

            # ---- TAB 2: Trajectory ----
            with TabPane("Trajectory [2]", id="trajectory"):
                table = DataTable(id="traj-table", zebra_stripes=True, cursor_type="row")
                yield table

            # ---- TAB 3: Events ----
            with TabPane("Events [3]", id="events"):
                table = DataTable(id="ev-table", zebra_stripes=True, cursor_type="row")
                yield table

        yield Footer()

    # ------------------------------------------------------------------
    # on_mount: populate DataTables
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self.title = f"pymfx  ·  {self._path.name}"
        self.sub_title = f".mfx v{self._mfx.version}  ·  {len(self._mfx.trajectory.points)} points"
        self._populate_trajectory()
        self._populate_events()

    def _populate_trajectory(self) -> None:
        table: DataTable = self.query_one("#traj-table", DataTable)
        pts = self._mfx.trajectory.points
        if not pts:
            table.add_column("(empty)")
            return

        # Build columns from schema fields
        schema_names = [sf.name for sf in self._mfx.trajectory.schema_fields]
        if not schema_names:
            schema_names = ["t", "lat", "lon", "alt_m", "speed_ms"]

        for col in schema_names:
            table.add_column(col, key=col)

        for p in pts:
            row = []
            for name in schema_names:
                if name == "t":
                    row.append(f"{p.t:.3f}")
                elif name == "lat":
                    row.append(f"{p.lat:.6f}" if p.lat is not None else "—")
                elif name == "lon":
                    row.append(f"{p.lon:.6f}" if p.lon is not None else "—")
                elif name == "alt_m":
                    row.append(f"{p.alt_m:.1f}" if p.alt_m is not None else "—")
                elif name == "speed_ms":
                    row.append(f"{p.speed_ms:.2f}" if p.speed_ms is not None else "—")
                elif name == "heading":
                    row.append(f"{p.heading:.1f}" if p.heading is not None else "—")
                elif name == "roll":
                    row.append(f"{p.roll:.2f}" if p.roll is not None else "—")
                elif name == "pitch":
                    row.append(f"{p.pitch:.2f}" if p.pitch is not None else "—")
                else:
                    val = p.extra.get(name)
                    row.append(str(val) if val is not None else "—")
            table.add_row(*row)

    def _populate_events(self) -> None:
        table: DataTable = self.query_one("#ev-table", DataTable)
        if not self._mfx.events or not self._mfx.events.events:
            table.add_column("(no events)")
            return

        schema_names = [sf.name for sf in self._mfx.events.schema_fields]
        if not schema_names:
            schema_names = ["t", "type", "severity", "detail"]

        for col in schema_names:
            table.add_column(col, key=col)

        for ev in self._mfx.events.events:
            row = []
            for name in schema_names:
                if name == "t":
                    row.append(f"{ev.t:.3f}")
                elif name == "type":
                    colour = {
                        "takeoff": "green", "landing": "red",
                        "waypoint": "cyan", "photo": "yellow",
                        "anomaly": "red bold", "warning": "yellow",
                    }.get(str(ev.type), "white")
                    row.append(f"[{colour}]{ev.type or '—'}[/{colour}]")
                elif name == "severity":
                    colour = {"info": "dim", "warning": "yellow", "critical": "red bold"}.get(
                        str(ev.severity), "dim"
                    )
                    row.append(f"[{colour}]{ev.severity or '—'}[/{colour}]")
                elif name == "detail":
                    row.append(str(ev.detail) if ev.detail is not None else "—")
                else:
                    val = ev.extra.get(name) if hasattr(ev, "extra") else None
                    row.append(str(val) if val is not None else "—")
            table.add_row(*row)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_tui(path: Path) -> None:
    """Launch the MfxTui app for the given .mfx file."""
    app = MfxTui(path)
    app.run()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m pymfx.tui <file.mfx>")
        sys.exit(1)
    run_tui(Path(sys.argv[1]))
