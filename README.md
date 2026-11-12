# Scan2Mesh

Scan2Mesh rekonstruiert Punktwolken mit **NKSR direkt auf höchster Detailstufe**. Auf `main` verwenden Play, F5 und der Terminalstart denselben Ablauf wie der Referenzlauf `nksr-direkt-20261103-102607-9a8c5ff5`: alle Originalpunkte, Modell `ks`, `detail_level=1.0`, `mise_iter=1` und beide Meshvarianten mit und ohne interne NKSR-Maske.

Die vorhandene NKSR-Installation unter Linux beziehungsweise WSL wird weiterverwendet. Ein Wechsel auf einen anderen Scan2Mesh-Branch ist nicht erforderlich.

## In VS Code starten (Windows)

1. Den Scan2Mesh-Projektordner öffnen, in dem `main.py` und `pyproject.toml` liegen. Die Erweiterungen **Python** und **Python Debugger** installieren.
2. Auf `main` aktualisieren:

   ```powershell
   git switch main
   git pull --ff-only origin main
   ```

3. Falls `uv` fehlt, einmal installieren und VS Code neu starten:

   ```powershell
   winget install --id astral-sh.uv --exact
   ```

4. **Strg+Umschalt+B** drücken und warten, bis **Scan2Mesh: Umgebung vorbereiten** erfolgreich abgeschlossen ist. Die Python-Umgebung und der Cache liegen unter `%LOCALAPPDATA%\Scan2Mesh`, außerhalb des Repositorys und eines möglichen OneDrive-Ordners.
5. **`main.py` öffnen und ▶ „Python-Datei ausführen“ klicken.** Alternativ **F5** mit **Scan2Mesh: NKSR direkt (Standard)** verwenden.
6. Im Dateidialog die Punktwolke auswählen. **Abbrechen** beendet die Auswahl ohne Verarbeitung.

Im Terminal erscheint **„NKSR direkt: Modell ks, Detailstufe 1.0, alle Originalpunkte.“** Anschließend zeigt NKSR die Verarbeitungsstufen und den Ausgabepfad. Für diesen Standardlauf sind keine Detail-, Filter- oder Vergleichsparameter erforderlich.

### Falls Play versucht, den Ordner `.venv` auszuführen

