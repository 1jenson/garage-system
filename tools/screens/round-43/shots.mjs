import {spawn} from 'node:child_process'; import fs from 'node:fs';
const CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const OUT=process.argv[2]; const PORT=9335; const BASE='http://localhost:8793/index.html';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const chrome=spawn(CHROME,['--headless=new','--disable-gpu','--hide-scrollbars','--no-first-run',`--remote-debugging-port=${PORT}`,`--user-data-dir=${process.argv[3]}`,'--window-size=1920,1080','about:blank']);
let targets; for(let i=0;i<40;i++){try{targets=await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();if(targets.find(t=>t.type==='page'))break}catch{} await sleep(250)}
const ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
await new Promise(r=>ws.onopen=r);
let id=0; const pend=new Map(); const events=[]; const errs=[];
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pend.has(m.id)){pend.get(m.id)(m);pend.delete(m.id)}else if(m.method){events.push(m.method);if(m.method==='Runtime.exceptionThrown')errs.push(m.params.exceptionDetails.text+' '+(m.params.exceptionDetails.exception||{}).description)}};
const send=(method,params={})=>new Promise(res=>{const i=++id;pend.set(i,m=>res(m.result||m.error));ws.send(JSON.stringify({id:i,method,params}))});
await send('Page.enable');await send('Runtime.enable');
const ev=async(js)=>{const r=await send('Runtime.evaluate',{expression:js,awaitPromise:true,returnByValue:true});return r.result?r.result.value:r};
const shots=[{n:'home-1440x900',w:1440,H:900,r:'home'},{n:'home-1920x1080',w:1920,H:1080,r:'home'},{n:'courtesy-1440x900',w:1440,H:900,r:'courtesy',full:true}];
let k=0;
for(const s of shots){
 await send('Emulation.setDeviceMetricsOverride',{width:s.w,height:s.H,deviceScaleFactor:1.5,mobile:false});
 await send('Page.navigate',{url:'about:blank'}); await sleep(200);
 await send('Page.navigate',{url:`${BASE}?nocache=${Date.now()}${k++}#/${s.r}`});
 for(let i=0;i<40&&!events.includes('Page.loadEventFired');i++)await sleep(100); events.length=0; await sleep(1500);
 if(s.full){const h=await ev('document.documentElement.scrollHeight');await send('Emulation.setDeviceMetricsOverride',{width:s.w,height:Math.max(s.H,h),deviceScaleFactor:1.5,mobile:false});await sleep(300)}
 const fit=await ev(`(()=>{const d=document.documentElement;const ls=[...document.querySelectorAll('.hv .scroll')].map(x=>x.scrollHeight+'/'+x.clientHeight);const t=[...document.querySelectorAll('.hvtile b')].filter(b=>b.scrollWidth>b.clientWidth+1).map(b=>b.textContent);return JSON.stringify({scrollH:d.scrollHeight,innerH:innerHeight,pageScrolls:d.scrollHeight>innerHeight,bodyScrollW:d.scrollWidth,lists:ls,clippedTiles:t,hvH:(document.querySelector('.hv')||{getBoundingClientRect:()=>({})}).getBoundingClientRect().height,side:document.querySelector('.side').getBoundingClientRect().width,ccCards:document.querySelectorAll('.ccv').length,ccRows:document.querySelectorAll('.hvcc').length,secmark:!!document.querySelector('.secmark'),foot:(()=>{const a=document.getElementById('bkfoot');return a?a.scrollWidth+'/'+a.parentElement.clientWidth+' h'+a.getBoundingClientRect().height:0})(),clipModel:[...document.querySelectorAll('.ccv .id b')].filter(b=>b.scrollWidth>b.clientWidth+1).map(b=>b.textContent)})})()`);
 console.log(s.n,fit);
 const r=await send('Page.captureScreenshot',{format:'png'});
 fs.writeFileSync(`${OUT}/${s.n}.png`,Buffer.from(r.data,'base64'));
}
console.log('JS exceptions:',errs.length,errs.slice(0,5));ws.close(); chrome.kill();
