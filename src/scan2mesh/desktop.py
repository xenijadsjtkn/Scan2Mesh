"""Choose a scan and run the reference NKSR workflow on the original points."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


SUPPORTED_FORMATS = {".ply", ".pcd", ".pts", ".xyz", ".xyzn", ".xyzrgb"}


def default_runs_root() -> Path:
    if sys.platform == "win32":
        local_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_data) if local_data else Path.home() / "AppData" / "Local"
        return base / "Scan2Mesh"
    return Path(__file__).resolve().parents[2] / "runs"


RUNS_ROOT = default_runs_root()

# Fixed command: selected paths return as UTF-8 data, never as shell source.
_WINDOWS_PICKER = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = 'Scan auswaehlen'
$dialog.Filter = 'Punktwolken (*.ply;*.pcd;*.xyz;*.xyzn;*.xyzrgb;*.pts)|*.ply;*.pcd;*.xyz;*.xyzn;*.xyzrgb;*.pts|Alle Dateien (*.*)|*.*'
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
            filetypes=[("Punktwolken", "*.ply *.pcd *.xyz *.xyzn *.xyzrgb *.pts"), ("Alle Dateien", "*")],
        )
        return Path(selected) if selected else None
    finally:
        root.destroy()


def choose_scan_file() -> Path | None:
    return _pick_windows_scan() if sys.platform == "win32" else _pick_tk_scan()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan auswaehlen und direkt mit NKSR auf hoechster Detailstufe verarbeiten")
    parser.add_argument("--input", type=Path, help="Datei direkt verarbeiten, ohne Auswahldialog")
    parser.add_argument("--units", choices=["m", "mm"], default="m", help="Eingabekoordinaten; Standard: Meter")
    parser.add_argument("--output-root", type=Path, help="Stammverzeichnis fuer neue nksr-direkt-Ergebnisordner; Windows: LOCALAPPDATA/Scan2Mesh")
    parser.add_argument("--nksr-python", help="Vorhandener Linux-Python-Interpreter mit NKSR; sonst Umgebungsvariable oder automatische Suche")
    parser.add_argument("--nksr-wsl-distro", help="WSL-Distribution; sonst SCAN2MESH_NKSR_WSL_DISTRO oder Ubuntu-22.04")
    args = parser.parse_args(argv)
    source = args.input
    if source is None:
        print("Scan-Datei im Auswahldialog oeffnen ...", flush=True)
        try:
            source = choose_scan_file()
        except RuntimeError as exc:
            parser.exit(2, f"Scan2Mesh: {exc}\n")
        if source is None:
            print("Abgebrochen. Es wurde keine Datei verarbeitet.")
            return None
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        parser.error(f"Scan-Datei nicht gefunden: {source}")
    if source.suffix.lower() not in SUPPORTED_FORMATS:
        parser.error("Der NKSR-Direktlauf liest PLY, PCD, PTS, XYZ, XYZN oder XYZRGB. E57/RCP/RCS bitte vorher als PLY oder PTS exportieren.")

    # Cancellation and invalid files must not start WSL or import GPU packages.
    from .nksr_runtime import run_direct

    output_root = args.output_root.expanduser().resolve() if args.output_root is not None else RUNS_ROOT
    print(f"Eingabe: {source}", flush=True)
    print(f"Ausgabe-Stammverzeichnis: {output_root}", flush=True)
    print("NKSR direkt: Modell ks, Detailstufe 1.0, alle Originalpunkte.", flush=True)
    print("Beide Exporte: mit und ohne interne NKSR-Maske; Originalfarben werden uebernommen.", flush=True)
    try:
        mesh = run_direct(
            source, output_root, units=args.units,
            python=args.nksr_python, wsl_distro=args.nksr_wsl_distro,
        )
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"Scan2Mesh: {exc}\n")
    print(f"Fertig: {mesh.parent}", flush=True)
    print(f"Mesh: {mesh}", flush=True)
    print(f"Laufparameter und beide Exporte: {mesh.parent / 'run.json'}", flush=True)
    return mesh.parent


if __name__ == "__main__":
    main()
