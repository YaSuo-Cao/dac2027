"""Read frozen scores and selected-candidate logs; never run models or evaluation."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "analysis" / "residual_failure_analysis"
STAGES = ("front_end", "native", "rtl", "passed")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(name, rows):
    assert rows
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def flag(value):
    assert value in ("True", "False"), value
    return value == "True"


def stage(row):
    c0, native, rtl = (flag(row[field]) for field in ("c0_pass", "native_pass", "rtl_pass"))
    assert not rtl or native
    assert not native or c0
    return "passed" if rtl else "front_end" if not c0 else "native" if not native else "rtl"


def first_junit_failure(path):
    assert path.exists(), path
    for node in ET.parse(path).findall(".//testcase"):
        for tag in ("failure", "error"):
            child = node.find(tag)
            if child is not None:
                return child.get("message", "") or child.text or tag
    raise AssertionError(f"No JUnit failure: {path}")


def diagnostic(row, result, folder, failure_stage):
    if failure_stage == "front_end":
        if result["outcome"] == "output_failure":
            return "output_failure", str(result.get("error", "Output not ready")), folder / "result.json"
        gate_path = folder / "gate.json"
        gate = read_json(gate_path)
        if gate.get("candidate_nonconvergence"):
            return "construction_nonconvergence", json.dumps(gate["candidate_nonconvergence"]), gate_path
        rejected = [p for p in gate.get("probes", []) if not p.get("constructible")]
        assert rejected, gate_path
        message = rejected[0].get("traceback") or rejected[0].get("error") or json.dumps(rejected[0])
        return "construction_error", str(message), gate_path
    if failure_stage == "native":
        path = ROOT / "evaluation" / "native" / "cases" / row["selected_key"] / "junit.xml"
        if result["outcome"] == "functional_mismatch":
            return "native_output_mismatch", first_junit_failure(path), path
        if path.exists():
            return result["outcome"], first_junit_failure(path), path
        return result["outcome"], str(result.get("candidate_nonconvergence", result.get("native", {}))), folder / "result.json"
    path = folder / "rtl" / "junit.xml"
    message = first_junit_failure(path)
    if "myhdl.ConversionError" in message or "myhdl.ToVerilogError" in message:
        kind = "myhdl_conversion_rejection"
    elif any(x in message for x in ("PyMTLSyntaxError", "PyMTLTypeError", "VerilogTranslationError")):
        kind = "pymtl_translation_rejection"
    elif "VerilogImportError" in message:
        kind = "verilator_import_rejection"
    elif "Port named" in message and "does not match" in message:
        kind = "rtl_output_mismatch"
    else:
        kind = "other_export_exception"
    return kind, message, path


def aggregate(rows, model, method, language="All"):
    counts = Counter(stage(r) for r in rows)
    assert sum(counts.values()) == len(rows)
    return dict(model=model, method=method, language=language, n=len(rows),
                front_end_failures=counts["front_end"], native_failures_after_c0=counts["native"],
                rtl_failures_after_native=counts["rtl"], total_residual=len(rows)-counts["passed"],
                rtl_passed=counts["passed"], rtl_percent=100*counts["passed"]/len(rows))


def markdown_table(rows, fields):
    return "\n".join(["| " + " | ".join(fields) + " |", "|" + "---|"*len(fields)] +
                     ["| " + " | ".join(str(r[f]) for f in fields) + " |" for r in rows])


def main():
    inputs = [ROOT / "analysis/exp4_instance_scores.csv",
              ROOT / "analysis/rtl_closed_loop_b5/round_4_instance_scores.csv",
              ROOT / "analysis/table_vii_viii.csv", ROOT / "configs/population.json",
              ROOT / "configs/evaluation_fingerprint.json"]
    hashes_before = {str(p.relative_to(ROOT)): digest(p) for p in inputs}
    population = {r["instance"]: r for r in read_json(inputs[3])}
    fingerprint = read_json(inputs[4])["sha256"]
    groups = defaultdict(list)
    for row in read_csv(inputs[0]):
        if row["arm"] == "Full":
            groups[(row["model"], "Full")].append(row)
    for row in read_csv(inputs[1]):
        groups[(row["model"], row["method"])].append(row)
    reference = {(r["model"], r["method"]): r for r in read_csv(inputs[2]) if r["language"] == "All"}
    summaries, languages, cases = [], [], []
    for (model, method), rows in sorted(groups.items()):
        assert len(rows) == 840
        assert set(r["instance"] for r in rows) == set(population)
        summary = aggregate(rows, model, method)
        if method == "Full":
            ref = reference[model, method]
            assert summary["rtl_passed"] == int(ref["rtl_passed"])
            assert summary["front_end_failures"] == int(ref["c0_errors"])
            assert 840-summary["front_end_failures"]-summary["native_failures_after_c0"] == int(ref["native_passed"])
        summaries.append(summary)
        for language in sorted({r["language"] for r in rows}):
            languages.append(aggregate([r for r in rows if r["language"] == language], model, method, language))
        for row in rows:
            failure_stage = stage(row)
            if failure_stage == "passed":
                continue
            folder = ROOT / "evaluation" / "cases" / row["selected_key"]
            result_path = folder / "result.json"
            result = read_json(result_path)
            assert not result.get("infrastructure_error"), result_path
            assert result["evaluation_fingerprint"] == fingerprint
            for field in ("c0_pass", "native_pass", "rtl_pass"):
                assert result[field] == flag(row[field]), (row["instance"], field)
            kind, message, evidence = diagnostic(row, result, folder, failure_stage)
            cases.append(dict(model=model, method=method, task=row["task"], language=row["language"],
                              instance=row["instance"], reporting_stratum=population[row["instance"]]["reporting_stratum"],
                              failure_stage=failure_stage, diagnostic_kind=kind, outcome=result["outcome"],
                              contract_output_failure=row.get("contract_output_failure", ""),
                              selected_key=row["selected_key"], source_sha256=result.get("source_sha256", ""),
                              result_path=str(result_path.relative_to(ROOT)), result_sha256=digest(result_path),
                              evidence_path=str(evidence.relative_to(ROOT)), evidence_sha256=digest(evidence),
                              first_recorded_diagnostic=message))
    OUT.mkdir(exist_ok=True)
    write_csv("summary.csv", summaries)
    write_csv("by_language.csv", languages)
    write_csv("residual_cases.csv", cases)
    kinds = Counter((r["model"], r["method"], r["failure_stage"], r["diagnostic_kind"]) for r in cases)
    kind_rows = [dict(model=m, method=a, failure_stage=s, diagnostic_kind=k, count=n)
                 for (m, a, s, k), n in sorted(kinds.items())]
    write_csv("diagnostic_counts.csv", kind_rows)
    strata = Counter((r["model"], r["method"], r["reporting_stratum"]) for r in cases if r["failure_stage"] == "native")
    stratum_rows = [dict(model=m, method=a, stratum=s, count=n) for (m, a, s), n in sorted(strata.items())]
    write_csv("native_by_stratum.csv", stratum_rows)
    input_hashes = {str(p.relative_to(ROOT)): digest(p) for p in inputs}
    assert input_hashes == hashes_before, "Frozen input changed"
    audit = dict(all_checks_passed=True, input_sha256=input_hashes, groups=len(groups),
                 scored_rows=sum(len(r) for r in groups.values()), residual_rows=len(cases),
                 unresolved_infrastructure_in_residuals=0, evaluation_fingerprint=fingerprint,
                 new_model_calls=0, new_simulations=0,
                 attribution="First failed gate on the final selected candidate, not all attempted candidates or a causal root-cause census")
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    report = """# 残余失败分析：冻结账本的本地复核

本报告没有调用模型、没有运行仿真、没有修改冻结主结果。每个方法各 840 个实例。
归类对象为方法最后选中的候选（selected_key），不是最后一次可能被门控拒绝的尝试。
按首次未通过阶段互斥归类：front_end = 未通过 C0 或未产出可评代码；native = 通过 C0 但未通过原生；rtl = 原生通过但 RTL 未通过。
这些是可观察的失败阶段和首条异常，不是穷尽性的人工根因标注。C_RTL 不含综合。

## 全母体汇总

""" + markdown_table(summaries, ["model", "method", "n", "front_end_failures", "native_failures_after_c0", "rtl_failures_after_native", "total_residual", "rtl_passed"]) + """

## 分语言汇总

""" + markdown_table(languages, ["model", "method", "language", "front_end_failures", "native_failures_after_c0", "rtl_failures_after_native", "rtl_passed"]) + """

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
"""
    (OUT / "report_zh.md").write_text(report, encoding="utf-8")
    print(json.dumps(dict(summary=summaries, residual_rows=len(cases), audit_passed=True), indent=2))


if __name__ == "__main__":
    main()
