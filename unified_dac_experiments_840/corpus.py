"""Full pinned official source/doc trees; complete RST/Markdown/API sections."""
from __future__ import annotations
import collections, concurrent.futures, math, re, shutil, subprocess, tarfile
from common import *
from prepare import insert_material

SOURCES={
 'pyrtl':('https://codeload.github.com/UCSBarchlab/PyRTL/tar.gz/59ddf73eb0e4447ab6fb6c5510779c9725294b42','pyrtl'),
 'myhdl':('https://codeload.github.com/myhdl/myhdl/tar.gz/15ff4fd9937bbd1fd97c64585e9b8e5239e6233e','myhdl'),
 'amaranth':('https://codeload.github.com/amaranth-lang/amaranth/tar.gz/refs/tags/v0.4.5','amaranth'),
 'migen':('https://codeload.github.com/m-labs/migen/tar.gz/refs/tags/0.9.2','migen'),
 'pymtl3':('https://codeload.github.com/pymtl/pymtl3/tar.gz/2eb57d3c4ca87d7fdc3fda467a9a9dca294c2c75','pymtl3'),
}
PWSH=Path(os.environ.get('PARAROUTE_PWSH', 'pwsh'))

def download(lang):
    url,_=SOURCES[lang];archive=ROOT/'corpus/downloads'/(lang+'.tar.gz');archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        p=subprocess.run([str(PWSH),'-NoProfile','-File',str(ROOT/'fetch_docs.ps1'),'-Uri',url,'-Destination',str(archive)],capture_output=True,text=True,timeout=150)
        if p.returncode:raise RuntimeError(lang+': '+p.stderr[-1200:])
    target=ROOT/'corpus/upstream'/lang;target.mkdir(parents=True,exist_ok=True)
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers();prefix=members[0].name.split('/')[0]
        for m in members:
            rel=Path(m.name).relative_to(prefix)
            if not rel.parts:continue
            dest=(target/rel).resolve()
            if target.resolve() not in dest.parents:raise ValueError('archive traversal')
            if m.isfile():
                dest.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(m) as src:dest.write_bytes(src.read())
    return {'language':lang,'url':url,'archive_sha256':sha(archive)}

def sections(text):
    # Preserve complete sections. No token prefix slicing is used in retrieval.
    parts=re.split(r'(?m)(?=^#{1,6} )|(?<=\n)(?=[^\n]+\n[=~\-^]{3,}\s*$)',text)
    for part in parts:
        if len(part.strip())<40:continue
        # Long source/doc sections split only on paragraph boundaries.
        paragraphs=re.split(r'\n\s*\n',part);current=[];size=0
        for paragraph in paragraphs:
            if current and size+len(paragraph)>2400:
                yield '\n\n'.join(current).strip();current=[];size=0
            current.append(paragraph);size+=len(paragraph)
        if current:yield '\n\n'.join(current).strip()

def build():
    manifests=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for result in pool.map(download,LANGS):manifests.append(result)
    enc=tokenizer();records=[];inventory=[]
    for lang in LANGS:
        base=ROOT/'corpus/upstream'/lang
        for path in sorted(base.rglob('*')):
            if not path.is_file() or path.suffix not in ['.rst','.md','.py']:continue
            rel=path.relative_to(base);parts=set(rel.parts)
            if parts & {'test','tests','testcases','example','examples','benchmark','benchmarks','.git','__pycache__'}:continue
            if path.name.startswith('test_') or path.name.endswith('_test.py'):continue
            is_doc=bool(parts & {'doc','docs','documentation'}) or path.name.lower().startswith('readme')
            if not is_doc and path.suffix!='.py':continue
            text=path.read_text(encoding='utf-8',errors='replace')
            inventory.append({'language':lang,'path':rel.as_posix(),'sha256':sha(path),'kind':'documentation' if is_doc else 'compiler_api_source'})
            for i,chunk in enumerate(sections(text)):
                tokens=len(enc.encode(chunk))
                if tokens>1500:continue # indivisible paragraph exceeds complete-passage budget; source remains indexed in inventory
                records.append({'id':f'{lang}/{rel.as_posix()}#{i}','language':lang,'text':chunk,
                                'tokens':tokens,'source_sha256':sha(path),'kind':inventory[-1]['kind']})
    assert all(any(r['language']==l for r in records) for l in LANGS)
    save(ROOT/'corpus/source_manifest.json',manifests);save(ROOT/'corpus/file_inventory.json',inventory);save(ROOT/'corpus/records.json',records)
    return records

