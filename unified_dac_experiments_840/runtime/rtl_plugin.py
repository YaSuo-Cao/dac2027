"""Observe official configurations; optionally substitute native exported RTL DUTs."""
import dataclasses, hashlib, importlib.util, json, os, re, sys
from pathlib import Path

def module_from(source):
    name='candidate_'+hashlib.sha256(str(source).encode()).hexdigest()[:12]
    spec=importlib.util.spec_from_file_location(name,source);mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod;spec.loader.exec_module(mod);return mod


def wrap_native(text,cfg,language):
    from pyhdl_eval.cfg import InputPort
    names={n for n,p in cfg.ports}
    header=re.search(r'module NativeTop\s*\((.*?)\);',text,re.S)
    if not header:raise RuntimeError('Native module header not found')
    native_ports=[n.strip() for n in header.group(1).split(',')]
    declarations=[]
    wrapper_names=[n for n,p in cfg.ports]
    # PyMTL always supplies implicit clk/reset. Its clock-name detection scans the
    # complete source, including the internal module, so wrappers expose both.
    for extra in ('clk','reset'):
        if extra not in names:
            wrapper_names.append(extra);declarations.append('input '+extra+';')
    for n,p in cfg.ports:
        declarations.append(('input' if isinstance(p,InputPort) else 'output')+f' [{p.nbits()-1}:0] {n};')
    connections=[]
    native_body=text[header.end():text.index('endmodule',header.end())]
    for n in native_ports:
        if n in names or n=='clk':value=n
        elif n=='rst':value='reset' if language=='pyrtl' and 'reset' in names else "1'b0"
        elif re.search(r'\boutput\s+(?:\[[^]]+\]\s*)?'+re.escape(n)+r'\s*;',native_body):
            value='unused_'+n;declarations.append('wire '+value+';')
        else:raise RuntimeError('Unsupported extra native port: '+n)
        connections.append('.'+n+'('+value+')')
    return text+'\nmodule RefModule('+','.join(wrapper_names)+');\n'+'\n'.join(declarations)+'\nNativeTop dut('+','.join(connections)+');\nendmodule\n'

