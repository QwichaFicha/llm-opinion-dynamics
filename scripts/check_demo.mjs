// Isolated headless browser test; built-in Node APIs, no npm packages.
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const discussion=process.argv[3]==='discussion';
const qa=path.join(root,'reports','qa',discussion?'discussion':'demo');await fs.mkdir(qa,{recursive:true});
if(typeof WebSocket!=='function')throw Error('Node 22+ with built-in WebSocket is required');
const profile=await fs.mkdtemp(path.join(qa,'cdp-profile-'));
const chrome=spawn(process.argv[2],[ '--headless=new','--disable-gpu','--disable-background-networking',
 '--disable-component-update','--disable-sync','--no-first-run','--no-default-browser-check',
 '--disable-extensions','--disable-crash-reporter','--disable-breakpad',
 '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],
 {windowsHide:true,stdio:['ignore','ignore','pipe']});
let errors='';chrome.stderr.on('data',chunk=>errors+=chunk.toString());
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));let socket;
try{
 let port;
 for(let i=0;i<120;i++){
  try{port=Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break;}catch{}
  if(chrome.exitCode!==null)throw Error('Headless Chrome exited before debugging started');
  await sleep(150);
 }
 if(!port)throw Error('No debugging port');
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 const target=pages.find(p=>p.type==='page');if(!target)throw Error('No isolated page');
 socket=new WebSocket(target.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
 let next=0;const pending=new Map();
 socket.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.id&&pending.has(data.id)){const{resolve,reject,timer}=pending.get(data.id);clearTimeout(timer);pending.delete(data.id);data.error?reject(Error(JSON.stringify(data.error))):resolve(data.result);}});
 const command=(method,params={})=>new Promise((resolve,reject)=>{const id=++next;const timer=setTimeout(()=>{pending.delete(id);reject(Error('Timeout: '+method));},30000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
 const evaluate=async expression=>{const result=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
 await command('Page.enable');await command('Runtime.enable');const results=[];
 for(const [label,width,height,mobile] of [['desktop',1280,1400,false],['mobile',420,1900,true]]){
  await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile});
  await command('Page.navigate',{url:pathToFileURL(path.join(root,'demo',discussion?'discussion.html':'replay.html')).href});
  let ready=false;for(let i=0;i<100;i++){if(await evaluate(discussion?"Boolean(document.getElementById('message')?.textContent)":"document.documentElement.dataset.case==='combined_11'")){ready=true;break;}await sleep(50);}
  if(!ready)throw Error('Replay did not render');
  const result=discussion?await evaluate(`(()=>{
   const d=document,checks=[];const ok=(name,value)=>{checks.push({name,passed:Boolean(value)});if(!value)throw Error(name);};
   const change=(id,value,type='change')=>{d.getElementById(id).value=String(value);d.getElementById(id).dispatchEvent(new Event(type,{bubbles:true}));};
   ok('exact viewport',window.innerWidth===${width});
   ok('both model routes',Object.keys(DATA.cases).some(k=>k.startsWith('codex/'))&&Object.keys(DATA.cases).some(k=>k.startsWith('bonsai/')));
   ok('six completed cases',Object.keys(DATA.cases).length===6);
   change('case','bonsai/rotating_text');ok('initial no partners',d.querySelectorAll('#graph line').length===0);
   const pairs=new Set();for(let t=1;t<=5;t++){change('round',t,'input');ok('three pairs round '+t,d.querySelectorAll('#graph line').length===3);for(let pair of DATA.cases['bonsai/rotating_text'].pair_schedule[t-1])pairs.add(pair.join('-'));}
   ok('fifteen unique pairs',pairs.size===15);ok('latest event displayed',d.getElementById('event').textContent.includes('E5_SUPPORT'));
   d.getElementById('agents').children[2].click();ok('agent selection',d.getElementById('role').textContent.includes('Агент 2'));
   ok('verbatim preserved message',d.getElementById('message').textContent===DATA.cases['bonsai/rotating_text'].actions[5][2].message);
   change('case','bonsai/rotating_role_only');change('round',3,'input');ok('role-only profile fallback',d.getElementById('needs').textContent.includes('скрыты'));
   ok('role-only recorded positions',DATA.cases['bonsai/rotating_role_only'].trajectory[3].opinions.every(x=>x===-1));
   change('case','codex/rotating_text');change('round',4,'input');ok('correction displayed',d.getElementById('event').textContent.includes('E4_CORRECTION'));
   ok('no horizontal overflow',d.documentElement.scrollWidth<=window.innerWidth);
   return {checks,viewport:window.innerWidth,overflow:d.documentElement.scrollWidth>window.innerWidth};
  })()`):await evaluate(`(async()=>{
   const d=document,checks=[];const ok=(name,value)=>{checks.push({name,passed:Boolean(value)});if(!value)throw Error(name);};
   const change=(id,value,type='change')=>{d.getElementById(id).value=String(value);d.getElementById(id).dispatchEvent(new Event(type,{bubbles:true}));};
   ok('exact viewport',window.innerWidth===${width});
   ok('15 recorded cases',Object.keys(JSON.parse(d.getElementById('recorded-data').textContent)).length===15);
   change('round',4,'input');ok('baseline variance',d.getElementById('variance').textContent==='0,3189');
   change('condition','combined_memory4_no_initial');ok('long memory variance',d.getElementById('variance').textContent==='0,2011');
   change('seed',33);ok('unsupported combination resets',d.documentElement.dataset.case==='combined_33');
   change('condition','peers_only');change('seed',22);ok('profile selection',d.documentElement.dataset.case==='peers_only_22');
   d.getElementById('agent-buttons').children[5].click();ok('agent selection',d.getElementById('selected-agent').textContent.includes('Агент 5'));
   ok('no horizontal overflow',d.documentElement.scrollWidth<=window.innerWidth);
   d.getElementById('play').click();await new Promise(resolve=>setTimeout(resolve,5100));
   ok('play completes',d.documentElement.dataset.round==='4');ok('play stops',d.getElementById('play').textContent==='▶');
   return {checks,viewport:window.innerWidth,overflow:d.documentElement.scrollWidth>window.innerWidth};
  })()`);
  results.push({layout:label,...result});
  const metrics=await command('Page.getLayoutMetrics');
  const shot=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,
   clip:{x:0,y:0,width,height:Math.ceil(metrics.cssContentSize.height),scale:1}});
  await fs.writeFile(path.join(qa,label+'.png'),Buffer.from(shot.data,'base64'));
 }
 await fs.writeFile(path.join(qa,'verification.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
 await command('Browser.close').catch(()=>{});
}catch(error){await fs.writeFile(path.join(qa,'cdp-stderr.txt'),errors);throw error;}
finally{if(socket)socket.close();if(chrome.exitCode===null)chrome.kill();}
