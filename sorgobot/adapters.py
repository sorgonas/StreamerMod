from __future__ import annotations

import asyncio
import contextvars
import copy
import base64
import hashlib
import json
import os
import random
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

from .core import ActionError


def follow_age(start,end):
    from dateutil.relativedelta import relativedelta
    age=relativedelta(max(start,end),start)
    return {'followAge.years':age.years,'followAge.months':age.months,'folowAge.months':age.months,'followAge.days':age.days}


class OBS:
    def __init__(self, session, config, on_event=None):
        self.session, self.config, self.on_event = session, config, on_event
        self.ws = None
        self.pending = {}
        self.ready = asyncio.Event()
        self.status = 'offline'

    def connection_arguments(self):
        return {'obs.id':self.config.get('obs_connection_id','default'),
                'obs.name':self.config.get('obs_connection_name',self.config.get('obs_name','Main OBS')),
                'obs.host':urlsplit(self.config.get('obs_url','ws://127.0.0.1:4455')).hostname or ''}

    async def connected_event(self,metadata):
        try:version=await self.call('GetVersion')
        except (ActionError,aiohttp.ClientError,OSError,TimeoutError):version={}
        metadata=dict(metadata,**{'obs.studioVersion':version.get('obsVersion',''),'obs.websocketVersion':version.get('obsWebSocketVersion','')})
        if self.on_event:
            self.on_event('OBSConnected',metadata);self.connected_notified=True

    async def listen(self):
        while True:
            connected_task=None;was_connected=False;metadata=self.connection_arguments();self.connected_notified=False
            try:
                async with self.session.ws_connect(self.config.get('obs_url', 'ws://127.0.0.1:4455'), heartbeat=20) as ws:
                    self.ws = ws
                    hello = (await ws.receive_json())['d']
                    identify = {'rpcVersion': 1, 'eventSubscriptions': (1 << 12) - 1}
                    if 'authentication' in hello:
                        auth = hello['authentication']
                        secret = base64.b64encode(hashlib.sha256((self.config.get('obs_password', '') + auth['salt']).encode()).digest()).decode()
                        identify['authentication'] = base64.b64encode(hashlib.sha256((secret + auth['challenge']).encode()).digest()).decode()
                    await ws.send_json({'op': 1, 'd': identify})
                    identified = await ws.receive_json()
                    if identified.get('op') != 2:
                        raise ActionError('OBS-Anmeldung fehlgeschlagen')
                    self.ready.set()
                    self.status = 'connected';was_connected=True
                    if self.on_event:connected_task=asyncio.create_task(self.connected_event(metadata))
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        data = msg.json()
                        d = data.get('d', {})
                        if data['op'] in (7,9):
                            future = self.pending.get(d['requestId'])
                            if future and not future.done():
                                future.set_result(d)
                        elif data['op'] == 5 and self.on_event:
                            self.on_event(d['eventType'], d.get('eventData', {}))
            except (aiohttp.ClientError, OSError, ValueError, ActionError):
                self.status = 'offline / Verbindung prüfen'
            finally:
                self.ready.clear()
                for future in self.pending.values():
                    if not future.done():
                        future.set_exception(ActionError('OBS-Verbindung unterbrochen'))
                if connected_task:
                    if not connected_task.done():
                        connected_task.cancel()
                        await asyncio.gather(connected_task,return_exceptions=True)
                    else:await asyncio.gather(connected_task,return_exceptions=True)
                self.ws=None
                if was_connected and self.on_event:
                    if not self.connected_notified:self.on_event('OBSConnected',dict(metadata,**{'obs.studioVersion':'','obs.websocketVersion':''}))
                    self.on_event('OBSDisconnected',metadata)
            if not self.config.get('obs_reconnect',True):break
            await asyncio.sleep(max(1,float(self.config.get('obs_retry_interval',5))))

    async def call(self, request, **data):
        try:
            await asyncio.wait_for(self.ready.wait(), 5)
        except TimeoutError:
            raise ActionError('OBS ist nicht verbunden') from None
        identity = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending[identity] = future
        try:
            await self.ws.send_json({'op': 6, 'd': {'requestType': request, 'requestId': identity, 'requestData': data}})
            result = await asyncio.wait_for(future, 10)
            if not result['requestStatus']['result']:
                raise ActionError(f"OBS {request} ({result['requestStatus'].get('code', '?')}): {result['requestStatus'].get('comment', 'Fehler')}")
            return result.get('responseData', {})
        finally:
            self.pending.pop(identity, None)

    async def batch(self,requests,halt=False,execution=0):
        try:await asyncio.wait_for(self.ready.wait(),5)
        except TimeoutError:raise ActionError('OBS ist nicht verbunden') from None
        identity=uuid.uuid4().hex;future=asyncio.get_running_loop().create_future();self.pending[identity]=future
        try:
            await self.ws.send_json({'op':8,'d':{'requestId':identity,'haltOnFailure':halt,'executionType':execution,'requests':requests}})
            result=await asyncio.wait_for(future,30)
            return result
        finally:self.pending.pop(identity,None)


