"""Observe native official pytest without changing values/assertions/adapters."""
import inspect, json, os, traceback
from pathlib import Path
import pytest
from slicer import trace_text

OUT = Path(os.environ['OBS_OUTPUT']); LANG = os.environ['OBS_LANGUAGE']
SOURCE = Path(os.environ['OBS_SOURCE']).resolve() if os.environ.get('OBS_SOURCE') else None
CURRENT = {}; LOCATIONS = {}; ACTIVE = ''; EVENTS = []
MULTI=[];MULTI_KEYS=set()

def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, default=str), encoding='utf-8')

def integer(v): return v.uint() if hasattr(v, 'uint') else int(v)

def config_record(cfg):
    return {'parameters': cfg.parameters, 'ports': [(n, type(p).__name__, p.nbits()) for n,p in cfg.ports],
            'dead_cycles': cfg.dead_cycles, 'dead_cycle_inputs': cfg.dead_cycle_inputs}

def cone(port):
    import pyrtl
    block = pyrtl.working_block(); block.sanity_check()
    output = block.get_wirevector_by_name(port, strict=True)
    producers = {d:n for n in block.logic for d in n.dests}; seen=set(); selected=set(); pending=[output]
    while pending:
        w=pending.pop()
        if w in seen: continue
        seen.add(w); n=producers.get(w)
        if n is None: continue
        selected.add(n); pending.extend(n.args)
        if n.op=='m':
            for wn in getattr(n.op_param[1], 'writeport_nets', []):
                selected.add(wn); pending.extend(wn.args)
    records=[{'op':n.op,'net':str(n),'source_bindings':LOCATIONS.get(n,[])} for n in sorted(selected,key=str)]
    return {'block_net_count':len(block.logic),'net_count':len(records),'nets':records}

def pytest_collection_modifyitems(config, items):
    # Official framework tests parametrize all six DSLs. Select only native HCLs.
    if os.environ.get('OBS_EXAMPLES') == '1':
        keep=[]; drop=[]
        for item in items:
            d=getattr(item,'callspec',None)
            (keep if d and d.params.get('dslstr')==LANG else drop).append(item)
        items[:]=keep; config.hook.pytest_deselected(items=drop)

def pytest_runtest_setup(item):
    global ACTIVE
    ACTIVE=item.nodeid

def pytest_runtest_logreport(report):
    if report.failed:
        write('exception.json', {'nodeid':report.nodeid,'phase':report.when,
                                'traceback':str(report.longrepr),'last_construction':CURRENT})

def pytest_sessionstart(session):
    import pyhdl_eval.core as core
    if LANG=='pyrtl':
        import pyrtl
        original_add=pyrtl.Block.add_net
        def add(self,net):
            original_add(self,net); frame=inspect.currentframe().f_back; bindings=[]
            while frame:
                path=Path(frame.f_code.co_filename).resolve()
                if path==CURRENT.get('source'):
                    code=path.read_text().splitlines(); line=frame.f_lineno
                    bindings.append({'line':line,'text':code[line-1] if line<=len(code) else ''})
                frame=frame.f_back
            if bindings: LOCATIONS[net]=bindings
        pyrtl.Block.add_net=add
    original=core.dsls[LANG]
    def factory(file,cfg):
        CURRENT.clear(); LOCATIONS.clear()
        source=SOURCE or Path(file).resolve()
        CURRENT.update(config=config_record(cfg), source=source, factory_returned=False)
        write('construction.json', {**CURRENT,'source':str(source)})
        try: dut=original(str(source),cfg)
        except Exception:
            write('construction_exception.json',{'config':CURRENT['config'],'traceback':traceback.format_exc()})
            raise
        CURRENT['factory_returned']=True
        EVENTS.append({'config':CURRENT['config'],'factory_returned':True})
        write('construction.json',{**CURRENT,'source':str(source)})
        write('construction_events.json',EVENTS)
        return dut
    core.dsls[LANG]=factory
    cls=core.TestHarness; reset=cls.reset; wr=cls.write; tick=cls.tick_phase0; check=cls.check
    def r(self):
        self._obs_inputs={};self._obs_history=[]
        return reset(self)
    def w(self,name,value):
        self._obs_inputs[name]=integer(value);return wr(self,name,value)
    def t(self):
        answer=tick(self)
        self._obs_history.append({'cycle':self.get_cycle_count(),'inputs':dict(self._obs_inputs)})
        return answer
    def c(self,port):
        expected=integer(self.ref.read(port));actual=integer(self.dut.read(port))
        if expected!=actual:
            f={'test_nodeid':ACTIVE,'config':CURRENT.get('config'),'cycle':self.get_cycle_count(),
               'failed_output':port,'expected':expected,'actual':actual,'input_sequence':self._obs_history,
               'phase':'after tick_phase0, before tick_phase1, including dead cycles'}
            write('failure.json',f)
            try:
                runtime=cone(port) if LANG=='pyrtl' else None
                if runtime: write('runtime_cone.json',runtime)
                output_names=[n for n,d,w in CURRENT['config']['ports'] if d=='OutputPort'] if LANG=='pyrtl' else None
                trace=trace_text(CURRENT['source'].read_text(),port,runtime,output_names)
                write('trace.json',trace)
                # Keep actual assertions unchanged. Deduplicate repeated Hypothesis
                # executions using their complete failing prefix, not just node ID.
                key=json.dumps({k:v for k,v in f.items() if k not in ['test_nodeid','phase']},sort_keys=True)
                if key not in MULTI_KEYS and len(MULTI)<5:
                    MULTI_KEYS.add(key);MULTI.append({**f,'T':trace})
                    write('F_multi.json',{'counterexamples':MULTI,'max_counterexamples':5,
                          'deduplication':'configuration, port, cycle, expected/actual, complete input prefix',
                          'actual_native_assertions_preserved':True})
            except Exception:write('trace.json',{'nonempty':False,'traceback':traceback.format_exc()})
        if os.environ.get('OBS_MULTI_STOP')=='1' and expected!=actual and len(MULTI)>=5:
            try:check(self,port)
            except AssertionError:
                write('capture_complete.json',{'counterexamples':len(MULTI),'original_official_assertion_raised':True,
                    'diagnostic_only':True,'reason':'requested first five distinct actual counterexamples collected'})
                pytest.exit('F_multi diagnostic complete: five distinct official counterexamples captured',returncode=1)
        return check(self,port)
    cls.reset=r;cls.write=w;cls.tick_phase0=t;cls.check=c
