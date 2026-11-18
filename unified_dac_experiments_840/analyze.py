"""840-denominator tables from complete stage ledgers; no missing-score imputation."""
from __future__ import annotations
import collections, math
import numpy as np
from common import *
from repair import evaluation,starts,choose,functional_routes
from pipelines import final_states

def usage(j):
    response=load(run_dir(j)/'response.json');u=response.get('usage') or {}
    return {'input':u.get('prompt_tokens'),'output':u.get('completion_tokens'),
            'cached':(u.get('prompt_tokens_details') or {}).get('cached_tokens',u.get('prompt_cache_hit_tokens')),
            'total':u.get('total_tokens'),'calls':1}

def known_sum(values):
    values=list(values)
    return sum(values) if all(v is not None for v in values) else None

def known_mean(values):
    values=list(values);total=known_sum(values)
    return total/len(values) if values and total is not None else None

def contract_usage(task,model):
    directory=ROOT/'runs/contracts'/model/task
    resolution=directory/'contract_resolution.json'
    keys=load(resolution)['attempt_keys'] if resolution.exists() else ['contracts/'+model+'/'+task]
    values=[usage({'key':key}) for key in dict.fromkeys(keys)]
    return {**{f:known_sum(u[f] for u in values) for f in ['input','output','cached','total']},'calls':len(values)}

def costs(jobs,model=MODEL,language=None,contract_attempt_tasks=()):
    jobs=list({j['key']:j for j in jobs if j}.values());u=[usage(j) for j in jobs]
    out={'calls':len(jobs)}
    for field in ['input','output','cached','total']:
        known=[x[field] for x in u if x[field] is not None]
        out[field]=sum(known) if len(known)==len(u) else None
    required=sorted({j['task'] for j in jobs if j.get('arm') in ['FC','FCT']}|set(contract_attempt_tasks))
    cu=[contract_usage(task,model) for task in required]
    contract_total=known_sum(u['total'] for u in cu);contract_calls=sum(u['calls'] for u in cu)
    total=out['total']
    out.update(contract_tasks=len(required),contract_calls=contract_calls,contract_tokens=contract_total,
               lazy_tokens=total+contract_total if total is not None and contract_total is not None else None,
               amortized_tokens=total+contract_total/5 if total is not None and contract_total is not None else None,
               lazy_calls=len(jobs)+contract_calls,amortized_calls=len(jobs)+contract_calls/5)
    for field in ['input','output','cached']:
        out['contract_'+field+'_tokens']=known_sum(u[field] for u in cu)
    return out

def per_instance_cost(jobs,model=MODEL,contract_attempt_tasks=()):
    # Logical deployment in one HCL pays one C(x) for a task on its first
    # FC/FCT use; later repairs of that instance reuse it. Across five HCLs
    # amortization divides that task call/cost by five exactly once per instance.
    return costs(jobs,model,contract_attempt_tasks=contract_attempt_tasks)

def allocate_joint_contracts(records,method_key='arm'):
    """One shared C call per task in the complete five-HCL deployment.

    Spread its actual cost over all five sibling HCL rows, including siblings
    whose own path does not need C. This prevents charging only a fifth of a
    contract when just one of the five languages triggers the branch.
    """
    groups=collections.defaultdict(list)
    for r in records:groups[(r.get('model',MODEL),r[method_key])].append(r)
    for _,rows in groups.items():
        assert all(n==5 for n in collections.Counter(r['task'] for r in rows).values()),'Five-HCL allocation requires complete sibling rows'
        contracts={}
        for r in rows:
            if r.get('contract_tasks',0):contracts[r['task']]=(r['contract_tokens'],r.get('contract_calls',1))
        for r in rows:
            shared,shared_calls=contracts.get(r['task'],(0,0))
            candidate=r.get('total')
            if candidate is not None:
                r['amortized_tokens']=candidate+shared/5 if shared is not None else None
            r['amortized_calls']=r['calls']+shared_calls/5
            r['shared_contract_triggered_by_any_hcl']=r['task'] in contracts
    return records

