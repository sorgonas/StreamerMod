"""Original trigger routes for charity, Guest Star, shield, warning and shoutout."""
import copy,re,sqlite3,time
from contextlib import closing
from decimal import Decimal,InvalidOperation
from .core import ActionError
from .twitch_queries import money
from .twitch_user_info import UserInfo
ENTRIES={
92200:('Moderation · Shield Mode Begin',{}),92201:('Moderation · Shield Mode End',{}),
92202:('Moderation · Warned User',{}),92203:('Moderation · Warning Acknowledged',{}),
92204:('Moderation · Shoutout Created',{}),92205:('General · Shoutout Received',{}),
92206:('Charity · Charity Started',{}),92207:('Charity · Charity Progress',{}),92208:('Charity · Charity Completed',{}),92209:('Charity · Charity Donation',{'rangeMin':-1.0,'rangeMax':-1.0}),
92210:('Guest Star · Guest Star Session Begin',{}),92211:('Guest Star · Guest Star Session End',{}),92212:('Guest Star · Guest Star Guest Update',{'state':'Any'}),92213:('Guest Star · Guest Star Settings Update',{}),
}
TYPES=['channel.shield_mode.begin','channel.shield_mode.end','channel.warning.send','channel.warning.acknowledge','channel.shoutout.create','channel.shoutout.receive','channel.charity_campaign.start','channel.charity_campaign.progress','channel.charity_campaign.stop','channel.charity_campaign.donate','channel.guest_star_session.begin','channel.guest_star_session.end','channel.guest_star_guest.update','channel.guest_star_settings.update']
MAP=dict(zip(TYPES,ENTRIES));STATES=('selected','backstage','invited','live','ready','removed')
def required(kind):
 if kind.startswith('channel.shield_mode.'):return {'moderator:read:shield_mode','moderator:manage:shield_mode'}
 if kind.startswith('channel.warning.'):return {'moderator:read:warnings','moderator:manage:warnings'}
 if kind.startswith('channel.shoutout.'):return {'moderator:read:shoutouts','moderator:manage:shoutouts'}
 if kind.startswith('channel.charity_campaign.'):return {'channel:read:charity'}
 return {'channel:read:guest_star','channel:manage:guest_star'}
def subscriptions(broadcaster):
 for kind in TYPES:
  condition={'broadcaster_user_id':broadcaster}
  if not kind.startswith('channel.charity_campaign.'):condition['moderator_user_id']=broadcaster
  yield kind,('beta' if 'guest_star' in kind else '1'),condition

def string(event,key,allow_empty=False,nullable=False):
 value=event.get(key)
 if nullable and value is None:return None
 if not isinstance(value,str) or not allow_empty and not value:raise ActionError('Twitch-Ereignisfeld fehlt oder ist ungültig: '+key)
 return value

def boolean(event,key,nullable=False):
 value=event.get(key)
 if nullable and value is None:return None
 if type(value) is not bool:raise ActionError('Ungültiges Twitch-Ereignisfeld: '+key)
 return value

def count(event,key,maximum=None,nullable=False):
 value=event.get(key)
 if nullable and value is None:return None
 if type(value) is not int or value<0 or maximum is not None and value>maximum:raise ActionError('Ungültiger Twitch-Ereigniszähler: '+key)
 return value

def person(event,prefix,nullable=False):
 return {'Id':string(event,prefix+'id',nullable=nullable),'Name':string(event,prefix+'login',nullable=nullable),'':string(event,prefix+'name',nullable=nullable)}
def put_user(args,who):args.update(userId=who['Id'],userName=who['Name'],userLogin=who['Name'],user=who[''])
def amount(args,prefix,value):
 value=money(value);args.update({prefix+'.value':value['value']/10**value['decimal_places'],prefix+'.valueMinor':value['value'],prefix+'.currency':value['currency'],prefix+'.decimalPlaces':value['decimal_places']})

