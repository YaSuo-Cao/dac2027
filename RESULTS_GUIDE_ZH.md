# ParaRoute 统一实验结果交接（论文写作 Agent 版）

> 用途：这份文档是论文写作的结果导航和口径说明。数字以 `unified_dac_experiments_840/analysis/` 中经最终审计的 CSV/JSON 为准；此处给出关键结论和最常引用的汇总。逐实例数、语言拆分、Token 明细和检验明细请读取文末所列源文件。不要把旧小样本结果与本文件的统一主实验合并。

## 1. 先读这几条

- **唯一主分母：**168 道题 × 5 种 HCL（PyRTL、MyHDL、Amaranth、Migen、PyMTL3）= **840 个实例**。全部语言各 168 个；组合题 485 个实例，时序题 355 个实例。
- **主模型：**`deepseek-v4.1-flash`。确定性生成/修复 `temperature=0.2, top_p=0.95, max_tokens=4096, reasoning_effort=none, seed=20261022`。多样本实验使用同分布 `temperature=0.7, top_p=0.95`，五个 seed 为 20261022–20261026。
- **验收顺序：**纯参考盲构造门控 `C_0`（`construction_probe.py`）→ 官方 `Q_native`（`pytest + Hypothesis` / `native_case.py`）→ Verilog lowering 与 RTL 功能验证 `C_RTL`。后一级通过数是通过前序门控后的数；分母始终保留 840，输出解析失败也算失败。
- **路由不读题号或 Cat 标签。**依据公开输入端口是否包含 `clk` 与原始规格中的算术/流水关键词：`C_0` 失败走 `FL`；无 `clk` 走 `FTL`；有 `clk` 且规格命中算术/流水关键词走 `FCTL`，其余时序任务走 `FCL`。这是实验冻结的接口/规格路由实现。
- **旧实验不进入核心表：**31 题及 52/96/117 修复起点、PyRTL+MyHDL 336 实例、`qwen3:14b`、旧 `v4-flash`、旧 Mini-RAG/DocOnly 消融均由最新协议明确废弃。最新四个模块都按统一 840 口径完成。不要用旧小样本报告中的百分数替换本文结果。
- **名称区分：**主实验 `Full` 是最多两次原生反馈修复的历史闭环。新增 `RTL-Aware-B5` 是初始代码生成加最多四次修复，并把 RTL 失败作为新反馈阶段；它是独立扩展，不能回头改称原 `Full`。

## 2. 实验 I：冻结边界规则 vs. 全文档检索

目的：比较基线 `Direct`、完整官方文档检索 `FullDocRAG`、以及加入冻结 HCL 边界规则 `Gen`（即 `ParaRoute-Gen (L_l)`）。`FullDocRAG` 检索的是完整的约 1,001–1,492 token 文档片段；`L_l` 每语言约 159–187 token。这里**不是**旧实验中等长约 200-token Mini-RAG 对照。

| 方法 | C0 通过/840 | Q_native 通过/840 | C_RTL 通过/840 | 平均输入 token | 平均 prefix-cached token |
|---|---:|---:|---:|---:|---:|
| Direct | 705 (83.93%) | 584 (69.52%) | 545 (64.88%) | 1,284.87 | 475.43 |
| FullDocRAG | 725 (86.31%) | 610 (72.62%) | 580 (69.05%) | 2,534.46 | 577.22 |
| Gen / `L_l` | 753 (89.64%) | 641 (76.31%) | 605 (72.02%) | 1,473.07 | 551.16 |

按 168 个题目聚类、20,000 次符号置换的配对检验（CI 为 task-cluster bootstrap 95% CI）：

| 对比（左减右） | 指标 | 差异 pp [95% CI] | p |
|---|---|---:|---:|
| Gen − Direct | C0 | +5.71 [3.10, 8.33] | 0.00010 |
| Gen − Direct | Q_native | +6.79 [4.05, 9.64] | 0.00010 |
| Gen − Direct | C_RTL | +7.14 [4.29, 10.00] | 0.00005 |
| Gen − FullDocRAG | C0 | +3.33 [1.31, 5.48] | 0.00260 |
| Gen − FullDocRAG | Q_native | +3.69 [1.19, 6.07] | 0.00470 |
| Gen − FullDocRAG | C_RTL | +2.98 [0.48, 5.48] | 0.02400 |

