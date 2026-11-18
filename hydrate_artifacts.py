"""Expand anonymous evidence bundles without models, network, or simulation."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--into', type=Path, default=BASE)
    args = parser.parse_args()
    root = args.into.resolve()
    if root != BASE:
        raise SystemExit('Run from an extracted copy; destination must be this artifact directory')
    count = 0
    for bundle in sorted((BASE / 'frozen_data').glob('*.jsonl.gz')):
        with gzip.open(bundle, 'rt', encoding='utf-8') as handle:
            for line in handle:
                row = json.loads(line)
                dest = (root / row['path']).resolve()
                if root not in dest.parents:
                    raise ValueError('Invalid evidence path')
                data = row['text'].encode('utf-8')
                assert hashlib.sha256(data).hexdigest() == row['public_sha256']
                if dest.exists():
                    if hashlib.sha256(dest.read_bytes()).hexdigest() != row['public_sha256']:
                        raise ValueError('Existing local evidence differs: ' + row['path'])
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                count += 1
    # Per-run requests and raw outputs duplicate the compact frozen stores.
    experiment = root / 'unified_dac_experiments_840'
    for config in sorted((experiment / 'configs').glob('*_requests.json')):
        for key, request in json.loads(config.read_text(encoding='utf-8-sig')).items():
            folder = experiment / 'runs' / key
            if not (folder / 'generation.json').exists():
                continue
            path = folder / 'request.json'
            if not path.exists():
                path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
            response = folder / 'response.json'
            raw = folder / 'raw_output.txt'
            if response.exists() and not raw.exists():
                obj = json.loads(response.read_text(encoding='utf-8-sig'))
                choices = obj.get('choices') or []
                if choices:
                    raw.write_text(choices[0].get('message', {}).get('content') or '', encoding='utf-8')
    print(json.dumps({'expanded_records': count, 'network_calls': 0, 'simulations': 0}))


if __name__ == '__main__':
    main()
