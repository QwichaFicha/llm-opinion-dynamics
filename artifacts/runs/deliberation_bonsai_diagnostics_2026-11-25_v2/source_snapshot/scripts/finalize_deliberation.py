"""Freeze completed v2 folders and count all new calls without double-counting checkpoints."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.experiment import dump
from analyze_deliberation import usage


def main():
    target=ROOT/'artifacts/analysis/deliberation_usage_2026-11-25.json'
    if target.exists():raise FileExistsError('Usage summary already exists')
    totals={'bonsai':[],'codex':[]};rows=[]
    for folder in sorted((ROOT/'artifacts/runs').glob('deliberation_*2026-11-25*')):
        protocol=json.loads((folder/'protocol.json').read_text(encoding='utf-8'))
        if protocol['backend']=='stub':continue
        execution=json.loads((folder/'execution.json').read_text(encoding='utf-8'))
        if execution['status']=='running':raise ValueError('Run still active')
        calls=[]
        for filename in ['diagnostics.json']+[c['name']+'.json' for c in protocol['plan']]:
            p=folder/filename
            if p.exists():calls+=json.loads(p.read_text(encoding='utf-8')).get('calls',[])
        if len(calls)!=execution['calls']:raise ValueError('Execution count mismatch')
        totals[protocol['backend']]+=calls
        rows.append({'folder':folder.relative_to(ROOT).as_posix(),'backend':protocol['backend'],
            'status':execution['status'],'calls':len(calls),'usage':usage(calls)})
        manifest=folder/'manifest.json'
        if manifest.exists():raise FileExistsError('Manifest already exists')
        dump(manifest,{'sha256':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob('*')) if p.is_file() and p!=manifest}})
    probe=json.loads((ROOT/'artifacts/runs/codex_luna_probe_2026-11-25_v1/result.json').read_text(encoding='utf-8'))
    codex_usage=usage(totals['codex']+[{'usage':u} for u in probe['usage']])
    result={'date':'2026-11-25','new_bonsai_http_calls':len(totals['bonsai']),
        'new_codex_cli_invocations':len(totals['codex'])+1,
        'historical_bonsai_http_calls':534,'historical_bonsai_total_tokens':217405,
        'bonsai_new_usage':usage(totals['bonsai']),'codex_new_usage_including_probe':codex_usage,
        'runs':rows,'probe_invocations':1,
        'note':'Includes failed initial smoke and all subsequent launches. Checkpoints and source snapshots are not separate calls. CLI usage includes service context and is not a direct API bill.'}
    dump(target,result)
    print(json.dumps({k:v for k,v in result.items() if k!='runs'},ensure_ascii=True,indent=2))


if __name__=='__main__':main()
