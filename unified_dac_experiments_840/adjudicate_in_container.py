"""Apply frozen timeout-attribution criteria when a DSL needs an export adapter.

This tool is outside the scoring runtime. It retains the frozen native/probe
execution and result, adds candidate-only diagnostic evidence, and changes only
the attribution of an isolated reproducible timeout with a confirmed loop.
"""
import ast,builtins,hashlib,importlib.util,json,os,subprocess,sys,traceback,shutil
from pathlib import Path
sys.path.insert(0,'/work/runtime')
import evaluate as official
ROOT=Path('/work');OUT=Path('/out')

def load(p):return json.loads(Path(p).read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2))

def invariant_length_loops(source):
    """Conservative proof shape: a wire-width guard with no possible update/exit.

    Accept only assignments of integer expressions or slices of the guard wire,
    and pass statements. No calls except builtin len, attribute stores, aliases,
    control-flow exits, mutable objects, or operators on wires are admitted.
    """
    loops={}
    for loop in ast.walk(ast.parse(Path(source).read_text())):
        if not isinstance(loop,ast.While) or loop.orelse:continue
        test=loop.test
        if not (isinstance(test,ast.Compare) and len(test.ops)==len(test.comparators)==1
                and isinstance(test.ops[0],ast.Gt) and isinstance(test.comparators[0],ast.Constant)
                and type(test.comparators[0].value) is int):continue
        call=test.left
        if not (isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=='len'
                and not call.keywords and len(call.args)==1 and isinstance(call.args[0],ast.Name)):continue
        name=call.args[0].id;integers=set()
        def integer(expr):
            if isinstance(expr,ast.Constant):return type(expr.value) is int
            if isinstance(expr,ast.Name):return expr.id in integers
            if isinstance(expr,ast.Call):return ast.dump(expr)==ast.dump(call)
            return (isinstance(expr,ast.BinOp) and isinstance(expr.op,(ast.Add,ast.Sub,ast.Mult,ast.FloorDiv,ast.Mod))
                    and integer(expr.left) and integer(expr.right))
        def wire_slice(expr):
            if not (isinstance(expr,ast.Subscript) and isinstance(expr.value,ast.Name) and expr.value.id==name):return False
            sub=expr.slice
            return (all(x is None or integer(x) for x in [sub.lower,sub.upper,sub.step])
                    if isinstance(sub,ast.Slice) else integer(sub))
        valid=True
        for statement in loop.body:
            if isinstance(statement,ast.Pass):continue
            if not (isinstance(statement,ast.Assign) and all(isinstance(t,ast.Name) and t.id not in [name,'len'] for t in statement.targets)):
                valid=False;break
            is_integer=integer(statement.value)
            if not (is_integer or wire_slice(statement.value)):
                valid=False;break
            for target in statement.targets:
                integers.discard(target.id)
                if is_integer:integers.add(target.id)
        if valid:
            loops[loop.lineno]={'guard_name':name,'threshold':test.comparators[0].value,
                'guard':ast.unparse(test),'body_sha256':hashlib.sha256(ast.dump(ast.Module(body=loop.body,type_ignores=[])).encode()).hexdigest()}
    return loops