def variables(kind,event):
 if kind not in MAP or not isinstance(event,dict):raise ActionError('Unbekanntes Twitch-Ereignis')
 owner='broadcaster_' if 'broadcaster_id' in event else 'broadcaster_user_'
 broad=person(event,owner);args={'platform':'twitch','userType':'twitch','broadcasterUserId':broad['Id'],'broadcasterUserName':broad['Name'],'broadcasterUser':broad['']}
 if kind.startswith('channel.shield_mode.'):
  mod=person(event,'moderator_user_');args.update(moderatorId=mod['Id'],moderatorLogin=mod['Name'],moderatorName=mod['']);args['startedAt' if kind.endswith('.begin') else 'endedAt']=string(event,'started_at' if kind.endswith('.begin') else 'ended_at')
 elif kind.startswith('channel.warning.'):
  put_user(args,person(event,'user_'))
  if kind.endswith('.send'):
   mod=person(event,'moderator_user_');args.update({'moderator.userName':mod[''],'moderator.login':mod['Name'],'moderator.id':mod['Id']})
   reason=event.get('reason');rules=event.get('chat_rules_cited')
   if reason is not None and not isinstance(reason,str) or rules is not None and (not isinstance(rules,list) or any(not isinstance(r,str) for r in rules)):raise ActionError('Ungültiger Warnungsgrund oder Chatregeln')
   args.update(reason=reason,chatRulesCited=rules)
 elif kind.startswith('channel.shoutout.'):
  args.update(viewerCount=count(event,'viewer_count'),startedAt=string(event,'started_at'))
  if kind.endswith('.create'):
   put_user(args,person(event,'moderator_user_'));target=person(event,'to_broadcaster_user_');args.update(targetUserId=target['Id'],targetUserLogin=target['Name'],targetUserDisplayName=target[''],cooldownEndsAt=string(event,'cooldown_ends_at'),targetCooldownEndsAt=string(event,'target_cooldown_ends_at'))
   # EventSub has no shoutout ID. Never replace it with a delivery ID.
  else:put_user(args,person(event,'from_broadcaster_user_'))
 elif kind.startswith('channel.charity_campaign.'):
  for remote,native in [('charity_name','name'),('charity_description','description'),('charity_logo','logo'),('charity_website','website')]:args['charity.'+native]=string(event,remote,True)
  if kind.endswith('.donate'):
   put_user(args,person(event,'user_'));args['charity.campaignId']=string(event,'campaign_id');args['charity.donationId']=string(event,'id');amount(args,'charity.amount',event.get('amount'))
  else:
   args['charity.id']=string(event,'id');amount(args,'charity.currentAmount',event.get('current_amount'))
   if 'target_amount' not in event:raise ActionError('Charity-Zielangabe fehlt')
   if event['target_amount'] is None:
    for field in ('value','valueMinor','currency','decimalPlaces'):args['charity.targetAmount.'+field]=None
   else:amount(args,'charity.targetAmount',event['target_amount'])
   if kind.endswith('.start'):args['charity.startedAt']=string(event,'started_at')
   if kind.endswith('.stop'):args['charity.stoppedAt']=string(event,'stopped_at')
 elif 'guest_star' in kind:
  if kind=='channel.guest_star_settings.update':
   raw=string(event,'group_layout').lower();layout=raw.removesuffix('_layout')
   if layout not in ('tiled','screenshare','horizontal','vertical','horizontal_top','horizontal_bottom','vertical_left','vertical_right'):raise ActionError('Ungültiges Guest-Star-Layout')
   args.update(isModeratorSendLiveEnabled=boolean(event,'is_moderator_send_live_enabled'),slotCount=count(event,'slot_count',6),isBrowserSourceAudioEnabled=boolean(event,'is_browser_source_audio_enabled'),groupLayout=layout)
  else:
   args['sessionId']=string(event,'session_id')
   if kind=='channel.guest_star_guest.update':
    mod=person(event,'moderator_user_',True);guest=person(event,'guest_user_',True);put_user(args,guest)
    args.update(moderatorUserName=mod[''],moderatorUserLogin=mod['Name'],moderatorUserId=mod['Id'],guestUserName=guest[''],guestUserLogin=guest['Name'],guestUserId=guest['Id'],slotId=string(event,'slot_id',nullable=True),state=(string(event,'state',nullable=True) or '').lower() or None,hostVideoEnabled=boolean(event,'host_video_enabled',True),hostAudioEnabled=boolean(event,'host_audio_enabled',True),hostVolume=count(event,'host_volume',100,True))
    if args['state'] is not None and args['state'] not in (*STATES,'accepted'):raise ActionError('Ungültiger Guest-Star-Gastzustand')
   else:
    args['startedAt']=string(event,'started_at')
    if kind.endswith('.end'):args['endedAt']=string(event,'ended_at')
 return MAP[kind],args

