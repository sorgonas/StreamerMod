"""Original-style category paths for the independent edition's implemented nodes."""
from .catalog import STEPS,TRIGGERS
from .csharp import DEFAULT_CODE

PATHS={
 4:'Core · Actions · Run Action',123:'Core · Arguments · Set Argument',
 1002:'Core · Delay',122:'Core · Globals · Global (Set)',121:'Core · Globals · Global (Get)',
 120:'Core · Logic · If/Else',124:'Core · Logic · Break',99900:'Core · Logic · Group',
 1009:'Core · Misc · Comment',90002:'Core · Network · Fetch URL',90003:'Core · System · Run a Program',
 602:'Core · Sounds · Text to Speech',90004:'Stream Apps · AI · Generate Response',
 90006:'Stream Apps · Camera · Linux Camera Effect',
 90010:'Core · Logic · Get Random Number',90011:'Core · Misc · Log',
 90012:'Core · File I/O · File Exists',90013:'Core · File I/O · Folder Exists',
 90014:'Core · File I/O · Read Lines From File',90015:'Core · File I/O · Read Random Line From File',
 90016:'Core · File I/O · Read Specific Line From File',90017:'Core · File I/O · Write To File',
 90018:'Core · Actions · Get Action State',90019:'Core · Actions · Set Action State',
 90020:'Stream Apps · Game Detection · Detect Running Game',
 90021:'Core · Commands · Get Commands',90022:'Core · Commands · Set Command State',
 90023:'Core · Commands · Set Command Group State',90024:'Core · Commands · Get Command Group State',
 90025:'Core · Commands · Get Command State',90026:'Core · Actions · Get Action Group State',
 90027:'Core · Actions · Set Action Group State',90028:'Core · Actions · Set Sub-Action State',
 90029:'Core · Actions · Set Sub-Action Weight',
 90050:'Core · Action Queues · Clear Action Queue',90051:'Core · Action Queues · Set Action Queue Pause State',
 90052:'Core · Action Queues · Set Action Queue Blocking State',
 90060:'Core · C# · Execute C# Code',90061:'Core · C# · Execute C# Method',
}
DEFAULTS={
 90006:{'effect':'Alt','duration':300,'sceneName':'-Overlay','sourceName':'Kamera','announce':False},
 90010:{'minimum':0,'maximum':100,'resultVariable':'randomNumber'},
 90011:{'text':'%rawInput%'},
 90012:{'path':'','resultVariable':'fileExists'},90013:{'path':'','resultVariable':'folderExists'},
 90014:{'path':'','resultVariable':'fileLines'},90015:{'path':'','resultVariable':'randomLine'},
 90016:{'path':'','line':0,'resultVariable':'fileLine'},90017:{'path':'','text':'%rawInput%','append':True},
 90018:{'actionId':'','resultVariable':'actionEnabled'},90019:{'actionId':'','state':True},
 90020:{'resultVariable':'detectedGame'},
 90021:{'group':'All','resultVariable':'commands','includeAll':False,'onlyHasPermission':False,'ignoreAliases':False},
 90022:{'commandId':'','state':'enabled'},90023:{'group':'','state':'enabled'},90024:{'group':''},
 90025:{'commandId':''},90026:{'group':''},90027:{'group':'','state':'enabled'},
 90028:{'actionId':'','subActionId':'','state':'enabled'},90029:{'actionId':'','subActionId':'','weight':1.0},
 90050:{'queueId':None},90051:{'queueId':None,'state':'pause','clear':False},90052:{'queueId':None,'state':'enabled'},
 90060:{'name':'','description':'','code':DEFAULT_CODE,'references':[],'precompile':False,'delayedStart':False,'saveResult':False,'resultVariable':'csharpResult','timeout':30},
 90061:{'codeId':'','method':'Execute','saveResult':False,'resultVariable':'csharpResult','timeout':30},
}

def steps():
    result={}
    for kind,(label,defaults) in STEPS.items():
        # Old explicit provider types still execute, but are no longer offered twice.
        if kind in (90006,90007,90008,90165,99900):continue
        if kind in PATHS:label=PATHS[kind]
        elif label.startswith('OBS · '):label='Stream Apps · OBS Studio · '+label.removeprefix('OBS · ')
        result[kind]=(label,defaults)
    from .menu_reference import apply_reference
    return apply_reference(result,"steps")

def triggers():
    result={402:TRIGGERS[402],**TRIGGERS}

    result[401]=('Core · Commands · Command Triggered',TRIGGERS[401][1])
    result[701]=('Core · Timed Actions',TRIGGERS[701][1])
    for kind in (14004,14005,14006):
        label,defaults=result[kind];result[kind]=('OBS Studio · '+label.removeprefix('OBS · '),defaults)
    from .menu_reference import apply_reference
    return apply_reference(result,"triggers")