def host_elaboration_loop(language,source,cfg):
    """Observe only a statically invariant PyRTL constructor loop, never score it.

    This is used after repeated official isolated timeouts. The candidate and
    official probe remain unchanged; the trace aborts only after 32 witnessed
    iterations of an invariant, true guard with supported native wire methods.
    """
    proof={'confirmed_host_elaboration_loop':False,'uses_functional_oracle':False}
    if language!='pyrtl':return proof
    loops=invariant_length_loops(source)
    if not loops:return proof
    import inspect,pyrtl
    from construction_probe import probe
    source=Path(source).resolve();source_name=str(source);observations={}
    class InvariantElaborationLoop(Exception):pass
    def observe(frame,event,arg):
        line=frame.f_lineno
        if event!='line' or frame.f_code.co_filename!=source_name or line not in loops:return observe
        shape=loops[line];value=frame.f_locals.get(shape['guard_name'])
        if not isinstance(value,pyrtl.WireVector):return observe
        if type(value).__len__ is not pyrtl.WireVector.__len__ or type(value).__getitem__ is not pyrtl.WireVector.__getitem__:return observe
        if frame.f_locals.get('len',frame.f_globals.get('len',builtins.len)) is not builtins.len:return observe
        width=len(value)
        if width<=shape['threshold']:return observe
        state=(id(value),width);seen=observations.setdefault((id(frame),line),[]);seen.append(state)
        if len(seen)>=32 and len(set(seen))==1:
            proof.update(confirmed_host_elaboration_loop=True,loop_line=line,**shape,
                observed_iterations=len(seen),unchanged_guard_width=width,wire_type=type(value).__module__+'.'+type(value).__name__,
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                native_len_sha256=hashlib.sha256(inspect.getsource(pyrtl.WireVector.__len__).encode()).hexdigest(),
                native_getitem_sha256=hashlib.sha256(inspect.getsource(pyrtl.WireVector.__getitem__).encode()).hexdigest(),
                evidence='True builtin len(wire)>constant guard; fixed wire identity/width; body only integer assignments, wire slices and pass; no guard update or control-flow exit')
            raise InvariantElaborationLoop('Proved invariant host elaboration loop')
        return observe
    previous=sys.gettrace();sys.settrace(observe)
    try:proof['native_probe']=probe(language,str(source),cfg)
    finally:sys.settrace(previous)
    return proof

def mixed_candidate_exercise(language,source,cfg):
    # Independent candidate-only stimuli, derived from public port widths.
    # This diagnoses data-dependent loops missed by uniform smoke patterns.
    # No reference DUT, test source, expected value or benchmark label is read.
    import random
    from pyhdl_eval.cfg import Config,InputPort,OutputPort
    from pyhdl_eval.core import dsls
    config=Config(parameters=cfg['parameters'],ports=[(n,InputPort(w) if d=='InputPort' else OutputPort(w)) for n,d,w in cfg['ports']])
    rng=random.Random(20261022);dut=None;stimuli=[]
    try:
        dut=dsls[language](str(source),config);dut.reset()
        if any(n=='reset' and d=='InputPort' for n,d,w in cfg['ports']):dut.write('reset',0)
        for cycle in range(32):
            values={};index=0
            for n,d,w in cfg['ports']:
                if d!='InputPort' or n in ['clk','reset']:continue
                value=((index+1) if cycle==0 else (32-index) if cycle==1 else rng.getrandbits(w))&((1<<w)-1)
                values[n]=value;dut.write(n,value);index+=1
            stimuli.append(values);dut.tick_phase0()
            for n,d,w in cfg['ports']:
                if d=='OutputPort':int(dut.read(n).uint())
            dut.tick_phase1()
        return {'constructible':True,'uses_functional_oracle':False,'diagnostic_stimuli':stimuli}
    except Exception:return {'constructible':False,'uses_functional_oracle':False,'diagnostic_stimuli':stimuli,'traceback':traceback.format_exc()}
    finally:
        if dut is not None:dut.cleanup()

