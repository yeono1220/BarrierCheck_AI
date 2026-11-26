/* BarrierCheck AI adapter.
   1) Local mode: same-origin calls to server.py (/api/status, /api/review). Key stays in the Python server.
   2) Browser mode (GitHub Pages, no server.py): the visitor enters their own Upstage API key.
      The key is kept in this tab's memory only (never stored, never sent anywhere except api.upstage.ai).
   Parsing mirrors server.py. No engineering decision is made here. */
(function(){
const API='https://api.upstage.ai/v2', LIMIT=840000;
const COMPACT_KEYS=['document_consistency','approval_compliance','reason'];
const REPORT_KEYS=['overall_decision','followup_type','recipient','psv_tag','action_items','document'];
const DECISIONS=['PASS','FAIL','검토 필요'];
const RULE_NODE='05_규칙평가_증빙대조';
const RULE_CODES=[...[1,2,3,4,5,6,7].map(i=>'R'+i),...[1,2,3,4,5,6,7,8].map(i=>'Q'+i)];
const RULE_STATES=['SATISFIED','VIOLATED','UNVERIFIED','NOT_APPLICABLE'];
const CITATION=/【[ \t]*†[ \t]*[0-9]+(?:[ \t]*[,，\-–][ \t]*[0-9]+)*[ \t]*】/g;
let KEY=null, CFG=null, mode='preview';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const sameKeys=(o,keys)=>o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).length===keys.length&&keys.every(k=>Object.hasOwn(o,k));

function unwrap(raw,keys){for(let i=0;i<4;i++){if(typeof raw==='string')raw=JSON.parse(raw);else if(sameKeys(raw,keys))return raw;else if(raw&&typeof raw==='object'&&'content' in raw)raw=raw.content;else return null;}return sameKeys(raw,keys)?raw:null;}
function findOutput(job,node,keys){
  if(job.status!=='completed')throw Error('Studio job is not completed.');
  const matches=[];let named=false;
  for(const step of job.output||[]){if(!step||typeof step!=='object')continue;const hit=['model','name','step_name'].some(k=>step[k]===node);if(hit)named=true;
    for(const item of step.content||[]){if(!item||item.type!=='output_text')continue;let v=null;try{v=unwrap(item.text,keys);}catch(_){continue;}if(v)matches.push([hit,v]);}}
  const c=named?matches.filter(m=>m[0]).map(m=>m[1]):matches.map(m=>m[1]);
  if(c.length!==1)throw Error('Cannot identify exactly one valid output for '+node+'. Check JSON syntax and API step names.');
  return c[0];}
function* ruleTexts(raw,depth=0){
  if(depth>12)return;
  if(typeof raw==='string'){const t=raw.trim().replace(/^﻿/,'');if(!t)return;
    if(/^["{\[]/.test(t)){let d;try{d=JSON.parse(t);}catch(_){d=undefined;}if(d!==undefined){yield* ruleTexts(d,depth+1);return;}}
    if(t.startsWith('```')&&t.endsWith('```')&&t.includes('\n')){yield* ruleTexts(t.split('\n').slice(1).join('\n').replace(/```\s*$/,''),depth+1);return;}
    yield t;}
  else if(Array.isArray(raw)){for(const x of raw)yield* ruleTexts(x,depth+1);}
  else if(raw&&typeof raw==='object'){for(const k of ['content','text','output_text','result','output','message','markdown','additional_values'])if(k in raw)yield* ruleTexts(raw[k],depth+1);
    if(['WORKFLOW_VERSION','A_DECISION','B_DECISION'].every(k=>k in raw))yield Object.entries(raw).filter(([,v])=>typeof v==='string').map(([k,v])=>k+'='+v).join('\n');}}
function parseRuleText(raw){
  const fields={};
  for(let line of raw.replace(/\r\n?/g,'\n').split('\n')){line=line.replace(/^[ \t]*(?:[-*•][ \t]+)?/,'');const m=line.match(/^[ *`_]*([A-Z][A-Z0-9_]*)[ *`_]*[ \t]*[=：:][ \t]*(.*)$/);if(m)(fields[m[1]]=fields[m[1]]||[]).push(m[2]);}
  const signature=['WORKFLOW_VERSION','A_DECISION','B_DECISION'].every(k=>k in fields);const rows={},evidence={},conflicts=[];
  for(const code of RULE_CODES){const values=fields[code]||[];const norm=values.map(v=>v.replace(CITATION,'').replace(/^[ \t*`_]+|[ \t*`_]+$/g,''));
    if(norm.length&&norm.every(v=>RULE_STATES.includes(v))&&new Set(norm).size===1)rows[code]=norm[0];else if(values.length)conflicts.push(code);
    const ev=fields[code+'_EVIDENCE']||[];if(ev.length&&new Set(ev).size===1)evidence[code]=ev[0].trim();}
  return [signature,rows,evidence,conflicts];}
function ruleSnapshot(job){
  let cands=[],named=false;
  for(const step of job.output||[]){if(!step||typeof step!=='object')continue;const hit=['model','name','step_name','node_name'].some(k=>step[k]===RULE_NODE);named=named||hit;
    for(const raw of ruleTexts(step.content||[])){const [sig,rows,ev,conf]=parseRuleText(raw);if(!hit&&!sig)continue;if(!Object.keys(rows).length)continue;cands.push([hit,rows,ev,conf]);}}
  if(named)cands=cands.filter(c=>c[0]);if(!cands.length)return null;
  const rows={},evidence={},blocked=new Set(),evb=new Set();
  for(const [,r,e,conf] of cands){conf.forEach(c=>blocked.add(c));for(const [k,v] of Object.entries(r)){if(k in rows&&rows[k]!==v)blocked.add(k);else rows[k]=v;}for(const [k,v] of Object.entries(e)){if(k in evidence&&evidence[k]!==v)evb.add(k);else evidence[k]=v;}}
  blocked.forEach(k=>{delete rows[k];delete evidence[k];});evb.forEach(k=>delete evidence[k]);
  return Object.keys(rows).length?{source:RULE_NODE,status:rows,evidence}:null;}
function resultFromJob(job,cfg){
  const node=cfg.result_node,reportNode=cfg.report_node||'08_요약보고서';
  const decision=findOutput(job,node,COMPACT_KEYS);
  if(!DECISIONS.includes(decision.document_consistency)||!DECISIONS.includes(decision.approval_compliance)||typeof decision.reason!=='string')throw Error('07 decision output violates the three-field contract.');
  let report=null,warning=null;
  try{const c=findOutput(job,reportNode,REPORT_KEYS);
    if(REPORT_KEYS.filter(k=>k!=='action_items').some(k=>typeof c[k]!=='string')||!Array.isArray(c.action_items)||!c.action_items.every(x=>typeof x==='string'))throw Error('08 report has invalid field types.');
    const expected=['FAIL','검토 필요','PASS'].find(v=>[decision.document_consistency,decision.approval_compliance].includes(v));
    const types={'FAIL':['부적합·재작업 요청서','정비·시험 담당'],'검토 필요':['보완 요청서','정비 패키지 제출자'],'PASS':['종결 검토 기록','설비 담당 승인자']};
    if(c.overall_decision!==expected||c.followup_type!==types[expected][0]||c.recipient!==types[expected][1]||(expected==='PASS'&&c.action_items.length))throw Error('08 report conflicts with 07 decision or the follow-up contract.');
    report=c;}catch(e){warning=String(e.message||e);}
  return {decision_output:decision,followup_output:report,followup_error:warning,rule_snapshot:ruleSnapshot(job)};}

async function api(path,{method='GET',body=null,ctype=null,signal}={}){
  const headers={'Authorization':'Bearer '+KEY,'Accept':'application/json','x-project-id':CFG.project_id};if(ctype)headers['Content-Type']=ctype;
  let res;try{res=await fetch(API+path,{method,headers,body,signal});}catch(e){if(signal?.aborted)throw e;throw Error('Upstage connection error.');}
  if(!res.ok){const stage=path.startsWith('/files')?'File upload':path==='/responses'?'Job creation':'Job polling';const msg={401:'API key rejected',403:'Key not authorized for this workflow/project',404:'Resource not found',429:'API quota or rate limit reached'}[res.status]||'Upstage API request failed';throw Error(`${stage}: ${msg} (HTTP ${res.status}).`);}
  return res.json();}
async function runBrowser(pdf,{signal}={}){
  const start=Date.now();const fd=new FormData();fd.append('purpose','user_data');fd.append('file',new Blob([await pdf.arrayBuffer()],{type:'application/pdf'}),'document.pdf');
  let up=await api('/files',{method:'POST',body:fd,signal});const fileId=up.id;if(!fileId)throw Error('Studio did not return a file ID.');
  while(String(up.status||'').toUpperCase()==='PROCESSING'){if(Date.now()-start>LIMIT)throw Error('File preparation timed out.');await sleep(2000);up=await api('/files/'+encodeURIComponent(fileId)+'?view=status&pages=none',{signal});const s=String(up.status||'').toUpperCase();if(['UPLOADED','READY',''].includes(s))break;if(s!=='PROCESSING')throw Error('File preparation did not return a ready status: '+s);}
  const body={model:CFG.workflow_id,config_id:CFG.config_id,include:['all'],input:[{role:'user',content:[{type:'input_file',file_id:fileId}]}]};
  let job=await api('/responses',{method:'POST',body:JSON.stringify(body),ctype:'application/json',signal});const jobId=job.id;if(!jobId)throw Error('Studio did not return a job ID.');
  while(true){if(Date.now()-start>LIMIT)throw Error('Polling timeout. Studio may still be running; check its monitoring page.');job=await api('/responses/'+encodeURIComponent(jobId)+'?include=all',{signal});
    if(job.status==='completed'){const r=resultFromJob(job,CFG);r.job_id=jobId;return r;}
    if(!['queued','in_progress','cancelling'].includes(job.status))throw Error('Studio job ended without a result ('+job.status+').');await sleep(2000);}}

window.__bcParse={resultFromJob};
window.BarrierCheckAdapter={isConnected:false,
  async run(pdfFile,{signal}={}){
    if(mode==='browser')return runBrowser(pdfFile,{signal});
    const res=await fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/pdf'},body:pdfFile,signal});const body=await res.json().catch(()=>null);
    if(!res.ok||!body)throw new Error(body?.error||`Backend response error (${res.status})`);return body.result;}};

function connectUI(){
  const host=document.querySelector('.sidebottom');if(!host||document.getElementById('byokBox'))return;
  const box=document.createElement('div');box.id='byokBox';box.className='byok';
  box.innerHTML='<div class="byok-title">Live API (browser)</div><input id="byokKey" type="password" autocomplete="off" placeholder="Upstage API key"><button id="byokBtn" class="btn primary small" type="button">Connect</button><div id="byokNote" class="byok-note">Key stays in this tab only; sent only to api.upstage.ai.</div>';
  host.prepend(box);
  const btn=box.querySelector('#byokBtn'),inp=box.querySelector('#byokKey'),note=box.querySelector('#byokNote');
  btn.addEventListener('click',async()=>{
    if(mode==='browser'){KEY=null;mode='preview';window.BarrierCheckAdapter.isConnected=false;inp.value='';inp.disabled=false;btn.textContent='Connect';note.textContent='Disconnected. Key cleared from memory.';configure();return;}
    const k=inp.value.trim();if(!k)return;btn.disabled=true;note.textContent='Checking key…';KEY=k;
    try{const r=await fetch(API+'/responses/job_check?include=all',{headers:{'Authorization':'Bearer '+k,'Accept':'application/json','x-project-id':CFG.project_id}});
      if(r.status===401||r.status===403){KEY=null;note.textContent='Key rejected for this workflow project (HTTP '+r.status+').';return;}
      mode='browser';Object.assign(window.BarrierCheckAdapter,{isConnected:true,label:CFG.label+' (browser)',outputContract:'compact'});
      inp.value='';inp.disabled=true;btn.textContent='Disconnect';note.textContent='Connected. Each PDF runs as a Studio job and uses this key\'s credits.';configure();
      document.getElementById('integrationHint').textContent='Live API in browser mode for '+CFG.label+'. Each PDF runs as a separate Studio job.';
    }catch(_){KEY=null;note.textContent='Could not reach api.upstage.ai.';}
    finally{btn.disabled=false;}});}

window.addEventListener('DOMContentLoaded',async()=>{
  try{const res=await fetch('/api/status',{cache:'no-store'});const info=await res.json();
    if(res.ok&&info.configured===true){mode='local';Object.assign(window.BarrierCheckAdapter,{isConnected:true,label:info.label,outputContract:info.output_contract});configure();
      document.getElementById('engineText').textContent='Studio target: '+info.label;document.getElementById('integrationHint').textContent='Live API configured for '+info.label+'. Each PDF runs as a separate Studio job.';return;}
  }catch(_){}
  try{CFG=await (await fetch('workflow_config.json',{cache:'no-store'})).json();if(CFG.output_contract==='compact')connectUI();}catch(_){/* preview only */}
});
})();
