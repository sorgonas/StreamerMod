'use strict';
const $=id=>document.getElementById(id), events=new URLSearchParams(location.search).has('events');
const storage='streamermod-chat-dock-'+(events?'events':'chat');
let credential=location.hash.slice(1), saved, current, signature='', busy=false;
if(credential){sessionStorage.setItem('streamermod-dock-key',credential);history.replaceState(null,'',location.pathname+location.search);}
else credential=sessionStorage.getItem('streamermod-dock-key')||'';
try{saved=JSON.parse(localStorage.getItem(storage));}catch{saved=null;}
if(events){$('title').textContent='StreamerMod Event Feed';document.querySelector('footer').hidden=true;}
const commands=['title','game','clear','clear/overlay','action','me','announce','timeout','ban','unban','mod','unmod','vip','unvip','slow','slowoff','subscribers','subscribersoff','commercial','raid','raidcancel','shoutout','unpin','clear/twitch'];
for(const name of commands){const opt=document.createElement('option');opt.value='/'+name;$('commands').append(opt);}
$('platform').onchange=()=>{$('account').disabled=$('platform').value==='youtube';$('commands').replaceChildren();for(const name of commands.filter(n=>$('platform').value==='twitch'||['clear','clear/overlay'].includes(n)||n==='action'&&$('platform').value==='youtube')){const option=document.createElement('option');option.value='/'+name;$('commands').append(option);}};
function persist(){localStorage.setItem(storage,JSON.stringify(saved));}
function apply(){
 $('font').value=saved.settings.fontSize;$('limit').value=saved.settings.historyLimit;$('emotes').checked=saved.settings.showEmotes;
 $('rows').style.fontSize=saved.settings.fontSize+'px';signature='';persist();render();
}
async function api(data){
 const response=await fetch('/api/chat-dock',{method:data?'POST':'GET',headers:{'X-StreamerMod-Dock-Key':credential,...(data?{'Content-Type':'application/json'}:{})},...(data?{body:JSON.stringify(data)}:{})});
 const value=await response.json().catch(()=>null);
 if(!response.ok){const error=Error(value?.error||'Dock-Link im StreamerMod-Chat neu kopieren und im OBS-Dock öffnen.');error.delivery=value;throw error;}
 return value;
}
async function run(data){try{await api(data);$('status').textContent='';return true;}catch(error){if(error.delivery?.partial){const failed=Object.keys(error.delivery.results).filter(p=>!error.delivery.results[p].success);if(failed.length===1){$('platform').value=failed[0];$('platform').dispatchEvent(new Event('change'));}}$('status').textContent=error.message;return false;}}
function button(label,callback){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=callback;return b;}
function quick(container,scope,row){
 for(const q of saved.settings.quickActions.filter(q=>q.scope===scope))container.append(button(q.name,()=>run({operation:'quick',quickId:q.id,rowId:row?.id,platform:row?.platform?.toLowerCase()||$('platform').value})));
}
function render(){
 if(!current||!saved)return;
 const rows=(events?current.events:current.chat).slice(-saved.settings.historyLimit);
 const next=JSON.stringify([rows,saved.settings]);if(next===signature)return;signature=next;
 const box=$('rows'),atEnd=box.scrollTop+box.clientHeight>=box.scrollHeight-20,old=box.scrollTop;box.replaceChildren();$('global').replaceChildren();quick($('global'),'global');
 for(const row of rows){
  const article=document.createElement('article'),name=document.createElement('strong');name.textContent='['+(row.platform?.toLowerCase()==='youtube'?'YouTube':'Twitch')+'] '+(row.user||'');article.append(name,document.createTextNode(events?' · '+row.type+' · '+row.time:': '));
  if(!events){
   for(const word of (row.message||'').split(/(\s+)/)){
    const url=row.emotes?.[word];let valid=false;
    if(saved.settings.showEmotes&&typeof url==='string')try{const u=new URL(url);valid=u.protocol==='https:'&&['static-cdn.jtvnw.net','cdn.betterttv.net','cdn.frankerfacez.com','cdn.7tv.app'].includes(u.hostname)&&!u.username&&!u.password&&(!u.port||u.port==='443');}catch{}
    if(valid){const img=document.createElement('img');img.src=url;img.alt=word;img.referrerPolicy='no-referrer';article.append(img);}else article.append(document.createTextNode(word));
   }
  }
  const tools=document.createElement('span');tools.className='tools';
  if(events)quick(tools,'event',row);else if(row.login){quick(tools,'user',row);quick(tools,'message',row);}
  article.append(tools);box.append(article);
 }
 box.scrollTop=atEnd?box.scrollHeight:old;
}
$('sync').onclick=()=>{if(current){saved={settings:current.settings,revision:current.revision};apply();$('status').textContent='Einstellungen aus StreamerMod übernommen.';}};
for(const id of ['font','limit','emotes'])$(id).onchange=()=>{
 if(!saved)return;const font=Number($('font').value),limit=Number($('limit').value);
 if(!Number.isInteger(font)||font<8||font>36||!Number.isInteger(limit)||limit<20||limit>1000)return;
 saved.settings={...saved.settings,fontSize:font,historyLimit:limit,showEmotes:$('emotes').checked};apply();
};
document.querySelector('form').onsubmit=async event=>{
 event.preventDefault();const text=$('message').value.trim();if(busy||!text)return;busy=true;$('send').disabled=true;
 try{if(await run({operation:'send',message:text,platform:$('platform').value,bot:$('account').value==='true'}))if($('message').value.trim()===text)$('message').value='';}
 finally{busy=false;$('send').disabled=false;}
};
async function poll(){
 try{current=await api();if(!saved||!saved.settings||saved.revision!==current.revision){saved={settings:current.settings,revision:current.revision};apply();}else render();if($('status').textContent.startsWith('Dock-Link'))$('status').textContent='';}
 catch(error){$('status').textContent=error.message;}
 setTimeout(poll,1200);
}
poll();