def export_dut(language,source,cfg):
    from pyhdl_eval.cfg import InputPort,OutputPort
    from pyhdl_eval.verilog import TopModuleVerilog
    key=hashlib.sha256(json.dumps({'p':cfg.parameters,'ports':[(n,type(p).__name__,p.nbits()) for n,p in cfg.ports]},sort_keys=True).encode()).hexdigest()[:12]
    dest=Path(os.environ['CASE_OUTPUT'])/'emitted'/key;dest.mkdir(parents=True,exist_ok=True)
    emitted=dest/('emitted_'+hashlib.sha256(str(source).encode()).hexdigest()[:12]+'_'+key+'.v')
    if not emitted.exists():
        mod=module_from(source)
        has_clk=any(n=='clk' for n,p in cfg.ports);has_reset=any(n=='reset' for n,p in cfg.ports)
        if language=='myhdl':
            import myhdl
            ports=[myhdl.ResetSignal(0,active=1,isasync=False) if n=='reset' else myhdl.Signal(myhdl.modbv(0)[p.nbits():]) for n,p in cfg.ports]
            block=mod.TopModule(*ports,**cfg.parameters)
            block.convert(hdl='Verilog',path=str(dest),name='RefModule')
            emitted.write_text((dest/'RefModule.v').read_text())
        elif language=='amaranth':
            import amaranth as am
            from amaranth.back import verilog
            top=mod.TopModule(**cfg.parameters)
            ports=[getattr(top,n) for n,p in cfg.ports if n not in ('clk','reset')]
            design=top
            if has_clk:ports.append(am.ClockSignal('sync'))
            if has_reset:
                reset=am.Signal(name='reset');ports.append(reset);design=am.ResetInserter(reset)(design)
            raw=verilog.convert(design,name='NativeTop',ports=ports)
            emitted.write_text(wrap_native(raw,cfg,'amaranth'))
        elif language=='migen':
            import migen
            from migen.fhdl import verilog
            top=mod.TopModule(**cfg.parameters)
            ios=set()
            for n,p in cfg.ports:
                if n=='clk':continue
                signal=getattr(top,n);signal.name_override=n;ios.add(signal)
            converted=verilog.convert(top,ios=ios,name='NativeTop')
            raw=str(converted)
            # Migen inserts implicit sys_clk/sys_rst. Normalize only those
            # interface wires, leaving candidate logic and reset wiring intact.
            raw=re.sub(r'\bsys_clk\b','clk',raw)
            raw=re.sub(r'\bsys_rst\b','implicit_sys_rst',raw)
            header=re.search(r'module NativeTop\s*\((.*?)\);',raw,re.S)
            if not header:raise RuntimeError('Migen module header missing')
            declarations=[];connections=[];names={n for n,p in cfg.ports}
            for token in header.group(1).split(','):
                n=re.findall(r'[A-Za-z_][A-Za-z_0-9]*',token)[-1]
                if n in names or n=='clk':value=n
                elif n=='implicit_sys_rst':value="1'b0"
                else:raise RuntimeError('Unsupported Migen implicit port: '+n)
                connections.append('.'+n+'('+value+')')
            wrapper=[n for n,p in cfg.ports]
            if 'clk' not in names:wrapper.append('clk');declarations.append('input clk;')
            for n,p in cfg.ports:declarations.append(('input' if isinstance(p,InputPort) else 'output')+f' [{p.nbits()-1}:0] {n};')
            emitted.write_text(raw+'\nmodule RefModule('+','.join(wrapper)+');\n'+'\n'.join(declarations)+'\nNativeTop dut('+','.join(connections)+');\nendmodule\n')
        elif language=='pymtl':
            from pymtl3.passes.backends.verilog import VerilogTranslationPass
            top=mod.TopModule(**cfg.parameters);top.elaborate()
            top.set_metadata(VerilogTranslationPass.enable,True)
            top.set_metadata(VerilogTranslationPass.explicit_module_name,'RefModule')
            top.set_metadata(VerilogTranslationPass.explicit_file_name,str(emitted))
            top.apply(VerilogTranslationPass())
            if not emitted.exists():raise RuntimeError('PyMTL3 translation did not emit Verilog')
        elif language=='pyrtl':
            import pyrtl,io
            from pyhdl_eval.pyrtl import TopModulePyRTL
            native=TopModulePyRTL(str(source),cfg)
            stream=io.StringIO();pyrtl.output_to_verilog(stream,add_reset=True)
            text=stream.getvalue();text=re.sub(r'module\s+toplevel\s*\(', 'module NativeTop(',text,count=1)
            header=re.search(r'module NativeTop\s*\((.*?)\);',text,re.S)
            if not header:raise RuntimeError('Unsupported PyRTL exporter module header')
            native_ports=[n.strip() for n in header.group(1).split(',')]
            emitted.write_text(wrap_native(text,cfg,'pyrtl'));native.cleanup()
        else:raise ValueError('Unsupported language: '+language)
    save_cfg=dataclasses.replace(cfg,parameters={})
    return TopModuleVerilog(str(emitted),save_cfg,ref=True)

def pytest_sessionstart(session):
    import pyhdl_eval.core as core
    original=core.run_sim
    out=Path(os.environ['CASE_OUTPUT']);out.mkdir(parents=True,exist_ok=True)
    configs={}
    def observed(dsl_or_config,script,cfg,test_vectors=None):
        item={'parameters':cfg.parameters,'ports':[(n,type(p).__name__,p.nbits()) for n,p in cfg.ports],
              'dead_cycles':cfg.dead_cycles,'dead_cycle_inputs':cfg.dead_cycle_inputs}
        key=json.dumps(item,sort_keys=True);configs[key]=item
        (out/'observed_configs.json').write_text(json.dumps(list(configs.values()),indent=2))
        return original(dsl_or_config,script,cfg,test_vectors)
    core.run_sim=observed
    if os.environ.get('EVAL_MODE')=='rtl':
        # Identical RTL warning policy for every language: warnings are logged
        # and do not substitute for a syntax or functional failure. Migen's
        # exporter emits an INITIALDLY warning even for the known-good fixture.
        from pymtl3.passes.backends.verilog import VerilogVerilatorImportPass as V
        original_import=V.__call__
        def import_with_reported_warnings(self,top):
            for component in top.get_all_components():component.set_metadata(V.vl_W_fatal,False)
            return original_import(self,top)
        V.__call__=import_with_reported_warnings
        language=os.environ['CANDIDATE_LANGUAGE']
        core.dsls[language]=lambda source,cfg:export_dut(language,Path(source),cfg)
