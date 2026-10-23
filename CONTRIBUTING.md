# Mitwirken

Beiträge zu StreamerMod sind willkommen: Fehlerberichte, Übersetzungen, Tests und nachvollziehbare Verbesserungen.

1. Issue mit Problem, Linux-Version und reproduzierbaren Schritten erstellen. Zugangsdaten, Chatverläufe und persönliche Konfigurationen vorher entfernen.
2. Fork/Branch anlegen, kleine zusammenhängende Änderungen umsetzen.
3. Die passenden Tests ausführen und Ergebnis im Pull Request nennen. Hardware-/Plattformtests ausdrücklich von Simulationen unterscheiden.
4. Eigener Code steht unter GPL-3.0. Drittanbieterdateien behalten ihre ursprünglichen Hinweise.

## Technische Struktur

- `sorgobot/next_desktop.py`: native Qt-Oberfläche.
- `sorgobot/core.py`, `catalog.py`, `next_catalog.py`: Action-Engine und Menükataloge.
- `sorgobot/adapters.py`, `twitch*.py`, `youtube*.py`, `obs*.py`: externe Dienste.
- `sorgobot/fresh_project.py`: kontenfreie Erstkonfiguration.
- `scripts/`, `install.sh`: Benutzer- und Systeminstallation.
- `tools/build_clean_distribution.py`: geprüfte Dateiliste für Weitergabekopien.

Niemals eine aktive `config/`, `next-studio/config/`, Datenbank, private JSON-Datei, einen Import mit echten Konten oder die eigene virtuelle Umgebung hochladen. Die Weitergabekopie wird immer mit neutralen Standardwerten erzeugt. Ein lokal gestartetes Programm kann neue private Dateien anlegen; diese gehören nicht ins Repository.

Beispiel für gezielte Tests aus dem Entwicklungsstand:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tests .venv-linux/bin/python -m unittest test_fresh_project test_installer -v
```

Für Fehler mit Stream Deck, MIDI, mehreren Geräten oder Plattformrechten bitte das getestete Modell und den tatsächlichen Prüfweg nennen. Nicht getestete Hardware gilt nicht durch einen bestandenen Unit-Test als abgenommen.
