"""Unified sequential gates; exact official native_case retained as a module."""
import concurrent.futures, hashlib, json, os, signal, subprocess, sys, time, traceback, shutil
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path('/work');OUT=Path('/out')

def load(p):return json.loads(Path(p).read_text())
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);q=p.with_name(p.name+'.tmp');q.write_text(json.dumps(v,indent=2));os.replace(q,p)
def command(cmd, log, build, env, timeout):
    log.parent.mkdir(parents=True,exist_ok=True);build.mkdir(parents=True,exist_ok=True);start=time.monotonic()
    with log.open('w') as handle:
        p=subprocess.Popen(cmd,cwd=build,env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
        try:rc=p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait();rc=124
    return rc,time.monotonic()-start

def probe_record(text):
    # Python may emit UnusedElaboratable warnings at interpreter shutdown,
    # after the probe has printed its structured result. Keep every log line
    # and select the last actual probe record, not the last physical line.
    for line in reversed(text.splitlines()):
        try:r=json.loads(line)
        except (ValueError,TypeError):continue
        if isinstance(r,dict) and isinstance(r.get('constructible'),bool) and r.get('uses_functional_oracle') is False:
            return r
    return {'constructible':False,'uses_functional_oracle':False,'error':'gate_no_json','log_tail':text[-3000:]}

def nonconvergence(j,source,configuration,dest,build,env):
    # Called only after the same candidate timed out once in parallel and once
    # under a longer isolated serial limit. A timeout alone is never a failure.
    folder=dest/'timeout_diagnostic';log=folder/'diagnostic.log'
    rc,seconds=command(['python','/work/runtime/timeout_diagnostic.py',j['adapter_language'],str(source),
                        json.dumps(configuration),str(folder)],log,build,env,90)
    records=[]
    for line in log.read_text(errors='replace').splitlines():
        try:record=json.loads(line)
        except ValueError:continue
        if isinstance(record,dict) and record.get('uses_functional_oracle') is False:records.append(record)
    r=(records or [{}])[-1]|{'diagnostic_returncode':rc,'diagnostic_seconds':seconds}
    save(folder/'result.json',r)
    return r if rc==0 and r.get('confirmed_combinational_loop') is True else None

def evaluate(j,serial=False):
    key=j['key'];dest=OUT/'cases'/key;result_path=dest/'result.json'
    if result_path.exists() and not load(result_path).get('infrastructure_error'):
        prior=load(result_path)
        if prior.get('evaluation_fingerprint')!=load(ROOT/'configs/evaluation_fingerprint.json')['sha256']:raise RuntimeError('evaluation fingerprint changed')
        return prior
    gen=load(ROOT/'runs/cases'/key/'generation.json');result={**j,'evaluation_fingerprint':load(ROOT/'configs/evaluation_fingerprint.json')['sha256'],
         'c0_pass':False,'native_pass':False,'rtl_pass':False,'infrastructure_error':False,'native_evaluated':False,'rtl_evaluated':False}
    if gen['status']!='ready':
        result.update(outcome='output_failure',error=gen.get('error'));save(result_path,result);return result
    source=ROOT/'runs/cases'/key/'candidate.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==gen['source_sha256']
    result['source_sha256']=gen['source_sha256'];dest.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONPATH='/dataset:/work/runtime',HOME='/tmp',PYTHONDONTWRITEBYTECODE='1')
    build=OUT/'build'/key;probes=[]
    for i,cfg in enumerate(load(ROOT/'configs/public_configurations.json')[j['task']]):
        log=dest/f'gate_{i}.log';rc,seconds=command(['python','/work/runtime/construction_probe.py',j['adapter_language'],str(source),json.dumps(cfg)],log,build,env,120 if serial else 45)
        text=log.read_text(errors='replace')
        r=probe_record(text)
        if rc<0 or rc in [124,137] or 'gate_no_json'==r.get('error'):
            diagnostic=nonconvergence(j,source,cfg,dest,build,env) if serial and rc==124 else None
            if diagnostic:
                gate={'accepted':False,'uses_functional_oracle':False,'probes':probes,
                      'candidate_nonconvergence':diagnostic,'isolated_probe_timeout_seconds':seconds}
                save(dest/'gate.json',gate)
                result.update(outcome='construction_nonconvergence',candidate_nonconvergence=diagnostic)
                save(result_path,result);return result
            result.update(infrastructure_error=True,outcome='gate_infrastructure_error',
                          gate_infrastructure={'configuration_index':i,'returncode':rc,'seconds':seconds,'parsed_record':r});save(result_path,result);return result
        probes.append({'config':cfg,'seconds':seconds,'returncode':rc,**r})
    gate={'accepted':all(p['constructible'] for p in probes),'uses_functional_oracle':False,'probes':probes,
          'warning_free':not any(p.get('warnings') for p in probes)}
    save(dest/'gate.json',gate);result.update(c0_pass=gate['accepted'],gate_warning_free=gate['warning_free'],probe_seconds=sum(p['seconds'] for p in probes))
    if not gate['accepted']:result['outcome']='construction_error';save(result_path,result);return result
    # Execute the SHA-pinned official native_case.py in a separate process so
    # its build directories, timeout overrides and observers stay isolated.
    native=dest/'native';njob={**j,'case':key,'language':j['adapter_language']}
    save(dest/'native_job.json',njob)
    code="import json,native_case; from pathlib import Path; native_case.OUT=Path('/out/native'); original=native_case.command_run; native_case.command_run=lambda c,d,e,b,t: original(c,d,e,Path("+repr(str(build/'native'))+"),max(t,"+str(300 if serial else 120)+")); j=json.loads(Path("+repr(str(dest/'native_job.json'))+").read_text()); native_case.evaluate(j,'generate')"
    (build/'native').mkdir(parents=True,exist_ok=True)
    rc,seconds=command(['python','-c',code],dest/'native_wrapper.log',build,env,360 if serial else 180)
    official=OUT/'native/cases'/key/'result.json'
    if not official.exists():result.update(infrastructure_error=True,outcome='native_wrapper_failure');save(result_path,result);return result
    nr=load(official);native.mkdir(exist_ok=True)
    result.update(native=nr,native_evaluated=True,native_seconds=seconds,native_pass=bool(nr['passed']))
    if nr.get('infrastructure_error') or nr.get('returncode',0)<0 or rc!=0:
        construction=OUT/'native/cases'/key/'construction.json'
        cfg=load(construction)['config'] if construction.exists() else load(ROOT/'configs/public_configurations.json')[j['task']][0]
        diagnostic=nonconvergence(j,source,cfg,dest,build,env) if serial and nr.get('returncode')==124 else None
        if diagnostic:
            result.update(native_pass=False,outcome='simulation_nonconvergence',candidate_nonconvergence=diagnostic)
            save(result_path,result);return result
        result.update(infrastructure_error=True,outcome='native_infrastructure_error');save(result_path,result);return result
    if not nr['passed']:result['outcome']=nr['outcome'];save(result_path,result);return result
    rtl=dest/'rtl';rtl.mkdir(exist_ok=True)
    cmd=['python','-m','pytest','-q','-o','addopts=','--tb=short','--disable-warnings','--maxfail=1','--hypothesis-seed=20261022',
         '--junitxml='+str(rtl/'junit.xml'),'-p','rtl_plugin',str(Path('/dataset/dataset')/(j['task']+'_test.py')),'--'+j['adapter_language']+'='+str(source)]
    renv=env|{'CASE_OUTPUT':str(rtl),'CANDIDATE_LANGUAGE':j['adapter_language'],'EVAL_MODE':'rtl'}
    rc,seconds=command(cmd,rtl/'pytest.log',build/'rtl',renv,600 if serial else 240)
    nodes=ET.parse(rtl/'junit.xml').findall('.//testcase') if (rtl/'junit.xml').exists() else []
    skipped=sum(n.find('skipped') is not None for n in nodes);failures=sum(n.find('failure') is not None or n.find('error') is not None for n in nodes)
    text=(rtl/'pytest.log').read_text(errors='replace');infra=rc<0 or rc in [124,137] or not nodes or any(p in text for p in ['No space left on device','Cannot allocate memory','INTERNALERROR>'])
    passed=rc==0 and len(nodes)>skipped and failures==0
    result.update(rtl_evaluated=True,rtl_pass=passed,rtl_seconds=seconds,rtl={'passed':passed,'returncode':rc,'tests':len(nodes),'failures':failures,'seconds':seconds},
                  infrastructure_error=infra,outcome='passed' if passed else 'rtl_infrastructure_error' if infra else 'rtl_failure')
    save(result_path,result);print(json.dumps({'key':key,'c0':True,'native':True,'rtl':passed}),flush=True);return result

