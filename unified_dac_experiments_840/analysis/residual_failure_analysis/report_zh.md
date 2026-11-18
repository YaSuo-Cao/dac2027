# 残余失败分析：冻结账本的本地复核

本报告没有调用模型、没有运行仿真、没有修改冻结主结果。每个方法各 840 个实例。
归类对象为方法最后选中的候选（selected_key），不是最后一次可能被门控拒绝的尝试。
按首次未通过阶段互斥归类：front_end = 未通过 C0 或未产出可评代码；native = 通过 C0 但未通过原生；rtl = 原生通过但 RTL 未通过。
这些是可观察的失败阶段和首条异常，不是穷尽性的人工根因标注。C_RTL 不含综合。

## 全母体汇总

| model | method | n | front_end_failures | native_failures_after_c0 | rtl_failures_after_native | total_residual | rtl_passed |
|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | Full | 840 | 0 | 6 | 60 | 66 | 774 |
| deepseek-v4.1-flash | Full | 840 | 40 | 78 | 42 | 160 | 680 |
| deepseek-v4.1-flash | NativeOnly-B5 | 840 | 29 | 74 | 44 | 147 | 693 |
| deepseek-v4.1-flash | RTL-Aware-B5 | 840 | 29 | 76 | 15 | 120 | 720 |
| glm-5.3-flash | Full | 840 | 38 | 158 | 55 | 251 | 589 |
| qwen3.8-flash | Full | 840 | 111 | 56 | 63 | 230 | 610 |

## 分语言汇总

| model | method | language | front_end_failures | native_failures_after_c0 | rtl_failures_after_native | rtl_passed |
|---|---|---|---|---|---|---|
| claude-haiku-5-5 | Full | amaranth | 0 | 1 | 0 | 167 |
| claude-haiku-5-5 | Full | migen | 0 | 0 | 0 | 168 |
| claude-haiku-5-5 | Full | myhdl | 0 | 2 | 32 | 134 |
| claude-haiku-5-5 | Full | pymtl3 | 0 | 2 | 28 | 138 |
| claude-haiku-5-5 | Full | pyrtl | 0 | 1 | 0 | 167 |
| deepseek-v4.1-flash | Full | amaranth | 2 | 13 | 0 | 153 |
| deepseek-v4.1-flash | Full | migen | 10 | 16 | 0 | 142 |
| deepseek-v4.1-flash | Full | myhdl | 4 | 14 | 30 | 120 |
| deepseek-v4.1-flash | Full | pymtl3 | 6 | 18 | 12 | 132 |
| deepseek-v4.1-flash | Full | pyrtl | 18 | 17 | 0 | 133 |
| deepseek-v4.1-flash | NativeOnly-B5 | amaranth | 0 | 14 | 0 | 154 |
| deepseek-v4.1-flash | NativeOnly-B5 | migen | 8 | 16 | 0 | 144 |
| deepseek-v4.1-flash | NativeOnly-B5 | myhdl | 4 | 12 | 31 | 121 |
| deepseek-v4.1-flash | NativeOnly-B5 | pymtl3 | 5 | 15 | 13 | 135 |
| deepseek-v4.1-flash | NativeOnly-B5 | pyrtl | 12 | 17 | 0 | 139 |
| deepseek-v4.1-flash | RTL-Aware-B5 | amaranth | 0 | 14 | 0 | 154 |
| deepseek-v4.1-flash | RTL-Aware-B5 | migen | 8 | 16 | 0 | 144 |
| deepseek-v4.1-flash | RTL-Aware-B5 | myhdl | 4 | 13 | 7 | 144 |
| deepseek-v4.1-flash | RTL-Aware-B5 | pymtl3 | 5 | 16 | 8 | 139 |
| deepseek-v4.1-flash | RTL-Aware-B5 | pyrtl | 12 | 17 | 0 | 139 |
| glm-5.3-flash | Full | amaranth | 3 | 28 | 0 | 137 |
| glm-5.3-flash | Full | migen | 4 | 34 | 1 | 129 |
| glm-5.3-flash | Full | myhdl | 3 | 23 | 45 | 97 |
| glm-5.3-flash | Full | pymtl3 | 13 | 25 | 9 | 121 |
| glm-5.3-flash | Full | pyrtl | 15 | 48 | 0 | 105 |
| qwen3.8-flash | Full | amaranth | 6 | 11 | 1 | 150 |
| qwen3.8-flash | Full | migen | 28 | 11 | 0 | 129 |
| qwen3.8-flash | Full | myhdl | 2 | 10 | 28 | 128 |
| qwen3.8-flash | Full | pymtl3 | 10 | 12 | 33 | 113 |
| qwen3.8-flash | Full | pyrtl | 65 | 12 | 1 | 90 |

