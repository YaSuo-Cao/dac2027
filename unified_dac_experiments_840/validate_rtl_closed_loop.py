"""Offline regression for acceptance, budget and diagnostic-source isolation."""
import copy, json, tempfile
from pathlib import Path
from unittest.mock import patch
import rtl_closed_loop as loop
from common import save,load


def main():
    initial={'key':'initial','task':'fixture','instance':'fixture/myhdl','language':'myhdl','arm':'Gen'}
    trial={**initial,'key':'trial','arm':'RTL-L','request_sha256':'request'}
    results={
        'initial':{'c0_pass':True,'native_pass':True,'rtl_pass':False,'infrastructure_error':False,'source_sha256':'src'},
        'trial':{'c0_pass':False,'native_pass':False,'rtl_pass':False,'infrastructure_error':False}}
    base={'method':'RTL-Aware-B5','instance':initial['instance'],'task':'fixture','language':'myhdl',
        'initial':initial,'current':initial,'accepted':initial,'attempts':[],'stop_reason':None,'contract_failures':[]}
    with tempfile.TemporaryDirectory(prefix='rtl_closed_loop_regression_') as folder:
        root=Path(folder);out=root/'analysis';out.mkdir()
        with patch.object(loop,'OUT',out),patch.object(loop.repair,'evaluation',side_effect=lambda j:results[j['key']]),patch.object(loop,'run_dir',side_effect=lambda j:root/'runs'/j['key']):
            assert loop.stop(base) is None, 'RTL failure must continue after native success'
            assert loop.stop({**base,'method':'NativeOnly-B5'})=='native_passed'
            assert loop.stop({**base,'attempts':[{}]*4})=='repair_budget_exhausted'
            results['initial']['rtl_pass']=True
            assert loop.stop(base)=='rtl_passed'
            results['initial']['rtl_pass']=False
            save(out/'round_0_states.json',[base])
            save(out/'round_1_plans.json',[{'method':'RTL-Aware-B5','instance':initial['instance'],
                'start_key':'initial','phase':'rtl','arm':'RTL-L','job_key':'trial'}])
            save(root/'runs/trial/generation.json',{'status':'output_failure','source_sha256':None})
            state=loop.finish(1,[trial])[0]
            assert state['accepted']['key']=='initial' and state['current']['key']=='trial'
            assert len(state['attempts'])==1 and not state['attempts'][0]['accepted_by_blind_gate']
            assert loop.feedback_phase(trial)=='construction'
            h=loop.history(state)
            assert h[0]['phase']=='rtl' and h[0]['repair_index']==1
            # C0 is the only replacement criterion, even when native regresses.
            results['trial']['c0_pass']=True
            save(out/'round_0_states.json',[base])
            state=loop.finish(1,[trial])[0]
            assert state['accepted']['key']=='trial' and loop.feedback_phase(trial)=='native'
            # Read message attributes only, never a traceback/test-source body.
            rtl=root/'result/rtl';rtl.mkdir(parents=True)
            (rtl/'junit.xml').write_text('<testsuites><testcase><failure message="myhdl.ConversionError: bad construct">SECRET_TEST_OR_REFERENCE_SOURCE</failure></testcase></testsuites>')
            with patch.object(loop,'result_dir',return_value=rtl.parent):
                feedback=loop.rtl_feedback(initial)
            assert 'SECRET_TEST' not in json.dumps(feedback)
            assert feedback['failure_kind']=='lowering_or_compiler'
            assert feedback['reference_source_accessed'] is False
            # No outcome selection among trials: latest C0-passing wins.
            assert state['attempts'][0]['accepted_by_blind_gate'] is True
    print(json.dumps({'passed':True,'model_calls':0,'simulations':0,'checks':[
        'native-only and RTL-aware early-stop differ','maximum four repairs','rejected output consumes slot',
        'gate-rejected source becomes next feedback target','accepted predecessor retained',
        'C0-only candidate replacement','diagnostic attributes exclude traceback/test source']}))


if __name__=='__main__':main()
