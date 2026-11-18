"""One immutable population, request identity, and provenance schema."""
from __future__ import annotations
import csv, hashlib, json, os, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
HISTORY = Path(os.environ.get('PARAROUTE_HISTORY', str(WORK / 'optional_history')))
PHASE1 = Path(os.environ.get('PARAROUTE_PHASE1', str(HISTORY / 'phase1')))
DATA = Path((os.environ.get('PARAROUTE_DATASET') or str(WORK / 'third_party/pyhdl-eval')))
LANGS = ['pyrtl', 'myhdl', 'amaranth', 'migen', 'pymtl3']
ADAPTER = {**{s:s for s in LANGS}, 'pymtl3':'pymtl'}
MODEL = 'deepseek-v4.1-flash'
SEED = 20261022
IMAGE = os.environ.get('PARAROUTE_IMAGE') or 'sha256:f55b7be23088a39a0dfbbae52f8f677022dfe6a734a99a9465e0cf1ad82c54e5'
PARAMS = dict(temperature=0.2, top_p=0.95, max_tokens=4096,
              reasoning_effort='none', seed=SEED, stream=False)

def load(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p, v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    q=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
    q.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
    for attempt in range(120):
        try:os.replace(q,p);break
        except PermissionError:
            if attempt==119:raise
            time.sleep(0.1)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def text_sha(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def canonical(v): return text_sha(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')))
def csv_write(p, rows):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    fields=list(dict.fromkeys(k for r in rows for k in r)) or ['status']
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def tokenizer():
    os.environ['TIKTOKEN_CACHE_DIR']=str(ROOT/'corpus/tokenizer_cache')
    import tiktoken
    return tiktoken.get_encoding('cl100k_base')
def payload(messages, model=MODEL, **parameters):
    return dict(model=model, **(PARAMS|parameters), messages=messages)
def run_dir(job): return ROOT/'runs'/job['key']
def result_dir(job): return ROOT/'evaluation/cases'/job['key']
def registered_job(key, task, language, arm, request, **meta):
    return dict(key=key, task=task, language=language, adapter_language=ADAPTER[language],
                instance=task+'/'+language, arm=arm, model=request['model'],
                request_sha256=canonical(request), prompt_sha256=canonical(request['messages']),
                **meta)