## 论文解释与边界

- DeepSeek Full 的 160 个残余失败 = 前端未通过 40 + 原生失败 78 + 后端失败 42；前端 40 中有 38 个 construction_error、2 个 output_failure，不应全部称为构造异常。
- Claude Full 的 66 个残余失败 = 前端未通过 0 + 原生失败 6 + 后端失败 60。不能声称 Claude 仍有持续构造死锁。
- DeepSeek Full 的 78 个原生失败中，组合 32、时序 46；Claude 的 6 个原生失败均为时序（DFF、保持授权/加权仲裁、FSM）。输出失配本身不能证明都是单拍偏移、反压或流水线冲刷问题。
- Claude 两个加权仲裁分支的 contract_output_failure 为 True，契约输出截断后保留前驱并停止该分支。不要声称这些实例已经得到完整契约仍修复失败。
- DeepSeek Full 的 42 个后端失败全部在 MyHDL (30) 和 PyMTL3 (12)；Claude 对应 60 个全部在 MyHDL (32) 和 PyMTL3 (28)。这在两个方法各自的后端失败池中均占 100%。
- 首条 JUnit 异常显示：DeepSeek 的 42 个为 MyHDL 转换拒绝 24、PyMTL3 翻译/类型拒绝 12、Verilator 导入拒绝 6；Claude 为 MyHDL 转换拒绝 29、PyMTL3 翻译/类型拒绝 28、Verilator 导入拒绝 2、导出阶段 concat 参数 TypeError 1。未观察到这两个 Full 后端失败池中的 RTL 输出失配。
- 典型确证：MyHDL 非布尔操作数用于逻辑运算（DeepSeek 16、Claude 24）；PyMTL3 不支持的 Python 调用/布尔运算/负循环端点；已导出的 Verilog 也可能被 Verilator 因语法或计时选项拒绝。导入拒绝是当前固定评测配置下的结果，不能一律称为固有不可综合。
- 它们是候选与固定转译工具链不兼容，并不能证明该题无法用可转译写法实现，因此不建议使用 Transpiler Lowering Ceiling。
- Full 以原生通过早停，其后端失败未被 Full 主动反馈修复；不能把 42/60 称为已经过 RTL 闭环仍无法恢复。
- 独立 B=5 复核：NativeOnly-B5 剩余 147 = 29+74+44；RTL-Aware-B5 剩余 120 = 29+76+15。后者 15 个后端失败在 MyHDL 7、PyMTL3 8。两方法总 RTL 通过从 693 提至 720，但原生从 737 降至 735，应同时保留这项回退。
- 已冻结工程审计 unresolved infrastructure=0；本次检查的残余实例均无 infrastructure_error。失败按阶段计入，不把网络或未归因超时解释为逻辑错误。

## 复现与证据

执行 `python unified_dac_experiments_840/analyze_residual_failures.py` 只读取日志并重建本目录。
summary.csv / by_language.csv 给出互斥计数；diagnostic_counts.csv 是首条异常类别；native_by_stratum.csv 是原生失败的 Comb/Seq 报告分组；residual_cases.csv 含每个实例的 selected_key、源码哈希、result/JUnit/门控证据路径及 SHA256、完整首条异常。audit.json 保存输入哈希与一致性断言结果。
