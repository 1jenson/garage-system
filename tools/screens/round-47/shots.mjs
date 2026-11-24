// round 47: Tyres day page. Usage: node shots.mjs <outDir> <chromeProfileDir> [beforeBaseUrl]
// Logs the y of the two column headings, buttons and first cards on Tyres and Diary (before and after),
// then shoots tyres at 1920x1080 and 1440x900 and the Add tyre to list modal with the Time in options shown.
import {spawn} from 'node:child_process'; import fs from 'node:fs';
const CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const OUT=process.argv[2]; const PROFILE=process.argv[3]; const BEFORE=process.argv[4]||'';
if(!OUT||!PROFILE){console.error('usage: node shots.mjs <outDir> <chromeProfileDir> [beforeBaseUrl]');process.exit(1)}
const PORT=9336; const BASE='http://localhost:8793/index.html';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const chrome=spawn(CHROME,['--headless=new','--disable-gpu','--hide-scrollbars','--no-first-run',`--remote-debugging-port=${PORT}`,`--user-data-dir=${PROFILE}`,'--window-size=1920,1080','about:blank']);
let targets; for(let i=0;i<40;i++){try{targets=await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();if(targets.find(t=>t.type==='page'))break}catch{} await sleep(250)}
const ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
await new Promise(r=>ws.onopen=r);
let id=0; const pend=new Map(); const events=[]; const errs=[];
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pend.has(m.id)){pend.get(m.id)(m);pend.delete(m.id)}else if(m.method){events.push(m.method);if(m.method==='Runtime.exceptionThrown')errs.push(m.params.exceptionDetails.text+' '+(m.params.exceptionDetails.exception||{}).description)}};
const send=(method,params={})=>new Promise(res=>{const i=++id;pend.set(i,m=>res(m.result||m.error));ws.send(JSON.stringify({id:i,method,params}))});
await send('Page.enable');await send('Runtime.enable');
const ev=async(js)=>{const r=await send('Runtime.evaluate',{expression:js,awaitPromise:true,returnByValue:true});return r.result?r.result.value:r};
let k=0;
const open=async(base,route,w,H,ready)=>{
 await send('Emulation.setDeviceMetricsOverride',{width:w,height:H,deviceScaleFactor:1.5,mobile:false});
 await send('Page.navigate',{url:'about:blank'}); await sleep(200); events.length=0;
 await send('Page.navigate',{url:`${base}?nocache=${Date.now()}${k++}#/${route}`});
 for(let i=0;i<40&&!events.includes('Page.loadEventFired');i++)await sleep(100);
 for(let i=0;i<60&&!(await ev(`!!document.querySelector(${JSON.stringify(ready)})`));i++)await sleep(100); await sleep(1200)};
// y of each section's heading (Diary: MOTs section and the first section inside .dvr), its header button and first card, for every .dv .cols on the page
const COLS=`(()=>{const y=e=>e?Math.round(e.getBoundingClientRect().top):null;return JSON.stringify([...document.querySelectorAll('.dv .cols')].map(c=>[...c.children].flatMap(x=>x.matches('section.dvsec')?[x]:x.matches('.dvr')?[...x.children].filter(z=>z.matches('section.dvsec')).slice(0,1):[]).map(s=>({h:(s.querySelector('h2')||{}).textContent?.trim().slice(0,24),h2:y(s.querySelector('h2')),btn:y(s.querySelector('h2 button, .hd button, button')),card:y(s.querySelector('.dvslot, .dvjob, .card')),mt:getComputedStyle(s).marginTop}))))})()`;
const measure=async(label,base)=>{for(const [route,ready] of [['tyres','.dv .cols section.dvsec'],['diary','.dv .cols section.dvsec']]){for(const [w,H] of [[1920,1080],[1000,900]]){await open(base,route,w,H,ready);console.log(label,route,`${w}x${H}`,await ev(COLS))}}};
if(BEFORE)await measure('BEFORE',BEFORE);
await measure('AFTER',BASE);
for(const s of [{n:'tyres-1920x1080',w:1920,H:1080},{n:'tyres-1440x900',w:1440,H:900}]){
 await open(BASE,'tyres',s.w,s.H,'.dv .cols section.dvsec');
 console.log(s.n,await ev(`JSON.stringify({scrollW:document.documentElement.scrollWidth,undef:document.body.innerText.includes('undefined'),pills:[...document.querySelectorAll('.tycyc')].map(b=>b.textContent.trim())})`));
 const r=await send('Page.captureScreenshot',{format:'png'}); fs.writeFileSync(`${OUT}/${s.n}.png`,Buffer.from(r.data,'base64'));
}
// modal: open Add tyre to list, show the Time in select as an open list (native popups are not captured headless)
await open(BASE,'tyres',1920,1080,'.dv .cols section.dvsec');
await ev(`tyAdd('');1`); await sleep(800);
console.log('modal',await ev(`(()=>{const sel=[...document.querySelectorAll('.modal label.field')].find(l=>l.querySelector('span')?.textContent.trim()==='Time in')?.querySelector('select');if(!sel)return 'no Time in select';sel.size=sel.options.length;sel.style.height='auto';sel.style.overflow='hidden';sel.scrollIntoView({block:'center'});return JSON.stringify({title:document.querySelector('.modal h2')?.textContent.trim().slice(0,40),options:[...sel.options].map(o=>o.textContent)})})()`));
await sleep(400);
{const r=await send('Page.captureScreenshot',{format:'png'}); fs.writeFileSync(`${OUT}/tyres-modal-1920x1080.png`,Buffer.from(r.data,'base64'))}
console.log('JS exceptions:',errs.length,errs.slice(0,5));ws.close(); chrome.kill();
