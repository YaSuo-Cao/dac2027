"""Evaluate only generation-complete candidates alongside further API work."""
import json,threading,time
from common import ROOT,save

class EvaluationStream:
    def __init__(self,stage,stop_generation,evaluator=None,minimum=16,maximum=256):
        if evaluator is None:
            import remote
            evaluator=remote.execute
        self.stage=stage;self.stop_generation=stop_generation;self.evaluator=evaluator
        self.minimum=minimum;self.maximum=maximum;self.condition=threading.Condition()
        self.pending=[];self.seen=set();self.finished=False;self.error=None;self.evaluated=0
        self.thread=threading.Thread(target=self.work,name='official-evaluation-stream');self.thread.start()
    def submit(self,job):
        with self.condition:
            if job['key'] not in self.seen:
                self.pending.append(job);self.seen.add(job['key']);self.condition.notify()
    def work(self):
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(lambda:len(self.pending)>=self.minimum or self.finished)
                    if not self.pending and self.finished:return
                    batch=self.pending[:self.maximum];del self.pending[:self.maximum]
                print(json.dumps({'stream_evaluation_started':self.stage,'batch_jobs':len(batch)}),flush=True)
                self.evaluator(batch);self.evaluated+=len(batch)
                save(ROOT/'progress'/(self.stage+'_evaluation_stream.json'),{'stage':self.stage,'evaluated_jobs':self.evaluated,
                    'submitted_jobs':len(self.seen),'pending_jobs':len(self.pending),'last_batch_jobs':len(batch),'updated_utc':time.time()})
        except Exception as exc:
            self.error=exc;self.stop_generation.set()
            save(ROOT/'progress'/(self.stage+'_evaluation_stream_error.json'),{'stage':self.stage,'error':str(exc),'updated_utc':time.time()})
            print(json.dumps({'stream_evaluation_failed':self.stage,'error':str(exc)[-2000:]}),flush=True)
    def close(self):
        with self.condition:self.finished=True;self.condition.notify_all()
        self.thread.join()
        if self.error is not None:raise RuntimeError('Official evaluation stream failed: '+str(self.error)) from self.error
