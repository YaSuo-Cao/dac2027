"""Local Docker adapter replacing author-specific SSH deployment details."""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
from common import *


def fingerprint():
    files = {p.name: sha(p) for p in (ROOT / 'runtime').glob('*.py')}
    value = {'image': IMAGE, 'runtime': files, 'hypothesis_seed': SEED,
             'public_config_sha256': sha(ROOT / 'configs/public_configurations.json'),
             'native_warning_policy': 'unchanged official',
             'rtl_warning_policy': 'same nonfatal warnings for all five HCLs; syntax/functional failures retained',
             'candidate_network': False}
    value['sha256'] = canonical(value)
    frozen = ROOT / 'configs/evaluation_fingerprint.json'
    if frozen.exists() and load(frozen)['sha256'] != value['sha256']:
        raise RuntimeError('Runtime differs from the frozen evaluation fingerprint')
    if not frozen.exists():
        save(frozen, value)
    return value


def execute(jobs):
    fingerprint()
    pending = []
    for job in jobs:
        if not (run_dir(job) / 'generation.json').exists():
            continue
        result = result_dir(job) / 'result.json'
        if result.exists() and not load(result).get('infrastructure_error'):
            continue
        pending.append(job)
    if not pending:
        return
    if not (DATA / 'dataset').is_dir():
        raise RuntimeError('Set PARAROUTE_DATASET to the PyHDL-Eval root')
    stage = ROOT / 'local_evaluation_work'
    stage.mkdir(exist_ok=True)
    for name in ('adjudicate_in_container.py', 'collect_results.py'):
        shutil.copyfile(ROOT / name, stage / name)
    shutil.copytree(ROOT / 'runtime', stage / 'runtime', dirs_exist_ok=True)
    (stage / 'configs').mkdir(exist_ok=True)
    save(stage / 'configs/evaluation_queue.json', pending)
    for name in ('evaluation_fingerprint.json', 'public_configurations.json'):
        shutil.copyfile(ROOT / 'configs' / name, stage / 'configs' / name)
    for job in pending:
        dest = stage / 'runs/cases' / job['key']
        dest.mkdir(parents=True, exist_ok=True)
        for name in ('candidate.py', 'generation.json'):
            source = run_dir(job) / name
            if source.exists():
                shutil.copyfile(source, dest / name)
    output = ROOT / 'evaluation'
    output.mkdir(exist_ok=True)
    command = ['docker', 'run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--pids-limit', '1024', '--memory', '6g', '--cpus', '2',
               '--tmpfs', '/tmp:rw,nosuid,nodev,size=1g', '-e', 'HOME=/tmp',
               '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONPATH=/dataset:/work/runtime',
               '-v', str(stage.resolve()) + ':/work:ro', '-v', str(output.resolve()) + ':/out:rw',
               '-v', str(DATA.resolve()) + ':/dataset:ro', '-w', '/tmp', IMAGE]
    process = subprocess.run(command + ['python', '-u', '/work/runtime/evaluate.py'])
    if process.returncode:
        subprocess.run(command + ['python', '-u', '/work/adjudicate_in_container.py'], check=True)
    for job in pending:
        result = result_dir(job) / 'result.json'
        if not result.exists() or load(result).get('infrastructure_error'):
            raise RuntimeError('Unresolved infrastructure; no score imputed: ' + job['key'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', default='exp1')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    jobs = load(ROOT / 'configs' / (args.stage + '_jobs.json'))
    execute(jobs[:args.limit] if args.limit else jobs)


if __name__ == '__main__':
    main()
