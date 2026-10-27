# NKSR als experimentellen Mesher einrichten

Scan2Mesh kann [Neural Kernel Surface Reconstruction (NKSR)](https://github.com/nv-tlabs/NKSR) in einem eigenen Prozess ausführen. Das Hauptprogramm übernimmt Import, Ausschnitt, Bereinigung, Normalen und Qualitätsbericht. Der zusätzliche Prozess erhält die vorbereiteten Punkte und Normalen und liefert das rekonstruierte Mesh zurück. Seine CUDA-/PyTorch-Pakete werden separat installiert.

Die Einbindung ist für einen ersten Vergleich an kleinen, bereits registrierten Ausschnitten gedacht. Sie erzeugt ein Mesh; semantische Bauteilklassen oder Instanzen gehören nicht zu diesem Modell. Ein Qualitätsgewinn an echten Hallen- oder Kraftwerksscans ist noch nicht nachgewiesen.

## Nutzung und Lizenz

Nach Abschnitt 3.3 der [NKSR-Code-Lizenz](https://github.com/nv-tlabs/NKSR/blob/public/LICENSE.txt) ist die Nutzung auf nichtkommerzielle Forschung und Evaluation beschränkt. Die [Projektbeschreibung](https://github.com/nv-tlabs/NKSR#testing-nksr-on-your-own-data) nennt für die „kitchen-sink“-Gewichte separat CC-BY-SA 4.0. Beide Bedingungen gelten auch dann, wenn Scan2Mesh den Code in einem eigenen Prozess aufruft. Für einen späteren kommerziellen Einsatz muss eine passende Berechtigung oder ein anderes Verfahren vorliegen.

Die reine Hardwareprüfung lädt kein Modell. Erst ein ausdrücklich gestarteter NKSR-Rekonstruktionslauf erzeugt einen `Reconstructor` und kann dessen offiziellen `ks`-Checkpoint von Hugging Face laden. Die [Modellkonfiguration](https://github.com/nv-tlabs/NKSR/blob/public/package/nksr/configs.py) nennt die Downloadadresse. Scan2Mesh überträgt die Punktdaten über lokale Prozess-Pipes; es lädt keine Scans zu einem Dienst hoch.

## Voraussetzungen

Der dokumentierte NKSR-Build verwendet x86-64 Linux, Python 3.10, PyTorch 2.7.0 und CUDA 12.8. Benötigt werden ein geeigneter NVIDIA-Treiber, ein funktionierender C++-Compiler, Git und das CUDA-Buildwerkzeug `nvcc`. Unter Windows läuft dieser Prozess in WSL2 mit einer eingerichteten Linux-Distribution. Der vorhandene Scan2Mesh-Start und die Dateiauswahl können auf Windows bleiben. Siehe [offizielle Umgebung](https://github.com/nv-tlabs/NKSR/blob/public/environment.yml) und [Build-Konfiguration](https://github.com/nv-tlabs/NKSR/blob/public/package/setup.py).

Die Einbindung verwendet die erste für PyTorch sichtbare CUDA-Karte (`cuda:0`). Eine pauschale Mindestgröße des Grafikspeichers lässt sich daraus nicht ableiten: Auflösung, Punktzahl und Geometrie bestimmen den Bedarf. Die Diagnose zeigt das tatsächlich erkannte Modell und den verfügbaren Gesamtspeicher an. Ein CPU-Modus existiert im [NKSR-Projekt](https://github.com/nv-tlabs/NKSR/blob/public/NKSR-USAGE.md#running-on-a-device-with-small-memory); dieser Adapter verwendet zunächst den CUDA-Weg.

## Separate NKSR-Umgebung aufbauen

Die folgenden Befehle sind **manuelle Einrichtungsschritte innerhalb von Linux beziehungsweise WSL**. Sie wurden hier anhand des aktuellen Upstream-Builds zusammengestellt; ein CUDA-Build auf der Nutzerhardware steht noch aus. Installiere zunächst Conda oder Micromamba und die nativen Buildwerkzeuge nach den Anleitungen deiner Distribution. Verwende ein Linux-Arbeitsverzeichnis außerhalb synchronisierter Windows-/OneDrive-Ordner. Die Scan2Mesh-Python-Umgebung wird für diesen Schritt nicht aktiviert oder verändert.

Zuerst prüfen, ob WSL beziehungsweise Linux die Karte sieht:

```bash
nvidia-smi
```

Dann das offizielle Projekt laden und seine separate Umgebung erzeugen:

```bash
git clone --branch public https://github.com/nv-tlabs/NKSR.git
cd NKSR
conda env create -f environment.yml
conda activate nksr
nvcc --version
```

Bei Micromamba die beiden `conda`-Befehle durch die entsprechenden `micromamba`-Befehle ersetzen. Ein aktueller Treiber allein stellt `nvcc` nicht bereit; das Toolkit kommt in diesem Beispiel aus der Upstream-Umgebung.

Die aktuell veröffentlichte [requirements.txt](https://github.com/nv-tlabs/NKSR/blob/public/requirements.txt) kombiniert PyTorch 2.7.0 mit einem Wheelindex für `torch-scatter` 2.8.0. Für diese Installation wird nur in einer lokalen Kopie der Requirements der zu PyTorch passende [offizielle 2.7.0/CUDA-12.8-Index](https://data.pyg.org/whl/torch-2.7.0+cu128.html) verwendet:

```bash
python -c "from pathlib import Path; p=Path('requirements.txt'); Path('requirements-scan2mesh.txt').write_text(p.read_text().replace('torch-2.8.0+cu128.html', 'torch-2.7.0+cu128.html'))"
python -m pip install -r requirements-scan2mesh.txt
python -m pip install omegaconf tqdm "open3d==0.19.0"
python -m pip install --no-build-isolation ./package
```

Der letzte Schritt kompiliert native Erweiterungen und lädt die im Build angegebenen externen Quellen. Er kann einige Zeit benötigen. Falls `CUDA_HOME` fehlt, zuerst `nvcc` und die aktive Conda-Umgebung prüfen; den Pfad nicht auf eine beliebige CUDA-Version setzen. Bei unterschiedlichen PyTorch-/CUDA-Versionen müssen auch die Erweiterungen passend gebaut sein.

NKSR importiert über `python-pycg` auch Open3D. Deshalb gehört Open3D zusätzlich in diese separate Umgebung. Die normale Open3D-Version wird vom [PyCG-Importpfad](https://github.com/heiwang1997/pycg/blob/master/pycg/o3d.py) unterstützt; der Hinweis auf einen fehlenden benutzerdefinierten Open3D-Build kann dabei als Warnung erscheinen. Für Ubuntu 22.04 können die Laufzeitbibliotheken so ergänzt werden:

```bash
sudo apt install -y libgl1 libgomp1
```

Falls NKSR bereits gebaut wurde und beim Import `ModuleNotFoundError: No module named 'open3d'` erscheint, reicht das Nachinstallieren von `open3d==0.19.0` mit `python -m pip install "open3d==0.19.0"` in der aktivierten `nksr`-Umgebung. Der bestehende NKSR-Build kann weiterverwendet werden.

Nach erfolgreichem Build den absoluten Pfad dieses Python-Interpreters ausgeben lassen:

```bash
python -c "import sys; print(sys.executable)"
git rev-parse HEAD
```

Den Python-Pfad für die folgenden Aufrufe verwenden und die NKSR-Revision für einen reproduzierbaren Vergleich notieren. Es ist nicht nötig, Scan2Mesh selbst in dieser Python-3.10-Umgebung zu installieren.

## Hardware und Installation prüfen

### Windows mit WSL

Im Windows-Terminal lässt sich der Name der eingerichteten Distribution anzeigen:

```powershell
wsl.exe --list --quiet
```

Im PowerShell-Terminal des Scan2Mesh-Projekts die beiden Beispielwerte durch die tatsächliche Distribution und den zuvor ausgegebenen Linux-Python-Pfad ersetzen:

```powershell
$env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA "Scan2Mesh\venv"
$env:UV_CACHE_DIR = Join-Path $env:LOCALAPPDATA "Scan2Mesh\cache\uv"
$env:SCAN2MESH_NKSR_WSL_DISTRO = "Ubuntu"
$env:SCAN2MESH_NKSR_PYTHON = "/vollstaendiger/linux/pfad/zur/nksr-umgebung/bin/python"
uv run python main.py --check-neural
```

`--check-neural` öffnet keine Dateiauswahl und erzeugt keinen Verarbeitungslauf. Alternativ ist `uv run scan2mesh neural-check` verfügbar. Die Prüfung meldet, ob PyTorch, NKSR und CUDA verwendbar sind, und zeigt die GPU-Angaben. `ready: false` und die zugehörigen Fehler bedeuten, dass zuerst die genannte Voraussetzung korrigiert werden muss. Ein erfolgreicher Check lädt weder Gewichte noch prüft er schon die vollständige Rekonstruktion.

In VS Code gibt es dafür unter **Ausführen und Debuggen** die Konfiguration **Scan2Mesh: NKSR pruefen**. Nach erfolgreicher Einrichtung startet **Scan2Mesh: NKSR (Experiment)** den Versuch mit Dateiauswahl. Wenn die Variablen im Terminal gesetzt wurden, müssen sie auch in der Umgebung des gestarteten VS-Code-Prozesses verfügbar sein; alternativ die Interpreter- und Distributionsoptionen im Terminal ausdrücklich mitgeben.

### Linux

Im normalen Scan2Mesh-Projektterminal:

```bash
uv run scan2mesh neural-check --nksr-python /vollstaendiger/pfad/zur/nksr-umgebung/bin/python
```

Der Interpreter ist eine einzelne ausführbare Datei. Ein Befehl wie `conda run ...` oder `wsl ...` gehört nicht in `--nksr-python`. WSL wird über `--nksr-wsl-distro` gewählt. Ohne expliziten Interpreter nutzt Scan2Mesh `SCAN2MESH_NKSR_PYTHON`, ansonsten den aktuellen Interpreter; bei gewählter WSL-Distribution ist der letzte Fallback `python3` innerhalb dieser Distribution. Für eine eigene Conda-Umgebung deshalb den vollständigen Pfad setzen. Die Optionen überschreiben die entsprechenden Umgebungsvariablen.

## Einen echten Ausschnitt rekonstruieren

Nach erfolgreicher Einrichtung öffnet dieser Windows-Aufruf die gewohnte Dateiauswahl und verarbeitet den ausgewählten Scan mit NKSR:

```powershell
uv run python main.py --reconstruction nksr
```

Die zuvor gesetzten Umgebungsvariablen wählen den WSL-Prozess. Die Datei muss dafür nicht manuell nach WSL kopiert werden: Import und Ausgabe bleiben beim Hauptprogramm, Punkte und Mesh werden über Prozess-Pipes ausgetauscht. Beim NKSR-Desktopstart ist die Voxelreduktion zunächst ausgeschaltet, damit sie dünne Bauteile vor dem Modell nicht entfernt. `--voxel-size` überschreibt diese Einstellung; `--normal-radius` und `--crop` stehen auch beim Desktopstart zur Verfügung. Kleine Ausschnitte begrenzen den Speicherbedarf.

Für einen kontrollierten kleinen Ausschnitt bietet die CLI die vollständigen Vorverarbeitungsparameter. Beispiel für Meterkoordinaten:

```bash
uv run scan2mesh process /pfad/zum/ausschnitt.e57 --output runs/nksr-versuch --reconstruction nksr --nksr-python /pfad/zur/nksr-umgebung/bin/python --units m --voxel-size 0 --nksr-detail-level 0
```

Für einen Ausschnitt mit Millimeterkoordinaten die Einheit ausdrücklich wählen und beispielsweise die Ebenentoleranz auf 10 Millimeter setzen:

```bash
uv run scan2mesh process /pfad/zum/ausschnitt-mm.e57 --output runs/nksr-mm-versuch --reconstruction nksr --nksr-python /pfad/zur/nksr-umgebung/bin/python --units mm --voxel-size 0 --plane-distance 10 --nksr-detail-level 0
```

Unter Windows stattdessen einen Windows-Dateipfad angeben und den WSL-Interpreter wie oben konfigurieren. `--voxel-size 0` lässt die Voxelreduktion der Eingangspunkte aus; das erhöht den Speicherbedarf und eignet sich deshalb zunächst nur für einen kleinen Ausschnitt. Ausreißerfilter und Normalenschätzung bleiben aktiv. Der neue Ergebnisordner enthält wie bisher `mesh.ply`, `cleaned.ply`, `segments.ply` und `report.json`. Der Bericht enthält unter `neural_reconstruction` die verwendeten Versionen, GPU-Angaben und NKSR-Parameter sowie die Einheitenumrechnung (`input_units`, `backend_units`, `input_units_to_meters`, `requested_voxel_size`). Die farbigen Ebenen sind weiterhin geometrische Hinweise, keine vom Netz erkannten Objektklassen.

NKSR wird zunächst nur mit `--surface-mode global` unterstützt. Die Verbindung mit `--surface-mode segmented` wird zurückgewiesen. Bei einem NKSR-Fehler wird kein anderes Verfahren als Ersatz ausgewählt.

## Rauschen, Details und Speicher steuern

| Option | Wirkung |
| --- | --- |
| `--units` | `m` oder `mm`, Standard `m`. Deklariert die Koordinateneinheit für die NKSR-interne Umrechnung; sie wird nicht automatisch erkannt. |
| `--nksr-detail-level` | Wert von 0 bis 1, Standard 0. Höhere Werte können feinere Strukturen, aber auch stärkeres Messrauschen und höheren Speicherbedarf erzeugen. |
| `--nksr-voxel-size` | Positive Rekonstruktionsskala in Eingabeeinheiten. Überschreibt die automatische Skalenwahl über `detail-level`; grob passend zur lokalen Rauschgröße wählen. |
| `--voxel-size` | Davon unabhängig: Vorverarbeitung der Punktwolke. Zu große Werte können feine Bauteile schon vor NKSR entfernen. |
| `--normal-radius` | Nachbarschaft für die vorhandene Normalenschätzung, in Eingabeeinheiten. Kanten, dünne Rohre und nahe Flächen benötigen besondere Kontrolle. |
| `--nksr-timeout` | Zeitgrenze für den Rekonstruktionsprozess in Sekunden, Standard 1800. Gewichte-Download und Initialisierung zählen dazu. |

Alle Längenoptionen bleiben in den **Eingabeeinheiten**, auch `--voxel-size`, `--plane-distance`, `--normal-radius`, `--crop` und `--nksr-voxel-size`. Die CLI rechnet diese Nutzerwerte nicht pauschal um. Bei `--units mm` bedeutet etwa `--nksr-voxel-size 3` eine Rekonstruktionsskala von 3 Millimetern. Nur die lokalen NKSR-Punktkoordinaten und die angeforderte NKSR-Skala werden vor dem Worker nach Metern normalisiert. Das zurückgegebene Mesh wird wieder in die ursprünglichen Einheiten und Koordinaten transformiert; auch die Abstände im Qualitätsbericht bleiben in Eingabeeinheiten. Damit ist die automatische NKSR-Skalenwahl bei Meter- und Millimeterdarstellung vergleichbar. Der Worker protokolliert seine `voxel_size` in Metern, `requested_voxel_size` dokumentiert den angeforderten Wert in Eingabeeinheiten.

Die Rausch-/Detailwirkung der NKSR-Optionen beschreibt die [offizielle Verwendung](https://github.com/nv-tlabs/NKSR/blob/public/NKSR-USAGE.md#dealing-with-noise). Es gibt keine allgemeingültige Einstellung für alle Hallenflächen und Rohrdurchmesser. Eine sehr feine Skala kann das Messrauschen statt der Oberfläche rekonstruieren.

Bei CUDA-Speicherfehlern zuerst einen kleineren Ausschnitt wählen oder die Punktzahl kontrolliert reduzieren. Der Adapter verwendet zunächst kein Chunking und wechselt bei Speicherproblemen nicht automatisch auf CPU. Das bloße Erhöhen des Timeouts löst einen Speichermangel nicht. Große Projektdateien werden im Hauptprogramm weiterhin zunächst vollständig in den Arbeitsspeicher eingelesen.

## Ergebnis beurteilen

Den identischen Ausschnitt zusätzlich mit Ball Pivoting und Poisson verarbeiten und jeweils einen neuen Ausgabeordner verwenden. Vorverarbeitung und Referenzpunkte für den Vergleich gleich halten. Relevante Stellen sind eine echte Öffnung, ein dünnes Rohr, zwei nahe Flächen sowie eine scharfe Kante.

Im Bericht sowohl Punkte-zu-Mesh als auch Mesh-zu-Punktwolke prüfen. Zusätzlich Rohrdurchmesser, Öffnungen und Anschlüsse visuell beziehungsweise mit lokalen Messungen kontrollieren. Eine glatte oder geschlossene Oberfläche allein belegt keine höhere Genauigkeit. Die erste Einbindung verwendet die bisherigen orientierten Normalen; die erhaltene E57-Scannerpose wird noch nicht pro Punkt an NKSR weitergegeben. Fehlerhafte Normalen oder Registrierung können deshalb auch das neuronale Ergebnis beeinträchtigen.