def paired(rows,left,right,metric='native_pass'):
    # Independent clusters are the 168 tasks, with five paired HCLs per task.
    by={a:{r['instance']:r for r in rows if r['arm']==a} for a in [left,right]}
    if len(by[left])!=840 or len(by[right])!=840:raise RuntimeError('paired /840 table incomplete')
    d=collections.defaultdict(list)
    for key,x in by[left].items():d[x['task']].append(int(x[metric])-int(by[right][key][metric]))
    delta=np.array([np.mean(v) for _,v in sorted(d.items())]);rng=np.random.default_rng(SEED)
    boots=np.array([rng.choice(delta,len(delta),replace=True).mean() for _ in range(20000)])
    extreme=0
    for _ in range(20000):extreme+=abs(np.mean(delta*rng.choice([-1,1],len(delta))))>=abs(delta.mean())-1e-12
    return {'left':left,'right':right,'metric':metric,'difference_pp':delta.mean()*100,
            'ci_low_pp':float(np.quantile(boots,.025)*100),'ci_high_pp':float(np.quantile(boots,.975)*100),
            'p':(extreme+1)/20001,'tasks':168,'instances':840,'test':'paired task-cluster sign flip; 20000 draws'}

def report_table(path,headers,rows):
    text='| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'
    for r in rows:text+='| '+' | '.join(str(r.get(k,'')) for k in headers)+' |\n'
    path.write_text(text,encoding='utf-8')

def report_notes(path,text):
    path.write_text(path.read_text(encoding='utf-8')+'\n'+text+'\n',encoding='utf-8')

def experiment1():
    jobs=load(ROOT/'configs/exp1_jobs.json');assert len(jobs)==2520
    records=[]
    for j in jobs:
        r=evaluation(j);u=usage(j)
        records.append({**j,'c0_pass':r['c0_pass'],'native_pass':r['native_pass'],'rtl_pass':r['rtl_pass'],
                        'outcome':r['outcome'],'infrastructure_error':r['infrastructure_error'],**{k+'_tokens':v for k,v in u.items() if k!='calls'}})
    assert len(records)==2520
    rows=[]
    for lang in LANGS+['All']:
        for arm in ['Direct','FullDocRAG','Gen']:
            selected=[r for r in records if r['arm']==arm and (lang=='All' or r['language']==lang)];n=len(selected)
            assert n==(840 if lang=='All' else 168)
            row={'language':lang,'arm':arm,'n':n,'c0_passed':sum(r['c0_pass'] for r in selected),
                 'native_passed':sum(r['native_pass'] for r in selected),'rtl_passed':sum(r['rtl_pass'] for r in selected)}
            for key in ['c0','native','rtl']:row[key+'_percent']=100*row[key+'_passed']/n
            for field in ['input_tokens','output_tokens','cached_tokens','total_tokens']:
                values=[r[field] for r in selected];row[field]=sum(values) if all(x is not None for x in values) else None
                row[field+'_mean']=row[field]/n if row[field] is not None else None
            rows.append(row)
    effects=[paired(records,'Gen',baseline,metric) for baseline in ['Direct','FullDocRAG'] for metric in ['c0_pass','native_pass','rtl_pass']]
    # Per-language exact paired binomial/McNemar tests (no independence assumed
    # between the two arms within a task).
    from scipy.stats import binomtest
    for lang in LANGS:
        for baseline in ['Direct','FullDocRAG']:
            by={a:{r['task']:r for r in records if r['arm']==a and r['language']==lang} for a in ['Gen',baseline]}
            for metric in ['c0_pass','native_pass','rtl_pass']:
                win=sum(by['Gen'][t][metric] and not by[baseline][t][metric] for t in by['Gen']);loss=sum(not by['Gen'][t][metric] and by[baseline][t][metric] for t in by['Gen'])
                effects.append({'left':'Gen','right':baseline,'language':lang,'metric':metric,'wins':win,'losses':loss,
                                'p':float(binomtest(win,win+loss).pvalue) if win+loss else 1.0,'instances':168})
    csv_write(ROOT/'analysis/exp1_instance_scores.csv',records);save(ROOT/'analysis/exp1_instance_scores.json',records)
    csv_write(ROOT/'analysis/table_iv.csv',rows);save(ROOT/'analysis/table_iv.json',rows);save(ROOT/'analysis/table_iv_paired.json',effects)
    report_table(ROOT/'analysis/experiment1_report.md',['language','arm','n','c0_passed','native_passed','rtl_passed','input_tokens_mean','cached_tokens_mean'],rows)
    report_notes(ROOT/'analysis/experiment1_report.md',
        'Each arm uses all 840 instances (168 per HCL), deepseek-v4.1-flash at temperature 0.2. '
        'The acceptance pipeline is C0 -> Q_native -> C_RTL; downstream pass indicators require earlier gates. '
        'Output-format failures remain in the denominator. All-instance paired tests use 168 task clusters; '
        'per-HCL tests use exact paired binomial tests. Detailed effects and p values are in table_iv_paired.json. '
        'Cached-token fields remain unknown when the provider omits them. Full-Doc RAG uses complete passages of 1001--1492 tokens.')
    save(ROOT/'progress/experiment1_complete.json',{'complete':True,'population':840,'records':2520,'infra_unresolved':0})
    print(json.dumps({'experiment':1,'all_rows':[r for r in rows if r['language']=='All']}),flush=True)

