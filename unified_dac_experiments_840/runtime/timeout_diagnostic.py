"""Candidate-only structural evidence after a reproducible isolated timeout."""
import importlib.util,json,subprocess,sys,traceback
from pathlib import Path

def diagnose(language,source,cfg,directory):
    result={'uses_functional_oracle':False,'confirmed_combinational_loop':False,
            'scope':'timeout attribution only; no reference/test inputs or outputs'}
    if language!='amaranth':return result|{'unsupported_language':language}
    try:
        from amaranth import ClockSignal,Signal,ResetInserter
        from amaranth.back import verilog
        spec=importlib.util.spec_from_file_location('timeout_candidate',source)
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        top=module.TopModule(**cfg['parameters'])
        names={n for n,d,w in cfg['ports']};ports=[getattr(top,n) for n,d,w in cfg['ports'] if n not in ['clk','reset']]
        design=top
        if 'clk' in names:ports.append(ClockSignal('sync'))
        if 'reset' in names:
            reset=Signal(name='reset');ports.append(reset);design=ResetInserter(reset)(design)
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        emitted=directory/'TimeoutDiagnosticTop.v'
        emitted.write_text(verilog.convert(design,name='TimeoutDiagnosticTop',ports=ports))
        lint=subprocess.run(['verilator','--lint-only','-Wall','-Wno-fatal','--top-module','TimeoutDiagnosticTop',str(emitted)],
                            capture_output=True,text=True,timeout=45)
        log=lint.stdout+lint.stderr;(directory/'verilator_lint.log').write_text(log)
        loop_lines=[line for line in log.splitlines() if '%Warning-UNOPTFLAT:' in line and 'Circular combinational logic' in line]
        result.update(confirmed_combinational_loop=bool(loop_lines),loop_diagnostics=loop_lines,
                      lint_returncode=lint.returncode,configuration=cfg,emitted_verilog=str(emitted))
    except Exception:result['diagnostic_error']=traceback.format_exc()
    return result

if __name__=='__main__':
    print(json.dumps(diagnose(sys.argv[1],sys.argv[2],json.loads(sys.argv[3]),sys.argv[4])))
