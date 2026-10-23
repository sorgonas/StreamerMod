"""Observed users persist; live presence is a bounded, session-only snapshot."""
import math
import time
from contextlib import nullcontext
from .core import ActionError

PLATFORMS=('twitch','youtube','kick')

def identity(platform,user):
    platform=str(platform).strip().casefold();user=str(user).strip()
    if platform!='youtube':user=user.casefold()
    if platform not in PLATFORMS:raise ActionError('Nutzerplattform muss twitch, youtube oder kick sein')
    if not user:raise ActionError('Nutzername fehlt')
    return platform,user

class Users:
    def __init__(self,engine):
        self.db=engine.state.db;self.presence={}
        self.db.execute('''CREATE TABLE IF NOT EXISTS known_users (
            platform TEXT NOT NULL, user TEXT NOT NULL, user_id TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '', last_seen REAL NOT NULL DEFAULT 0,
            last_active REAL NOT NULL DEFAULT 0, PRIMARY KEY(platform,user))''')
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='points_accounts'").fetchone():
            with nullcontext() if self.db.in_transaction else self.db:
                self.db.execute("INSERT OR IGNORE INTO known_users(platform,user) SELECT DISTINCT platform,user FROM points_accounts")
    def remember(self,platform,user,user_id='',display_name='',active=False,now=None):
        platform,user=identity(platform,user)
        timestamp=time.time() if now is None else float(now)
        if not math.isfinite(timestamp) or timestamp<0:raise ActionError('Ungültiger Nutzerzeitpunkt')
        # A points transaction can register a user without committing its outer transaction.
        with nullcontext() if self.db.in_transaction else self.db:
            self.db.execute('''INSERT INTO known_users VALUES(?,?,?,?,?,?)
                ON CONFLICT(platform,user) DO UPDATE SET
                user_id=CASE WHEN excluded.user_id!='' THEN excluded.user_id ELSE known_users.user_id END,
                display_name=CASE WHEN excluded.display_name!='' THEN excluded.display_name ELSE known_users.display_name END,
                last_seen=MAX(known_users.last_seen,excluded.last_seen),
                last_active=MAX(known_users.last_active,excluded.last_active)''',
                (platform,user,str(user_id or ''),str(display_name or ''),timestamp,timestamp if active else 0))
        return platform,user
    def replace_presence(self,platform,users,now=None,ttl=600):
        timestamp=time.time() if now is None else float(now)
        ttl=float(ttl)
        if not math.isfinite(ttl) or ttl<=0:raise ActionError('Presence TTL muss positiv sein')
        incoming=set()
        with nullcontext() if self.db.in_transaction else self.db:
            if not self.db.in_transaction:self.db.execute('BEGIN IMMEDIATE')
            for user in users:
                _,login=self.remember(platform,user['login'],user.get('id',''),user.get('name',''),now=timestamp)
                incoming.add(login)
        self.presence[platform.casefold()]={'time':timestamp,'ttl':ttl,'users':incoming}
    def clear_presence(self,platform):self.presence.pop(platform.casefold(),None)
    def known(self,platform='',only_active=False,window=300,now=None):
        platform=str(platform).strip().casefold()
        if platform and platform not in PLATFORMS:raise ActionError('Ungültige Nutzerplattform')
        timestamp=time.time() if now is None else float(now)
        try:window=float(window)
        except (ValueError,TypeError):raise ActionError('Aktivitätsfenster benötigt eine Zahl') from None
        if not math.isfinite(window) or window<=0:raise ActionError('Aktivitätsfenster muss positiv sein')
        query='SELECT platform,user,user_id,display_name,last_seen,last_active FROM known_users';values=()
        if platform:query+=' WHERE platform=?';values=(platform,)
        result=[]
        for p,u,uid,display,seen,active in self.db.execute(query+' ORDER BY platform,user',values):
            snapshot=self.presence.get(p,{})
            present=u in snapshot.get('users',set()) and 0<=timestamp-snapshot.get('time',0)<=snapshot.get('ttl',0)
            recent=active>0 and 0<=timestamp-active<=window
            if only_active and not (present or recent):continue
            result.append({'platform':p,'userName':u,'userId':uid,'displayName':display or u,'lastSeen':seen,'lastActive':active,'active':bool(present or recent),'present':bool(present)})
        return result

def store(engine):
    if not hasattr(engine,'users'):engine.users=Users(engine)
    return engine.users

def members(group,users):
    """Qualified IDs survive renames; legacy bare logins retain matching on all platforms."""
    names={str(name).strip().casefold() for name in group.get('users',[])}
    ids={str(name).strip() for name in group.get('users',[]) if ':id:' in str(name)}
    return [user for user in users if user['userName'] and (user['userName'] in names or user['platform']+':'+user['userName'] in names) or user.get('userId') and user['platform']+':id:'+user['userId'] in ids]

def remove_membership(names,platform,login,user_id=''):
    result=[]
    for value in names:
        key=value.strip().casefold()
        if user_id and value.strip()==platform+':id:'+user_id:continue
        if login and key==platform+':'+login:continue
        if login and key==login:
            for other in PLATFORMS:
                entry=other+':'+login
                if other!=platform and not any(v.strip().casefold()==entry for v in [*result,*names]):result.append(entry)
        else:result.append(value)
    return result