def experiment2():
    base=starts();armjobs=load(ROOT/'configs/exp2_factorial_jobs.json')
    lookup={(j['start_key'],j['arm']):j for j in armjobs};rows=[];instance=[]
    for method in ['F','FT','FC','FCT','Inverse-Route','ParaRoute']:
        for s in base:
            initial,start=s['initial'],s['start'];r=evaluation(start);eligible=r['c0_pass'] and not r['native_pass'];trial=None
            if eligible:
                routed,inverse=functional_routes(start);arm=routed if method=='ParaRoute' else inverse if method=='Inverse-Route' else method
                trial=lookup[(start['key'],arm)];selected=choose(start,trial)
            else:selected=start
            result=evaluation(selected);sequence=[initial,s['shared_fl'],trial];cost=per_instance_cost(sequence)
            # The factual token increment for C injection comes from paired
            # provider usage on exactly the same source/evidence, with C the
            # only request-text difference (FC-F or FCT-FT). Output differences
            # remain in total deployment cost and are not attributed to C.
            injection=0
            if trial and trial['arm'] in ['FC','FCT']:
                without=lookup[(start['key'],'F' if trial['arm']=='FC' else 'FT')]
                with_input,without_input=usage(trial)['input'],usage(without)['input']
                injection=with_input-without_input if with_input is not None and without_input is not None else None
                if injection is not None and injection<0:raise RuntimeError('Inconsistent paired input token usage')
            pop=next(p for p in load(ROOT/'configs/population.json') if p['instance']==initial['instance'])
            instance.append({'method':method,'instance':initial['instance'],'task':initial['task'],'language':initial['language'],
                 'has_clk':pop['interface_route']['has_clk'],'functional_eligible':eligible,'native_pass':result['native_pass'],'rtl_pass':result['rtl_pass'],
                 'selected_key':selected['key'],'contract_injection_input_tokens':injection,**cost})
    allocate_joint_contracts(instance,'method')
    for method in ['F','FT','FC','FCT','Inverse-Route','ParaRoute']:
        for group in ['All','Stateless Comb','Clocked Seq','F_func']:
            x=[r for r in instance if r['method']==method and (group=='All' or r['functional_eligible'] and (group=='F_func' or r['has_clk']==(group=='Clocked Seq')))];n=len(x)
            rows.append({'method':method,'group':group,'n':n,'native_passed':sum(r['native_pass'] for r in x),'rtl_passed':sum(r['rtl_pass'] for r in x),
                         'native_percent':100*sum(r['native_pass'] for r in x)/n if n else None,'rtl_percent':100*sum(r['rtl_pass'] for r in x)/n if n else None,
                         'lazy_tokens':sum(r['lazy_tokens'] for r in x) if all(r['lazy_tokens'] is not None for r in x) else None})
    csv_write(ROOT/'analysis/exp2_instance_scores.csv',instance);save(ROOT/'analysis/exp2_instance_scores.json',instance)
    csv_write(ROOT/'analysis/table_v.csv',rows);save(ROOT/'analysis/table_v.json',rows)
    cost_summary=[]
    for method in ['F','FT','FC','FCT','Inverse-Route','ParaRoute']:
        x=[r for r in instance if r['method']==method]
        cost_summary.append({'method':method,'n':840,'candidate_calls':sum(r['calls'] for r in x),
             'candidate_tokens':known_sum(r['total'] for r in x),
             'candidate_input_tokens':known_sum(r['input'] for r in x),'candidate_output_tokens':known_sum(r['output'] for r in x),
             'candidate_cached_tokens':known_sum(r['cached'] for r in x),
             'single_hcl_lazy_total_tokens':known_sum(r['lazy_tokens'] for r in x),
             'five_hcl_joint_total_tokens':known_sum(r['amortized_tokens'] for r in x),
             'single_hcl_contract_tokens':known_sum(r['contract_tokens'] for r in x),
             'contract_injection_input_tokens':known_sum(r['contract_injection_input_tokens'] for r in x),
             'joint_contract_tasks':len({r['task'] for r in x if r['contract_tasks']}),
             'joint_contract_generation_tokens':known_sum({r['task']:r['contract_tokens'] for r in x if r['contract_tasks']}.values())})
    for r in cost_summary:
        for prefix,generation_field in [('single_hcl','single_hcl_contract_tokens'),('five_hcl_joint','joint_contract_generation_tokens')]:
            r[prefix+'_contract_generation_plus_injection_tokens']=known_sum([r[generation_field],r['contract_injection_input_tokens']])
    stacked=next(r for r in cost_summary if r['method']=='FCT')
    for r in cost_summary:
        for field in ['single_hcl_lazy_total_tokens','five_hcl_joint_total_tokens','single_hcl_contract_generation_plus_injection_tokens','five_hcl_joint_contract_generation_plus_injection_tokens']:
            r[field+'_saving_vs_fct_percent']=100*(1-r[field]/stacked[field]) if r[field] is not None and stacked[field] else None
    csv_write(ROOT/'analysis/table_v_actual_costs.csv',cost_summary)
    save(ROOT/'analysis/table_v_actual_costs.json',cost_summary)
    paired_rows=[{**r,'arm':r['method']} for r in instance]
    effects=[paired(paired_rows,'ParaRoute',baseline,metric) for baseline in ['F','FT','FC','FCT','Inverse-Route'] for metric in ['native_pass','rtl_pass']]
    save(ROOT/'analysis/table_v_paired.json',effects)
    report_table(ROOT/'analysis/experiment2_report.md',['method','group','n','native_passed','native_percent','rtl_passed','lazy_tokens'],rows)
    flow={'initial_native_passed':sum(evaluation(s['initial'])['native_pass'] for s in base),
          'initial_c0_rejected_and_FL_attempted':sum(bool(s['shared_fl']) for s in base),
          'after_shared_FL_native_passed':sum(evaluation(s['start'])['native_pass'] for s in base),
          'remaining_c0_rejected':sum(not evaluation(s['start'])['c0_pass'] for s in base),
          'functional_pool':sum(evaluation(s['start'])['c0_pass'] and not evaluation(s['start'])['native_pass'] for s in base)}
    assert flow['after_shared_FL_native_passed']+flow['remaining_c0_rejected']+flow['functional_pool']==840
    save(ROOT/'analysis/exp2_population_flow.json',flow)
    report_notes(ROOT/'analysis/experiment2_report.md',
        'All is the end-to-end /840 score. F_func, Stateless Comb and Clocked Seq are conditional repair-recovery rows '
        'from the common post-FL functional-failure pool, not alternative populations. Population flow: '+json.dumps(flow)+'. '
        'Inverse and Equation-4 policies alias the same independently generated F/FT/FC/FCT requests. '
        'A rejected repair falls back using C0 alone. All /840 paired effects are in table_v_paired.json. '
        'table_v_actual_costs.csv reports deployment costs, actual paired-provider prompt increments for contract injection, '
        'and savings versus FCT; shared contract generation is counted once per task. '
        'The physical factorial bill is separate from per-policy deployment cost.')
    save(ROOT/'progress/experiment2_complete.json',{'complete':True,'population':840,'F_func':sum(evaluation(s['start'])['c0_pass'] and not evaluation(s['start'])['native_pass'] for s in base),'infra_unresolved':0})
    print(json.dumps({'experiment':2,'rows':rows}),flush=True)

