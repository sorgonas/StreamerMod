"""Public-client Twitch Device OAuth; credentials never leave the runtime result."""
import asyncio
import time
import aiohttp
from urllib.parse import urlparse
from .catalog import ConfigStore
from .core import ActionError

BROADCASTER_SCOPES='user:read:chat user:write:chat moderator:read:followers channel:read:redemptions channel:manage:redemptions moderator:read:chatters channel:manage:broadcast clips:edit moderator:manage:banned_users'
# All account-specific CPH bot writes are bundled in one Bot authorization.
BOT_SCOPES='user:read:chat user:write:chat user:manage:whispers moderator:manage:announcements moderator:manage:chat_messages moderator:manage:banned_users'
FEATURE_SCOPES={'whispers':{'user:read:whispers'},'goals_bits':{'bits:read','channel:read:goals'},'moderation_events':{'moderator:read:blocked_terms','moderator:read:unban_requests','moderator:read:moderators','moderator:read:vips','moderator:manage:automod','moderator:read:suspicious_users'},'guest_star':{'channel:read:guest_star','channel:manage:guest_star'},'queries_shoutout':{'channel:read:charity','channel:manage:clips','moderator:manage:shoutouts'},'moderation_extended':{'moderator:read:shield_mode', 'moderator:manage:suspicious_users', 'moderator:manage:shield_mode', 'moderator:manage:warnings'},'chat_actions':{'moderator:manage:chat_messages','moderator:manage:announcements'},'hype_train':{'channel:read:hype_train'},'ads':{'channel:read:ads','channel:manage:ads','channel:edit:commercial'},'raids':{'channel:manage:raids'},'subscriptions':{'channel:read:subscriptions'},'polls':{'channel:manage:polls'},'predictions':{'channel:manage:predictions'},'chat_modes':{'moderator:manage:chat_settings'},'moderation':{'channel:moderate','moderation:read','channel:manage:vips','channel:manage:moderators'}}

FEATURE_LABELS={'whispers':'Broadcaster-Whispers','goals_bits':'Kanalziele, Cheers und Power-ups','moderation_events':'AutoMod, Moderationsereignisse, Entsperranträge und verdächtige Nutzer','guest_star':'Guest Star','queries_shoutout':'Charity, Clip-Download-URLs und Shoutouts','moderation_extended':'Shield Mode, Warnungen und verdächtige Nutzer','chat_actions':'Chat-Nachrichten, Pins und Ankündigungen','chat_modes':'Chatmodi','hype_train':'Hype Train','ads':'Werbung','raids':'Raids','subscriptions':'Abonnements','polls':'Polls','predictions':'Predictions','moderation':'Moderation'}
FEATURE_SCOPES['csharp_api']={'user:manage:blocked_users','moderator:manage:blocked_terms','user:manage:whispers'}
FEATURE_LABELS['csharp_api']='C#-API: Nutzer blockieren, blockierte Begriffe und Whispers senden'
# The user requested one bundled authorization for the remaining Twitch work.
# These are explicitly planned rights, not a claim that the features exist.
PLANNED_SCOPES={}
PLANNED_LABELS={}
def broadcaster_scopes():return set(BROADCASTER_SCOPES.split()) | set().union(*FEATURE_SCOPES.values(),*PLANNED_SCOPES.values())
def missing_permissions(config):
 from .twitch_rewards import scopes
 return broadcaster_scopes()-scopes(config)

