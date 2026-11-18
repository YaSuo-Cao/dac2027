"""Budget-five native-only control and RTL-aware closed loop; frozen /840 inputs."""
from __future__ import annotations
import argparse, collections, re, subprocess, sys, xml.etree.ElementTree as ET
from common import *
import repair, pipelines, contract_flow, remote, ledger

NAME='rtl_closed_loop_b5'
OUT=ROOT/'analysis'/NAME
METHODS=['NativeOnly-B5','RTL-Aware-B5']
MAX_REPAIRS=4


def immutable(path,value):
    if path.exists():assert canonical(load(path))==canonical(value), 'Frozen content changed: '+str(path)
    else:save(path,value)


def initial_jobs():
    jobs=[j for j in load(ROOT/'configs/exp1_jobs.json') if j['arm']=='Gen']
    assert len(jobs)==840 and len({j['instance'] for j in jobs})==840
    return jobs


def feedback_phase(job):
    r=repair.evaluation(job)
    return 'construction' if not r['c0_pass'] else 'native' if not r['native_pass'] else 'rtl' if not r['rtl_pass'] else 'passed'


def sanitize(message,job):
    message=message.replace(job['key'],'<candidate-id>').replace(job['task'],'<public-task>')
    message=re.sub(r'/dataset/[^\s:]+', '<evaluation-harness>',message)
    message=re.sub(r'/work/runs/cases/[^\s,:]+/candidate.py','candidate.py',message)
    return message


def rtl_feedback(job):
    r=repair.evaluation(job)
    assert r['native_pass'] and not r['rtl_pass'] and not r['infrastructure_error']
    directory=result_dir(job)/'rtl';p=directory/'junit.xml'
    if not p.exists():raise RuntimeError('RTL diagnostic XML missing: '+job['key'])
    messages=[]
    for node in ET.parse(p).getroot().iter():
        if node.tag in ('failure','error'):
            message=node.get('message','').strip()
            if message and message not in messages:messages.append(message)
    if not messages:raise RuntimeError('RTL failure has no explicit diagnostic: '+job['key'])
    feedback={'phase':'rtl','native_passed':True,'rtl_passed':False,
        'diagnostics':[sanitize(s,job)[:12000] for s in messages[:3]],
        'truncated':len(messages)>3 or any(len(s)>12000 for s in messages[:3]),
        'provenance':'JUnit exception message attributes only; no traceback body or test/reference source',
        'junit_sha256':sha(p),'candidate_source_sha256':r['source_sha256'],
        'reference_source_accessed':False}
    compiler=any(re.search(r'ConversionError|VerilogImportError|PyMTL(?:Type|Syntax)Error|'
        r'RTLIR|syntax error|not supported|not convertible|cannot be converted',s,re.I) for s in messages)
    feedback['failure_kind']='lowering_or_compiler' if compiler else 'rtl_validation'
    return feedback


def history(state):
    return [{'repair_index':i+1,'phase':a['phase'],'arm':a['arm'],
        'c0_pass':a['c0_pass'],'native_pass':a['native_pass'],'rtl_pass':a['rtl_pass'],
        'candidate_sha256':a['candidate_sha256'],'accepted_by_blind_gate':a['accepted_by_blind_gate']}
        for i,a in enumerate(state['attempts'])]