**可写结论：**短小、冻结的编译器边界规则在完整五语言母体中提升了三道门的通过率；它比 Direct 和成本更高的 FullDocRAG 都有更高的 C_RTL 通过数。不要称 FullDocRAG 为 Mini-RAG，也不要称它与 `L_l` 等 token 长度。

逐 HCL 数字见 `analysis/table_iv.csv`；配对检验见 `analysis/table_iv_paired.json`；完整逐实例账本见 `analysis/exp1_instance_scores.csv`。

## 3. 实验 II：后编译功能修复机制与接口路由

共同流程先对 `Gen` 中 C0 不通过的候选做一次共享 `FL` 编译修复。840 个初始候选中 641 个原生通过；87 个 C0 不通过并进入 FL，FL 后 672 个原生通过，47 个仍不通过 C0。最终在共同的 **121 个构造通过但原生功能失败实例**（49 个无时钟组合实例、72 个有时钟时序实例）上运行同源修复消融；条件修复数必须与端到端 `/840` 结果分开表述。

| 方法 | 条件功能池 n=121 原生恢复 | 条件恢复率 | 合并后的 Q_native /840 | C_RTL /840 |
|---|---:|---:|---:|---:|
| F（反例日志） | 18 | 14.88% | 690 (82.14%) | 650 |
| FT（反例+切片） | 28 | 23.14% | 700 (83.33%) | 659 |
| FC（反例+契约） | 37 | 30.58% | 709 (84.40%) | 669 |
| FCT（反例+契约+切片） | 42 | 34.71% | 714 (85.00%) | 671 |
| Inverse-Route（错配） | 25 | 20.66% | 697 (82.98%) | 657 |
| ParaRoute（接口路由） | 40 | 33.06% | 712 (84.76%) | 671 |

功能池按结构拆分：组合 49 个、时序 72 个。时序池 `F=9/72`、`FT=13/72`、`FC=25/72`、`FCT=27/72`、ParaRoute=25/72；组合池 `F=9/49`、`FT=15/49`、`FC=12/49`、`FCT=15/49`、ParaRoute=15/49。该对照支持时序任务的契约证据价值；`FCT` 的时序恢复率最高，ParaRoute 的条件通过数与 FC 相同，路由的总体价值还来自组合任务避开不合适契约、减少账单。

全 `/840` 的 ParaRoute−基线配对效应：对 F，原生 +2.62 pp [0.95, 4.64]，p=0.00155；RTL +2.50 pp [0.83, 4.40]，p=0.00330。对 FT/FC/FCT 的端到端差异均较小且未显著；ParaRoute 原生为 712/840，FCT 原生为 714/840，两者 RTL 均为 671/840。因此不要声称路由在总通过率显著击败 FCT；主张应是它提供结构化、按需的证据分配与契约节省。

成本对比（机制表的部署逻辑账本）：

| 方法 | 修复代码调用 | 单语言按需总 Token | 五语言共享分摊总 Token | 契约生成+注入 Token：单语言 / 五语言账本 |
|---|---:|---:|---:|---:|
| FCT | 1,048 | 2,344,273 | 2,276,473 | 178,721 / 110,921 |
| ParaRoute | 1,048 | 2,248,233 | 2,199,295 | 126,051 / 77,113 |

相对 FCT，ParaRoute 单语言按需总账减少 4.10%，五语言部署总账减少 3.39%；在契约生成与注入这一特定成本项上分别节省 29.47% 和 30.48%。五语言共享口径把共享契约生成一次的账单在五种 HCL 兄弟实例间分摊；单语言按需口径只在该语言触发 C 分支时付费。不要混淆两种 Token 口径。

完整条件分组和成本表分别为 `analysis/table_v.csv`、`analysis/table_v_actual_costs.csv`；配对效果为 `analysis/table_v_paired.json`；共同功能池及流转为 `analysis/functional_pool.json`、`analysis/exp2_population_flow.json`。

