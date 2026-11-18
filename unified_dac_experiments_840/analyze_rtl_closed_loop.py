"""Separate budget-five extension tables; never overwrite the frozen main tables."""
from __future__ import annotations
import argparse, collections
import numpy as np
from common import *
import repair, analyze
from rtl_closed_loop import NAME,OUT,METHODS,MAX_REPAIRS


def records_at(round_index):
    states=load(OUT/f'round_{round_index}_states.json');records=[]
    for s in states:
        jobs=[s['initial']]+[a['job'] for a in s['attempts']]
        r=repair.evaluation(s['accepted']);cost=analyze.per_instance_cost(jobs,MODEL,s['contract_failures'])
        assert cost['calls']==1+len(s['attempts'])<=1+round_index<=5
        evals=[repair.evaluation(j) for j in jobs]
        records.append({'model':MODEL,'method':s['method'],'arm':s['method'],'budget_code_calls':round_index+1,
            'max_repairs':round_index,'task':s['task'],'language':s['language'],'instance':s['instance'],
            'c0_pass':r['c0_pass'],'native_pass':r['native_pass'],'rtl_pass':r['rtl_pass'],
            'selected_key':s['accepted']['key'],'stop_reason':s['stop_reason'],
            'repairs_used':len(s['attempts']),'rtl_feedback_repairs':sum(a['phase']=='rtl' for a in s['attempts']),
            'native_feedback_repairs':sum(a['phase']=='native' for a in s['attempts']),
            'construction_feedback_repairs':sum(a['phase']=='construction' for a in s['attempts']),
            'native_regressions_after_rtl_feedback':sum(a['phase']=='rtl' and not a['native_pass'] for a in s['attempts']),
            'accepted_native_regressions_after_rtl_feedback':sum(a['phase']=='rtl' and a['c0_pass'] and not a['native_pass'] for a in s['attempts']),
            'contract_output_failure':bool(s['contract_failures']),
            'logical_c0_candidate_checks':len(jobs),'logical_native_checks':sum(bool(e.get('native_evaluated')) for e in evals),
            'logical_rtl_checks':sum(bool(e.get('rtl_evaluated')) for e in evals),
            'recorded_probe_seconds':sum(e.get('probe_seconds',0) for e in evals),
            'recorded_native_seconds':sum(e.get('native_seconds',0) for e in evals),
            'recorded_rtl_seconds':sum(e.get('rtl_seconds',0) for e in evals),
            'timing_scope':'Recorded authoritative attempt times only; excludes archived retry overhead',**cost})
    analyze.allocate_joint_contracts(records)
    return records


def summarize(records):
    rows=[]
    for method in METHODS:
        for language in LANGS+['All']:
            x=[r for r in records if r['method']==method and (language=='All' or r['language']==language)]
            assert len(x)==(840 if language=='All' else 168)
            row={'method':method,'language':language,'n':len(x),'budget_code_calls':x[0]['budget_code_calls'],
                'max_repairs':x[0]['max_repairs'],
                **{k+'_passed':sum(r[k+'_pass'] for r in x) for k in ['c0','native','rtl']},
                **{k+'_percent':100*np.mean([r[k+'_pass'] for r in x]) for k in ['c0','native','rtl']},
                'max_actual_code_calls':max(r['calls'] for r in x),
                'mean_code_calls':float(np.mean([r['calls'] for r in x])),
                'mean_calls_including_lazy_contracts':float(np.mean([r['lazy_calls'] for r in x])),
                'mean_calls_including_shared_contracts':float(np.mean([r['amortized_calls'] for r in x])),
                'mean_candidate_input_tokens':analyze.known_mean(r['input'] for r in x),
                'mean_candidate_output_tokens':analyze.known_mean(r['output'] for r in x),
                'mean_candidate_cached_tokens':analyze.known_mean(r['cached'] for r in x),
                'mean_amortized_tokens':analyze.known_mean(r['amortized_tokens'] for r in x),
                'mean_lazy_tokens':analyze.known_mean(r['lazy_tokens'] for r in x),
                'rtl_feedback_repairs':sum(r['rtl_feedback_repairs'] for r in x),
                'native_regressions_after_rtl_feedback':sum(r['native_regressions_after_rtl_feedback'] for r in x),
                'accepted_native_regressions_after_rtl_feedback':sum(r['accepted_native_regressions_after_rtl_feedback'] for r in x),
                'logical_c0_candidate_checks':sum(r['logical_c0_candidate_checks'] for r in x),
                'logical_native_checks':sum(r['logical_native_checks'] for r in x),
                'logical_rtl_checks':sum(r['logical_rtl_checks'] for r in x),
                'recorded_probe_seconds':sum(r['recorded_probe_seconds'] for r in x),
                'recorded_native_seconds':sum(r['recorded_native_seconds'] for r in x),
                'recorded_rtl_seconds':sum(r['recorded_rtl_seconds'] for r in x)}
            rows.append(row)
    return rows