# IDs are private Linux extension IDs; original serialized C# formats are not implied.
for kind,defaults in DEFAULTS.items():STEPS[kind]=(PATHS[kind],defaults)

for kind,label in {90030:'General · Stream Update',90031:'Subscriptions · Gift Sub',90032:'Subscriptions · Gift Bomb',90033:'Pyramid · Pyramid Success',90034:'Pyramid · Pyramid Broken'}.items():TRIGGERS[kind]=('Twitch · '+label,{})

TRIGGERS[90040]=('Core · StreamerMod Started',{})
TRIGGERS[90041]=('Core · Test',{})

from .core_catalog import ENTRIES,TRIGGER_ENTRIES
for kind,(label,defaults) in ENTRIES.items():STEPS[kind]=('Core · '+label,defaults)
for kind,value in TRIGGER_ENTRIES.items():TRIGGERS[kind]=value

from .obs_actions import ENTRIES as OBS_ENTRIES
for kind,(label,defaults) in OBS_ENTRIES.items():STEPS[kind]=("Stream Apps · OBS Studio · "+label,defaults)

from .obs_actions import EVENTS as OBS_EVENTS, OUTPUT_EVENTS as OBS_OUTPUT_EVENTS
for kind,label,defaults in OBS_EVENTS.values():TRIGGERS[kind]=("OBS Studio · "+label,dict(defaults))
for events in OBS_OUTPUT_EVENTS.values():
    for kind,label in events.values():TRIGGERS[kind]=("OBS Studio · "+label,{})

from .points_catalog import ENTRIES as POINT_ENTRIES
for kind,(label,defaults) in POINT_ENTRIES.items():STEPS[kind]=('Core · Points · '+label,defaults)

from .obs_actions import CONNECTION_TRIGGERS
for kind,(label,defaults) in CONNECTION_TRIGGERS.items():TRIGGERS[kind]=('OBS Studio · '+label,defaults)

from .obs_connections import OBS_TYPES
for kind in OBS_TYPES:
    if kind in STEPS:STEPS[kind][1].setdefault('obsConnection','default')
for kind,(label,defaults) in TRIGGERS.items():
    if label.startswith('OBS Studio · ') or label.startswith('OBS · '):defaults.setdefault('obsConnection','default')

from .twitch_rewards_catalog import ENTRIES as REWARD_ENTRIES,TRIGGERS as REWARD_TRIGGERS
for kind,(label,defaults) in REWARD_ENTRIES.items():STEPS[kind]=('Twitch · Rewards · '+label,defaults)
for kind,(label,defaults) in REWARD_TRIGGERS.items():TRIGGERS[kind]=('Twitch · Channel Reward · '+label,defaults)

from .twitch_votes_catalog import ENTRIES as VOTE_ENTRIES,TRIGGERS as VOTE_TRIGGERS
for kind,(label,defaults) in VOTE_ENTRIES.items():STEPS[kind]=('Twitch · '+label,defaults)
for kind,label in VOTE_TRIGGERS.items():TRIGGERS[kind]=('Twitch · '+label,{})

from .twitch_moderation_catalog import ENTRIES as MOD_ENTRIES,TRIGGERS as MOD_TRIGGERS
for kind,(label,defaults) in MOD_ENTRIES.items():STEPS[kind]=('Twitch · Moderation · '+label,defaults)
for kind,label in MOD_TRIGGERS.items():TRIGGERS[kind]=('Twitch · Moderation · '+label,{})

from .twitch_subscriptions_catalog import ENTRIES as SUB_ENTRIES,TRIGGERS as SUB_TRIGGERS,GIFT_DEFAULTS
for kind,(label,defaults) in SUB_ENTRIES.items():STEPS[kind]=('Twitch · Subscribers · '+label,defaults)
for kind,(label,defaults) in SUB_TRIGGERS.items():TRIGGERS[kind]=('Twitch · Subscriptions · '+label,defaults)
for kind,defaults in GIFT_DEFAULTS.items():TRIGGERS[kind][1].update(defaults)

from .twitch_ads_raids_catalog import ENTRIES as BROADCAST_ENTRIES,TRIGGERS as BROADCAST_TRIGGERS
for kind,(label,defaults) in BROADCAST_ENTRIES.items():STEPS[kind]=('Twitch · '+label,defaults)
for kind,label in BROADCAST_TRIGGERS.items():TRIGGERS[kind]=('Twitch · '+label,{})
TRIGGERS[107][1].update(rangeMin=-1,rangeMax=-1)