## 4. 实验 III：Pass@k、盲门控 Best-of-k 与原生闭环

840 个任务实例的 Direct 和 Gen 每个各采五个独立样本，温度/top-p 为 0.7/0.95。所有 Pass@k 值使用五个样本的无偏组合估计 `1 - C(5-c,k)/C(5,k)`，所以聚合的期望通过数可能是小数。Best-of-k 只看纯 `C_0` 探针与 warning-free 状态挑第一个候选，选择时不读 `Q_native` 或 RTL 结果。闭环 Fast/Full 使用确定性修复参数，最多分别一轮/两轮原生反馈修复。此表不是相同温度协议下的闭环对比。

| 方法 | 原生通过（%） | RTL 通过（%） | 平均代码调用/实例 | 含按需契约调用 | 五语言共享 Token/实例 | 单语言按需 Token/实例 |
|---|---:|---:|---:|---:|---:|---:|
| Direct Pass@1 | 591.0 (70.36%) | 551.6 (65.67%) | 1.00 | 1.00 | 1,487.89 | 1,487.89 |
| Direct Pass@3 | 678.6 (80.79%) | 644.9 (76.77%) | 3.00 | 3.00 | 4,463.67 | 4,463.67 |
| Direct Pass@5 | 710 (84.52%) | 680 (80.95%) | 5.00 | 5.00 | 7,439.45 | 7,439.45 |
| Direct G(P)-Best@5 | 643 (76.55%) | 598 (71.19%) | 5.00 | 5.00 | 7,439.45 | 7,439.45 |
| Gen Pass@1 | 619.6 (73.76%) | 588.2 (70.02%) | 1.00 | 1.00 | 1,692.61 | 1,692.61 |
| Gen Pass@3 | 712.5 (84.82%) | 689.4 (82.07%) | 3.00 | 3.00 | 5,077.82 | 5,077.82 |
| Gen Pass@5 | 740 (88.10%) | 719 (85.60%) | 5.00 | 5.00 | 8,463.04 | 8,463.04 |
| Gen G(P)-Best@5 | 661 (78.69%) | 630 (75.00%) | 5.00 | 5.00 | 8,463.04 | 8,463.04 |
| ParaRoute-Fast | 708 (84.29%) | 667 (79.40%) | 1.237 | 1.315 | 2,574.66 | 2,626.37 |
| ParaRoute-Full | 722 (85.95%) | 680 (80.95%) | 1.351 | 1.437 | 2,908.25 | 2,966.51 |

成本注意：Pass@k 的 k 个候选成本按五个生成样本成本平均估计；物理采样实验实际对每臂/实例生成了五个候选。Pass@5 是读取全部样本结果后的 oracle any-pass 上界，G(P)-Best@5 才是只能看盲门控的可部署筛选基线。此前 Task C 的 336 实例旧表已废弃。

专项结果（下面直接按最新 `/840` 账本，n 为该专项中的跨语言实例数）：

| 专项 | n | Direct Pass@5 原生/RTL | Direct G(P)-Best@5 原生/RTL | Gen Pass@5 原生/RTL | ParaRoute-Fast 原生/RTL | ParaRoute-Full 原生/RTL |
|---|---:|---:|---:|---:|---:|---:|
| MyHDL 常量题 | 4 | 0/4, 0/4 | 0/4, 0/4 | 0/4, 0/4 | 2/4, 2/4 | 2/4, 2/4 |
| Prob02p05 64-bit 位宽题 | 5 | 4/5, 4/5 | 3/5, 2/5 | 5/5, 5/5 | 5/5, 5/5 | 5/5, 5/5 |
| 全时序实例 | 355 | 290/355, 277/355 | 250/355, 232/355 | 305/355, 294/355 | 287/355, 269/355 | 290/355, 271/355 |
| FSM | 65 | 50/65, 50/65 | 38/65, 38/65 | 58/65, 58/65 | 49/65, 48/65 | 49/65, 48/65 |
| 仲裁器 | 25 | 16/25, 8/25 | 10/25, 5/25 | 19/25, 12/25 | 16/25, 8/25 | 18/25, 9/25 |
| 串行算术 | 20 | 7/20, 7/20 | 4/20, 4/20 | 6/20, 6/20 | 10/20, 10/20 | 10/20, 10/20 |

