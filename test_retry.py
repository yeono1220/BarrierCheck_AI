"""Transport regression tests; no live API or credentials required."""
import io, json, ssl, unittest, urllib.error, http.client
from unittest.mock import patch, MagicMock
from functools import partial
from server import request_api, run_studio, load_config, BridgeError, RULE_CODES, RULE_NODE
from test_bridge import D,F,NODE,REPORT,step,job

class TestRetry(unittest.TestCase):
    def setUp(self):
        self.delays=[]; self.t=0; self.calls=[]
    def sleep(self,n): self.delays.append(n); self.t+=n
    def clock(self): return self.t
    def request(self,path,method='GET',timeout=40):
        return request_api('test-only',path,method,b'payload' if method=='POST' else None,timeout=timeout,project_id='proj_test',sleep=self.sleep,clock=self.clock)
    def http(self,status):
        return urllib.error.HTTPError('https://api.upstage.ai/v2/files',status,'synthetic failure',{},io.BytesIO(b'{}'))
    def responses(self,*replies):
        it=iter(replies)
        def urlopen(req,timeout):
            self.calls.append((req,timeout))
            reply=next(it)
            if isinstance(reply,Exception): raise reply
            r=MagicMock();r.__enter__.return_value.read.return_value=json.dumps(reply).encode();return r
        return patch('server.urllib.request.urlopen',side_effect=urlopen)
    def test_525_then_success(self):
        with self.responses(self.http(525),{'id':'file_test'}): self.assertEqual(self.request('/files','POST')['id'],'file_test')
        self.assertEqual(self.delays,[1]);self.assertEqual(len(self.calls),2)
        self.assertEqual(self.calls[0][0].data,self.calls[1][0].data)
    def test_upload_four_attempt_limit(self):
        with self.responses(*[self.http(525) for _ in range(4)]):
            with self.assertRaisesRegex(BridgeError,'4 attempts'): self.request('/files','POST')
        self.assertEqual(self.delays,[1,2,4]);self.assertEqual(len(self.calls),4)
    def test_mixed_gateway_failures(self):
        with self.responses(self.http(502),self.http(503),self.http(504),{'id':'file_test'}): self.assertEqual(self.request('/files','POST')['id'],'file_test')
        self.assertEqual(self.delays,[1,2,4])
    def test_no_retry_permanent_http(self):
        for status in (400,401,403,404,413,415,422,429):
            with self.subTest(status=status),self.responses(self.http(status)):
                with self.assertRaisesRegex(BridgeError,'HTTP '+str(status)): self.request('/files','POST')
        self.assertEqual(self.delays,[]);self.assertEqual(len(self.calls),8)
    def test_poll_retries_same_job(self):
        with self.responses(self.http(525),TimeoutError(),{'status':'completed'}): self.assertEqual(self.request('/responses/job_test?include=all')['status'],'completed')
        self.assertEqual(self.delays,[1,2]);self.assertTrue(all(r.full_url.endswith('/responses/job_test?include=all') and r.get_method()=='GET' for r,_ in self.calls))
    def test_get_timeout_budget(self):
        def consume(req,timeout):
            self.calls.append((req,timeout));self.t+=timeout;raise TimeoutError()
        with patch('server.urllib.request.urlopen',side_effect=consume):
            with self.assertRaises(BridgeError): self.request('/responses/job_test?include=all',timeout=10)
        self.assertLessEqual(self.t,10.0001);self.assertLessEqual(len(self.calls),3)
    def test_read_transport_disconnect(self):
        with self.responses(http.client.RemoteDisconnected(),{'status':'UPLOADED'}):self.assertEqual(self.request('/files/file_test?view=status')['status'],'UPLOADED')
        self.assertEqual(self.delays,[1])
    def test_tls_verification_not_retried(self):
        with self.responses(urllib.error.URLError(ssl.SSLCertVerificationError('bad cert'))):
            with self.assertRaises(BridgeError):self.request('/files','POST')
        self.assertEqual(self.delays,[]);self.assertEqual(len(self.calls),1)
    def test_create_never_retried(self):
        for error in (self.http(525),TimeoutError(),http.client.RemoteDisconnected()):
            with self.responses(error):
                with self.assertRaisesRegex(BridgeError,'No automatic resubmission'): self.request('/responses','POST')
        self.assertEqual(self.delays,[]);self.assertEqual(len(self.calls),3)
    def test_create_auth_error_no_retry(self):
        with self.responses(self.http(403)):
            with self.assertRaisesRegex(BridgeError,'HTTP 403'): self.request('/responses','POST')
        self.assertEqual(self.delays,[])
    def test_full_flow_with_upload_and_poll_retries(self):
        final=job(step(RULE_NODE,'\n'.join(c+'=SATISFIED' for c in RULE_CODES)),step(NODE,json.dumps(D)),step(REPORT,json.dumps(F)))
        cfg=load_config();request=partial(request_api,project_id=cfg['project_id'],sleep=self.sleep,clock=self.clock)
        with self.responses(self.http(525),{'id':'file_test'}, {'id':'job_test','status':'in_progress'},self.http(503),final):
            result=run_studio(b'%PDF-1.4 synthetic',cfg,'test-only',request=request,sleep=self.sleep,clock=self.clock)
        self.assertEqual(result['decision_output'],D);self.assertEqual(result['followup_output'],F);self.assertEqual(result['overall_decision'],'검토 필요')
        self.assertEqual([r.get_method() for r,_ in self.calls],['POST','POST','POST','GET','GET'])
        self.assertEqual(sum(r.full_url.endswith('/responses') and r.get_method()=='POST' for r,_ in self.calls),1)
    def test_poll_exhausted_preserves_job_id(self):
        cfg=load_config(); request=partial(request_api,project_id=cfg['project_id'],sleep=self.sleep,clock=self.clock)
        with self.responses({'id':'file_test'},{'id':'job_test','status':'in_progress'},self.http(525),self.http(525),self.http(525)):
            with self.assertRaisesRegex(BridgeError,'Existing job: job_test'):run_studio(b'%PDF-1.4 synthetic',cfg,'test-only',request=request,sleep=self.sleep,clock=self.clock)
        self.assertEqual(sum(r.full_url.endswith('/responses') for r,_ in self.calls),1)

if __name__=='__main__': unittest.main()
