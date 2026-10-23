"""CPH Twitch operations using the existing native platform services.

CPH strings are literal. They must not pass through Sub-Action variable expansion.
Each call snapshots the accounts and rejects changes before/after network awaits.
"""
import asyncio,copy
from .core import ActionError

ACCOUNT_KEYS=('twitch_client_id','broadcaster_id','twitch_token','twitch_scopes','bot_id','twitch_bot_token','twitch_bot_scopes')

class BoundIO:
    def __init__(self,source):
        self.source=source;self.config=copy.deepcopy(source.config)
        self.account={key:copy.deepcopy(source.config.get(key)) for key in ACCOUNT_KEYS}
    def __getattr__(self,name):return getattr(self.source,name)
    def check(self):
        if any(self.source.config.get(key)!=value for key,value in self.account.items()):raise ActionError('Twitch-Konto während des C#-Aufrufs geändert; Status vor erneutem Aufruf prüfen')
        if getattr(getattr(getattr(self.source,'engine',None),'studio',None),'closing',False):raise ActionError('Twitch-Laufzeit wird beendet')
    async def twitch(self,*args,**kwargs):
        self.check()
        if self.dry_run:raise ActionError('C#-Vorschau darf keine Twitch-Anfrage ausführen')
        result=await self.source.twitch(*args,**kwargs)
        self.check();return result
    async def user(self,login):
        from .adapters import IO
        return await IO.user(self,login)

def identity(value,label='ID'):
    if not isinstance(value,str) or not value.strip() or value!=value.strip():raise ActionError(label+' fehlt oder ist ungültig')
    return value

async def rpc(engine,values):
    if len(values)!=2 or not isinstance(values[0],str) or not isinstance(values[1],list):raise ActionError('Ungültiger Twitch-C#-Aufruf')
    if not hasattr(engine.io,'csharp_twitch_lock'):engine.io.csharp_twitch_lock=asyncio.Lock()
    # Shared read/modify/write operations from C# must not overwrite each other.
    async with engine.io.csharp_twitch_lock:
        io=BoundIO(engine.io);io.engine=engine;io.check()
        return await operation(io,values[0],values[1])

async def operation(io,name,args):
    from .csharp_twitch_counters import OPERATIONS as COUNTERS,operation as counter_operation
    if name in COUNTERS:return await counter_operation(io,name,args)
    from .csharp_twitch_automod import OPERATIONS as AUTOMOD,operation as automod_operation
    if name in AUTOMOD:return await automod_operation(io,name,args)
    from .csharp_twitch_clips import OPERATIONS as CLIPS,operation as clip_operation
    if name in CLIPS:return await clip_operation(io,name,args)
    from .csharp_twitch_data import OPERATIONS as DATA,operation as data_operation
    if name in DATA:return await data_operation(io,name,args)
    from .csharp_twitch_controls import OPERATIONS,operation as controls
    if name in OPERATIONS:return await controls(io,name,args)
    if name=='TwitchReplyToMessage':
        from .twitch_chat_actions import Chat,message_id,text
        message,parent,bot,fallback=args
        await Chat(io).reply(message_id(parent),text(message),bot,fallback);return None
    if name in ('TwitchSubscriberOnly','TwitchEmoteOnly','TwitchSlowMode','TwitchFollowMode'):
        from .twitch_chat_modes import ChatModes
        kind={'TwitchSubscriberOnly':91403,'TwitchEmoteOnly':91400,'TwitchSlowMode':91402,'TwitchFollowMode':91401}[name]
        enabled=args[0];duration=args[1] if len(args)>1 else ''
        # Original default zero means Twitch's default slow delay. Follower zero
        # is a valid explicit number of minutes and must be retained.
        if name=='TwitchSlowMode' and duration==0:duration=''
        await ChatModes(io).change({'type':kind,'state':enabled,'duration':duration},{});return None
    if name in ('TwitchAddChannelTag','TwitchRemoveChannelTag','TwitchClearChannelTags','TwitchSetChannelTags'):
        from .twitch_channel_tools import ChannelTools
        op={'TwitchAddChannelTag':'add','TwitchRemoveChannelTag':'remove','TwitchClearChannelTags':'clear','TwitchSetChannelTags':'set'}.get(name)
        if op is None:raise ActionError('Unbekannte C#-Tagfunktion')
        fields={} if op=='clear' else {'tags' if op=='set' else 'tag':args[0]}
        result=await ChannelTools(io).change(op,**fields);return bool(result.get('success'))
    if name in ('TwitchShieldModeOn','TwitchShieldModeOff'):
        from .twitch_moderation_extended import Extended
        return await Extended(io).update('Yes' if name.endswith('On') else 'No') is not None
    if name in ('TwitchWarnUser','TwitchAddActiveMonitoringSuspiciousStatus','TwitchAddRestrictedSuspiciousStatus','TwitchRemoveSuspiciousStatus'):
        from .twitch_moderation_extended import Extended
        kind=91902 if name=='TwitchWarnUser' else 91904 if name=='TwitchRemoveSuspiciousStatus' else 91903
        result=await Extended(io).user_change(kind,args[0],args[1] if kind==91902 else '', 'RESTRICTED' if name=='TwitchAddRestrictedSuspiciousStatus' else 'ACTIVE_MONITORING')
        return result is not None
    if name.startswith(('TwitchPoll','TwitchPrediction')):
        from .twitch_votes import Votes
        service=Votes(io,'polls' if name.startswith('TwitchPoll') else 'predictions')
        if name=='TwitchPollCreate':
            result=await service.create(*args);return not result.get('preview',False)
        if name=='TwitchPredictionCreate':
            result=await service.create(*args)
            if result.get('preview'):return ''
            return identity(result['data'][0].get('id'),'Prediction-ID')
        status={'TwitchPollTerminate':'TERMINATED','TwitchPollArchive':'ARCHIVED','TwitchPredictionCancel':'CANCELED','TwitchPredictionLock':'LOCKED','TwitchPredictionResolve':'RESOLVED'}.get(name)
        if status is None:raise ActionError('Unbekannte C#-Abstimmungsfunktion')
        await service.change(identity(args[0]),status,identity(args[1],'Gewinner-ID') if len(args)>1 else '');return None
    if name in ('TwitchRunCommercial','TwitchCancelRaid','TwitchGetPrerollFreeTime'):
        from .twitch_ads_raids import BroadcastTools,schedule_variables
        service=BroadcastTools(io)
        if name=='TwitchRunCommercial':result=await service.commercial(args[0]);return not result.get('preview',False)
        if name=='TwitchCancelRaid':result=await service.raid_cancel();return bool(result.get('cancelled')) and not result.get('preview',False)
        result=await service.schedule()
        if not result.get('data'):return 0
        return schedule_variables(result['data'][0])['prerollFreeSeconds']
    if name in REWARD_OPERATIONS:return await reward(io,name,args)
    raise ActionError('Unbekannte Twitch-C#-Funktion: '+name)