因此可写：采样五次能提高总体 oracle 上界，且 Gen Pass@5 达 85.60% RTL；但时序 FSM/仲裁/串行算术专项中盲门控 Best-of-5 仍明显低于闭环修复。**不要**写成“Direct 五次在 Prob02p05 仍无法解决”或“任何 MyHDL 常量都被闭环攻克”：真实 `/840` 数据是 Direct Pass@5 在 Prob02p05 为 4/5，Gen Pass@5 为 5/5，MyHDL 常量 Fast/Full 各为 2/4。

机器明细见 `analysis/table_vi.csv` 与 `analysis/table_vi_specialized.csv`；采样逐实例账本见 `analysis/exp3_instance_scores.csv`。这一模块没有单独写入显著性检验文件；不要给 Pass@k 对比添加未计算的 p 值。

## 5. 实验 IV：四模型 × 五语言泛化

主表为每模型/方法完整 840 实例（下表按通过数 /840）。`Full` 为最多两轮原生反馈修复。C0 栏给出构造门控拒绝数（`C_0` errors），RTL 必须通过原生门控。

| 模型 | 方法 | C0 错误 | Q_native 通过 | C_RTL 通过 | 平均代码调用 | 单语言按需 Token/实例 |
|---|---|---:|---:|---:|---:|---:|
| deepseek-v4.1-flash | Direct | 135 | 584 (69.52%) | 545 (64.88%) | 1.000 | 1,488.67 |
|  | Direct+F | 67 | 659 (78.45%) | 616 (73.33%) | 1.305 | 2,179.58 |
|  | Gen | 87 | 641 (76.31%) | 605 (72.02%) | 1.000 | 1,693.01 |
|  | Fast | 47 | 708 (84.29%) | 667 (79.40%) | 1.237 | 2,626.37 |
|  | Full | 40 | 722 (85.95%) | 680 (80.95%) | 1.351 | 2,966.51 |
| qwen3.8-flash | Direct | 235 | 542 (64.52%) | 501 (59.64%) | 1.000 | 1,835.18 |
|  | Direct+F | 157 | 620 (73.81%) | 565 (67.26%) | 1.355 | 3,164.38 |
|  | Gen | 233 | 543 (64.64%) | 501 (59.64%) | 1.000 | 2,051.30 |
|  | Fast | 140 | 641 (76.31%) | 585 (69.64%) | 1.354 | 3,726.24 |
|  | Full | 111 | 673 (80.12%) | 610 (72.62%) | 1.551 | 4,462.04 |
| glm-5.3-flash | Direct | 169 | 510 (60.71%) | 461 (54.88%) | 1.000 | 1,440.42 |
|  | Direct+F | 86 | 586 (69.76%) | 531 (63.21%) | 1.393 | 2,300.89 |
|  | Gen | 140 | 516 (61.43%) | 472 (56.19%) | 1.000 | 1,628.80 |
|  | Fast | 64 | 612 (72.86%) | 559 (66.55%) | 1.386 | 2,801.48 |
|  | Full | 38 | 644 (76.67%) | 589 (70.12%) | 1.604 | 3,436.35 |
| claude-haiku-5-5 | Direct | 32 | 779 (92.74%) | 717 (85.36%) | 1.000 | 2,788.26 |
|  | Direct+F | 2 | 831 (98.93%) | 763 (90.83%) | 1.073 | 3,119.09 |
|  | Gen | 30 | 779 (92.74%) | 728 (86.67%) | 1.000 | 3,101.53 |
|  | Fast | 2 | 832 (99.05%) | 772 (91.90%) | 1.070 | 3,660.47 |
|  | Full | 0 | 834 (99.29%) | 774 (92.14%) | 1.077 | 3,718.57 |

各模型都出现了 Full 相对 Direct 和 Gen 的显著提升。总体 `/840` 的 Full−Direct / Full−Gen 配对效应（pp；每模型均按 168 题聚类）：

