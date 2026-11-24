"""Bounded first live pilot: six-call smoke, then four paired conditions."""
import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.experiment import Config, conditions, dump, simulate
from src.models import load_env


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='artifacts/runs/live_pilot_2026-11-23_v1')
    args=parser.parse_args()
    out=Path(args.output)
    if out.exists():
        raise FileExistsError('Choose a new directory; earlier results are preserved')
    load_env()
    if os.getenv('LLM_BASE_URL','').rstrip('/')!='https://ftii.llm.actcognitive.org/v1' or os.getenv('LLM_MODEL')!='bonsai2-27b':
        raise SystemExit('Unexpected endpoint/model; check local .env')
    if not os.getenv('LLM_API_KEY'):
        raise SystemExit('Missing local key')
    out.mkdir(parents=True)
    hashes={}
    for folder in ('src','tests'):
        for f in sorted((ROOT/folder).glob('*.py')):
            target=out/'source_snapshot'/folder/f.name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(f,target)
            hashes[str(f.relative_to(ROOT))]=hashlib.sha256(f.read_bytes()).hexdigest()
    for name in ('run_live_pilot.py',):
        f=ROOT/'scripts'/name
        target=out/'source_snapshot/scripts'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(f,target)
        hashes['scripts/'+name]=hashlib.sha256(f.read_bytes()).hexdigest()
    protocol={'created_utc':datetime.now(timezone.utc).isoformat(),
        'model':os.getenv('LLM_MODEL'),'base_url':os.getenv('LLM_BASE_URL'),
        'seed':11,'request_cap':102,'smoke_requests':6,'main_requests':96,
        'conditions':['control','news_only','peers_only','combined'],
        'rounds':4,'agents':6,'generation':{'temperature':os.getenv('LLM_TEMPERATURE','0'),
            'max_tokens':os.getenv('LLM_MAX_TOKENS','300'),'thinking':'provider default; not explicitly enabled'},
        'gateway_limits_from_user':{'rpm':20,'tpm':100000,'max_concurrent':2},
        'runner_limits':{'min_interval_seconds':3.2,'concurrent':1,'automatic_retries':0},
        'source_sha256':hashes,
        'interpretation':'Engineering pilot, one initial seed per condition; no statistical significance claims'}
    dump(out/'protocol.json',protocol)
    selected=[replace(Config(),name='smoke',rounds=1)]+[
        replace(c,seed=11) for name in protocol['conditions'] for c in conditions() if c.name==name]
    completed=[]; calls=0
    for config in selected:
        print(json.dumps({'event':'start','condition':config.name,'utc':datetime.now(timezone.utc).isoformat()}),flush=True)
        def progress(data):
            dump(out/(config.name+'.checkpoint.json'),data)
            if len(data['calls'])%6==0:
                print(json.dumps({'event':'round_complete','condition':config.name,'round':data['round'],
                    'requests':len(data['calls']),'last_usage':data['calls'][-1].get('usage')},ensure_ascii=False),flush=True)
        result=simulate(config,'live',max_calls=6*config.rounds,progress=progress)
        dump(out/(config.name+'.json'),result)
        calls+=len(result['calls'])
        completed.append({'condition':config.name,'status':result['status'],
            'requests':len(result['calls']),'seconds':result['duration_seconds'],
            'error':result['error']})
        dump(out/'execution.json',{'finished_conditions':completed,'requests':calls,
            'status':'running' if result['status']=='ok' else 'stopped_on_error'})
        print(json.dumps({'event':'finish',**completed[-1]},ensure_ascii=False),flush=True)
        if result['status']!='ok':
            raise SystemExit('Stopped on first failed condition. Partial results saved; no retries.')
    dump(out/'execution.json',{'finished_conditions':completed,'requests':calls,
        'status':'ok','finished_utc':datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'event':'complete','requests':calls,'output':str(out)}),flush=True)


if __name__=='__main__':
    main()
