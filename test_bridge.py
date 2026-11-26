import unittest,json
from server import *
NODE='07_최종판정_JSON'
# Synthetic transport fixture only, not an actual Studio execution.
SAMPLE=dict(workflow_version='조은 v5.1.1',psv_tag='PSV-TEST',decision='FAIL',a_decision='PASS',b_decision='FAIL',a_issues=[],b_issues=['Q7'],test_attribution='CONFIRMED',missing_documents=[],rule_status={**{f'R{i}':'SATISFIED' for i in range(1,8)},**{f'Q{i}':'SATISFIED' for i in range(1,9)},'Q7':'VIOLATED'},data_status='OK',data_issues=[],independent_validation='UNCONFIRMED',facts=[],follow_up=[],reason='Synthetic test fixture')
def step(name,text): return {'model':name,'content':[{'type':'output_text','text':text}]}
def job(*steps): return {'status':'completed','output':list(steps)}
class TestBridge(unittest.TestCase):
 def test_direct(self): self.assertEqual(result_from_job(job(step(NODE,json.dumps(SAMPLE)),step('08','summary')),NODE),SAMPLE)
 def test_wrapper(self): self.assertEqual(result_from_job(job(step(NODE,json.dumps({'decision':'FAIL','content':json.dumps(SAMPLE)}))),NODE),SAMPLE)
 def test_generated_name(self): self.assertEqual(result_from_job(job(step('step_12_instruct',json.dumps(SAMPLE)),step('step_13_instruct','report')),NODE),SAMPLE)
 def test_broken(self):
  with self.assertRaises(BridgeError): result_from_job(job(step(NODE,'{"psv_tag":"x"【†1】}')),NODE)
 def test_wrong_node_no_fallback(self):
  with self.assertRaises(BridgeError): result_from_job(job(step(NODE,'bad'),step('08',json.dumps(SAMPLE))),NODE)
 def test_ambiguity(self):
  with self.assertRaises(BridgeError): result_from_job(job(step('a',json.dumps(SAMPLE)),step('b',json.dumps(SAMPLE))),NODE)
 def test_duplicate(self):
  with self.assertRaises(ValueError): strict_json('{"a":1,"a":2}')
 def test_incomplete(self):
  with self.assertRaises(BridgeError): result_from_job({'status':'in_progress'},NODE)
 def test_full_flow(self):
  calls=[]; responses=iter([{'id':'file_test'},{'id':'job_test','status':'in_progress'},{'status':'in_progress'},job(step(NODE,json.dumps(SAMPLE)),step('08','report'))])
  def req(key,path,method='GET',payload=None,ctype=None,timeout=40): calls.append((path,method,payload)); return next(responses)
  cfg=load_config();cfg['output_contract']='full16'; out=run_studio(b'%PDF-1.4 test',cfg,'test-only',request=req,sleep=lambda _:None)
  self.assertEqual(out,SAMPLE);self.assertEqual(calls[0][0],'/files');self.assertEqual(json.loads(calls[1][2])['config_id'],cfg['config_id']);self.assertIn('include=all',calls[-1][0])
