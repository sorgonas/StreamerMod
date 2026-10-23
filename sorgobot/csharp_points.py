"""C# Points user methods sharing native accounts, multipliers and ledger."""
import uuid
from .core import ActionError
from .points import store,integer,scaled_amount,multiplier,operation
from .command_state import platform

def definition(points,value):
 try:key=str(uuid.UUID(value))
 except (ValueError,AttributeError,TypeError):raise ActionError('Points-Definition benötigt eine GUID') from None
 candidates=[]
 for item in getattr(getattr(points.engine,'services',None),'config',{}).get('pointDefinitions',[]):
  try:match=str(uuid.UUID(item['id']))==key
  except (ValueError,TypeError,AttributeError):match=False
  if match:candidates.append(item)
 if len(candidates)!=1:raise ActionError('Points-Definition fehlt oder ist nicht eindeutig')
 points.definition(candidates[0]['id']);return candidates[0]['id']

def username(value):
 if not isinstance(value,str) or not value.strip():raise ActionError('Points-Login fehlt')
 return value.strip().casefold()

def names(values):
 if not isinstance(values,list):raise ActionError('Points-Nutzerliste muss List<string> sein')
 return list(dict.fromkeys(username(value) for value in values))

async def rpc(engine,method,values):
 if getattr(getattr(engine,'studio',None),'closing',False):raise ActionError('Points-Laufzeit wird geschlossen')
 if engine.state.db.in_transaction:raise ActionError('Points-Aufruf benötigt eine eigene Transaktion')
 points=store(engine)
 if method=='points_admin_reset':
  cid=definition(points,values[0]);operation(engine,{'type':90401,'pointDefinitionId':cid},{});return True
 if method=='points_group_multiplier':
  op,cid,name,value=values;cid=definition(points,cid)
  from .csharp_groups import group
  target=group(engine.services.config.get('userGroups',[]),name)
  if target is None:raise ActionError('Points-Gruppe nicht gefunden')
  kind={'get':90404,'set':90405,'remove':90406}.get(op)
  if kind is None:raise ActionError('Unbekannte Points-Multiplier-Operation')
  args={};node={'type':kind,'pointDefinitionId':cid,'groupId':target['id'],'destinationVariable':'value'}
  if op=='set':node['multiplier']=multiplier(value)
  operation(engine,node,args);return args['value'] if op=='get' else True
 if method=='points_award':
  cid,amount,only_active,p,apply,name=values;cid=definition(points,cid);amount=integer(amount)
  if type(only_active) is not bool or type(apply) is not bool:raise ActionError('Points-Flags müssen bool sein')
  p='' if p is None else platform(p)
  node={'type':90402,'pointDefinitionId':cid,'amount':amount,'platform':p,'onlyActive':only_active,'useMultipliers':apply}
  if name is not None:
   from .csharp_groups import group
   target=group(engine.services.config.get('userGroups',[]),name)
   if target is None:raise ActionError('Points-Gruppe nicht gefunden')
   node.update(type=90403,groupId=target['id'])
  args={};operation(engine,node,args);return args['pointsUsersUpdated']
 if method=='points_bulk':
  users,p,cid,delta=values;users=names(users);p=platform(p);cid=definition(points,cid);delta=integer(delta,False)
  def bulk():
   # Compute all results before writing; a later SQL failure rolls back all rows/ledger entries.
   changes=[(u,integer(points.balance(cid,p,u)+delta)) for u in users]
   for u,balance in changes:points.write(cid,p,u,balance,'csharpBulkUpdate')
   return True
  return points.atomic(bulk)
 if method=='points_get_many':
  users,p,cid=values;users=names(users);p=platform(p);cid=definition(points,cid)
  return {u:points.balance(cid,p,u) for u in users}
 if method=='points_transfer':
  source,target,p,cid,amount=values;source=username(source);target=username(target);p=platform(p);cid=definition(points,cid);amount=integer(amount)
  def transfer():
   a=points.balance(cid,p,source);b=points.balance(cid,p,target)
   if a<amount:return False
   if source==target:return True
   integer(b+amount)
   points.write(cid,p,source,a-amount,'csharpTransferOut');points.write(cid,p,target,b+amount,'csharpTransferIn');return True
  return points.atomic(transfer)
 if method=='points_user':
  op,user,p,cid,amount,apply=values;user=username(user);p=platform(p);cid=definition(points,cid)
  if op=='get':return points.balance(cid,p,user)
  if op=='multiplier':return points.user_multiplier(cid,p,user)
  if op not in ('has','add','update','set','remove','spend','reset','delete'):raise ActionError('Unbekannte Points-Nutzeroperation')
  amount=integer(amount,nonnegative=op!='update')
  if type(apply) is not bool:raise ActionError('useMultipliers muss bool sein')
  def change():
   old=points.balance(cid,p,user)
   if op=='has':return old>=amount
   if op in ('remove','spend'):
    if old<amount:return False
    result=old-amount
   elif op in ('add','update'):result=old+scaled_amount(points,cid,p,user,amount,apply)
   elif op=='set':result=amount
   else:result=0
   integer(result)
   if op=='delete':
    exists=points.db.execute('SELECT 1 FROM points_accounts WHERE definition=? AND platform=? AND user=?',(cid,p,user)).fetchone()
    if not exists:return False
   points.write(cid,p,user,result,'csharp:'+op)
   if op=='delete':points.db.execute('DELETE FROM points_accounts WHERE definition=? AND platform=? AND user=?',(cid,p,user))
   return True
  if op=='has':return points.balance(cid,p,user)>=amount
  return points.atomic(change)
 raise ActionError('Unbekannte C#-Points-Methode')
