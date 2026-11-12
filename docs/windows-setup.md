# Windows einmalig einrichten

`Einrichten.cmd` bereitet einen Windows-Rechner für den gemeinsamen NKSR-Direktlauf vor. Für den täglichen Start dient anschließend `Starten.cmd`. Eine Installation von Git, Python, Ubuntu oder VS Code vor dem Setup ist nicht erforderlich.

Eine [ausführliche Anleitung für Mitarbeiter mit bereits installiertem VS Code](mitarbeiter-anleitung.md) beschreibt jeden Schritt einschließlich Python-Auswahl, F5/Play, erster Punktwolke und Ergebnissen im Branch `codex/windows-setup`.

## Voraussetzungen

- Windows mit Unterstützung für WSL2 und aktivierbarer Hardwarevirtualisierung.
- Eine geeignete NVIDIA-GPU mit funktionierendem NVIDIA-Windows-Treiber. Der Rechner muss die GPU später auch in WSL sehen können. Das Setup installiert keinen Hardwaretreiber.
- Internetzugang für die Installationspakete, Quellen und NKSR-Modellgewichte sowie ausreichend freien Platz für WSL, CUDA, PyTorch und den Build.
- Administratorrechte für die einmalige Aktivierung der Windows-/WSL-Funktionen. Der spätere normale Programmstart benötigt keine Administratorrechte.

Der tatsächliche GPU-Speicherbedarf einer Punktwolke hängt von Auflösung und Geometrie ab. Der kleine Installationstest belegt nicht, dass jeder große Scan in den vorhandenen Speicher passt.

## Herunterladen und einrichten

