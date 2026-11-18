"""Model-consistent Fast/Full and Direct+F; at most two selected repairs."""
from common import *
from repair import evaluation,choose,queue_repairs,functional_routes,generation_job

def contract_unavailable(task,model):
    p=ROOT/'runs/contracts'/model/task/'contract_resolution.json'
    return p.exists() and load(p).get('available') is False

def contract_failures(stage):
    p=ROOT/'configs'/(stage+'_contract_failures.json')
    return {r['start_key']:r for r in load(p)} if p.exists() else {}

def split_plans(stage,plans,model):
    ready=[];failed=[]
    for j,arm,logical in plans:
        if 'C' in arm and contract_unavailable(j['task'],model):
            failed.append({'start_key':j['key'],'task':j['task'],'instance':j['instance'],
                'arm':arm,'logical_stage':logical,'contract_key':'contracts/'+model+'/'+j['task'],
                'reason':'contract_output_failure_after_frozen_correction_budget'})
        else:ready.append((j,arm,logical))
    save(ROOT/'configs'/(stage+'_contract_failures.json'),failed)
    return queue_repairs(stage,ready,model)

def initial_jobs(model):
    stage='exp1' if model==MODEL else 'cross_'+model
    return load(ROOT/'configs'/(stage+'_jobs.json'))

def prepare_first(model=MODEL):
    jobs=initial_jobs(model);plans=[]
    for j in jobs:
        if j['arm'] not in ['Direct','Gen'] or evaluation(j)['native_pass']:continue
        arm='F' if j['arm']=='Direct' else 'FL' if not evaluation(j)['c0_pass'] else functional_routes(j)[0]
        plans.append((j,arm,'DirectF' if j['arm']=='Direct' else 'FullRound1'))
    return split_plans('pipeline1_'+model,plans,model)

def states_first(model=MODEL):
    repairs={j['start_key']:j for j in load(ROOT/'configs'/('pipeline1_'+model+'_jobs.json'))}
    states=[];failed=contract_failures('pipeline1_'+model)
    for j in initial_jobs(model):
        if j['arm'] not in ['Direct','Gen']:continue
        trial=repairs.get(j['key']);selected=choose(j,trial) if trial else j
        states.append({'instance':j['instance'],'task':j['task'],'language':j['language'],
                       'kind':'DirectF' if j['arm']=='Direct' else 'ParaRoute',
                       'initial':j,'first':trial,'selected':selected,
                       'first_contract_failure':failed.get(j['key'])})
    return states

def prepare_second(model=MODEL):
    states=states_first(model);plans=[]
    for s in states:
        if s['kind']!='ParaRoute' or evaluation(s['selected'])['native_pass'] or s.get('first_contract_failure'):continue
        # A rejected first repair provides a new compiler failure. Repair that
        # exact rejected source in round two, while retaining the accepted
        # fast candidate as the final fallback. Repeating its original prompt
        # would add no new evidence and would only hit the same response cache.
        j=second_start(s);arm='FL' if not evaluation(j)['c0_pass'] else functional_routes(j)[0]
        plans.append((j,arm,'FullRound2'))
    save(ROOT/'configs'/('pipeline_first_states_'+model+'.json'),states)
    return split_plans('pipeline2_'+model,plans,model)

def second_start(state):
    first=state.get('first')
    return first if first and not evaluation(first)['c0_pass'] else state['selected']

def final_states(model=MODEL):
    first=states_first(model);second={j['start_key']:j for j in load(ROOT/'configs'/('pipeline2_'+model+'_jobs.json'))}
    failed=contract_failures('pipeline2_'+model)
    for s in first:
        trial=second.get(second_start(s)['key']) if s['kind']=='ParaRoute' else None
        s['second_contract_failure']=failed.get(second_start(s)['key']) if s['kind']=='ParaRoute' else None
        s['fast_selected']=s['selected'];s['second']=trial
        if trial:s['selected']=choose(s['selected'],trial)
    save(ROOT/'analysis'/('pipeline_states_'+model+'.json'),first);return first

def contract_tasks_for_first(model=MODEL):
    tasks=[]
    for j in initial_jobs(model):
        if j['arm']=='Gen' and evaluation(j)['c0_pass'] and not evaluation(j)['native_pass'] and 'C' in functional_routes(j)[0]:tasks.append(j['task'])
    return tasks

def contract_tasks_for_second(model=MODEL):
    return [s['task'] for s in states_first(model) if s['kind']=='ParaRoute' and not s.get('first_contract_failure') and not evaluation(s['selected'])['native_pass'] and evaluation(second_start(s))['c0_pass'] and 'C' in functional_routes(second_start(s))[0]]
