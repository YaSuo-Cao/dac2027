"""Read-only public checksum, cohort, and table verification."""
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent


def csv_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def number(row, name):
    value = row[name]
    return float(value == 'True') if value in ('True', 'False') else float(value)


def main():
    manifest = json.loads((BASE / 'MANIFEST.json').read_text())
    for rel, expected in manifest['files_sha256'].items():
        path = (BASE / rel).resolve()
        assert BASE in path.parents
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, rel
    root = BASE / 'unified_dac_experiments_840'
    analysis = root / 'analysis'
    pop = json.loads((root / 'configs/population.json').read_text(encoding='utf-8-sig'))
    assert len(pop) == 840 and len({r['task'] for r in pop}) == 168
    assert Counter(r['language'] for r in pop) == dict.fromkeys(['pyrtl', 'myhdl', 'amaranth', 'migen', 'pymtl3'], 168)
    for filename, total in [('exp1_instance_scores.csv', 2520), ('exp2_instance_scores.csv', 5040),
                            ('exp3_instance_scores.csv', 11760), ('exp4_instance_scores.csv', 16800)]:
        assert len(csv_rows(analysis / filename)) == total, filename
    scores = csv_rows(analysis / 'exp4_instance_scores.csv')
    for row in csv_rows(analysis / 'table_vii_viii.csv'):
        selected = [r for r in scores if r['model'] == row['model'] and r['arm'] == row['method']
                    and (row['language'] == 'All' or r['language'] == row['language'])]
        assert len(selected) == int(row['n'])
        assert sum(r['c0_pass'] == 'False' for r in selected) == int(row['c0_errors'])
        for metric, count in [('native_pass', 'native_passed'), ('rtl_pass', 'rtl_passed')]:
            assert sum(number(r, metric) for r in selected) == int(row[count])
    scores = csv_rows(analysis / 'exp3_instance_scores.csv')
    for row in csv_rows(analysis / 'table_vi.csv'):
        selected = [r for r in scores if r['method'] == row['method']]
        assert len(selected) == 840
        for metric, count in [('native_pass', 'native_expected_passed'), ('rtl_pass', 'rtl_expected_passed')]:
            assert abs(sum(number(r, metric) for r in selected) - float(row[count])) < 1e-7
    expected = json.loads((root / 'configs/evaluation_fingerprint.json').read_text())
    for name, sha in expected['runtime'].items():
        assert hashlib.sha256((root / 'runtime' / name).read_bytes()).hexdigest() == sha, name
    records = 0
    for bundle in sorted((BASE / 'frozen_data').glob('*.jsonl.gz')):
        with gzip.open(bundle, 'rt', encoding='utf-8') as handle:
            for line in handle:
                row = json.loads(line)
                assert hashlib.sha256(row['text'].encode()).hexdigest() == row['public_sha256']
                target = (BASE / row['path']).resolve()
                assert BASE in target.parents
                records += 1
    print(json.dumps({'verified': True, 'files': len(manifest['files_sha256']), 'evidence_records': records,
                      'population': 840, 'original_runtime_hashes_match': True, 'network_calls': 0, 'simulations': 0}))


if __name__ == '__main__':
    main()