class IO:
    def __init__(self, root, config, session, dry_run=True, obs_test=False):
        self.root, self.config, self.session, self.dry_run = Path(root), config, session, dry_run
        self.obs_test = obs_test
        self.obs = OBS(session, config)
        from .obs_connections import OBSConnections
        self.obs_pool=OBSConnections(self,self.obs)
        self.obs_context=contextvars.ContextVar('obs_target',default=None)
        self.effects = []
        self.audio_locks = {}

    def trace(self, kind, **data):
        self.effects.append({'kind': kind, **data})
        self.effects[:] = self.effects[-300:]
        if getattr(self,'diagnostics',None) and (kind=='log' or kind.endswith('_error')):
            self.diagnostics.write(kind,level=data.get('level'),message=data.get('text',data.get('message',data.get('error',''))))

    def path(self, raw):
        raw = re.sub(r'\\+', '/', str(raw))
        if raw.lower().startswith('e:/streaming/'):
            raw = raw[len('e:/streaming/'):]
        p = Path(raw)
        if p.is_absolute():
            result = p.resolve()
        else:
            if re.match(r'^[a-zA-Z]:', raw):
                raise ActionError('Nicht zugeordneter Windows-Pfad')
            result = (self.root / 'assets' / p).resolve()
        # Imported paths and event values cannot escape the copied media directory.
        if not result.is_relative_to((self.root / 'assets').resolve()):
            raise ActionError('Medienpfad liegt außerhalb von assets')
        return result

    async def wait(self, seconds):
        if self.dry_run:
            self.trace('wait', seconds=seconds)
        else:
            await asyncio.sleep(max(0, seconds))

    async def obs_call(self, request, **data):
        self.trace('obs', request=request, data=data)
        if self.obs_test and request not in {
            'GetSceneList', 'GetCurrentProgramScene', 'GetSourceScreenshot',
            'GetSceneItemId', 'GetSceneItemEnabled', 'GetInputSettings',
            'GetStreamStatus', 'GetRecordStatus', 'SetCurrentProgramScene',
            'SetSceneItemEnabled', 'SetInputSettings', 'TriggerMediaInputAction',
            'GetMediaInputStatus', 'SetInputMute', 'GetInputMute',
            'GetReplayBufferStatus', 'GetSceneItemList', 'GetSceneItemTransform',
            'SetSceneItemTransform', 'GetSourceFilter', 'SetSourceFilterEnabled', 'SetInputVolume',
        }:
            raise ActionError('Dieser OBS-Befehl ist im OBS-Testmodus gesperrt')
        if self.dry_run and not self.obs_test:
            return {'sceneItemId': 1, 'currentProgramSceneName': 'Gaming - Live', 'outputActive': False,
                    'inputSettings': {}, 'sceneItemEnabled': False, 'inputMuted': False,
                    'filterEnabled': False, 'sceneItems': [],
                    'sceneItemTransform': {'rotation':0.0,'scaleX':1.0,'scaleY':1.0}}
        identity=self.obs_context.get()
        client=self.obs_pool.get() if identity is None else self.obs_pool.clients[identity]
        return await client.call(request, **data)

    async def obs_batch(self,requests,halt=False,execution=0):
        self.trace('obs_batch',requests=requests,haltOnFailure=halt,executionType=execution)
        if self.obs_test:raise ActionError('OBS-Batches sind im OBS-Testmodus gesperrt')
        if self.dry_run:return {'results':[],'simulated':True}
        identity=self.obs_context.get();client=self.obs_pool.get() if identity is None else self.obs_pool.clients[identity]
        return await client.batch(requests,halt,execution)

    async def settings(self, source, settings):
        return await self.obs_call('SetInputSettings', inputName=source, inputSettings=settings, overlay=True)

    async def visible(self, scene, source, state):
        source = self.config.get('source_aliases', {}).get(source, source)
        item = await self.obs_call('GetSceneItemId', sceneName=scene, sourceName=source)
        return await self.obs_call('SetSceneItemEnabled', sceneName=scene, sceneItemId=item['sceneItemId'], sceneItemEnabled=state)

    async def http(self, method, url, *, headers=None, body=None, params=None):
        try:
            async with self.session.request(method, url, headers=headers, json=body, params=params,
                                            timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status >= 400:
                    # Never include URLs (webhook secrets) or response bodies in logs.
                    raise ActionError(f'HTTP {response.status}: Zugang oder Dienst prüfen')
                if response.status == 204:
                    return {}
                return await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError):
            raise ActionError('Netzwerkverbindung fehlgeschlagen') from None

    async def twitch(self, method, endpoint, body=None, params=None, bot=False):
        token = self.config.get('twitch_bot_token' if bot else 'twitch_token', '')
        if not token or not self.config.get('twitch_client_id'):
            raise ActionError('Twitch-Zugang fehlt in config/local.json')
        return await self.http(method, 'https://api.twitch.tv/helix/' + endpoint,
                               headers={'Authorization': 'Bearer ' + token, 'Client-Id': self.config['twitch_client_id']},
                               body=body, params=params)

    async def send(self, text, bot=True):
        bot=bool(bot and self.config.get('twitch_bot_token') and self.config.get('bot_id'))
        text = ' '.join(str(text).replace('\\r\\n', ' ').split())[:500]
        if not text.strip():raise ActionError('Chatnachricht ist leer. Prüfe den Text und seine Variablen; ein gelöschter C#-Schritt erzeugt keine Ergebnisvariable mehr.')
        self.trace('chat', text=text, bot=bot)
        if self.dry_run:
            return
        if text.lower().startswith('/shoutout'):
            raise ActionError('Shoutout braucht einen Zielkanal')
        if text.startswith('/me '):
            text = text[4:]
        result = await self.twitch('POST', 'chat/messages', {
            'broadcaster_id': self.config['broadcaster_id'],
            'sender_id': self.config.get('bot_id') if bot else self.config['broadcaster_id'],
            'message': text}, bot=bot)
        if not result.get('data', [{}])[0].get('is_sent'):
            raise ActionError('Twitch hat die Chatnachricht nicht gesendet')

    async def user(self, login):
        login = str(login).lstrip('@').lower()
        if not re.fullmatch(r'[a-z0-9_]{1,25}', login):
            raise ActionError('Ungültiger Twitch-Name')
        if self.dry_run:
            return {'id': '123', 'login': login, 'display_name': login, 'profile_image_url': 'https://example.invalid/avatar.png', 'description': ''}
        users = (await self.twitch('GET', 'users', params={'login': login}))['data']
        if not users:
            raise ActionError('Twitch-Nutzer nicht gefunden')
        return users[0]

    async def step(self, t, n, args):
        from .obs_connections import OBS_TYPES
        if t not in OBS_TYPES:return await self._step(t,n,args)
        from .core import expand
        selected=self.obs_pool.targets(expand(n.get('obsConnection','default'),args))
        original=copy.deepcopy(args);results={}
        try:
            for identity in selected:
                target=args if len(selected)==1 else copy.deepcopy(original)
                token=self.obs_context.set(identity)
                try:
                    await self._step(t,n,target)
                    if len(selected)>1:results[identity]={k:copy.deepcopy(v) for k,v in target.items() if k not in original or original[k]!=v}
                    args.update(target)
                finally:self.obs_context.reset(token)
        finally:
            if len(selected)>1:args['obsConnectionResults']=results

    async def _step(self, t, n, args):
        if t==96005:
            from .multichat import operation
            return await operation(self,n,args)
        if t in (96017,96018):
            from .youtube_extras import operation
            return await operation(self,n,args)
        if 96013<=t<=96016:
            from .youtube_users import operation
            return await operation(self,n,args)
        if 96000<=t<=96004 or t in (96010,96011,96012):
            from .youtube import operation
            return await operation(self,n,args)
        if 95000<=t<=95003:
            from .standard_settings import operation
            return await operation(self,n,args)
        if 94000<=t<=94005:
            from .linux_audio import operation
            return await operation(self,n,args)
        if t in (97400,97401,97500,97501):
            from .timed_effects import operation
            return await operation(self,n,args)
        if t==97300:
            from .discord_webhooks import operation
            return await operation(self,n,args)
        if 97100<=t<=97109:
            from .streamermod_decks import operation
            return await operation(self,n,args)
        if 97200<=t<=97202:
            from .streamermod_remote import operation
            return await operation(self,n,args)
        if 93000<=t<=93006:
            from .streamdeck_bridge import operation
            return await operation(self,n,args)
        if 92100<=t<=92111:
            from .twitch_guest_star import operation
            return await operation(self,n,args)
        if 92000<=t<=92003:
            from .twitch_queries import operation
            return await operation(self,n,args)
        if 91900<=t<=91904:
            from .twitch_moderation_extended import operation
            return await operation(self,n,args)
        if 91800<=t<=91806:
            from .twitch_chat_actions import operation
            return await operation(self,n,args)
        if t in (91600,91601):
            from .twitch_user_info import operation
            return await operation(self,n,args)
        if 91400<=t<=91403:
            from .twitch_chat_modes import operation
            return await operation(self,n,args)
        if 91300<=t<=91305:
            from .twitch_channel_tools import operation
            return await operation(self,n,args)
        if t in (91200,91201,91202):
            from .twitch_channel import operation
            return await operation(self,n,args)
        if t in (91100,91101,91102):
            from .twitch_sub_counter import operation
            return await operation(self,n,args)
        if t==91000:
            from .twitch_hype_train import operation
            return await operation(self,n,args)
        if t in (90900,90901,90902,90903,90910,90911):
            from .twitch_ads_raids import operation
            return await operation(self,n,args)
        if t==90800:
            from .twitch_subscriptions import operation
            return await operation(self,n,args)
        if t==20 or 90700<=t<=90706:
            from .twitch_moderation import operation
            return await operation(self,n,args)
        if 90600<=t<=90615:
            from .twitch_vote_actions import operation
            return await operation(self,n,args)
        if 90500<=t<=90516:
            from .twitch_reward_actions import operation
            return await operation(self,n,args)
        if 90300<=t<=90324:
            from .obs_actions import operation
            await operation(self,n,args)
        elif t == 90005:
            await self.obs_call('SetCurrentProgramScene',sceneName=n['sceneName'])
        elif t in (90002,97000):
            from .core import expand
            def resolve(value):
                if isinstance(value,dict): return {k:resolve(v) for k,v in value.items()}
                if isinstance(value,list): return [resolve(v) for v in value]
                return expand(value,args)
            self.trace('http',method=n['method'])
            args[n.get('resultVariable','httpResult')] = {'preview':True} if self.dry_run else await self.http(
                n['method'],n['url'],headers=resolve(n.get('headers',{})),
                body=resolve(n.get('body')) if n['method'].upper() not in ('GET','HEAD') else None)
        elif t == 90003:
            from .core import expand
            argv=[expand(str(v),args) for v in n.get('arguments',[])]
            self.trace('program',program=n['program'],arguments=argv)
            if not self.dry_run:
                args['programOutput']=await self.process(n['program'],*argv)
        elif t == 10:
            if n['text'].lower().startswith('/shoutout'):
                target = args.get('targetUserId')
                if not target:
                    raise ActionError('Shoutout-Ziel fehlt')
                if self.dry_run:
                    self.trace('shoutout', user=target)
                else:
                    await self.twitch('POST', 'chat/shoutouts', params={'from_broadcaster_id': self.config['broadcaster_id'], 'to_broadcaster_id': target, 'moderator_id': self.config['broadcaster_id']})
            else:
                await self.send(n['text'], n.get('useBot', True))
        elif t in (38, 39, 322, 323):
            field = {38: 'url', 39: 'text', 322: 'local_file', 323: 'file'}[t]
            val = n[{38: 'url', 39: 'text', 322: 'fileName', 323: 'fileName'}[t]]
            if t in (322, 323):
                val = str(self.path(val))
                if not self.dry_run and not Path(val).is_file():
                    raise ActionError('Mediendatei fehlt: ' + str(Path(val).relative_to(self.root)))
            await self.settings(n['sourceName'], {field: val, **({'is_local_file': True} if t == 322 else {})})
        elif t == 30:
            state=n['state']
            if state==2:
                item=await self.obs_call('GetSceneItemId',sceneName=n['sceneName'],sourceName=n['sourceName'])
                current=await self.obs_call('GetSceneItemEnabled',sceneName=n['sceneName'],sceneItemId=item['sceneItemId'])
                await self.obs_call('SetSceneItemEnabled',sceneName=n['sceneName'],sceneItemId=item['sceneItemId'],sceneItemEnabled=not current['sceneItemEnabled'])
            else:await self.visible(n['sceneName'],n['sourceName'],state==0)
        elif t == 48:
            from .core import expand
            args.setdefault('filedatetime',datetime.now().astimezone().isoformat())
            path = self.path(expand(n['path'],args))
            image_format=path.suffix.lower().lstrip('.')
            if image_format not in ('png','jpg','jpeg','bmp','webp'):raise ActionError('Screenshot benötigt png, jpg, jpeg, bmp oder webp als Dateiendung')
            quality=n.get('quality',-1)
            if isinstance(quality,bool) or not str(quality).lstrip('-').isdigit() or not -1<=int(quality)<=100:raise ActionError('Screenshot-Qualität muss -1 bis 100 sein')
            source=n.get('sourceName') or n.get('sceneName')
            if not source:source=(await self.obs_call('GetCurrentProgramScene'))['currentProgramSceneName']
            source=self.config.get('source_aliases',{}).get(source,source)
            args['screenshotFile'] = str(path)
            if self.dry_run:
                self.trace('screenshot', path=str(path))
            else:
                result = await self.obs_call('GetSourceScreenshot', sourceName=source, imageFormat=image_format,imageCompressionQuality=int(quality))
                path.parent.mkdir(parents=True, exist_ok=True)
                try:data=base64.b64decode(result['imageData'].split(',', 1)[1],validate=True)
                except (KeyError,IndexError,ValueError):raise ActionError('OBS hat keine gültigen Screenshot-Daten geliefert') from None
                await asyncio.to_thread(path.write_bytes,data)
        elif t in (50, 51):
            user = await self.user(n['userLogin'])
            args.update(targetUser=user['display_name'], targetUserName=user['login'], targetUserId=user['id'],
                        targetUserProfileImageUrl=user['profile_image_url'], targetDescription=user.get('description', ''), targetChannelDescription=user.get('description', ''))
            if t == 50:
                channel = {'game_name': 'Testspiel', 'title': 'Testtitel', 'tags': []} if self.dry_run else (await self.twitch('GET', 'channels', params={'broadcaster_id': user['id']}))['data'][0]
                args.update(game=channel['game_name'], targetGame=channel['game_name'], targetChannelTitle=channel['title'], tagsDelimited=', '.join(channel.get('tags', [])))
            else:
                followers = [{'followed_at': '2020-01-01T00:00:00Z'}] if self.dry_run else (await self.twitch('GET', 'channels/followers', params={'broadcaster_id': self.config['broadcaster_id'], 'user_id': user['id']}))['data']
                args['isFollowing'] = bool(followers)
                if followers:
                    date = datetime.fromisoformat(followers[0]['followed_at'].replace('Z', '+00:00'))
                    args.update(followDate=date.strftime('%d.%m.%Y'))
                    args.update(follow_age(date,datetime.now(timezone.utc)))
        elif t == 602:
            self.trace('tts', text=n['message'])
            if not self.dry_run:
                await self.process('espeak-ng', '-v', self.config.get('tts_voice', 'de'), '--', n['message'])
        elif t == 7001:
            self.trace('discord', content=n['content'])
            if self.dry_run:
                return
            url = self.config.get('webhooks', {}).get(n['id'])
            if not url:
                raise ActionError('Discord-Webhook fehlt')
            payload = {'content': n['content'], 'username': n.get('username') or 'Sorgobot', 'allowed_mentions': {'parse': []}}
            if n.get('avatar'):
                payload['avatar_url'] = n['avatar']
            if n.get('image'):
                path = self.path(n['image'])
                form = aiohttp.FormData()
                form.add_field('payload_json', json.dumps(payload))
                form.add_field('files[0]', path.read_bytes(), filename=path.name, content_type='image/png')
                async with self.session.post(url, data=form) as response:
                    if response.status >= 400:
                        raise ActionError('Discord-Upload fehlgeschlagen')
            else:
                await self.http('POST', url, body=payload)
        elif t in (15, 16, 17, 18, 20):
            self.trace('twitch', operation=t)
            if self.dry_run:
                if t == 18:
                    args.update(createClipSuccess=True, createClipUrl='https://clips.twitch.tv/Example', clipDuration=33000)
                return
            broadcaster = self.config['broadcaster_id']
            if t == 15:
                await self.twitch('PATCH', 'channels', {'title': n['title']}, {'broadcaster_id': broadcaster})
            elif t == 16:
                games = (await self.twitch('GET', 'games', params={'name': n['game']}))['data']
                if not games:
                    raise ActionError('Twitch-Kategorie nicht gefunden')
                await self.twitch('PATCH', 'channels', {'game_id': games[0]['id']}, {'broadcaster_id': broadcaster})
            elif t == 17:
                await self.twitch('POST', 'streams/markers', {'user_id': broadcaster, 'description': n['description']})
            elif t == 18:
                clip = (await self.twitch('POST', 'clips', params={'broadcaster_id': broadcaster}))['data'][0]
                args['createClipSuccess'] = False
                for _ in range(15):
                    clips = (await self.twitch('GET', 'clips', params={'id': clip['id']}))['data']
                    if clips:
                        args.update(createClipSuccess=True, createClipUrl=clips[0]['url'], clipDuration=clips[0]['duration'] * 1000)
                        break
                    await asyncio.sleep(1)
                if not args['createClipSuccess']:
                    raise ActionError('Clip wurde noch nicht bereitgestellt')
        elif t == 2:
            # Lens IDs alone cannot reproduce proprietary camera effects on Linux.
            raise ActionError('Kamera-Lens benötigt einen portierten Effekt; siehe Migrationsbericht')
        elif t == 3:
            path = self.path(n['file'])
            if not self.dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('a' if n.get('append') else 'w', encoding='utf-8') as f:
                    f.write(n['text'] + '\n')
            self.trace('file', path=str(path))
        else:
            raise ActionError(f'Nicht portierter Subaktionstyp: {t}')

    async def process(self, *argv):
        if not shutil.which(argv[0]):
            raise ActionError('Linux-Programm fehlt: ' + argv[0])
        process = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, _ = await process.communicate()
        except asyncio.CancelledError:
            process.terminate()
            await process.wait()
            raise
        if process.returncode:
            raise ActionError('Programm fehlgeschlagen: ' + argv[0])
        return stdout.decode(errors='replace')

    async def mute(self, device, duration):
        self.trace('mute', device=device, duration=duration)
        if self.dry_run:
            return
        lock = self.audio_locks.setdefault(device, asyncio.Lock())
        async with lock:
            old = await self.process('wpctl', 'get-volume', device)
            await self.process('wpctl', 'set-mute', device, '1')
            try:
                await asyncio.sleep(duration)
            finally:
                await asyncio.shield(self.process('wpctl', 'set-mute', device, '1' if '[MUTED]' in old else '0'))