def main():
    jobs=load(ROOT/'configs/evaluation_queue.json');done=0;retry=[]
    def isolated(j):
        try:return evaluate(j)
        finally:
            build=(OUT/'build'/j['key']).resolve()
            if (OUT/'build').resolve() not in build.parents:raise RuntimeError('invalid build path')
            if build.exists():shutil.rmtree(build)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(isolated,j):j for j in jobs}
        for f in concurrent.futures.as_completed(futures):
            j=futures[f]
            try:r=f.result()
            except Exception:r={'infrastructure_error':True,'error':traceback.format_exc()}
            if r.get('infrastructure_error'):retry.append(j)
            done+=1;save(OUT/'progress.json',{'completed':done,'total':len(jobs),'serial_retry_pending':len(retry)})
    # Never convert unresolved infrastructure into a candidate failure. Retain
    # all attempts, retry alone, then stop on reproducible unresolved problems.
    for j in retry:
        key=j['key'];dest=OUT/'cases'/key
        for attempt in range(1,4):
            for folder in [dest,OUT/'native/cases'/key]:
                if folder.exists():
                    archive=folder.parent/(folder.name+f'.infra_attempt_{attempt}')
                    if not archive.exists():folder.rename(archive)
            r=evaluate(j,serial=True)
            if not r.get('infrastructure_error'):break
        if r.get('infrastructure_error'):
            save(OUT/'blocked.json',{'key':key,'reason':'serial retries unresolved; no score imputed'});raise RuntimeError('Unresolved infrastructure: '+key)
    save(OUT/'complete.json',{'complete':True,'jobs':len(jobs),'infra_unresolved':0})
if __name__=='__main__':main()
