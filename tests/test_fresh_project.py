import json,tempfile,unittest
from pathlib import Path
from sorgobot.next_desktop import initialize
from sorgobot.catalog import ConfigStore,PROMPTS
from sorgobot.fresh_project import documents
class Fresh(unittest.TestCase):
 def test_initialize_never_inherits_source_accounts_or_private_prompts(self):
  with tempfile.TemporaryDirectory() as folder:
   source=Path(folder)/'source';(source/'config').mkdir(parents=True)
   (source/'config/local.json').write_text(json.dumps({'twitch_token':'private-sentinel','channel':'private-owner'}));(source/'config/prompts.json').write_text(json.dumps({'behavior':'private-owner'}))
   target=Path(folder)/'fresh';initialize(target,source);store=ConfigStore(target);self.assertEqual(store.read('local.json')['twitch_token'],'');self.assertFalse(store.read('local.json')['obs_enabled']);self.assertNotIn('private-owner',json.dumps(store.read('prompts.json')));self.assertEqual(store.read('actions.json')['actions'],[])
   own=store.read('local.json');own['channel']='own-channel';store.save('local.json',own);initialize(target,source);self.assertEqual(store.read('local.json')['channel'],'own-channel')
 def test_fresh_defaults_have_no_account_and_neutral_prompts(self):
  d=documents();self.assertFalse(d['youtube.json']['autoConnect']);self.assertEqual(len(d['prompts.json']),11)
  for key in ('twitch_token','twitch_refresh_token','twitch_bot_token','twitch_bot_refresh_token','obs_password','broadcaster_id','bot_id','llm_key','openai_key'):self.assertEqual(d['local.json'][key],'')
  text=json.dumps(d).lower();self.assertNotIn('sorgonas',text);self.assertNotIn('sorgobot',text)
