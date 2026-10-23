"""Chat-mode action steps and real setting-change events, without a platform page."""
import copy
import sqlite3
from contextlib import closing
from datetime import datetime,timezone
from .core import ActionError,expand
from .twitch_rewards import scopes,integer

WRITE_SCOPE='moderator:manage:chat_settings'
EVENT_SCOPE='user:read:chat'
EVENT_TYPE='channel.chat_settings.update'
ENTRIES={
    91400:('Emote Only',{'state':True}),
    91401:('Follow Mode',{'state':True,'duration':''}),
    91402:('Slow Mode',{'state':True,'duration':''}),
    91403:('Subscriber Only',{'state':True}),
}
TRIGGERS={
    91450:'Emote Mode On',91451:'Emote Mode Off',
    91452:'Follower Mode On',91453:'Follower Mode Off',91454:'Follower Mode Changed',
    91455:'Slow Mode On',91456:'Slow Mode Off',91457:'Slow Mode Changed',
    91458:'Subscriber Mode On',91459:'Subscriber Mode Off',
    91460:'Unique Mode On',91461:'Unique Mode Off',
}
FIELDS={91400:'emote_mode',91401:'follower_mode',91402:'slow_mode',91403:'subscriber_mode'}
MODES={
    'emote_mode':('emoteMode',91450,91451,None,None),
    'follower_mode':('followerMode',91452,91453,91454,'follower_mode_duration'),
    'slow_mode':('slowMode',91455,91456,91457,'slow_mode_wait_time'),
    'subscriber_mode':('subscriberMode',91458,91459,None,None),
    'unique_chat_mode':('uniqueMode',91460,91461,None,None),
}

def state(value):
    if isinstance(value,bool):return value
    if isinstance(value,str):
        text=value.strip().casefold()
        if text in ('true','on','yes','enabled','1'):return True
        if text in ('false','off','no','disabled','0'):return False
    raise ActionError('Chatmodus-State muss On/Off oder true/false sein')

def payload(node,args):
    kind=node.get('type')
    if kind not in FIELDS:raise ActionError('Unbekannter Chatmodus-Baustein')
    enabled=state(expand(node.get('state'),args));body={FIELDS[kind]:enabled}
    duration=expand(node.get('duration',''),args)
    if enabled and kind in (91401,91402) and duration not in ('',None):
        minimum,maximum,field=(0,129600,'follower_mode_duration') if kind==91401 else (3,120,'slow_mode_wait_time')
        value=integer(duration,minimum)
        if value>maximum:raise ActionError('Chatmodus-Dauer außerhalb des zulässigen Bereichs')
        body[field]=value
    return body

def normalized(row,event=False):
    if not isinstance(row,dict):raise ActionError('Ungültiger Chatmodus-Stand')
    result={}
    for field in MODES:
        if not isinstance(row.get(field),bool):raise ActionError('Unvollständiger Chatmodus-Stand')
        result[field]=row[field]
    for field,mode,low,high in [('follower_mode_duration','follower_mode',0,129600),('slow_mode_wait_time','slow_mode',3,120)]:
        source=field+('_minutes' if field.startswith('follower') else '_seconds') if event else field
        if not result[mode]:result[field]=None;continue
        value=integer(row.get(source),low)
        if value>high:raise ActionError('Ungültige Chatmodus-Dauer von Twitch')
        result[field]=value
    return result

