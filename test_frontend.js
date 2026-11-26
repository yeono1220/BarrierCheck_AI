// Unit-test actual frontend parsing, overall display and export data without a browser or API.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('app.js','utf8');const start=code.slice(0,code.indexOf('const sampleDefinitions='));
const ctx=vm.createContext({window:{}});vm.runInContext(start+'\nwindow.viewData=viewData;',ctx);
const parse=ctx.window.BarrierCheckContract.parse,view=ctx.window.viewData;
const vals=['PASS','FAIL','검토 필요'];let checks=0;
for(const a of vals)for(const b of vals){const d={document_consistency:a,approval_compliance:b,reason:'대상: PSV-001. 문서 정합성 테스트.'};const r=parse(d);const expected=[a,b].includes('FAIL')?'FAIL':[a,b].includes('검토 필요')?'REVIEW':'PASS';assert.equal(view(r).decision,expected);assert.equal(view(r).psv_tag,'PSV-001');assert.equal(r.followup_output,null);assert.equal(r.overall_source,'07_fixed_aggregation');checks++;}
const d={document_consistency:'PASS',approval_compliance:'검토 필요',reason:'대상: PSV-001. 문서 정합성 PASS: 기준 충족.'};const f={overall_decision:'검토 필요',followup_type:'보완 요청서',recipient:'정비 패키지 제출자',psv_tag:'PSV-001',action_items:['Q5: 확인'],document:'원문 보고서'};
let r=parse({decision_output:d,followup_output:f});assert.equal(r.followup_output.document,f.document);assert.equal(view(r).decision,'REVIEW');assert.equal(r.overall_source,'08_validated');checks++;
for(const bad of [{...f,overall_decision:'PASS'},{...f,recipient:'wrong'}, {...f,action_items:'bad'}, {...f,extra:1}]){r=parse({decision_output:d,followup_output:bad});assert.equal(r.followup_output,null);assert.equal(view(r).decision,'REVIEW');assert.ok(r.followup_error);checks++;}
assert.throws(()=>parse({...d,approval_compliance:'UNKNOWN'}));checks++;
console.log(`${checks} frontend cases passed`);
