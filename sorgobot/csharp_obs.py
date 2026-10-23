"""Original CPH OBS signatures over the existing WebSocket 5 connection pool."""
import asyncio,copy,json,random
from pathlib import PurePath
from .core import ActionError

STRINGS={'ObsGetCurrentScene','ObsSendRaw','ObsSendBatchRaw','ObsGetSceneItemProperties','ObsSetRandomGroupSourceVisible','ObsSetRandomSceneSourceVisible'}
BOOLS={'ObsIsConnected','ObsConnect','ObsIsStreaming','ObsIsRecording','ObsIsSourceVisible','ObsIsFilterEnabled','ObsTakeScreenshot','ObsCreateRecordChapter'}
SIMPLE={'ObsStartStreaming':'StartStream','ObsStopStreaming':'StopStream','ObsStartRecording':'StartRecord','ObsStopRecording':'StopRecord','ObsPauseRecording':'PauseRecord','ObsResumeRecording':'ResumeRecord','ObsReplayBufferStart':'StartReplayBuffer','ObsReplayBufferStop':'StopReplayBuffer','ObsReplayBufferSave':'SaveReplayBuffer'}
MEDIA={name:'OBS_WEBSOCKET_MEDIA_INPUT_ACTION_'+state.upper() for name,state in [('ObsMediaPlay','play'),('ObsMediaPause','pause'),('ObsMediaRestart','restart'),('ObsMediaStop','stop'),('ObsMediaNext','next'),('ObsMediaPrevious','previous')]}

def parsed(text,kind):
    def invalid(value):raise ValueError(value)
    try:
        result=json.loads(text,parse_constant=invalid)
        json.dumps(result,allow_nan=False)
    except (ValueError,TypeError):raise ActionError('Ungültiges OBS-JSON') from None
    if not isinstance(result,kind):raise ActionError('OBS-JSON hat den falschen Typ')
    return result

def state(value,current=False):
    if type(value) is not int or value not in (0,1,2):raise ActionError('OBS-Zustand muss 0, 1 oder 2 sein')
    return not current if value==2 else value==0

def dumps(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)

