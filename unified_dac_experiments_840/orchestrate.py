"""Resume-safe ordered execution; no stage report until its full ledger exists."""
from __future__ import annotations
import argparse, subprocess, sys, time
from common import *
import repair, pipelines, remote, ledger, contract_flow

def command(script,*args):
    p=subprocess.run([sys.executable,str(ROOT/script),*map(str,args)],cwd=WORK)
    if p.returncode:raise RuntimeError(script+' failed; fix the saved blocker and resume without overwriting responses')

def progress(module,phase):
    save(ROOT/'progress/orchestrator.json',{'status':'running','pid':os.getpid(),'module':module,'phase':phase,'updated_utc':time.time(),'population':840})

def generated(stage):command('cache_audit.py','--stage',stage);command('generate.py','--stage',stage,'--workers',2)
def evaluated(stage):remote.execute(load(ROOT/'configs'/(stage+'_jobs.json')));ledger.refresh()
def contracts(tasks,model=MODEL,allow_output_failures=False):
    contract_flow.ensure(tasks,model,allow_output_failures=allow_output_failures)

def pipeline(model=MODEL):
    contracts(pipelines.contract_tasks_for_first(model),model,allow_output_failures=True)
    pipelines.prepare_first(model);generated('pipeline1_'+model);evaluated('pipeline1_'+model)
    contracts(pipelines.contract_tasks_for_second(model),model,allow_output_failures=True)
    pipelines.prepare_second(model);generated('pipeline2_'+model);evaluated('pipeline2_'+model)
    pipelines.final_states(model)

def cross(model):
    base=[j for j in load(ROOT/'configs/exp1_jobs.json') if j['arm'] in ['Direct','Gen']]
    req0=load(ROOT/'configs/exp1_requests.json');jobs=[];requests={}
    for j in base:
        request={**req0[j['key']],'model':model};key='cross/'+model+'/'+j['task']+'/'+j['language']+'/'+j['arm']
        jobs.append(registered_job(key,j['task'],j['language'],j['arm'],request,experiment=4));requests[key]=request
    save(ROOT/'configs'/('cross_'+model+'_jobs.json'),jobs);save(ROOT/'configs'/('cross_'+model+'_requests.json'),requests)
    generated('cross_'+model);evaluated('cross_'+model);pipeline(model)

def main():
    p=argparse.ArgumentParser();p.add_argument('--from-module',type=int,default=1);a=p.parse_args()
    save(ROOT/'progress/orchestrator.json',{'status':'running','pid':os.getpid(),'started_utc':time.time(),'from_module':a.from_module})
    try:
        if a.from_module<=1:
            progress(1,'generation_and_official_evaluation')
            if not (ROOT/'corpus/freeze.json').exists():command('corpus.py')
            command('validate.py')
            generated('exp1');evaluated('exp1');command('analyze.py',1)
        if a.from_module<=2:
            progress(2,'shared_FL_and_functional_factorial')
            repair.precondition();generated('exp2_fl');evaluated('exp2_fl')
            pool=[s for s in repair.starts() if repair.evaluation(s['start'])['c0_pass'] and not repair.evaluation(s['start'])['native_pass']]
            contracts([s['start']['task'] for s in pool]);repair.factorial();generated('exp2_factorial');evaluated('exp2_factorial');command('analyze.py',2)
        if a.from_module<=3:
            progress(3,'routed_pipeline_and_same_distribution_sampling')
            pipeline();command('sampling.py');generated('exp3');evaluated('exp3');command('analyze.py',3)
        if a.from_module<=4:
            progress(4,'full_population_cross_family_generalization')
            models=[MODEL]
            for model in ['qwen3.8-flash','glm-5.3-flash','claude-haiku-5-5']:
                cross(model);models.append(model);command('analyze.py',4,'--models',*models)
            save(ROOT/'analysis/model_availability.json',{'claude-haiku-5-5':{
                'http_status':200,'protocol':'anthropic_messages',
                'included_in_denominator':True}})
        ledger.refresh();save(ROOT/'progress/orchestrator.json',{'status':'complete','completed_utc':time.time(),'population':840})
    except Exception as exc:
        import traceback
        save(ROOT/'progress/orchestrator.json',{'status':'blocked','error':str(exc),'traceback':traceback.format_exc(),'time_utc':time.time()});raise
if __name__=='__main__':main()