def pipeline_rows(model=MODEL):
    states=final_states(model);rows=[]
    for s in states:
        if s['kind']=='DirectF':
            methods=[('Direct',s['initial'],[s['initial']]),('Direct+F',s['selected'],[s['initial'],s['first']])]
        else:methods=[('Gen',s['initial'],[s['initial']]),('Fast',s['fast_selected'],[s['initial'],s['first']]),('Full',s['selected'],[s['initial'],s['first'],s['second']])]
        for method,selected,sequence in methods:
            failures=[]
            if method in ['Fast','Full'] and s.get('first_contract_failure'):failures.append(s['task'])
            if method=='Full' and s.get('second_contract_failure'):failures.append(s['task'])
            r=evaluation(selected);cost=per_instance_cost(sequence,model,contract_attempt_tasks=failures)
            rows.append({'model':model,'arm':method,'task':s['task'],'language':s['language'],'instance':s['instance'],
                 'c0_pass':r['c0_pass'],'native_pass':r['native_pass'],'rtl_pass':r['rtl_pass'],'selected_key':selected['key'],
                 'contract_output_failure':bool(failures),**cost})
    return allocate_joint_contracts(rows)

def experiment3():
    jobs=load(ROOT/'configs/exp3_jobs.json');assert len(jobs)==8400
    initial=pipeline_rows();rows=[];detail=[]
    by=collections.defaultdict(list)
    for j in jobs:by[(j['instance'],j['arm'])].append(j)
    for (instance,arm),samples in sorted(by.items()):
        samples.sort(key=lambda j:j['sample']);assert len(samples)==5
        results=[evaluation(j) for j in samples];success={m:sum(r[m] for r in results) for m in ['native_pass','rtl_pass']}
        for k in [1,3,5]:
            row={'instance':instance,'task':samples[0]['task'],'language':samples[0]['language'],'arm':arm,'k':k,'method':arm+' Pass@'+str(k),
                 'calls':k,'input':None,'output':None,'cached':None,'contract_tasks':0,'contract_tokens':0}
            for m in success:row[m]=1-math.comb(5-success[m],k)/math.comb(5,k) if 5-success[m]>=k else 1.0
            u=[usage(j) for j in samples];total=known_sum(x['total'] for x in u)
            row.update(lazy_tokens=total*k/5 if total is not None else None,amortized_tokens=total*k/5 if total is not None else None,lazy_calls=k,amortized_calls=k);detail.append(row)
            eligible=[(j,r) for j,r in zip(samples[:k],results[:k]) if r['c0_pass']]
            clean=[(j,r) for j,r in eligible if r.get('gate_warning_free')];chosen=(clean or eligible or [(None,{})])[0]
            cost=per_instance_cost(samples[:k]);detail.append({**row,'method':arm+' GatedBest@'+str(k),
                  'native_pass':bool(chosen[1].get('native_pass')),'rtl_pass':bool(chosen[1].get('rtl_pass')),
                  **cost})
    for r in initial:
        if r['arm'] in ['Fast','Full']:detail.append({**r,'method':'ParaRoute-'+r['arm']})
    for method in sorted({r['method'] for r in detail}):
        x=[r for r in detail if r['method']==method];assert len(x)==840
        rows.append({'method':method,'n':840,'native_expected_passed':sum(r['native_pass'] for r in x),'native_percent':100*np.mean([r['native_pass'] for r in x]),
             'rtl_expected_passed':sum(r['rtl_pass'] for r in x),'rtl_percent':100*np.mean([r['rtl_pass'] for r in x]),
             'mean_calls':np.mean([r['calls'] for r in x]),'mean_calls_including_lazy_contracts':np.mean([r['lazy_calls'] for r in x]),
             'mean_calls_including_amortized_contracts':np.mean([r['amortized_calls'] for r in x]),
             'mean_amortized_tokens':known_mean(r['amortized_tokens'] for r in x),'mean_lazy_tokens':known_mean(r['lazy_tokens'] for r in x)})
    csv_write(ROOT/'analysis/exp3_instance_scores.csv',detail);save(ROOT/'analysis/exp3_instance_scores.json',detail)
    csv_write(ROOT/'analysis/table_vi.csv',rows);save(ROOT/'analysis/table_vi.json',rows)
    special=[]
    population={p['instance']:p for p in load(ROOT/'configs/population.json')}
    predicates={
       'MyHDL constants':lambda r:r['language']=='myhdl' and population[r['instance']]['reporting_category']==1,
       'Prob02p05 width truncation':lambda r:r['task'].startswith('Prob02p05'),
       'FSM':lambda r:population[r['instance']]['reporting_category']==16,
       'Arbiters':lambda r:population[r['instance']]['reporting_category']==15,
       'Serial arithmetic':lambda r:population[r['instance']]['reporting_category']==18,
       'All clocked':lambda r:population[r['instance']]['interface_route']['has_clk']}
    for name,predicate in predicates.items():
        for method in sorted({r['method'] for r in detail}):
            x=[r for r in detail if r['method']==method and predicate(r)];n=len(x)
            special.append({'stratum':name,'method':method,'n':n,'native_expected_passed':sum(r['native_pass'] for r in x),
                 'native_percent':100*np.mean([r['native_pass'] for r in x]) if n else None,
                 'rtl_expected_passed':sum(r['rtl_pass'] for r in x),'rtl_percent':100*np.mean([r['rtl_pass'] for r in x]) if n else None})
    csv_write(ROOT/'analysis/table_vi_specialized.csv',special)
    save(ROOT/'analysis/table_vi_specialized.json',special)
    report_table(ROOT/'analysis/experiment3_report.md',['method','n','native_percent','rtl_percent','mean_calls','mean_amortized_tokens','mean_lazy_tokens'],rows)
    report_notes(ROOT/'analysis/experiment3_report.md',
        'All 840 instances have five fresh samples per arm, all at temperature 0.7 / top_p 0.95; no temperature-0.2 k1 is imported. '
        'Pass@k is the unbiased estimator 1-C(5-c,k)/C(5,k), so expected pass counts need not be integers. '
        'Its k-call cost is the expected cost of k samples estimated from all five responses; the physical sampling experiment generates all five. '
        'GatedBest uses only C0 on the first k samples and prefers the first warning-free gate-passing candidate; '
        'native/RTL outcomes never rank candidates. Fast and Full use the same model at temperature 0.2 with at most one/two code repairs. '
        'mean_calls counts code-generation/repair calls; table_vi.csv additionally includes calls for lazy and shared contracts. '
        'All contract formatting attempts are charged. Five-HCL sharing conserves each actual contract bill once across siblings; '
        'single-HCL lazy accounting pays only on the first contract-requiring branch. Specialized strata are secondary diagnostics in table_vi_specialized.csv.')
    save(ROOT/'progress/experiment3_complete.json',{'complete':True,'population':840,'samples':8400,'infra_unresolved':0})
    print(json.dumps({'experiment':3,'rows':rows}),flush=True)

