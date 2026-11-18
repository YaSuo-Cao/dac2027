"""Mock checks for completed-source handoff and incremental evidence archives."""
import json,tarfile,tempfile,threading
from pathlib import Path
import collect_results as collector
import evaluation_stream as streaming
from common import ROOT,save,sha

def main():
    old_root,old_out,old_stream=collector.ROOT,collector.OUT,streaming.ROOT
    with tempfile.TemporaryDirectory(prefix='pararoute_stream_') as tmp:
        base=Path(tmp).resolve();collector.ROOT=base;collector.OUT=base/'output';streaming.ROOT=base
        queue=[{'key':'mock/a'},{'key':'mock/b'}]
        save(base/'configs/evaluation_queue.json',queue)
        for name in ['cases/mock/a/result.json','cases/mock/a.infra_attempt_1/result.json','native/cases/mock/a/failure.json',
                     'cases/mock/b/result.json','cases/unrelated/result.json','build/unused/x.json']:
            save(collector.OUT/name,{'mock':True})
        collector.main()
        with tarfile.open(base/'results.tar.gz') as archive:names=set(archive.getnames())
        assert 'output/cases/mock/a/result.json' in names
        assert 'output/cases/mock/a.infra_attempt_1/result.json' in names
        assert 'output/native/cases/mock/a/failure.json' in names
        assert 'output/cases/mock/b/result.json' in names
        assert not any('unrelated' in n or '/build/' in n for n in names)
        completed=set();seen=[];batches=[];stop=threading.Event()
        def evaluate(jobs):
            assert all(j['key'] in completed for j in jobs)
            seen.extend(j['key'] for j in jobs);batches.append(len(jobs))
        stream=streaming.EvaluationStream('mock',stop,evaluate,minimum=2,maximum=3)
        for n in range(8):
            j={'key':'ready/'+str(n)};completed.add(j['key']);stream.submit(j);stream.submit(j)
        stream.close()
        assert len(seen)==len(set(seen))==8 and all(0<n<=3 for n in batches) and not stop.is_set()
        blocked=threading.Event()
        def fail(_):raise RuntimeError('mock evaluation blocker')
        stream=streaming.EvaluationStream('mock_failure',blocked,fail,minimum=1)
        stream.submit({'key':'blocked'})
        try:stream.close()
        except RuntimeError:pass
        else:raise AssertionError('Evaluation failure must block the parent stage')
        assert blocked.is_set()
    collector.ROOT=old_root;collector.OUT=old_out;streaming.ROOT=old_stream
    result={'all_passed':True,'network_calls':0,'official_evaluations':0,'checks':['only generation-complete jobs handed off',
        'no duplicate evaluation jobs','bounded batch sizes','evaluation error stops new cloud requests',
        'archive retains selected score, native and infrastructure retry evidence','unrelated scores and build folders excluded'],
        'tool_sha256':{name:sha(ROOT/name) for name in ['evaluation_stream.py','collect_results.py','remote.py','generate.py']}}
    save(ROOT/'analysis/stream_evaluation_validation.json',result);print(json.dumps(result))

if __name__=='__main__':main()
