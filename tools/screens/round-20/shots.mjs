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
 {n:'01-diary-desktop',h:'#/diary',w:1440,H:1500,js:"day='2026-11-11';go();'ok'"},
 {n:'02-diary-time-coloured-desktop',h:'#/diary',w:1440,H:1500,js:"day='2026-11-11';localStorage.setItem('ws.tmv','col');tmv='col';go();'ok'"},
 {n:'03-diary-time-big-desktop',h:'#/diary',w:1440,H:1500,js:"day='2026-11-11';localStorage.setItem('ws.tmv','big');tmv='big';go();'ok'"},
 {n:'04-book-service-form-desktop',h:'#/diary',w:1440,H:1100,js:"localStorage.removeItem('ws.tmv');tmv='box';day='2026-11-11';go();openBk('new','svc');'ok'"},
 {n:'05-book-unknown-reg-desktop',h:'#/diary',w:1440,H:1100,js:"day='2026-11-11';go();openBk('new','svc');edBk.reg='ZZ99 ABC';edBk.make='Honda Jazz 1.3';edBk.name='New customer';edBk.job='Clutch judder';go();'ok'"},
 {n:'06-day-sheet-desktop',h:'#/doc/diaryday/2026-11-11',w:1440,H:1400},
 {n:'07-tyres-desktop',h:'#/tyres/2026-11-11',w:1440,H:1100},
 {n:'08-tyre-callout-form-desktop',h:'#/tyres/2026-11-11',w:1440,H:1200,js:"document.querySelector('.actions .btn.pri').click();'ok'"},
 {n:'09-add-tyre-form-desktop',h:'#/tyres/2026-11-11',w:1440,H:1200,js:"document.querySelectorAll('.actions .btn.pri')[1].click();'ok'"},
 {n:'10-quote-new-desktop',h:'#/quote/new',w:1440,H:1500},
 {n:'11-quote-full-service-desktop',h:'#/quote/new',w:1440,H:1700,js:"qtpl(0);'ok'"},
 {n:'12-quote-more-menu-desktop',h:'#/quote/new',w:1440,H:1000,js:"document.querySelector('details.menu').open=true;'ok'"},
 {n:'13-quote-print-preview-desktop',h:'#/quote/new',w:1440,H:1500,js:"qPrev('new');'ok'"},
 {n:'14-quotes-list-desktop',h:'#/quotes',w:1440,H:1000},
 {n:'15-invoices-list-desktop',h:'#/invoices',w:1440,H:1000},
 {n:'20-mobile-diary',h:'#/diary',w:375,H:812,s:3,m:true,js:"day='2026-11-11';go();window.scrollTo(0,900);'ok'"},
 {n:'21-mobile-book-form',h:'#/diary',w:375,H:812,s:3,m:true,js:"day='2026-11-11';go();openBk('new','svc');'ok'"},
 {n:'22-mobile-tyres',h:'#/tyres/2026-11-11',w:375,H:812,s:3,m:true},
 {n:'23-mobile-add-tyre-form',h:'#/tyres/2026-11-11',w:375,H:812,s:3,m:true,js:"document.querySelectorAll('.actions .btn.pri')[1].click();'ok'"},
 {n:'24-mobile-quote-new',h:'#/quote/new',w:375,H:812,s:3,m:true},
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
 const r=await send('Page.captureScreenshot',{format:'png'});
 fs.writeFileSync(`${OUT}/${s.n}.png`,Buffer.from(r.data,'base64'));
 console.log(s.n, fs.statSync(`${OUT}/${s.n}.png`).size, await ev('location.hash'));
}
console.log('JS exceptions:',errs.length,errs.slice(0,5));ws.close(); chrome.kill();