def experiment4(models):
    expected=[MODEL,'qwen3.8-flash','glm-5.3-flash','claude-haiku-5-5']
    if len(models)!=len(set(models)) or set(models)-set(expected):
        raise ValueError('Experiment 4 received unexpected or duplicate model names')
    if set(models)!=set(expected):
        print(json.dumps({'experiment':4,'completed_models':models,
                          'awaiting_models':[m for m in expected if m not in models],
                          'cross_model_tables_published':False}),flush=True)
        return
    models=expected
    records=[];rows=[];effects=[]
    for model in models:
        data=pipeline_rows(model);records.extend(data)
        for lang in LANGS+['All']:
            for method in ['Direct','Direct+F','Gen','Fast','Full']:
                x=[r for r in data if r['arm']==method and (lang=='All' or r['language']==lang)]
                assert len(x)==(840 if lang=='All' else 168)
                rows.append({'model':model,'language':lang,'method':method,'n':len(x),'c0_errors':sum(not r['c0_pass'] for r in x),
                     'native_passed':sum(r['native_pass'] for r in x),'native_percent':100*np.mean([r['native_pass'] for r in x]),
                     'rtl_passed':sum(r['rtl_pass'] for r in x),'rtl_percent':100*np.mean([r['rtl_pass'] for r in x]),
                     'mean_calls':np.mean([r['calls'] for r in x]),'mean_calls_including_lazy_contracts':np.mean([r['lazy_calls'] for r in x]),
                     'mean_input_tokens':known_mean(r['input'] for r in x),'mean_output_tokens':known_mean(r['output'] for r in x),
                     'mean_cached_tokens':known_mean(r['cached'] for r in x),
                     'mean_amortized_tokens':known_mean(r['amortized_tokens'] for r in x),'mean_lazy_tokens':known_mean(r['lazy_tokens'] for r in x)})
        effects.extend([paired(data,'Full',baseline,metric)|{'model':model,'language':'All'} for baseline in ['Direct','Direct+F','Gen','Fast'] for metric in ['native_pass','rtl_pass']])
        from scipy.stats import binomtest
        for lang in LANGS:
            for baseline in ['Direct','Direct+F','Gen','Fast']:
                by={a:{r['task']:r for r in data if r['arm']==a and r['language']==lang} for a in ['Full',baseline]}
                for metric in ['native_pass','rtl_pass']:
                    wins=sum(by['Full'][t][metric] and not by[baseline][t][metric] for t in by['Full'])
                    losses=sum(not by['Full'][t][metric] and by[baseline][t][metric] for t in by['Full'])
                    effects.append({'model':model,'language':lang,'left':'Full','right':baseline,'metric':metric,
                         'wins':wins,'losses':losses,'n':168,'p':float(binomtest(wins,wins+losses).pvalue) if wins+losses else 1.0})
    from statsmodels.stats.multitest import multipletests
    if effects:
        corrected=multipletests([e['p'] for e in effects],method='holm')[1]
        for e,p in zip(effects,corrected):e['p_holm']=float(p);e['holm_family_size']=len(effects)
    csv_write(ROOT/'analysis/exp4_instance_scores.csv',records);save(ROOT/'analysis/exp4_instance_scores.json',records)
    csv_write(ROOT/'analysis/table_vii_viii.csv',rows);save(ROOT/'analysis/table_vii_viii.json',rows);save(ROOT/'analysis/table_vii_viii_paired_holm.json',effects)
    report_table(ROOT/'analysis/experiment4_report.md',['model','language','method','n','c0_errors','native_percent','rtl_percent','mean_lazy_tokens'],rows)
    report_notes(ROOT/'analysis/experiment4_report.md',
        'Every included model/method uses all 840 instances (168 per HCL) with the same prompts, output cap and acceptance pipeline. '
        'C0 errors are blind-gate rejections, including invalid/truncated source output. '
        'Native and RTL pass indicators follow sequential acceptance. All paired comparisons and the exact Holm family size '
        'are recorded in table_vii_viii_paired_holm.json. Claude uses the confirmed Anthropic Messages '
        'transport. Its endpoint does not accept seed/reasoning_effort or the deprecated temperature/top_p controls; '
        'these nominal fields in the canonical request are omitted on the wire, so identical sampling control across '
        'families is not claimed. Every selected Claude candidate has its own generation and official evaluation record; '
        'parse failures remain in the fixed denominator. A support contract that still fails after two schema-only '
        'corrections terminates that repair branch, retains the accepted predecessor, and charges all support attempts; '
        'the corresponding instance remains in /840. Contract output failures are explicitly flagged in exp4_instance_scores.csv.')
    save(ROOT/'progress/experiment4_complete.json',{'complete':all(m in models for m in expected),
         'population':840,'models':models,'infra_unresolved':0,'claude_available':'claude-haiku-5-5' in models})

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('experiment',type=int);p.add_argument('--models',nargs='*',default=[MODEL]);a=p.parse_args()
    {1:experiment1,2:experiment2,3:experiment3,4:lambda:experiment4(a.models)}[a.experiment]()
