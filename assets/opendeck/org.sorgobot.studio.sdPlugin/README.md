# StreamerMod für OpenDeck 1.1.0

OpenDeck separat installieren und starten. Das eigene Plugin über **Stream Apps → Stream Deck / OpenDeck → StreamerMod-Plugin einrichten / aktualisieren** einrichten. OpenDeck danach einmal neu starten. Kategorie **StreamerMod**, bestehende Action-UUIDs bleiben erhalten.

Action Button, Action Switch, Status Indicator oder Action Dial belegen; eigene Button-ID und gewünschte Actions im Einstellungsbereich auswählen. Der Pluginprozess verbindet sich automatisch neu, auch wenn StreamerMod später gestartet oder neu gestartet wird. OpenDeck läuft beim Schließen von StreamerMod weiter.

**Sub-Actions → StreamerMod → Decks** enthält zehn ausführbare Funktionen: Notify, Background, Icon, State, Title, Value, Toggle State, Page Next/Previous/Set. Die sieben vorhandenen Elgato-Unteraktionen und neun Eingabetrigger bleiben ebenfalls erhalten. Profile entsprechen Seiten. Items sind sichtbare eigene Pluginbelegungen; andere Plugins werden nicht verändert. Das Plugin bestätigt die SDK-Übergabe, nicht die physische Sichtprüfung. Zustände 0/1 gelten für Tasten; Regler verwenden Feedback. Wertoperationen +=, -=, *=, /= werden geprüft.

Private lokale Verbindung auf Port 8059, ausschließlich Loopback; Schlüssel wird bei StreamerMod-Neustart erneuert. Beide Programme unter demselben Benutzer ausführen. Der eigene Renderer nutzt getrennte Hintergrund-/Iconebenen, stellt Anzeigen nach Benachrichtigungen wieder her und hält Profildaten während der Laufzeit in einem begrenzten Cache. Bilder/Downloads maximal 2 MB. Iconify-Namen benötigen Internetzugriff; eigene lokale Bilder nicht.

Remote ist unabhängig vom Deck-Plugin unter **Integrations → StreamerMod Remote** eingerichtet: direkte Instanzen mit dauerhaftem privatem Schlüssel, keine Streamer.bot-Webseitenanmeldung. Vollständige Bedienung und Grenzen: `FORTSETZUNG-DECKS-REMOTE-2026-10-22.md` im Projekt.

Die mitgelieferte WebSocket-Bibliothek ws steht unter MIT; siehe vendor/ws/LICENSE und vendor/DEPENDENCIES.json.