REWARD_OPERATIONS={
    'EnableReward','DisableReward','PauseReward','UnPauseReward',
    'UpdateRewardCost','UpdateRewardCooldown','UpdateRewardMaxPerStream','UpdateRewardMaxPerUserPerStream',
    'UpdateRewardTitle','UpdateRewardPrompt','UpdateRewardBackgroundColor','UpdateReward',
    'TwitchRedemptionFulfill','TwitchRedemptionCancel',
    'TwitchRewardGroupEnable','TwitchRewardGroupDisable','TwitchRewardGroupToggleEnable',
    'TwitchRewardGroupPause','TwitchRewardGroupUnPause','TwitchRewardGroupTogglePause',
}

async def reward(io,name,args):
    from .twitch_rewards import Rewards,integer,LIMITS,variables,validate
    service=Rewards(io);target=identity(args[0],'Reward-ID' if not name.startswith('TwitchRewardGroup') else 'Gruppenname')
    if name.startswith('TwitchRewardGroup'):
        rows=[row for row in (await service.list())['data'] if row.get('group')==target]
        if not rows:raise ActionError('Reward-Gruppe ist leer oder unbekannt')
        if any(not row.get('manageable') for row in rows):raise ActionError('Gruppe enthält fremde Rewards; keine Änderung ausgeführt')
        if not io.dry_run:service.require(True)
        field='is_enabled' if name.endswith(('Enable','Disable')) else 'is_paused'
        toggle='Toggle' in name;value=name.endswith('Enable') if field=='is_enabled' else name.endswith('Pause') and not name.endswith('UnPause')
        for row in rows:await service.update(row['id'],{field:not bool(row.get(field)) if toggle else value})
        return None
    if name in ('TwitchRedemptionFulfill','TwitchRedemptionCancel'):
        result=await service.redeem(target,identity(args[1],'Einlösungs-ID'),'FULFILLED' if name.endswith('Fulfill') else 'CANCELED')
        return not result.get('preview',False)
    fields={'EnableReward':('is_enabled',True),'DisableReward':('is_enabled',False),'PauseReward':('is_paused',True),'UnPauseReward':('is_paused',False)}
    if name in fields:key,value=fields[name];payload={key:value}
    elif name in ('UpdateRewardTitle','UpdateRewardPrompt','UpdateRewardBackgroundColor'):
        payload={ {'UpdateRewardTitle':'title','UpdateRewardPrompt':'prompt','UpdateRewardBackgroundColor':'background_color'}[name]:args[1] }
    elif name=='UpdateReward':
        payload={key:value for key,value in zip(('title','prompt','cost','background_color'),args[1:]) if value is not None}
        if not payload:return False
    else:
        value,additive=args[1:]
        if type(additive) is not bool:raise ActionError('Additive muss true/false sein')
        key={'UpdateRewardCost':'cost','UpdateRewardCooldown':'global_cooldown_seconds','UpdateRewardMaxPerStream':'max_per_stream','UpdateRewardMaxPerUserPerStream':'max_per_user_per_stream'}[name]
        value=integer(value,-2**63 if additive else 1 if key=='cost' else 0)
        if additive:
            row=await service.get(target,True)
            current=row['cost'] if key=='cost' else variables(row)[{'global_cooldown_seconds':'rewardGlobalCooldown','max_per_stream':'rewardMaxPerStream','max_per_user_per_stream':'rewardMaxPerUserPerStream'}[key]]
            value=integer(value+integer(current,0),1 if key=='cost' else 0)
        payload={key:value} if key=='cost' else {LIMITS[key]:value>0,**({key:value} if value>0 else {})}
    validate(payload)
    result=await service.update(target,payload)
    return not result.get('preview',False)
