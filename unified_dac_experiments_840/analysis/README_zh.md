所有新主结果使用同一母体：168 题 × 5 HCL = 840 实例。每种语言的分解为 168；实验二的功能失败集合仅用于恢复率，同时必须并列报告合入全量后的 /840 结果。历史小子集不进入新表。

文件对应关系：

| 模块 | 主表 | 逐实例评分 | 配对检验 |
| --- | --- | --- | --- |
| 实验一 | table_iv.csv / json | exp1_instance_scores.csv / json | table_iv_paired.json |
| 实验二 | table_v.csv / json；table_v_actual_costs.csv / json | exp2_instance_scores.csv / json | table_v_paired.json |
| 实验三 | table_vi.csv / json；table_vi_specialized.csv / json | exp3_instance_scores.csv / json | 同分布 n=5 无偏 Pass@k；盲门控 Best@k |
| 实验四 | table_vii_viii.csv / json | exp4_instance_scores.csv / json | table_vii_viii_paired_holm.json |

对应报告为 experiment1_report.md 至 experiment4_report.md，仅在该模块所需全量评分齐备后生成。尚未生成报告表示模块未完成，不能用旧实验数字填充。

实验四须等三个已纳入模型家族的完整 /840 账本全部齐备后统一发布跨模型表。全部四组完成后运行 audit_final.py；只有 analysis/final_audit.json 明确确认核验通过，才视为本轮数据锁定。该审计覆盖冻结环境、完整母体、响应与源码身份、缓存来源、五样本同分布参数和 seed、样本内响应编号去重、顺序验收及两种契约成本守恒。

candidate_ledger.csv / json 是物理候选账本；strict_reuse_summary.json 记录严格哈希复用。方法部署成本与全因子实验的物理总账不同：未部署的消融臂不应计入单个方法；复用的历史响应不应冒充本轮新增调用。契约格式修正产生的全部响应均计入成本。五语言联合部署的一次契约费用只分摊一次；单语言仅在实际触发契约分支时首次计费。

模型输出格式失败计入分母；容器中止、超时等基础设施异常先串行复评，未解决则阻止发布统计，不当作模型失败。所有原生和 RTL 指标均采用 C0 → Q_native → C_RTL 的顺序验收口径。

实时状态见上一级 progress/orchestrator.json、progress/remote_evaluation.json、progress/orchestrator_console.log。原论文及旧实验目录未被修改。
