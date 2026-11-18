"""Audit authoritative jobs, distinguishing scored output errors from infrastructure.

Historical directories are inventoried for provenance only: the unified /840
protocol supersedes their smaller cohorts. No model call or evaluation here.
"""
from __future__ import annotations
import collections, re
from common import *

INFRA_TEXT = re.compile(r'No space left on device|Cannot allocate memory|out of memory|'
    r'command not found|No such file or directory.*(?:iverilog|verilator)|'
    r'ModuleNotFoundError: No module named [\x27\"](?:pyhdl_eval|pytest|hypothesis)|'
    r'INTERNALERROR>|Fatal Python error: Aborted|LLVM ERROR|Connection (?:reset|refused)', re.I)

def registry():
    jobs = {}
    for path in sorted((ROOT/'configs').glob('*_jobs.json')):
        for j in load(path):
            if j.get('key') and not j['key'].startswith('calibration/'):
                if j['key'] in jobs:
                    assert jobs[j['key']]['request_sha256'] == j['request_sha256']
                jobs[j['key']] = j
    return jobs

def read(path):
    return load(path) if path.exists() else {}

def retry_evidence(jobs):
    rows=[]
    parents={result_dir(j).parent for j in jobs.values() if j.get('kind')!='contract'}
    for parent in sorted(parents):
        for folder in sorted(parent.glob('*.infra_attempt_*')):
            p=folder/'result.json'
            if not p.exists():continue
            relative=folder.relative_to(ROOT/'evaluation/cases').as_posix()
            key=relative.rsplit('.infra_attempt_',1)[0]
            if key not in jobs:continue
            old=load(p);current=read(result_dir(jobs[key])/'result.json')
            rows.append({'key':key,'archived_attempt':relative,
                'archived_outcome':old.get('outcome'),
                'archived_infrastructure_error':old.get('infrastructure_error'),
                'final_outcome':current.get('outcome'),
                'final_infrastructure_error':current.get('infrastructure_error'),
                'candidate_nonconvergence_evidence':bool(current.get('candidate_nonconvergence')),
                'resolved':bool(current) and not current.get('infrastructure_error')})
    withdrawn=[]
    p=ROOT/'protocol/withdrawn_output_cap_recovery.json'
    if p.exists():
        record=load(p);key=record['job_key']
        for a in sorted((run_dir({'key':key})/'attempts').glob('*.json')):
            r=load(a)
            withdrawn.append({'key':key,'attempt_file':str(a.relative_to(ROOT)),
                'http_status':r.get('http_status',r.get('status')),
                'billing_unknown':r.get('billing_unknown',False),
                'scored':False,'reason':record['reason']})
    csv_write(ROOT/'analysis/engineering_evaluation_retry_history.csv',rows)
    csv_write(ROOT/'analysis/engineering_withdrawn_diagnostic_attempts.csv',withdrawn)
    unique={r['key']:r for r in rows}
    return {'archived_evaluation_attempts':len(rows),'evaluation_retry_jobs':len(unique),
        'evaluation_retry_final_outcomes':dict(collections.Counter(r['final_outcome'] for r in unique.values())),
        'evaluation_retry_jobs_unresolved':sum(not r['resolved'] for r in unique.values()),
        'withdrawn_diagnostic_attempts':len(withdrawn),
        'withdrawn_diagnostic_http_statuses':dict(collections.Counter(str(r['http_status']) for r in withdrawn)),
        'withdrawn_diagnostic_billing_unknown':sum(r['billing_unknown'] for r in withdrawn)}

