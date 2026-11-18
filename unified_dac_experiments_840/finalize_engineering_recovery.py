"""Publish a local-only recovery audit after Claude's full pipeline completes."""
from __future__ import annotations
import collections, subprocess, sys
from common import *
import audit_engineering_failures as engineering


def main():
    marker=load(ROOT/'progress/experiment4_complete.json')
    assert marker.get('complete') and marker.get('claude_available'), 'Claude full pipeline is still pending'
    records=load(ROOT/'analysis/exp4_instance_scores.json')
    old=load(ROOT/'archives/pre_claude_completion/exp4_instance_scores.json')
    stable=[]
    for model in sorted({r['model'] for r in old}):
        def normalized(rows):
            return sorted([{k:v for k,v in r.items() if k!='contract_output_failure'}
                for r in rows if r['model']==model],key=lambda r:(r['instance'],r['arm']))
        before,after=normalized(old),normalized(records)
        assert before==after, 'Pre-existing model scores or costs changed: '+model
        stable.append({'model':model,'records':len(before),'unchanged':True,
                       'normalized_records_sha256':canonical(after)})
    save(ROOT/'analysis/recovery_existing_models_unchanged.json',stable)

    availability=load(ROOT/'analysis/model_availability.json')
    availability['claude-haiku-5-5'].update(
        included_in_denominator=True,included_in_full_routed_denominator=True,
        full_routed_status='complete',protocol='anthropic_messages',
        actual_unsupported_fields_omitted=['seed','reasoning_effort','temperature','top_p'])
    save(ROOT/'analysis/model_availability.json',availability)

    engineering.audit()
    audit=load(ROOT/'analysis/engineering_audit_summary.json')
    assert audit['suspect_or_pending_jobs']==0
    assert audit['transport_retry_jobs_unresolved']==0
    assert audit['evaluation_retry_jobs_unresolved']==0
    claude=[r for r in records if r['model']=='claude-haiku-5-5']
    failures=[r for r in claude if r.get('contract_output_failure')]
    failure_summary={'model':'claude-haiku-5-5',
        'logical_rows_by_method':dict(collections.Counter(r['arm'] for r in failures)),
        'affected_instances':sorted({r['instance'] for r in failures}),
        'affected_tasks':sorted({r['task'] for r in failures}),
        'policy':'Fixed 4096 cap; at most two schema-only corrections; retain predecessor and charge all attempts'}
    save(ROOT/'analysis/claude_contract_output_failures.json',failure_summary)
    summary=load(ROOT/'analysis/table_vii_viii.json')
    lines=[
        '# 统一 840 实验：工程与网络失败复核、Claude 队列恢复', '',
        '范围为当前生效的 168 题 × 5 HCL 统一实验。历史 52/96/117/336 子集已按最新要求归档，不重跑、不混入主表。', '',
        f"已核查 {audit['registered_jobs']:,} 个物理任务。当前待完成/待归因工程任务为 {audit['suspect_or_pending_jobs']}，未恢复传输任务为 {audit['transport_retry_jobs_unresolved']}，未恢复评测重试任务为 {audit['evaluation_retry_jobs_unresolved']}。", '',
        f"已登记的 {audit['non_200_attempts']:,} 次非 200 请求最终均获得有效响应，涉及 {audit['transport_retry_jobs_recovered']} 个任务；保留原请求哈希与全部尝试日志。这些是尝试次数，不是失败实例数。", '',
        f"主任务传输日志中仍有 {audit['registered_billing_unknown_attempts']} 次尝试的账单状态未知；最终成功响应不会消除此前请求是否收费的不确定性，已单独保留，不视作零成本。", '',
        f"评测留存 {audit['archived_evaluation_attempts']} 次工程重试记录，覆盖 {audit['evaluation_retry_jobs']} 个案例。最终分类为 {json.dumps(audit['evaluation_retry_final_outcomes'],ensure_ascii=False)}。重复超时本身不作为代码失败；不收敛分类有候选侧结构或动态证据。", '',
        f"另有 {audit['withdrawn_diagnostic_attempts']} 次已撤销诊断请求（HTTP 状态 {json.dumps(audit['withdrawn_diagnostic_http_statuses'])}），没有有效响应或评分候选，单独留档；其中 {audit['withdrawn_diagnostic_billing_unknown']} 次账单未知，不按零成本处理。该诊断曾拟提高输出上限，未混入固定 4096 主协议。", '',
        'Claude 通过 Anthropic Messages 接口完成基础生成与两轮上限的修复流程。端点不支持 seed/reasoning_effort 及已弃用 temperature/top_p，实际请求省略这些字段；不能声称与其他模型具有相同的采样参数控制。', '',
        f"契约固定预算耗尽影响的实例：{', '.join(failure_summary['affected_instances']) or '无'}。对应方法行数：{json.dumps(failure_summary['logical_rows_by_method'])}。这些实例仍留在 /840 中，保留已接受前驱，所有契约格式纠正成本计入；没有伪造契约或提升上限重抽。", '',
        '原三模型的全部逐实例分数与成本已与恢复前档案逐字段比较，完全一致；跨模型 Holm 校正随新增模型扩展检验族重新计算。', '',
        '| 模型 | 方法 | 原生通过/840 | RTL通过/840 | 平均代码调用 | 平均按需契约总Token |',
        '|---|---|---:|---:|---:|---:|'
    ]
    for row in summary:
        if row['language']!='All':continue
        token=row['mean_lazy_tokens']
        lines.append(f"| {row['model']} | {row['method']} | {row['native_passed']} | {row['rtl_passed']} | {row['mean_calls']:.6f} | {token:.6f} |")
    lines.extend(['',
        '真实模型输出失败（固定预算截断、语法错误、多个代码块）与候选不收敛均保留在分母。没有为了提高成功率选择性重抽这些失败。', '',
        '五轮修复仅整理了 protocol/closed_loop_budget_extension_zh.md；没有启动额外轮次的模型调用或仿真。现有 Fast/Full 仍分别为最多一次/两次代码修复。'])
    (ROOT/'analysis/engineering_recovery_report_zh.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    subprocess.run([sys.executable,str(ROOT/'audit_final.py')],cwd=WORK,check=True)
    print(json.dumps({'engineering_recovery_complete':True,'unresolved':0,
        'existing_models_unchanged':True,'claude_contract_failures':failure_summary},ensure_ascii=False))


if __name__=='__main__':main()