class Events:
 def __init__(self,io):self.io=io;self.cache=UserInfo(io)
 def db(self):
  path=self.io.root/'state/twitch-event-receipts.sqlite3';path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(path,timeout=10);path.chmod(0o600);db.execute('CREATE TABLE IF NOT EXISTS receipts(account TEXT,kind TEXT,identity TEXT,received REAL,PRIMARY KEY(account,kind,identity))');return db
 def invalidate(self,kind):
  if not (self.io.root/'state/twitch-user-info.sqlite3').exists():return
  key='|'.join(self.cache.account())
  with closing(self.cache.db()) as db:
   with db:
    if 'guest_star' in kind:db.execute("DELETE FROM info_cache WHERE account=? AND kind LIKE 'guest-star-%'",(key,))
    elif 'charity_campaign' in kind:db.execute("DELETE FROM info_cache WHERE account=? AND kind='charity'",(key,))
    elif 'shield_mode' in kind:db.execute("DELETE FROM info_cache WHERE account=? AND kind='shield-mode'",(key,))
 def ingest(self,kind,event,identity):
  if self.io.dry_run:return None
  owner=event.get('broadcaster_user_id',event.get('broadcaster_id')) if isinstance(event,dict) else None
  if owner!=self.io.config.get('broadcaster_id'):return None
  if not isinstance(identity,str) or not identity:raise ActionError('EventSub-Zustellungs-ID fehlt')
  trigger,args=variables(kind,event)
  return self.commit(kind,identity,trigger,args)
 def commit(self,kind,identity,trigger,args):
  if self.io.dry_run or args.get('broadcasterUserId')!=self.io.config.get('broadcaster_id'):return None
  if not isinstance(identity,str) or not identity:raise ActionError('EventSub-Zustellungs-ID fehlt')
  account='|'.join(self.cache.account())
  with closing(self.db()) as db:
   with db:
    changed=db.execute('INSERT OR IGNORE INTO receipts VALUES(?,?,?,?)',(account,kind,identity,time.time())).rowcount
    if not changed:return None
    db.execute('DELETE FROM receipts WHERE account=? AND rowid NOT IN (SELECT rowid FROM receipts WHERE account=? ORDER BY received DESC,rowid DESC LIMIT 5000)',(account,account))
  try:self.invalidate(kind)
  except (sqlite3.Error,OSError):self.io.trace('twitch_event_cache_error',message='Ereignis bestätigt; alter Vorschau-Cache konnte nicht verworfen werden.')
  args.setdefault('messageId',identity);args['eventSubMessageId']=identity;return trigger,args

def matches(kind,trigger,args):
 if kind==92212:
  state=trigger.get('state','Any')
  if not isinstance(state,str) or state.lower() not in ('any',*STATES):raise ActionError('Ungültiger Guest-Star-Zustandsfilter')
  return state.lower()=='any' or args.get('state') in (('accepted','selected') if state.lower()=='selected' else (state.lower(),))
 if kind==92209:
  amount_value=args.get('charity.amount.value')
  if isinstance(amount_value,bool) or not isinstance(amount_value,(int,float,Decimal)):return False
  try:
   minor=args.get('charity.amount.valueMinor');places=args.get('charity.amount.decimalPlaces')
   amount_decimal=Decimal(minor).scaleb(-places) if type(minor) is int and type(places) is int and 0<=places<=9 else Decimal(str(amount_value))
   if not amount_decimal.is_finite():return False
   for key,lower in [('rangeMin',True),('rangeMax',False)]:
    raw=trigger.get(key,-1)
    if isinstance(raw,bool):raise ValueError()
    boundary=Decimal(str(raw))
    if not boundary.is_finite() or boundary<0 and boundary!=-1:raise ValueError()
    if boundary!=-1 and (amount_decimal<boundary if lower else amount_decimal>boundary):return False
  except (ValueError,InvalidOperation):raise ActionError('Charity-Range: -1 oder nichtnegative Beträge in Hauptwährungseinheiten') from None
 return True

