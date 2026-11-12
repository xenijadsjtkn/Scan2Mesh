# NKSR-Umgebung einrichten

Scan2Mesh startet den direkten NKSR-Lauf in einer **bereits eingerichteten Linux-Python-Umgebung mit PyTorch und CUDA**. Unter Windows läuft diese Umgebung in WSL2; Dateiauswahl und VS Code können unter Windows bleiben. Die normale Scan2Mesh-Umgebung wird weiterhin separat mit `uv` vorbereitet.

Wer bereits den Referenzlauf erfolgreich ausgeführt hat, kann dieselbe NKSR-Installation weiterverwenden. Der Standardstart installiert oder verändert dort keine Pakete. [Start und Ausgaben](nksr-direct.md) beschreiben den jetzt auf `main` gemeinsamen Ablauf.

## Vorhandene Installation auswählen

Unter Windows zeigt dieser Befehl die eingerichteten WSL-Distributionen:

```powershell
wsl.exe --list --quiet
```

Ohne weitere Einstellung verwendet Scan2Mesh **Ubuntu-22.04**. Der Starter sucht dort nach einer vorhandenen `nksr`-Umgebung unter üblichen Conda-/Mamba-Pfaden im Linux-Benutzerprofil sowie beim aufgerufenen Interpreter. Er verwendet genau einen Kandidaten, der `torch` und `nksr` importieren kann. Bei mehreren passenden Umgebungen muss der gewünschte Interpreter ausdrücklich gewählt werden.

Für einen einmaligen Start im PowerShell-Terminal des Projekts die tatsächlichen Werte einsetzen:

```powershell
uv run python main.py --nksr-wsl-distro Ubuntu-22.04 --nksr-python /home/DEIN_LINUXNAME/miniforge3/envs/nksr/bin/python
```

Der Interpreterpfad muss auf eine einzelne ausführbare **Linux-Python-Datei** zeigen. Befehle wie `conda run ...` oder `wsl ...` gehören nicht in `--nksr-python`.

Für eine dauerhafte Auswahl auf Benutzerebene beide Beispielwerte ersetzen:

```powershell
[Environment]::SetEnvironmentVariable('SCAN2MESH_NKSR_WSL_DISTRO', 'Ubuntu-22.04', 'User')
[Environment]::SetEnvironmentVariable('SCAN2MESH_NKSR_PYTHON', '/home/DEIN_LINUXNAME/miniforge3/envs/nksr/bin/python', 'User')
```

Anschließend **VS Code vollständig schließen und neu öffnen**, damit Play/F5 die Variablen erhalten. Nur im integrierten Terminal mit `$env:…` gesetzte Variablen stehen einem bereits laufenden VS-Code-Prozess nicht automatisch zur Verfügung. Ausdrückliche Kommandozeilenoptionen haben Vorrang vor den Umgebungsvariablen.

Unter Linux ohne WSL den vorhandenen Interpreter direkt wählen:

```bash
uv run python main.py --input scan.ply --nksr-python /vollstaendiger/pfad/zur/nksr-umgebung/bin/python
```

## Neue NKSR-Umgebung aufbauen

