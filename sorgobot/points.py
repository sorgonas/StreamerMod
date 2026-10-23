"""Native persistent points accounts. Original wire/import compatibility is separate."""
import copy
from decimal import Decimal,localcontext
import math
import time
from .core import ActionError, StopAction
from .core_logic import resolve

MAX_POINTS=2**63-1

def integer(value, nonnegative=True):
    if isinstance(value,bool):raise ActionError('Punkte benötigen eine ganze Zahl')
    try:
        result=int(value)
        if str(result)!=str(value).strip() and result!=value:raise ValueError()
    except (ValueError,TypeError,OverflowError):raise ActionError('Punkte benötigen eine ganze Zahl') from None
    if result>MAX_POINTS or result<(0 if nonnegative else -MAX_POINTS-1):raise ActionError('Punkte außerhalb des erlaubten Bereichs')
    return result

def multiplier(value):
    try:result=float(value)
    except (ValueError,TypeError):raise ActionError('Multiplier benötigt eine Zahl') from None
    if not math.isfinite(result) or result<0:raise ActionError('Multiplier muss endlich und mindestens 0 sein')
    return result

def scaled_amount(points,definition,platform,user,amount,enabled):
    if not enabled:return amount
    factor=multiplier(points.user_multiplier(definition,platform,user))
    with localcontext() as context:
        context.prec=80
        result=int(Decimal(amount)*Decimal(str(factor)))
    return integer(result,nonnegative=amount>=0)

