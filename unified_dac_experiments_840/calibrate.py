"""Five-language known-good/wrong fixtures; native and RTL infrastructure audit."""
from common import *
import remote

def main():
    task='Prob02p01_comb_wires_8b_passthru';jobs=[]
    for lang in LANGS:
        for kind in ['gold','wrong']:
            key=f'calibration/{task}/{lang}/{kind}'
            job={'key':key,'task':task,'language':lang,'adapter_language':ADAPTER[lang],'arm':kind,'instance':task+'/'+lang,'model':'handwritten_fixture'}
            directory=run_dir(job);directory.mkdir(parents=True,exist_ok=True)
            src=HISTORY/'hcl_full168_phase0_20261022/fixtures'/ADAPTER[lang]/('dataset_'+kind+'.py')
            (directory/'candidate.py').write_bytes(src.read_bytes());save(directory/'generation.json',{'status':'ready','source_sha256':sha(directory/'candidate.py')})
            jobs.append(job)
    # Regression: each source raises a real Amaranth construction exception,
    # then emits UnusedElaboratable warnings after the structured probe JSON.
    # These must be construction failures, never infrastructure failures.
    for task in ['Prob05p07_comb_mux_4b_1to5','Prob05p08_comb_mux_1b_128to1',
                 'Prob07p08_comb_arith_8b_rotator','Prob07p11_comb_arith_8b_fxp_umul']:
        for arm in (['Direct','Gen'] if 'rotator' in task else ['Direct']):
            key=f'calibration/{task}/amaranth/construction_negative_{arm}'
            job={'key':key,'task':task,'language':'amaranth','adapter_language':'amaranth','arm':'construction_negative',
                 'instance':task+'/amaranth','model':'frozen_regression_fixture'}
            directory=run_dir(job);directory.mkdir(parents=True,exist_ok=True)
            src=ROOT/'runs/exp1'/task/'amaranth'/arm/'candidate.py'
            (directory/'candidate.py').write_bytes(src.read_bytes())
            save(directory/'generation.json',{'status':'ready','source_sha256':sha(directory/'candidate.py')})
            jobs.append(job)
    for task in ['Prob06p14_comb_codes_100b_parity','Prob07p05_comb_arith_100b_popcount','Prob07p17_comb_arith_4x8b_sorter']:
        key=f'calibration/{task}/amaranth/nonconvergence_negative'
        job={'key':key,'task':task,'language':'amaranth','adapter_language':'amaranth','arm':'nonconvergence_negative',
             'instance':task+'/amaranth','model':'frozen_regression_fixture'}
        directory=run_dir(job);directory.mkdir(parents=True,exist_ok=True)
        (directory/'candidate.py').write_bytes((ROOT/'runs/exp1'/task/'amaranth/Gen/candidate.py').read_bytes())
        save(directory/'generation.json',{'status':'ready','source_sha256':sha(directory/'candidate.py')});jobs.append(job)
    save(ROOT/'configs/calibration_jobs.json',jobs);remote.execute(jobs)
    results=[load(result_dir(j)/'result.json') for j in jobs]
    for r in results:
        if r['arm']=='gold':assert r['c0_pass'] and r['native_pass'] and r['rtl_pass'],r
        elif r['arm']=='wrong':assert r['c0_pass'] and not r['native_pass'] and r['outcome']=='functional_mismatch',r
        elif r['arm']=='construction_negative':assert not r['c0_pass'] and not r['infrastructure_error'] and r['outcome']=='construction_error',r
        else:assert not r['infrastructure_error'] and not r['native_pass'] and r['outcome'] in ['construction_nonconvergence','simulation_nonconvergence'],r
    save(ROOT/'analysis/calibration.json',{'passed':True,'fixtures':len(results),'results':results})
    print('ALL FIVE LANGUAGE NATIVE/RTL CALIBRATIONS PASSED')
if __name__=='__main__':main()
