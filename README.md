# Scan2Mesh

Ein Python-Prototyp für die Verarbeitung von Punktwolken aus Baustellen und Industrieanlagen: Ausreißer bereinigen, geometrische Ebenen erkennen, ein Dreiecksmesh rekonstruieren und das Ergebnis prüfen. Der erste Anwendungsfall sind bereits registrierte Ausschnitte von Hallen und Kraftwerken mit großen Flächen und feinen Strukturen wie Rohrleitungen.

Die Ebenenerkennung liefert geometrische Modelle. Sie bezeichnet Flächen noch nicht automatisch als Wand, Boden oder Bauteil. Rohr- und Objekterkennung, eine Optimierung der Scanregistrierung und CAD-Ableitung sind noch nicht enthalten.

## In VS Code starten (Windows)

1. Die aktuelle lokale Kopie des Repositorys über **Datei → Ordner öffnen** in VS Code öffnen. Im geöffneten Ordner muss `pyproject.toml` liegen.
2. Die empfohlenen Microsoft-Erweiterungen **Python** und **Python Debugger** installieren.
3. Falls `uv` noch fehlt, im integrierten Terminal installieren und VS Code danach neu starten:

   ```powershell
   winget install --id astral-sh.uv --exact
   ```

4. Vor dem ersten Start einmal **Strg+Umschalt+B** drücken. Die Standardaufgabe **Scan2Mesh: Umgebung vorbereiten** legt mit `uv sync --frozen` die Python-Umgebung an und installiert die festgelegten Abhängigkeiten. Warten, bis sie erfolgreich abgeschlossen ist.
5. **`main.py` öffnen und oben rechts auf ▶ „Python-Datei ausführen“ klicken.** Alternativ startet **F5** die Standardkonfiguration **Scan2Mesh: Eigener Scan**.
6. Im Windows-Dateiauswahldialog die Punktwolke auswählen. Anschließend beginnt die Verarbeitung automatisch. **Abbrechen** schließt die Auswahl ohne Verarbeitung.

Jeder Verarbeitungslauf schreibt in einen neuen Ergebnisordner. Unter Windows liegt dieser standardmäßig unter **`%LOCALAPPDATA%\Scan2Mesh\runs`**, beispielsweise in `vscode-scan-<Kennung>\result`. Diesen Basispfad kannst du direkt in die Adressleiste des Windows-Explorers eingeben. Falls `LOCALAPPDATA` nicht gesetzt ist, wird `%USERPROFILE%\AppData\Local\Scan2Mesh\runs` verwendet. Auf anderen Betriebssystemen liegen die Ergebnisse unter `runs` im Repository.

Der vollständige Ergebnisordner wird im integrierten Terminal ausgegeben. Dort liegen `mesh.ply`, `cleaned.ply`, `segments.ply` und `report.json`. Zum Ansehen `mesh.ply` beispielsweise in CloudCompare oder MeshLab öffnen. Die ausgewählte Quelldatei bleibt an ihrem ursprünglichen Ort, auch wenn sie in einem OneDrive-Ordner liegt.

Für einen eigenen Ergebnis-Basispfad im Terminal starten:

```powershell
uv run python main.py --output-root "D:\Scan2Mesh-Ergebnisse"
```

Auch dieser Start öffnet die Dateiauswahl und erzeugt anschließend einen neuen Ergebnisordner am gewählten Speicherort. Falls die Ausgabe abschließend nicht in den Ergebnisordner übernommen werden kann, bleiben fertig geschriebene Dateien am im Terminal genannten Wiederherstellungspfad erhalten.

Der einfache Start geht von **Koordinaten in Metern** aus, wie bei einem üblichen E57-Export. Einheiten werden nicht automatisch erkannt. Voxelgröße und Ebenentoleranz sind zunächst auf einen Zentimeter eingestellt. Für eine Punktwolke mit Millimeterkoordinaten im Terminal stattdessen starten:

```powershell
uv run python main.py --units mm
```