def native_delta_cycle(source,cfg,mixed_patterns=False):
    # Observe exact native commit/execute operations, without changing values,
    # inputs or scheduling. A repeated complete state with pending changes in
    # one combinational propagation proves a periodic delta-cycle loop.
    import inspect
    from migen.sim.core import Simulator
    from construction_probe import probe
    original=Simulator._commit_and_comb_propagate;proof={}
    class PeriodicDeltaCycle(Exception):pass
    def observed(self):
        all_modified=set();modified=self.evaluator.commit();all_modified|=modified;seen={};step=0
        while modified:
            state=(tuple(sorted((s.duid,int(v)) for s,v in self.evaluator.signal_values.items())),tuple(sorted(s.duid for s in modified)))
            if state in seen:
                proof.update(confirmed_native_delta_cycle=True,period=step-seen[state],first_seen_delta=seen[state],
                             repeated_at_delta=step,complete_state_sha256=hashlib.sha256(repr(state).encode()).hexdigest(),
                             signal_count=len(state[0]),pending_signal_count=len(modified))
                raise PeriodicDeltaCycle('Periodic native combinational propagation; complete evaluator state repeats with pending changes')
            if step>=100000:raise RuntimeError('Diagnostic limit reached; no periodic-state proof')
            seen[state]=step;step+=1
            self.evaluator.execute(self.fragment.comb);modified=self.evaluator.commit();all_modified|=modified
        for signal in all_modified:self.vcd.set(signal,self.evaluator.signal_values[signal])
    Simulator._commit_and_comb_propagate=observed
    try:result=mixed_candidate_exercise('migen',source,cfg) if mixed_patterns else probe('migen',str(source),cfg)
    finally:Simulator._commit_and_comb_propagate=original
    return {'uses_functional_oracle':False,'native_probe':result,'native_simulator_source_sha256':hashlib.sha256(inspect.getsource(original).encode()).hexdigest(),
            'observer':'exact native commit/execute plus complete-state repetition detection; signal values and scheduling unchanged',**proof}

def amaranth_delta_cycle(source,cfg,mixed_patterns=False):
    # Preserve the native eval/commit operations and process iteration order.
    # Compare states only while hardware processes execute; a coroutine/clock
    # execution clears the history so hidden coroutine state cannot recur.
    import inspect
    from amaranth.sim.pysim import PySimEngine
    from amaranth.sim._pyrtl import PyRTLProcess
    from construction_probe import probe
    original=PySimEngine._step;proof={}
    class PeriodicDeltaCycle(Exception):pass
    def observed(self):
        changed=set() if self._vcd_writers else None
        converged=False;seen={};step=0
        while not converged:
            processes=tuple(self._processes)
            if any(p.runnable and not isinstance(p,PyRTLProcess) for p in processes):
                seen.clear()
            else:
                indices={p:i for i,p in enumerate(processes)}
                slots={id(s):i for i,s in enumerate(self._state.slots)}
                state=(self._timeline.now,
                    tuple((s.curr,s.next,tuple(sorted((indices[p],trigger) for p,trigger in s.waiters.items()))) for s in self._state.slots),
                    tuple(sorted(slots[id(s)] for s in self._state.pending)),
                    tuple((p.runnable,p.passive) for p in processes),
                    tuple(sorted((indices[p],deadline) for p,deadline in self._timeline.deadlines.items())))
                if state in seen and any(p.runnable for p in processes):
                    proof.update(confirmed_native_delta_cycle=True,period=step-seen[state],first_seen_delta=seen[state],
                        repeated_at_delta=step,complete_state_sha256=hashlib.sha256(repr(state).encode()).hexdigest(),
                        signal_count=len(self._state.slots),simulation_time=self._timeline.now,
                        runnable_hardware_processes=sum(p.runnable for p in processes),
                        nonhardware_processes_executed_between_matches=False)
                    raise PeriodicDeltaCycle('Periodic native hardware delta propagation with unchanged external processes and time')
                seen[state]=step
            if step>=100000:raise RuntimeError('Diagnostic limit reached; no periodic-state proof')
            step+=1
            for process in self._processes:
                if process.runnable:
                    process.runnable=False
                    process.run()
            converged=self._state.commit(changed)
        for vcd_writer in self._vcd_writers:
            for signal_state in changed:
                vcd_writer.update(self._timeline.now,signal_state.signal,signal_state.curr)
    PySimEngine._step=observed
    try:result=mixed_candidate_exercise('amaranth',source,cfg) if mixed_patterns else probe('amaranth',str(source),cfg)
    finally:PySimEngine._step=original
    return {'uses_functional_oracle':False,'native_probe':result,'native_simulator_source_sha256':hashlib.sha256(inspect.getsource(original).encode()).hexdigest(),
        'observer':'native hardware eval/commit plus complete-state recurrence; discard history whenever any nonhardware process runs; values and scheduling unchanged',**proof}