def request_for(job,state):
    phase=feedback_phase(job)
    if phase in ('construction','native'):
        arm='FL' if phase=='construction' else repair.functional_routes(job)[0]
        request=repair.repair_request(job,arm,MODEL)
    elif phase=='rtl':
        arm='RTL-L'
        base=repair.generation_job(job['instance'],'Gen',MODEL)
        initial=load(ROOT/'configs/exp1_requests.json')[base['key']]
        source=(run_dir(job)/'candidate.py').read_text(encoding='utf-8')
        feedback=rtl_feedback(job)
        prompt=initial['messages'][1]['content']
        prompt+='\n\nRepair this exact Python HCL candidate. It passes official native simulation but fails Verilog lowering or RTL validation. Preserve its native behavior and exact public interface; fix the supplied RTL failure. Do not replace the Python HCL source with Verilog.\n<ORIGINAL>\n'+source+'\n</ORIGINAL>\n'
        prompt+='F_RTL: actual Verilog-lowering/RTL-validation diagnostic:\n'+json.dumps(feedback,ensure_ascii=False)
        prompt+='\nUse constructs accepted by the native HCL compiler and Verilog exporter. Native simulation success alone is insufficient.\nReturn one complete Python source file inside <CODE>...</CODE>. No explanation, tests or reference access.'
        request=payload([{'role':'system','content':'Repair one existing '+ADAPTER[job['language']]+' hardware design using the public interface and actual RTL-stage diagnostic. Preserve specified behavior and native compatibility. One repair attempt only.'},
                         {'role':'user','content':prompt}])
        immutable(OUT/'feedback'/(canonical({'job':job['key']})+'.json'),feedback)
    else:raise ValueError('No repair for a passing candidate')
    if state['attempts']:
        request['messages'][1]['content']+='\n\nClosed-loop repair history (earlier code attempts, not independent samples):\n'+json.dumps(history(state),ensure_ascii=False)
        request['messages'][1]['content']+='\nThe ORIGINAL above is the latest attempted source, including a rejected attempt when applicable. Address its current failure. Avoid repeating an earlier failed implementation.'
    assert 'BCD_GUARD' not in request['messages'][1]['content']
    return request,arm,phase


def initialize():
    if (OUT/'round_0_states.json').exists():return load(OUT/'round_0_states.json')
    states=[]
    for j in initial_jobs():
        for method in METHODS:
            states.append({'method':method,'instance':j['instance'],'task':j['task'],'language':j['language'],
                'initial':j,'accepted':j,'current':j,'attempts':[],'stop_reason':None,'contract_failures':[]})
    save(OUT/'round_0_states.json',states)
    return states


def stop(state):
    r=repair.evaluation(state['accepted'])
    if r['rtl_pass']:return 'rtl_passed'
    if state['method']=='NativeOnly-B5' and r['native_pass']:return 'native_passed'
    if len(state['attempts'])>=MAX_REPAIRS:return 'repair_budget_exhausted'
    return state.get('stop_reason')


def pending(states):
    return [s for s in states if not stop(s)]


def prepare(round_index):
    states=load(OUT/f'round_{round_index-1}_states.json')
    active=pending(states)
    tasks=[s['task'] for s in active if feedback_phase(s['current'])=='native' and 'C' in repair.functional_routes(s['current'])[0]]
    contract_flow.ensure(tasks,MODEL,allow_output_failures=True)
    jobs={};requests={};plans=[]
    for s in active:
        start=s['current'];phase=feedback_phase(start)
        arm='FL' if phase=='construction' else repair.functional_routes(start)[0] if phase=='native' else 'RTL-L'
        plan={'method':s['method'],'instance':s['instance'],'start_key':start['key'],'phase':phase,'arm':arm}
        if 'C' in arm and pipelines.contract_unavailable(s['task'],MODEL):
            plan['contract_failure']=True
        else:
            request,arm,phase=request_for(start,s);identity=canonical(request)
            key='repairs/'+MODEL+'/'+identity
            if identity in {a['request_sha256'] for a in s['attempts']}:
                plan['repeat_request']=True
            else:
                j=registered_job(key,s['task'],s['language'],arm,request,start_key=start['key'],
                    logical_stage=NAME+'_round_'+str(round_index),generation_arm='Gen')
                jobs[key]=j;requests[key]=request;plan['job_key']=key
        plans.append(plan)
    stage=NAME+'_r'+str(round_index)
    immutable(ROOT/'configs'/(stage+'_jobs.json'),list(jobs.values()))
    immutable(ROOT/'configs'/(stage+'_requests.json'),requests)
    immutable(OUT/f'round_{round_index}_plans.json',plans)
    print(json.dumps({'round':round_index,'active_paths':len(active),'physical_jobs':len(jobs),
        'cached_responses':sum((run_dir(j)/'response.json').exists() for j in jobs.values()),
        'rtl_feedback_jobs':sum(j['arm']=='RTL-L' for j in jobs.values())}),flush=True)
    return stage,list(jobs.values())


