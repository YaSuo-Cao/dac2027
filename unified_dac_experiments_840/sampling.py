"""Five fresh same-distribution samples on the complete 840 population."""
from common import *

def main():
    initial=load(ROOT/'configs/exp1_jobs.json');requests0=load(ROOT/'configs/exp1_requests.json')
    jobs=[];requests={}
    for j in initial:
        if j['arm'] not in ['Direct','Gen']:continue
        for sample in range(1,6):
            request={**requests0[j['key']],'temperature':0.7,'seed':SEED+sample-1}
            key=f'exp3/{j["task"]}/{j["language"]}/{j["arm"]}/s{sample}'
            jobs.append(registered_job(key,j['task'],j['language'],j['arm'],request,experiment=3,sample=sample))
            requests[key]=request
    assert len(jobs)==8400
    save(ROOT/'configs/exp3_jobs.json',jobs);save(ROOT/'configs/exp3_requests.json',requests)
    print(json.dumps({'jobs':len(jobs),'temperature':0.7,'samples_per_arm_instance':5,'population':840}))
if __name__=='__main__':main()