Auch dabei öffnet sich die Dateiauswahl; die Verarbeitungsschwellen werden an Millimeterkoordinaten angepasst. Für feine Bauteile müssen diese Ausgangswerte gegebenenfalls weiter angepasst werden. Weitere Parameter lassen sich über die folgenden Terminalbefehle steuern.

Die alternative Startkonfiguration **Scan2Mesh: Demo** erzeugt und verarbeitet eine synthetische Industrieszene. Sie lässt sich auch mit `uv run python main.py --demo` starten. Ohne Dateiauswahl ist ein Start mit `uv run python main.py --input "C:\Scans\halle.e57"` möglich.

Für die Vorschau der getrennten Flächenverarbeitung unter **Ausführen und Debuggen** die Konfiguration **Scan2Mesh: Segmentierte Rekonstruktion (Vorschau)** wählen und F5 drücken. Es öffnet sich dieselbe Dateiauswahl. Die Vorschau lässt sich auch mit `uv run python main.py --surface-mode segmented` starten. Der normale Play-Start verwendet weiterhin den globalen Modus.

## Im Terminal starten

Im Repository-Verzeichnis mit Python 3.12 und [uv](https://docs.astral.sh/uv/):

In der Cloud-Umgebung zuerst den Cache auf einen beschreibbaren Pfad legen:

```bash
export UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}"
```

```bash
uv sync --frozen
uv run scan2mesh demo --output data/demo.ply
uv run scan2mesh process data/demo.ply --output runs/demo --voxel-size 0.025 --plane-distance 0.015
uv run pytest
```

Die Demo erzeugt eine **synthetische** Industrieszene in Metern. Sie dient dem reproduzierbaren Funktionstest und ersetzt keine Validierung an einem echten Baustellenscan. Die Verarbeitung und Tests benötigen kein grafisches Fenster.

Für einen Vergleich mit Poisson-Rekonstruktion einen anderen Ausgabeordner verwenden:

```bash
uv run scan2mesh process data/demo.ply --output runs/demo-poisson --voxel-size 0.025 --plane-distance 0.015 --reconstruction poisson --poisson-depth 8
```

## Segmentierte Rekonstruktion (Vorschau)

Mit `--surface-mode segmented` werden zusammenhängende ebene Bereiche geometrisch erkannt und getrennt vermesht. Die Triangulation orientiert sich an der tatsächlich beobachteten Punktunterstützung, um insbesondere größere ungemessene Bereiche nicht pauschal zu überspannen. Restpunkte bleiben als `unknown` erkennbar und werden separat rekonstruiert. Dieser Modus verwendet kein vortrainiertes Modell und weist keine semantischen Klassen wie „Wand“, „Rohr“ oder „Maschine“ zu.

```bash
uv run scan2mesh process /pfad/zum/ausschnitt.ply --output runs/segmentiert --surface-mode segmented --voxel-size 0.01 --plane-distance 0.01
```

Punktdichte und Verarbeitungsschwellen begrenzen auch hier den Detailerhalt. Kleine Öffnungen können überbrückt werden; der Modus garantiert nicht die Erhaltung aller Löcher. Die globale Rekonstruktion bleibt der Standard (`--surface-mode global`) und dient als Vergleich. Ein Nachweis besserer Genauigkeit an einem realen Baustellenscan steht noch aus.

## Eigene Scans

Unterstützte Eingabeformate sind `.e57`, `.ply`, `.pcd`, `.xyz`, `.xyzn`, `.xyzrgb` und `.pts`. E57-Dateien werden über `pye57` gelesen; gespeicherte Scanpositionen und -orientierungen werden angewendet. Eine fehlerhafte Registrierung wird dabei nicht neu berechnet oder optimiert. ReCap-Projektdateien im Format RCP/RCS werden nicht direkt gelesen; zunächst beispielsweise E57 exportieren.

```bash
uv run scan2mesh process /pfad/zum/ausschnitt.ply --output runs/ausschnitt --voxel-size 0.01 --plane-distance 0.01
uv run scan2mesh process --help
```

Ein räumlicher Ausschnitt lässt sich mit sechs Koordinaten auswählen:

```bash
uv run scan2mesh process /pfad/zur/halle.e57 --output runs/hallenausschnitt --crop 1000 2000 0 1020 2020 15 --voxel-size 0.01 --plane-distance 0.01
```

Die Reihenfolge ist `xmin ymin zmin xmax ymax zmax`. Die Beispielgrenzen müssen an die tatsächlichen Baustellenkoordinaten angepasst werden. Es gilt das Koordinatensystem der importierten Punktwolke, bei E57 nach Anwendung der gespeicherten Scantransformationen.

Für den Anfang einen kleinen, bereits registrierten Ausschnitt wählen, der eine relevante Fläche, eine echte Öffnung und ein feines Bauteil enthält. Das Zuschneiden erfolgt vor der aufwendigen Bereinigung und Rekonstruktion. Der Import liest Punktdaten jedoch zunächst in den Arbeitsspeicher; `--crop` ist keine Verarbeitung großer Dateien in speicherbegrenzten Blöcken. Ein kompletter Kraftwerks- oder Baustellenscan ist noch kein geprüfter Anwendungsfall.

**Einheiten werden aus den Koordinaten übernommen und nicht automatisch erkannt oder umgerechnet.** Bei einer Punktwolke in Metern entsprechen `0.01` einem Zentimeter. Bei Millimeterkoordinaten müssen die Parameter entsprechend angepasst werden. Die Demo-Einstellungen sind kein allgemeines Genauigkeitsversprechen. Eine zu große Voxelgröße kann dünne Strukturen entfernen.

Die Quelldatei bleibt unverändert. Als Ausgabe einen neuen oder leeren Ordner verwenden; bestehende Ergebnisse werden nicht überschrieben.

## Ergebnisse beurteilen

| Datei | Inhalt |
| --- | --- |
| `cleaned.ply` | Bereinigte Punktwolke als Grundlage für die Rekonstruktion |
| `segments.ply` | Punktwolke mit farbig markierten Ebenen; im segmentierten Modus getrennte ebene Bereiche und unbekannte Restpunkte |
| `mesh.ply` | Rekonstruiertes Dreiecksmesh |
| `report.json` | Parameter, Punkt- und Meshanzahlen, Ebenenmodelle, Abstände und Topologiekennzahlen; im segmentierten Modus zusätzlich Segmentierungsangaben |
| `segmentation.npz` | Nur im segmentierten Modus: ganzzahlige `patch_ids` in derselben Punktreihenfolge wie `cleaned.ply` |

Im segmentierten Modus enthält `segmentation.npz` die `int32`-Zuordnungen `patch_ids`; `-1` steht für `unknown`. Sie beziehen sich auf die Punkte **nach Bereinigung und Voxelreduktion**, nicht auf die Originalpunktreihenfolge des Scans. Die IDs bezeichnen geometrische Bereiche und keine erkannten realen Objekte.

Unter `segmentation` dokumentiert `report.json` die Anzahl der Bereiche (`patch_count`), zugeordnete Ebenenpunkte (`planar_points`), unbekannte Punkte (`unknown_points`) und Angaben zu jedem Bereich. `kind` ist `geometric`; `semantic_model` und die `semantic_class` der Bereiche sind `null`. Objektklassen und Klassifikationswahrscheinlichkeiten werden nicht automatisch erzeugt. `diagnostics` nennt problematische Bereiche. Nicht verwendbare Flächenbereiche fallen auf `unknown` zurück; nicht vermeshte Randpunkte akzeptierter Bereiche werden als `unmeshed_points` ausgewiesen. Diese Punkte bei der Vollständigkeitsprüfung berücksichtigen.

Die PLY-Dateien lassen sich beispielsweise in CloudCompare oder MeshLab öffnen. Originalpunktwolke und Mesh gemeinsam ansehen, besonders an Öffnungen, Kanten, Rohren und dünnen Blechen.

Unter `quality` unterscheidet der Bericht drei Referenzen:

| Feld | Vergleich |
| --- | --- |
| `point_to_mesh` | Bereinigte Punkte → Mesh: Wie gut passt das Mesh zur verarbeiteten Punktwolke? |
| `mesh_to_cloud` | Meshoberfläche → bereinigte Punktwolke: Wo entstehen Flächen mit wenig Unterstützung durch Messpunkte? |
| `original_to_mesh` | Importierte Originalpunkte mit endlichen Koordinaten innerhalb des Ausschnitts → Mesh, vor Duplikatentfernung, Voxelreduktion und Ausreißerfilter |

Alle Abstandsangaben verwenden die Eingabeeinheiten und werden aus Stichproben berechnet. Für die Meshoberfläche werden Meshknoten, Dreiecksmittelpunkte und flächengleichverteilte Zufallspunkte kombiniert. `sample_counts` nennt die tatsächlich ausgewerteten Anzahlen. Median und 95-Prozent-Quantil helfen beim Vergleich; `max` ist das beobachtete Stichprobenmaximum und keine garantierte Schranke der größten Abweichung beziehungsweise des Hausdorff-Abstands.

Eine gute Anpassung ausschließlich an die bereinigte Wolke könnte zuvor entfernte Details verbergen. Deshalb `original_to_mesh`, entfernte Punktanzahlen und die visuelle Kontrolle zusammen betrachten. In den Originaldaten enthaltene Ausreißer können diese Abstände ebenfalls erhöhen; ein größerer Wert allein belegt keinen Rekonstruktionsfehler. Die Gegenrichtung `mesh_to_cloud` hilft, zusätzlich erzeugte Flächen zu erkennen.

Die Messungen sind Qualitätsindikatoren für diesen Ausschnitt und kein Nachweis korrekter Geometrie in nicht gescannten Bereichen. Ein glattes oder geschlossenes Mesh allein belegt keine höhere Genauigkeit.

## Umgang mit Öffnungen

Der Standard verwendet Ball Pivoting. Auch dieses Verfahren kann abhängig von Punktdichte und Radien unerwünschte Verbindungen erzeugen; offene Bereiche bleiben nicht garantiert erhalten. Poisson kann in schwach oder gar nicht gemessenen Bereichen zusätzliche Flächen erzeugen und gewünschte Öffnungen überspannen.

**Gezieltes Lochschließen und das Markieren von „offen halten“ sind noch nicht implementiert.** Entsprechend prüft der erste Vergleich, wo beide Rekonstruktionsverfahren an den vorhandenen Messdaten scheitern. Fehlende Geometrie wird noch nicht anhand einer erkannten Objektklasse ergänzt.

## Nächste Entwicklungsschritte

1. Die geometrische Aufteilung in zusammenhängende Ebenen ist als Vorschau verfügbar. Als Nächstes an einem echten Baustellenausschnitt Originalpunkte, bereinigte Punkte und beide Meshvarianten vergleichen; Anforderungen an Laufzeit, Detailerhalt und zulässige Abweichung festlegen.
2. Öffnungen gezielt auswählen, lokale Rekonstruktion und kontrolliertes Lochschließen ergänzen; große Scans in überlappende Bereiche aufteilen.
3. Zylinder und Rohrabschnitte geometrisch anpassen und gemeinsam mit Ebenen prüfen.
4. Eine visuelle Auswahl und Korrektur ergänzen. Später einen optionalen Linux-/GPU-Adapter für passende Punktwolkenmodelle wie Mask3D oder Pointcept prüfen. Solche Modelle verarbeiten 3D-Punkte und gegebenenfalls Punktfarben; Kamerabilder sind dafür keine generelle Voraussetzung. Passende Klassen und Modellgewichte für Industrieanlagen müssen separat bewertet werden.

Originalpunkte, Einheiten und geometrische Modelle bleiben dabei die Grundlage für eine spätere CAD-Ableitung.
