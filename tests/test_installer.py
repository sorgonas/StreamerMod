import hashlib,importlib.util,io,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('install_user',ROOT/'scripts/install-user.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
class Installer(unittest.TestCase):
 def test_default_plan_includes_keyguard_and_full_python_stack_without_writes(self):
  with tempfile.TemporaryDirectory() as tmp:
   prefix=Path(tmp)/'Not Created'
   r=subprocess.run(['bash',str(ROOT/'install.sh'),'--dry-run','--prefix',str(prefix)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr);self.assertFalse(prefix.exists());self.assertIn('Timed letter service: 1',r.stdout);self.assertIn('desktop,voice,keyboard,camera,youtube',r.stdout);self.assertIn('Whisper Base model: 1',r.stdout)
 def test_optional_components_and_spaces_in_prefix_are_preserved(self):
  r=subprocess.run(['bash',str(ROOT/'install.sh'),'--dry-run','--prefix','/tmp/With Spaces','--without-keyguard','--without-dotnet','--without-models','--with-opendeck'],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr);self.assertIn('/tmp/With Spaces',r.stdout);self.assertIn('OpenDeck: 1',r.stdout);self.assertIn('Timed letter service: 0',r.stdout)
 def test_unknown_or_missing_options_fail_before_installation(self):
  for flags in (['--unknown'],['--prefix']):
   r=subprocess.run(['bash',str(ROOT/'install.sh'),*flags],capture_output=True,text=True);self.assertNotEqual(r.returncode,0)
 def test_deployment_never_copies_source_accounts_or_replaces_existing_user_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source';target=Path(tmp)/'target'
   for p in (source/'sorgobot',source/'assets/opendeck',source/'config',target/'next-studio/config'):p.mkdir(parents=True)
   (source/'sorgobot/__init__.py').write_text('');(source/'config/local.json').write_text('PRIVATE-SOURCE-SENTINEL');own=target/'next-studio/config/local.json';own.write_text('OWN-TARGET-SENTINEL')
   installer.deploy(source,target);self.assertEqual(own.read_text(),'OWN-TARGET-SENTINEL');self.assertFalse((target/'config/local.json').exists())
 def test_desktop_entry_and_launcher_use_the_chosen_path(self):
  with tempfile.TemporaryDirectory() as tmp:
   home=Path(tmp)/'home';target=Path(tmp)/'App 100%';(target/'sorgobot/resources').mkdir(parents=True);(target/'sorgobot/resources/StreamerMod.png').write_bytes(b'icon')
   with patch.dict(os.environ,{'XDG_DATA_HOME':str(home/'.local/share')},clear=False):installer.shortcuts(target,home)
   desktop=(home/'.local/share/applications/streamermod.desktop').read_text();self.assertIn('App 100%%/StreamerMod',desktop);self.assertIn('App 100%/StreamerMod',(home/'.local/bin/streamermod').read_text())
 def test_download_checksum_failure_is_fatal(self):
  with tempfile.TemporaryDirectory() as tmp,patch('urllib.request.urlopen',return_value=io.BytesIO(b'data')):
   with self.assertRaisesRegex(ValueError,'checksum'):installer.fetch('https://official.example/file',Path(tmp)/'file','0'*128)
 def test_download_accepts_matching_sha512(self):
  with tempfile.TemporaryDirectory() as tmp,patch('urllib.request.urlopen',return_value=io.BytesIO(b'data')):
   target=Path(tmp)/'file';installer.fetch('https://official.example/file',target,hashlib.sha512(b'data').hexdigest());self.assertEqual(target.read_bytes(),b'data')
 def test_root_and_home_are_not_application_directories(self):
  with self.assertRaises(ValueError):installer.deploy(ROOT,Path('/'))
  with self.assertRaises(ValueError):installer.deploy(ROOT,Path.home())
if __name__=='__main__':unittest.main()
