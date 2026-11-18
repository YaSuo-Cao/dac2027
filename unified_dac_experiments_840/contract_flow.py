"""Schema-only contract recovery, with every billed response retained."""
from common import *
import repair,subprocess,sys

def generate(stage):
    subprocess.run([sys.executable,str(ROOT/'generate.py'),'--stage',stage,'--workers','2'],check=True,cwd=WORK)

def ensure(tasks,model=MODEL,allow_output_failures=False):
    stage=repair.build_contracts(tasks,model);original=load(ROOT/'configs'/(stage+'_jobs.json'))
    if not original:return
    generate(stage)
    original_requests=load(ROOT/'configs'/(stage+'_requests.json'))
    attempts={j['key']:[j] for j in original};unresolved=original
    retry_stage='contract_retries_'+model
    rp=ROOT/'configs'/(retry_stage+'_requests.json');jp=ROOT/'configs'/(retry_stage+'_jobs.json')
    retry_requests=load(rp) if rp.exists() else {};retry_jobs=load(jp) if jp.exists() else []
    for round_index in range(3):
        pending=[]
        for j in unresolved:
            current=attempts[j['key']][-1];g=load(run_dir(current)/'generation.json')
            if g['status']=='contract_ready':
                save(run_dir(j)/'contract.json',load(run_dir(current)/'contract.json'))
                save(run_dir(j)/'contract_resolution.json',{'attempt_keys':[a['key'] for a in attempts[j['key']]],
                    'selected_key':current['key'],'contract_sha256':sha(run_dir(current)/'contract.json'),
                    'policy':'first schema-valid contract; no functional/reference feedback'})
            else:pending.append(j)
        if not pending:return
        if round_index==2:
            if not allow_output_failures:
                raise RuntimeError('Contract schema still invalid after two format corrections: '+','.join(j['task'] for j in pending))
            for j in pending:
                save(run_dir(j)/'contract_resolution.json',{
                    'attempt_keys':[a['key'] for a in attempts[j['key']]],
                    'selected_key':None,'contract_sha256':None,'available':False,
                    'status':'output_failure','correction_budget_exhausted':True,
                    'policy':'No fabricated contract or increased output cap; retain accepted predecessor and charge every attempt.'})
            return [j['task'] for j in pending]
        for j in pending:
            current=attempts[j['key']][-1];raw=(run_dir(current)/'raw_output.txt').read_text(encoding='utf-8')
            req0=original_requests[j['key']]
            correction='Return the complete required JSON object only. The previous response failed JSON/schema validation: '+str(load(run_dir(current)/'generation.json').get('error'))+'. Do not add Markdown, an explanation, or implementation code.'
            req={**req0,'messages':req0['messages']+[{'role':'assistant','content':raw},{'role':'user','content':correction}]}
            key=j['key']+'/format_retry_'+str(round_index+1)
            attempt={**j,'key':key,'request_sha256':canonical(req),'prompt_sha256':canonical(req['messages']),
                     'contract_base_key':j['key'],'format_retry':round_index+1}
            if key in retry_requests:assert canonical(retry_requests[key])==canonical(req),'Immutable contract correction changed'
            else:retry_requests[key]=req;retry_jobs.append(attempt)
            attempts[j['key']].append(attempt)
        save(rp,retry_requests);save(jp,retry_jobs);generate(retry_stage);unresolved=pending

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--model',default=MODEL);p.add_argument('tasks',nargs='+');a=p.parse_args()
    ensure(a.tasks,a.model)
