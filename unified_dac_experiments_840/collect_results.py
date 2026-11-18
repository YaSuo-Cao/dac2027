"""Archive only the current completed batch; retain all its retry evidence."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'output'

def main():
    queue=json.loads((ROOT/'configs/evaluation_queue.json').read_text());paths=set()
    for j in queue:
        for category in ['cases','native/cases','adjudication']:
            path=(OUT/category/j['key']).resolve()
            if OUT.resolve() not in path.parents:raise RuntimeError('Unsafe result path')
            if path.exists():paths.add(path)
            paths.update(path.parent.glob(path.name+'.infra_attempt_*'))
    for name in ['progress.json','complete.json','blocked.json','adjudication_summary.json','native_delta_observer_validation.json']:
        if (OUT/name).exists():paths.add(OUT/name)
    manifest={'job_keys':[j['key'] for j in queue],'archived_roots':[str(p.relative_to(ROOT)) for p in sorted(paths)]}
    (OUT/'collection_manifest.json').write_text(json.dumps(manifest,indent=2));paths.add(OUT/'collection_manifest.json')
    with tarfile.open(ROOT/'results.tar.gz','w:gz') as archive:
        for path in sorted(paths):archive.add(path,arcname=str(path.relative_to(ROOT)))
    print(json.dumps({'archived_jobs':len(queue),'archive_bytes':(ROOT/'results.tar.gz').stat().st_size}))

if __name__=='__main__':main()
