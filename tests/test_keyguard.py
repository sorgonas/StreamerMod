import asyncio,importlib.util,math,tempfile,unittest,uuid,struct
from pathlib import Path
from unittest.mock import AsyncMock,patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('keyguard',ROOT/'scripts/streamermod-keyguard.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class Guard(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):self.clock=100.;self.apply=AsyncMock();self.guard=module.Guard(self.apply,clock=lambda:self.clock);self.owner=str(uuid.uuid4())
 async def request(self,**values):return await self.guard.request({'owner':self.owner,**values})
 async def test_one_key_expires_and_overlaps_do_not_unlock_early(self):
  await self.request(op='lock',key='a',seconds=5);await self.request(op='lock',key='a',seconds=10)
  self.assertEqual(self.apply.await_count,1);self.clock=106;await self.guard.tick();self.assertEqual(self.guard.active,{'a'})
  self.clock=111;await self.guard.tick();self.assertEqual(self.guard.active,set());self.apply.assert_awaited_with(set())
 async def test_other_letters_and_other_owner_are_preserved(self):
  await self.request(op='lock',key='a',seconds=10)
  other=str(uuid.uuid4());await self.guard.request({'owner':other,'op':'lock','key':'b','seconds':20})
  await self.request(op='release');self.assertEqual(self.guard.active,{'b'})
  self.assertEqual((await self.request(op='status'))['active'],[])
 async def test_rejects_arbitrary_shortcuts_invalid_names_and_durations(self):
  for key in ['A','abc','ctrl+a','escape',';','',None]:
   with self.assertRaises(ValueError):await self.request(op='lock',key=key,seconds=10)
  for duration in [0,-1,601,True,float('nan'),float('inf'),'10']:
   with self.assertRaises(ValueError):await self.request(op='lock',key='a',seconds=duration)
  self.apply.assert_not_awaited()
 async def test_failed_binding_resets_before_returning_error(self):
  self.apply.side_effect=[RuntimeError('failed'),None]
  with self.assertRaises(RuntimeError):await self.request(op='lock',key='a',seconds=5)
  self.assertEqual(self.guard.leases,{});self.assertEqual(self.guard.active,set());self.assertEqual(self.apply.await_args_list[-1].args,(set(),))
 async def test_manual_release_and_service_shutdown_restore_baseline(self):
  lease=await self.request(op='lock',key='z',seconds=5);await self.request(op='release',leaseId=lease['leaseId']);self.assertFalse(self.guard.active)
  await self.request(op='lock',key='b',seconds=5);await self.guard.close();self.apply.assert_awaited_with(set())
 def test_only_key_up_on_identified_virtual_device(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);device=root/'sys/event1/device';(device/'id').mkdir(parents=True);(device/'name').write_text('keyd virtual keyboard');(device/'id/vendor').write_text('0fac');(root/'dev').mkdir();target=root/'dev/event1';target.write_bytes(b'')
   module.release_output_keys({'a'},root/'sys',root/'dev');raw=target.read_bytes();size=struct.calcsize('@llHHi')
   self.assertEqual(struct.unpack('@llHHi',raw[:size])[-3:],(1,30,0));self.assertEqual(struct.unpack('@llHHi',raw[size:])[-3:],(0,0,0))
