"""Freeze and verify final experiment-1 inputs before further model calls."""
from common import *
from router import route
import remote, collections

def validate():
    jobs=load(ROOT/'configs/exp1_jobs.json');requests=load(ROOT/'configs/exp1_requests.json')
    population=load(ROOT/'configs/population.json');public=load(ROOT/'configs/public_configurations.json')
    assert len(population)==840 and len({p['instance'] for p in population})==840
    assert len(jobs)==len(requests)==2520
    assert collections.Counter(j['arm'] for j in jobs)=={'Direct':840,'Gen':840,'FullDocRAG':840}
    for j in jobs:
        req=requests[j['key']]
        assert req['model']==MODEL and all(req[k]==v for k,v in PARAMS.items())
        assert j['request_sha256']==canonical(req)
        assert 'BCD_GUARD' not in json.dumps(req) and 'KNOWN SPECIFICATION/REFERENCE DISPUTE' not in json.dumps(req)
        assert req['messages'][1]['content'].count('Answer:')>=3
    for p in population:
        spec=(ROOT/'protocol/specifications'/(p['task']+'.txt')).read_text(encoding='utf-8')
        assert route(public[p['task']][0]['ports'],spec)==p['interface_route']
    assert load(ROOT/'analysis/calibration.json')['passed']
    fp=remote.fingerprint();assert all(r['evaluation_fingerprint']==fp['sha256'] for r in load(ROOT/'analysis/calibration.json')['results'])
    assert sha(ROOT/'runtime/native_case.py')==sha(PHASE1/'runtime/native_case.py')
    files=[ROOT/'configs/exp1_jobs.json',ROOT/'configs/exp1_requests.json',ROOT/'configs/population.json',
           ROOT/'configs/public_configurations.json',ROOT/'protocol/freeze.json',ROOT/'router.py',ROOT/'corpus/freeze.json',
           ROOT/'corpus/records.json',ROOT/'corpus/source_manifest.json',ROOT/'corpus/file_inventory.json',ROOT/'corpus/retrieval_ledger.json']
    files+=list((ROOT/'protocol').glob('L_*.txt'))+list((ROOT/'protocol/specifications').glob('*.txt'))+list((ROOT/'runtime').glob('*.py'))
    hashes={p.relative_to(ROOT).as_posix():sha(p) for p in files}
    frozen=ROOT/'protocol/experiment1_final_freeze.json'
    value={'population':840,'requests':2520,'model':MODEL,'evaluation_fingerprint':fp['sha256'],
           'input_hashes':hashes,'input_hashes_sha256':canonical(hashes),'calibration_fixtures':load(ROOT/'analysis/calibration.json')['fixtures']}
    if frozen.exists():assert load(frozen)==value,'Frozen experiment-1 input changed'
    else:save(frozen,value)
    save(ROOT/'protocol/input_hashes.json',hashes)
    print(json.dumps({'validated':True,'population':840,'requests':2520,'freeze_sha256':sha(frozen),'runtime':fp['sha256']}),flush=True)

if __name__=='__main__':validate()
