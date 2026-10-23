# Drittanbieterhinweise: Spracherkennung

Die optionale lokale Spracherkennung verwendet [Vosk](https://github.com/alphacep/vosk-api), Copyright Alpha Cephei Inc., unter Apache License 2.0. Die installierte Python-Distribution enthält ihre Lizenzinformationen. [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

Das Modell `vosk-model-small-de-0.15` stammt von [Alpha Cephei](https://alphacephei.com/vosk/models) und ist dort mit Apache 2.0 ausgewiesen. Das Modell wird separat unter `runtime/speech-models` installiert; die mitgelieferte README bleibt erhalten. Das eigene Manifest dokumentiert Downloadquelle und Prüfsummen. Das optionale englische Modell `vosk-model-small-en-us-0.15` ist ebenfalls dort als Apache 2.0 ausgewiesen.

Diese Hinweise betreffen die eingebundenen Komponenten. Eigener StreamerMod-Code steht unter GPL-3.0; diese Lizenz ersetzt nicht die jeweiligen Drittanbieterbedingungen. Die heruntergeladenen Modelle enthalten ihre Herstellerhinweise.


Die zusätzliche lokale Whisper-Erkennung nutzt [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT), CTranslate2 und die separat heruntergeladenen, zu CTranslate2 konvertierten [Whisper Base](https://huggingface.co/Systran/faster-whisper-base) / [Small](https://huggingface.co/Systran/faster-whisper-small) von Systran. Diese Modellkarten weisen MIT aus; Originalmodell und Lizenz: [OpenAI Whisper](https://github.com/openai/whisper). Beide lokal eingerichteten Modellordner enthalten die Original-MIT-Lizenztexte für Whisper und faster-whisper sowie die unveränderte Modell-README. Die Zuordnung von Bezugsquelle, festem Commit und Modell-SHA256 liegt jeweils im Manifest.

Für die Trennung von Sprache und Pausen wird [webrtcvad-wheels](https://github.com/daanzu/py-webrtcvad-wheels) verwendet; Lizenzangaben für Wrapper und WebRTC sind in der installierten Distribution enthalten. Audiodaten bleiben bei der lokalen Verarbeitung auf dem Rechner.