from .twitch_hype_train import TRIGGERS as HYPE_TRIGGERS
STEPS[91000]=('Twitch · Hype Train · Get Hype Train Status',{})
for kind,label in HYPE_TRIGGERS.items():TRIGGERS[kind]=('Twitch · Hype Train · '+label,{'rangeMin':-1,'rangeMax':-1} if kind==91052 else {})

STEPS[91100]=('Twitch · Sub Counter · Get Twitch Sub Counter Count',{})
STEPS[91101]=('Twitch · Sub Counter · Set Twitch Sub Counter Count',{'count':'0'})
TRIGGERS[91150]=('Twitch · Subscriptions · Sub Counter Rollover',{})
STEPS[91102]=('Twitch · Subscribers · Get Latest Subscriber',{})

from .twitch_channel import STEPS as CHANNEL_STEPS,TRIGGERS as CHANNEL_TRIGGERS
for kind,label in CHANNEL_STEPS.items():STEPS[kind]=('Twitch · '+('Followers' if kind in (91201,91202) else 'Channel')+' · '+label,{})
for kind,label in CHANNEL_TRIGGERS.items():TRIGGERS[kind]=('Twitch · Channel · '+label,{'rangeMin':-1,'rangeMax':-1} if kind==91252 else {})

from .twitch_channel_tools import ENTRIES as CHANNEL_TOOLS
for kind,(label,defaults) in CHANNEL_TOOLS.items():STEPS[kind]=('Twitch · '+label,defaults)

# Imported IDs remain stable; only the Action editor's category paths change.
for kind,path in {10:'Chat',15:'Channel',16:'Channel',18:'Channel',20:'Moderation',50:'User'}.items():
    label,defaults=STEPS[kind];STEPS[kind]=('Twitch · '+path+' · '+label.removeprefix('Twitch · '),defaults)
for kind,path in {101:'Channel',107:'Raid',112:'Channel Reward',120:'Chat',133:'Chat'}.items():
    label,defaults=TRIGGERS[kind];TRIGGERS[kind]=('Twitch · '+path+' · '+label.removeprefix('Twitch · '),defaults)

from .twitch_chat_modes import ENTRIES as CHAT_MODE_ENTRIES,TRIGGERS as CHAT_MODE_TRIGGERS
for kind,(label,defaults) in CHAT_MODE_ENTRIES.items():STEPS[kind]=('Twitch · Moderation · Chat Modes · '+label,defaults)
for kind,label in CHAT_MODE_TRIGGERS.items():TRIGGERS[kind]=('Twitch · Chat · Mode · '+label,{})

from .twitch_user_groups import ENTRIES as TWITCH_GROUP_ENTRIES
for kind,(label,defaults) in TWITCH_GROUP_ENTRIES.items():STEPS[kind]=('Twitch · User Groups · '+label,defaults)

from .twitch_user_info import ENTRIES as USER_INFO_ENTRIES
for kind,(label,defaults) in USER_INFO_ENTRIES.items():STEPS[kind]=('Twitch · User · '+label,defaults)

from .twitch_user_selection import ENTRIES as USER_SELECTION_ENTRIES
for kind,(label,defaults) in USER_SELECTION_ENTRIES.items():STEPS[kind]=('Twitch · User · '+label,defaults)

from .menu_reference import apply_reference
apply_reference(STEPS,"steps")
apply_reference(TRIGGERS,"triggers")


# The native status query is not in the 1.0.7 Twitch sub-action menu.
STEPS[91000]=('Stream Apps · Twitch · Get Hype Train Status',STEPS[91000][1])

from .twitch_chat_actions import ENTRIES as CHAT_ACTION_ENTRIES
for kind,(label,defaults) in CHAT_ACTION_ENTRIES.items():STEPS[kind]=('Twitch · Chat · '+label,defaults)

from .twitch_moderation_extended import ENTRIES as MODERATION_EXTENDED_ENTRIES
for kind,(label,defaults) in MODERATION_EXTENDED_ENTRIES.items():STEPS[kind]=('Twitch · Moderation · '+label,defaults)

from .twitch_queries import ENTRIES as TWITCH_QUERY_ENTRIES
for kind,(label,defaults) in TWITCH_QUERY_ENTRIES.items():STEPS[kind]=('Twitch · '+label,defaults)

from .twitch_guest_star import ENTRIES as GUEST_STAR_ENTRIES
for kind,(label,defaults) in GUEST_STAR_ENTRIES.items():STEPS[kind]=('Twitch · Guest Star · '+label,defaults)

from .twitch_expansion_events import ENTRIES as TWITCH_EXPANSION_TRIGGERS
for kind,(label,defaults) in TWITCH_EXPANSION_TRIGGERS.items():TRIGGERS[kind]=('Twitch · '+label,defaults)

