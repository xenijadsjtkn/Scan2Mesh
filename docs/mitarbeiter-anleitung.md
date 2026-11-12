# Scan2Mesh auf einem neuen Windows-Rechner einrichten und mit VS Code benutzen

Diese Anleitung richtet sich an einen Mitarbeiter, der bereits **Visual Studio Code** besitzt und Scan2Mesh zum ersten Mal einrichtet. Python, Git und Ubuntu müssen vorher nicht installiert sein.

Du brauchst einen Windows-Rechner mit geeigneter NVIDIA-Grafikkarte, funktionierendem NVIDIA-Windows-Treiber, Internetzugang und Administratorrechten für die einmalige WSL-Einrichtung. Für den späteren normalen Start sind keine Administratorrechte erforderlich.

Die Einrichtung ist für Intel-/AMD-Rechner mit 64-Bit-Windows vorgesehen. WSL unterstützt die verwendeten Installationsbefehle unter Windows 11 sowie Windows 10 ab Version 2004, Build 19041. Die [Microsoft-Anleitung zu WSL](https://learn.microsoft.com/en-us/windows/wsl/install) beschreibt die Voraussetzungen und den möglichen Neustart.

**Verwendeter Branch für diese Anleitung: `codex/windows-setup`.** Die Anleitung und die Einrichtungsdateien werden in diesem Branch bereitgestellt. Für diesen Ablauf bleibst du bei dieser Version.

Der Ablauf ist: **Projekt herunterladen → in VS Code öffnen → einmal einrichten → Windows-Python auswählen → mit F5 oder Play starten → Ergebnisse öffnen.**

> Die Einrichtungs- und Startskripte wurden automatisiert geprüft. Eine vollständige Neuinstallation auf einem echten Windows-/GPU-Rechner wurde in der Entwicklungsumgebung noch nicht durchgeführt. Deshalb führt die Einrichtung auf deinem Rechner abschließend eine kleine echte NKSR-Rekonstruktion durch und meldet erst danach Erfolg. Die erste Einrichtung benötigt größere Downloads und kompiliert native Erweiterungen; sie kann deutlich länger dauern als ein späterer Programmstart.

## 1. Projekt von GitHub herunterladen

1. Öffne den Browser und melde dich gegebenenfalls bei GitHub an.
2. Öffne diesen Branch:

   **[Scan2Mesh – codex/windows-setup](https://github.com/xenijadsjtkn/Scan2Mesh/tree/codex/windows-setup)**

3. Falls GitHub „404“ oder eine Zugriffsfehlermeldung zeigt, lass dir vom Besitzer Zugriff auf das Repository geben. Bei einem privaten Repository muss dein GitHub-Konto berechtigt sein.
4. Prüfe in der Branch-Auswahl oberhalb der Dateiliste, dass **`codex/windows-setup`** ausgewählt ist.
5. Klicke auf den grünen Button **Code**.
6. Klicke auf **Download ZIP**.
7. Warte, bis der Download abgeschlossen ist.

Alternativ kannst du die ZIP direkt herunterladen:

**[ZIP des Setup-Branches herunterladen](https://github.com/xenijadsjtkn/Scan2Mesh/archive/refs/heads/codex/windows-setup.zip)**

Für diesen Downloadweg ist keine Git-Installation erforderlich.

## 2. ZIP vollständig in einen lokalen Ordner entpacken

1. Öffne im Windows-Explorer den Downloadordner.
2. Klicke mit der rechten Maustaste auf die heruntergeladene ZIP-Datei.
3. Wähle **Alle extrahieren …**.
4. Wähle einen beschreibbaren lokalen Zielordner. Ein Ordner außerhalb von OneDrive ist für das Projekt praktisch.

   Du kannst zum Beispiel mit **Windows-Taste + R** diesen Ort öffnen:

   ```text
   %LOCALAPPDATA%
   ```

   Lege dort einen Ordner **`Scan2Mesh-Projekt`** an und verwende ihn als Ziel für das Entpacken. Der Quellcode liegt damit getrennt von den späteren Installations- und Ergebnisdateien unter `%LOCALAPPDATA%\Scan2Mesh`.

5. Klicke auf **Extrahieren**.
6. Öffne den entpackten Inhalt. Je nach Entpackziel kann darin noch ein zusätzlicher Projektordner liegen.
7. Suche den Ordner, in dem diese Dateien und Unterordner **direkt nebeneinander** liegen:

   ```text
   main.py
   pyproject.toml
   Einrichten.cmd
   Starten.cmd
   README.md
   scripts
   src
   setup
   .vscode
   ```

   Diesen Ordner nenne ich in den nächsten Schritten **Projektordner**.

8. Falls Windows die Dateiendungen versteckt, können die Dateien nur als **Einrichten** und **Starten** angezeigt werden. Im Explorer kannst du über **Ansicht → Anzeigen → Dateinamenerweiterungen** die Endungen einblenden; bei Windows 10 befindet sich die Option im Register **Ansicht**.

**Starte die Dateien aus dem vollständig entpackten Projektordner.** Wenn du noch innerhalb der ZIP-Datei navigierst, zuerst zum entpackten Ordner wechseln.

## 3. Den richtigen Ordner in VS Code öffnen

1. Starte VS Code als normaler Windows-Benutzer.
2. Klicke auf **Datei → Ordner öffnen …** beziehungsweise **File → Open Folder …**.
3. Wähle den Projektordner aus Schritt 2 aus.
4. Bestätige mit **Ordner auswählen**.
5. Falls VS Code nach dem Vertrauen in den Arbeitsbereich fragt, gib den vom Team bereitgestellten Projektordner frei, damit Aufgaben und Debugger dort ausgeführt werden können.
6. Prüfe links im Explorer von VS Code, dass du `main.py`, `pyproject.toml`, `Einrichten.cmd` und `Starten.cmd` sehen kannst.

Wenn du links nur einen einzelnen Unterordner mit diesen Dateien siehst, öffne diesen Unterordner stattdessen über **Datei → Ordner öffnen …**. Die mitgelieferten VS-Code-Konfigurationen erwarten den eigentlichen Projektordner.

Der Projektordner wird für diese Anleitung in der normalen Windows-Ausgabe von VS Code geöffnet. Den Linux-/WSL-Prozess startet Scan2Mesh später selbst.

## 4. Die beiden Python-Erweiterungen installieren

VS Code und seine Python-Erweiterungen sind getrennte Installationen. Prüfe daher die Erweiterungen auch dann, wenn VS Code bereits vorhanden ist.

1. Drücke **Strg + Umschalt + X**. Links öffnet sich die Erweiterungsansicht.
2. Suche nach **Python**.
3. Installiere **Python** vom Herausgeber **Microsoft**. Die Erweiterungs-ID lautet `ms-python.python`.
4. Suche anschließend nach **Python Debugger**.
5. Installiere **Python Debugger** von **Microsoft**, ID `ms-python.debugpy`, falls die Erweiterung nicht bereits mitinstalliert wurde.
6. Falls VS Code einen Neustart oder **Fenster neu laden / Reload Window** anbietet, führe das aus.

Ein Hinweis auf noch fehlendes Python ist an dieser Stelle möglich: Die eigentliche Windows-Python-Umgebung wird erst im nächsten Abschnitt automatisch eingerichtet.

## 5. Das PowerShell-Terminal im Projektordner öffnen

1. Klicke in VS Code oben auf **Terminal → Neues Terminal** beziehungsweise **Terminal → New Terminal**.
2. Prüfe, dass das Terminal **PowerShell** verwendet. Über den kleinen Pfeil neben dem Pluszeichen im Terminalbereich lässt sich ein neues PowerShell-Terminal auswählen.
3. Prüfe mit diesem Befehl den aktuellen Ordner:

   ```powershell
   Get-Location
   ```

4. Prüfe danach, dass die benötigten Dateien dort liegen:

   ```powershell
   Get-ChildItem main.py, pyproject.toml, Einrichten.cmd, Starten.cmd
   ```

   Es sollten alle vier Dateien angezeigt werden.

Wenn die Dateien nicht gefunden werden, korrigiere zuerst den geöffneten Projektordner aus Schritt 3 und öffne anschließend ein neues Terminal.

In den folgenden Codeblöcken stehen nur die einzugebenden Befehle. Eine bereits im Terminal sichtbare Eingabeaufforderung wie `PS C:\...>` wird nicht mitkopiert.

## 6. Die einmalige Einrichtung starten

1. Gib im PowerShell-Terminal folgenden Befehl ein und drücke **Enter**:

   ```powershell
   .\Einrichten.cmd
   ```

   Der Präfix `.\` bedeutet, dass die Datei im aktuellen Ordner gestartet wird. Das ist in PowerShell erforderlich.

2. Wenn Windows eine Administratorabfrage zur Aktivierung von WSL anzeigt, bestätige sie beziehungsweise gib die erlaubten Administratorzugangsdaten ein.
3. Lass das Setup-Fenster geöffnet und beachte die dortigen Meldungen.

Du kannst `Einrichten.cmd` alternativ im Windows-Explorer doppelklicken. Für den ersten Aufbau ist der Start im VS-Code-Terminal hilfreich, weil die Meldungen dort gut nachlesbar bleiben.

### 6.1 Falls ein Windows-Neustart verlangt wird

Das Setup kann zuerst diese Meldung ausgeben:

```text
WSL wurde vorbereitet. Windows jetzt selbst neu starten und danach Einrichten.cmd erneut oeffnen.
```

Dann:

1. Speichere gegebenenfalls offene Arbeit.
2. Starte Windows über **Start → Ein/Aus → Neu starten** neu.
3. Öffne danach VS Code erneut.
4. Öffne denselben Projektordner wie zuvor.
5. Öffne erneut **Terminal → Neues Terminal → PowerShell**.
6. Starte die Einrichtung wieder:

   ```powershell
   .\Einrichten.cmd
   ```

Der Neustart allein führt die restliche Einrichtung noch nicht aus. Der zweite Aufruf ist erforderlich. Das Setup löst keinen automatischen Windows-Neustart aus.

### 6.2 Was die Einrichtung anschließend erledigt

Auf einem neuen Rechner richtet das Setup folgende Bestandteile ein:

1. Das Werkzeug `uv` und die externe Windows-Python-Umgebung für Scan2Mesh.
2. Die festgelegten Windows-Projektabhängigkeiten.
3. Eine eigene WSL2-Distribution namens **`Scan2Mesh-NKSR`** mit Ubuntu 22.04.
4. Darin die separate Python-/CUDA-/PyTorch-Umgebung für NKSR.
5. Die NKSR-Erweiterungen, die auf dem Rechner kompiliert werden.
6. Eine kleine synthetische Testrekonstruktion auf der GPU, einschließlich beider Meshvarianten.
7. Nach erfolgreichem Test die gespeicherte Auswahl der NKSR-Umgebung für spätere Starts.

Für diesen Abschnitt brauchst du noch keine eigene Punktwolke auszuwählen. Der Installationstest verwendet eine erzeugte Testgeometrie. Beim ersten Test können außerdem die vortrainierten Modellgewichte heruntergeladen werden.

Downloads und Kompilierung können längere Zeit beanspruchen. Das Programm zeigt Schritte und Build-Ausgaben, aber keine verbindliche Gesamtrestzeit. Warte den vollständigen Abschluss ab. Starte währenddessen keine zweite Einrichtung im selben Ordner.

### 6.3 Woran du den erfolgreichen Abschluss erkennst

Am Ende muss eine Erfolgsmeldung erscheinen, zum Beispiel:

```text
Einrichtung abgeschlossen. Ab jetzt Starten.cmd oeffnen.
```

Zusätzlich kann die Ausgabe darauf hinweisen, dass Play/F5 dieselbe Umgebung verwendet.

Die Aufforderung, eine beliebige Taste zu drücken, erscheint auch nach Fehlern. Sie allein bedeutet noch keinen erfolgreichen Abschluss. Bei **`Einrichtung fehlgeschlagen:`** oder einer anderen Fehlermeldung zuerst Abschnitt 13 lesen und den Fehlertext sichern.

Nach einem erfolgreichen Abschluss ist die Einrichtung für den normalen täglichen Start erledigt.

## 7. In VS Code den richtigen Windows-Python-Interpreter auswählen

Dieser Schritt sorgt dafür, dass der normale Play-Button den richtigen Python-Interpreter verwendet.

1. Öffne in VS Code die Datei **`main.py`**.
2. Gib im PowerShell-Terminal diesen Befehl ein:

   ```powershell
   Join-Path $env:LOCALAPPDATA 'Scan2Mesh\venv\Scripts\python.exe'
   ```

3. Kopiere den ausgegebenen vollständigen Pfad. Er sieht ungefähr so aus:

   ```text
   C:\Users\DEIN_WINDOWSNAME\AppData\Local\Scan2Mesh\venv\Scripts\python.exe
   ```

   Verwende die tatsächliche Ausgabe deines Rechners. `DEIN_WINDOWSNAME` ist im Beispiel nur ein Platzhalter.

4. Drücke **Strg + Umschalt + P**.
5. Suche nach **Python: Select Interpreter** beziehungsweise **Python: Interpreter auswählen**.
6. Wähle **Enter interpreter path … / Interpreterpfad eingeben …**.
7. Füge den kopierten vollständigen Pfad ein und bestätige. Falls stattdessen ein Dateiauswahldialog erscheint, navigiere zu diesem Pfad und wähle die Datei `python.exe` aus.
8. Falls VS Code danach zum Neuladen auffordert, lade das Fenster neu.

Der Pfad für diesen Windows-Start endet auf **`\Scan2Mesh\venv\Scripts\python.exe`**. Wähle die ausführbare Datei aus. Ein Ordner wie `.venv` ist kein ausführbares Programm. Der Linux-Interpreter unter `/opt/scan2mesh/...` wird intern von Scan2Mesh für NKSR aufgerufen.

Falls du prüfen möchtest, ob die Windows-Datei tatsächlich existiert:

```powershell
Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'Scan2Mesh\venv\Scripts\python.exe')
```

Nach erfolgreicher Einrichtung muss die Ausgabe **`True`** lauten.

Die Auswahl von Python-Umgebungen beschreibt auch die [VS-Code-Dokumentation](https://code.visualstudio.com/docs/python/environments).

## 8. Den ersten Scan aus VS Code starten

Verwende für den ersten eigenen Test einen überschaubaren, bereits registrierten Ausschnitt. Die Koordinaten sollen bekannt sein; der normale Start interpretiert sie als **Meter**. Eine fehlerhafte Scanregistrierung wird durch Scan2Mesh nicht neu berechnet.

Unterstützt werden:

```text
.ply  .pcd  .pts  .xyz  .xyzn  .xyzrgb
```

E57 sowie RCP/RCS vorher beispielsweise als PLY oder PTS exportieren. Vorhandene Punktfarben können später auf das Mesh übertragen werden.

### 8.1 Start mit F5

1. Öffne die Datei **`main.py`**.
2. Öffne links **Ausführen und Debuggen / Run and Debug**, gegebenenfalls mit **Strg + Umschalt + D**.
3. Wähle oben die Konfiguration **`Scan2Mesh: NKSR direkt (Standard)`**.
4. Drücke **F5**. Bei einigen Laptops ist dafür **Fn + F5** nötig.
5. Warte, bis die Aufgabe **Scan2Mesh: Umgebung vorbereiten** abgeschlossen ist. Sie gleicht die externe Windows-Python-Umgebung mit dem Projektstand ab.
6. Im anschließend geöffneten Dateidialog die Punktwolke auswählen und mit **Öffnen** bestätigen.

Falls die genannte Konfiguration nicht angeboten wird, prüfe, ob der richtige Projektordner mit dem Unterordner `.vscode` geöffnet wurde und die Python-Debugger-Erweiterung installiert ist.

### 8.2 Alternativ der normale Play-Button

1. Öffne **`main.py`**.
2. Klicke oben rechts auf **▶ Python-Datei im Terminal ausführen / Run Python File in Terminal**.
3. Wähle die Punktwolke im Dateidialog aus.

Prüfe bei mehreren Dreieck-Symbolen den eingeblendeten Namen. Hier ist der Python-Dateistart gemeint. Die [VS-Code-Anleitung zum Ausführen von Python](https://code.visualstudio.com/docs/python/run) beschreibt diese Funktion.

### 8.3 Alternativ der gemeinsame Starter im Terminal

Du kannst auch aus dem VS-Code-Terminal starten:

```powershell
.\Starten.cmd
```

Dieser Weg verwendet den eingerichteten Windows-Interpreter direkt und öffnet ebenfalls die Dateiauswahl. Außerhalb von VS Code reicht ein Doppelklick auf `Starten.cmd` im Projektordner.

### 8.4 Den Lauf abwarten

Nach der Dateiauswahl sollte unter anderem Folgendes erscheinen:

```text
NKSR direkt: Modell ks, Detailstufe 1.0, alle Originalpunkte.
Beide Exporte: mit und ohne interne NKSR-Maske; Originalfarben werden uebernommen.
```

Für eine frisch eingerichtete Umgebung wird außerdem die WSL-Distribution **`Scan2Mesh-NKSR`** angezeigt. Es folgen Meldungen zum Einlesen, zu gegebenenfalls fehlenden Normalen, zur NKSR-Rekonstruktion und zu den Exporten.

Lass den Lauf zu Ende arbeiten und starte währenddessen keinen weiteren Scan. Eine längere einzelne Stufe ist noch keine abgeschlossene Verarbeitung; es gibt keine verlässliche Prozentanzeige oder Restzeit.

Der normale Programmstart bestätigt den vollständigen Abschluss mit einer Meldung wie:

```text
Fertig: C:\Users\...\AppData\Local\Scan2Mesh\nksr-direkt-...
```

Ein Ergebnisordner kann bereits während der Verarbeitung existieren. Bei einem späteren Fehler können auch schon einzelne Dateien vorhanden sein. Prüfe deshalb den Abschluss im Terminal und gegebenenfalls eine danach ausgegebene Fehlermeldung.

Wenn du im Dateidialog **Abbrechen** wählst, wird kein Scan verarbeitet. Das ist ein regulärer Abbruch der Auswahl.

## 9. Die Ergebnisse finden und ansehen

1. Kopiere den im Terminal genannten Ergebnisordner.
2. Öffne den Windows-Explorer.
3. Füge den Pfad in die Adressleiste ein und drücke **Enter**.

Du kannst den Stammordner auch mit **Windows-Taste + R** öffnen:

```text
%LOCALAPPDATA%\Scan2Mesh
```

Darin liegt für jeden Lauf ein neuer Ordner:

```text
nksr-direkt-<Zeitstempel>-<Kennung>
```

Bei einer Punktwolke mit RGB-Farben entstehen nach erfolgreichem Lauf diese Dateien:

| Datei | Verwendung |
| --- | --- |
| `mesh_colored.ply` | Mesh mit interner NKSR-Maske, `trim=True` |
| `mesh_colored_untrimmed.ply` | Mesh ohne interne NKSR-Maske, `trim=False` |
| `nksr_raw.npz` | NKSR-Rohdaten des ersten Exports |
| `nksr_raw_untrimmed.npz` | NKSR-Rohdaten des zweiten Exports |
| `run.json` | Tatsächlich verwendete Laufparameter, Eingabe und Exportangaben |

Ohne RGB-Farben heißen die PLY-Dateien stattdessen **`mesh_raw.ply`** und **`mesh_raw_untrimmed.ply`**.

Zum Ansehen ein vorhandenes 3D-Programm wie CloudCompare oder MeshLab verwenden und die PLY-Dateien dort öffnen. Scan2Mesh installiert keinen Mesh-Viewer. Bei vorhandener Vertexfarbe gegebenenfalls die RGB-/Farbanzeige im Viewer einschalten.

Beide Varianten stammen aus derselben Rekonstruktion. Die interne Maske kann Bereiche entfernen; die unmaskierte Variante kann zusätzliche Flächen enthalten. Vergleiche relevante Öffnungen, Kanten und feine Bauteile mit der Originalpunktwolke.

## 10. Millimeter, direkte Dateipfade und andere Ausgabeordner

Die Standardeinstellung des Play-/F5-Starts sind Meterkoordinaten. Wenn deine exportierten Punktkoordinaten in Millimetern vorliegen, starte aus dem PowerShell-Terminal so:

```powershell
.\Starten.cmd -Units mm
```

Der Dateidialog öffnet sich wie gewohnt. Die Einheit wird nicht automatisch aus dem Dateiformat erkannt.

Einen Scan direkt ohne Auswahldialog verarbeiten:

```powershell
.\Starten.cmd -InputFile "C:\Scans\Ausschnitt.ply"
```

Einen anderen Ausgabe-Stammordner wählen:

```powershell
.\Starten.cmd -InputFile "C:\Scans\Ausschnitt.ply" -OutputRoot "D:\Scan2Mesh-Ergebnisse"
```

Optionen lassen sich kombinieren:

```powershell
.\Starten.cmd -InputFile "C:\Scans\Ausschnitt-mm.ply" -Units mm -OutputRoot "D:\Scan2Mesh-Ergebnisse"
```

Die Pfade sind Beispiele und müssen durch vorhandene Eingabedateien beziehungsweise einen passenden Ausgabeort ersetzt werden. Anführungszeichen bei Pfaden mit Leerzeichen beibehalten.

## 11. So sieht der tägliche Start später aus

Die Einrichtung ist abgeschlossen und Windows wurde gegebenenfalls bereits neu gestartet. Für einen weiteren normalen Lauf:

1. VS Code öffnen.
2. Den Projektordner öffnen.
3. `main.py` öffnen.
4. **F5** mit **Scan2Mesh: NKSR direkt (Standard)** oder den konfigurierten Python-Play-Button verwenden.
5. Die nächste Punktwolke auswählen.
6. Den Abschluss abwarten und den neuen Ergebnisordner ansehen.

Alternativ einfach `Starten.cmd` doppelklicken. WSL und der NKSR-Prozess werden intern aufgerufen; ein manuelles Öffnen eines Ubuntu-Terminals ist für den normalen Lauf nicht erforderlich.

`Einrichten.cmd` ist für die erstmalige Einrichtung und bei Bedarf für einen erneuten Einrichtungsversuch vorgesehen. Es muss nicht vor jedem Scan gestartet werden.

## 12. Eine neue Projektversion übernehmen

### Wenn du das Projekt als ZIP heruntergeladen hast

Eine entpackte ZIP ist keine Git-Arbeitskopie. Für diesen Weg:

1. Laufende Verarbeitungen zuerst beenden lassen.
2. Die aktuelle ZIP desselben Branches erneut von GitHub herunterladen.
3. Die neue ZIP vollständig in einen neuen Projektordner entpacken.
4. In VS Code diesen neuen Ordner öffnen.
5. Für den ersten Start **F5** mit der Projektkonfiguration oder **`Starten.cmd`** verwenden. Beide bereiten die Windows-Umgebung für den neuen Quellcodeordner vor.
6. Falls VS Code den Interpreter erneut abfragt, wieder die externe Windows-`python.exe` aus Schritt 7 auswählen.

Installation und Ergebnisse liegen außerhalb des ZIP-Projektordners unter `%LOCALAPPDATA%\Scan2Mesh` und bleiben dort erhalten. Bei Änderungen an der eigentlichen NKSR-Installation die Versionshinweise des Betreuers beachten.

### Nur wenn bereits eine echte Git-Arbeitskopie verwendet wird

Nach Abschluss laufender Verarbeitungen im Projektterminal:

```powershell
git fetch origin
git switch codex/windows-setup
git pull --ff-only origin codex/windows-setup
```

Falls Git eigene lokale Änderungen meldet, diese zuerst mit dem Betreuer klären beziehungsweise sichern. Der ZIP-Weg oben funktioniert weiterhin ohne Git.

## 13. Typische Probleme und passende nächste Schritte

### „Einrichten.cmd“ oder „Starten.cmd“ wird nicht gefunden

Im PowerShell-Terminal die Form mit `.\` verwenden:

```powershell
.\Einrichten.cmd
```

Mit `Get-Location` den aktuellen Ordner und mit `Get-ChildItem` dessen Inhalt prüfen. Bei einer ZIP prüfen, ob sie vollständig entpackt ist und der tatsächliche Projektordner geöffnet wurde.

### Das Setup fordert nach dem ersten Start einen Neustart

Windows neu starten und danach dieselbe `Einrichten.cmd` erneut ausführen, wie in Abschnitt 6.1 beschrieben. Bei einer erneuten Fehlermeldung zu WSL oder Virtualisierung deren genauen Text sichern und die IT beziehungsweise den Ansprechpartner einbeziehen.

### „Einrichtung fehlgeschlagen“ oder ein Download-/Buildfehler erscheint

1. Nicht allein anhand der Aufforderung „beliebige Taste drücken“ von Erfolg ausgehen.
2. Die erste aussagekräftige Fehlermeldung und den zugehörigen Schritt kopieren.
3. Bei einem blockierten Download die angezeigte Quelle und den Fehlertext weitergeben.
4. Nach Behebung des Hindernisses `Einrichten.cmd` erneut starten.

Bereits angelegte Installationen und WSL-Distributionen nicht vorsorglich löschen. Das Setup ist für Wiederholungen nach einem Abbruch vorbereitet. Bei gesperrten Skripten oder Downloads auf einem Firmenrechner die zuständige IT einbeziehen.

### VS Code versucht, nur den Ordner `.venv` auszuführen

Die Fehlermeldung zeigt dann beispielsweise einen Startpfad, der mit `Scan2Mesh/.venv` endet.

Den Interpreter aus Abschnitt 7 erneut auswählen. Er muss auf diese Datei zeigen:

```text
%LOCALAPPDATA%\Scan2Mesh\venv\Scripts\python.exe
```

Für den unmittelbar ausführbaren Terminalstart:

```powershell
.\Starten.cmd
```

### `uv` oder `python` wird als Terminalbefehl nicht erkannt

Nach erfolgreichem Setup `Starten.cmd` oder die eingerichtete F5-Konfiguration verwenden. Die Werkzeuge liegen im verwalteten Benutzerverzeichnis und müssen für diesen Ablauf nicht manuell auf den systemweiten Suchpfad gesetzt werden.

### Die Konfiguration „Scan2Mesh: NKSR direkt (Standard)“ fehlt

Prüfen, ob `main.py`, `pyproject.toml` und `.vscode` direkt im geöffneten Projektordner liegen. Außerdem prüfen, ob die Microsoft-Erweiterung **Python Debugger** installiert und aktiviert ist. Anschließend VS Code gegebenenfalls neu laden.

### „Die NKSR-Einrichtung ist noch nicht abgeschlossen“ erscheint

Das Setup hat die Umgebung noch nicht erfolgreich für den normalen Start registriert. `Einrichten.cmd` erneut ausführen und den tatsächlichen Abschluss beziehungsweise die Fehlermeldung abwarten. Eine `backend.json` muss nicht von Hand erstellt werden.

### Keine NVIDIA-/CUDA-GPU ist sichtbar

Die NVIDIA-Grafikkarte benötigt einen funktionierenden Windows-Treiber und WSL2-GPU-Zugriff. Der kleine Setup-Test muss erfolgreich durchlaufen. Das Setup installiert keinen NVIDIA-Windows-Treiber. Den genauen Fehlertext an den Ansprechpartner beziehungsweise die IT weitergeben.

### „CUDA out of memory“ erscheint

Der GPU-Prozess meldet einen Speicherfehler. Die Phase des Abbruchs ist dabei wichtig. Sichere den Fehlertext und nenne die verwendete Eingabedatei beziehungsweise deren Punktzahl, soweit sie im Terminal ausgegeben wurde. Für einen ersten Vergleich einen kleineren, bereits vorbereiteten Ausschnitt verwenden.

Scan2Mesh reduziert die höchste Detailstufe nicht automatisch. Ein erfolgreicher kleiner Installationstest garantiert nicht, dass eine beliebig große Punktwolke in den GPU-Speicher passt.

### Eine Warnung zum „Customized build of Open3D“ erscheint

Ein Hinweis auf einen fehlenden angepassten Open3D-Build kann aus PyCG stammen. Achte auf den weiteren Verlauf: Eine Warnung allein ist kein erfolgreicher Abschluss, aber auch noch kein Beleg für den späteren Abbruchgrund. Entscheidend sind eine konkrete Fehlermeldung oder der erfolgreiche vollständige Lauf. Bei Bedarf den gesamten relevanten Abschnitt weitergeben.

### Ein Ergebnisordner ist vorhanden, aber der Lauf ist fehlgeschlagen

Der NKSR-Direktlauf legt den Ordner bereits vor der Rekonstruktion an. Bei Fehlern können einzelne Rohdaten oder ein erster Export erhalten bleiben. Ein vorhandener Ordner ersetzt deshalb nicht die Abschlussmeldung im Terminal. Den Fehlertext sichern und vorhandene Dateien zunächst erhalten.

## 14. Was der eingestellte Ablauf macht

Die normale Rekonstruktion verwendet:

- alle eingelesenen Originalpunkte, ohne Voxelreduktion, Ausreißerfilter oder Segmentierung;
- vorhandene Normalen beziehungsweise eine Schätzung fehlender Normalen;
- NKSR mit dem vortrainierten Modell `ks` auf `cuda:0`;
- die höchste Detailstufe `1.0`;
- Meshextraktion mit `mise_iter=1`;
- beide Varianten `trim=True` und `trim=False`;
- bei vorhandenen Punktfarben die Farbübertragung auf die Mesh-Eckpunkte.

Die Quelldatei bleibt erhalten und jeder Lauf erhält einen neuen Ausgabeordner. Der normale Start erzeugt die oben beschriebenen NKSR-Dateien; die früheren Vergleichsdateien `cleaned.ply`, `segments.ply` und `report.json` gehören nicht zu diesem direkten Standardablauf.

Weitere technische Angaben und die Bedingungen für NKSR-Code und Modellgewichte stehen in [NKSR-Umgebung](nksr.md). Eine kürzere Übersicht zur Windows-Einrichtung bietet [Windows einmalig einrichten](windows-setup.md).

## 15. Kurze Liste für den ersten vollständigen Durchlauf

- [ ] Zugriff auf den Branch `codex/windows-setup` vorhanden.
- [ ] ZIP vollständig entpackt und richtigen Projektordner in VS Code geöffnet.
- [ ] Microsoft-Erweiterungen **Python** und **Python Debugger** installiert.
- [ ] `.\Einrichten.cmd` gestartet.
- [ ] Falls verlangt: Windows neu gestartet und `.\Einrichten.cmd` erneut ausgeführt.
- [ ] Erfolgsmeldung der Einrichtung einschließlich GPU-Test erhalten.
- [ ] Externe Windows-`python.exe` in VS Code ausgewählt.
- [ ] Ersten kleinen Scan mit Meterkoordinaten über F5 oder Play gestartet.
- [ ] Abschlussmeldung ohne nachfolgenden Fehler erhalten.
- [ ] Beide PLY-Varianten im Ergebnisordner gefunden und im Mesh-Viewer angesehen.
