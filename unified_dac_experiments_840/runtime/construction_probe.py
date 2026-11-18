"""Reference-blind, explicit reset assertion/release plus six clock probes."""
import json, sys, traceback, warnings

def probe(language, source, configuration):
    from pyhdl_eval.cfg import Config,InputPort,OutputPort
    from pyhdl_eval.core import dsls
    cfg=Config(parameters=configuration['parameters'],ports=[(n,InputPort(w) if d=='InputPort' else OutputPort(w)) for n,d,w in configuration['ports']])
    dut=None;observed=[]
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always');dut=dsls[language](source,cfg);dut.reset()
            for reset_value in [1,0]:
                if any(n=='reset' and d=='InputPort' for n,d,w in configuration['ports']):dut.write('reset',reset_value)
                for pattern in ['zero','one','allones']:
                    for n,d,w in configuration['ports']:
                        if d=='InputPort' and n not in ['clk','reset']:dut.write(n,0 if pattern=='zero' else 1 if pattern=='one' else (1<<w)-1)
                    dut.tick_phase0()
                    for n,d,w in configuration['ports']:
                        if d=='OutputPort':int(dut.read(n).uint())
                    dut.tick_phase1();observed.append({'reset':reset_value,'pattern':pattern})
        return {'constructible':True,'observed_cycles':len(observed),'stimulus':observed,
                'warnings':[str(w.message) for w in captured],'uses_functional_oracle':False}
    except Exception:return {'constructible':False,'traceback':traceback.format_exc(),'uses_functional_oracle':False}
    finally:
        if dut is not None:dut.cleanup()
if __name__=='__main__':
    result=probe(sys.argv[1],sys.argv[2],json.loads(sys.argv[3]));print(json.dumps(result));sys.exit(0 if result['constructible'] else 1)
