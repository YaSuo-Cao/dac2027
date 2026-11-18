"""Bounded concurrent model calls, immutable cache, and lossless parser ledger."""
from __future__ import annotations
import argparse, ast, concurrent.futures, collections, heapq, re, sys, threading, time
from common import *
import api_run

class RetryDeferred(Exception):
    def __init__(self,next_attempt,delay,status):
        self.next_attempt=next_attempt;self.delay=delay;self.status=status

class RequestPacer:
    """Cap new HTTP starts while retry waits release their worker slots."""
    def __init__(self,interval=1.0):self.interval=interval;self.lock=threading.Lock();self.next_start=0.0
    def acquire(self,stop):
        with self.lock:
            delay=max(0,self.next_start-time.monotonic())
            if stop.wait(delay):raise RuntimeError('provider batch stopped')
            self.next_start=time.monotonic()+self.interval

def extract(response):
    choice=response['choices'][0];text=choice.get('message',{}).get('content') or ''
    if choice.get('finish_reason')=='length':raise ValueError('output_truncated')
    text=re.sub(r'<think>.*?</think>','',text,flags=re.S).strip()
    tags=re.findall(r'<CODE>\s*(.*?)\s*</CODE>',text,re.S|re.I)
    markdown=re.findall(r'```(?:python|py)?\s*\n(.*?)```',text,re.S|re.I)
    sources=tags or markdown or ([text] if re.search(r'(?m)^(?:class|def) TopModule\b',text) else [])
    if len(sources)!=1:raise ValueError('expected_one_complete_source_block')
    code=sources[0].strip()+'\n';tree=ast.parse(code)
    if not any(isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name=='TopModule' for n in tree.body):
        raise ValueError('missing_TopModule')
    return code,text,choice.get('finish_reason')

def perform(job,request,key,stop,retry_offset=0,defer_retries=False,pacer=None):
    directory=run_dir(job);directory.mkdir(parents=True,exist_ok=True)
    identity=canonical(request)
    if (directory/'request.json').exists() and canonical(load(directory/'request.json'))!=identity:
        raise ValueError('immutable request differs: '+job['key'])
    save(directory/'request.json',request)
    response_path=directory/'response.json'
    if response_path.exists():response=load(response_path)
    else:
        for retry in range(retry_offset,24):
            if stop.is_set():raise RuntimeError('provider batch stopped')
            if pacer is not None:pacer.acquire(stop)
            started=time.monotonic()
            # The provider requires a session header. Reconnect only after an
            # explicit overload receipt; keep the canonical request unchanged.
            overloads=sum(load(p).get('http_status')==429 for p in (directory/'attempts').glob('*.json'))
            session='unified840-'+identity[:28]+('-reconnect-'+str(overloads) if overloads else '')
            try:r=api_run.transport(request,key,session)
            except Exception as exc:r={'status':0,'body':str(exc).replace(key,'[REDACTED]')}
            info={'http_status':r.get('status'),'seconds':time.monotonic()-started,'request_sha256':identity,
                  'transport_session':session,
                  'billing_unknown':r.get('status',0)==0 or r.get('status',0)>=500}
            if r.get('status')==200:
                try:response=json.loads(r['body'])
                except ValueError:
                    rejected=directory/'rejected_responses'/f'{time.time_ns()}.txt';rejected.parent.mkdir(parents=True,exist_ok=True)
                    rejected.write_text(str(r.get('body','')).replace(key,'[REDACTED]'),encoding='utf-8')
                    info.update(billing_unknown=True,error='HTTP 200 body is not JSON',raw_body_sha256=sha(rejected))
                    save(directory/'attempts'/f'{time.time_ns()}.json',info)
                    stop.set();raise RuntimeError('Malformed HTTP 200 body retained; billing unresolved, no score assigned')
                info.update(response_id=response.get('id'),returned_model=response.get('model'),usage=response.get('usage'))
                save(directory/'attempts'/f'{time.time_ns()}.json',info)
                if response.get('model')!=request['model'] or not response.get('choices'):
                    save(directory/'rejected_responses'/f'{time.time_ns()}.json',response)
                    stop.set();raise RuntimeError('wrong returned model / missing choices')
                save(response_path,response);break
            info['error']=str(r.get('body','')).replace(key,'[REDACTED]')[:2000]
            save(directory/'attempts'/f'{time.time_ns()}.json',info)
            if r.get('status') not in [0,429,500,502,503,504]:
                stop.set();raise RuntimeError('API unavailable: '+str(r.get('status'))+' '+info['error'])
            if retry==23:raise RuntimeError('transport retries exhausted; response remains pending')
            # Overload rejections leave the immutable request pending.
            # Longer backoff avoids synchronized bursts during service load.
            delay=min(60,10*2**min(retry,3)) if r.get('status')==429 else min(60,2**min(retry,6))
            print(json.dumps({'provider_retry':r.get('status'),'job_key':job['key'],'attempt':retry+1,'wait_seconds':delay}),flush=True)
            if defer_retries:raise RetryDeferred(retry+1,delay,r.get('status'))
            if stop.wait(delay):raise RuntimeError('provider batch stopped')
    if response.get('model')!=request['model']:raise ValueError('returned model mismatch')
    result={**job,'request_sha256':identity,'status':'output_failure','usage':response.get('usage',{}),
            'response_sha256':sha(response_path),'returned_model':response.get('model')}
    raw=response['choices'][0].get('message',{}).get('content') or ''
    (directory/'raw_output.txt').write_text(raw,encoding='utf-8')
    try:
        if job.get('kind')=='contract':
            if response['choices'][0].get('finish_reason')=='length':raise ValueError('contract_truncated')
            text=re.sub(r'<think>.*?</think>','',raw,flags=re.S).strip()
            text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
            contract=json.loads(text)
            required=['interface_parameters','datapath_guard_rules','state_transition_invariants','ambiguities']
            if not isinstance(contract,dict) or any(k not in contract for k in required):raise ValueError('contract_schema_incomplete')
            save(directory/'contract.json',contract);result.update(status='contract_ready',contract_sha256=sha(directory/'contract.json'))
        else:
            code,_,finish=extract(response);(directory/'candidate.py').write_text(code,encoding='utf-8',newline='\n')
            result.update(status='ready',source_sha256=sha(directory/'candidate.py'),finish_reason=finish)
    except (ValueError,SyntaxError) as exc:result['error']=str(exc)
    save(directory/'generation.json',result)
    return result