D={'document_consistency':'PASS','approval_compliance':'검토 필요','reason':'Synthetic fixture; Q5 evidence missing.'}
F={'overall_decision':'검토 필요','followup_type':'보완 요청서','recipient':'정비 패키지 제출자','psv_tag':'PSV-TEST','action_items':['Q5: Missing evidence → submit certificate'], 'document':'Synthetic draft; not approval.'}
REPORT='08_요약보고서'
class TestCompact(unittest.TestCase):
 def test_pair(self):
  x=result_from_job(job(step(NODE,json.dumps(D)),step(REPORT,json.dumps(F))),NODE,'compact',REPORT); self.assertEqual(x['decision_output'],D);self.assertEqual(x['followup_output'],F);self.assertIsNone(x['followup_error'])
 def test_generated_names(self):
  x=result_from_job(job(step('step_12_instruct',json.dumps({'content':json.dumps(D)})),step('step_13_instruct',json.dumps(F))),NODE,'compact',REPORT);self.assertEqual(x['followup_output'],F)
 def test_missing_report(self):
  x=result_from_job(job(step(NODE,json.dumps(D))),NODE,'compact',REPORT);self.assertEqual(x['decision_output'],D);self.assertIsNone(x['followup_output']);self.assertTrue(x['followup_error'])
 def test_conflict(self):
  x=result_from_job(job(step(NODE,json.dumps(D)),step(REPORT,json.dumps(dict(F,overall_decision='PASS')))),NODE,'compact',REPORT);self.assertIsNone(x['followup_output']);self.assertTrue(x['followup_error'])
 def test_broken_07(self):
  with self.assertRaises(BridgeError): result_from_job(job(step(NODE,'broken'),step(REPORT,json.dumps(F))),NODE,'compact',REPORT)
 def test_bad_enum(self):
  with self.assertRaises(BridgeError):result_from_job(job(step(NODE,json.dumps(dict(D,approval_compliance='REVIEW')))),NODE,'compact',REPORT)
 def test_full_flow(self):
  calls=[]; responses=iter([{'id':'file_test'},{'id':'job_test','status':'in_progress'},job(step(NODE,json.dumps(D)),step(REPORT,json.dumps(F))),job(step(NODE,json.dumps(D)),step(REPORT,json.dumps(F)))])
  def req(key,path,method='GET',payload=None,ctype=None,timeout=40):calls.append((path,method,payload));return next(responses)
  cfg=load_config();out=run_studio(b'%PDF-1.4 test',cfg,'fake-key',request=req,sleep=lambda _:None);self.assertEqual(out['decision_output'],D);self.assertEqual(out['followup_output'],F);self.assertEqual(json.loads(calls[1][2])['model'],cfg['workflow_id']);self.assertEqual(json.loads(calls[1][2])['config_id'],cfg['config_id'])
class TestProject(unittest.TestCase):
 def test_config(self):
  c=load_config();self.assertEqual(c['config_id'],'4');self.assertEqual(c['project_id'],'proj_YqEvTJxpcNamP9CrEXEFcU')
 def test_headers_all_requests(self):
  from unittest.mock import patch,MagicMock
  cfg=load_config(); replies=iter([{'id':'file_test'},{'id':'job_test','status':'in_progress'},job(step(NODE,json.dumps(D)),step(REPORT,json.dumps(F))),job(step(NODE,json.dumps(D)),step(REPORT,json.dumps(F)))])
  calls=[]
  def urlopen(req,timeout):
   calls.append(req); r=MagicMock();r.__enter__.return_value.read.return_value=json.dumps(next(replies)).encode();return r
  with patch('server.urllib.request.urlopen',side_effect=urlopen):
   result=run_studio(b'%PDF-1.4 test',cfg,'fake-key',sleep=lambda _:None)
  self.assertEqual(result['decision_output'],D);self.assertEqual(len(calls),4)
  for req in calls:
   headers={k.lower():v for k,v in req.header_items()};self.assertEqual(headers['x-project-id'],cfg['project_id']);self.assertEqual(headers['authorization'],'Bearer fake-key')
  self.assertEqual(json.loads(calls[1].data)['config_id'],'4');self.assertIn('include=all',calls[-2].full_url);self.assertIn('include%5B%5D=all',calls[-1].full_url)
class TestRuleSnapshot(unittest.TestCase):
 def test_named_rules(self):
  text='\n'.join([f'{c}=SATISFIED' for c in RULE_CODES]+['Q7_EVIDENCE=calibration date'])
  x=result_from_job(job(step('05_규칙평가_증빙대조',text),step(NODE,json.dumps(D)),step(REPORT,json.dumps(F))),NODE,'compact',REPORT)
  self.assertEqual(len(x['rule_snapshot']['status']),15);self.assertEqual(x['rule_snapshot']['evidence']['Q7'],'calibration date')
 def test_no_rules(self):
  self.assertIsNone(result_from_job(job(step(NODE,json.dumps(D))),NODE,'compact',REPORT)['rule_snapshot'])
 def test_duplicate_rule_not_guessed(self):
  x=rule_snapshot(job(step('05_규칙평가_증빙대조','R1=SATISFIED\nR1=VIOLATED\nR2=UNVERIFIED')))
  self.assertEqual(x['status'],{'R2':'UNVERIFIED'})