def structure(j,cfg,dest):
    from pyhdl_eval.cfg import InputPort
    source=ROOT/'runs/cases'/j['key']/'candidate.py';language=j['adapter_language']
    host_proof=host_elaboration_loop(language,source,cfg)
    if host_proof.get('confirmed_host_elaboration_loop'):return host_proof
    spec=importlib.util.spec_from_file_location('timeout_export_'+hashlib.sha256(str(source).encode()).hexdigest()[:12],source)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    emitted=dest/'TimeoutDiagnosticTop.v'
    if language=='migen':
        from migen.fhdl import verilog
        top=module.TopModule(**cfg['parameters']);ios=set()
        for n,d,w in cfg['ports']:
            if n=='clk':continue
            s=getattr(top,n);s.name_override=n;ios.add(s)
        emitted.write_text(str(verilog.convert(top,ios=ios,name='TimeoutDiagnosticTop')))
    elif language=='myhdl':
        import myhdl
        signals=[myhdl.ResetSignal(0,active=1,isasync=False) if n=='reset' else myhdl.Signal(myhdl.modbv(0)[w:]) for n,d,w in cfg['ports']]
        module.TopModule(*signals,**cfg['parameters']).convert(hdl='Verilog',path=str(dest),name='TimeoutDiagnosticTop')
    elif language=='pymtl':
        from pymtl3.passes.backends.verilog import VerilogTranslationPass as V
        top=module.TopModule(**cfg['parameters']);top.elaborate()
        top.set_metadata(V.enable,True);top.set_metadata(V.explicit_module_name,'TimeoutDiagnosticTop');top.set_metadata(V.explicit_file_name,str(emitted));top.apply(V())
    elif language=='amaranth':
        from timeout_diagnostic import diagnose
        result=diagnose(language,source,cfg,dest)
        if not result.get('confirmed_combinational_loop'):result.update(amaranth_delta_cycle(source,cfg))
        if not result.get('confirmed_combinational_loop') and not result.get('confirmed_native_delta_cycle'):
            result.update(amaranth_delta_cycle(source,cfg,mixed_patterns=True))
        return result
    else:return {'confirmed_combinational_loop':False,'unsupported_language':language,'uses_functional_oracle':False}
    lint=subprocess.run(['verilator','--lint-only','-Wall','-Wno-fatal','--top-module','TimeoutDiagnosticTop',str(emitted)],capture_output=True,text=True,timeout=45)
    log=lint.stdout+lint.stderr;(dest/'verilator_lint.log').write_text(log)
    lines=[line for line in log.splitlines() if '%Warning-UNOPTFLAT:' in line and 'Circular combinational logic' in line]
    result={'confirmed_combinational_loop':bool(lines),'loop_diagnostics':lines,'lint_returncode':lint.returncode,
            'uses_functional_oracle':False,'configuration':cfg,'emitted_verilog':str(emitted)}
    if not lines and language=='migen':result.update(native_delta_cycle(source,cfg))
    if not lines and language=='migen' and not result.get('confirmed_native_delta_cycle'):
        result.update(native_delta_cycle(source,cfg,mixed_patterns=True))
    return result