def audit():
    jobs=registry(); rows=[]; failed=[]; network=[]; physical=collections.Counter()
    for key,j in sorted(jobs.items()):
        d=run_dir(j); g=read(d/'generation.json'); response=read(d/'response.json')
        e=read(result_dir(j)/'result.json'); issues=[]; status=g.get('status','missing')
        attempts=[load(p) for p in (d/'attempts').glob('*.json')]
        for a in attempts:
            code=a.get('http_status',a.get('status'));physical[str(code)]+=1
            if code != 200:
                network.append({'key':key,'http_status':code,'error':a.get('error',''),
                    'eventually_has_response':bool(response),'generation_status':status,
                    'billing_unknown':a.get('billing_unknown',False)})
        contract=j.get('kind')=='contract'
        if not response: issues.append('missing_response')
        if not g and response: issues.append('missing_generation_receipt')
        if response and response.get('model') != j['model']: issues.append('wrong_model')
        if status=='ready' and not (d/'candidate.py').exists():issues.append('missing_source')
        if status=='ready' and (d/'candidate.py').exists() and sha(d/'candidate.py')!=g.get('source_sha256'):
            issues.append('source_hash_mismatch')
        if not contract:
            if not e: issues.append('missing_official_evaluation')
            elif e.get('infrastructure_error'): issues.append('unresolved_evaluation_infrastructure')
            elif e.get('candidate_nonconvergence'): pass # retained candidate-only structural/delta evidence
            elif e and not e.get('native_pass'):
                nr=e.get('native') or {}
                if nr.get('returncode',0)<0 or nr.get('returncode') in (124,137):
                    issues.append('unattributed_native_signal_or_timeout')
            if e and e.get('native_pass') and not e.get('rtl_pass'):
                rr=e.get('rtl') or {}
                if rr.get('returncode',0)<0 or rr.get('returncode') in (124,137):
                    issues.append('unattributed_rtl_signal_or_timeout')
            # Inspect only the final authoritative logs, never archived attempts.
            if e and not e.get('rtl_pass') and not e.get('candidate_nonconvergence'):
                for lp in [result_dir(j)/'rtl/pytest.log',ROOT/'evaluation/native/cases'/key/'pytest.log']:
                    if lp.exists():
                        match=INFRA_TEXT.search(lp.read_text(encoding='utf-8',errors='replace'))
                        if match:issues.append('log_review:'+match.group(0))
        finish=(response.get('choices') or [{}])[0].get('finish_reason')
        reason=g.get('error','')
        row={'key':key,'model':j['model'],'language':j.get('language'),
             'arm':j['arm'],'kind':'contract' if contract else 'candidate',
             'generation_status':status,'generation_error':reason,'finish_reason':finish,
             'outcome':e.get('outcome','not_applicable' if contract else 'missing'),
             'c0_pass':e.get('c0_pass'),'native_pass':e.get('native_pass'),
             'rtl_pass':e.get('rtl_pass'),'candidate_nonconvergence':bool(e.get('candidate_nonconvergence')),
             'issues':';'.join(dict.fromkeys(issues)),
             'response_exists':bool(response),'http_attempts':len(attempts)}
        if contract:
            resolution=read(d/'contract_resolution.json')
            row['contract_resolved']=bool(resolution and (d/'contract.json').exists())
        rows.append(row)
        if issues: failed.append(row)
    history=retry_evidence(jobs)
    summary={'registered_jobs':len(rows),
        'generations':dict(collections.Counter(r['generation_status'] for r in rows)),
        'candidate_outcomes':dict(collections.Counter(r['outcome'] for r in rows if r['kind']=='candidate')),
        'suspect_or_pending_jobs':len(failed),'suspects_by_reason':dict(collections.Counter(s for r in failed for s in r['issues'].split(';'))),
        'transport_attempts':dict(physical),'non_200_attempts':len(network),
        'non_200_attempts_with_eventual_response':sum(r['eventually_has_response'] for r in network),
        'transport_retry_jobs_recovered':len({r['key'] for r in network if r['eventually_has_response']}),
        'transport_retry_jobs_unresolved':len({r['key'] for r in network if not r['eventually_has_response']}),
        'registered_billing_unknown_attempts':sum(r['billing_unknown'] for r in network),
        **history,
        'output_errors':dict(collections.Counter(r['generation_error'] for r in rows if r['generation_status']=='output_failure')),
        'scope':'All registered physical jobs in unified_dac_experiments_840; historical smaller cohorts are superseded.',
        'audited_utc':time.time()}
    csv_write(ROOT/'analysis/engineering_audit_jobs.csv',rows)
    csv_write(ROOT/'analysis/engineering_audit_suspects.csv',failed)
    csv_write(ROOT/'analysis/engineering_audit_network_attempts.csv',network)
    save(ROOT/'analysis/engineering_audit_summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False))
    print(json.dumps({'suspects':failed[:25]},ensure_ascii=False))

if __name__=='__main__':audit()