class TwitchOAuth:
    def __init__(self,session,root,config,on_authenticated=None):
        self.session=session;self.store=ConfigStore(root);self.config=config;self.pending={};self.locks={False:asyncio.Lock(),True:asyncio.Lock()}
        self.states={};self.on_authenticated=on_authenticated;self.authenticated_identity=None

    async def authenticated(self,bot,account,force=False):
        if bot:return
        identity=(self.config.get('twitch_client_id'),account['user_id'])
        if not force and identity==self.authenticated_identity:return
        self.authenticated_identity=identity
        if self.on_authenticated:await self.on_authenticated(account)

    def account_states(self):
        result={}
        for bot in (False,True):
            token=self.config.get(self.keys(bot)[0],'');login=self.config.get(self.keys(bot)[3],'')
            saved=self.states.get(bot,{})
            current=saved if token and saved.get('_token')==token else {'state':'unverified' if token else 'disconnected'}
            result[bot]={k:v for k,v in current.items() if k!='_token'}
            result[bot]['login']=login
        return result

    def confirmed(self,bot,account):
        self.states[bot]={'state':'valid','login':account['login'],'scopes':account.get('scopes',[]),'_token':self.config[self.keys(bot)[0]]}

    @staticmethod
    def keys(bot):
        return ('twitch_bot_token','twitch_bot_refresh_token','bot_id','twitch_bot_login') if bot else ('twitch_token','twitch_refresh_token','broadcaster_id','twitch_login')

    async def request(self,path,data=None,token=None):
        if token is not None:
            context=self.session.get('https://id.twitch.tv/oauth2/'+path,headers={'Authorization':'OAuth '+token})
        else:context=self.session.post('https://id.twitch.tv/oauth2/'+path,data=data)
        async with context as response:
            try:body=await response.json()
            except (ValueError,TypeError):raise ActionError('Ungültige Antwort vom Twitch-Anmeldedienst') from None
            return response.status,body

    async def begin(self,bot,features=()):
        client=self.config.get('twitch_client_id','').strip()
        if not client or client in ('Sorgonas','Sorgobot'):
            raise ActionError('Zuerst eine registrierte Twitch Client-ID unter Accounts > Application Setup eintragen.')
        if not isinstance(features,(list,tuple)) or set(features)-set(FEATURE_SCOPES) or (bot and features):raise ActionError('Ungültige Twitch-Freigabeauswahl')
        scopes=BOT_SCOPES if bot else BROADCASTER_SCOPES
        if not bot:
            scopes=' '.join(sorted(broadcaster_scopes()))
        status,body=await self.request('device',{'client_id':client,'scopes':scopes})
        if status!=200:raise ActionError('Twitch-Anmeldung konnte nicht gestartet werden. Registrierte Public-Client-ID prüfen.')
        url=body.get('verification_uri','');parsed=urlparse(url)
        if parsed.scheme!='https' or parsed.hostname!='www.twitch.tv' or parsed.path!='/activate':
            raise ActionError('Twitch hat eine unerwartete Anmeldeadresse geliefert')
        interval=max(1,int(body['interval']))
        self.pending[bot]={'client':client,'scopes':scopes,'code':body['device_code'],'deadline':time.monotonic()+int(body['expires_in']),'interval':interval,'next':time.monotonic()+interval}
        return {'bot':bot,'state':'pending','url':url,'code':body['user_code'],'interval':interval}

    def cancel(self,bot):self.pending.pop(bot,None)

    async def poll(self,bot):
        pending=self.pending.get(bot)
        if not pending:return {'bot':bot,'state':'cancelled'}
        if pending['client']!=self.config.get('twitch_client_id') or time.monotonic()>=pending['deadline']:
            self.cancel(bot);raise ActionError('Twitch-Anmeldung abgelaufen. Login erneut starten.')
        if time.monotonic()<pending['next']:return {'bot':bot,'state':'pending','interval':pending['interval']}
        pending['next']=time.monotonic()+pending['interval']
        status,body=await self.request('token',{'client_id':pending['client'],'scopes':pending['scopes'],'device_code':pending['code'],'grant_type':'urn:ietf:params:oauth:grant-type:device_code'})
        if self.pending.get(bot) is not pending:return {'bot':bot,'state':'cancelled'}
        if status!=200:
            reason=body.get('message',body.get('error',''))
            if reason=='authorization_pending':return {'bot':bot,'state':'pending','interval':pending['interval']}
            if reason=='slow_down':
                pending['interval']+=5;pending['next']=time.monotonic()+pending['interval'];return {'bot':bot,'state':'pending','interval':pending['interval']}
            self.cancel(bot);raise ActionError('Twitch-Anmeldung abgelehnt oder abgelaufen. Login erneut starten.')
        status,account=await self.request('validate',token=body['access_token'])
        if self.pending.get(bot) is not pending:return {'bot':bot,'state':'cancelled'}
        if status!=200 or account.get('client_id')!=pending['client']:
            self.cancel(bot);raise ActionError('Twitch-Anmeldung konnte nicht validiert werden')
        self.save(bot,body,account);self.cancel(bot)
        await self.authenticated(bot,account,True)
        return {'bot':bot,'state':'connected','login':account['login'],'userId':account['user_id'],'scopes':account.get('scopes',[])}

    def save(self,bot,tokens,account):
        token,refresh,uid,login=self.keys(bot)
        changes={token:tokens['access_token'],uid:account['user_id'],login:account['login'],'twitch_bot_scopes' if bot else 'twitch_scopes':account.get('scopes',[])}
        if 'refresh_token' in tokens:changes[refresh]=tokens['refresh_token']
        if not bot:changes['channel']=account['login']
        self.config.update(self.store.update('local.json',changes))
        self.confirmed(bot,account)

    async def validate(self,bot):
        async with self.locks[bot]:
            token=self.config.get(self.keys(bot)[0],'')
            if self.account_states()[bot]['state']!='valid':self.states[bot]={'state':'checking','_token':token}
            try:return await self._validate(bot)
            except (ActionError,aiohttp.ClientError,OSError,asyncio.TimeoutError,KeyError,TypeError,ValueError) as exc:
                if self.config.get(self.keys(bot)[0],'')==token:
                    self.states[bot]={'state':'unverified','_token':token,'message':str(exc) if isinstance(exc,ActionError) else 'Kontoprüfung momentan nicht erreichbar'}
                raise

    async def _validate(self,bot):
        token,refresh,uid,login=self.keys(bot);original=self.config.get(token,'')
        if not original:raise ActionError('Dieses Twitch-Konto ist nicht angemeldet')
        status,account=await self.request('validate',token=original)
        if status==401 or (status==200 and account.get('expires_in',3600)<1800):
            refresh_token=self.config.get(refresh,'')
            if refresh_token:
                response,tokens=await self.request('token',{'grant_type':'refresh_token','refresh_token':refresh_token,'client_id':self.config['twitch_client_id']})
                if response!=200:raise ActionError('Twitch-Anmeldung abgelaufen. Bitte erneut Login wählen.')
                response,account=await self.request('validate',token=tokens['access_token'])
                if response!=200 or account.get('client_id')!=self.config.get('twitch_client_id'):raise ActionError('Erneuerte Twitch-Anmeldung konnte nicht validiert werden')
                if self.config.get(token)!=original:raise ActionError('Twitch-Konto wurde inzwischen geändert')
                self.save(bot,tokens,account);status=200
        if status!=200:raise ActionError('Twitch-Anmeldung ungültig oder abgelaufen. Bitte erneut Login wählen.')
        if account.get('client_id')!=self.config.get('twitch_client_id'):raise ActionError('Token gehört zu einer anderen Twitch Client-ID')
        if self.config.get(token)==original:
            changes={uid:account['user_id'],login:account['login'],'twitch_bot_scopes' if bot else 'twitch_scopes':account.get('scopes',[])}
            if not bot:changes['channel']=account['login']
            self.config.update(self.store.update('local.json',changes))
        self.confirmed(bot,account)
        await self.authenticated(bot,account)
        return {'bot':bot,'login':account['login'],'userId':account['user_id'],'scopes':account.get('scopes',[])}

    async def maintain(self,on_error):
        while True:
            for bot in (False,True):
                if self.config.get(self.keys(bot)[0]):
                    try:await self.validate(bot)
                    except ActionError as exc:on_error(str(exc))
                    except (aiohttp.ClientError,OSError,asyncio.TimeoutError):on_error('Twitch-Kontoprüfung momentan nicht erreichbar')
                    except (KeyError,TypeError,ValueError):on_error('Unerwartete Antwort bei der Twitch-Kontoprüfung')
            await asyncio.sleep(900)
