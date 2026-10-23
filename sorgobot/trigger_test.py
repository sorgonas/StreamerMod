"""Build a manual test event from the selected trigger's saved criteria."""
import copy
from .core import ActionError

def arguments(trigger,commands,timers,config,core_config=None):
    kind=trigger['type']
    values=copy.deepcopy(trigger.get('arguments',{}))
    values.update({key:copy.deepcopy(value) for key,value in trigger.items() if key not in ('id','type','enabled','arguments')})
    login=config.get('twitch_login') or 'testuser'
    values.setdefault('user',login);values.setdefault('userName',login);values.setdefault('userLogin',login)
    values.setdefault('userId',config.get('broadcaster_id',''));values.setdefault('rawInput','');values.setdefault('input0','')
    if kind in (401,402):
        identity=trigger.get('commandId','')
        command=next((c for c in commands if c['id']==identity),None) if identity else next((c for c in commands if c.get('enabled',True)),None)
        if identity and command is None:raise ActionError('Der im Trigger ausgewählte Befehl wurde gelöscht. Bitte den Trigger bearbeiten.')
        if command:
            text=command.get('command','').splitlines()
            values.update(commandId=command['id'],commandName=command.get('name',''),command=text[0] if text else '',commandSource='twitch',commandType='message')
        else:values.update(commandId='',commandName='Any',command='',commandSource='twitch',commandType='message')
        # Command events carry the original message, even when no input follows
        # the command. Consumers such as AI prompts need that context in tests too.
        values.setdefault('message',' '.join(part for part in (values['command'],values['rawInput']) if part))
        values.setdefault('roles',['Broadcaster'] if config.get('twitch_login') else [])
        values.setdefault('counter',1);values.setdefault('userCounter',1)
        if kind==402:
            global_left=command.get('globalCooldown',0) if command else 0;user_left=command.get('userCooldown',0) if command else 0
            values.update(globalCooldownLeft=global_left,userCooldownLeft=user_left,cooldownLeft=max(global_left,user_left))
    elif kind==701:
        identity=trigger.get('timerId','');timer=next((t for t in timers if t['id']==identity),None)
        if identity and timer is None:raise ActionError('Der im Trigger ausgewählte Timer wurde gelöscht. Bitte den Trigger bearbeiten.')
        if timer:values.update(timerId=identity,timerName=timer.get('name',''))
    if kind in (112,90550):
        values.update(redemptionId='test-redemption',rewardId=trigger.get('rewardId') or 'test-reward',rewardName='Test Reward',rewardTitle='Test Reward',rewardCost=100,rewardPrompt='',rewardStatus=trigger.get('rewardStatus') or ('fulfilled' if kind==90550 else 'unfulfilled'),counter=1,userCounter=1)
        values.update(trigger.get('arguments',{}))
    if 90350<=kind<=90362:
        examples={'sceneName':'Test Scene','sceneItemId':1,'sceneItemEnabled':True,'inputName':'Test Source','sourceName':'Test Source','filterName':'Test Filter','filterEnabled':True,'inputMuted':False,'inputVolumeMul':1.0,'inputVolumeDb':0.0,'savedReplayPath':'/tmp/test-replay.mkv'}
        for key,value in examples.items():
            if not values.get(key):values[key]=value
        values.update(trigger.get('arguments',{}))
    if 90200<=kind<=90270:
        from .core_test_context import examples
        explicit=copy.deepcopy(trigger.get('arguments',{}))
        values.update(examples(trigger,core_config or {}));values.update(explicit)
    if kind in (90031,90032,90850,90851,90852,90853,90854,90855):
        from .twitch_subscription_events import notification,expired
        notice={90031:'sub_gift',90032:'community_sub_gift',90850:'sub',90851:'resub',90852:'gift_paid_upgrade',90853:'prime_paid_upgrade',90854:'pay_it_forward'}.get(kind)
        event={'broadcaster_user_id':config.get('broadcaster_id',''),'broadcaster_user_login':login,'broadcaster_user_name':login,'chatter_user_id':'test-subscriber','chatter_user_login':'testsubscriber','chatter_user_name':'Test Subscriber','notice_type':notice,'message':{'text':'Test resub'},'system_message':'Test Subscription'}
        if notice:event[notice]={'sub_tier':'1000','duration_months':1,'cumulative_months':6,'streak_months':3,'total':5,'cumulative_total':10,'recipient_user_id':'test-recipient','recipient_user_login':'recipient','recipient_user_name':'Recipient'}
        mapped=notification(event) if notice else expired({'user_id':'test-subscriber','user_login':'testsubscriber','user_name':'Test Subscriber','tier':'1000'})
        values.update(mapped[1]);values.update(trigger.get('arguments',{}))
    if kind in (90950,90951):
        from .twitch_ads_raids_events import ad,raid
        if kind==90950:mapped=ad({'duration_seconds':90,'is_automatic':True,'broadcaster_user_id':config.get('broadcaster_id',''),'broadcaster_user_login':login})
        else:mapped=raid({'from_broadcaster_user_id':config.get('broadcaster_id','test-owner'),'from_broadcaster_user_login':login,'to_broadcaster_user_id':'test-target','to_broadcaster_user_login':'testtarget','to_broadcaster_user_name':'Test Target','viewers':20},config.get('broadcaster_id','test-owner'))
        values.update(mapped[1]);values.update(trigger.get('arguments',{}))
    if kind in (91250,91251,91252):
        values.update(broadcasterUserId=config.get('broadcaster_id',''),broadcasterUserName=login,broadcasterUser=login)
        if kind==91252:values.update(viewerCount=max(0,trigger.get('rangeMin',-1)),isInitialSample=False)
        elif kind==91250:values.update(startedAt='2026-10-13T12:00:00Z',streamId='test-stream',channelInfoAvailable=False)
        else:values.update(endedAt='',endedAtSource='unknown')
        values.update(trigger.get('arguments',{}))
    if kind==91150:
        values.update(subCounter=0,rollover=10,rolloverCount=1,broadcasterUserId=config.get('broadcaster_id',''),broadcasterUserName=login,broadcasterUser=login);values.update(trigger.get('arguments',{}))
    if kind in (90033,90034):
        from .twitch_pyramids import event_arguments
        owner={'userId':'test-owner','userName':'testowner','user':'Test Owner'}
        values.update(event_arguments(kind,values,{'emote':'Kappa','height':3,'users':{'test-owner'},'owner':owner},1));values.update(trigger.get('arguments',{}))
    if 91050<=kind<=91053:
        from .twitch_hype_train import variables
        values.update(variables({'id':'test-train','level':2,'total':700,'progress':200,'goal':500,'type':'regular','is_shared_train':False,'broadcaster_user_id':config.get('broadcaster_id',''),'broadcaster_user_login':login,'started_at':'2026-10-13T12:00:00Z','expires_at':'2026-10-13T12:05:00Z'}))
        if kind==91052:values['prevLevel']=1
        values.update(trigger.get('arguments',{}))
    if 91450<=kind<=91461:
        from .twitch_chat_modes import MODES
        values.update(broadcasterUserId=config.get('broadcaster_id',''),broadcasterUserName=login,broadcasterUser=login)
        for field,(variable,on,off,changed,duration) in MODES.items():
            values[variable]=kind in (on,changed)
        values.update(followerModeDuration=10 if values['followerMode'] else None,slowModeWaitTime=30 if values['slowMode'] else None)
        values.update(trigger.get('arguments',{}))
    if 92200<=kind<=92213:
        from .twitch_expansion_events import example
        values.update(example(kind,config,trigger));values.update(trigger.get('arguments',{}))
    if 92300<=kind<=92316:
        from .twitch_shared_chat import example
        values.update(example(kind,config,trigger));values.update(trigger.get('arguments',{}))
    if 92400<=kind<=92418:
        from .twitch_moderation_details import example
        values.update(example(kind,config,trigger));values.update(trigger.get('arguments',{}))
    if 92500<=kind<=92506:
        from .twitch_goals_bits import example
        values.update(example(kind,config,trigger));values.update(trigger.get('arguments',{}))
    if 92600<=kind<=92610:
        from .twitch_connections_whispers import example
        values.update(example(kind,config));values.update(trigger.get('arguments',{}))
    if 92700<=kind<=92705:
        from .twitch_polling_triggers import example
        values.update(example(kind,config));values.update(trigger.get('arguments',{}))
    if 92800<=kind<=92801:
        from .twitch_raid_lifecycle import example
        values.update(example(kind,config));values.update(trigger.get('arguments',{}))
    if 92900<=kind<=92902:
        from .twitch_reward_lifecycle import example
        values.update(example(kind,config));values.update(trigger.get('arguments',{}))
    if 93050<=kind<=93058:
        values.update(streamDeckClientId='test-client',streamDeckButtonId=trigger.get('buttonId') or 'test-button',streamDeckDeviceId=trigger.get('deviceId') or 'test-device',streamDeckTicks=1,streamDeckState=0,streamDeckEvent='test')
    if 94050<=kind<=94058:
        values.update(audioKind=trigger.get('audioKind') if trigger.get('audioKind') not in ('any','',None) else 'output',audioTarget=trigger.get('audioTarget') or 'test-audio',audioDeviceName='test-device',audioName='Test Audio',audioVolume=42,audioPreviousVolume=40,audioMuted=False,audioDefault=True,audioChannels=[27525])
    if kind==97050:values.update(webhookName=trigger.get('webhookName') or 'example',webhookData={'message':'Test webhook'})
    if kind==97250:values.update(instanceId=trigger.get('instanceId') or '00000000-0000-4000-8000-000000000001',instanceName='Test StreamerMod',instanceOs='linux',instanceVersion='StreamerMod-direct-1',eventName=trigger.get('eventName') or 'test')
    if kind==90041 and trigger.get('_originalEventFilter')==702:
        values.update(copy.deepcopy(trigger.get('variables',{})))
    values.update(isTest=True,triggerId=trigger['id'],triggerType=kind)
    from .event_context import arguments as event_arguments
    from .original_triggers import arguments as trigger_arguments
    return event_arguments(kind,trigger_arguments(trigger,values))