def final_checks(records):
    protocol=load(ROOT/'protocol'/(NAME+'.json'))
    assert protocol['maximum_code_calls']==5 and protocol['maximum_code_repairs']==4
    assert sha(ROOT/'configs/exp1_jobs.json')==protocol['initial_jobs_sha256']
    assert sha(ROOT/'configs/exp1_requests.json')==protocol['initial_requests_sha256']
    assert sha(ROOT/'router.py')==protocol['router_sha256']
    core_audit=load(ROOT/'analysis/final_audit.json')
    core_tables=['exp1_instance_scores.json','exp2_instance_scores.json','exp3_instance_scores.json',
        'exp4_instance_scores.json','table_iv.json','table_v.json','table_vi.json','table_vii_viii.json']
    for name in core_tables:
        key=next(k for k in core_audit['analysis_file_sha256'] if Path(k).name==name)
        assert sha(ROOT/key)==core_audit['analysis_file_sha256'][key], 'Original main table changed: '+name
    states=load(OUT/'round_4_states.json');jobs={}
    for s in states:
        assert len(s['attempts'])<=4
        assert len({a['request_sha256'] for a in s['attempts']})==len(s['attempts'])
        accepted=s['initial']
        for a in s['attempts']:
            j=a['job'];request=load(run_dir(j)/'request.json')
            assert canonical(request)==j['request_sha256']==a['request_sha256']
            response=load(run_dir(j)/'response.json')
            assert response['model']==MODEL
            result=repair.evaluation(j);assert result['evaluation_fingerprint']==protocol['evaluation_fingerprint']
            if a['c0_pass']:accepted=j
            jobs[j['key']]=j
        assert accepted['key']==s['accepted']['key']
        assert int(repair.evaluation(accepted)['rtl_pass'])<=int(repair.evaluation(accepted)['native_pass'])
    for method in METHODS:
        subset=[r for r in records if r['method']==method]
        assert len(subset)==840 and len({r['instance'] for r in subset})==840
        shared={r['task']:r['contract_tokens'] for r in subset if r['contract_tasks']}
        assert np.isclose(sum(r['amortized_tokens'] for r in subset),sum(r['total'] for r in subset)+sum(shared.values()))
    attempts=[load(p) for j in jobs.values() for p in (run_dir(j)/'attempts').glob('*.json')]
    result={'complete':True,'population_per_method':840,'methods':METHODS,'model':MODEL,
        'maximum_code_calls':5,'maximum_repairs':4,'physical_repair_jobs':len(jobs),
        'physical_transport_status_counts':dict(collections.Counter(str(a.get('http_status')) for a in attempts)),
        'billing_unknown_transport_attempts':sum(bool(a.get('billing_unknown')) for a in attempts),
        'infra_unresolved':0,'evaluation_fingerprint':protocol['evaluation_fingerprint'],
        'original_main_tables_unchanged':core_tables,
        'protocol_sha256':sha(ROOT/'protocol'/(NAME+'.json')),
        'implementation_sha256':sha(ROOT/'rtl_closed_loop.py'),'audited_utc':time.time()}
    assert result['implementation_sha256']==protocol['implementation_sha256']
    save(OUT/'final_audit.json',result)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--round',type=int,required=True);p.add_argument('--final',action='store_true');args=p.parse_args()
    records=records_at(args.round)
    csv_write(OUT/f'round_{args.round}_instance_scores.csv',records);save(OUT/f'round_{args.round}_instance_scores.json',records)
    summary=[]
    for i in range(args.round+1):summary.extend(summarize(records_at(i)))
    by_budget={(r['method'],r['language'],r['max_repairs']):r for r in summary}
    for row in summary:
        previous=by_budget.get((row['method'],row['language'],row['max_repairs']-1))
        for metric in ['native','rtl']:
            row[metric+'_net_gain_vs_previous']=row[metric+'_passed']-previous[metric+'_passed'] if previous else 0
    csv_write(OUT/'budget_curve.csv',summary);save(OUT/'budget_curve.json',summary)
    transitions=[]
    for i in range(1,args.round+1):
        old={(r['method'],r['instance']):r for r in records_at(i-1)}
        new=records_at(i)
        for method in METHODS:
            subset=[r for r in new if r['method']==method]
            for metric in ['native_pass','rtl_pass']:
                gains=sum(r[metric] and not old[(method,r['instance'])][metric] for r in subset)
                losses=sum(not r[metric] and old[(method,r['instance'])][metric] for r in subset)
                transitions.append({'method':method,'round':i,'metric':metric,'n':840,
                    'newly_passed':gains,'newly_failed':losses,'net_gain':gains-losses})
    csv_write(OUT/'round_transitions.csv',transitions);save(OUT/'round_transitions.json',transitions)
    if not args.final:
        print(json.dumps({'round':args.round,'summary':[r for r in summary if r['language']=='All' and r['max_repairs']==args.round]}),flush=True)
        return
    from statsmodels.stats.multitest import multipletests
    baselines=[r for r in load(ROOT/'analysis/exp3_instance_scores.json') if r['method'] in
        ['Direct Pass@5','Direct GatedBest@5','Gen Pass@5','Gen GatedBest@5','ParaRoute-Full']]
    rows=[*records,*[{**r,'arm':r['method']} for r in baselines]]
    effects=[analyze.paired(rows,'RTL-Aware-B5',b,m) for b in
        ['NativeOnly-B5','Direct Pass@5','Direct GatedBest@5','Gen Pass@5','Gen GatedBest@5','ParaRoute-Full']
        for m in ['native_pass','rtl_pass']]
    for e,adjusted in zip(effects,multipletests([e['p'] for e in effects],method='holm')[1]):
        e['p_holm']=float(adjusted);e['holm_family_size']=len(effects)
    save(OUT/'paired_effects.json',effects);csv_write(OUT/'paired_effects.csv',effects)
    initial={r['instance']:r for r in records_at(0) if r['method']=='RTL-Aware-B5'}
    escapes={k for k,r in initial.items() if r['native_pass'] and not r['rtl_pass']}
    diagnostics=[]
    for method in METHODS:
        for language in LANGS+['All']:
            x=[r for r in records if r['method']==method and r['instance'] in escapes and (language=='All' or r['language']==language)]
            diagnostics.append({'method':method,'language':language,'initial_native_pass_rtl_fail_n':len(x),
                'final_native_passed':sum(r['native_pass'] for r in x),'final_rtl_passed':sum(r['rtl_pass'] for r in x)})
    csv_write(OUT/'initial_rtl_escapes.csv',diagnostics);save(OUT/'initial_rtl_escapes.json',diagnostics)
    audit=final_checks(records)
    base_summary=load(ROOT/'analysis/table_vi.json')
    table=[r for r in summary if r['language']=='All']
    lines=['# RTL 反馈闭环：初始生成 + 最多四次代码修复（N=840）','',
        '主模型 deepseek-v4.1-flash；冻结 840 个 Gen 初始候选，不重新采样初始生成。NativeOnly-B5 以 Q_native 通过早停；RTL-Aware-B5 以 C_RTL 通过早停。两臂在原生成功前使用相同路由和历史提示，仅是否继续反馈 RTL 失败不同。', '',
        '候选替换仍只看 C0：最新通过盲门控的候选被接受，拒绝候选仍作为下一轮修复目标并保留已接受前驱。原生失败修复使用既有公开 clk/规格路由；RTL 阶段提供真实 JUnit 异常消息与冻结 L_l。没有提供测试源码、参考 Verilog 或 traceback 测试代码。', '',
        '| 方法 | 最多代码调用 | 原生通过/840 | RTL通过/840 | 平均代码调用 | 含按需契约调用 | 五语言共享Token | 单语言按需Token |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in table:
        lines.append(f"| {r['method']} | {r['budget_code_calls']} | {r['native_passed']} ({r['native_percent']:.2f}%) | {r['rtl_passed']} ({r['rtl_percent']:.2f}%) | {r['mean_code_calls']:.4f} | {r['mean_calls_including_lazy_contracts']:.4f} | {r['mean_amortized_tokens']:.2f} | {r['mean_lazy_tokens']:.2f} |")
    lines.extend(['','既有同模型五样本对照（全部 temp=0.7）与原 Full（最多两轮原生修复）保持冻结：','',
        '| 方法 | 原生% | RTL% | 平均代码调用 | 五语言共享Token | 单语言按需Token |','|---|---:|---:|---:|---:|---:|'])
    for r in base_summary:
        if r['method'] not in {r['method'] for r in baselines}:continue
        lines.append(f"| {r['method']} | {r['native_percent']:.2f} | {r['rtl_percent']:.2f} | {r['mean_calls']:.4f} | {r['mean_amortized_tokens']:.2f} | {r['mean_lazy_tokens']:.2f} |")
    lines.extend(['','Pass@5 为 oracle any-pass；Best-of-5 仅用 C0 选择。闭环使用 Q_native/RTL 失败反馈，信息和评测预算不同。5 次为代码生成/修复调用上限；契约调用另外完整计账，不能声称所有 LLM 调用严格不超过 5 次。闭环统计为累计实际成功率，不使用独立采样 Pass@k 估计公式。', '',
        '| RTL-Aware-B5 对比 | 指标 | 差异pp | 95% CI pp | 配对p | Holm p |','|---|---|---:|---|---:|---:|'])
    for e in effects:
        lines.append(f"| {e['right']} | {e['metric']} | {e['difference_pp']:.3f} | [{e['ci_low_pp']:.3f}, {e['ci_high_pp']:.3f}] | {e['p']:.6g} | {e['p_holm']:.6g} |")
    lines.extend(['',f"初始原生通过但 RTL 失败共 {len(escapes)} 个；分语言恢复见 initial_rtl_escapes.csv。按 168 个题目聚类、每题五语言配对，20000 次 Bootstrap 与符号置换；Holm 检验族为 {len(effects)} 个比较。", '',
        '成本为逻辑部署的累计账单，按完整请求哈希复用的物理响应不视为独立样本。每任务共享契约只在五语言部署总账计一次；单语言按需成本仅对触发契约的实例收取并复用。记录的评测秒数仅覆盖权威结果，归档重试额外耗时未合并，不能当完整墙钟耗时。', '',
        f"最终审计通过，未解决基础设施失败为 {audit['infra_unresolved']}。原核心实验表未覆盖；本扩展输出保存在独立目录。"])
    (OUT/'report_zh.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'rtl_closed_loop_complete':True,'rows':table[-2:],'audit':audit}),flush=True)


if __name__=='__main__':main()
