"""Read-only final consistency audit; publishes no incomplete-stage scores."""
import collections,math
from common import *
from remote import fingerprint

def main():
    markers=[ROOT/'progress'/f'experiment{i}_complete.json' for i in range(1,5)]
    if not all(p.exists() and load(p).get('complete') for p in markers):
        raise RuntimeError('All four full-population modules must complete before the final audit')
    population=load(ROOT/'configs/population.json')
    assert len(population)==840 and len({r['instance'] for r in population})==840
    assert collections.Counter(r['language'] for r in population)==dict.fromkeys(LANGS,168)
    assert all(n==5 for n in collections.Counter(r['task'] for r in population).values())
    current=fingerprint()['sha256'];frozen=load(ROOT/'protocol/experiment1_final_freeze.json')
    assert current==frozen['evaluation_fingerprint']
    for name,digest in frozen['input_hashes'].items():assert sha(ROOT/name)==digest,name
    ledger=load(ROOT/'analysis/candidate_ledger.json');physical=collections.Counter();unknown=0
    by_key={row['job_key']:row for row in ledger};assert len(by_key)==len(ledger)
    exp1_requests=load(ROOT/'configs/exp1_requests.json')
    sampling_bases={(j['instance'],j['arm']):exp1_requests[j['key']] for j in load(ROOT/'configs/exp1_jobs.json') if j['arm'] in ('Direct','Gen')}
    sampling_jobs=load(ROOT/'configs/exp3_jobs.json');sampling_by_key={j['key']:j for j in sampling_jobs}
    sample_receipts=collections.defaultdict(set);sample_cache_reuses=0;sample_missing_receipt_ids=0
    for row in ledger:
        directory=ROOT/'runs'/row['job_key'];request=load(directory/'request.json');response=load(directory/'response.json')
        assert canonical(request)==row['request_sha256'] and canonical(request['messages'])==row['prompt_sha256']
        assert request['model']==response['model']==row['model_requested']==row['model_returned']
        assert sha(directory/'response.json')==row['response_sha256']
        assert request['top_p']==.95 and request['max_tokens']==4096 and request['reasoning_effort']=='none'
        sample=row['job_key'].startswith('exp3/')
        assert request['temperature']==(.7 if sample else .2)
        assert request['seed'] in range(SEED,SEED+5) if sample else request['seed']==SEED
        provenance_path=directory/'cache_provenance.json'
        if provenance_path.exists():
            provenance=load(provenance_path)
            assert provenance['canonical_request_sha256']==row['request_sha256']
            assert provenance['response_sha256']==row['response_sha256']
            if row['generation_status']=='ready' and provenance.get('candidate_sha256'):
                assert provenance['candidate_sha256']==row['candidate_sha256']
        if sample:
            j=sampling_by_key[row['job_key']];group=(j['instance'],j['arm'])
            assert request=={**sampling_bases[group],'temperature':.7,'seed':SEED+j['sample']-1}
            assert row['request_sha256']==j['request_sha256']
            sample_cache_reuses+=int(provenance_path.exists())
            receipt=response.get('id')
            if receipt:
                assert receipt not in sample_receipts[group], (group,receipt)
                sample_receipts[group].add(receipt)
            else:sample_missing_receipt_ids+=1
        if row['language']!='shared':
            result=load(ROOT/'evaluation/cases'/row['job_key']/'result.json')
            assert not result.get('infrastructure_error') and result['evaluation_fingerprint']==current
            assert int(result['rtl_pass'])<=int(result['native_pass'])<=int(result['c0_pass'])
            if row['generation_status']=='ready':assert sha(directory/'candidate.py')==row['candidate_sha256']==result['source_sha256']
        attempts=[load(p) for p in (directory/'attempts').glob('*.json')]
        physical.update(a.get('http_status') for a in attempts)
        unknown+=sum(bool(a.get('billing_unknown')) for a in attempts)
        expected=(response.get('usage',{}).get('prompt_tokens_details') or {}).get('cached_tokens',response.get('usage',{}).get('prompt_cache_hit_tokens'))
        assert row['cached_tokens']==expected
    exp1=load(ROOT/'analysis/exp1_instance_scores.json')
    exp2=load(ROOT/'analysis/exp2_instance_scores.json')
    exp3=load(ROOT/'analysis/exp3_instance_scores.json')
    exp4=load(ROOT/'analysis/exp4_instance_scores.json')
    assert len(exp1)==2520 and len(exp2)==5040 and len(exp3)==11760 and len(exp4)==16800
    for rows,field in [(exp1,'arm'),(exp2,'method'),(exp3,'method')]:
        assert all(n==840 for n in collections.Counter(r[field] for r in rows).values())
        for method in {r[field] for r in rows}:
            subset=[r for r in rows if r[field]==method]
            assert len({r['instance'] for r in subset})==840
    models={MODEL,'qwen3.8-flash','glm-5.3-flash','claude-haiku-5-5'}
    assert {r['model'] for r in exp4}==models
    assert all(n==840 for n in collections.Counter((r['model'],r['arm']) for r in exp4).values())
    assert len(sampling_jobs)==len(sampling_by_key)==8400 and sampling_by_key.keys()<=by_key.keys()
    groups=collections.defaultdict(list)
    for j in sampling_jobs:groups[j['instance'],j['arm']].append(j['sample'])
    assert len(groups)==1680 and all(sorted(v)==[1,2,3,4,5] for v in groups.values())
    for rows,field in [(exp2,'method'),(exp3,'method'),(exp4,'arm')]:
        grouped=collections.defaultdict(list)
        for r in rows:grouped[r.get('model',MODEL),r[field]].append(r)
        for _,subset in grouped.items():
            if 'Pass@' in subset[0].get('method',''):continue
            candidates=sum(r['total'] for r in subset)
            shared={r['task']:r['contract_tokens'] for r in subset if r.get('contract_tasks')}
            assert math.isclose(sum(r['amortized_tokens'] for r in subset),candidates+sum(shared.values()),rel_tol=1e-12)
            assert math.isclose(sum(r['lazy_tokens'] for r in subset),candidates+sum(r['contract_tokens'] for r in subset),rel_tol=1e-12)
    source_manifest={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'analysis').glob('*') if p.suffix in ['.csv','.json'] and p.name!='final_audit.json'}
    result={'complete':True,'all_checks_passed':True,'population':840,'tasks':168,'hcls':LANGS,'models':sorted(models),
        'evaluation_fingerprint':current,'scored_rows':{'experiment1':len(exp1),'experiment2':len(exp2),'experiment3':len(exp3),'experiment4':len(exp4)},
        'physical_jobs':len(ledger),'http_status_counts':dict(physical),'billing_unknown_attempts':unknown,
        'sampling_cache_reuses':sample_cache_reuses,'sampling_missing_receipt_ids':sample_missing_receipt_ids,
        'infra_unresolved':0,'claude_included':True,'analysis_file_sha256':source_manifest,'audited_utc':time.time()}
    save(ROOT/'analysis/final_audit.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='analysis_file_sha256'},ensure_ascii=False))

if __name__=='__main__':main()