def retrieval(records,spec,lang,enc):
    docs=[r for r in records if r['language']==lang];query=collections.Counter(re.findall(r'[a-z_][a-z_0-9]+',spec.lower()))
    terms=[collections.Counter(re.findall(r'[a-z_][a-z_0-9]+',(r['id']+' '+r['text']).lower())) for r in docs]
    df=collections.Counter(t for d in terms for t in d);avg=sum(sum(d.values()) for d in terms)/len(docs)
    ranked=[]
    for r,d in zip(docs,terms):
        length=sum(d.values());score=0
        for term in query.keys() & d.keys():
            f=d[term];idf=math.log(1+(len(docs)-df[term]+0.5)/(df[term]+0.5))
            score+=idf*f*2.2/(f+1.2*(0.25+0.75*length/avg))
        ranked.append((score,r['id'],r))
    ranked.sort(key=lambda x:(-x[0],x[1]));selected=[];used=0
    for score,_,r in ranked:
        block=f"Source: {r['id']}\n{r['text']}";n=len(enc.encode(block))+2
        if used+n<=1500:selected.append((r,block,score));used+=n
        if len(enc.encode('\n\n'.join(b for _,b,_ in selected)))>=1000:break
    combined='\n\n'.join(b for _,b,_ in selected)
    if not 1000<=len(enc.encode(combined))<=1500:raise RuntimeError('Complete-passage token budget not met for '+lang)
    return combined,[{'id':r['id'],'tokens':r['tokens'],'score':s} for r,_,s in selected]

def main():
    records=load(ROOT/'corpus/records.json') if (ROOT/'corpus/records.json').exists() else build()
    jobs=[j for j in load(ROOT/'configs/exp1_jobs.json') if j['arm']!='FullDocRAG'];requests={k:v for k,v in load(ROOT/'configs/exp1_requests.json').items() if not k.endswith('/FullDocRAG')};enc=tokenizer();ledger=[]
    for j in list(jobs):
        if j['arm']!='Direct':continue
        spec=(ROOT/'protocol/specifications'/(j['task']+'.txt')).read_text(encoding='utf-8')
        fragment,selected=retrieval(records,spec,j['language'],enc)
        messages=[dict(m) for m in requests[j['key']]['messages']]
        messages[1]['content']=insert_material(messages[1]['content'],'Official documentation retrieved from the full frozen technical corpus:\n'+fragment)
        req=payload(messages);key=j['key'].rsplit('/',1)[0]+'/FullDocRAG'
        requests[key]=req;jobs.append(registered_job(key,j['task'],j['language'],'FullDocRAG',req,experiment=1))
        ledger.append({'instance':j['instance'],'tokens':len(enc.encode(fragment)),'passages':selected,'fragment_sha256':text_sha(fragment)})
    assert len(jobs)==2520 and len({j['key'] for j in jobs})==2520
    save(ROOT/'configs/exp1_jobs.json',jobs);save(ROOT/'configs/exp1_requests.json',requests);save(ROOT/'corpus/retrieval_ledger.json',ledger)
    save(ROOT/'corpus/freeze.json',{'source_manifest_sha256':sha(ROOT/'corpus/source_manifest.json'),'records_sha256':sha(ROOT/'corpus/records.json'),
         'inventory_sha256':sha(ROOT/'corpus/file_inventory.json'),'retrieval_sha256':sha(ROOT/'corpus/retrieval_ledger.json'),
         'exclusions':'benchmark questions, truth HDL, tests, candidates, logs and example trees; official docs/API/compiler source retained',
         'passages':'complete paragraphs/sections, no tokenizer prefix truncation','range':[min(x['tokens'] for x in ledger),max(x['tokens'] for x in ledger)]})
    print(json.dumps({'records':len(records),'jobs':len(jobs),'retrieval_tokens':[min(x['tokens'] for x in ledger),max(x['tokens'] for x in ledger)]}))
if __name__=='__main__':main()
