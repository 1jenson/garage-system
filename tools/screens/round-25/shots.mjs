import {spawn} from 'node:child_process'; import fs from 'node:fs';
const CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const OUT=process.argv[2]; const PORT=9333; const BASE='http://localhost:8793/index.html';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const chrome=spawn(CHROME,['--headless=new','--disable-gpu','--hide-scrollbars','--no-first-run',`--remote-debugging-port=${PORT}`,`--user-data-dir=${process.argv[3]}`,'--window-size=1440,1000','about:blank'],{stdio:'ignore'});
let targets; for(let i=0;i<40;i++){try{targets=await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();if(targets.find(t=>t.type==='page'))break}catch{} await sleep(250)}
const ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
await new Promise(r=>ws.onopen=r);
let id=0; const pend=new Map(); const events=[];
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pend.has(m.id)){pend.get(m.id)(m);pend.delete(m.id)}else if(m.method)events.push(m.method)};
const send=(method,params={})=>new Promise(res=>{const i=++id;pend.set(i,m=>res(m.result||m.error));ws.send(JSON.stringify({id:i,method,params}))});
await send('Page.enable');await send('Runtime.enable');const errs=[];ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')errs.push(m.params.exceptionDetails.text+' '+(m.params.exceptionDetails.exception||{}).description)});
const ev=async(js)=>{const r=await send('Runtime.evaluate',{expression:js,awaitPromise:true,returnByValue:true});return r.result?r.result.value:r};
const shots=[
 {n:'01-diary-desktop',h:'#/diary',w:1440,H:1300,js:"day='2026-11-11';go();'ok'"},
 {n:'02-diary-desktop-1920',h:'#/diary',w:1920,H:1300,js:"day='2026-11-11';go();'ok'"},
 {n:'03-diary-laptop',h:'#/diary',w:1280,H:800,js:"day='2026-11-11';go();document.querySelector('.cols').scrollIntoView();'ok'"},
 {n:'04-booking-form-desktop',h:'#/diary',w:1440,H:1000,js:"day='2026-11-11';go();openBk('b10');'ok'"},
 {n:'06-lookup-desktop-1920',h:'#/home',w:1920,H:1200,js:"'ok'"},
 {n:'05-mobile-diary-service',h:'#/diary',w:375,H:812,s:3,m:true,js:"day='2026-11-11';go();document.querySelector('.dvr').scrollIntoView();'ok'"},
];
let k=0;
const ONLY=process.argv[4];
for(const s of shots){ if(ONLY&&!s.n.startsWith(ONLY))continue;
 const scale=s.s||2;
 await send('Emulation.setDeviceMetricsOverride',{width:s.w,height:s.H||1000,deviceScaleFactor:scale,mobile:!!s.m});
 await send('Page.navigate',{url:'about:blank'}); await sleep(200);
 await send('Page.navigate',{url:`${BASE}?nocache=${Date.now()}${k++}${s.h}`});
 for(let i=0;i<40&&!events.includes('Page.loadEventFired');i++)await sleep(100); events.length=0; await sleep(1200);
 if(s.js){await ev(s.js);await sleep(600)}
 if(s.fit){const b=await ev(`(()=>{const r=document.querySelector('${s.fit}').getBoundingClientRect();return Math.ceil(r.bottom+window.scrollY+40)})()`);await send('Emulation.setDeviceMetricsOverride',{width:s.w,height:b,deviceScaleFactor:scale,mobile:false});await sleep(500)}
 if(s.fitchk){console.log('  fit:',await ev(`(()=>{const x=document.querySelector('.modal .box');return x?x.scrollHeight+'/'+x.clientHeight+' vh='+innerHeight:'no modal'})()`))}
 const r=await send('Page.captureScreenshot',{format:'png'});
 fs.writeFileSync(`${OUT}/${s.n}.png`,Buffer.from(r.data,'base64'));
 console.log(s.n, fs.statSync(`${OUT}/${s.n}.png`).size, await ev('location.hash'));
}
console.log('JS exceptions:',errs.length,errs.slice(0,5));ws.close(); chrome.kill();
