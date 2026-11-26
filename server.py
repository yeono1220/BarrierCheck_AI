"""Local demo bridge. Standard library only; no engineering decisions here."""
import getpass, json, os, re, secrets, time, urllib.request, urllib.error, webbrowser, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from functools import partial
from urllib.parse import urlsplit, urlencode, quote

ROOT=Path(__file__).resolve().parent
API='https://api.upstage.ai/v2'
KEYS=set('workflow_version psv_tag decision a_decision b_decision a_issues b_issues test_attribution missing_documents rule_status data_status data_issues independent_validation facts follow_up reason'.split())
COMPACT_KEYS=set("document_consistency approval_compliance reason".split())
REPORT_KEYS=set("overall_decision followup_type recipient psv_tag action_items document".split())
COMPACT_DECISIONS=("PASS","FAIL","검토 필요")
MAX_BYTES=30*1024*1024
LIMIT=840
class BridgeError(Exception): pass

def strict_json(s):
    def reject(v): raise ValueError('Nonstandard JSON constant: '+v)
    def pairs(items):
        out={}
        for k,v in items:
            if k in out: raise ValueError('Duplicate key: '+k)
            out[k]=v
        return out
    return json.loads(s,parse_constant=reject,object_pairs_hook=pairs)

def unwrap(raw,keys=KEYS):
    # Preserve the output object; only remove the transport envelope, never repair JSON.
    for _ in range(4):
        if isinstance(raw,str): raw=strict_json(raw)
        elif isinstance(raw,dict) and set(raw)==keys: return raw
        elif isinstance(raw,dict) and 'content' in raw: raw=raw['content']
        else: return None
    return raw if isinstance(raw,dict) and set(raw)==keys else None

def find_output(job,node,keys=KEYS):
    if job.get('status')!='completed': raise BridgeError('Studio job is not completed.')
    matches=[]; named=[]
    for step in job.get('output',[]):
        if not isinstance(step,dict): continue
        names=[step.get(k) for k in ('model','name','step_name')]
        is_named=node in names
        if is_named: named.append(True)
        for item in step.get('content',[]):
            if not isinstance(item,dict) or item.get('type')!='output_text': continue
            try: value=unwrap(item.get('text'),keys)
            except (ValueError,TypeError): continue
            if value is not None: matches.append((is_named,value))
    # Prefer identifiable 07 output. If API only exposes generated step names,
    # require exactly one full 16-key object in ALL steps (08 report is not used).
    if named:
        candidates=[v for hit,v in matches if hit]
    else: candidates=[v for _,v in matches]
    if len(candidates)!=1:
        raise BridgeError(f'Cannot identify exactly one valid output for {node}. Check JSON syntax and API step names.')
    return candidates[0]

RULE_CODES=tuple([f'R{i}' for i in range(1,8)]+[f'Q{i}' for i in range(1,9)])
RULE_STATES=('SATISFIED','VIOLATED','UNVERIFIED','NOT_APPLICABLE')
# Citation decorations are transport metadata, not engineering state values.
RULE_NODE='05_규칙평가_증빙대조'
CITATION=re.compile(r'【[ \t]*†[ \t]*[0-9]+(?:[ \t]*[,，\-–][ \t]*[0-9]+)*[ \t]*】')

def rule_texts(raw,depth=0):
    if depth>12: return
    if isinstance(raw,str):
        t=raw.strip().lstrip('\ufeff')
        if not t: return
        if t.startswith(('"','{','[')):
            try: decoded=strict_json(t)
            except (ValueError,TypeError): decoded=None
            if decoded is not None:
                yield from rule_texts(decoded,depth+1)
                return
        if t.startswith('```') and t.endswith('```') and '\n' in t:
            yield from rule_texts(t.split('\n',1)[1].rsplit('```',1)[0],depth+1)
            return
        yield t
    elif isinstance(raw,dict):
        # Only recognized envelopes, never arbitrary source document fields.
        for k in ('content','text','output_text','result','output','message','markdown','additional_values'):
            if k in raw: yield from rule_texts(raw[k],depth+1)
        # Some API envelopes may represent the same explicit contract as a mapping.
        if all(k in raw for k in ('WORKFLOW_VERSION','A_DECISION','B_DECISION')):
            yield '\n'.join(str(k)+'='+str(v) for k,v in raw.items() if isinstance(v,str))
    elif isinstance(raw,list):
        for x in raw: yield from rule_texts(x,depth+1)