Über **Strg+Umschalt+P → Python: Select Interpreter → Enter interpreter path** die Datei **`%LOCALAPPDATA%\Scan2Mesh\venv\Scripts\python.exe`** auswählen. Der Interpreter muss eine ausführbare Python-Datei sein. Eine bereits gespeicherte Auswahl wird durch Änderungen am Repository nicht automatisch ersetzt; siehe [VS-Code-Einstellungen](https://code.visualstudio.com/docs/python/settings-reference#general-python-settings).

Der direkte Start aus dem PowerShell-Terminal des Projekts funktioniert unabhängig von dieser Auswahl:

```powershell
& "$env:LOCALAPPDATA\Scan2Mesh\venv\Scripts\python.exe" .\main.py
```

## Vorhandene NKSR-Umgebung

Unter Windows verwendet der Start WSL, standardmäßig die Distribution **Ubuntu-22.04**. Eine ausdrücklich gesetzte Option oder Umgebungsvariable hat Vorrang:

| Einstellung | Option | Umgebungsvariable |
| --- | --- | --- |
| WSL-Distribution | `--nksr-wsl-distro` | `SCAN2MESH_NKSR_WSL_DISTRO` |
| Linux-Python mit NKSR | `--nksr-python` | `SCAN2MESH_NKSR_PYTHON` |

Ohne angegebenen Python-Pfad sucht der Starter nach einer bereits eingerichteten `nksr`-Umgebung in üblichen Conda-/Mamba-Verzeichnissen im Linux-Benutzerprofil und prüft, ob PyTorch und NKSR importierbar sind. Genau ein gefundener Interpreter wird verwendet. Bei keiner oder mehreren passenden Umgebungen nennt die Fehlermeldung die erforderliche Einstellung. Es werden keine Pakete automatisch in die NKSR-Umgebung installiert.

Für einen abweichenden vorhandenen Interpreter ist beispielsweise folgender Start möglich; den Beispielpfad ersetzen:

```powershell
uv run python main.py --nksr-wsl-distro Ubuntu-22.04 --nksr-python /home/DEIN_LINUXNAME/miniforge3/envs/nksr/bin/python
```

Eine einmalige, dauerhaft für Play/F5 verfügbare Konfiguration und die Einrichtung einer neuen NKSR-Umgebung beschreibt [NKSR einrichten](docs/nksr.md).

## Eingabe und Terminalstart

Unterstützt werden **PLY, PCD, PTS, XYZ, XYZN und XYZRGB**. E57 sowie ReCap-Dateien RCP/RCS vor diesem direkten Ablauf als PLY oder PTS exportieren. RGB-Farben und vorhandene Normalen lassen sich beispielsweise in PLY speichern.

Ohne Dateidialog:

```powershell
uv run python main.py --input "C:\Scans\Abstellkammer_01.pts"
```

Die Eingabekoordinaten werden standardmäßig als Meter interpretiert. Bei Millimeterkoordinaten ausdrücklich `--units mm` angeben. Einheiten werden nicht automatisch erkannt; die Ergebnisse erhalten die ursprünglichen Einheiten und Weltkoordinaten zurück.

Ein eigener Ausgabe-Stammordner ist möglich:

```powershell
uv run python main.py --input "C:\Scans\scan.ply" --output-root "D:\Scan2Mesh-Ergebnisse"
```

`uv run scan2mesh`, `uv run scan2mesh --input DATEI` und `uv run scan2mesh process DATEI --output-root ORDNER` führen denselben Ablauf aus. Beim `process`-Befehl bleibt `--output` als Alias für das **Stammverzeichnis** verfügbar; jeder Lauf erzeugt darunter einen neuen Ergebnisordner. Der frühere PowerShell-Start `powershell.exe -NoProfile -STA -File .\nksr-direkt.ps1` ruft ebenfalls den gemeinsamen Standardstart auf.

Für optionale `uv`-Terminalbefehle unter Windows dieselbe externe Umgebung und denselben Cache wie in VS Code wählen:

```powershell
$env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA 'Scan2Mesh\venv'
$env:UV_CACHE_DIR = Join-Path $env:LOCALAPPDATA 'Scan2Mesh\cache\uv'
```

Unter Linux läuft NKSR direkt im gewählten Interpreter; dort beispielsweise `uv run python main.py --input scan.ply --nksr-python /pfad/zur/nksr-umgebung/bin/python` verwenden.

## Ergebnisse

Unter Windows liegt jeder Lauf in einem neuen Ordner unter **`%LOCALAPPDATA%\Scan2Mesh\nksr-direkt-<Zeitstempel>-<Kennung>`**. Auf anderen Betriebssystemen liegt der Standard unter `runs` im Repository. Der genaue Pfad steht im Terminal. Bestehende Ergebnisse und die Quelldatei bleiben erhalten.

| Datei | Inhalt |
| --- | --- |
| `mesh_colored.ply` | Mesh mit interner NKSR-Maske (`trim=True`), mit Farben aus der Originalpunktwolke |
| `mesh_colored_untrimmed.ply` | Mesh ohne interne NKSR-Maske (`trim=False`), ebenfalls mit Originalfarben |
| `nksr_raw.npz` | Unveränderte Vertex- und Dreiecksarrays des maskierten NKSR-Exports samt Koordinatenmetadaten |
| `nksr_raw_untrimmed.npz` | Entsprechende Roharrays des unmaskierten Exports |
| `run.json` | Eingabe, Punktzahl, Einheiten, Normalenherkunft, Modell, Detailstufe und beide Exporte mit ihren Zählwerten und Pfaden |
| `cuda_diagnostics.json` | GPU-Name, PyTorch-/CUDA-Versionen und Speicherwerte beim Start, vor dem Punkttransfer und bei einem CUDA-Transferfehler |

Wenn die Quelle keine RGB-Farben besitzt, heißen die PLY-Dateien stattdessen `mesh_raw.ply` und `mesh_raw_untrimmed.ply`. Zum Ansehen CloudCompare oder MeshLab verwenden und vorhandene RGB-Farben einschalten.

Der Ablauf entfernt keine Punkte, filtert keine Ausreißer, segmentiert keine Flächen und bereinigt oder vereinfacht das NKSR-Mesh nicht nachträglich. Vorhandene Normalen werden übernommen; fehlende Normalen werden mit Open3D geschätzt und konsistent ausgerichtet. Die Einzelheiten einschließlich Farbübertragung und Maskenvergleich stehen in [NKSR-Direktlauf](docs/nksr-direct.md).

Die Punktwolke wird vollständig geladen und ohne Chunking rekonstruiert. RAM und GPU-Speicher begrenzen die verarbeitbare Größe. Bei Speichermangel oder NKSR-Fehlern wird der Lauf mit einer Fehlermeldung beendet; es erfolgt kein automatischer Wechsel des Verfahrens oder der Detailstufe. Bereits geschriebene Rohdaten und Exporte bleiben erhalten. Höchste Detailstufe garantiert kein rauschfreies oder geschlossenes Mesh; Originalpunkte, feine Bauteile und echte Öffnungen weiterhin vergleichen.

Bei einem CUDA-Fehler schon beim Übertragen der Punkte zuerst die ausgegebene GPU-Diagnose prüfen. `nvidia-smi` nach dem Abbruch zeigt den späteren Zustand; daraus lässt sich die Belegung zum Fehlerzeitpunkt nicht sicher ableiten. Schlägt der Transfer vor der Rekonstruktion fehl, liegt noch keine `run.json` mit Mesh-Ergebnissen vor. Die zusätzlichen Diagnosen ändern weder Originalpunkte noch Detailstufe oder Rekonstruktionsverfahren.

Die älteren Module für Ball Pivoting, Poisson und geometrische Segmentierung bleiben als Vergleichscode im Repository; die normalen Programmstarts rufen sie nicht auf. Die automatisierten Tests prüfen unter anderem Startweiterleitung und den Exportvertrag mit einem nachgebildeten NKSR-Backend. Eine echte GPU-Rekonstruktion benötigt die eingerichtete Linux-/WSL-Umgebung.

NKSR-Code und vortrainierte Gewichte haben eigene Lizenzbedingungen; siehe [Nutzung und Lizenz](docs/nksr.md#nutzung-und-lizenz).