class Points:
    def __init__(self,engine):
        self.engine=engine;self.db=engine.state.db
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS points_accounts (
          definition TEXT, platform TEXT, user TEXT, balance INTEGER NOT NULL CHECK(balance>=0),
          last_active REAL NOT NULL DEFAULT 0, PRIMARY KEY(definition,platform,user));
        CREATE TABLE IF NOT EXISTS points_multipliers (
          definition TEXT, group_id TEXT, multiplier REAL NOT NULL, PRIMARY KEY(definition,group_id));
        CREATE TABLE IF NOT EXISTS points_ledger (
          id INTEGER PRIMARY KEY, timestamp REAL, definition TEXT, platform TEXT, user TEXT,
          delta INTEGER, balance INTEGER, operation TEXT);
        ''')
        from .users import store as users
        users(engine)
    def definition(self,identity):
        config=getattr(getattr(self.engine,'services',None),'config',{})
        item=next((d for d in config.get('pointDefinitions',[]) if d['id']==identity),None)
        if item is None:raise ActionError('Points Definition nicht gefunden')
        if not item.get('enabled',True):raise ActionError('Points Definition ist deaktiviert')
        return item
    def identity(self,platform,user):
        platform,user=str(platform).strip().casefold(),str(user).strip().casefold()
        if platform not in ('twitch','youtube','kick'):raise ActionError('Points benötigt Plattform twitch, youtube oder kick')
        if not user:raise ActionError('Points benötigt einen Nutzernamen')
        return platform,user
    def balance(self,definition,platform,user):
        row=self.db.execute('SELECT balance FROM points_accounts WHERE definition=? AND platform=? AND user=?',(definition,platform,user)).fetchone()
        return row[0] if row else 0
    def write(self,definition,platform,user,balance,operation):
        balance=integer(balance);old=self.balance(definition,platform,user)
        self.db.execute('INSERT INTO points_accounts(definition,platform,user,balance) VALUES(?,?,?,?) ON CONFLICT(definition,platform,user) DO UPDATE SET balance=excluded.balance',(definition,platform,user,balance))
        from .users import store as users
        users(self.engine).remember(platform,user,now=0)
        self.db.execute('INSERT INTO points_ledger(timestamp,definition,platform,user,delta,balance,operation) VALUES(?,?,?,?,?,?,?)',(time.time(),definition,platform,user,balance-old,balance,operation))
        return balance
    def user_multiplier(self,definition,platform,user):
        item=self.definition(definition)
        user_value=multiplier(item.get('userMultipliers',{}).get(platform+':'+user,1))
        config=getattr(getattr(self.engine,'services',None),'config',{})
        from .users import store as users,members
        current=next((r for r in users(self.engine).known(platform) if r['userName']==user),{'platform':platform,'userName':user,'userId':''})
        group_values=[]
        for group in config.get('userGroups',[]):
            if members(group,[current]):
                row=self.db.execute('SELECT multiplier FROM points_multipliers WHERE definition=? AND group_id=?',(definition,group['id'])).fetchone()
                if row:group_values.append(row[0])
        # Native rule: personal multiplier times highest configured group multiplier.
        return multiplier(user_value*(max(group_values) if group_values else 1))
    def leaderboard(self,definition,count=10,offset=0,platform=''):
        count,offset=integer(count),integer(offset)
        if count>10000:raise ActionError('Leaderboard Count darf höchstens 10000 sein')
        query='SELECT platform,user,balance FROM points_accounts WHERE definition=?';params=[definition]
        if platform:query+=' AND platform=?';params.append(platform)
        query+=' ORDER BY balance DESC,platform,user LIMIT ? OFFSET ?';params.extend((count,offset))
        return [{'platform':p,'userName':u,'points':v,'rank':offset+i+1} for i,(p,u,v) in enumerate(self.db.execute(query,params))]
    def atomic(self,callback):
        if self.db.in_transaction:raise ActionError('Points-Änderung benötigt eine eigene Transaktion')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            return callback()

def store(engine):
    if not hasattr(engine,'points'):engine.points=Points(engine)
    return engine.points

def operation(engine,node,args):
    points=store(engine);kind=node['type']
    get=lambda key,default='':resolve(node.get(key,default),args,engine)
    definition=str(get('pointDefinitionId'));item=points.definition(definition)
    destination=str(get('destinationVariable','userPoints'))
    if kind==90400:args[destination]=copy.deepcopy(item);return
    if kind==90401:
        def reset():
            for platform,user,_ in points.db.execute('SELECT platform,user,balance FROM points_accounts WHERE definition=?',(definition,)).fetchall():points.write(definition,platform,user,0,'resetDefinition')
        points.atomic(reset);return
    if kind in (90404,90405,90406):
        group=str(get('groupId'));config=engine.services.config
        if not any(g['id']==group for g in config['userGroups']):raise ActionError('Points Group nicht gefunden')
        if kind==90404:
            row=points.db.execute('SELECT multiplier FROM points_multipliers WHERE definition=? AND group_id=?',(definition,group)).fetchone()
            args[destination]=row[0] if row else 1;return
        def change():
            if kind==90406:points.db.execute('DELETE FROM points_multipliers WHERE definition=? AND group_id=?',(definition,group))
            else:points.db.execute('INSERT OR REPLACE INTO points_multipliers VALUES(?,?,?)',(definition,group,multiplier(get('multiplier',1))))
        points.atomic(change);return
    if kind==90407:
        args[destination]=points.leaderboard(definition,get('count',10),get('offset',0),get('platform'));return
    if kind in (90402,90403):
        amount=integer(get('amount',0));platform=str(get('platform')).casefold()
        if platform and platform not in ('twitch','youtube','kick'):raise ActionError('Ungültige Points-Plattform')
        group=None
        if kind==90403:
            group=next((g for g in engine.services.config['userGroups'] if g['id']==str(get('groupId'))),None)
            if group is None:raise ActionError('Points Group nicht gefunden')
        from .users import store as users, members
        registry=users(engine)
        # Preserve accounts created by earlier releases, including accounts at zero.
        for p,u in points.db.execute('SELECT DISTINCT platform,user FROM points_accounts').fetchall():registry.remember(p,u,now=0)
        recipients=registry.known(platform,node.get('onlyActive',False),get('activeWindowSeconds',300))
        if group is not None:recipients=members(group,recipients)
        def bulk():
            count=0
            for recipient in recipients:
                p,u=recipient['platform'],recipient['userName'];balance=points.balance(definition,p,u)
                delta=scaled_amount(points,definition,p,u,amount,node.get('useMultipliers',False))
                points.write(definition,p,u,balance+delta,'bulkAward');count+=1
            return count
        args['pointsUsersUpdated']=points.atomic(bulk);return
    if kind==90416:
        source=points.identity(get('sourcePlatform'),get('sourceUser'));target=points.identity(get('targetPlatform'),get('targetUser'));amount=integer(get('amount',0))
        def transfer():
            a=points.balance(definition,*source);b=points.balance(definition,*target)
            if a<amount:raise ActionError('Nicht genügend Punkte für Transfer')
            if source==target:return a,b
            return points.write(definition,*source,a-amount,'transferOut'),points.write(definition,*target,b+amount,'transferIn')
        a,b=points.atomic(transfer);args[destination+'Source']=a;args[destination+'Target']=b;return
    platform,user=points.identity(get('platform'),get('user'))
    if kind==90412:args[destination]=points.user_multiplier(definition,platform,user);return
    if kind==90411:args[destination]=points.balance(definition,platform,user);return
    def mutate():
        balance=points.balance(definition,platform,user)
        if kind==90409:return balance,balance>=integer(get('requiredAmount',0))
        if kind==90410:
            points.write(definition,platform,user,0,'delete');points.db.execute('DELETE FROM points_accounts WHERE definition=? AND platform=? AND user=?',(definition,platform,user));return 0,True
        amount=0 if kind==90413 else integer(get('amount',0),nonnegative=kind!=90417)
        if kind==90415:
            if balance<amount:return balance,False
            new=balance-amount
        elif kind in (90413,90414):new=amount
        elif kind in (90408,90417):
            if node.get('useMultipliers'):amount=scaled_amount(points,definition,platform,user,amount,True)
            new=balance+amount
        else:raise ActionError('Unbekannte Points-Unteraktion')
        return points.write(definition,platform,user,new,str(kind)),True
    balance,success=points.atomic(mutate);args[destination]=balance
    if kind in (90409,90415):
        args['pointsSuccess']=success
        if not success and node.get('breakOnFailure',True):raise StopAction()
