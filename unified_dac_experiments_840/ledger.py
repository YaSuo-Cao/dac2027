"""Common schema for every physical candidate and logical scoring ledger."""
from __future__ import annotations
import collections
from common import *

def refresh():
    jobs={}
    for path in sorted((ROOT/'configs').glob('*_jobs.json')):
        for j in load(path):
            if 'key' in j:jobs[j['key']]=j
    rows=[]
    for key,j in sorted(jobs.items()):
        if key.startswith('calibration/'):continue
        directory=run_dir(j);gp=directory/'generation.json';rp=result_dir(j)/'result.json'
        gen=load(gp) if gp.exists() else {};result=load(rp) if rp.exists() else {}
        request=load(directory/'request.json') if (directory/'request.json').exists() else {}
        response=load(directory/'response.json') if (directory/'response.json').exists() else {}
        usage=response.get('usage') or {};provenance=load(directory/'cache_provenance.json') if (directory/'cache_provenance.json').exists() else {}
        attempts=[load(p) for p in (directory/'attempts').glob('*.json')]
        row={'schema_version':'unified840.candidate.v1','population_n':840,'task':j['task'],
             'language':j.get('language'),'instance':j.get('instance'),'model_requested':j['model'],
             'model_returned':response.get('model'),'arm':j['arm'],'job_key':key,
             'request_sha256':canonical(request) if request else j.get('request_sha256'),
             'prompt_sha256':canonical(request['messages']) if request else j.get('prompt_sha256'),
             'response_sha256':sha(directory/'response.json') if response else None,
             'candidate_sha256':gen.get('source_sha256'),'evaluation_fingerprint':result.get('evaluation_fingerprint'),
             'temperature':request.get('temperature'),'top_p':request.get('top_p'),'seed':request.get('seed'),
             'generation_status':gen.get('status','pending'),'c0_pass':result.get('c0_pass'),
             'q_native_pass':result.get('native_pass'),'c_rtl_pass':result.get('rtl_pass'),
             'native_evaluated':result.get('native_evaluated'),'rtl_evaluated':result.get('rtl_evaluated'),
             'infrastructure_error':result.get('infrastructure_error'),'outcome':result.get('outcome'),
             'input_tokens':usage.get('prompt_tokens'),'output_tokens':usage.get('completion_tokens'),
             'cached_tokens':(usage.get('prompt_tokens_details') or {}).get('cached_tokens',usage.get('prompt_cache_hit_tokens')),
             'total_tokens':usage.get('total_tokens'),'reused_exact_payload':bool(provenance),
             'new_http_attempts':len(attempts),'new_http_200_responses':sum(a.get('http_status')==200 for a in attempts),
             'new_billing_unknown_attempts':sum(bool(a.get('billing_unknown')) for a in attempts),
             'historical_source':provenance.get('source'),'probe_seconds':result.get('probe_seconds'),
             'native_seconds':result.get('native_seconds'),'rtl_seconds':result.get('rtl_seconds')}
        rows.append(row)
    csv_write(ROOT/'analysis/candidate_ledger.csv',rows);save(ROOT/'analysis/candidate_ledger.json',rows)
    summary={'population':840,'jobs_registered':len(rows),'generation_status':dict(collections.Counter(r['generation_status'] for r in rows)),
             'official_evaluations':sum(r['outcome'] is not None for r in rows),
             'infra_unresolved':sum(bool(r['infrastructure_error']) for r in rows),
             'no_partial_percentages_reported':True}
    save(ROOT/'analysis/progress_summary.json',summary);return summary
if __name__=='__main__':print(json.dumps(refresh()))
