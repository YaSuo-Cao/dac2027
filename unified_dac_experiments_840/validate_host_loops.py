"""Candidate-only calibration of host nontermination attribution; no scoring."""
import ast,hashlib,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,'/work')
import adjudicate_in_container as diagnostic

def main():
    cases={
        'invariant':('while len(current)>1:\n    part=current[:len(current)//2]\n    pass',True),
        'shrinking':('while len(current)>1:\n    current=current[1:]',False),
        'break':('while len(current)>1:\n    break',False),
        'return':('while len(current)>1:\n    return current[0]',False),
        'attribute_write':('while len(current)>1:\n    current.bitwidth=1',False),
        'unknown_call':('while len(current)>1:\n    callback(current)',False),
        'alias':('while len(current)>1:\n    alias=current\n    alias.bitwidth=1',False),
        'shadow_len':('while len(current)>1:\n    len=current[0]',False),
        'body_branch':('while len(current)>1:\n    if nbits>1: break',False),
    }
    records=[]
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory)
        for name,(loop,expected) in cases.items():
            source=folder/(name+'.py')
            code='def TopModule(in_,nbits):\n    current=in_\n'+''.join('    '+line+'\n' for line in loop.splitlines())+'    return in_[0]\n'
            source.write_text(code)
            result=bool(diagnostic.invariant_length_loops(source));assert result==expected,(name,result)
            records.append({'fixture':name,'static_expected':expected,'passed':True})
        if Path('/dataset').exists():
            cfg={'parameters':{'nbits':4},'ports':[['in_','InputPort',4],['out','OutputPort',1]]}
            for name in ['invariant','shrinking','break']:
                import pyrtl
                pyrtl.reset_working_block()
                proof=diagnostic.host_elaboration_loop('pyrtl',folder/(name+'.py'),cfg)
                assert proof.get('confirmed_host_elaboration_loop')==(name=='invariant'),(name,proof)
                if name!='invariant':
                    from construction_probe import probe
                    native=probe('pyrtl',str(folder/(name+'.py')),cfg)
                    assert native['constructible'],(name,native)
                    proof['native_probe']=native
                records.append({'fixture':name,'dynamic_proof':proof,'passed':True})
            jobs=diagnostic.load('/work/configs/evaluation_queue.json')
            configurations=diagnostic.load('/work/configs/public_configurations.json')
            for job in jobs:
                result_path=diagnostic.OUT/'cases'/job['key']/'result.json'
                if not result_path.exists():continue
                result=diagnostic.load(result_path)
                if not result.get('infrastructure_error') or job['language']!='pyrtl':continue
                source=diagnostic.ROOT/'runs/cases'/job['key']/'candidate.py'
                cfg=configurations[job['task']][result['gate_infrastructure']['configuration_index']]
                pyrtl.reset_working_block()
                proof=diagnostic.host_elaboration_loop('pyrtl',source,cfg)
                assert proof.get('confirmed_host_elaboration_loop'),proof
                records.append({'job':job['key'],'frozen_candidate_proof':proof,'passed':True})
    result={'all_passed':True,'diagnostic_only':True,'reference_inputs_read':False,'frozen_runtime_changed':False,
            'adapter_sha256':hashlib.sha256(Path(diagnostic.__file__).read_bytes()).hexdigest(),'checks':records}
    if Path('/out').exists():diagnostic.save(Path('/out/host_loop_validation.json'),result)
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
