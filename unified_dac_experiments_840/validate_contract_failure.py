"""Offline regression: contract output failure is not a whole-stage outage."""
import json, tempfile
from pathlib import Path
import contract_flow as flow
import pipelines as pipeline
import analyze
from common import save,load,canonical

def main():
    with tempfile.TemporaryDirectory(prefix='pararoute_contract_failure_') as tmp:
        root=Path(tmp);task='public_fixture';model='fixture-model'
        key='contracts/'+model+'/'+task;stage='contracts_'+model
        request={'model':model,'max_tokens':4096,'messages':[{'role':'user','content':'public fixture'}]}
        job={'key':key,'task':task,'model':model,'kind':'contract','arm':'C','language':'shared'}
        save(root/'configs'/(stage+'_jobs.json'),[job])
        save(root/'configs'/(stage+'_requests.json'),{key:request})
        flow.ROOT=root;flow.run_dir=lambda j:root/'runs'/j['key']
        flow.repair.build_contracts=lambda tasks,model:stage
        calls=[]
        def fake_generate(name):
            jobs=load(root/'configs'/(name+'_jobs.json'));requests=load(root/'configs'/(name+'_requests.json'))
            for j in jobs:
                d=flow.run_dir(j)
                if (d/'response.json').exists():continue
                assert requests[j['key']]['max_tokens']==4096
                calls.append(j['key']);d.mkdir(parents=True,exist_ok=True)
                (d/'raw_output.txt').write_text('{"incomplete":',encoding='utf-8')
                save(d/'generation.json',{'status':'output_failure','error':'contract_truncated'})
                save(d/'response.json',{'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}})
        flow.generate=fake_generate
        failures=flow.ensure([task],model,allow_output_failures=True)
        resolution=load(flow.run_dir(job)/'contract_resolution.json')
        assert failures==[task] and len(calls)==3 and resolution['available'] is False
        assert len(resolution['attempt_keys'])==3 and not (flow.run_dir(job)/'contract.json').exists()
        flow.ensure([task],model,allow_output_failures=True)
        assert len(calls)==3,'Resume must not create extra model attempts'
        pipeline.ROOT=root;queued=[]
        pipeline.queue_repairs=lambda stage,plans,model:queued.extend(plans)
        start={'key':'fixture/design','task':task,'instance':task+'/pyrtl'}
        pipeline.split_plans('fixture',[(start,'FC','FullRound1')],model)
        assert not queued and pipeline.contract_failures('fixture')[start['key']]['contract_key']==key
        analyze.ROOT=root;analyze.run_dir=lambda j:root/'runs'/j['key']
        cost=analyze.costs([],model,contract_attempt_tasks=[task])
        assert cost['calls']==0 and cost['contract_calls']==3 and cost['contract_tokens']==90
        assert cost['lazy_tokens']==90 and cost['amortized_tokens']==18
        def unavailable(stage):raise RuntimeError('mock HTTP outage')
        flow.generate=unavailable
        try:flow.ensure([task],model,allow_output_failures=True)
        except RuntimeError as exc:assert 'HTTP outage' in str(exc)
        else:raise AssertionError('Infrastructure outage must remain an unscored blocker')
    print(json.dumps({'passed':True,'network_calls':0,'checks':['output cap unchanged',
        'two format corrections only','no fabricated contract or candidate','resume reuses receipts',
        'failed support costs charged','unrelated branches continue','network outage stays a blocker']}))

if __name__=='__main__':main()
