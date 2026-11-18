"""Diagnostic calibration only; never changes official candidate scores."""
import json,sys
from pathlib import Path
sys.path.insert(0,'/work')
import adjudicate_in_container as a
configs=a.load(a.ROOT/'configs/public_configurations.json')
rows=[]
for language,observer in [('migen',a.native_delta_cycle),('amaranth',a.amaranth_delta_cycle)]:
    for arm in ['gold','wrong']:
        task='Prob02p01_comb_wires_8b_passthru'
        source=a.ROOT/'runs/cases/calibration'/task/language/arm/'candidate.py'
        result=observer(source,configs[task][0])
        assert result['native_probe']['constructible'] and not result.get('confirmed_native_delta_cycle'),result
        rows.append({'language':language,'fixture':arm,'passed':True})
        mixed=observer(source,configs[task][0],mixed_patterns=True)
        assert mixed['native_probe']['constructible'] and not mixed.get('confirmed_native_delta_cycle'),mixed
        rows.append({'language':language,'fixture':arm,'mixed_candidate_only_inputs':True,'passed':True})
jobs=a.load(a.ROOT/'configs/evaluation_queue.json');checked=set()
for j in jobs:
    if j['language']!='amaranth' or j['task'] in checked or len(checked)>=4:continue
    cfg=configs[j['task']][0]
    if not any(n=='clk' for n,d,w in cfg['ports']):continue
    rp=a.OUT/'cases'/j['key']/'result.json'
    if not rp.exists() or not a.load(rp).get('c0_pass'):continue
    result=a.amaranth_delta_cycle(a.ROOT/'runs/cases'/j['key']/'candidate.py',cfg)
    assert result['native_probe']['constructible'] and not result.get('confirmed_native_delta_cycle'),result
    checked.add(j['task']);rows.append({'key':j['key'],'clocked_positive':True,'passed':True})
task='Prob15p02_seq_arb_4in_rotating'
key='exp1/'+task+'/amaranth/FullDocRAG'
rp=a.OUT/'cases'/key/'result.json';r=a.load(rp)
cfg=configs[task][r['gate_infrastructure'].get('configuration_index',0)]
result=a.amaranth_delta_cycle(a.ROOT/'runs/cases'/key/'candidate.py',cfg)
assert result.get('confirmed_native_delta_cycle') and not result['native_probe']['constructible'],result
rows.append({'key':key,'cyclic_negative':True,'diagnostic':result,'passed':True})
dest=a.OUT/'diagnostic_validation/amaranth_bounded_worker';dest.mkdir(parents=True,exist_ok=True)
isolated=a.bounded_structure({'key':key,'adapter_language':'amaranth'},cfg,dest)
assert isolated.get('confirmed_native_delta_cycle'),isolated
rows.append({'key':key,'isolated_diagnostic_worker':True,'passed':True})
key='repairs/deepseek-v4.1-flash/623f5e02ea52304ba50ba7d46367be2782f9a18739b96c93a546435cd1fc78b0'
source=a.ROOT/'runs/cases'/key/'candidate.py'
if source.exists():
    cfg=configs['Prob07p17_comb_arith_4x8b_sorter'][0]
    uniform=a.native_delta_cycle(source,cfg)
    mixed=a.native_delta_cycle(source,cfg,mixed_patterns=True)
    assert uniform['native_probe']['constructible'] and not uniform.get('confirmed_native_delta_cycle'),uniform
    assert mixed.get('confirmed_native_delta_cycle'),mixed
    rows.append({'key':key,'uniform_smoke_passes':True,'independent_mixed_input_cycle_proof':mixed,'passed':True})
record={'diagnostic_only':True,'frozen_evaluator_unchanged':True,'all_passed':True,'rows':rows,
    'tool_sha256':a.hashlib.sha256(Path(a.__file__).read_bytes()).hexdigest()}
a.save(a.OUT/'native_delta_observer_validation.json',record)
print(json.dumps(record),flush=True)
