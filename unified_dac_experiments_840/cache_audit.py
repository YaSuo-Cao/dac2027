"""Only full payload identity permits historical reuse; never accept model aliases."""
from __future__ import annotations
import argparse, collections, shutil
from common import *

def index():
    candidates=[]
    for name in ['task_a_20261109','task_b_20261109','task_c_20261109','task_d_20261109']:
        candidates.extend((WORK/name).rglob('request.json'))
    for name in ['hcl_full168_phase1_20261022','hcl_full168_phase2_incremental_20261022']:
        candidates.extend((HISTORY/name/'runs').rglob('request.json'))
    found={};counts=collections.Counter()
    for p in candidates:
        try:
            req=load(p);model=req.get('model')
            if model!=MODEL:counts['excluded_model']+=1;continue
            response=p.with_name('response.json')
            if not response.exists():counts['missing_response']+=1;continue
            value=load(response)
            if value.get('model')!=MODEL or not value.get('choices'):counts['wrong_returned_model']+=1;continue
            generation=p.with_name('generation.json');candidate=p.with_name('candidate.py')
            gen=load(generation) if generation.exists() else {}
            if gen.get('status')=='ready' and (not candidate.exists() or sha(candidate)!=gen.get('source_sha256')):
                counts['candidate_hash_mismatch']+=1;continue
            found.setdefault(canonical(req),[]).append(str(p.parent));counts['valid_payload_response']+=1
        except (ValueError,OSError):counts['unreadable']+=1
    save(ROOT/'analysis/cache_index.json',found);save(ROOT/'analysis/cache_scan.json',dict(counts))
    return found

def audit(stage='exp1'):
    cache=load(ROOT/'analysis/cache_index.json') if (ROOT/'analysis/cache_index.json').exists() else index()
    jobs=load(ROOT/'configs'/(stage+'_jobs.json'));requests=load(ROOT/'configs'/(stage+'_requests.json'))
    rows=[]
    for job in jobs:
        request=requests[job['key']];identity=canonical(request);assert identity==job['request_sha256']
        target=run_dir(job);prior=cache.get(identity,[])
        state='new_request'
        if (target/'response.json').exists():state='current_response'
        elif prior:
            source=Path(prior[0]);target.mkdir(parents=True,exist_ok=True)
            for name in ['request.json','response.json','generation.json','candidate.py','raw_output.txt']:
                if (source/name).exists():shutil.copyfile(source/name,target/name)
            save(target/'cache_provenance.json',{'source':str(source),'canonical_request_sha256':identity,
                 'response_sha256':sha(source/'response.json'),'candidate_sha256':sha(source/'candidate.py') if (source/'candidate.py').exists() else None,
                 'evaluation_reused':False,'evaluation_reason':'new unified gate/runtime fingerprint requires official reevaluation'})
            state='exact_payload_reused'
        rows.append({**job,'cache_state':state,'cache_source':prior[0] if prior else ''})
    csv_write(ROOT/'analysis'/(stage+'_request_queue.csv'),rows)
    summary={'jobs':len(rows),'states':dict(collections.Counter(r['cache_state'] for r in rows)),
             'by_arm':{a:dict(collections.Counter(r['cache_state'] for r in rows if r['arm']==a)) for a in sorted({r['arm'] for r in rows})}}
    save(ROOT/'analysis'/(stage+'_cache_audit.json'),summary);print(json.dumps(summary))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',default='exp1');p.add_argument('--reindex',action='store_true');a=p.parse_args()
    if a.reindex:index()
    audit(a.stage)