Die folgenden Einrichtungsschritte laufen **innerhalb von Linux beziehungsweise WSL**. Sie entsprechen dem bislang dokumentierten Build mit x86-64 Linux, Python 3.10, PyTorch 2.7.0 und CUDA 12.8. Eine Installation auf der jeweiligen Nutzerhardware muss separat geprüft werden. Siehe [offizielle Umgebung](https://github.com/nv-tlabs/NKSR/blob/public/environment.yml) und [Build-Konfiguration](https://github.com/nv-tlabs/NKSR/blob/public/package/setup.py).

Benötigt werden eine NVIDIA-GPU mit passendem Treiber, Conda oder Micromamba, Git, ein C++-Compiler und das CUDA-Buildwerkzeug `nvcc`. Das Linux-Arbeitsverzeichnis für den Build außerhalb synchronisierter Windows-/OneDrive-Ordner anlegen. Zuerst prüfen, ob WSL beziehungsweise Linux die GPU sieht:

```bash
nvidia-smi
```

Dann das offizielle Projekt und seine separate Umgebung einrichten:

```bash
git clone --branch public https://github.com/nv-tlabs/NKSR.git
cd NKSR
conda env create -f environment.yml
conda activate nksr
nvcc --version
```

Bei Micromamba die beiden `conda`-Befehle durch die entsprechenden `micromamba`-Befehle ersetzen. Ein aktueller Grafiktreiber allein stellt `nvcc` nicht bereit; das Toolkit kommt in diesem Beispiel aus der Upstream-Umgebung.

Die bisher dokumentierte [requirements.txt](https://github.com/nv-tlabs/NKSR/blob/public/requirements.txt) kombiniert PyTorch 2.7.0 mit einem Wheelindex für `torch-scatter` 2.8.0. Für diesen Build wird in einer **lokalen Kopie** der Requirements der passende [2.7.0/CUDA-12.8-Index](https://data.pyg.org/whl/torch-2.7.0+cu128.html) verwendet:

```bash
python -c "from pathlib import Path; p=Path('requirements.txt'); Path('requirements-scan2mesh.txt').write_text(p.read_text().replace('torch-2.8.0+cu128.html', 'torch-2.7.0+cu128.html'))"
python -m pip install -r requirements-scan2mesh.txt
python -m pip install omegaconf tqdm "open3d==0.19.0"
python -m pip install --no-build-isolation ./package
```

Der letzte Schritt kompiliert native Erweiterungen und lädt externe Buildquellen. Falls `CUDA_HOME` fehlt, zuerst `nvcc` und die aktive Conda-Umgebung prüfen. Bei anderen PyTorch-/CUDA-Versionen müssen auch die nativen Erweiterungen passend gebaut sein.

NKSR importiert über `python-pycg` auch Open3D. Die normale Open3D-Version wird vom [PyCG-Importpfad](https://github.com/heiwang1997/pycg/blob/master/pycg/o3d.py) unterstützt; ein Hinweis auf einen fehlenden benutzerdefinierten Open3D-Build kann dabei als Warnung erscheinen. Für Ubuntu 22.04 lassen sich die Laufzeitbibliotheken so ergänzen:

```bash
sudo apt install -y libgl1 libgomp1
```

Bei einer bestehenden Installation mit `ModuleNotFoundError: No module named 'open3d'` Open3D in der aktivierten NKSR-Umgebung nachinstallieren:

```bash
python -m pip install "open3d==0.19.0"
```

Der bestehende NKSR-Build kann dabei weiterverwendet werden. Scan2Mesh selbst muss nicht in dieser Python-3.10-Umgebung installiert werden; der Starter führt den Worker aus dem lokalen Repository aus. Der Direktlauf nutzt zusätzlich NumPy und SciPy zur Daten- und Farbübertragung; diese müssen in der NKSR-Umgebung importierbar sein.

## Installation prüfen

Innerhalb der aktivierten NKSR-Umgebung:

```bash
python -c "import sys, torch, nksr, open3d, numpy, scipy; print(sys.executable); print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'Keine CUDA-GPU')"
git rev-parse HEAD
```

Den ausgegebenen Python-Pfad für die Scan2Mesh-Konfiguration verwenden und die NKSR-Revision für reproduzierbare Vergleiche notieren. Der Importcheck lädt keine Modellgewichte und ersetzt keinen vollständigen Rekonstruktionstest. Der erste Rekonstruktionslauf kann den offiziellen vortrainierten `ks`-Checkpoint herunterladen; die [Modellkonfiguration](https://github.com/nv-tlabs/NKSR/blob/public/package/nksr/configs.py) nennt dessen Adresse.

Die Rekonstruktion verwendet **`cuda:0`**, die erste für PyTorch sichtbare CUDA-GPU. Der Speicherbedarf hängt von Punktzahl, Auflösung und Geometrie ab. Bei fehlendem CUDA, Importfehlern oder Speichermangel meldet Scan2Mesh den Fehler und erhält bereits geschriebene Ergebnisse. Es gibt keinen automatischen CPU-Modus, Mesherwechsel oder Detailverlust durch eine automatische Reduktion.

## Nutzung und Lizenz

Nach Abschnitt 3.3 der [NKSR-Code-Lizenz](https://github.com/nv-tlabs/NKSR/blob/public/LICENSE.txt) ist die Nutzung auf nichtkommerzielle Forschung und Evaluation beschränkt. Die [Projektbeschreibung](https://github.com/nv-tlabs/NKSR#testing-nksr-on-your-own-data) nennt für die „kitchen-sink“-Gewichte separat CC-BY-SA 4.0. Beide Bedingungen gelten auch beim Aufruf durch Scan2Mesh.

NKSR verarbeitet die Scanpunkte lokal im gewählten Linux-/WSL-Prozess. Die Auswahl von NKSR erzeugt keine automatische semantische Klassifikation von Rohren, Wänden oder Maschinen. Eine höhere Auflösung oder ein geschlossen wirkendes Mesh ersetzt die Kontrolle gegen die Messpunkte nicht.
