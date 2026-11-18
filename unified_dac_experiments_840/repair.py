"""Same-source repair factorial and two-round interface-routed pipelines."""
from __future__ import annotations
import ast, importlib.util
from common import *
from router import route

def generation_job(instance,arm='Gen',model=MODEL):
    stage='exp1' if model==MODEL else 'cross_'+model
    jobs=load(ROOT/'configs'/(stage+'_jobs.json'))
    return next(j for j in jobs if j['instance']==instance and j['arm']==arm)

def evaluation(j):
    path=result_dir(j)/'result.json'
    if not path.exists():raise RuntimeError('Official evaluation missing: '+j['key'])
    r=load(path)
    if r.get('infrastructure_error'):raise RuntimeError('Unresolved infrastructure: '+j['key'])
    gen=load(run_dir(j)/'generation.json')
    if gen.get('status')=='ready' and r.get('source_sha256')!=gen.get('source_sha256'):
        raise RuntimeError('Evaluation/source identity mismatch: '+j['key'])
    if r.get('evaluation_fingerprint')!=load(ROOT/'configs/evaluation_fingerprint.json')['sha256']:
        raise RuntimeError('Evaluation/runtime identity mismatch: '+j['key'])
    return r

def official_artifacts(j):return ROOT/'evaluation/native/cases'/j['key']

def contract_request(task,model=MODEL):
    specification=(ROOT/'protocol/specifications'/(task+'.txt')).read_text(encoding='utf-8')
    population=next(p for p in load(ROOT/'configs/population.json') if p['task']==task)
    ports=load(ROOT/'configs/public_configurations.json')[task][0]['ports']
    schema={'interface_parameters':{'ports':[],'parameters':[]},'state_storage_roles':[],
            'datapath_guard_rules':[],'state_transition_invariants':[],'ambiguities':[]}
    content=('Extract a language-independent behavioral intermediate representation from only the public specification and interface below. '
        'Use exact port names and parameter expressions. Represent transforms, guards, priorities, state hold/reset behavior and per-output latency. '
        'Do not invent unstated behavior. For combinational interfaces keep state/transition lists empty. '
        'Return only JSON with these required keys:\n'+json.dumps(schema)+'\nPublic interface:\n'+json.dumps(ports)+'\nSpecification:\n'+specification)
    return payload([{'role':'system','content':'Extract a precise hardware behavior contract. No implementation, tests, benchmark identifiers or reference access.'},
                    {'role':'user','content':content}],model=model)

def build_contracts(tasks,model=MODEL):
    stage='contracts_'+model
    path=ROOT/'configs'/(stage+'_jobs.json');jobs=load(path) if path.exists() else []
    requests=load(ROOT/'configs'/(stage+'_requests.json')) if path.exists() else {}
    for task in sorted(set(tasks)):
        key='contracts/'+model+'/'+task
        if key in requests:continue
        request=contract_request(task,model);requests[key]=request
        jobs.append({'key':key,'task':task,'language':'shared','arm':'C','kind':'contract','model':model,
                     'request_sha256':canonical(request),'prompt_sha256':canonical(request['messages'])})
    save(path,jobs);save(ROOT/'configs'/(stage+'_requests.json'),requests);return stage

def contract(task,model):
    path=ROOT/'runs/contracts'/model/task/'contract.json'
    if not path.exists():raise RuntimeError('Required contract missing: '+str(path))
    return load(path)

def directives(language,text):
    # Candidate-exception mappings apply to every task. No task-name matching.
    maps={
       'pyrtl': [('multiple','Use one driver per wire and register.next; combine guards with conditional_assignment.'),('slice','PyRTL slices use low-inclusive/high-exclusive bounds; use temporary internal wires.')],
       'myhdl': [('sensitivity','@always_comb requires reading at least one Signal in its body; preserve the exact public interface.'),('intbv','Use explicitly sized Signal(intbv(...)[W:]) or modbv, including bounded intermediate values.')],
       'amaranth':[('driver','Assign each signal in exactly one clock domain; use m.d.comb or m.d.sync consistently.')],
       'migen':[('Case','Migen Case uses a dictionary of cases, with a "default" key for default assignments.')],
       'pymtl3':[('UpdateFF','Use <<= to update complete registers only inside @update_ff; @= is combinational.')],
    }
    matches=[message for term,message in maps.get(language,[]) if term.lower() in text.lower()]
    return matches or ['Fix the actual syntax/construction exception below using the required native HCL interface; preserve specified behavior.']

