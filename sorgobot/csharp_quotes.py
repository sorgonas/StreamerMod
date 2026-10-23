"""C# quote access over the existing native store and queued Core events."""
import datetime as dt
from .core import ActionError
from .core_operations import quote_operation
from .core_events import emit
from .csharp_globals import known,user_id
from .twitch_user_info import user_data

MAX_ID=2**31-1

def quotes(engine):
    rows=engine.state.get('core:quotes',[])
    if not isinstance(rows,list):raise ActionError('Ungültiger gespeicherter Zitatbestand')
    identities=set()
    for row in rows:
        identity=row.get('quoteId') if isinstance(row,dict) else None
        if type(identity) is not int or not 0<=identity<=MAX_ID or identity in identities:raise ActionError('Ungültige oder doppelte gespeicherte Zitat-ID')
        identities.add(identity)
    return rows

def quote_id(value):
    if type(value) is not int or not -(2**31)<=value<=MAX_ID:raise ActionError('Zitat-ID muss ein Int32 sein')
    return value

def model(row):
    mapping={'Timestamp':'quoteTimestamp','Id':'quoteId','UserId':'quoteUserId','User':'quoteUser','Platform':'quotePlatform','GameName':'quoteGame','Quote':'quote'}
    if any(key not in row for key in mapping.values()):raise ActionError('Zitat besitzt unvollständige Metadaten; Originalimport/Migration erforderlich')
    for key in ('quoteTimestamp','quoteUserId','quoteUser','quotePlatform','quoteGame','quote'):
        if not isinstance(row[key],str):raise ActionError('Ungültiger gespeicherter Zitatwert: '+key)
    try:stamp=dt.datetime.fromisoformat(row['quoteTimestamp'].replace('Z','+00:00'))
    except ValueError:raise ActionError('Ungültiger gespeicherter Zitatzeitpunkt') from None
    if stamp.tzinfo is None:raise ActionError('Zitatzeitpunkt besitzt keine Zeitzone')
    return {field:row[key] for field,key in mapping.items()}

def session(engine):return tuple(engine.io.config.get(k) for k in ('broadcaster_id','twitch_client_id','twitch_token'))

def check_session(engine,before):
    if before!=session(engine):raise ActionError('Twitch-Konto während der Zitatabfrage gewechselt; Antwort verworfen')

async def author(engine,uid,before):
    row=known(engine,uid=uid)
    if row:return row
    if engine.io.dry_run:raise ActionError('Twitch-Nutzer in Vorschau nicht eindeutig bekannt; zuerst im Live-Modus abrufen')
    reply=await engine.io.twitch('GET','users',params={'id':uid});check_session(engine,before)
    if isinstance(reply,dict) and reply.get('data')==[]:return None
    row=user_data(reply,uid,by_id=True)
    return {'id':row['id'],'login':row['login'],'display_name':row['display_name']}

async def game(engine,before):
    if engine.io.dry_run:
        value=engine.state.get('currentGame')
        if not isinstance(value,str):raise ActionError('Keine gespeicherte Twitch-Kategorie für Vorschau vorhanden')
        return value
    broadcaster=user_id(before[0]);reply=await engine.io.twitch('GET','channels',params={'broadcaster_id':broadcaster});check_session(engine,before)
    rows=reply.get('data') if isinstance(reply,dict) else None
    if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or rows[0].get('broadcaster_id')!=broadcaster or not isinstance(rows[0].get('game_name'),str):raise ActionError('Twitch hat keine eindeutige Kanalkategorie geliefert')
    return rows[0]['game_name']

def own_transaction(engine):
    if engine.state.db.in_transaction:raise ActionError('C#-Zitatänderung benötigt eine eigene Transaktion')

async def rpc(engine,method,values):
    if method=='quote_count':return len(quotes(engine))
    if method=='quote_get':
        identity=quote_id(values[0]);row=next((q for q in quotes(engine) if q['quoteId']==identity),None)
        return model(row) if row is not None else None
    if method=='quote_delete':
        identity=quote_id(values[0]);own_transaction(engine);args={}
        with engine.state.db:
            engine.state.db.execute('BEGIN IMMEDIATE');quotes(engine)
            event=quote_operation(engine,{'type':90111,'quoteId':identity},args)
        if event:emit(engine,event,args)
        return args['success']
    if method=='quote_add_twitch':
        uid,text,capture=values;uid=user_id(uid)
        if not isinstance(text,str) or not text.strip():raise ActionError('Zitattext fehlt')
        if type(capture) is not bool:raise ActionError('captureGame muss bool sein')
        own_transaction(engine);before=session(engine)
        user=await author(engine,uid,before)
        if user is None:return -1
        category=await game(engine,before) if capture else ''
        check_session(engine,before);own_transaction(engine)
        args={'userId':uid,'user':user['display_name'] or user['login'],'platform':'twitch','currentGame':category}
        with engine.state.db:
            engine.state.db.execute('BEGIN IMMEDIATE');rows=quotes(engine);identity=engine.state.get('core:quoteNextId',1)
            if type(identity) is not int or not 1<=identity<=MAX_ID or any(q['quoteId']==identity for q in rows):raise ActionError('Nächste Zitat-ID ungültig oder erschöpft; Zitatbestand prüfen')
            event=quote_operation(engine,{'type':90110,'text':text},args)
        if event:emit(engine,event,args)
        return args['quoteId']
    raise ActionError('Unbekannte C#-Zitatmethode')