class TestWrappedRules(unittest.TestCase):
 def text(self): return '\n'.join(['WORKFLOW_VERSION=조은 v5.2','A_DECISION=PASS','B_DECISION=FAIL']+[f'{c}='+('VIOLATED' if c=='Q7' else 'SATISFIED') for c in RULE_CODES]+['Q7_EVIDENCE=actual evidence from fixture'])
 def test_json_envelope(self):
  x=rule_snapshot(job(step('05_규칙평가_증빙대조',json.dumps({'content':self.text()}))))
  self.assertEqual(len(x['status']),15);self.assertEqual(x['status']['Q7'],'VIOLATED')
 def test_double_wrapper_generated_name(self):
  x=rule_snapshot(job(step('step_10_instruct',json.dumps({'content':{'text':json.dumps(self.text())}}))))
  self.assertEqual(len(x['status']),15);self.assertEqual(x['evidence']['Q7'],'actual evidence from fixture')
 def test_conflicting_candidates(self):
  x=rule_snapshot(job(step('05_규칙평가_증빙대조',self.text()),step('05_규칙평가_증빙대조',self.text().replace('Q7=VIOLATED','Q7=SATISFIED'))));self.assertEqual(len(x['status']),14);self.assertNotIn('Q7',x['status'])
 def test_alternative_retrieval(self):
  j=job(step(NODE,json.dumps(D)),step(REPORT,json.dumps(F)))
  alt=job(step('step_10_instruct',json.dumps({'content':self.text()})),*j['output'])
  calls=[]
  def req(key,path): calls.append(path);return alt
  x=completed_result(j,'job_test',load_config(),'fake',req)
  self.assertEqual(x['rule_snapshot']['status']['Q7'],'VIOLATED');self.assertEqual(x['decision_output'],D);self.assertEqual(len(calls),1);self.assertIn('include%5B%5D=all',calls[0])
 def test_alternative_error_keeps_result(self):
  def req(key,path): raise BridgeError('unsupported query')
  x=completed_result(job(step(NODE,json.dumps(D)),step(REPORT,json.dumps(F))),'job_test',load_config(),'fake',req)
  self.assertEqual(x['decision_output'],D);self.assertIsNone(x['rule_snapshot'])
class TestCitationRegression(unittest.TestCase):
 def test_cited_all(self):
  text='WORKFLOW_VERSION=조은 v5.2【†1】\nA_DECISION=PASS【†2】\nB_DECISION=FAIL【†3】\n'+'\n'.join(f'{c}='+('VIOLATED' if c=='Q7' else 'NOT_APPLICABLE' if c=='Q8' else 'SATISFIED')+'【†57】【†58】' for c in RULE_CODES)
  x=rule_snapshot(job(step('step_10_instruct',json.dumps({'content':text}))));self.assertEqual(len(x['status']),15);self.assertEqual(x['status']['Q7'],'VIOLATED');self.assertEqual(x['status']['Q8'],'NOT_APPLICABLE')
 def test_partial_generated(self):
  text='WORKFLOW_VERSION=v5.2\nA_DECISION=REVIEW\nB_DECISION=PASS\nR1=UNVERIFIED【†1】\nR2=unknown\nQ2_EVIDENCE=Q2=SATISFIED'
  x=rule_snapshot(job(step('step_9_instruct',text)));self.assertEqual(x['status'],{'R1':'UNVERIFIED'})
 def test_preserve_evidence(self):
  x=rule_snapshot(job(step(RULE_NODE,'R1=SATISFIED【†1】\nR1_EVIDENCE=source evidence【†2】')));self.assertEqual(x['evidence']['R1'],'source evidence【†2】')
 def test_duplicate_same(self):
  x=rule_snapshot(job(step(RULE_NODE,'R1=SATISFIED【†1】\nR1=SATISFIED【†2】')));self.assertEqual(x['status'],{'R1':'SATISFIED'})
 def test_nonrule_not_inferred(self):
  self.assertIsNone(rule_snapshot(job(step('step_2_extract','R1=SATISFIED\nQ1=VIOLATED'))))
 def test_batch_independence(self):
  for i in range(1,11):
   val=RULE_STATES[i%4];text='WORKFLOW_VERSION=v5.2\nA_DECISION=PASS\nB_DECISION=PASS\n'+'\n'.join(f'{c}={val}【†{i}】' for c in RULE_CODES)
   x=result_from_job(job(step('step_'+str(i)+'_instruct',text),step(NODE,json.dumps(D))),NODE,'compact',REPORT);self.assertEqual(x['rule_snapshot']['status'],dict.fromkeys(RULE_CODES,val))
if __name__=='__main__': unittest.main()
