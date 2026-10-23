from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import logging
import secrets
import time
from pathlib import Path

import aiohttp
from aiohttp import web

from .adapters import IO
from .core import ActionError, Dispatcher, Engine, State
from .custom import BEHAVIOR, Custom
from .twitch import TwitchEvents


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


class Studio:
    def __init__(self, root, live, obs_test=False):
        self.root, self.live = Path(root).resolve(), live
        from .diagnostics import Diagnostics
        self.diagnostics=Diagnostics(self.root,lambda:getattr(self,'config',{}))
        self.diagnostics.write('application_start',mode='live' if live else 'preview')
        if live and obs_test:
            raise ValueError('Live- und OBS-Testmodus schließen sich aus')
        self.obs_test = obs_test
        self.tasks = set();self.closing=False
        from .main_websocket import MainWebsocket
        self.main_websocket=MainWebsocket(self)
        self.token = secrets.token_urlsafe(32)
        self.config = read(self.root / 'config/local.json')
        prompts = self.root / 'config/prompts.json'
        if prompts.exists(): self.config['prompts'] = read(prompts)
        self.webroot = Path(__file__).parent / 'web'

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine, context=contextvars.Context())
        self.tasks.add(task)
        def done(t):
            self.tasks.discard(t)
            if not t.cancelled() and t.exception():
                exc = t.exception()
                self.io.trace('task_error', error=str(exc) if isinstance(exc, ActionError) else type(exc).__name__)
        task.add_done_callback(done)
        return task

    async def start(self, app):
        (self.root / 'state').mkdir(exist_ok=True)
        from .dotnet_values import prepare
        try:await asyncio.to_thread(prepare)
        except ActionError as exc:self.diagnostics.write('format_service_unavailable',error=str(exc))
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        self.state = State(self.root / 'state' / ('live.db' if self.live else 'preview.db'))
        imported = self.root / 'config/imported-globals.private.json'
        if imported.exists() and not self.state.get('globals_imported'):
            for key,value in read(imported).items():
                if key not in ('LLM_API_KEY','own3d_oauth_token'):
                    self.state.set(key,value)
            self.state.set('globals_imported',True)
        self.io = IO(self.root, self.config, self.session, dry_run=not self.live, obs_test=self.obs_test)
        self.io.diagnostics=self.diagnostics
        self.io.camera = None
        await self.configure_camera()
        self.custom = Custom(self.io, self.state, read(self.root / 'config/custom.json'))
        self.engine = Engine(read(self.root / 'config/actions.json'), self.state, self.io, self.custom)
        self.engine.diagnostics=self.diagnostics
        self.custom.engine = self.engine
        self.io.engine = self.engine
        self.engine.studio = self
        self.timer_due = {}
        self.timer_lines = {}
        self.timer_definitions = read(self.root / 'config/timers.json')
        self.dispatcher = Dispatcher(self.engine, read(self.root / 'config/commands.json')['commands'])
        from .core_services import CoreServices
        self.core_services=CoreServices(self)
        from .linux_watchers import LocalWatchers
        self.local_watchers=LocalWatchers(self)
        from .service_management import Services
        self.services=Services(self)
        from .core_events import CoreEvents
        self.engine.core_events=CoreEvents(self)
        self.spawn(self.engine.core_events.dispatch())
        from .core_connections import Connections
        self.connections=Connections(self)
        from .linux_notifications import Notifications
        self.notifications=Notifications(self)
        self.twitch = TwitchEvents(self.io, self.dispatcher, self.spawn)
        from .csharp import precompile
        await precompile(self.engine)
        self.spawn(precompile(self.engine,delayed=True))
        self.state.set('pauseMusicAktiv', False)
        if self.state.get('death_counts') is None:
            counts = {}
            path = self.root / 'assets/Streamer.bot/saves/tode.txt'
            if path.exists():
                for line in path.read_text(encoding='utf-8-sig').splitlines():
                    key, sep, value = line.rpartition('=')
                    if sep and value.strip().isdigit(): counts[key.strip()] = int(value.strip())
            self.state.set('death_counts', counts)
        self.obs_task=None
        await self.io.obs_pool.configure(self.config,self.obs_event if self.live else None)
        if self.obs_test:self.io.obs_pool.auto_connect(self.spawn)
        self.obs_task=self.io.obs_pool.tasks.get('default')
        from .twitch_connections_whispers import BotEvents
        self.twitch_bot=BotEvents(self.io,self.dispatcher,self.twitch.connections);self.twitch_bot_task=None
        self.twitch_task=None
        from .linux_audio import Audio
        self.audio=Audio(self)
        from .timed_effects import Effects
        self.temporary_effects=Effects(self)
        if self.live:self.spawn(self.audio.run())
        from .streamdeck_bridge import Bridge
        self.streamdeck=Bridge(self)
        await self.streamdeck.start()
        from .streamermod_remote import Remote
        self.remote=Remote(self)
        await self.remote.start()

        if self.live:
            self.io.obs_pool.auto_connect(self.spawn)
            self.obs_task=self.io.obs_pool.tasks.get('default')
            if self.config.get('twitch_token'):
                self.twitch_task=self.spawn(self.twitch.run())
            if self.config.get('twitch_bot_token'):self.twitch_bot_task=self.spawn(self.twitch_bot.run())
            self.spawn(self.timers())
            self.spawn(self.core_services.poll_tails())
            self.spawn(self.core_services.dispatch_tails())
            from .linux_inputs import DeviceListeners
            from .linux_hotkeys import Hotkeys
            from .core_schedule import CronSchedules
            self.device_listeners=DeviceListeners(self)
            self.spawn(self.device_listeners.run())
            self.spawn(Hotkeys(self).run())
            self.spawn(CronSchedules(self).run())
            self.spawn(self.connections.run())
            self.spawn(self.local_watchers.poll())
            self.spawn(self.local_watchers.dispatch())
            self.spawn(self.dispatcher.event(90040,{}))

        from .twitch_auth import TwitchOAuth
        self.twitch_auth=TwitchOAuth(self.session,self.root,self.config,self.twitch.connections.authenticated)
        self.spawn(self.twitch_auth.maintain(lambda message:getattr(self,'auth_error',logging.warning)(message)))
        from .youtube import YouTube
        self.youtube=YouTube(self);await self.youtube.start()
        await self.services.start()

    async def configure_camera(self):
        current=getattr(self.io,'camera',None)
        enabled=self.live and self.config.get('camera_enabled',False)
        device=self.config.get('camera_device',0)
        if current is not None and enabled and current.device==device and current.thread and current.thread.is_alive():return
        if current is not None:
            current.stop.set()
            if current.thread:
                await asyncio.to_thread(current.thread.join,3)
                if current.thread.is_alive():raise ActionError('Kameradienst beendet sich noch; erneut laden')
            self.io.camera=None
        if enabled:
            from .camera import Camera
            self.io.camera=Camera(device);self.io.camera.start()

    async def camera_preview(self):
        import base64,sys
        camera=getattr(self.io,'camera',None)
        if camera is not None:
            deadline=asyncio.get_running_loop().time()+5
            while camera.frame is None:
                if camera.error:raise ActionError(camera.error)
                if asyncio.get_running_loop().time()>=deadline:raise ActionError('Kamera liefert innerhalb von fünf Sekunden kein Bild')
                await asyncio.sleep(.05)
            image=camera.frame
        else:
            process=await asyncio.create_subprocess_exec(sys.executable,'-m','sorgobot.camera_snapshot',str(self.config.get('camera_device',0)),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            try:
                try:image,error=await asyncio.wait_for(process.communicate(),6)
                except TimeoutError:raise ActionError('Kamera liefert innerhalb von sechs Sekunden kein Bild') from None
                if process.returncode or not image:raise ActionError('Kameratest fehlgeschlagen: '+error.decode(errors='replace')[-500:])
            finally:
                if process.returncode is None:
                    try:process.kill()
                    except ProcessLookupError:pass
                await process.wait()
        return 'data:image/jpeg;base64,'+base64.b64encode(image).decode()

    async def close(self, app):
        if getattr(self,'closed',False):return
        self.closed=True;self.closing=True
        if hasattr(self,'temporary_effects'):await self.temporary_effects.close()
        if hasattr(self,'youtube'):await self.youtube.close()
        if hasattr(self,'services'):await self.services.close()
        from .csharp import shutdown
        await shutdown(self.engine)
        if getattr(self,'remote',None):await self.remote.close()
        if getattr(self,'streamdeck',None):await self.streamdeck.close()
        await self.main_websocket.close()
        await self.io.obs_pool.close()
        self.notifications.close()
        self.state.set('first_words_closed_at',time.time())
        if self.io.camera:
            self.io.camera.stop.set()
            await asyncio.to_thread(self.io.camera.thread.join, 3)
        tasks = list(self.tasks | self.custom.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        from .csharp_sounds import close_players
        await close_players(self.io)
        await self.session.close()
        self.state.db.close()
        self.diagnostics.write('application_stop');self.diagnostics.close()

    def obs_event(self, kind, data, metadata=None):
        from .obs_actions import event, general_events
        metadata=metadata or self.io.obs.connection_arguments();connection=metadata['obs.id']
        from .websocket_notifications import obs as notify_obs
        notify_obs(self,kind,data,metadata)
        for identity,arguments,filters in general_events(kind,data,metadata):
            self.spawn(self.dispatcher.event(identity,arguments,obsConnection=connection,**filters))
        extra=event(kind,data)
        if extra:
            identity,arguments,filters=extra
            self.spawn(self.dispatcher.event(identity,dict(metadata,**arguments),obsConnection=connection,**filters))
        if kind == 'CurrentProgramSceneChanged':
            self.spawn(self.dispatcher.event(14004, dict(metadata,sceneName=data['sceneName']), obsConnection=connection, sceneName=data['sceneName']))
        elif kind == 'StreamStateChanged':
            state = data.get('outputState')
            if state in ('OBS_WEBSOCKET_OUTPUT_STARTED', 'OBS_WEBSOCKET_OUTPUT_STOPPED'):
                if state.endswith('_STARTED'):
                    self.dispatcher.first_users.clear()
                    self.state.set('first_words_users',[])
                self.spawn(self.dispatcher.event(14005 if state.endswith('_STARTED') else 14006, dict(metadata),obsConnection=connection))
                if connection=='default' and 'Sorgobot: Voice-Status' in self.engine.actions:self.spawn(self.engine.run('Sorgobot: Voice-Status'))

    async def timers(self):
        from .timer_control import tick
        while True:
            now = time.time()
            expires = self.state.get('behavior_expires', 0)
            if expires and now >= expires:
                await self.custom.behavior('Verhalten wiederherstellen', {})
                self.state.set('behavior_expires', 0)
            tick(self,now)
            await asyncio.sleep(1)

    async def index(self, request):
        text = (self.webroot / 'index.html').read_text(encoding='utf-8').replace('__TOKEN__', self.token)
        return web.Response(text=text, content_type='text/html', headers={'Cache-Control': 'no-store'})

    async def status(self, request):
        from .youtube_events import combined_messages
        return web.json_response({'live': self.live, 'obs': self.io.obs.status,
            'twitch': self.twitch.status, 'youtube':self.youtube.status(), 'streamDeck':self.streamdeck.status(), 'streamerModRemote':self.remote.status(),'temporaryEffects':self.temporary_effects.status(), 'actions': [{'id': a['id'], 'name': a['name'], 'group': a.get('group', ''), 'enabled': a['enabled'], 'blocked': a.get('migrationBlock', '')} for a in self.engine.actions.values()],
            'history': self.engine.history[-30:], 'effects': self.io.effects[-30:], 'chat': combined_messages(self,30),
            'settings': {k: self.config.get(k, '') for k in ['channel', 'llm_url', 'llm_model', 'vision_model', 'reply_probability', 'tts_voice', 'obs_url']},
            'behavior': self.state.get('LLM_BEHAVIOR', BEHAVIOR), 'game': self.state.get('currentGame', '')})

    async def credits_overlay(self,request):
        return web.Response(text=(self.webroot/'credits.html').read_text(),content_type='text/html',headers={'Cache-Control':'no-store'})

    async def get_credits(self,request):
        from .http_contracts import public_credits
        return web.json_response(public_credits(self.engine))

    async def action(self, request):
        data = await request.json()
        identity = request.match_info['id']
        if identity not in self.engine.actions:
            raise web.HTTPNotFound()
        raw = data.get('input', '')[:2000]
        login=self.config.get('twitch_login') or self.config.get('channel','')
        args = {'userName': login, 'user': login, 'userLogin': login, 'message': raw,
                'rawInput': raw, 'input0': raw.split()[0].lstrip('@') if raw else '', 'roles': ['Broadcaster']}
        # Return immediately: actions can have ten-minute timers.
        self.spawn(self.engine.run(identity, args))
        return web.json_response({'queued': True})

    async def settings(self, request):
        data = await request.json()
        allowed = {'llm_url', 'llm_model', 'vision_model', 'tts_voice', 'reply_probability', 'obs_url'}
        for key in allowed & data.keys():
            value = data[key]
            if key == 'reply_probability':
                value = max(0, min(100, int(value)))
            elif not isinstance(value, str) or len(value) > 2000:
                raise web.HTTPBadRequest(text='Ungültiger Wert')
            self.config[key] = value
        if 'behavior' in data:
            self.state.set('LLM_BEHAVIOR', str(data['behavior'])[:12000])
        # Preview settings stay isolated from live credentials/configuration.
        if self.live:
            path = self.root / 'config/local.json'
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)
        return web.json_response({'ok': True})

    async def obs_status(self, request):
        if not self.live:
            return web.json_response({'scenes': [{'sceneName': 'Gaming - Live'}, {'sceneName': '_SteamPause'}], 'currentProgramSceneName': 'Vorschaumodus', 'stream': {}, 'record': {}})
        scenes = await self.io.obs_call('GetSceneList')
        scenes['stream'] = await self.io.obs_call('GetStreamStatus')
        scenes['record'] = await self.io.obs_call('GetRecordStatus')
        return web.json_response(scenes)

    async def obs_command(self, request):
        data = await request.json()
        command = data.get('command')
        if command not in ('StartStream', 'StopStream', 'StartRecord', 'StopRecord', 'SetCurrentProgramScene', 'ToggleInputMute'):
            raise web.HTTPBadRequest(text='Unbekannter OBS-Befehl')
        params = {}
        if command == 'SetCurrentProgramScene': params['sceneName'] = data['scene']
        if command == 'ToggleInputMute': params['inputName'] = data['input']
        return web.json_response(await self.io.obs_call(command, **params))

    async def preview(self, request):
        if not self.live:
            return web.json_response({'image': None})
        scene = (await self.io.obs_call('GetCurrentProgramScene'))['currentProgramSceneName']
        data = await self.io.obs_call('GetSourceScreenshot', sourceName=scene, imageFormat='jpeg', imageWidth=960, imageCompressionQuality=65)
        return web.json_response({'image': data['imageData']})

    async def chat(self, request):
        data = await request.json()
        await self.io.send(str(data['message']))
        return web.json_response({'ok': True})

    async def clip(self, request):
        import html
        clip = request.query.get('clip', '')
        if not __import__('re').fullmatch(r'[\w-]{1,150}', clip):
            raise web.HTTPBadRequest()
        return web.Response(text='<style>html,body,iframe{margin:0;width:100%;height:100%;border:0}</style><iframe allow="autoplay; fullscreen" src="https://clips.twitch.tv/embed?clip=' + html.escape(clip) + '&parent=127.0.0.1&autoplay=true&muted=false"></iframe>', content_type='text/html')

    async def camera_page(self, request):
        return web.Response(text='<style>html,body{margin:0;background:transparent}img{width:100vw;height:100vh;object-fit:contain}</style><img src="/camera.mjpeg">',content_type='text/html')

    async def camera_stream(self, request):
        camera = self.io.camera
        if camera is None or camera.frame is None:
            raise web.HTTPServiceUnavailable(text='Kamera nicht verfügbar')
        response = web.StreamResponse(headers={'Content-Type':'multipart/x-mixed-replace; boundary=frame','Cache-Control':'no-store'})
        await response.prepare(request)
        try:
            while camera.frame:
                frame = camera.frame
                await response.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(frame)).encode() + b'\r\n\r\n' + frame + b'\r\n')
                await asyncio.sleep(1/25)
        except (ConnectionError, asyncio.CancelledError):
            pass
        return response

    async def legacy(self, request, original=False, authenticated=True):
        # Local voice/action requests and the explicitly supported event subset.
        ws = web.WebSocketResponse(heartbeat=30,max_msg_size=65536)
        await ws.prepare(request)
        from .service_management import SERVICE_PEERS
        service_peers=request.app.get(SERVICE_PEERS)
        if service_peers is not None:service_peers.add(ws)
        address=str(request.remote)+':'+str(request.transport.get_extra_info('peername')[1])
        if not self.main_websocket.register(ws,original,authenticated,address):
            await ws.close()
            if service_peers is not None:service_peers.discard(ws)
            return ws
        try:
            if original:
                from .original_websocket import hello,AUTH_TIMEOUT
                auth_deadline=asyncio.get_running_loop().time()+AUTH_TIMEOUT
                greeting=hello(self,self.main_websocket.peers[ws])
            else:greeting={'request': 'Hello', 'info': {'name': 'StreamerMod'}, 'authentication': {}}
            await self.main_websocket.send(ws,greeting)
            while not ws.closed:
                try:msg=await asyncio.wait_for(ws.receive(),max(0,auth_deadline-asyncio.get_running_loop().time())) if not self.main_websocket.peers[ws]['authenticated'] else await ws.receive()
                except TimeoutError:
                    await ws.close(code=1008,message=b'Authentication timeout');break
                if msg.type in (aiohttp.WSMsgType.CLOSE,aiohttp.WSMsgType.CLOSED,aiohttp.WSMsgType.ERROR):break
                if msg.type != aiohttp.WSMsgType.TEXT:continue
                d=None
                try:
                    d=msg.json()
                    if not isinstance(d,dict):raise ValueError()
                    if original:
                        if not isinstance(d.get('id'),str) or len(d['id'])>512:raise ValueError('request id')
                        if d.get('request')=='Authenticate':
                            response=self.main_websocket.authenticate(ws,d);await self.main_websocket.send(ws,response)
                            if response['status']=='error':await ws.close(code=1008,message=b'Authentication failed')
                            continue
                        if not self.main_websocket.peers[ws]['authenticated']:
                            await self.main_websocket.send(ws,{'id':d['id'],'status':'error','error':'Authentifizierung erforderlich'})
                            await ws.close(code=1008,message=b'Authentication required');continue
                    response=self.main_websocket.request(ws,d)
                    if response is None and original:
                        from .original_websocket import request as original_request
                        response=await original_request(self,d)
                    if response is None:
                        response = {'id': d.get('id'), 'status': 'ok'}
                        if d.get('request') == 'DoAction':
                            action = d.get('action', {})
                            identity = action.get('id') or action.get('name')
                            self.spawn(self.engine.run(identity, d.get('args', {})))
                        elif d.get('request') == 'RecognizeVoice':
                            self.spawn(self.core_services.voice(str(d.get('text',''))[:10000],d.get('args',{})))
                        elif d.get('request') == 'GetGlobal':
                            response['value'] = self.state.get(d.get('variable'))
                        elif d.get('request') == 'GetActions':
                            response['actions'] = [{'id': a['id'], 'name': a['name']} for a in self.engine.actions.values()]
                        else:response.update(status='error', error='Nicht unterstützte Anfrage')
                except ActionError as exc:
                    response={'id':d.get('id') if isinstance(d,dict) else None,'status':'error','error':str(exc)}
                except (ValueError,KeyError,TypeError,AttributeError):
                    response={'id':d.get('id') if isinstance(d,dict) else None,'status':'error','error':'Ungültige Anfrage'}
                await self.main_websocket.send(ws,response)
        finally:
            self.main_websocket.unregister(ws)
            if service_peers is not None:service_peers.discard(ws)
        return ws

    def application(self):
        @web.middleware
        async def guard(request, handler):
            host = request.host.split(':')[0]
            if host not in ('127.0.0.1', 'localhost'):
                raise web.HTTPForbidden(text='Nur lokaler Zugriff')
            from .chat_dock import authorized as dock_authorized
            dock_request=request.path=='/api/chat-dock' and dock_authorized(self,request)
            if request.method != 'GET' and request.headers.get('X-Studio-Token') != self.token and not dock_request:
                raise web.HTTPForbidden(text='Sitzung neu laden')
            if request.headers.get('Origin') and request.headers['Origin'] not in ('http://127.0.0.1:8766', 'http://localhost:8766'):
                raise web.HTTPForbidden()
            try:
                return await handler(request)
            except ActionError as exc:
                return web.json_response({'error': str(exc)}, status=409)
            except (ValueError, KeyError, TypeError):
                return web.json_response({'error': 'Ungültige Anfrage'}, status=400)
        app = web.Application(middlewares=[guard], client_max_size=1024*1024)
        app.on_startup.append(self.start)
        app.on_cleanup.append(self.close)
        app.on_shutdown.append(self.main_websocket.close)
        app.add_routes([web.get('/', self.index), web.get('/api/status', self.status),
            web.get('/GetCredits', self.get_credits),web.get('/credits', self.credits_overlay),
            web.post('/api/actions/{id}', self.action), web.post('/api/settings', self.settings),
            web.get('/api/obs', self.obs_status), web.post('/api/obs', self.obs_command),
            web.get('/api/preview', self.preview), web.post('/api/chat', self.chat),
            web.get('/clip', self.clip), web.get('/ws', self.legacy),
            web.get('/camera', self.camera_page), web.get('/camera.mjpeg', self.camera_stream)])
        from .chat_dock import install as install_chat_dock
        install_chat_dock(app,self)
        app.router.add_static('/static/', self.webroot)
        return app


def main():
    parser = argparse.ArgumentParser(description='Sorgobot Studio für Debian')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--live', action='store_true', help='OBS/Twitch und echte Aktionen aktivieren')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    web.run_app(Studio(args.root, args.live).application(), host='127.0.0.1', port=8766, access_log=None)


if __name__ == '__main__':
    main()