def repair_request(start,arm,model=MODEL):
    generation_arm=start.get('generation_arm',start['arm'] if start['arm'] in ['Direct','Gen'] else 'Gen')
    genjob=generation_job(start['instance'],arm=generation_arm,model=model)
    initial=load(ROOT/'configs'/('exp1_requests.json' if model==MODEL else 'cross_'+model+'_requests.json'))[genjob['key']]
    prompt=initial['messages'][1]['content']
    directory=run_dir(start)
    source=(directory/'candidate.py').read_text(encoding='utf-8') if (directory/'candidate.py').exists() else (directory/'raw_output.txt').read_text(encoding='utf-8')
    evidence=official_artifacts(start);r=evaluation(start)
    prompt+='\n\nRepair this exact selected candidate, preserving all required interfaces and unrelated correct behavior.\n<ORIGINAL>\n'+source+'\n</ORIGINAL>\n'
    if arm=='FL':
        gate=result_dir(start)/'gate.json'
        failure=load(gate) if gate.exists() else {'output_format_error':load(directory/'generation.json').get('error')}
        prompt+='F_exc: actual reference-blind construction failure:\n'+json.dumps(failure,ensure_ascii=False)
        prompt+='\nL_diag: generic compiler-exception mapping:\n'+'\n'.join(directives(start['language'],json.dumps(failure)))
    else:
        fpath=evidence/'F_multi.json';single=evidence/'failure.json'
        if fpath.exists():failures=load(fpath)['counterexamples'][:5]
        elif single.exists():failures=[load(single)]
        else:
            # A gate-passing native elaboration/simulation exception remains
            # explicit feedback, without fabricating a mismatching vector.
            exception=r['candidate_nonconvergence'] if r.get('candidate_nonconvergence') else load(evidence/'exception.json') if (evidence/'exception.json').exists() else load(result_dir(start)/'gate.json') if (result_dir(start)/'gate.json').exists() else r.get('native',r)
            failures=[{'native_exception':exception}]
        prompt+='F_multi: up to five actual official-native counterexamples or the exact native exception:\n'+json.dumps([{k:v for k,v in f.items() if k!='T'} for f in failures],ensure_ascii=False)
        if 'C' in arm:prompt+='\nC(x): shared specification-derived behavioral intermediate representation:\n'+json.dumps(contract(start['task'],model),ensure_ascii=False)
        if 'T' in arm:
            traces=[f['T'] for f in failures if f.get('T')]
            if not traces and (evidence/'trace.json').exists():traces=[load(evidence/'trace.json')]
            prompt+='\nT: backward dependency evidence (conservative source slice; line numbers refer to ORIGINAL):\n'+json.dumps(traces if traces else {'slice_available':False,'reason':'native exception without a failed output'},ensure_ascii=False)
    prompt+='\nReturn one complete Python source file inside <CODE>...</CODE>. No explanation, tests or reference access.'
    request=payload([{'role':'system','content':'You repair one existing '+ADAPTER[start['language']]+' hardware design using native semantics, exact public interface, and the supplied evidence. One repair attempt only.'},
                     {'role':'user','content':prompt}],model=model)
    assert 'BCD_GUARD' not in prompt and 'KNOWN SPECIFICATION/REFERENCE DISPUTE' not in prompt
    return request

def queue_repairs(stage,plans,model=MODEL):
    jobs=[];requests={}
    for start,arm,logical in plans:
        req=repair_request(start,arm,model);identity=canonical(req)
        key='repairs/'+model+'/'+identity
        job=registered_job(key,start['task'],start['language'],arm,req,start_key=start['key'],logical_stage=logical,
                           generation_arm=start.get('generation_arm',start['arm'] if start['arm'] in ['Direct','Gen'] else 'Gen'))
        requests[key]=req;jobs.append(job)
    # Same evidence arms used by Inverse/Equation4 are exact request aliases.
    jobs=list({j['key']:j for j in jobs}.values())
    save(ROOT/'configs'/(stage+'_jobs.json'),jobs);save(ROOT/'configs'/(stage+'_requests.json'),requests);return jobs

def precondition():
    gen=[j for j in load(ROOT/'configs/exp1_jobs.json') if j['arm']=='Gen']
    assert len(gen)==840
    plans=[(j,'FL','shared_FL') for j in gen if not evaluation(j)['c0_pass']]
    return queue_repairs('exp2_fl',plans)

def choose(start,candidate):
    # Gate-only acceptance; no functional pass/fail selection among repairs.
    return candidate if evaluation(candidate)['c0_pass'] else start

def starts():
    fl={j['start_key']:j for j in load(ROOT/'configs/exp2_fl_jobs.json')}
    out=[]
    for j in load(ROOT/'configs/exp1_jobs.json'):
        if j['arm']!='Gen':continue
        selected=choose(j,fl[j['key']]) if j['key'] in fl else j
        out.append({'initial':j,'start':selected,'shared_fl':fl.get(j['key'])})
    assert len(out)==840;return out

def factorial():
    pool=[s for s in starts() if evaluation(s['start'])['c0_pass'] and not evaluation(s['start'])['native_pass']]
    save(ROOT/'configs/functional_pool.json',pool)
    return queue_repairs('exp2_factorial',[(s['start'],arm,'factorial') for s in pool for arm in ['F','FT','FC','FCT']])

def functional_routes(j):
    pop=next(p for p in load(ROOT/'configs/population.json') if p['instance']==j['instance'])
    decision=pop['interface_route'];branch=decision['branch'][:-1]
    return branch,'FT' if decision['has_clk'] else 'FC'

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['precondition','contracts','factorial']);a=p.parse_args()
    if a.mode=='precondition':print(len(precondition()))
    elif a.mode=='contracts':
        pool=[s for s in starts() if evaluation(s['start'])['c0_pass'] and not evaluation(s['start'])['native_pass']]
        print(build_contracts([s['start']['task'] for s in pool]))
    else:print(len(factorial()))
