"""Project-data maintenance with a stopped runtime and verified restore preview."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QThread,Signal,Qt,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QFileDialog,QMessageBox,QApplication
from . import project_backup as backup

class Job(QThread):
 done=Signal(object);failed=Signal(str)
 def __init__(self,callback,parent):super().__init__(parent);self.callback=callback
 def run(self):
  try:self.done.emit(self.callback())
  except Exception as exc:self.failed.emit(str(exc) if isinstance(exc,(backup.BackupError,OSError)) else 'Projektoperation fehlgeschlagen: '+type(exc).__name__)

class BackupDialog(QDialog):
 def __init__(self,host):
  super().__init__(host);self.host=host;self.setWindowTitle('Projekt sichern / wiederherstellen');self.resize(640,360)
  self.setWindowModality(Qt.WindowModality.ApplicationModal);self.busy=False;self.paused=False;self.jobs=[]
  layout=QVBoxLayout(self)
  label=QLabel('Enthalten: gespeicherte Studio-Konfiguration einschließlich Kontozugängen, persistente Datenbanken, Projektmedien und zusätzliche C#-Bibliotheken.\n\nNicht enthalten: separat verwaltete OBS-/OpenDeck-Profile, installierte Programme und Dateien außerhalb des Projekts. Externe Dateiverweise werden gemeldet.\n\nFür Sicherung und Wiederherstellung wird die Studio-Engine vorübergehend angehalten; laufende und wartende Actions werden beendet. Währenddessen verarbeitet sie keine neuen Ereignisse. Ein Backup enthält private Zugangsdaten und ist nicht verschlüsselt.')
  label.setWordWrap(True);layout.addWidget(label)
  self.message=QLabel('Bereit.');self.message.setWordWrap(True);self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(self.message)
  self.create_button=QPushButton('Projektbackup erstellen …');self.create_button.clicked.connect(self.create);layout.addWidget(self.create_button)
  self.inspect_button=QPushButton('Backup prüfen …');self.inspect_button.clicked.connect(self.inspect);layout.addWidget(self.inspect_button)
  self.restore_button=QPushButton('Backup wiederherstellen …');self.restore_button.clicked.connect(self.restore);layout.addWidget(self.restore_button)
  self.close_button=QPushButton('Schließen');self.close_button.clicked.connect(self.reject);layout.addWidget(self.close_button)
 def set_busy(self,value):
  self.busy=value
  for widget in (self.create_button,self.inspect_button,self.restore_button,self.close_button):widget.setEnabled(not value)
 def start(self,callback,complete):
  self.set_busy(True);job=Job(callback,self);self.jobs.append(job)
  def success(result):job.wait();complete(result)
  def failure(message):job.wait();self.failed(message)
  job.done.connect(success);job.failed.connect(failure);job.finished.connect(lambda:self.jobs.remove(job));job.finished.connect(job.deleteLater);job.start()
 def pause(self):
  self.host.poll.stop()
  if not self.host.runtime.stop():
   self.paused=True;self.set_busy(True);self.message.setText('Die Engine räumt noch auf. Der Vorgang wurde nicht gestartet; danach wird die Engine wieder aktiviert.')
   runtime=self.host.runtime
   def finished():
    runtime.finished.disconnect(finished);self.resume();self.set_busy(False)
   runtime.finished.connect(finished)
   if not runtime.isRunning():QTimer.singleShot(0,finished)
   return False
  self.paused=True;return True
 def resume(self):
  if self.paused:
   self.host.runtime.deleteLater();self.host.start_runtime();self.paused=False
 def failed(self,message):
  self.resume();self.set_busy(False);self.message.setText('Nicht abgeschlossen: '+message)
 def choose(self):return QFileDialog.getOpenFileName(self,'Projektbackup auswählen',str(self.host.root/'state/project-backups'),'Studio-Projektbackup (*.slbackup);;Alle Dateien (*)')[0]
 @staticmethod
 def describe(result):
  text=f"Erstellt: {result['created']}\n{result['actions']} Actions · {result['commands']} Commands · {result['timers']} Timer\n{result['databases']} Datenbanken · {result['files']} Dateien · {result['bytes']/1024**2:.1f} MiB unkomprimiert"
  if result.get('externalReferences'):text+='\nNicht eingebettete externe Dateien:\n'+'\n'.join(result['externalReferences'][:20])
  return text
 def inspect(self):
  path=self.choose()
  if not path:return
  self.message.setText('Prüfe Archiv, Prüfsummen, Konfiguration und Datenbanken …')
  self.start(lambda:backup.inspect(path),self.inspected)
 def inspected(self,result):self.set_busy(False);self.message.setText('Backupprüfung erfolgreich.\n'+self.describe(result))
 def create(self):
  default=self.host.root/'state/project-backups'/('studio-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.slbackup')
  path=QFileDialog.getSaveFileName(self,'Neues Projektbackup',str(default),'Studio-Projektbackup (*.slbackup)')[0]
  if not path:return
  if not path.endswith('.slbackup'):path+='.slbackup'
  if not self.pause():return
  self.message.setText('Sichere Projekt und prüfe das fertige Archiv …')
  self.start(lambda:backup.create(self.host.root,path,quiesced=True),self.created)
 def created(self,result):
  self.resume();self.set_busy(False);self.message.setText('Backup vollständig erstellt und geprüft:\n'+result['path']+'\n'+self.describe(result))
 def restore(self):
  path=self.choose()
  if not path:return
  self.message.setText('Prüfe das ausgewählte Backup vor der Wiederherstellung …')
  self.start(lambda:backup.inspect(path),lambda result:self.confirm_restore(path,result))
 def confirm_restore(self,path,result):
  self.set_busy(False)
  message=self.describe(result)+'\n\nDie aktuellen Projektdaten werden ersetzt. Vorher wird automatisch ein separates Rettungsbackup erstellt. Die Engine wird angehalten und die Anwendung anschließend neu gestartet. Externe OBS-/OpenDeck-Profile bleiben unberührt. Dateipfade werden unverändert übernommen; bei einem anderen Projektordner müssen absolute Pfade angepasst werden. Fortfahren?'
  if QMessageBox.question(self,'Geprüftes Projektbackup wiederherstellen',message,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
  if not self.pause():return
  self.message.setText('Erstelle Rettungsbackup und stelle das Projekt wieder her …')
  self.start(lambda:backup.restore(self.host.root,path,quiesced=True),self.restored)
 def restored(self,result):
  self.set_busy(False);self.paused=False
  QMessageBox.information(self,'Wiederherstellung abgeschlossen','Geprüftes Backup wiederhergestellt. Rettungsbackup:\n'+result['rescue']+'\nDie Anwendung startet jetzt neu.')
  QApplication.instance().exit(42)
 def reject(self):
  if not self.busy:super().reject()
 def closeEvent(self,event):
  if self.busy:event.ignore()
  else:super().closeEvent(event)