def scheduled(jobs,requests,key,workers,on_complete,pacer=None,external_stop=None):
    # A throttled job retains its own backoff, but cannot occupy the entire
    # batch while unrelated frozen requests have not had a first attempt.
    stop=external_stop if external_stop is not None else threading.Event();ready=collections.deque((j,0) for j in jobs)
    delayed=[];sequence=0;futures={};errors=[];pacer=pacer or RequestPacer()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        while ready or delayed or futures:
            now=time.monotonic()
            while delayed and delayed[0][0]<=now:
                _,_,j,attempt=heapq.heappop(delayed);ready.append((j,attempt))
            if stop.is_set():
                cancelled=[j for j,_ in ready]+[item[2] for item in delayed];ready.clear();delayed.clear()
                for j in cancelled:
                    error={'key':j['key'],'error':'provider batch stopped; frozen request remains pending'}
                    errors.append(error);on_complete(j,'infrastructure_error',error)
            while ready and len(futures)<workers and not stop.is_set():
                j,attempt=ready.popleft()
                f=pool.submit(perform,j,requests[j['key']],key,stop,attempt,True,pacer);futures[f]=j
            if not futures:
                if delayed:stop.wait(min(60,max(0,delayed[0][0]-time.monotonic())))
                continue
            timeout=min(60,max(0,delayed[0][0]-time.monotonic())) if delayed and len(futures)<workers else 60
            done,_=concurrent.futures.wait(futures,timeout=timeout,return_when=concurrent.futures.FIRST_COMPLETED)
            for f in done:
                j=futures.pop(f)
                error=None
                try:r=f.result();status=r['status']
                except RetryDeferred as exc:
                    sequence+=1;heapq.heappush(delayed,(time.monotonic()+exc.delay,sequence,j,exc.next_attempt))
                    continue
                except Exception as exc:
                    error={'key':j['key'],'error':str(exc).replace(key,'[REDACTED]')}
                    errors.append(error);stop.set();status='infrastructure_error'
                on_complete(j,status,error)
    return errors

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',default='exp1');p.add_argument('--workers',type=int,default=4);p.add_argument('--limit',type=int);p.add_argument('--no-stream-evaluation',action='store_true');a=p.parse_args()
    jobs=load(ROOT/'configs'/(a.stage+'_jobs.json'));requests=load(ROOT/'configs'/(a.stage+'_requests.json'))
    if a.limit:jobs=jobs[:a.limit]
    key=api_run.credential();started=time.monotonic();counts={};errors=[];completed=0;stop=threading.Event();stream=None
    policy=ROOT/'protocol/stream_evaluation.json'
    if not a.no_stream_evaluation and policy.exists() and load(policy).get('enabled') and jobs and all(j.get('kind')!='contract' and j.get('language') in LANGS for j in jobs):
        from evaluation_stream import EvaluationStream
        stream=EvaluationStream(a.stage,stop)
    def completed_job(j,status,error):
        nonlocal completed
        if error:errors.append(error)
        completed+=1;counts[status]=counts.get(status,0)+1
        save(ROOT/'progress'/(a.stage+'_generation.json'),{'complete':completed==len(jobs) and not errors,'completed':completed,'total':len(jobs),'counts':counts,'errors':errors[-8:],'seconds':time.monotonic()-started})
        if stream is not None and status in ['ready','output_failure']:stream.submit(j)
        if completed%16==0 or completed==len(jobs):print(json.dumps({'stage':a.stage,'completed':completed,'total':len(jobs),'counts':counts}),flush=True)
    try:scheduled(jobs,requests,key,a.workers,completed_job,external_stop=stop)
    finally:
        if stream is not None:stream.close()
    if errors:
        save(ROOT/'progress'/(a.stage+'_generation_errors.json'),errors)
        raise SystemExit(2)
if __name__=='__main__':main()
