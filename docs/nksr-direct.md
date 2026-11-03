# NKSR direkt mit Dateiauswahl und Farbe testen

`nksr-direkt.ps1` oeffnet den Windows-Dateiauswahldialog und ruft NKSR in der bereits eingerichteten WSL-Umgebung auf. Dieser Test verwendet `scripts/nksr_direct.py` statt der Scan2Mesh-Pipeline. Er liest die Originalpunktwolke ohne Ausduennung, Ausreisserfilter oder Segmentierung ein und exportiert das NKSR-Mesh ohne Meshbereinigung oder Qualitaetspruefung.

Die bestehende NKSR-Installation kann weiterverwendet werden. Es gelten weiterhin die separate NKSR-Code- und Modelllizenz; siehe [Einrichtung](nksr.md).

## Start unter Windows

Im Scan2Mesh-Projektordner in PowerShell starten:

```powershell
powershell.exe -NoProfile -STA -File .\nksr-direkt.ps1 -WslDistro Ubuntu-22.04 -NksrPython /home/DEIN_LINUXNAME/miniforge3/envs/nksr/bin/python
```

Den Python-Pfad durch den absoluten Pfad der vorhandenen Linux-Umgebung ersetzen. Wenn `SCAN2MESH_NKSR_WSL_DISTRO` und `SCAN2MESH_NKSR_PYTHON` bereits gesetzt sind, reicht `powershell.exe -NoProfile -STA -File .\nksr-direkt.ps1`.

Im Dialog eine PLY-, PCD-, PTS-, XYZ-, XYZN- oder XYZRGB-Datei waehlen. Bei Abbruch startet keine Rekonstruktion. E57 wird von diesem direkten Test nicht eingelesen. Fuer vorhandene RGB-Farben eignet sich zum Beispiel ein PLY-Export mit Punktfarben.

Standard sind Koordinaten in Metern. Fuer Millimeter `-Units mm` an den Startbefehl anhaengen. `-OutputRoot C:\Pfad\zu\Ergebnissen` waehlt einen anderen Ausgabeort; Standard ist `%LOCALAPPDATA%\Scan2Mesh`.

## Was der direkte Test macht

- Alle eingelesenen Punkte gehen in NKSR ein. Vorhandene Normalen werden uebernommen. Nur wenn Normalen fehlen, werden sie mit Open3D geschaetzt und konsistent ausgerichtet.
- Eine reversible Verschiebung des Koordinatenursprungs schuetzt die Float32-Genauigkeit. Millimeter werden fuer NKSR nach Metern umgerechnet. Der PLY-Export erhaelt die urspruenglichen Einheiten und Weltkoordinaten zurueck.
- NKSR laeuft mit `cuda:0`, dem vortrainierten `ks`-Modell, standardmaessig `detail_level=1.0` (hoechste Detailstufe) und `extract_dual_mesh(mise_iter=1, trim=True)`. `-DetailLevel` waehlt ausdruecklich einen anderen Wert zwischen 0 und 1. Der Detailgrad steht beim Start im Terminal und anschliessend in `run.json`.
- Die unveraenderten NKSR-Vertex- und Dreiecksarrays werden zuerst als `nksr_raw.npz` gesichert.
- Bei RGB in der Quelle bekommt jeder Mesh-Eckpunkt die Farbe des naechstgelegenen Originalpunkts. Diese Zuordnung hat keinen Abstandsschwellwert und aendert keine Meshgeometrie. Es ist eine Vertexfaerbung, keine Bildtextur.
- Ohne RGB wird ein farbloses Mesh geschrieben und darauf hingewiesen. Es werden keine Farben erfunden.

Die Ausgabe liegt jeweils in einem neuen `nksr-direkt-<Zeitstempel>-<Kennung>`-Ordner. Bei RGB heisst das Mesh `mesh_colored.ply`, sonst `mesh_raw.ply`. Den genauen Pfad zeigt das Terminal; nach Erfolg oeffnet sich der Windows-Explorer im Ausgabe-Stammordner. In CloudCompare gegebenenfalls RGB/Colors einschalten.