def parse_rule_text(raw):
    # Only anchored contract fields. Preserve evidence verbatim; strip citations
    # ONLY from a fixed status token. Never search evidence prose for states.
    lines=raw.replace('\r\n','\n').replace('\r','\n').split('\n')
    fields={}
    for line in lines:
        # Support harmless markdown around an otherwise exact key/value line.
        line=re.sub(r'^[ \t]*(?:[-*•][ \t]+)?','',line)
        m=re.fullmatch(r'[ *`_]*([A-Z][A-Z0-9_]*)[ *`_]*[ \t]*[=：:][ \t]*(.*)',line)
        if m: fields.setdefault(m[1],[]).append(m[2])
    signature=all(k in fields for k in ('WORKFLOW_VERSION','A_DECISION','B_DECISION'))
    rows={}; evidence={}; conflicts=[]
    for code in RULE_CODES:
        values=fields.get(code,[])
        normalized=[CITATION.sub('',v).strip(' \t*`_') for v in values]
        if normalized and all(v in RULE_STATES for v in normalized) and len(set(normalized))==1:
            rows[code]=normalized[0]
        elif values: conflicts.append(code)
        ev=fields.get(code+'_EVIDENCE',[])
        if ev and len(set(ev))==1: evidence[code]=ev[0].strip()
    return signature,rows,evidence,conflicts

def rule_snapshot(job):
    candidates=[]; named=False; shape=[]
    for step in job.get('output',[]):
        if not isinstance(step,dict): continue
        names=[step.get(k) for k in ('model','name','step_name','node_name')]
        hit=RULE_NODE in names
        named=named or hit
        shape.append(str(next((n for n in names if isinstance(n,str)), '(unnamed)'))[:100])
        for raw in rule_texts(step.get('content',[])):
            signature,rows,evidence,conflicts=parse_rule_text(raw)
            if not hit and not signature: continue
            if not rows: continue
            # A generated step name need not be stable across classifier branches.
            # Require the contract signature, not 15 perfect states, for fallback.
            candidate=(hit,rows,evidence,conflicts)
            if candidate not in candidates: candidates.append(candidate)
    if named: candidates=[x for x in candidates if x[0]]
    if not candidates:
        print('05 rule snapshot unavailable | API steps:',', '.join(shape),flush=True)
        return None
    # Repeated identical output or compatible fragments do not invalidate it.
    # Conflicting explicit states are not guessed. Preserve other known states.
    rows={}; evidence={}; blocked=set(); ev_blocked=set()
    for _,r,e,conflicts in candidates:
        blocked.update(conflicts)
        for code,value in r.items():
            if code in rows and rows[code]!=value: blocked.add(code)
            else: rows[code]=value
        for code,value in e.items():
            if code in evidence and evidence[code]!=value: ev_blocked.add(code)
            else: evidence[code]=value
    for code in blocked: rows.pop(code,None); evidence.pop(code,None)
    for code in ev_blocked: evidence.pop(code,None)
    if not rows: return None
    print('05 rule snapshot:',len(rows),'/ 15 explicit states', '| unresolved:',','.join(c for c in RULE_CODES if c not in rows) or 'none',flush=True)
    return {'source':RULE_NODE,'status':rows,'evidence':evidence}

def result_from_job(job,node,contract='full16',report_node='08_요약보고서'):
    if contract=='full16': return find_output(job,node)
    decision=find_output(job,node,COMPACT_KEYS)
    if any(decision[k] not in COMPACT_DECISIONS for k in ('document_consistency','approval_compliance')) or not isinstance(decision['reason'],str):
        raise BridgeError('07 decision output violates the three-field contract.')
    report=None; warning=None
    try:
        candidate=find_output(job,report_node,REPORT_KEYS)
        if any(not isinstance(candidate[k],str) for k in REPORT_KEYS-{'action_items'}) or not isinstance(candidate['action_items'],list) or not all(isinstance(x,str) for x in candidate['action_items']):
            raise BridgeError('08 report has invalid field types.')
        expected=next(v for v in ('FAIL','검토 필요','PASS') if v in (decision['document_consistency'],decision['approval_compliance']))
        types={'FAIL':('부적합·재작업 요청서','정비·시험 담당'),'검토 필요':('보완 요청서','정비 패키지 제출자'),'PASS':('종결 검토 기록','설비 담당 승인자')}
        if candidate['overall_decision']!=expected or (candidate['followup_type'],candidate['recipient'])!=types[expected] or (expected=='PASS' and candidate['action_items']):
            raise BridgeError('08 report conflicts with 07 decision or the follow-up contract.')
        report=candidate
    except BridgeError as e: warning=str(e)
    # Transport envelope only: preserve both original node objects, never fill missing results.
    return {'decision_output':decision,'followup_output':report,'followup_error':warning,'rule_snapshot':rule_snapshot(job)}

