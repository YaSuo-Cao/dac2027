"""One case inside read-only/no-network official image. No candidate RTL export."""
import hashlib, json, os, signal, subprocess, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path('/work');DATA=Path('/dataset');OUT=Path('/out')
def load(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2))

def command_run(command,dest,env,build,timeout):
    start=time.monotonic()
    with dest.open('w') as log:
        p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,cwd=build,start_new_session=True)
        try:rc=p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait();rc=124
    return rc,time.monotonic()-start

def evaluate(job,phase):
    directory=ROOT/'runs/cases'/job['case'];dest=OUT/'cases'/job['case'];result_path=dest/'result.json'
    if result_path.exists():
        prior=load(result_path)
        if not prior.get('infrastructure_error'):return prior
    if not (directory/'generation.json').exists():return None
    gen=load(directory/'generation.json');dest.mkdir(parents=True,exist_ok=True)
    if gen['status']!='ready':
        result={**job,'passed':False,'outcome':'construction_error','subreason':'output_failure','error':gen.get('error'),
                'gate_accepted':False if phase=='repair' else None,'source_available':False}
        save(result_path,result);return result
    source=directory/'candidate.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==gen['source_sha256']
    build=OUT/'build'/job['task'];build.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONPATH='/dataset:/work/runtime',PYTHONDONTWRITEBYTECODE='1',HOME='/tmp',
             OBS_OUTPUT=str(dest),OBS_SOURCE=str(source),OBS_LANGUAGE=job['language'],OBS_EXAMPLES='0')
    gate=None
    if phase=='repair':
        probes=[]
        for i,cfg in enumerate(load(ROOT/'configs/public_configurations.json')[job['task']]):
            log=dest/f'gate_{i}.log'
            rc,seconds=command_run(['python','/work/runtime/construction_probe.py',job['language'],str(source),json.dumps(cfg)],log,env,build,30)
            text=log.read_text(errors='replace')
            try:record=json.loads(text.strip().splitlines()[-1])
            except Exception:record={'constructible':False,'error':'probe_timeout' if rc==124 else 'probe_did_not_return_json','log_tail':text[-8000:]}
            probes.append({'config':cfg,'returncode':rc,'seconds':seconds,**record})
        gate={'accepted':all(p['constructible'] for p in probes),'uses_functional_oracle':False,'probes':probes}
        save(dest/'gate.json',gate)
    command=['python','-m','pytest','-q','-o','addopts=','--tb=short','--disable-warnings','--maxfail=1',
             '--hypothesis-seed=20261022','--junitxml='+str(dest/'junit.xml'),'-p','observer',
             str(DATA/'dataset'/(job['task']+'_test.py')),'--'+job['language']+'='+str(source)]
    rc,seconds=command_run(command,dest/'pytest.log',env,build,120)
    nodes=ET.parse(dest/'junit.xml').findall('.//testcase') if (dest/'junit.xml').exists() else []
    failures=sum(n.find('failure') is not None or n.find('error') is not None for n in nodes)
    skipped=sum(n.find('skipped') is not None for n in nodes)
    passed=rc==0 and len(nodes)>skipped and failures==0
    text=(dest/'pytest.log').read_text(errors='replace')
    infrastructure=rc in [124,137] or not nodes or (rc==0 and len(nodes)==skipped)
    infra_patterns=['command "verilator','verilator failed','cannot find -l','No space left on device','Cannot allocate memory','ModuleNotFoundError: No module named \'pyhdl_eval\'','INTERNALERROR>']
    infrastructure=infrastructure or any(s in text for s in infra_patterns)
    outcome='passed' if passed else 'functional_mismatch' if (dest/'failure.json').exists() and 'does not match between ref and dut' in text else 'construction_error'
    result={**job,'source_sha256':gen['source_sha256'],'passed':passed,'outcome':outcome,'returncode':rc,'seconds':seconds,
            'tests':len(nodes),'skipped':skipped,'failures':failures,'infrastructure_error':bool(infrastructure),
            'gate_accepted':gate['accepted'] and outcome!='construction_error' if gate else None,'candidate_exported':False}
    if infrastructure:result['outcome']='infrastructure_error';result['passed']=False
    save(result_path,result);return result

def main(task,phase):
    queue=load(ROOT/'configs'/('generation_queue.json' if phase=='generate' else 'repair_queue.json'))
    for job in queue:
        if job['task']!=task:continue
        result=evaluate(job,phase)
        if result is not None:
            print(json.dumps({'case':job['case'],'outcome':result['outcome']}),flush=True)
            if result.get('infrastructure_error'):raise RuntimeError('Infrastructure evaluation stopped: '+job['case'])

if __name__=='__main__':main(sys.argv[1],sys.argv[2])
