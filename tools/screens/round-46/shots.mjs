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
// round 46: measure the Notes for Jenson column (last note, divider, title, textarea, Save note)
const NOTES=`(()=>{const R=e=>e?e.getBoundingClientRect():null;const sec=document.querySelector('.hvnotes');const sc=sec.querySelector('.scroll');const ns=sc.querySelectorAll('.hvn');const last=R(ns[ns.length-1]);const jot=R(sec.querySelector('.jot'));const h=R(sec.querySelector('.jot h2'));const ta=R(sec.querySelector('#hvjt'));const sv=R(sec.querySelector('.jsave'));const sr=R(sec);return JSON.stringify({notes:ns.length,listScroll:sc.scrollHeight+'/'+sc.clientHeight,lastNoteBottom:Math.round(last.bottom),listBottom:Math.round(R(sc).bottom),dividerTop:Math.round(jot.top),titleTop:Math.round(h.top),textareaH:Math.round(ta.height),saveBottom:Math.round(sv.bottom),sectionBottom:Math.round(sr.bottom),saveVisible:sv.bottom<=sr.bottom-1})})()`;
const shots=[{n:'home-1920x1080',w:1920,H:1080,r:'home'},{n:'home-1440x900',w:1440,H:900,r:'home'}];
let k=0;
for(const s of shots){
 await send('Emulation.setDeviceMetricsOverride',{width:s.w,height:s.H,deviceScaleFactor:1.5,mobile:false});
 await send('Page.navigate',{url:'about:blank'}); await sleep(200);
 await send('Page.navigate',{url:`${BASE}?nocache=${Date.now()}${k++}#/${s.r}`});
 for(let i=0;i<40&&!events.includes('Page.loadEventFired');i++)await sleep(100); events.length=0; for(let i=0;i<50&&!(await ev("!!document.querySelector('.hvnotes .jot')"));i++)await sleep(100); await sleep(1500);
 if(s.full){const h=await ev('document.documentElement.scrollHeight');await send('Emulation.setDeviceMetricsOverride',{width:s.w,height:Math.max(s.H,h),deviceScaleFactor:1.5,mobile:false});await sleep(300)}
 const fit=await ev(`(()=>{const d=document.documentElement;const ls=[...document.querySelectorAll('.hv .scroll')].map(x=>x.scrollHeight+'/'+x.clientHeight);const t=[...document.querySelectorAll('.hvtile b')].filter(b=>b.scrollWidth>b.clientWidth+1).map(b=>b.textContent);return JSON.stringify({scrollH:d.scrollHeight,innerH:innerHeight,pageScrolls:d.scrollHeight>innerHeight,bodyScrollW:d.scrollWidth,lists:ls,clippedTiles:t,hvH:(document.querySelector('.hv')||{getBoundingClientRect:()=>({})}).getBoundingClientRect().height,side:document.querySelector('.side').getBoundingClientRect().width,ccCards:document.querySelectorAll('.ccv').length,ccRows:document.querySelectorAll('.hvcc').length,secmark:!!document.querySelector('.secmark'),foot:(()=>{const a=document.getElementById('bkfoot');return a?a.scrollWidth+'/'+a.parentElement.clientWidth+' h'+a.getBoundingClientRect().height:0})(),rdy:[...document.querySelectorAll('.hvr .row')].map(r=>Math.round(r.getBoundingClientRect().bottom)).join(','),rdyCard:(()=>{const c=document.querySelector('.hvr');return c?Math.round(c.getBoundingClientRect().bottom):0})(),rdyClip:[...document.querySelectorAll('.hvr .x')].filter(b=>b.scrollWidth>b.clientWidth+1).map(b=>b.textContent),clipModel:[...document.querySelectorAll('.ccv .id b')].filter(b=>b.scrollWidth>b.clientWidth+1).map(b=>b.textContent)})})()`);
 console.log(s.n,fit); console.log(s.n,'notes',await ev(NOTES));
 const r=await send('Page.captureScreenshot',{format:'png'});
 fs.writeFileSync(`${OUT}/${s.n}.png`,Buffer.from(r.data,'base64'));
}
console.log('JS exceptions:',errs.length,errs.slice(0,5));ws.close(); chrome.kill();