def bounded_structure(j,cfg,dest):
    # Candidate elaboration can itself contain an infinite Python loop. The
    # diagnostic must be bounded independently from the frozen score attempt.
    request=dest/'diagnostic_request.json';response=dest/'diagnostic_response.json'
    save(request,{'job':j,'configuration':cfg,'destination':str(dest)})
    with (dest/'diagnostic_worker.log').open('w') as log:
        process=subprocess.Popen([sys.executable,str(Path(__file__)),'--diagnostic',str(request)],
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:returncode=process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(process.pid,signal.SIGKILL);process.wait();returncode=124
    if returncode==0 and response.exists():return load(response)
    return {'confirmed_combinational_loop':False,'uses_functional_oracle':False,
        'diagnostic_worker_returncode':returncode,'unresolved':True,'reason':'bounded independent diagnosis did not complete'}

def main():
    jobs=load(ROOT/'configs/evaluation_queue.json');outcomes=[]
    for j in jobs:
        rp=OUT/'cases'/j['key']/'result.json'
        if not rp.exists():continue
        r=load(rp)
        if not r.get('infrastructure_error'):continue
        dest=OUT/'adjudication'/j['key'];dest.mkdir(parents=True,exist_ok=True)
        original=r;save(dest/'original_result.json',original)
        gate=r.get('gate_infrastructure') or {};native=r.get('native') or {}
        isolated_gate=gate.get('returncode')==124 and gate.get('seconds',0)>=119
        isolated_native=native.get('returncode')==124 and native.get('seconds',0)>=299
        if not isolated_gate and not isolated_native:
            # Exact same SHA-pinned official evaluator, isolated larger limits.
            for folder in [rp.parent,OUT/'native/cases'/j['key']]:
                if folder.exists():
                    target=dest/('prior_gate_case' if folder==rp.parent else 'prior_native_case')
                    if target.exists():raise RuntimeError('Prior isolated attempt already saved; inspect before rerun')
                    folder.rename(target)
            r=official.evaluate(j,serial=True);save(dest/'isolated_result.json',r)
            gate=r.get('gate_infrastructure') or {};native=r.get('native') or {}
            isolated_gate=gate.get('returncode')==124 and gate.get('seconds',0)>=119
            isolated_native=native.get('returncode')==124 and native.get('seconds',0)>=299
            if not r.get('infrastructure_error'):
                outcomes.append({'key':j['key'],'outcome':r['outcome'],'resolved_by_serial':True});continue
        if not isolated_gate and not isolated_native:
            outcomes.append({'key':j['key'],'unresolved':True,'reason':'no isolated repeated timeout'});continue
        configs=load(ROOT/'configs/public_configurations.json')[j['task']]
        construction=OUT/'native/cases'/j['key']/'construction.json'
        cfg=load(construction)['config'] if isolated_native and construction.exists() else configs[gate.get('configuration_index',0)]
        try:proof=bounded_structure(j,cfg,dest)
        except Exception:proof={'confirmed_combinational_loop':False,'uses_functional_oracle':False,'error':traceback.format_exc()}
        save(dest/'candidate_only_diagnostic.json',proof)
        if not (proof.get('confirmed_combinational_loop') or proof.get('confirmed_native_delta_cycle')
                or (isolated_gate and proof.get('confirmed_host_elaboration_loop'))):
            outcomes.append({'key':j['key'],'unresolved':True,'reason':'structural loop unconfirmed'});continue
        r.update(infrastructure_error=False,native_pass=False,rtl_pass=False,
                 outcome='construction_nonconvergence' if isolated_gate else 'simulation_nonconvergence',
                 candidate_nonconvergence=proof,timeout_adjudication={'policy':'isolated repeated timeout AND candidate-only circular logic, native delta-state recurrence, or statically invariant host elaboration loop with native trace proof',
                   'original_result_sha256':hashlib.sha256((dest/'original_result.json').read_bytes()).hexdigest(),
                   'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'native_or_probe_execution_changed':False})
        if isolated_gate:
            r['c0_pass']=False
            save(rp.parent/'gate.json',{'accepted':False,'uses_functional_oracle':False,'candidate_nonconvergence':proof,'isolated_timeout_seconds':gate['seconds']})
        save(rp,r);outcomes.append({'key':j['key'],'outcome':r['outcome'],'confirmed_loop':True})
        build=(OUT/'build'/j['key']).resolve()
        if (OUT/'build').resolve() not in build.parents:raise RuntimeError('invalid build path')
        if build.exists():shutil.rmtree(build)
        print(json.dumps(outcomes[-1]),flush=True)
    save(OUT/'adjudication_summary.json',outcomes)
    if any(x.get('unresolved') for x in outcomes):raise RuntimeError('Unexplained infrastructure remains; no score imputed')

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--diagnostic':
        request=load(sys.argv[2]);dest=Path(request['destination'])
        try:proof=structure(request['job'],request['configuration'],dest)
        except Exception:proof={'confirmed_combinational_loop':False,'uses_functional_oracle':False,'error':traceback.format_exc()}
        save(dest/'diagnostic_response.json',proof)
    else:main()