| 模型 | Full−Direct 原生 | Full−Direct RTL | Full−Gen 原生 | Full−Gen RTL |
|---|---:|---:|---:|---:|
| deepseek-v4.1-flash | +16.43 [13.10,19.88] | +16.07 [12.74,19.52] | +9.64 [7.14,12.38] | +8.93 [6.55,11.43] |
| qwen3.8-flash | +15.60 [12.14,19.05] | +12.98 [9.76,16.31] | +15.48 [12.86,18.21] | +12.98 [10.60,15.36] |
| glm-5.3-flash | +15.95 [12.62,19.40] | +15.24 [11.90,18.69] | +15.24 [12.38,18.21] | +13.93 [11.19,16.79] |
| claude-haiku-5-5 | +6.55 [4.17,9.29] | +6.79 [4.29,9.52] | +6.55 [4.40,9.05] | +5.48 [3.45,7.74] |

上述对比 raw `p=0.00005`，跨语言/方法/模型共 192 个比较的全局 Holm 校正 `p=0.00755`。DeepSeek Full−Fast 的效应为原生 +1.67 pp、RTL +1.55 pp，raw p=.001，但全局 Holm p=.1045；不能将其写成校正后显著。Qwen、GLM Full−Fast 在同一校正族下仍显著，Claude Full−Fast 不显著。

跨语言 Full 与 Gen 的精确通过数见下表（每格 native/RTL）：

| HCL | DeepSeek Gen → Full | Qwen Gen → Full | GLM Gen → Full | Claude Gen → Full |
|---|---:|---:|---:|---:|
| PyRTL | 109/109 → 133/133 | 69/69 → 91/90 | 71/71 → 105/105 | 147/147 → 167/167 |
| MyHDL | 138/111 → 150/120 | 134/113 → 156/128 | 118/81 → 142/97 | 159/129 → 166/134 |
| Amaranth | 140/140 → 153/153 | 130/129 → 151/150 | 116/116 → 137/137 | 157/157 → 167/167 |
| Migen | 123/123 → 142/142 | 89/89 → 129/129 | 104/104 → 130/129 | 161/161 → 168/168 |
| PyMTL3 | 131/122 → 144/132 | 121/101 → 146/113 | 107/100 → 130/121 | 155/134 → 166/138 |

**Claude 可比性限制：**Claude 经确认使用 OpenCode Anthropic Messages endpoint（`/v1/messages`），不是 OpenAI-compatible Chat Completions。端点不接受 `seed`、`reasoning_effort`，并拒绝已弃用的 `temperature`/`top_p`；这些字段没有发到 Claude wire request。因此 Claude 是全母体/同提示和评测下的异构模型结果，但不能声称与其他模型进行了相同 temperature/seed 控制。固定 `max_tokens=4096`，解析/输出失败仍计入 `/840`。

另有一个 Claude 共享行为契约在 4096-token 输出上限内原始响应及两次 schema-only 格式纠正均截断，影响 `Prob15p05_seq_arb_4in_weighted/amaranth` 和 `.../pymtl3` 两个实例的 Fast/Full 分支。保留此前已接受候选、该分支停止，所有格式纠正成本照计；无人工契约、无提高上限后重抽。具体标志在 `analysis/exp4_instance_scores.csv` 的 `contract_output_failure` 列及 `analysis/claude_contract_output_failures.json`。

四模型同表：`analysis/table_vii_viii.csv`；总体/逐 HCL 全字段：`analysis/table_vii_viii.json`；Holm 检验（JSON）：`analysis/table_vii_viii_paired_holm.json`；逐实例：`analysis/exp4_instance_scores.csv`。

## 6. 新增扩展：RTL 失败反馈闭环，B=5

这是独立的新实验：主模型 DeepSeek v4.1；冻结原 840 个 Gen 初始候选，不重采样。每个实例最多一次初始生成 + 四次代码修复。`NativeOnly-B5` 在 Q_native 通过时停止；`RTL-Aware-B5` 只有 C0、Q_native、C_RTL 都通过才停止。后者在原生通过但 RTL 失败时，再以 JUnit failure/error 的异常消息（不含 traceback 测试代码/测试源码/参考 Verilog）和 `L_l` 规则作为反馈。C0 是唯一候选替换门控，失败候选不替换最近已接受前驱。

