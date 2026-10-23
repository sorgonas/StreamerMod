"""Original RewardConfigure.states (a JsonProperty field, not a CLR property)."""
NAMES=('Enabled','Paused','Disabled','NotConfigured')

def convert(states):
 if not isinstance(states,dict):raise ValueError('Original-Reward-Zustände müssen ein Objekt sein.')
 result=[];seen=set()
 for key,identities in states.items():
  mode=NAMES.index(key) if key in NAMES else int(key) if str(key) in ('0','1','2','3') else -1
  if mode<0 or not isinstance(identities,list):raise ValueError('Unbekannte Original-Reward-Gruppe.')
  for identity in identities:
   if not isinstance(identity,str) or not identity or identity in seen:raise ValueError('Original-Reward-ID fehlt oder ist mehrfach zugeordnet.')
   seen.add(identity)
   if mode==3:continue
   result.append({'rewardId':identity,**({'is_enabled':False} if mode==2 else {'is_enabled':True,'is_paused':mode==1})})
 return result

def original(rows):
 if not isinstance(rows,list):raise ValueError('Reward-Konfiguration benötigt eine Liste.')
 states={name:[] for name in NAMES};seen=set()
 for row in rows:
  identity=row.get('rewardId') if isinstance(row,dict) else None
  if not identity or identity in seen or set(row)-{'rewardId','is_enabled','is_paused'}:raise ValueError('Reward-Konfiguration besitzt keine Originalzuordnung.')
  seen.add(identity)
  if row.get('is_enabled') is False:mode=2
  elif row.get('is_enabled') is True and type(row.get('is_paused')) is bool:mode=int(row['is_paused'])
  else:raise ValueError('Originalexport benötigt einen vollständigen Reward-Zielzustand.')
  states[NAMES[mode]].append(identity)
 return states