def timestamp(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
        return result if result.tzinfo else None
    except (ValueError,TypeError,AttributeError):return None

class ChatModes:
    def __init__(self,io):
        self.io=io;self.previous=None;self.account=None;self.last_timestamp=None;self.cutoff=None
    def key(self):return self.io.config.get('broadcaster_id','')+'|'+self.io.config.get('twitch_client_id','')
    def require(self,write=False):
        if not all(self.io.config.get(k) for k in ('twitch_token','twitch_client_id','broadcaster_id')):raise ActionError('Broadcaster-Konto zuerst anmelden')
        if write and WRITE_SCOPE not in scopes(self.io.config):raise ActionError('Chatmodus-Schreibrecht fehlt. Die gemeinsame Broadcaster-Freigabe unter Accounts ergänzt die eingebauten Funktionen.')
    async def start_session(self):
        # Never infer current settings from a snapshot taken before a disconnect.
        self.previous=None;self.last_timestamp=None;self.cutoff=None;self.account=self.key()
        if self.io.dry_run:return
        self.require();cutoff=datetime.now(timezone.utc)
        result=await self.io.twitch('GET','chat/settings',params={'broadcaster_id':self.io.config['broadcaster_id']})
        rows=result.get('data',[])
        if not rows or rows[0].get('broadcaster_id')!=self.io.config['broadcaster_id']:raise ActionError('Twitch hat keinen passenden Chatmodus-Stand geliefert')
        self.previous=normalized(rows[0]);self.cutoff=cutoff
    async def change(self,node,args):
        body=payload(node,args)
        if self.io.dry_run:
            self.io.trace('twitch_chat_modes_preview',payload=body);args['isPreview']=True;return
        self.require(write=True);owner=self.io.config['broadcaster_id']
        result=await self.io.twitch('PATCH','chat/settings',body,params={'broadcaster_id':owner,'moderator_id':owner})
        rows=result.get('data',[])
        if not rows or rows[0].get('broadcaster_id')!=owner:raise ActionError('Twitch hat die Chatmodus-Änderung nicht bestätigt')
        confirmed=normalized(rows[0])
        if any(confirmed.get(field)!=value for field,value in body.items()):raise ActionError('Twitch hat einen abweichenden Chatmodus-Stand bestätigt')
        # Do not replace the event comparison baseline here: the real EventSub
        # notification must still be able to trigger the user's Actions.
    def ingest(self,event,identity,occurred_at=''):
        if self.io.dry_run:return []
        if not identity:raise ActionError('Chatmodus-Ereignis ohne Nachrichten-ID')
        if event.get('broadcaster_user_id')!=self.io.config.get('broadcaster_id'):return []
        current=normalized(event,event=True);key=self.key();stamp=timestamp(occurred_at)
        if self.account!=key:self.previous=None;self.account=key;self.last_timestamp=None;self.cutoff=None
        if stamp and ((self.cutoff and stamp<self.cutoff) or (self.last_timestamp and stamp<self.last_timestamp)):return []
        path=self.io.root/'state/twitch-chat-modes.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(path,timeout=10)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS chat_mode_seen(account TEXT,message TEXT,stamp INTEGER PRIMARY KEY AUTOINCREMENT,UNIQUE(account,message))');path.chmod(0o600)
            with db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT 1 FROM chat_mode_seen WHERE account=? AND message=?',(key,identity)).fetchone():return []
                db.execute('INSERT INTO chat_mode_seen(account,message) VALUES(?,?)',(key,identity))
                db.execute('DELETE FROM chat_mode_seen WHERE account=? AND stamp NOT IN (SELECT stamp FROM chat_mode_seen WHERE account=? ORDER BY stamp DESC LIMIT 10000)',(key,key))
        previous=self.previous;self.previous=current
        if stamp:self.last_timestamp=stamp
        if previous is None:return [] # Unknown baseline is not an On/Off transition.
        values={'userType':'twitch','platform':'twitch','broadcasterUserId':event.get('broadcaster_user_id',''),'broadcasterUserName':event.get('broadcaster_user_login',''),'broadcasterUser':event.get('broadcaster_user_name',''),'messageId':identity,'occurredAt':occurred_at}
        values.update({definition[0]:current[field] for field,definition in MODES.items()})
        values.update(followerModeDuration=current['follower_mode_duration'],slowModeWaitTime=current['slow_mode_wait_time'])
        output=[]
        for field,(_,on,off,changed,duration) in MODES.items():
            transition=previous[field]!=current[field]
            if transition:output.append((on if current[field] else off,copy.deepcopy(values)))
            if changed and (transition or previous[duration]!=current[duration]):output.append((changed,copy.deepcopy(values)))
        return output

async def operation(io,node,args):await ChatModes(io).change(node,args)