| 预算 B（初始+修复上限） | NativeOnly 原生/840 | NativeOnly RTL/840 | RTL-Aware 原生/840 | RTL-Aware RTL/840 | RTL-Aware 平均代码调用 | 平均含契约调用 | 共享/按需 Token 每实例 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1（0 修复） | 641 | 605 | 641 | 605 | 1.000 | 1.000 | 1,693 / 1,693 |
| 2（1 修复） | 708 | 667 | 706 | 688 | 1.280 | 1.358 | 2,678 / 2,730 |
| 3（2 修复） | 722 | 680 | 721 | 703 | 1.461 | 1.548 | 3,235 / 3,295 |
| 4（3 修复） | 732 | 688 | 730 | 714 | 1.624 | 1.711 | 3,758 / 3,817 |
| 5（4 修复） | 737 | 693 | 735 | 720 | 1.774 | 1.862 | 4,253 / 4,314 |

最终 B=5 的 RTL-Aware−NativeOnly：RTL +3.214 pp，95% CI `[+2.143,+4.286]`，配对 p=`0.00005`（20,000 次符号置换），12 项 Holm 校正后 p=`0.00060`。原生差异 −0.238 pp，95% CI `[-0.595,0]`，raw p=.505，Holm p=1。与原 `ParaRoute-Full` 比，RTL-Aware RTL +4.762 pp，95% CI `[+3.214,+6.310]`，raw p=.00005，Holm p=.00060；原生 +1.548 pp，raw p=.0294、Holm p=.147（不显著）。

初始有 36 个“原生通过、RTL 失败”的实例。预算用尽时 RTL-Aware 共做 79 次 RTL 反馈修复；13 次 RTL 修复候选原生失败，其中 5 个通过 C0 并被接受后造成可见原生回退。按轮次 RTL-Aware 新增 RTL 净提升分别为 +83、+15、+11、+6；NativeOnly 分别 +62、+13、+8、+5。收益递减，最后一轮只净增 6 个 RTL 通过案例。

与采样对比时必须声明：B=5 对齐的是**代码调用上限**，不是 Token 上限、温度或信息量。RTL 闭环能看到 Q_native/RTL 的失败反馈，Best-of-5 只用 C0 门控；Pass@5 又是事后 oracle。RTL-Aware B=5 的 RTL 85.71%，高于 Direct Pass@5 的 80.95%、Gen Pass@5 的 85.60%，及各自 G(P)-Best@5 的 71.19%、75.00%；与 Gen Pass@5 的差仅 +0.12 pp，配对 p=1（非显著），不要声称显著击败 Gen oracle Pass@5。

RTL 闭环完整报告、每轮曲线、配对检验和审计：`analysis/rtl_closed_loop_b5/report_zh.md`、`budget_curve.csv`、`round_transitions.csv`、`paired_effects.csv`、`initial_rtl_escapes.csv`、`final_audit.json`。协议为 `protocol/rtl_closed_loop_b5_zh.md`。

## 7. 工程审计与复现可信度

- 最终统一账本审计通过：840 主母体、四实验 scored rows 分别 2,520 / 5,040 / 11,760 / 16,800；官方评测指纹固定；全实验 `infra_unresolved=0`。
- 注册 18,739 个物理任务。1,931 次非 200 网络尝试最终均取得有效响应；42 次账本中账单状态仍未知，另有 8 次已撤销诊断调用无有效响应且账单未知，二者均不当作零成本。
- 留存 62 次评测重试日志覆盖 34 个案例；最终 2 个通过，其余 32 个是经隔离重试及候选侧证据归因的不收敛（28 construction、4 simulation），没有未归因超时/信号被当作设计失败。
- 所有输出格式失败、截断、语法失败和行为失败均按固定分母计入；没有对单独失败候选加预算重抽以改善分数。C0/Native/RTL 各结果来源及源哈希均有逐实例账本。
- 原三模型（DeepSeek、Qwen、GLM）Claude 恢复前后的 4,200 个逐实例结果/模型完全不变；四模型最终表完成一次全局 Holm 校正。

