"""Public local dataset identity audit; no SSH host is configured."""
from common import *
def main():
    entries = load(ROOT/'protocol/dataset_identity_audit.json')
    files = {p.relative_to(DATA).as_posix(): sha(p) for folder in ['dataset','pyhdl_eval']
             for p in (DATA/folder).rglob('*') if p.is_file() and p.suffix in ['.py','.v','.txt'] and '__pycache__' not in p.parts}
    print(json.dumps({'dataset_files':len(files), 'local_dataset_sha256':canonical(files), 'network_calls':0}))
if __name__=='__main__':main()