async def rpc(engine,values):
    operation,index,payload=values;io=engine.io;pool=io.obs_pool
    rows=list(pool.rows.values())
    if operation=='names':return [row['name'] for row in rows]
    if type(index) is not int or not 0<=index<len(rows):raise ActionError('OBS-Verbindungsindex ist ungültig')
    row=copy.deepcopy(rows[index]);identity=row['id']
    if not row.get('enabled',True):raise ActionError('OBS-Verbindung ist deaktiviert')
    client=pool.clients[identity]
    raw=None
    if operation=='ObsSendRaw':raw=parsed(payload[1] or '{}',dict)
    elif operation=='ObsSendBatchRaw':
        raw=parsed(payload[0],list)
        if type(payload[1]) is not bool or payload[2] not in (0,1,2):raise ActionError('Ungültige OBS-Batchoptionen')
        if any(not isinstance(r,dict) or not isinstance(r.get('requestType'),str) or not r['requestType'] or not isinstance(r.get('requestData',{}),dict) for r in raw):raise ActionError('Ungültige OBS-Batchanfrage')
    if operation in ('ObsSetSourceVisibilityState','ObsSetFilterState','ObsSetSourceMuteState','ObsSetRandomFilterState'):state(payload[-1])
    if operation=='ObsSetMediaState' and (type(payload[-1]) is not int or not 0<=payload[-1]<=5):raise ActionError('Ungültiger OBS-Medienzustand')
    if operation=='ObsSetReplayBufferState':state(payload[0])
    if operation=='ObsTakeScreenshot':
        suffix=PurePath(payload[1]).suffix.lower().lstrip('.')
        if suffix not in ('png','jpg','jpeg','bmp','webp') or not -1<=payload[2]<=100:raise ActionError('Ungültiges OBS-Screenshotformat oder Qualität')
    if io.dry_run:
        io.trace('obs_csharp',operation=operation,connectionId=identity,simulated=True)
        return False if operation in BOOLS else [] if operation=='ObsGetGroupSources' else '{}' if operation in ('ObsSendRaw','ObsGetSceneItemProperties') else '{"results":[],"simulated":true}' if operation=='ObsSendBatchRaw' else '' if operation in STRINGS else None
    def check():
        if pool.rows.get(identity)!=row or pool.clients.get(identity) is not client:raise ActionError('OBS-Verbindung während des Aufrufs geändert')
        if getattr(getattr(engine,'studio',None),'closing',False):raise ActionError('OBS-Laufzeit wird beendet')
    check()
    if operation=='ObsIsConnected':return client.ready.is_set() and client.ws is not None and not client.ws.closed
    if operation=='ObsDisconnect':await pool.disconnect(identity);return None
    if operation=='ObsConnect':
        studio=getattr(engine,'studio',None)
        if studio is None:raise ActionError('OBS-Verbindungsaufbau benötigt Studio-Laufzeit')
        pool.connect(identity,studio.spawn)
        try:await asyncio.wait_for(client.ready.wait(),5)
        except TimeoutError:return False
        check();return client.ready.is_set()
    token=io.obs_context.set(identity)
    async def call(request,**data):check();return await io.obs_call(request,**data)
    async def item(scene,source):
        result=await call('GetSceneItemId',sceneName=scene,sourceName=source)
        return {'sceneName':scene,'sceneItemId':result['sceneItemId']}
    async def set_item(scene,source,enabled):await call('SetSceneItemEnabled',**(await item(scene,source)),sceneItemEnabled=enabled)
    try:
        if operation in SIMPLE:await call(SIMPLE[operation]);return None
        if operation=='ObsGetCurrentScene':return (await call('GetCurrentProgramScene'))['currentProgramSceneName']
        if operation in ('ObsIsStreaming','ObsIsRecording'):return bool((await call('GetStreamStatus' if operation=='ObsIsStreaming' else 'GetRecordStatus'))['outputActive'])
        if operation=='ObsSetScene':await call('SetCurrentProgramScene',sceneName=payload[0]);return None
        if operation=='ObsSendRaw':return dumps(await call(payload[0],**raw))
        if operation=='ObsSendBatchRaw':check();return dumps(await io.obs_batch(raw,payload[1],payload[2]))
        if operation in ('ObsIsSourceVisible','ObsSetSourceVisibility','ObsSetSourceVisibilityState','ObsShowSource','ObsHideSource','ObsGetSceneItemProperties'):
            scene,source,*args=payload;target=await item(scene,source)
            if operation=='ObsGetSceneItemProperties':return dumps((await call('GetSceneItemTransform',**target))['sceneItemTransform'])
            if operation=='ObsIsSourceVisible':return bool((await call('GetSceneItemEnabled',**target))['sceneItemEnabled'])
            if operation=='ObsSetSourceVisibility':enabled=args[0]
            elif operation=='ObsSetSourceVisibilityState':enabled=state(args[0],bool((await call('GetSceneItemEnabled',**target))['sceneItemEnabled']) if args[0]==2 else False)
            else:enabled=operation=='ObsShowSource'
            await call('SetSceneItemEnabled',**target,sceneItemEnabled=enabled);return None
        if operation in ('ObsGetGroupSources','ObsHideGroupsSources','ObsSetRandomGroupSourceVisible','ObsHideSceneSources','ObsSetRandomSceneSourceVisible'):
            scene=payload[0];group=len(payload)>1
            container=payload[1] if group else scene
            items=(await call('GetGroupSceneItemList' if group else 'GetSceneItemList',sceneName=container))['sceneItems']
            if operation=='ObsGetGroupSources':return [row['sourceName'] for row in items]
            chosen=random.choice(items) if items and operation.startswith('ObsSetRandom') else None
            for entry in items:await call('SetSceneItemEnabled',sceneName=container,sceneItemId=entry['sceneItemId'],sceneItemEnabled=entry is chosen)
            return chosen['sourceName'] if chosen else '' if operation.startswith('ObsSetRandom') else None
        if operation in ('ObsIsFilterEnabled','ObsSetFilterState','ObsShowFilter','ObsHideFilter','ObsToggleFilter','ObsSetRandomFilterState','ObsHideSourcesFilters','ObsHideScenesFilters'):
            args=list(payload)
            if operation in ('ObsHideSourcesFilters','ObsHideScenesFilters'):source=args[1] if len(args)>1 else args[0];filters=(await call('GetSourceFilterList',sourceName=source))['filters'];names=[f['filterName'] for f in filters];value=1
            elif operation=='ObsSetRandomFilterState':
                source=args[1] if len(args)==3 else args[0];value=args[-1];state(value);filters=(await call('GetSourceFilterList',sourceName=source))['filters'];names=[random.choice(filters)['filterName']] if filters else []
            else:
                tail=1 if operation=='ObsSetFilterState' else 0;parts=args[:-tail] if tail else args
                source=parts[1] if len(parts)==3 else parts[0];names=[parts[-1]];value=args[-1] if tail else 0 if operation=='ObsShowFilter' else 1 if operation=='ObsHideFilter' else 2
            for name in names:
                current=bool((await call('GetSourceFilter',sourceName=source,filterName=name))['filterEnabled']) if operation=='ObsIsFilterEnabled' or value==2 else False
                if operation=='ObsIsFilterEnabled':return current
                await call('SetSourceFilterEnabled',sourceName=source,filterName=name,filterEnabled=state(value,current))
            return None
        if operation in ('ObsSetSourceMuteState','ObsSourceMute','ObsSourceUnMute','ObsSourceMuteToggle'):
            source=payload[1];value=payload[2] if operation=='ObsSetSourceMuteState' else {'ObsSourceMute':0,'ObsSourceUnMute':1,'ObsSourceMuteToggle':2}[operation]
            current=bool((await call('GetInputMute',inputName=source))['inputMuted']) if value==2 else False
            await call('SetInputMute',inputName=source,inputMuted=state(value,current));return None
        if operation in MEDIA or operation=='ObsSetMediaState':
            if operation in MEDIA:action=MEDIA[operation]
            else:
                value=payload[2]
                if type(value) is not int or not 0<=value<=5:raise ActionError('Ungültiger OBS-Medienzustand')
                action=list(MEDIA.values())[value]
            await call('TriggerMediaInputAction',inputName=payload[1],mediaAction=action);return None
        if operation=='ObsSetReplayBufferState':
            value=payload[0]
            if type(value) is not int or value not in (0,1,2):raise ActionError('Ungültiger Replay-Zustand')
            await call(('StartReplayBuffer','StopReplayBuffer','SaveReplayBuffer')[value]);return None
        settings={'ObsSetBrowserSource':('url',None),'ObsSetGdiText':('text',None),'ObsSetMediaSourceFile':('local_file',None),'ObsSetImageSourceFile':('file',None),'ObsSetColorSourceColor':('color',None),'ObsSetColorSourceRandomColor':('color',None)}
        if operation in settings:
            key=settings[operation][0];value=(255<<24)|random.randrange(1<<24) if operation=='ObsSetColorSourceRandomColor' else payload[2]
            await call('SetInputSettings',inputName=payload[1],inputSettings={key:value},overlay=True);return None
        if operation=='ObsTakeScreenshot':
            source,path,quality=payload;suffix=PurePath(path).suffix.lower().lstrip('.')
            if suffix not in ('png','jpg','jpeg','bmp','webp') or not -1<=quality<=100:raise ActionError('Ungültiges OBS-Screenshotformat oder Qualität')
            await call('SaveSourceScreenshot',sourceName=source,imageFormat=suffix,imageFilePath=path,imageCompressionQuality=quality);return True
        if operation=='ObsCreateRecordChapter':await call('CreateRecordChapter',chapterName=payload[0]);return True
        raise ActionError('Unbekannte C#-OBS-Methode: '+operation)
    finally:io.obs_context.reset(token)
