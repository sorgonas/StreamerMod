"""Whitelisted native notifications; event names are documented, OBS/Quote schemas aren't."""

def obs(studio,kind,data,metadata):
 hub=studio.main_websocket
 connection={key:metadata.get('obs.'+key,'') for key in ('id','name','host')}
 if kind in ('OBSConnected','OBSDisconnected'):
  body={'connection':connection}
  if kind=='OBSConnected':body.update(studioVersion=data.get('obs.studioVersion',''),websocketVersion=data.get('obs.websocketVersion',''))
  hub.publish('Obs','Connected' if kind=='OBSConnected' else 'Disconnected',body);return
 body={'connection':connection,'eventType':kind,'eventData':data}
 hub.publish('Obs','Event',body)
 if kind=='CurrentProgramSceneChanged' and isinstance(data.get('sceneName'),str):hub.publish('Obs','SceneChanged',{'connection':connection,'sceneName':data['sceneName']})
 if kind in ('StreamStateChanged','RecordStateChanged'):
  state=data.get('outputState')
  if state in ('OBS_WEBSOCKET_OUTPUT_STARTED','OBS_WEBSOCKET_OUTPUT_STOPPED'):
   event=('Streaming' if kind=='StreamStateChanged' else 'Recording')+('Started' if state.endswith('_STARTED') else 'Stopped')
   hub.publish('Obs',event,{'connection':connection,'outputState':state})
 if kind=='VendorEvent':hub.publish('Obs','VendorEvent',body)

def quote(engine,kind,args):
 if kind not in (90203,90254):return
 studio=getattr(engine,'studio',None);hub=getattr(studio,'main_websocket',None)
 if hub is None:return
 mapping={'id':'quoteId','quote':'quote','user':'quoteUser','userId':'quoteUserId','platform':'quotePlatform','game':'quoteGame','timestamp':'quoteTimestamp'}
 if type(args.get('quoteId')) is not int or not isinstance(args.get('quote'),str):return
 body={key:args[source] for key,source in mapping.items() if source in args}
 hub.publish('Quote','Added' if kind==90203 else 'Show',body)
