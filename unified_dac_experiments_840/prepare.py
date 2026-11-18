"""Freeze the 840-instance population and deterministic Direct/Gen requests."""
from __future__ import annotations
import collections, re, shutil
from common import *
from router import route, PATTERNS

def insert_material(content, material):
    marker='\n\nReturn a complete Python design file'
    if marker not in content: raise ValueError('Missing frozen interface/output template')
    head,tail=content.rsplit(marker,1)
    return head+'\n\n'+material.strip()+marker+tail

def main():
    for folder in ['configs','analysis','protocol','corpus','runtime','runs','evaluation','progress','archives']:
        (ROOT/folder).mkdir(parents=True,exist_ok=True)
    base=load(PHASE1/'configs/generation_requests.json')
    public=load(WORK/'task_b_20261109/configs/public_configurations.json')
    enc=tokenizer();rules={};rule_provenance={}
    for lang in LANGS:
        path=PHASE1/'prompts'/('L_'+ADAPTER[lang]+'.txt')
        text=path.read_text(encoding='utf-8-sig').strip()
        if lang=='myhdl':
            text=text.split('4. Even constant-only modules')[0].rstrip()+'\n4. @always_comb requires reading at least one Signal to form a non-empty sensitivity list. Return every generator instance.'
        assert 'BCD_GUARD' not in text
        rules[lang]='Target language obligations:\n'+text
        target=ROOT/'protocol'/('L_'+lang+'.txt');target.write_text(text+'\n',encoding='utf-8')
        rule_provenance[lang]={'tokens_cl100k':len(enc.encode(text)), 'sha256':sha(target),
                               'inherited_source':str(path),'source_sha256':sha(path)}
    tasks=sorted({k.split('/')[0] for k in base})
    assert len(tasks)==168
    population=[];requests={};jobs=[];strata=collections.Counter()
    for task in tasks:
        spec_path=DATA/'dataset'/(task+'_prompt.txt')
        specification=spec_path.read_text(encoding='utf-8-sig')
        (ROOT/'protocol/specifications').mkdir(exist_ok=True)
        (ROOT/'protocol/specifications'/(task+'.txt')).write_text(specification,encoding='utf-8')
        ports=public[task][0]['ports']
        decision=route(ports,specification)
        for lang in LANGS:
            source=base[f'{task}/{ADAPTER[lang]}/Direct']
            direct=source['messages'][1]['content']
            assert direct.count('Answer:')>=3, (task,lang,'missing 3-shot')
            assert '<CODE>' in direct and 'Common benchmark calling convention:' in direct
            assert 'BCD_GUARD' not in direct and 'KNOWN SPECIFICATION/REFERENCE DISPUTE' not in direct
            p={'instance':task+'/'+lang,'task':task,'language':lang,
               'adapter_language':ADAPTER[lang],'spec_sha256':sha(spec_path),
               'public_config_sha256':canonical(public[task]),'interface_route':decision,
               'reporting_category':int(task[4:6]),'reporting_stratum':'Comb' if int(task[4:6])<10 else 'Seq'}
            population.append(p);strata[p['reporting_stratum']]+=1
            for arm,content in [('Direct',direct),('Gen',insert_material(direct,rules[lang]))]:
                messages=[dict(m) for m in source['messages']];messages[1]={'role':'user','content':content}
                request=payload(messages);key=f'exp1/{task}/{lang}/{arm}'
                requests[key]=request;jobs.append(registered_job(key,task,lang,arm,request,experiment=1))
    assert len(population)==840 and strata=={'Comb':485,'Seq':355}
    save(ROOT/'configs/population.json',population);save(ROOT/'configs/public_configurations.json',public)
    save(ROOT/'configs/exp1_jobs.json',jobs);save(ROOT/'configs/exp1_requests.json',requests)
    protocol={'schema_version':'unified840.v1','population':840,'tasks':168,'languages':LANGS,
              'model':MODEL,'deterministic_parameters':PARAMS,'hypothesis_seed':SEED,'image':IMAGE,
              'strata':dict(strata),'rules':rule_provenance,'router_patterns':PATTERNS,
              'router_sha256':sha(ROOT/'router.py'),'route_inputs':'public clk input port and original specification prose only',
              'native_primary':'unmodified official pytest+Hypothesis native_case.py',
              'rtl_primary':'lowering plus official vectors; common nonfatal warning policy for all five HCLs, warnings separately retained',
              'end_to_end_denominator':840,'functional_pool_denominator':'measured F_func, reported alongside /840',
              'sampling_temperature':0.7,'sampling_seeds':[SEED+i for i in range(5)],
              'pass_at_k':'unbiased combinatorial estimator from n=5 iid-distribution samples',
              'infra_policy':'retry serially at larger limits; unresolved infrastructure remains unknown, never a scored failure',
              'historical_results':'read-only; reuse requires full canonical request, returned model, candidate SHA256; evaluation additionally requires identical evaluation fingerprint'}
    save(ROOT/'protocol/freeze.json',protocol)
    save(ROOT/'protocol/input_hashes.json',{str(p.relative_to(ROOT)):sha(p) for folder in ['protocol','configs'] for p in (ROOT/folder).rglob('*') if p.is_file() and p.name!='input_hashes.json'})
    print(json.dumps({'population':len(population),'deterministic_generation_jobs_pre_RAG':len(jobs),'strata':strata,'rules_tokens':{k:v['tokens_cl100k'] for k,v in rule_provenance.items()}}))
if __name__=='__main__':main()
