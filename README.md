# Scan2Mesh

Scan2Mesh rekonstruiert Punktwolken mit **NKSR direkt auf höchster Detailstufe**. Auf `main` verwenden Play, F5 und der Terminalstart denselben Ablauf wie der Referenzlauf `nksr-direkt-20261103-102607-9a8c5ff5`: alle Originalpunkte, Modell `ks`, `detail_level=1.0`, `mise_iter=1` und beide Meshvarianten mit und ohne interne NKSR-Maske.

## Auf einem neuen Windows-Rechner starten

Voraussetzungen sind Windows mit einer NVIDIA-GPU und einem funktionierenden NVIDIA-Windows-Treiber, Internetzugang sowie Administratorrechte für die einmalige WSL-Einrichtung. Python, Git, Ubuntu und VS Code müssen vorher nicht installiert sein.

1. Auf [GitHub](https://github.com/xenijadsjtkn/Scan2Mesh) den Branch **main** wählen und **Code → Download ZIP** anklicken.
2. Die ZIP-Datei vollständig in einen beschreibbaren Ordner entpacken. Die Programme aus dem entpackten Ordner starten, nicht direkt aus der ZIP-Datei.
3. **`Einrichten.cmd` doppelklicken.** Eine Abfrage für die WSL-Aktivierung bestätigen. Falls das Setup einen Windows-Neustart verlangt, neu starten und danach **`Einrichten.cmd` erneut öffnen**.
4. Warten, bis die Einrichtung erfolgreich abgeschlossen ist. Sie lädt die benötigten Pakete, baut NKSR in einer eigenen WSL-Umgebung und prüft eine kleine echte GPU-Rekonstruktion mit beiden Meshvarianten.
5. **`Starten.cmd` doppelklicken** und im Dateidialog die Punktwolke auswählen.

Die erste Einrichtung lädt größere Pakete und kompiliert native Erweiterungen. Sie kann deutlich länger dauern als ein normaler Programmstart. Hier wird keine bereits auf deiner Hardware geprüfte, vorinstallierte WSL-Abbildung verteilt. Erst die lokale GPU-Prüfung bestätigt, dass die eingerichtete Umgebung dort rekonstruieren kann. Einzelheiten und Hilfe bei einem Abbruch stehen in [Windows einrichten](docs/windows-setup.md).

Für spätere Läufe genügt **`Starten.cmd`**; dafür sind keine Administratorrechte erforderlich. Die normale Rekonstruktion verwendet weiterhin alle Originalpunkte, Detailstufe 1.0 und beide NKSR-Exporte. Die eigene WSL-Distribution **Scan2Mesh-NKSR** und die Python-Umgebungen werden vom Setup verwaltet. Vorhandene andere WSL-Distributionen und Python-Umgebungen bleiben erhalten.

## In VS Code starten

Eine vorhandene NKSR-Installation kann weiterverwendet werden. Das Setup kann eine ausdrücklich gewählte bestehende Umgebung nach erfolgreicher GPU-Prüfung registrieren; sonst richtet es die eigene Umgebung ein. Auf `main` führen alle Starts denselben Rekonstruktionsablauf aus, ein Branchwechsel ist nicht erforderlich.

Nach der Einrichtung den entpackten beziehungsweise geklonten Projektordner in VS Code öffnen. Die Erweiterungen **Python** und **Python Debugger** installieren. **`main.py` öffnen und ▶ „Python-Datei ausführen“ klicken** oder **F5** mit **Scan2Mesh: NKSR direkt (Standard)** verwenden. Die externe Windows-Python-Umgebung liegt unter `%LOCALAPPDATA%\Scan2Mesh\venv`.

Bei einer bestehenden Git-Kopie lässt sich `main` im Terminal aktualisieren:

```powershell
git switch main
git pull --ff-only origin main
```

Im Terminal erscheint **„NKSR direkt: Modell ks, Detailstufe 1.0, alle Originalpunkte.“** Anschließend zeigt NKSR die Verarbeitungsstufen und den Ausgabepfad. Für den Standardlauf sind keine Detail-, Filter- oder Vergleichsparameter erforderlich.

## Vorhandene NKSR-Umgebung

Nach erfolgreicher Einrichtung speichert Scan2Mesh die verwendete WSL-Distribution und den NKSR-Python-Pfad in **`%LOCALAPPDATA%\Scan2Mesh\backend.json`**. `Starten.cmd` und Play/F5 verwenden diese Konfiguration automatisch. Die Reihenfolge ist: ausdrückliche Kommandozeilenoption, Umgebungsvariable, gespeicherte Konfiguration, automatische Suche. Für eine abweichende bestehende Installation stehen diese Einstellungen zur Verfügung:

| Einstellung | Option | Umgebungsvariable |
| --- | --- | --- |
| WSL-Distribution | `--nksr-wsl-distro` | `SCAN2MESH_NKSR_WSL_DISTRO` |
| Linux-Python mit NKSR | `--nksr-python` | `SCAN2MESH_NKSR_PYTHON` |

Ohne angegebenen Python-Pfad sucht der Starter nach einer bereits eingerichteten `nksr`-Umgebung in üblichen Conda-/Mamba-Verzeichnissen im Linux-Benutzerprofil und prüft, ob PyTorch und NKSR importierbar sind. Genau ein gefundener Interpreter wird verwendet. Bei keiner oder mehreren passenden Umgebungen nennt die Fehlermeldung die erforderliche Einstellung. Der normale Programmstart installiert keine Pakete in diese vorhandene NKSR-Umgebung. Ohne gespeicherte oder ausdrücklich gewählte Distribution bleibt für ältere Installationen Ubuntu-22.04 die Vorgabe.

Für einen abweichenden vorhandenen Interpreter ist beispielsweise folgender Start möglich; den Beispielpfad ersetzen:

```powershell
uv run python main.py --nksr-wsl-distro Ubuntu-22.04 --nksr-python /home/DEIN_LINUXNAME/miniforge3/envs/nksr/bin/python
```

Die automatische Einrichtung beschreibt [Windows einrichten](docs/windows-setup.md). Hinweise für vorhandene und manuell verwaltete Installationen stehen unter [NKSR-Umgebung](docs/nksr.md).

## Eingabe und optionale Terminalstarts

Unterstützt werden **PLY, PCD, PTS, XYZ, XYZN und XYZRGB**. E57 sowie ReCap-Dateien RCP/RCS vor diesem direkten Ablauf als PLY oder PTS exportieren. RGB-Farben und vorhandene Normalen lassen sich beispielsweise in PLY speichern.

Nach der Einrichtung lässt sich `Starten.cmd` auch im PowerShell-Terminal aufrufen. Ohne Dateidialog:

```powershell
.\Starten.cmd -InputFile "C:\Scans\Abstellkammer_01.pts"
```

Die Eingabekoordinaten werden standardmäßig als Meter interpretiert. Bei Millimeterkoordinaten ausdrücklich `-Units mm` angeben:

```powershell
.\Starten.cmd -Units mm
```

Einheiten werden nicht automatisch erkannt; die Ergebnisse erhalten die ursprünglichen Einheiten und Weltkoordinaten zurück. Ein eigener Ausgabe-Stammordner ist möglich:

```powershell
.\Starten.cmd -InputFile "C:\Scans\scan.ply" -OutputRoot "D:\Scan2Mesh-Ergebnisse"
```

Die Python-Einstiege verwenden die entsprechenden Optionen `--input`, `--units` und `--output-root`. Bei einer vorhandenen `uv`-Installation ist beispielsweise `uv run python main.py --input "C:\Scans\scan.ply"` möglich.

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

Wenn die Quelle keine RGB-Farben besitzt, heißen die PLY-Dateien stattdessen `mesh_raw.ply` und `mesh_raw_untrimmed.ply`. Zum Ansehen CloudCompare oder MeshLab verwenden und vorhandene RGB-Farben einschalten.

Der Ablauf entfernt keine Punkte, filtert keine Ausreißer, segmentiert keine Flächen und bereinigt oder vereinfacht das NKSR-Mesh nicht nachträglich. Vorhandene Normalen werden übernommen; fehlende Normalen werden mit Open3D geschätzt und konsistent ausgerichtet. Die Einzelheiten einschließlich Farbübertragung und Maskenvergleich stehen in [NKSR-Direktlauf](docs/nksr-direct.md).

Die Punktwolke wird vollständig geladen und ohne Chunking rekonstruiert. RAM und GPU-Speicher begrenzen die verarbeitbare Größe. Bei Speichermangel oder NKSR-Fehlern wird der Lauf mit einer Fehlermeldung beendet; es erfolgt kein automatischer Wechsel des Verfahrens oder der Detailstufe. Bereits geschriebene Rohdaten und Exporte bleiben erhalten. Höchste Detailstufe garantiert kein rauschfreies oder geschlossenes Mesh; Originalpunkte, feine Bauteile und echte Öffnungen weiterhin vergleichen.

Die älteren Module für Ball Pivoting, Poisson und geometrische Segmentierung bleiben als Vergleichscode im Repository; die normalen Programmstarts rufen sie nicht auf. Die automatisierten Tests prüfen unter Linux unter anderem Startweiterleitung, Setup-Verträge und den Exportvertrag mit einem nachgebildeten NKSR-Backend. Sie ersetzen keinen Test einer frischen Windows-/WSL-Installation auf der Zielhardware; diese wird beim lokalen Setup durch eine echte kleine GPU-Rekonstruktion geprüft.

NKSR-Code und vortrainierte Gewichte haben eigene Lizenzbedingungen; siehe [Nutzung und Lizenz](docs/nksr.md#nutzung-und-lizenz).