def request_api(key,path,method='GET',payload=None,ctype=None,timeout=40,*,project_id):
    headers={'Authorization':'Bearer '+key,'Accept':'application/json','x-project-id':project_id}
    if ctype: headers['Content-Type']=ctype
    req=urllib.request.Request(API+path,data=payload,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as resp:
            return strict_json(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        # Display limited, redacted provider diagnostics in the local console only.
        route=path.split('?',1)[0]
        stage={'/files':'1. File upload','/responses':'2. Job creation'}.get(route, 'File preparation' if route.startswith('/files/') else '3. Job polling' if route.startswith('/responses/') else 'API request')
        msg={401:'Authentication rejected',403:'Request forbidden by Upstage',404:'Requested resource not found',429:'API quota or rate limit reached'}.get(e.code,'Upstage API request failed')
        detail=f'{stage}: {msg} (HTTP {e.code}). Check organization, project access, usage and Studio monitoring.'
        print(detail,flush=True)
        try:
            raw=e.read(8192).decode('utf-8',errors='replace')
            # Do not display arbitrary payloads or credentials. Prefer API error fields.
            parsed=json.loads(raw)
            err=parsed.get('error',parsed) if isinstance(parsed,dict) else {}
            if isinstance(err,str): err={'message':err}
            if isinstance(err,dict):
                info={k:str(err[k])[:1200] for k in ('code','type','message','detail') if isinstance(err.get(k),(str,int))}
                safe=json.dumps(info,ensure_ascii=False).replace(key,'[REDACTED]') if key else json.dumps(info,ensure_ascii=False)
                safe=re.sub(r'up_[A-Za-z0-9_-]{8,}', '[REDACTED]', safe)
                print('Upstage error detail:',safe if info else '(no standard error fields)',flush=True)
            else: print('Upstage error detail: (unrecognized error format)',flush=True)
        except Exception: print('Upstage error detail: (unavailable or non-JSON)',flush=True)
        rid=e.headers.get('x-request-id') if e.headers else None
        if rid: print('Upstage request ID:',str(rid)[:200].replace(key,'[REDACTED]') if key else str(rid)[:200],flush=True)
        raise BridgeError(detail+' See the local terminal for provider error details.') from None
    except (OSError,ValueError) as e: raise BridgeError('Upstage connection or response error: '+type(e).__name__) from None

def run_studio(pdf,config,key,request=None,sleep=time.sleep,clock=time.monotonic):
    if request is None: request=partial(request_api,project_id=config['project_id'])
    start=clock(); boundary='bc'+secrets.token_hex(16)
    # Do not send original filename (could contain expected labels).
    head=(f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nuser_data\r\n'
          f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="document.pdf"\r\nContent-Type: application/pdf\r\n\r\n').encode()
    upload=request(key,'/files','POST',head+pdf+f'\r\n--{boundary}--\r\n'.encode(),'multipart/form-data; boundary='+boundary)
    file_id=upload.get('id')
    if not isinstance(file_id,str) or not file_id: raise BridgeError('Studio did not return a file ID.')
    while str(upload.get('status','')).upper()=='PROCESSING':
        remaining=LIMIT-(clock()-start)
        if remaining<=0: raise BridgeError('File preparation timed out.')
        meta=request(key,'/files/'+quote(file_id,safe='')+'?view=status&pages=none',timeout=min(40,max(1,remaining)))
        state=str(meta.get('status','')).upper()
        if state in ('UPLOADED','READY',''): break
        if state!='PROCESSING': raise BridgeError('File preparation did not return a ready status: '+(state or 'missing'))
        sleep(min(2,max(0,remaining)))
    body={'model':config['workflow_id'],'config_id':config['config_id'],'include':['all'],'input':[{'role':'user','content':[{'type':'input_file','file_id':file_id}]}]}
    job=request(key,'/responses','POST',json.dumps(body).encode(),'application/json')
    created=job
    job_id=job.get('id')
    if not isinstance(job_id,str) or not job_id: raise BridgeError('Studio did not return a job ID.')
    print('Studio job:',job_id,flush=True)
    # Always retrieve full step outputs, even if create immediately reports completed.
    while True:
        remaining=LIMIT-(clock()-start)
        if remaining<=0: raise BridgeError('Local polling timeout. Studio may still be running; check its monitoring page before retrying.')
        job=request(key,'/responses/'+quote(job_id,safe='')+'?'+urlencode({'include':'all'}),timeout=min(40,max(1,remaining)))
        state=job.get('status')
        if state=='completed': return completed_result(job,job_id,config,key,request,initial_job=created)
        if state not in ('queued','in_progress','cancelling'): raise BridgeError(f'Studio job ended without a result ({state}). See Studio monitoring.')
        sleep(min(2,max(0,LIMIT-(clock()-start))))

def completed_result(job,job_id,config,key,request,initial_job=None):
    contract=config.get('output_contract','full16')
    node=config['result_node']; report_node=config.get('report_node','08_요약보고서')
    result=result_from_job(job,node,contract,report_node)
    if contract!='compact': return result
    def coverage(r): return len((r.get('rule_snapshot') or {}).get('status',{}))
    def consider(other_job):
        nonlocal result
        if not isinstance(other_job,dict) or other_job.get('status')!='completed': return
        try: other=result_from_job(other_job,node,'compact',report_node)
        except BridgeError: return
        if other['decision_output']!=result['decision_output']: return
        if coverage(other)>coverage(result):
            old=(result.get('rule_snapshot') or {}).get('status',{})
            new=other['rule_snapshot']['status']
            if all(new.get(k)==v for k,v in old.items()): result['rule_snapshot']=other['rule_snapshot']
        if result.get('followup_output') is None and other.get('followup_output') is not None:
            result['followup_output']=other['followup_output'];result['followup_error']=None
    if coverage(result)<15: consider(initial_job)
    raw_attempts=[job]
    if coverage(result)<15:
        # Read-only retry of the SAME job, never create another job or upload again.
        try:
            alternate=request(key,'/responses/'+quote(job_id,safe='')+'?'+urlencode({'include[]':'all'}))
            raw_attempts.append(alternate);consider(alternate)
        except (BridgeError,OSError,ValueError,TypeError) as e:
            print('Alternative read-only output query unavailable:',type(e).__name__,flush=True)
    result['job_id']=job_id
    if coverage(result)<15:
        # Store only the actual candidate step outputs locally for troubleshooting.
        # No credentials, request headers, or input PDF are stored here.
        try:
            out=ROOT/'diagnostics';out.mkdir(exist_ok=True)
            safe_id=re.sub(r'[^A-Za-z0-9_-]','_',job_id)[:120]
            records=[]
            for response in raw_attempts:
                steps=[]
                for step in response.get('output',[]):
                    if not isinstance(step,dict): continue
                    names={k:step.get(k) for k in ('model','name','step_name','node_name') if isinstance(step.get(k),str)}
                    texts=list(rule_texts(step.get('content',[])))
                    candidates=[t for t in texts if parse_rule_text(t)[0] or RULE_NODE in names.values()]
                    steps.append({'names':names,'rule_candidates':candidates})
                records.append({'status':response.get('status'),'steps':steps})
            (out/(safe_id+'_rules.json')).write_text(json.dumps({'job_id':job_id,'reported':coverage(result),'attempts':records},ensure_ascii=False,indent=2),encoding='utf-8')
            print('Rule diagnostics saved:',safe_id+'_rules.json',flush=True)
        except (OSError,ValueError,TypeError) as e: print('Could not save rule diagnostics:',type(e).__name__,flush=True)
    return result

def recover_job(job_id):
    # Local-only retrieval of an existing completed job. No upload or creation.
    cfg=load_config()
    if not re.fullmatch(r'job_[A-Za-z0-9_-]+',job_id): raise BridgeError('Enter an existing job_ ID from the terminal.')
    key=os.environ.get('UPSTAGE_API_KEY') or getpass.getpass('Upstage API key (hidden): ').strip()
    if not key: raise BridgeError('API key required.')
    request=partial(request_api,project_id=cfg['project_id'])
    job=request(key,'/responses/'+quote(job_id,safe='')+'?'+urlencode({'include':'all'}))
    result=completed_result(job,job_id,cfg,key,request)
    out=ROOT/(job_id+'_result.json')
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved:',out,flush=True)
    print('Import this JSON in the dashboard; confirm it belongs to the selected PDF.',flush=True)

def load_config():
    cfg=strict_json((ROOT/'workflow_config.json').read_text(encoding='utf-8'))
    for name,prefix in [('workflow_id','agt_'),('project_id','proj_')]:
        if not isinstance(cfg.get(name),str) or not re.fullmatch(prefix+r'[A-Za-z0-9_-]+',cfg[name]): raise ValueError('Invalid '+name)
    if not isinstance(cfg.get('config_id'),str) or not re.fullmatch(r'(?:[1-9][0-9]*|cfg_[A-Za-z0-9_-]+)',cfg['config_id']): raise ValueError('Invalid config_id: use the saved version from Studio Code')
    for name in ('label','result_node'):
        if not isinstance(cfg.get(name),str) or not cfg[name]: raise ValueError('Invalid '+name)
    if cfg.get('output_contract','full16') not in ('full16','compact'): raise ValueError('Invalid output_contract')
    return cfg

class Handler(BaseHTTPRequestHandler):
    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/status': return self.send_json(200,{'configured':bool(self.server.key),'label':self.server.config['label'],'output_contract':self.server.config.get('output_contract','full16')})
        files={'/':('index.html','text/html'),'/index.html':('index.html','text/html'),'/style.css':('style.css','text/css'),'/app.js':('app.js','application/javascript'),'/adapter.js':('adapter.js','application/javascript')}
        if path not in files: return self.send_error(404)
        f,typ=files[path];raw=(ROOT/f).read_bytes();self.send_response(200);self.send_header('Content-Type',typ+'; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        if urlsplit(self.path).path!='/api/review': return self.send_error(404)
        host=self.headers.get('Host',''); origin=self.headers.get('Origin','')
        if host not in self.server.allowed_hosts or (origin and origin!='http://'+host): return self.send_json(403,{'error':'Only local same-origin requests are allowed.'})
        if not self.server.key: return self.send_json(503,{'error':'API key not configured. Restart local server.'})
        if self.headers.get_content_type()!='application/pdf': return self.send_json(415,{'error':'Expected PDF upload.'})
        try: n=int(self.headers.get('Content-Length','0'))
        except ValueError: n=0
        if not 0<n<=MAX_BYTES: return self.send_json(413,{'error':'Select a PDF up to 30 MB (local demo limit).'})
        if not self.server.lock.acquire(blocking=False): return self.send_json(409,{'error':'A Studio job is already running. Check its result before retrying.'})
        try:
            pdf=self.rfile.read(n)
            if not pdf.startswith(b'%PDF-'): return self.send_json(400,{'error':'File does not have a valid PDF header.'})
            result=run_studio(pdf,self.server.config,self.server.key)
            self.send_json(200,{'result':result})
        except BridgeError as e: self.send_json(502,{'error':str(e)})
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception as e:
            print('Bridge error:',type(e).__name__,flush=True)
            try: self.send_json(500,{'error':'Unexpected backend error. Check local console.'})
            except OSError: pass
        finally: self.server.lock.release()

def main():
    config=load_config(); print('Target:',config['label'],config['workflow_id'],config['config_id'], '| Project:',config['project_id'])
    key=os.environ.get('UPSTAGE_API_KEY') or getpass.getpass('Upstage API key (hidden; Enter for preview mode): ').strip()
    port=8765; server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.key=key;server.config=config;server.lock=threading.Lock();server.allowed_hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
    url=f'http://127.0.0.1:{port}'; print('Open:',url,'| Ctrl+C to stop.');webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=='__main__':
    import sys
    if len(sys.argv)>=2 and sys.argv[1]=='--recover-job':
        try: recover_job(sys.argv[2] if len(sys.argv)==3 else input('Existing Job ID (job_...): ').strip())
        except BridgeError as e: print(str(e)); sys.exit(1)
    else: main()