def finish(round_index,jobs):
    states=load(OUT/f'round_{round_index-1}_states.json')
    plans={(p['method'],p['instance']):p for p in load(OUT/f'round_{round_index}_plans.json')}
    lookup={j['key']:j for j in jobs}
    for s in states:
        p=plans.get((s['method'],s['instance']))
        if p:
            if p.get('contract_failure'):
                s['contract_failures'].append(s['task']);s['stop_reason']='contract_output_failure'
            elif p.get('repeat_request'):s['stop_reason']='identical_request_no_progress'
            else:
                j=lookup[p['job_key']];r=repair.evaluation(j);g=load(run_dir(j)/'generation.json')
                a={'round':round_index,'job':j,'start_key':p['start_key'],'phase':p['phase'],'arm':p['arm'],
                    'request_sha256':j['request_sha256'],'candidate_sha256':g.get('source_sha256'),
                    'c0_pass':r['c0_pass'],'native_pass':r['native_pass'],'rtl_pass':r['rtl_pass'],
                    'accepted_by_blind_gate':bool(r['c0_pass'])}
                s['attempts'].append(a);s['current']=j
                if r['c0_pass']:s['accepted']=j
        s['stop_reason']=stop(s)
    save(OUT/f'round_{round_index}_states.json',states)
    return states


def freeze():
    protocol={'name':NAME,'population':840,'tasks':168,'languages':LANGS,'model':MODEL,'parameters':PARAMS,
        'initial_arm':'Gen','initial_generation_calls':1,'maximum_code_repairs':4,'maximum_code_calls':5,
        'methods':METHODS,'success':'C0 and Q_native and C_RTL on the same selected source',
        'control_early_stop':'Q_native pass','rtl_aware_early_stop':'C_RTL pass',
        'selection':'Latest C0-passing candidate; C0-rejected trial is next feedback target while accepted predecessor is retained',
        'feedback':'construction/native: existing interface route; RTL: JUnit exception message attributes only plus public prompt and exact candidate',
        'rtl_branch':'RTL-L: actual lowering or validation diagnostic plus frozen L_l; no reference or test source',
        'history':'After the first repair, append compact outcomes and source hashes of all prior code attempts',
        'no_progress':'Repeated exact request stops; repeated source alone does not stop before the four-repair limit',
        'contracts':'Lazy, reuse once per task, two schema-only correction maximum; bill all attempts separately from code calls',
        'physical_cache':'Exact request SHA256 and model only; aliases within/across methods are not independent samples',
        'output_failure':'Consumes a repair slot; network/evaluation failures remain pending and do not consume another repair slot',
        'evaluation_fingerprint':load(ROOT/'configs/evaluation_fingerprint.json')['sha256'],
        'initial_jobs_sha256':sha(ROOT/'configs/exp1_jobs.json'),
        'initial_requests_sha256':sha(ROOT/'configs/exp1_requests.json'),
        'router_sha256':sha(ROOT/'router.py'),
        'implementation_sha256':sha(Path(__file__))}
    immutable(ROOT/'protocol'/(NAME+'.json'),protocol)
    return protocol


def main():
    freeze();initialize()
    for i in range(1,MAX_REPAIRS+1):
        done=OUT/f'round_{i}_states.json'
        if done.exists():continue
        save(ROOT/'progress'/(NAME+'.json'),{'status':'running','round':i,'population':840,'updated_utc':time.time()})
        stage,jobs=prepare(i)
        if jobs:
            subprocess.run([sys.executable,str(ROOT/'generate.py'),'--stage',stage,'--workers','2'],cwd=WORK,check=True)
            remote.execute(jobs)
        finish(i,jobs)
        subprocess.run([sys.executable,str(ROOT/'analyze_rtl_closed_loop.py'),'--round',str(i)],cwd=WORK,check=True)
    ledger.refresh()
    subprocess.run([sys.executable,str(ROOT/'analyze_rtl_closed_loop.py'),'--round','4','--final'],cwd=WORK,check=True)
    save(ROOT/'progress'/(NAME+'.json'),{'status':'complete','population':840,'repairs_max':4,'code_calls_max':5,'completed_utc':time.time()})


if __name__=='__main__':
    try:main()
    except Exception as exc:
        import traceback
        save(ROOT/'progress'/(NAME+'.json'),{'status':'blocked','error':str(exc),
            'traceback':traceback.format_exc(),'updated_utc':time.time()})
        raise