Dieser Aufruf trainiert kein Modell und verwendet keine Scan2Mesh-Bewertungskriterien. Lese-, Schreib- und NKSR-Laufzeitfehler werden weiterhin angezeigt. Die Punktwolke wird vollstaendig geladen und ohne Chunking rekonstruiert; RAM und Grafikspeicher begrenzen auch diesen direkten Test. Mehr Punkte verbessern das Ergebnis nicht automatisch: Punktverteilung, Normalen und die Rekonstruktionsskala wirken ebenfalls darauf.

Die hoechste Detailstufe benoetigt mehr Grafikspeicher und kann Messrauschen staerker rekonstruieren. Der Starter reduziert den Detailgrad bei Speichermangel nicht automatisch.

## Loecher untersuchen: NKSRs interne Exportmaske vergleichen

NKSRs Mesh-Export verwendet standardmaessig `trim=True`. Beim `ks`-Modell kann dabei eine gelernte Maske Teile der berechneten Oberflaeche entfernen. Mit `-CompareTrim` werden aus derselben Rekonstruktion beide Varianten exportiert:

```powershell
powershell.exe -NoProfile -STA -File .\nksr-direkt.ps1 -WslDistro Ubuntu-22.04 -NksrPython /home/DEIN_LINUXNAME/miniforge3/envs/nksr/bin/python -CompareTrim
```

| Variante | Mit RGB | Ohne RGB | Roharrays |
| --- | --- | --- | --- |
| NKSR-Standard, `trim=True` | `mesh_colored.ply` | `mesh_raw.ply` | `nksr_raw.npz` |
| Ohne interne Exportmaske, `trim=False` | `mesh_colored_untrimmed.ply` | `mesh_raw_untrimmed.ply` | `nksr_raw_untrimmed.npz` |

Das Netzwerk und die Normalen werden einmal berechnet. Die beiden Meshextraktionen und Farbuebertragungen laufen anschliessend nacheinander. `run.json` enthaelt unter `exports` die tatsaechliche `trim`-Einstellung, Dateipfade und Zaehlwerte jeder erfolgreich geschriebenen Variante. Die Roharrays einer Variante werden jeweils vor deren Farbuebertragung gesichert; die erste PLY und ihr Bericht bleiben erhalten, falls der zweite Export fehlschlaegt.

Wenn ein Loch nur in der Standardvariante vorhanden ist, hat die Exportmaske dort Flaeche entfernt. `trim=False` kann aber auch unerwuenschte Flaechen ausserhalb der Messdaten sichtbar machen. Es ist kein allgemeiner Lochfueller und garantiert kein geschlossenes Mesh: Das berechnete Feld und seine raeumliche Stuetzstruktur bleiben begrenzt. Es werden weiterhin keine zusaetzlichen Scan2Mesh-Filter, Meshbereinigungen oder Bewertungskriterien angewandt. Siehe [NKSR-Meshextraktion](https://github.com/nv-tlabs/NKSR/blob/public/package/nksr/fields/base_field.py).

Fuer einen zweiten kontrollierten Vergleich denselben Ausschnitt beispielsweise mit `-DetailLevel 0.5 -CompareTrim` starten. Der Standard bleibt 1.0. Die [NKSR-API](https://github.com/nv-tlabs/NKSR/blob/public/package/nksr/__init__.py) weist ausdruecklich darauf hin, dass hoehere Detailstufen die Vollstaendigkeit verschlechtern koennen. Hoeher aufgeloeste Dreiecke allein ersetzen keine fehlenden Messpunkte; an anhaltenden Loechern Originalpunktwolke und Normalenorientierung vergleichen.

Bei Abschattungen fehlen tatsaechliche Oberflaechenmessungen. Eine dort zusaetzlich sichtbare unmaskierte Flaeche ist eine moegliche Ergaenzung des Modells und keine gemessene Oberflaeche. Fuer den Vergleich einen Ausschnitt mit ausreichend gemessener Umgebung um die Luecke waehlen. Kleine Luecken koennen sich bei anderer Skala ueberbruecken; groessere verdeckte Bereiche lassen sich ohne weitere Annahmen oder Aufnahmen nicht verlaesslich bestimmen. Eine gezielte Fortsetzung einer belegten Ebene oder eines Zylinders ist eine separate geometrische Ergaenzung. Ein automatisches Verschliessen aller Raender koennte auch echte Oeffnungen verschliessen und wird hier nicht ausgefuehrt.
