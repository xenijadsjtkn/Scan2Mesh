"""Local desktop entry point: choose a scan, then process it."""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic


class _ProgressPrinter:
    """Show real stages and elapsed time, without claiming an estimated finish."""

    def __init__(self, heartbeat_interval: float = 30.0):
        self._interval = heartbeat_interval
        self._started = monotonic()
        self._last_update = self._started
        self._message = "Verarbeitung startet"
        self._stop = Event()
        self._lock = Lock()
        self._thread = Thread(target=self._heartbeat, name="scan2mesh-progress", daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._stop.set()
        self._thread.join()

    def _print(self, message: str, now: float) -> None:
        elapsed = max(0, int(now - self._started))
        minutes, seconds = divmod(elapsed, 60)
        print(f"[{minutes:02d}:{seconds:02d}] {message}", flush=True)

    def __call__(self, message: str) -> None:
        with self._lock:
            self._message = message
            self._last_update = monotonic()
            self._print(message, self._last_update)

    def _heartbeat(self) -> None:
        while not self._stop.wait(self._interval):
            with self._lock:
                now = monotonic()
                if now - self._last_update >= self._interval:
                    self._print(f"Warte auf Abschluss: {self._message}", now)


def default_runs_root() -> Path:
    if sys.platform == "win32":
        local_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_data) if local_data else Path.home() / "AppData" / "Local"
        return base / "Scan2Mesh" / "runs"
    return Path(__file__).resolve().parents[2] / "runs"


RUNS_ROOT = default_runs_root()

# Fixed command: selected paths return as UTF-8 data, never as shell source.
_WINDOWS_PICKER = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = 'Scan auswaehlen'
$dialog.Filter = 'Punktwolken (*.e57;*.ply;*.pcd;*.xyz;*.xyzn;*.xyzrgb;*.pts)|*.e57;*.ply;*.pcd;*.xyz;*.xyzn;*.xyzrgb;*.pts|Alle Dateien (*.*)|*.*'
$dialog.CheckFileExists = $true
$dialog.Multiselect = $false
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.Opacity = 0
try {
    $owner.Show()
    if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::WriteLine($dialog.FileName)
    }
} finally {
    $dialog.Dispose()
    $owner.Close()
    $owner.Dispose()
}
"""


def _pick_windows_scan() -> Path | None:
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", _WINDOWS_PICKER],
            check=True, capture_output=True, text=True, encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        raise RuntimeError(f"Windows-Dateiauswahl konnte nicht geoeffnet werden: {detail}") from exc
    selected = completed.stdout.rstrip("\r\n")
    return Path(selected) if selected else None


def _pick_tk_scan() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise RuntimeError("Die Dateiauswahl benoetigt Tk auf diesem System. Alternativ --input DATEI verwenden.") from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("Die Dateiauswahl benoetigt einen lokalen Desktop. Alternativ --input DATEI verwenden.") from exc
    try:
        root.withdraw()
        selected = filedialog.askopenfilename(
            parent=root, title="Scan auswählen",
            filetypes=[("Punktwolken", "*.e57 *.ply *.pcd *.xyz *.xyzn *.xyzrgb *.pts"), ("Alle Dateien", "*")],
        )
        return Path(selected) if selected else None
    finally:
        root.destroy()


def choose_scan_file() -> Path | None:
    return _pick_windows_scan() if sys.platform == "win32" else _pick_tk_scan()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Datei auswaehlen und mit Scan2Mesh verarbeiten")
    source_args = parser.add_mutually_exclusive_group()
    source_args.add_argument("--input", type=Path, help="Datei direkt verarbeiten, ohne Auswahldialog")
    source_args.add_argument("--demo", action="store_true", help="Synthetische Demo statt eigener Datei")
    parser.add_argument("--units", choices=["m", "mm"], default="m", help="Eingabekoordinaten; Standard: Meter")
    parser.add_argument("--voxel-size", type=float, help="Voxelgroesse in Eingabeeinheiten; 0 erhaelt die volle Punktaufloesung (Standard fuer eigene Scans; Demo: 0.025 m)")
    parser.add_argument("--output-root", type=Path, help="Speicherort fuer neue Ergebnisordner; Windows-Standard: LOCALAPPDATA/Scan2Mesh/runs")
    parser.add_argument("--surface-mode", choices=["global", "segmented"], default="global", help="Segmentierte Rekonstruktion als geometrische Vorschau")
    args = parser.parse_args(argv)
    if args.demo and args.units != "m":
        parser.error("Die synthetische Demo verwendet Meter.")
    source = args.input
    if source is None and not args.demo:
        print("Scan-Datei im Auswahldialog oeffnen ...", flush=True)
        try:
            source = choose_scan_file()
        except RuntimeError as exc:
            parser.exit(2, f"Scan2Mesh: {exc}\n")
        if source is None:
            print("Abgebrochen. Es wurde keine Datei verarbeitet.")
            return None
    if source is not None:
        source = Path(source).resolve()
        if not source.is_file():
            parser.error(f"Scan-Datei nicht gefunden: {source}")

    # Cancelling must not initialize reconstruction or create output folders.
    from .demo import generate_demo
    from .pipeline import PipelineConfig, run_pipeline

    scale = 1 if args.units == "m" else 1_000
    try:
        config = PipelineConfig(
            voxel_size=args.voxel_size if args.voxel_size is not None else (0.025 if args.demo else 0.0),
            plane_distance=0.015 if args.demo else 0.01 * scale,
            surface_mode=args.surface_mode,
            max_planes=8 if args.surface_mode == "segmented" else 3,
        )
    except ValueError as exc:
        parser.error(str(exc))

    runs_root = args.output_root.expanduser().resolve() if args.output_root is not None else RUNS_ROOT
    try:
        runs_root.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(prefix="vscode-demo-" if args.demo else "vscode-scan-", dir=runs_root))
    except OSError as exc:
        parser.exit(2, f"Scan2Mesh: Ausgabeordner kann nicht angelegt werden: {runs_root}: {exc}\n")
    if args.demo:
        source = run_dir / "demo.ply"
        generate_demo(source)
    result = run_dir / "result"
    print(f"Eingabe: {source}", flush=True)
    print(f"Ausgabe: {result}", flush=True)
    print("Der Ergebnisordner wird erst nach Abschluss der Verarbeitung und Qualitaetspruefung angelegt.", flush=True)
    print(f"Koordinateneinheit: {args.units}; Voxelgroesse: {config.voxel_size}", flush=True)
    if config.voxel_size == 0:
        print("Detailstufe: volle Punktaufloesung, keine Voxelreduktion.", flush=True)
    print("Verarbeitung laeuft ...", flush=True)
    if args.surface_mode == "segmented":
        print("Vorschau: zusammenhaengende Ebenenbereiche, keine semantische Objekterkennung.", flush=True)
    try:
        with _ProgressPrinter() as progress:
            report = run_pipeline(source, result, config, progress=progress)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"Scan2Mesh: {exc}\n")
    print(f"Fertig: {report['counts']['mesh_triangles']} Dreiecke")
    print(f"Mesh: {result / 'mesh.ply'}")
    print(f"Qualitaetsbericht: {result / 'report.json'}")
    print("Das Mesh laesst sich in CloudCompare oder MeshLab oeffnen.")
    return result


if __name__ == "__main__":
    main()
