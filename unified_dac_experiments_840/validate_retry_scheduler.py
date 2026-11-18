"""Mock transport regression: no network, credentials, or scoring candidates."""
import collections,json,shutil,tempfile,threading
from pathlib import Path
import generate as g
from common import ROOT,canonical,load,save,sha

def main():
    events=[];attempts=collections.Counter();transport=g.api_run.transport;directory=g.run_dir;perform=g.perform
    with tempfile.TemporaryDirectory(prefix='pararoute_retry_') as tmp:
        g.run_dir=lambda j:Path(tmp)/j['key']
        requests={k:{'model':g.MODEL,'messages':[{'role':'user','content':k}]} for k in ['throttle','server','valid','truncated']}
        jobs=[{'key':k,'model':g.MODEL,'arm':'mock'} for k in requests]
        def fake(request,key,session):
            name=request['messages'][0]['content'];events.append(name);attempts[name]+=1
            if attempts[name]==1 and name in ['throttle','server']:
                return {'status':429 if name=='throttle' else 500,'body':'mock transient'}
            return {'status':200,'body':json.dumps({'model':g.MODEL,'choices':[{'message':{'content':'<CODE>\nclass TopModule: pass\n</CODE>'},
                'finish_reason':'length' if name=='truncated' else 'stop'}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})}
        def fast(*args,**kwargs):
            try:return perform(*args,**kwargs)
            except g.RetryDeferred as exc:exc.delay=0;raise
        g.api_run.transport=fake;g.perform=fast;complete=[]
        errors=g.scheduled(jobs,requests,'mock-key',1,lambda j,s,e:complete.append((j['key'],s,e)),g.RequestPacer(0))
        assert not errors and len(complete)==4
        assert dict((k,s) for k,s,_ in complete)=={'throttle':'ready','server':'ready','valid':'ready','truncated':'output_failure'}
        assert events[:4]==list(requests),events
        assert attempts=={'throttle':2,'server':2,'valid':1,'truncated':1}
        for j in jobs:
            path=g.run_dir(j);record=load(path/'generation.json')
            assert record['request_sha256']==canonical(requests[j['key']])
            logs=[load(p) for p in (path/'attempts').glob('*.json')]
            assert len(logs)==attempts[j['key']]
            if j['key']=='server':assert sum(x.get('billing_unknown',False) for x in logs)==1
        old=dict(attempts);g.scheduled(jobs,requests,'mock-key',2,lambda *args:None,g.RequestPacer(0));assert dict(attempts)==old
        failures=[]
        denied=[{'key':k,'model':g.MODEL,'arm':'mock'} for k in ['denied','never_started']]
        denied_requests={j['key']:{'model':g.MODEL,'messages':[]} for j in denied}
        g.api_run.transport=lambda *args:{'status':401,'body':'mock denied'}
        errors=g.scheduled(denied,denied_requests,'mock-key',1,lambda j,s,e:failures.append((j['key'],s)),g.RequestPacer(0))
        assert len(errors)==2 and len(failures)==2 and all(s=='infrastructure_error' for _,s in failures)
        j={'key':'malformed_receipt','model':g.MODEL,'arm':'mock'}
        g.api_run.transport=lambda *args:{'status':200,'body':'mock malformed response'}
        errors=g.scheduled([j],{j['key']:{'model':g.MODEL,'messages':[]}},'mock-key',1,lambda *args:None,g.RequestPacer(0))
        logs=[load(p) for p in (g.run_dir(j)/'attempts').glob('*.json')]
        assert len(errors)==1 and len(logs)==1 and logs[0]['billing_unknown'] and list((g.run_dir(j)/'rejected_responses').glob('*.txt'))
    g.api_run.transport=transport;g.run_dir=directory;g.perform=perform
    result={'all_passed':True,'mock_transport_only':True,'network_calls':0,'validated':['deferred 429 fairness','500 billing unknown retained',
        'each request keeps canonical hash','format failure remains a scored output failure','cached responses never resent','401 stops pending requests without fabricating scores',
        'malformed 200 receipt retained with unknown billing'],
        'request_start_spacing_seconds':1,'production_workers':2,'tool_sha256':sha(ROOT/'generate.py')}
    save(ROOT/'analysis/retry_scheduler_validation.json',result);print(json.dumps(result))

if __name__=='__main__':main()
