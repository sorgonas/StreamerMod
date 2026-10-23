'use strict';
const WebSocket = require('./vendor/ws');
const fs=require('fs'), os=require('os'), path=require('path');
const argv=process.argv.slice(2), option=name=>argv[argv.indexOf(name)+1];
const contexts=new Map(), renderCache=new Map(); let cacheBytes=0; let bridge=null, actions=[], sequence=0, connected=false;
const sdk=new WebSocket('ws://127.0.0.1:'+option('-port'));
const send=(event,context,payload)=>{if(sdk.readyState===WebSocket.OPEN)sdk.send(JSON.stringify({event,context,...(event==='sendToPropertyInspector'?{action:contexts.get(context)?.action}:{}),...(payload===undefined?{}:{payload})}));};
const upstream=data=>{if(connected&&bridge?.readyState===WebSocket.OPEN)bridge.send(JSON.stringify(data));};
function bind(context){const c=contexts.get(context);if(c)upstream({op:'bind',context,device:c.device,controller:c.controller,settings:c.settings,state:c.state});}
function discovery(){
 if(bridge&&[WebSocket.OPEN,WebSocket.CONNECTING].includes(bridge.readyState))return;
 try {
  const config=JSON.parse(fs.readFileSync(path.join(process.env.XDG_CONFIG_HOME||path.join(os.homedir(),'.config'),'sorgobot/streamdeck-bridge.private.json'),'utf8'));
  if(!/^ws:\/\/127\.0\.0\.1:\d+\/bridge$/.test(config.endpoint))return;
  bridge=new WebSocket(config.endpoint,{maxPayload:4*1024*1024});
  bridge.on('open',()=>bridge.send(JSON.stringify({token:config.token})));
  bridge.on('error',()=>{}); bridge.on('close',()=>{connected=false;});
  bridge.on('message',raw=>{
   try {
    const message=JSON.parse(raw);
    if(message.op==='ready'){connected=true;upstream({op:'capabilities',version:2});for(const context of contexts.keys())bind(context);upstream({op:'actions'});}
    else if(message.op==='actions'){
     actions=message.actions;
     for(const context of contexts.keys())send('sendToPropertyInspector',context,{op:'actions',actions});
    } else if(message.op==='command'){
     let ok=false;
     try {command(message);ok=true;}catch(error){}
     upstream({op:'ack',id:message.id,ok});
    }
   }catch(error){}
  });
 }catch(error){}
}
function escape(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));}
function changeValue(previous,value){
 const operation=/^([+\-*/])=(.+)$/.exec(value);
 if(!operation)return value;
 const a=Number(previous??0),b=Number(operation[2]);
 const result=({'+':()=>a+b,'-':()=>a-b,'*':()=>a*b,'/':()=>a/b})[operation[1]]();
 if(!Number.isFinite(a)||!Number.isFinite(b)||!Number.isFinite(result))throw Error('Invalid numeric operation');
 return String(result);
}
function renderDeck(context,c,notice){
 const layer=c.layers?.[c.state]||{};
 const title=notice?.title??layer.title??c.title??c.settings.title??'';
 const value=notice?.description??layer.value??c.value??'';
 let svg='<svg xmlns="http://www.w3.org/2000/svg" width="144" height="144"><rect width="144" height="144" fill="#302536"/>';
 if(!notice&&c.legacyImage&&!layer.background)svg+=`<image href="data:image/svg+xml;base64,${Buffer.from(c.legacyImage).toString('base64')}" width="144" height="144"/>`;
 if(!notice&&layer.background)svg+=`<image href="data:image/svg+xml;base64,${Buffer.from(layer.background).toString('base64')}" width="144" height="144"/>`;
 if(!notice&&layer.icon)svg+=`<image href="data:image/svg+xml;base64,${Buffer.from(layer.icon).toString('base64')}" x="20" y="8" width="104" height="104"/>`;
 if(value&&c.controller!=='Encoder')svg+=`<text x="72" y="80" text-anchor="middle" font-size="18" fill="white">${escape(value).slice(0,1200)}</text>`;
 svg+='</svg>';
 if(c.controller==='Encoder'){send('setFeedback',context,{title,value,icon:svg});return;}
 send('setImage',context,{target:0,state:c.state,image:svg});
 send('setTitle',context,{target:0,state:c.state,title});
}
function cacheRender(context,c){
 const previous=renderCache.get(context);if(previous){cacheBytes-=previous.bytes;renderCache.delete(context);}
 const data={layers:c.layers,title:c.title,value:c.value,legacyImage:c.legacyImage};
 const bytes=Buffer.byteLength(JSON.stringify(data));
 if(bytes>16*1024*1024)return;
 while(renderCache.size&&cacheBytes+bytes>16*1024*1024){const key=renderCache.keys().next().value;cacheBytes-=renderCache.get(key).bytes;renderCache.delete(key);}
 renderCache.set(context,{bytes,data});cacheBytes+=bytes;
}
function command(message){
 const c=contexts.get(message.context); if(!c||sdk.readyState!==WebSocket.OPEN)throw Error('Unknown context');
 const payload=message.payload||{}, event=message.event, context=message.context;
 if(event==='deckUpdate'){
  if(![0,1].includes(payload.state))throw Error('Invalid state');
  c.layers=c.layers||{};const layer=c.layers[payload.state]||(c.layers[payload.state]={});
  // Compute numeric updates before mutation, so rejected division keeps state.
  const value=payload.value===undefined?undefined:changeValue(layer.value,payload.value);
  for(const key of ['background','icon','title'])if(payload[key]!==undefined)layer[key]=payload[key];
  if(value!==undefined)layer.value=value;
  if(payload.state===c.state)renderDeck(context,c);return;
 }
 if(event==='deckNotify'){
  if(c.notifyTimer)clearTimeout(c.notifyTimer);
  renderDeck(context,c,payload);
  c.notifyTimer=setTimeout(()=>{if(contexts.get(context)===c)renderDeck(context,c);},payload.duration);return;
 }
 if(event==='setValue'){
  const value=changeValue(c.value,payload.value);c.value=value;
  if(c.controller==='Encoder')send('setFeedback',context,{value,title:c.title||c.settings.title||'Studio'});
  else send('setImage',context,{target:0,image:`<svg xmlns="http://www.w3.org/2000/svg" width="144" height="144"><rect width="144" height="144" fill="#302536"/><text x="72" y="80" text-anchor="middle" font-size="22" fill="white">${escape(value)}</text></svg>`});
 } else if(['setTitle','setImage','setState','showAlert','showOk'].includes(event)) {
  if(event==='setTitle')c.title=payload.title;
  if(event==='setImage')c.legacyImage=payload.image;
  if(event==='setState'){if(c.controller==='Encoder')throw Error('State switching requires a key');c.state=payload.state;}
  if(c.controller==='Encoder'&&event==='setTitle'){c.title=payload.title;send('setFeedback',context,{title:payload.title});}
  else if(c.controller==='Encoder'&&event==='setImage')send('setFeedback',context,{icon:payload.image});
  else send(event,context,['showAlert','showOk'].includes(event)?undefined:{...payload,target:0});
  if(event==='setState'&&c.layers)renderDeck(context,c);
 } else throw Error('Unknown command');
}
sdk.on('open',()=>sdk.send(JSON.stringify({event:option('-registerEvent'),uuid:option('-pluginUUID')})));
sdk.on('error',()=>{});sdk.on('close',()=>{if(bridge)bridge.close();process.exit(0);});
sdk.on('message',raw=>{
 try {
  const m=JSON.parse(raw), context=m.context, data=m.payload||{};
  if(m.event==='willAppear'){
   contexts.set(context,{...(renderCache.get(context)?.data||{}),settings:data.settings||{},device:m.device||'',controller:data.controller||'Keypad',state:data.state||0,action:m.action});
   bind(context);
  } else if(m.event==='willDisappear'){const c=contexts.get(context);if(c){if(c.notifyTimer)clearTimeout(c.notifyTimer);cacheRender(context,c);}contexts.delete(context);upstream({op:'remove',context});}
  else if(m.event==='didReceiveSettings'){
   const c=contexts.get(context);if(c){c.settings=data.settings||{};bind(context);}
  } else if(m.event==='sendToPlugin'){
   if(data.op==='actions'){
    send('sendToPropertyInspector',context,{op:'actions',actions,connected});upstream({op:'actions'});
   }
  } else if(['keyDown','keyUp','dialRotate','dialDown','dialUp','touchTap'].includes(m.event)){
   const c=contexts.get(context);
   if(m.event==='keyDown'&&c?.action==='org.sorgobot.studio.switch'){c.state=1-(data.state??c.state);data.state=c.state;send('setState',context,{state:c.state});}
   if(c?.action==='org.sorgobot.studio.switch'){data.state=c.state;if(c.layers)renderDeck(context,c);}
   upstream({op:'input',context,event:m.event,data,sequence:++sequence});
  }
 }catch(error){}
});
setInterval(discovery,2000);discovery();
