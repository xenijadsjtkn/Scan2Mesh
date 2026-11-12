# NKSR-Direktlauf auf main

`main.py`, Play/F5, `scan2mesh process` und `nksr-direkt.ps1` starten denselben direkten NKSR-Ablauf. Dieser ist auf `main` der Standard. Die Einstellungen entsprechen der `run.json` des Referenzlaufs `nksr-direkt-20261103-102607-9a8c5ff5`.

## Fester Ablauf

1. Die Originalpunktwolke mit Open3D einlesen. Unterstützt sind PLY, PCD, PTS, XYZ, XYZN und XYZRGB. E57/RCP/RCS vorher nach PLY oder PTS exportieren.
2. Alle eingelesenen Punkte übernehmen: keine Voxelreduktion, kein Ausreißerfilter und keine Segmentierung.
3. Den Koordinatenursprung reversibel verschieben, um die Float32-Genauigkeit bei großen Weltkoordinaten zu schützen. Millimeter werden für die interne NKSR-Berechnung nach Metern umgerechnet.
4. Vorhandene Normalen unverändert übernehmen. Nur fehlende Normalen mit Open3D schätzen und konsistent ausrichten.
5. Mit dem vortrainierten Modell **`ks`** auf **`cuda:0`** und **`detail_level=1.0`** rekonstruieren.
6. Aus demselben berechneten Feld beide Meshes mit **`mise_iter=1`** extrahieren: zunächst **`trim=True`**, anschließend **`trim=False`**.
7. Jede Variante vor Farbübertragung und PLY-Export als unveränderte Roharrays sichern.
8. Bei vorhandenen RGB-Farben jedem Mesh-Eckpunkt die Farbe des nächsten Originalpunkts zuweisen. Diese Zuordnung verändert keine Meshgeometrie und verwendet keinen Abstandsschwellwert. Es handelt sich um Vertexfarben, nicht um eine Bildtextur.
9. Für die PLY-Dateien ursprüngliche Einheiten und Weltkoordinaten wiederherstellen und die Laufparameter in `run.json` speichern.

Es gibt keine nachträgliche Glättung, Meshvereinfachung, Dreiecksbereinigung oder automatische Qualitätsbewertung. Der Ablauf trainiert kein Modell. Für denselben Eingabestand sind weiterhin dieselbe NKSR-Installation, Modellgewichte und Normalen maßgeblich; identische Dreieckszahlen werden nicht zugesichert.

## Start und Ausgabe

In VS Code `main.py` öffnen und Play drücken oder die F5-Konfiguration **Scan2Mesh: NKSR direkt (Standard)** verwenden. Im Terminal reicht:

```powershell
uv run python main.py
```

Der Dateidialog öffnet sich. Alle Einstellungen oben sind bereits aktiv. Mit `--input DATEI` lässt sich der Dialog überspringen; `--units mm` deklariert Millimeterkoordinaten und `--output-root ORDNER` setzt das Ausgabe-Stammverzeichnis. Zur Wahl der vorhandenen NKSR-Installation dienen `--nksr-python` und `--nksr-wsl-distro`; siehe [Einrichtung](nksr.md).

Der bisherige PowerShell-Aufruf bleibt möglich und führt ebenfalls beide Exporte mit Detailstufe 1.0 aus:

```powershell
powershell.exe -NoProfile -STA -File .\nksr-direkt.ps1
```

`-CompareTrim` ist dafür nicht mehr erforderlich. Die Parameter `-Units`, `-OutputRoot`, `-WslDistro` und `-NksrPython` sind weiterhin für die Eingabe- und Umgebungsauswahl vorgesehen.

Die Ausgabe liegt in einem neuen `nksr-direkt-<Zeitstempel>-<Kennung>`-Ordner unter `%LOCALAPPDATA%\Scan2Mesh` beziehungsweise dem gewählten Stammverzeichnis.

| Variante | Mit RGB | Ohne RGB | Roharrays |
| --- | --- | --- | --- |
| Mit interner Maske, `trim=True` | `mesh_colored.ply` | `mesh_raw.ply` | `nksr_raw.npz` |
| Ohne interne Maske, `trim=False` | `mesh_colored_untrimmed.ply` | `mesh_raw_untrimmed.ply` | `nksr_raw_untrimmed.npz` |

`run.json` enthält `model`, `detail_level`, `mise_iter`, `compare_trim`, `input_points`, `normal_source`, Einheiten und Koordinatenursprung. Unter `exports` stehen `trim`, Dateipfade und Zählwerte jeder erfolgreich geschriebenen Variante. Die obersten Felder `mesh_path`, `raw_path`, `vertices`, `triangles` und `trim` beschreiben weiterhin den ersten, maskierten Export.

Die Roharrays speichern NKSRs interne Koordinaten sowie die Metadaten für die Rücktransformation. Die PLY-Dateien stehen bereits im ursprünglichen Koordinatensystem. Die erste PLY und ihr Bericht bleiben erhalten, falls der zweite Export fehlschlägt; bei einem Fehler vor der Farbübertragung können bereits Roharrays zur Wiederherstellung vorliegen.

## Masken, Öffnungen und Grenzen

Beim `ks`-Modell kann die interne NKSR-Maske Teile der berechneten Oberfläche entfernen. Fehlt ein Bereich nur im maskierten Mesh, hat die Exportmaske dort Fläche entfernt. `trim=False` kann aber auch zusätzliche Flächen außerhalb der Messdaten sichtbar machen. Es ist kein allgemeiner Lochfüller und garantiert kein geschlossenes Mesh. Siehe [NKSR-Meshextraktion](https://github.com/nv-tlabs/NKSR/blob/public/package/nksr/fields/base_field.py).

Bei Abschattungen fehlen tatsächliche Oberflächenmessungen. Eine dort sichtbare Ergänzung des Modells ist keine gemessene Oberfläche. Beide Meshes zusammen mit der Originalpunktwolke an Öffnungen, feinen Bauteilen und Kanten ansehen. Die [NKSR-API](https://github.com/nv-tlabs/NKSR/blob/public/package/nksr/__init__.py) weist darauf hin, dass höhere Detailstufen die Vollständigkeit verschlechtern können.

Die höchste Detailstufe benötigt mehr Grafikspeicher und kann Messrauschen stärker rekonstruieren. Die Punktwolke wird vollständig geladen und ohne Chunking verarbeitet. Bei Speichermangel wird die Detailstufe nicht automatisch reduziert. Eine funktionierende NVIDIA-/CUDA-Umgebung ist erforderlich; der Starter wechselt bei Fehlern nicht auf ein anderes Rekonstruktionsverfahren.