工程报告：`analysis/engineering_recovery_report_zh.md`；综合最终账本：`analysis/candidate_ledger.csv`；机器可查审计：`analysis/final_audit.json`。

## 8. 写作口径与禁止误述

1. 每张核心表都写 N=840（或明确条件子集 n=121、修复分组 n=49/72）；不给 336/117/96/52 的旧分母混入主结果。
2. 全文使用模型名 `deepseek-v4.1-flash`、`qwen3.8-flash`、`glm-5.3-flash`、`claude-haiku-5-5`；不混入 `v4-flash`、本地 `qwen3:14b`。
3. 报 C_RTL 时说明它是先通过 Q_native 后的 Verilog lowering/RTL 验收；Task IV 中 C0 error 是构造门控拒绝数，不是纯 Python parser failure 数。
4. `Pass@k` 用 oracle any-pass 估计；`G(P)-Best@k` 是纯参考盲门控选择；闭环是适应性反馈。三者不能称为同一信息条件。
5. RTL-B5 的 5-call budget = 初始生成 1 + 最多四次修复；契约生成及格式纠正另计，平均全部 LLM 调用高于代码调用均值。不要写成总 LLM calls 永远 ≤5。
6. RTL-aware 收益集中在 RTL 通过；它的最终原生总通过数比 NativeOnly 少 2 个。应报告回退，不只报告 RTL 提升。
7. MyHDL 常量、Prob02p05 专项按第 4 节数值写。旧稿声称“Direct 抽 5 次仍 0/2”与当前统一实验不符。
8. 不把 Task B 旧 `Mini-RAG/DocOnly`、Task A 的 117 起点或此前关于 BCD 的小样本论证并入最新主表。若 Section V-D 要讲 BCD Oracle 溢出，只称独立事后规格审计发现参考实现边界缺陷；不能称生成/修复提示注入了 `BCD_GUARD` 或共享契约引导。
9. Claude 比较需说明 Messages endpoint 的参数限制（seed/temperature/top_p/reasoning_effort 没有发出），故不宣称相同采样控制。输出失败留在分母。
10. `p=0.00005` 是 20,000 次 Monte Carlo 符号置换的最小加一估计量量级（代码公式 `(extreme+1)/20001`），写作 `p≤0.00005` 或按表原值写 `p=4.99975×10^-5`，不要写 p=0。

## 9. 首选机器数据文件

| 内容 | 文件 |
|---|---|
| 实验 I 汇总/逐实例/检验 | `analysis/table_iv.csv`, `analysis/exp1_instance_scores.csv`, `analysis/table_iv_paired.json` |
| 实验 II 汇总/成本/配对效应 | `analysis/table_v.csv`, `analysis/table_v_actual_costs.csv`, `analysis/table_v_paired.json`, `analysis/functional_pool.json` |
| 实验 III 总表/专项/逐实例 | `analysis/table_vi.csv`, `analysis/table_vi_specialized.csv`, `analysis/exp3_instance_scores.csv` |
| 实验 IV 四模型表/检验/逐实例 | `analysis/table_vii_viii.csv`, `analysis/table_vii_viii_paired_holm.json`, `analysis/exp4_instance_scores.csv` |
| 全部真实调用及 C0/Qnative/RTL 结果、模型、Token、成本/用时 | `analysis/candidate_ledger.csv` |
| RTL-aware B=5 扩展 | `analysis/rtl_closed_loop_b5/` |
| 协议及冻结哈希 | `protocol/freeze.json`, `protocol/experiment1_final_freeze.json`, `protocol/rtl_closed_loop_b5.json` |
| 最终总审计 | `analysis/final_audit.json` |

原始实验结果不必手工搬运到论文章节：写作 Agent 应从以上 CSV/JSON 生成 LaTeX 表格，并对每个表中的 count、分母和百分比做脚本断言。
