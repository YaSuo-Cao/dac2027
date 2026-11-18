"""Resume Claude under the frozen output cap; never invent a failed contract."""
from __future__ import annotations
import subprocess, sys, time, traceback
from common import *
import contract_flow, pipelines, remote, ledger

CLAUDE='claude-haiku-5-5'

def command(script,*args):
    subprocess.run([sys.executable,str(ROOT/script),*map(str,args)],cwd=WORK,check=True)

def progress(phase):
    save(ROOT/'progress/orchestrator.json',{'status':'running','module':4,
        'phase':phase,'model':CLAUDE,'population':840,'pid':os.getpid(),'updated_utc':time.time()})

def main():
    try:
        progress('claude_contract_resolution_frozen_budget')
        contract_flow.ensure(pipelines.contract_tasks_for_first(CLAUDE),CLAUDE,allow_output_failures=True)
        pipelines.prepare_first(CLAUDE)
        for round_index in [1,2]:
            stage=f'pipeline{round_index}_{CLAUDE}'
            progress(stage)
            command('generate.py','--stage',stage,'--workers',2)
            remote.execute(load(ROOT/'configs'/(stage+'_jobs.json')))
            ledger.refresh()
            if round_index==1:
                contract_flow.ensure(pipelines.contract_tasks_for_second(CLAUDE),CLAUDE,allow_output_failures=True)
                pipelines.prepare_second(CLAUDE)
        pipelines.final_states(CLAUDE)
        ledger.refresh()
        command('analyze.py',4,'--models',MODEL,'qwen3.8-flash','glm-5.3-flash',CLAUDE)
        command('audit_final.py')
        save(ROOT/'progress/claude_repair_blocked.json',{'status':'resolved','model':CLAUDE,
            'network_recovery':'Native user environment; confirmed Anthropic Messages transport',
            'output_cap':4096,'resolved_utc':time.time()})
        save(ROOT/'progress/orchestrator.json',{'status':'complete','module':4,
            'population':840,'completed_utc':time.time()})
    except Exception as exc:
        save(ROOT/'progress/orchestrator.json',{'status':'blocked','module':4,
            'error':str(exc),'traceback':traceback.format_exc(),'updated_utc':time.time()})
        raise

if __name__=='__main__':main()
