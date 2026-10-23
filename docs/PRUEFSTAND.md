# Installations- und Prüfstand

Dieser Stand wurde auf Debian 13 / x86_64 vorbereitet. Eine pauschale Abnahme aller Distributionen und Geräte wird nicht behauptet.

## Geprüft

- Shell- und Python-Syntax des Installers.
- Installer-Tests für Standardumfang, optionale Komponenten, Leerzeichen in Pfaden, Prüfsummenfehler und Erhalt vorhandener Zielkonfigurationen.
- Vorhandene Tests des eingeschränkten Tastensperrdiensts und des .NET-Wertdiensts.
- Wirkliche Installation aller Python-Extras in ein separates Benutzerverzeichnis, getrennt von der laufenden Anwendung.
- Auflösung der vorgesehenen Systempakete über apt im Simulationsmodus.
- Import der Audio- und YouTube-Laufzeitabhängigkeiten mit den benötigten Distributionsbibliotheken.
- Download und SHA512-Prüfung des offiziellen .NET-10-SDK.
- Download von Whisper Base mit fester Modellrevision und Prüfsummenprüfung.
- Vollständiger Diagnose-Lauf mit SDK, Sprachmodell und allen Python-Funktionsgruppen.
- Erfolgreicher Bau des festgelegten keyd-Quellpakets für den Fallback ohne Distributionspaket.

## Grenzen

Der Test ersetzt keine vollständige Neuinstallation in einer leeren VM und keine physische Abnahme auf arm64 oder allen Ubuntu-Versionen. Systempakete und Dienste werden im Standardinstaller tatsächlich eingerichtet; die isolierte Installerprüfung hat die vorhandene Desktop-Installation nicht überschrieben.

Im Projekt wurden ein Stream Deck + mit OpenDeck und verschiedene Twitch-/OBS-Abläufe praktisch geprüft. Nicht jeder Trigger, jede Schreibwirkung, jedes Gerät und jedes Fremdplugin ist dadurch automatisch abgenommen. Frühere Entwicklungsarchive, private Konten und persönliche Testverläufe sind nicht Teil dieses Repositorys.

Ein erfolgreicher `tools/check_installation.py`-Lauf prüft Abhängigkeiten und Dateien. Er aktiviert kein Mikrofon, meldet keine Konten an und startet keinen Stream.
