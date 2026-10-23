import json,unittest
from unittest.mock import AsyncMock
from types import SimpleNamespace
from sorgobot.ai_action import generate
class Context(unittest.IsolatedAsyncioTestCase):
 async def test_event_and_target_info_are_passed_without_manual_context_or_provider(self):
  c=SimpleNamespace(llm=AsyncMock(return_value='Antwort'));args={'user':'Raider','viewers':7,'targetGame':'Golf','targetChannelTitle':'Letzter Titel','targetDescription':'Beschreibung','twitch_token':'private'}
  result=await generate(c,{'autoContext':True,'promptKind':'raid','limit':12,'provider':'openai','prompt':'obsolete'},args,lambda x:x)
  self.assertEqual(result,'Antwort');call=c.llm.call_args;data=json.loads(call.args[1]);self.assertEqual(data['viewers'],7);self.assertEqual(data['targetGame'],'Golf');self.assertEqual(data['targetChannelTitle'],'Letzter Titel');self.assertEqual(data['targetChannelDescription'],'Beschreibung');self.assertNotIn('twitch_token',data);self.assertNotIn('provider',call.kwargs);self.assertEqual(call.kwargs['prompt_kind'],'raid')
 async def test_custom_instructions_stay_separate_from_event_data(self):
  c=SimpleNamespace(llm=AsyncMock(return_value='Text'));await generate(c,{'autoContext':True,'promptKind':'__custom__','prompt':'Eigene Regeln'}, {'user':'Name'},lambda x:x)
  self.assertEqual(c.llm.call_args.kwargs['custom_instructions'],'Eigene Regeln');self.assertEqual(json.loads(c.llm.call_args.args[1]),{'user':'Name'})
 async def test_legacy_action_keeps_explicit_request_and_provider(self):
  c=SimpleNamespace(llm=AsyncMock(return_value='Text'));await generate(c,{'type':90008,'prompt':'Alt','limit':123}, {},lambda x:x)
  self.assertEqual(c.llm.call_args.args[1],'Alt');self.assertEqual(c.llm.call_args.kwargs['provider'],'openai');self.assertEqual(c.llm.call_args.kwargs['limit'],123)

 async def test_user_lookup_exposes_exact_description_alias_and_event_count(self):
  from pathlib import Path
  from sorgobot.adapters import IO
  from sorgobot.core import expand
  io=IO(Path('.'),{},None,False)
  io.user=AsyncMock(return_value={'id':'42','login':'raider','display_name':'Raider','profile_image_url':'','description':'Kanalbeschreibung'})
  io.twitch=AsyncMock(return_value={'data':[{'game_name':'Golf','title':'Letzter Streamtitel','tags':[]}]})
  args={'viewers':17};await io.step(50,{'type':50,'userLogin':'raider'},args)
  self.assertEqual(expand('%viewers% | %targetChannelTitle% | %targetChannelDescription% | %targetGame%',args),'17 | Letzter Streamtitel | Kanalbeschreibung | Golf')
  self.assertEqual(args['targetDescription'],args['targetChannelDescription'])
  c=SimpleNamespace(llm=AsyncMock(return_value='Text'));await generate(c,{'autoContext':True,'promptKind':'raid'},args,lambda x:expand(x,args));payload=json.loads(c.llm.call_args.args[1]);self.assertEqual(payload['targetChannelDescription'],'Kanalbeschreibung');self.assertEqual(payload['viewers'],17)