from .twitch_shared_chat import ENTRIES as SHARED_CHAT_TRIGGERS
for kind,(label,defaults) in SHARED_CHAT_TRIGGERS.items():TRIGGERS[kind]=('Twitch · '+label,defaults)

from .twitch_polling_triggers import ENTRIES as POLLING_TRIGGERS
for kind,(label,defaults) in POLLING_TRIGGERS.items():TRIGGERS[kind]=('Twitch · '+label,defaults)

from .twitch_connections_whispers import ENTRIES as CONNECTION_WHISPER_TRIGGERS
for kind,(label,defaults) in CONNECTION_WHISPER_TRIGGERS.items():TRIGGERS[kind]=('Twitch · '+label,defaults)

from .twitch_goals_bits import ENTRIES as GOALS_BITS_TRIGGERS
for kind,(label,defaults) in GOALS_BITS_TRIGGERS.items():TRIGGERS[kind]=('Twitch · '+label,defaults)

from .twitch_moderation_details import ENTRIES as MODERATION_DETAIL_TRIGGERS
for kind,(label,defaults) in MODERATION_DETAIL_TRIGGERS.items():TRIGGERS[kind]=('Twitch · '+label,defaults)

from .twitch_raid_lifecycle import ENTRIES as RAID_LIFECYCLE_TRIGGERS
for kind,(label,defaults) in RAID_LIFECYCLE_TRIGGERS.items():TRIGGERS[kind]=('Twitch · '+label,defaults)

from .streamdeck_bridge import STEPS as DECK_STEPS,TRIGGERS as DECK_TRIGGERS
for kind,(label,defaults) in DECK_STEPS.items():STEPS[kind]=('Elgato · Stream Deck · '+label,defaults)
for kind,(label,defaults) in DECK_TRIGGERS.items():TRIGGERS[kind]=('Elgato · Stream Deck · '+label,defaults)

from .linux_audio import STEPS as AUDIO_STEPS,TRIGGERS as AUDIO_TRIGGERS
for kind,(label,defaults) in AUDIO_STEPS.items():STEPS[kind]=('Core · System · Linux Audio · '+label,defaults)
for kind,(label,defaults) in AUDIO_TRIGGERS.items():TRIGGERS[kind]=('Core · System · Linux Audio · '+label,defaults)

from .standard_settings import STEPS as SETTINGS_STEPS
for kind,(label,defaults) in SETTINGS_STEPS.items():STEPS[kind]=('Settings · '+label,defaults)

from .twitch_reward_lifecycle import ENTRIES as REWARD_LIFECYCLE_TRIGGERS
for kind,(label,defaults) in REWARD_LIFECYCLE_TRIGGERS.items():TRIGGERS[kind]=('Twitch · '+label,defaults)

from .youtube import STEPS as YOUTUBE_STEPS
from .youtube_events import TRIGGERS as YOUTUBE_TRIGGERS
for kind,(label,defaults) in YOUTUBE_STEPS.items():STEPS[kind]=('YouTube · '+label,defaults)
for kind,(label,defaults) in YOUTUBE_TRIGGERS.items():TRIGGERS[kind]=('YouTube · '+label,defaults)

STEPS[96005]=('Core · Misc · Send Chat Message',{'message':'Hallo %user%!','chatPlatform':'source','useBot':True})

from .youtube_users import STEPS as YOUTUBE_USER_STEPS
for kind,(label,defaults) in YOUTUBE_USER_STEPS.items():STEPS[kind]=('YouTube · '+label,defaults)

from .youtube_extras import STEPS as YOUTUBE_POLL_STEPS
for kind,(label,defaults) in YOUTUBE_POLL_STEPS.items():STEPS[kind]=('YouTube · '+label,defaults)

# Native local webhooks; no dependency on the Original's website service.
STEPS[97000]=('Core · Network · Send Custom Webhook',{'method':'POST','url':'http://127.0.0.1:7474/api/webhooks/example','body':{},'headers':{},'resultVariable':'webhookResult'})
TRIGGERS[97050]=('Integrations · StreamerMod · Custom Webhook',{'webhookName':''})

from .streamermod_catalog import STEPS as OWN_STEPS,TRIGGERS as OWN_TRIGGERS
for kind,(label,defaults) in OWN_STEPS.items():STEPS[kind]=('StreamerMod · '+label,defaults)
TRIGGERS.update(OWN_TRIGGERS)

from .discord_webhooks import KIND as DISCORD_WEBHOOK,DEFAULTS as DISCORD_DEFAULTS
STEPS[DISCORD_WEBHOOK]=('Integrations · Discord · Basic Webhook',DISCORD_DEFAULTS)

from .timed_effects import STEPS as TIMED_STEPS
STEPS.update(TIMED_STEPS)
