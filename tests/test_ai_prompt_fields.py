import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QDialog
from sorgobot.catalog import ConfigStore,new_step
from sorgobot.desktop import FieldsDialog,MainWindow
import sorgobot.next_catalog
class PromptFields(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_saved_prompt_selection_preserves_id_and_uses_central_provider(self):
  with tempfile.TemporaryDirectory() as folder:
   (Path(folder)/'config').mkdir()
   host=QWidget();host.store=ConfigStore(Path(folder));host.store.save('local.json',{'ai_provider':'local','llm_model':'installed-model'});host.store.save('prompts.json',{'chat':'CHAT','stream_raid':'RAID','my_prompt':'CUSTOM'})
   d=FieldsDialog('KI',new_step(90004),host);box=d.controls['promptKind'][0];self.assertGreaterEqual(box.findData('my_prompt'),0);box.setCurrentIndex(box.findData('my_prompt'));d.accept()
   self.assertEqual(d.result(),QDialog.DialogCode.Accepted);self.assertEqual(d.value['promptKind'],'my_prompt');self.assertNotIn('provider',d.value);self.assertNotIn('limit',d.value);self.assertNotIn('provider',d.controls);self.assertNotIn('limit',d.controls);self.assertNotIn('llm_model',d.value)
   reopened=FieldsDialog('KI',d.value,host);self.assertEqual(reopened.controls['promptKind'][0].currentData(),'my_prompt');host.deleteLater()
 def test_missing_prompt_survives_and_obsolete_provider_override_is_removed(self):
  host=QWidget();node=new_step(90004);node.update(promptKind='missing-template',provider='openai');d=FieldsDialog('KI',node,host);self.assertIn('nicht gespeichert',d.controls['promptKind'][0].currentText());d.accept();self.assertEqual(d.value['promptKind'],'missing-template');self.assertNotIn('provider',d.value);host.deleteLater()
 def test_central_editor_displays_and_preserves_custom_prompts(self):
  with tempfile.TemporaryDirectory() as folder:
   (Path(folder)/'config').mkdir()
   host=QWidget();host.store=ConfigStore(Path(folder));host.store.save('local.json',{'ai_provider':'local'});host.store.save('prompts.json',{'chat':'CHAT','custom':'OWN'});host.page=lambda _:QVBoxLayout(host);host.save_ai=lambda:None;host.runtime=Mock();host.statusBar=lambda:Mock()
   MainWindow.make_ai(host);self.assertIn('custom',host.prompt_fields);host.prompt_fields['custom'].setPlainText('EDITED');MainWindow.save_ai(host);self.assertEqual(host.store.read('prompts.json')['custom'],'EDITED');host.deleteLater()

 def test_only_custom_mode_exposes_an_editable_prompt(self):
  host=QWidget();d=FieldsDialog('KI',new_step(90004),host);d.show();self.app.processEvents();box=d.controls['promptKind'][0];text=d.controls['prompt'][0];self.assertTrue(text.isHidden());box.setCurrentIndex(box.findData('__custom__'));self.assertFalse(text.isHidden());text.setPlainText('Mein Auftrag');d.accept();self.assertEqual(d.value['prompt'],'Mein Auftrag');self.assertTrue(d.value['autoContext']);host.deleteLater()

 def test_opening_an_old_free_text_action_keeps_its_custom_prompt(self):
  host=QWidget();node={'type':90004,'prompt':'Eigener alter Auftrag','promptKind':'chat'};d=FieldsDialog('KI',node,host);self.assertEqual(d.controls['promptKind'][0].currentData(),'__custom__');d.accept();self.assertEqual(d.value['prompt'],'Eigener alter Auftrag');host.deleteLater()
