# Drittanbieter und Lizenzgrenzen

Die GPL-3.0-Lizenz im Projektverzeichnis gilt für den eigenen StreamerMod-Code. Drittanbieterdateien behalten ihre jeweiligen Lizenzen; eine GPL-Neulizenzierung fremder Bibliotheken wird nicht behauptet.

| Komponente | Verwendung | Bezugsquelle und Lizenz |
|---|---|---|
| Python, Qt/PySide6 und Python-Pakete | Anwendung, Oberfläche und Integrationen | Installation aus PyPI; Lizenzen der jeweiligen Distributionen, u. a. LGPL/GPL/commercial für Qt/PySide6 |
| .NET 10 SDK | C#-Kompilierung und separater Wertdienst | [Microsoft](https://dotnet.microsoft.com/download/dotnet/10.0), eigene MIT-/Drittanbieterhinweise im SDK |
| mXparser 6.1.0 | Mathematische Ausdrücke im separaten .NET-Wertdienst | Unveränderte DLL, vollständige [Dual License](sorgobot/vendor/mxparser-6.1.0/LICENSE.txt), Herkunft und Prüfsummen im selben Ordner |
| Whisper Base / Small, faster-whisper | Lokale Spracherkennung | MIT, siehe [Sprachhinweise](THIRD-PARTY-SPEECH.md) und Modellmanifeste |
| Vosk und optionale Modelle | Alternative lokale Spracherkennung | Apache-2.0 bzw. Modelllizenz, siehe Sprachhinweise |
| OBS Studio | Externes Aufnahme-/Streamingprogramm | [obsproject/obs-studio](https://github.com/obsproject/obs-studio), GPL-2.0-or-later |
| OpenDeck, optional | Eigenständiger Stream-Deck-Host | [nekename/OpenDeck](https://github.com/nekename/OpenDeck), unverändertes offizielles Paket mit eigenen Lizenzdateien |
| YouTube-Protokolldefinitionen | Live-Chat-Streaming | Herkunft und Hinweise in `sorgobot/youtube_proto/`; generierte Laufzeitabhängigkeiten über PyPI |

## mXparser ausdrücklich beachten

mXparser ist nicht von der GPL des eigenen Codes erfasst. Seine Dual License unterscheidet nichtkommerzielle und kommerzielle Nutzung. Ein kostenloser Download von StreamerMod ist keine pauschale Freigabe der Bibliothek für jede kommerzielle Verwendung. Wer sie kommerziell nutzen oder eine kombinierte Software weiterverteilen möchte, muss die vollständigen Bedingungen prüfen und gegebenenfalls eine Herstellerlizenz erwerben. Die vollständige Original-Lizenz bleibt unverändert neben der DLL und wird zum Wertdienst kopiert. Quellen und Prüfsummen stehen in `UPSTREAM.json`.

Das Repository enthält keinen aus persönlichen Daten kompilierten Wertdienst. Er wird lokal mit dem installierten SDK erstellt. Die Veröffentlichung dieses Quellcodes beansprucht keine weitergehenden Rechte an Drittanbieterkomponenten.

Die Installation lädt Pakete und Modelle von ihren offiziellen Anbietern. Es werden keine Twitch-, Google-, Discord-, OpenAI- oder OBS-Zugangsdaten mitgeliefert.

Der Wertdienst ist standardmäßig für nichtkommerzielle Nutzung konfiguriert. Wer bereits die erforderliche kommerzielle Herstellerlizenz besitzt, kann vor dem Start `STREAMERMOD_MXPARSER_LICENSE_MODE=commercial` setzen. Diese Einstellung kauft oder erteilt keine Lizenz.