1. Das [Repository auf GitHub](https://github.com/xenijadsjtkn/Scan2Mesh) öffnen, **main** auswählen und **Code → Download ZIP** verwenden.
2. Die ZIP-Datei vollständig in einen beschreibbaren Ordner entpacken, zum Beispiel in einen eigenen Projektordner. Bei einer vorhandenen Git-Installation kann stattdessen das Repository geklont oder auf `main` aktualisiert werden.
3. **`Einrichten.cmd` doppelklicken.** Die Abfrage für die Aktivierung erforderlicher Windows-/WSL-Funktionen bestätigen.
4. Fordert das Setup einen Neustart an, Windows neu starten und anschließend **dieselbe `Einrichten.cmd` erneut ausführen**. Die Einrichtung wird nicht allein durch den Neustart fertiggestellt.
5. Die Downloads, den Linux-Build und den abschließenden GPU-Test abwarten. Erst nach erfolgreichem Abschluss **`Starten.cmd` öffnen**.

Während der erstmaligen Einrichtung werden größere Pakete heruntergeladen und native Erweiterungen kompiliert. Dauer und Speicherbedarf hängen von Rechner und Verbindung ab. Es gibt hier keine fertige, auf beliebigen Kollegenrechnern geprüfte WSL-Abbildung; der erste Aufbau erfolgt auf dem jeweiligen Zielrechner.

## Was die Einrichtung anlegt

Das Setup verwendet eine eigene WSL2-Distribution **`Scan2Mesh-NKSR`** auf Basis eines festgelegten Ubuntu-22.04-Root-Dateisystems. Die Linux-Umgebung liegt dort unter `/opt/scan2mesh`, der NKSR-Interpreter unter `/opt/scan2mesh/envs/nksr/bin/python`.

Auf Windows verwaltet Scan2Mesh seine Werkzeuge, die Python-3.12-Umgebung und den Cache unter **`%LOCALAPPDATA%\Scan2Mesh`**, außerhalb des Quellcodeordners und möglicher OneDrive-Synchronisierung. Windows-Python und Projektabhängigkeiten werden mit dem verwalteten `uv` und `uv sync --frozen` vorbereitet. Die separate Linux-Umgebung verwendet Python 3.10, CUDA 12.8, PyTorch 2.7.0 und den festgelegten NKSR-Quellstand.

Downloadadressen, Versionen und Prüfsummen stehen in [setup/versions.json](../setup/versions.json). Die ausgewählten direkten Python-Abhängigkeiten stehen in [setup/nksr-requirements.txt](../setup/nksr-requirements.txt). Diese Festlegungen sind keine vollständige transitive Sperrdatei für alle Linux-Pakete und kein Versprechen bitweise identischer Builds.

Andere vorhandene WSL-Distributionen und Benutzerumgebungen werden nicht ersetzt. Eine ausdrücklich ausgewählte vorhandene NKSR-Installation kann stattdessen nach erfolgreicher Funktionsprüfung weiterverwendet werden. Damit muss ein bereits funktionierender Referenzaufbau nicht neu installiert werden.

## Bestehende persönliche Installation weiterverwenden

Wenn bereits eine passende WSL-/NKSR-Umgebung eingerichtet ist, kann sie vor dem Setup ausdrücklich im PowerShell-Terminal gewählt werden. Die Beispielwerte durch die tatsächliche Distribution und den vollständigen Linux-Python-Pfad ersetzen:

```powershell
$env:SCAN2MESH_NKSR_WSL_DISTRO = 'Ubuntu-22.04'
$env:SCAN2MESH_NKSR_PYTHON = '/home/DEIN_LINUXNAME/miniforge3/envs/nksr/bin/python'
.\Einrichten.cmd
```

Das Setup prüft diese Installation mit der kleinen echten Rekonstruktion und registriert sie bei Erfolg. Es installiert oder repariert keine Pakete in dieser persönlichen Umgebung. Eine bereits gespeicherte `backend.json` wird ebenfalls für diesen Wiederverwendungspfad berücksichtigt. Eine bisher nicht konfigurierte Umgebung wird nicht allein aufgrund ihres Namens als fertiger Ersatz für die neue verwaltete Installation übernommen.

## Abschlussprüfung und gespeicherte Auswahl

Der abschließende Installationstest führt eine **kleine echte NKSR-Rekonstruktion auf CUDA mit beiden Trim-Exporten** aus. Ein erfolgreicher Import von PyTorch oder die bloße Anzeige einer Grafikkarte reicht nicht als Setup-Erfolg aus.

Erst nach erfolgreicher Rekonstruktion wird die verwendete Installation in **`%LOCALAPPDATA%\Scan2Mesh\backend.json`** gespeichert. Der normale Programmstart und Play/F5 lesen diese Auswahl automatisch. Ausdrückliche Optionen oder Umgebungsvariablen haben weiterhin Vorrang:

1. `--nksr-python` und `--nksr-wsl-distro`.
2. `SCAN2MESH_NKSR_PYTHON` und `SCAN2MESH_NKSR_WSL_DISTRO`.
3. Die gespeicherte Konfiguration in `backend.json`.
4. Die automatische Suche nach einer bestehenden Umgebung.

Der Test gehört ausschließlich zur Installation. Er verändert den Rekonstruktionsablauf der später ausgewählten Punktwolken nicht. Details zu Modell, Normalen und beiden Exporten stehen unter [NKSR-Direktlauf](nksr-direct.md).

## Nach der Einrichtung

**`Starten.cmd` doppelklicken**, die Punktwolke auswählen und die Meldung **Fertig** abwarten. Der Launcher verwendet die verwalteten Windows-Werkzeuge; Python oder `uv` müssen dafür nicht von Hand auf den systemweiten Suchpfad gesetzt werden. Für einen neuen Datenlauf ist kein Administratorfenster erforderlich.

Unterstützte Dateien sind PLY, PCD, PTS, XYZ, XYZN und XYZRGB. E57/RCP/RCS vorher als PLY oder PTS exportieren. Die Koordinaten werden standardmäßig als Meter interpretiert. Die feste Rekonstruktion arbeitet mit Modell `ks`, höchster Detailstufe `1.0`, allen Originalpunkten und beiden Maskenvarianten. Bei Fehlern oder Speichermangel wechselt sie nicht auf ein anderes Verfahren oder eine geringere Detailstufe.

Für Millimeterkoordinaten lässt sich im PowerShell-Terminal `.\Starten.cmd -Units mm` aufrufen. `-InputFile "C:\Scans\scan.ply"` überspringt die Dateiauswahl und `-OutputRoot "D:\Ergebnisse"` wählt einen anderen Ergebnis-Stammordner.

Die Ergebnisse liegen unter `%LOCALAPPDATA%\Scan2Mesh\nksr-direkt-…`; im Terminal steht der genaue Pfad. Bei vorhandenen Punktfarben entstehen `mesh_colored.ply` und `mesh_colored_untrimmed.ply`, sonst die entsprechenden `mesh_raw…`-Dateien. Für jeden Lauf wird ein neuer Ordner angelegt.

## Wenn die Einrichtung abbricht

| Meldung oder Situation | Nächster Schritt |
| --- | --- |
| Neustart erforderlich | Windows neu starten und `Einrichten.cmd` erneut öffnen. |
| Virtualisierung/WSL2 nicht verfügbar | Hardwarevirtualisierung beziehungsweise die WSL-Unterstützung durch die zuständige IT prüfen lassen. |
| NVIDIA-Treiber fehlt oder keine CUDA-GPU sichtbar | Einen passenden NVIDIA-Windows-Treiber installieren beziehungsweise die vorhandene GPU-/WSL-Unterstützung prüfen lassen. Das Setup installiert diesen Treiber nicht. |
| Download durch Firmennetz gesperrt | Die konkret im Setup genannte offizielle Downloadquelle und Fehlermeldung an die IT weitergeben; Downloads werden unter anderem für Ubuntu, GitHub, Conda, NVIDIA, PyTorch und Modellgewichte benötigt. |
| Native NKSR-Erweiterung lässt sich nicht bauen | Die erste Buildfehlermeldung und den zugehörigen Schritt sichern. Ein vorangegangener Downloadabschluss bedeutet noch keine erfolgreiche Installation. |
| Kleiner GPU-Test scheitert | Die Setup-Fehlermeldung prüfen. Die neue Umgebung wird erst nach erfolgreichem Test für den normalen Start registriert. |
| Großer eigener Scan meldet zu wenig GPU-Speicher | Einen kleineren bereits vorbereiteten Ausschnitt verwenden. Der Standardlauf reduziert die Detailstufe nicht automatisch. |

Fehlermeldungen stehen im geöffneten Setup-Fenster; den betreffenden Text vor dem Schließen kopieren. Das Setup lässt sich nach einem behobenen Hindernis erneut starten. Eine bereits vorhandene persönliche WSL- oder NKSR-Installation nicht vorsorglich löschen. Weitergehende Informationen und die Lizenzbedingungen stehen unter [NKSR-Umgebung](nksr.md).

Die bereitgestellten automatisierten Tests prüfen die Start- und Setup-Verträge in der Entwicklungsumgebung. Eine frische Installation auf Windows mit der konkreten GPU muss durch den dort ausgeführten lokalen Setup-Test bestätigt werden.
