"""Publish the saved Claude Anthropic-Messages base cross-model ledger.

The 1,680 Direct/Gen responses and official results are immutable.  This
report is deliberately separate from the full routed table until Claude's
repair arms have their own generated candidates.
"""
from __future__ import annotations
import json, statistics, time
from pathlib import Path
from common import *

MODEL_CLAUDE = 'claude-haiku-5-5'

def main():
    jobs = load(ROOT/('configs/cross_'+MODEL_CLAUDE+'_jobs.json'))
    records = []
    for j in jobs:
        g = load(run_dir(j)/'generation.json')
        e = load(result_dir(j)/'result.json')
        u = g.get('usage') or {}
        records.append({
            'model': MODEL_CLAUDE, 'task': j['task'], 'language': j['language'],
            'arm': j['arm'], 'key': j['key'],
            'generation_ready': g.get('status') == 'ready',
            'generation_error': g.get('error',''),
            'c0_pass': bool(e.get('c0_pass')), 'native_pass': bool(e.get('native_pass')),
            'rtl_pass': bool(e.get('rtl_pass')),
            'input_tokens': u.get('prompt_tokens'),
            'output_tokens': u.get('completion_tokens'),
            'cached_tokens': (u.get('prompt_tokens_details') or {}).get('cached_tokens', 0),
            'total_tokens': u.get('total_tokens'),
        })
    assert len(records) == 1680
    rows = []
    for lang in LANGS + ['All']:
        for arm in ['Direct','Gen']:
            x = [r for r in records if r['arm'] == arm and (lang == 'All' or r['language'] == lang)]
            n = len(x)
            row = {
                'model': MODEL_CLAUDE, 'language': lang, 'method': arm, 'n': n,
                'parse_failures': sum(not r['generation_ready'] for r in x),
                'c0_passed': sum(r['c0_pass'] for r in x),
                'native_passed': sum(r['native_pass'] for r in x),
                'rtl_passed': sum(r['rtl_pass'] for r in x),
            }
            for metric in ['c0','native','rtl']:
                row[metric+'_percent'] = 100 * row[metric+'_passed'] / n
            for field in ['input_tokens','output_tokens','cached_tokens','total_tokens']:
                values = [r[field] for r in x if r[field] is not None]
                row[field+'_mean'] = sum(values) / len(values) if len(values) == n else None
                row[field+'_sum'] = sum(values) if len(values) == n else None
            rows.append(row)
    csv_write(ROOT/'analysis/claude_haiku_base_instance_scores.csv', records)
    csv_write(ROOT/'analysis/claude_haiku_base_summary.csv', rows)
    save(ROOT/'analysis/claude_haiku_base_instance_scores.json', records)
    save(ROOT/'analysis/claude_haiku_base_summary.json', rows)
    cost_rows = []
    for arm in ['Direct','Gen']:
        x = [r for r in records if r['arm'] == arm]
        cost_rows.append({
            'model': MODEL_CLAUDE, 'method': arm, 'instances': len(x),
            'calls': len(x),
            'input_tokens': sum(r['input_tokens'] or 0 for r in x),
            'output_tokens': sum(r['output_tokens'] or 0 for r in x),
            'cached_tokens': sum(r['cached_tokens'] or 0 for r in x),
            'total_tokens': sum(r['total_tokens'] or 0 for r in x),
            'parse_failures': sum(not r['generation_ready'] for r in x),
            'official_evaluations': len(x),
        })
    csv_write(ROOT/'analysis/claude_haiku_base_cost.csv', cost_rows)
    save(ROOT/'analysis/claude_haiku_base_cost.json', cost_rows)
    lines = [
        '# Claude Haiku 5.5 — saved Anthropic Messages base ledger', '',
        'The confirmed Anthropic Messages transport returned model `claude-haiku-5-5`. '
        'This report uses the immutable 840-instance cross-family population and the '
        'saved `Direct`/`Gen` responses; no score is imputed for the seven parse failures.', '',
        '| Language | Method | n | Parse failures | C0 pass | Native pass | RTL pass | Mean input tok | Mean output tok | Mean total tok |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for r in rows:
        lines.append('| {language} | {method} | {n} | {parse_failures} | {c0_passed} ({c0_percent:.2f}%) | '
                     '{native_passed} ({native_percent:.2f}%) | {rtl_passed} ({rtl_percent:.2f}%) | '
                     '{input_tokens_mean:.1f} | {output_tokens_mean:.1f} | {total_tokens_mean:.1f} |'.format(**r))
    failure_counts = {}
    for r in records:
        if not r['generation_ready']:
            failure_counts[r['generation_error']] = failure_counts.get(r['generation_error'], 0) + 1
    save(ROOT/'analysis/claude_haiku_base_failure_counts.json', failure_counts)
    lines += ['',
        'Seven outputs failed the frozen source parser; their exact error classes are retained '
        'in `claude_haiku_base_failure_counts.json` and each per-job `generation.json`. '
        'All 1,680 jobs have an official evaluation record. The routed repair arms and their '
        'contract costs require separate Claude repair responses and are not represented by this base-only table.',
    ]
    (ROOT/'analysis/claude_haiku_base_report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    save(ROOT/'analysis/model_availability.json', {
        'claude-haiku-5-5': {
            'http_status': 200,
            'protocol': 'anthropic_messages',
            'probe': 'analysis/claude_transport_probe.json',
            'base_population': 840,
            'base_jobs': 1680,
            'base_parse_failures': 7,
            'base_official_evaluations': 1680,
            'included_in_full_routed_denominator': False,
            'full_routed_status': 'pending_repair_responses',
        }
    })
    save(ROOT/'progress/experiment4_claude_base_complete.json', {
        'complete': True, 'model': MODEL_CLAUDE, 'population': 840,
        'jobs': 1680, 'ready': sum(r['generation_ready'] for r in records),
        'parse_failures': sum(not r['generation_ready'] for r in records),
        'official_evaluations': 1680, 'routed_repairs_complete': False,
        'published_utc': time.time(),
    })
    print(json.dumps({'model':MODEL_CLAUDE, 'jobs':len(records),
                      'ready':sum(r['generation_ready'] for r in records),
                      'parse_failures':sum(not r['generation_ready'] for r in records)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