# Synthetic manual contexts derived from the public Twitch notification examples.
EXAMPLES={'channel.guest_star_session.begin': {'broadcaster_user_id': '1337', 'broadcaster_user_name': 'Cool_User', 'broadcaster_user_login': 'cool_user', 'moderator_user_id': '1338', 'moderator_user_name': 'Cool_Mod', 'moderator_user_login': 'cool_mod', 'session_id': '2KFRQbFtpmfyD3IevNRnCzOPRJI', 'started_at': '2023-04-11T16:20:03.17106713Z'}, 'channel.guest_star_session.end': {'broadcaster_user_id': '1337', 'broadcaster_user_name': 'Cool_User', 'broadcaster_user_login': 'cool_user', 'moderator_user_id': '1338', 'moderator_user_name': 'Cool_Mod', 'moderator_user_login': 'cool_mod', 'session_id': '2KFRQbFtpmfyD3IevNRnCzOPRJI', 'started_at': '2023-04-11T16:20:03.17106713Z', 'ended_at': '2023-04-11T17:51:29.153485Z'}, 'channel.guest_star_guest.update': {'broadcaster_user_id': '1337', 'broadcaster_user_name': 'Cool_User', 'broadcaster_user_login': 'cool_user', 'session_id': '2KFRQbFtpmfyD3IevNRnCzOPRJI', 'moderator_user_id': '1312', 'moderator_user_name': 'Cool_Mod', 'moderator_user_login': 'cool_mod', 'guest_user_id': '1234', 'guest_user_name': 'Cool_Guest', 'guest_user_login': 'cool_guest', 'slot_id': '1', 'state': 'live', 'host_video_enabled': True, 'host_audio_enabled': True, 'host_volume': 100}, 'channel.guest_star_settings.update': {'broadcaster_user_id': '1337', 'broadcaster_user_name': 'Cool_User', 'broadcaster_user_login': 'cool_user', 'is_moderator_send_live_enabled': True, 'slot_count': 5, 'is_browser_source_audio_enabled': True, 'group_layout': 'tiled'}, 'channel.warning.acknowledge': {'broadcaster_user_id': '423374343', 'broadcaster_user_login': 'glowillig', 'broadcaster_user_name': 'glowillig', 'user_id': '141981764', 'user_login': 'twitchdev', 'user_name': 'TwitchDev'}, 'channel.warning.send': {'broadcaster_user_id': '423374343', 'broadcaster_user_login': 'glowillig', 'broadcaster_user_name': 'glowillig', 'moderator_user_id': '424596340', 'moderator_user_login': 'quotrok', 'moderator_user_name': 'quotrok', 'user_id': '141981764', 'user_login': 'twitchdev', 'user_name': 'TwitchDev', 'reason': 'cut it out', 'chat_rules_cited': None}, 'channel.charity_campaign.donate': {'id': 'a1b2c3-aabb-4455-d1e2f3', 'campaign_id': '123-abc-456-def', 'broadcaster_user_id': '123456', 'broadcaster_user_name': 'SunnySideUp', 'broadcaster_user_login': 'sunnysideup', 'user_id': '654321', 'user_login': 'generoususer1', 'user_name': 'GenerousUser1', 'charity_name': 'Example name', 'charity_description': 'Example description', 'charity_logo': 'https://abc.cloudfront.net/ppgf/1000/100.png', 'charity_website': 'https://www.example.com', 'amount': {'value': 10000, 'decimal_places': 2, 'currency': 'USD'}}, 'channel.charity_campaign.start': {'id': '123-abc-456-def', 'broadcaster_id': '123456', 'broadcaster_name': 'SunnySideUp', 'broadcaster_login': 'sunnysideup', 'charity_name': 'Example name', 'charity_description': 'Example description', 'charity_logo': 'https://abc.cloudfront.net/ppgf/1000/100.png', 'charity_website': 'https://www.example.com', 'current_amount': {'value': 0, 'decimal_places': 2, 'currency': 'USD'}, 'target_amount': {'value': 1500000, 'decimal_places': 2, 'currency': 'USD'}, 'started_at': '2022-07-26T17:00:03.17106713Z'}, 'channel.charity_campaign.progress': {'id': '123-abc-456-def', 'broadcaster_id': '123456', 'broadcaster_name': 'SunnySideUp', 'broadcaster_login': 'sunnysideup', 'charity_name': 'Example name', 'charity_description': 'Example description', 'charity_logo': 'https://abc.cloudfront.net/ppgf/1000/100.png', 'charity_website': 'https://www.example.com', 'current_amount': {'value': 260000, 'decimal_places': 2, 'currency': 'USD'}, 'target_amount': {'value': 1500000, 'decimal_places': 2, 'currency': 'USD'}}, 'channel.charity_campaign.stop': {'id': '123-abc-456-def', 'broadcaster_id': '123456', 'broadcaster_name': 'SunnySideUp', 'broadcaster_login': 'sunnysideup', 'charity_name': 'Example name', 'charity_description': 'Example description', 'charity_logo': 'https://abc.cloudfront.net/ppgf/1000/100.png', 'charity_website': 'https://www.example.com', 'current_amount': {'value': 1450000, 'decimal_places': 2, 'currency': 'USD'}, 'target_amount': {'value': 1500000, 'decimal_places': 2, 'currency': 'USD'}, 'stopped_at': '2022-07-26T22:00:03.17106713Z'}, 'channel.shield_mode.begin': {'broadcaster_user_id': '12345', 'broadcaster_user_name': 'SimplySimple', 'broadcaster_user_login': 'simplysimple', 'moderator_user_id': '98765', 'moderator_user_name': 'ParticularlyParticular123', 'moderator_user_login': 'particularlyparticular123', 'started_at': '2022-07-26T17:00:03.17106713Z'}, 'channel.shield_mode.end': {'broadcaster_user_id': '12345', 'broadcaster_user_name': 'SimplySimple', 'broadcaster_user_login': 'simplysimple', 'moderator_user_id': '98765', 'moderator_user_name': 'ParticularlyParticular123', 'moderator_user_login': 'particularlyparticular123', 'ended_at': '2022-07-27T01:30:23.17106713Z'}, 'channel.shoutout.create': {'broadcaster_user_id': '12345', 'broadcaster_user_name': 'SimplySimple', 'broadcaster_user_login': 'simplysimple', 'moderator_user_id': '98765', 'moderator_user_name': 'ParticularlyParticular123', 'moderator_user_login': 'particularlyparticular123', 'to_broadcaster_user_id': '626262', 'to_broadcaster_user_name': 'SandySanderman', 'to_broadcaster_user_login': 'sandysanderman', 'started_at': '2022-07-26T17:00:03.17106713Z', 'viewer_count': 860, 'cooldown_ends_at': '2022-07-26T17:02:03.17106713Z', 'target_cooldown_ends_at': '2022-07-26T18:00:03.17106713Z'}, 'channel.shoutout.receive': {'broadcaster_user_id': '626262', 'broadcaster_user_name': 'SandySanderman', 'broadcaster_user_login': 'sandysanderman', 'from_broadcaster_user_id': '12345', 'from_broadcaster_user_name': 'SimplySimple', 'from_broadcaster_user_login': 'simplysimple', 'viewer_count': 860, 'started_at': '2022-07-26T17:00:03.17106713Z'}}
def example(kind,config,trigger=None):
 trigger=trigger or {};event=copy.deepcopy(EXAMPLES[TYPES[kind-92200]])
 owner='broadcaster_' if 'broadcaster_id' in event else 'broadcaster_user_'
 event[owner+'id']=config.get('broadcaster_id') or 'test-broadcaster';event[owner+'login']=config.get('twitch_login') or 'testbroadcaster';event[owner+'name']=config.get('twitch_login') or 'Test Broadcaster'
 if kind==92212 and trigger.get('state','Any')!='Any':event['state']='accepted' if trigger['state']=='Selected' else trigger['state'].lower()
 if kind==92209:
  minimum=trigger.get('rangeMin',-1)
  try:
   if Decimal(str(minimum))>=0:event['amount']['value']=int(Decimal(str(minimum))*100)
  except (ValueError,InvalidOperation):pass
 return variables(TYPES[kind-92200],event)[1]
