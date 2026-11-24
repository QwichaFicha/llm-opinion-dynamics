"""264-call bounded study. All cells and planned contrasts saved in advance."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.experiment import dump, simulate
from src.models import load_env
from src.robustness_study import study_plan


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='artifacts/runs/robustness_study_2026-11-23_v1')
    args=parser.parse_args();out=Path(args.output)
    if out.exists():raise FileExistsError('Choose a new output folder')
    load_env()
    if os.getenv('LLM_BASE_URL','').rstrip('/')!='https://ftii.llm.actcognitive.org/v1' or os.getenv('LLM_MODEL')!='bonsai2-27b':
        raise SystemExit('Unexpected endpoint/model')
    if not os.getenv('LLM_API_KEY'):raise SystemExit('Missing local key')
    if os.getenv('LLM_TEMPERATURE','0') not in ('0','0.0'):raise SystemExit('Expected temperature=0 for historical comparability')
    plan=study_plan();random.Random(2303).shuffle(plan)
    out.mkdir(parents=True)
    hashes={}
    for folder in ('src','tests'):
        for f in sorted((ROOT/folder).glob('*.py')):
            target=out/'source_snapshot'/folder/f.name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(f,target);hashes[str(f.relative_to(ROOT))]=hashlib.sha256(f.read_bytes()).hexdigest()
    f=Path(__file__);target=out/'source_snapshot/scripts'/f.name;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(f,target);hashes['scripts/'+f.name]=hashlib.sha256(f.read_bytes()).hexdigest()
    protocol={'created_utc':datetime.now(timezone.utc).isoformat(),'model':os.getenv('LLM_MODEL'),
        'base_url':os.getenv('LLM_BASE_URL'),'request_cap':264,'plan':[asdict(c) for c in plan],
        'randomized_run_order_seed':2303,'source_sha256':hashes,
        'generation':{'temperature':os.getenv('LLM_TEMPERATURE','0'),'max_tokens':os.getenv('LLM_MAX_TOKENS','300'),'thinking':'not explicitly enabled'},
        'limits':{'rpm':20,'tpm_reserved':100000,'concurrent':1,'min_interval_seconds':3.2,'automatic_retries':0},
        'historical_baselines':{'seed11':'artifacts/runs/live_pilot_2026-11-23_v1',
            'exact_repeat':'artifacts/runs/quality_study_2026-11-23_v1'},
        'planned_contrasts':[
            'Each baseline condition minus control within each seed 11,22,33; inspect sign and range across three profile sets',
            'Memory 4 minus memory 1, with and without historical initial-opinion field',
            'Field removed minus field present, at both memory windows',
            'Interaction: (memory4_no_initial-memory1_no_initial)-(memory4_initial-memory1_initial)'],
        'interpretation':'Three initial profile sets are a small sensitivity screen, not human subjects or stochastic repeats. Memory/anchor factorial is seed11 only. No significance tests planned.'}
    dump(out/'protocol.json',protocol)
    complete=[];calls=0
    for config in plan:
        label=f'{config.name}_{config.seed}'
        print(json.dumps({'event':'start','run':label,'requests_planned':24,'utc':datetime.now(timezone.utc).isoformat()}),flush=True)
        def progress(data):
            dump(out/(label+'.checkpoint.json'),data)
            if len(data['calls'])%6==0:print(json.dumps({'event':'round','run':label,'round':data['round']}),flush=True)
        result=simulate(config,'live',max_calls=24,progress=progress)
        dump(out/(label+'.json'),result);calls+=len(result['calls'])
        row={'run':label,'status':result['status'],'requests':len(result['calls']),
            'mean_opinion':result['final_metrics']['mean_opinion'],'variance':result['final_metrics']['variance'],
            'mean_abs_shift':result['final_metrics']['mean_abs_shift']}
        complete.append(row)
        dump(out/'execution.json',{'status':'running' if result['status']=='ok' else 'stopped_on_error','requests':calls,'completed':complete})
        print(json.dumps({'event':'finish',**row}),flush=True)
        if result['status']!='ok':raise SystemExit('Stopped on error; partial result and checkpoints preserved')
    dump(out/'execution.json',{'status':'ok','requests':calls,'completed':complete,'finished_utc':datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'event':'complete','requests':calls,'runs':len(complete)}),flush=True)


if __name__=='__main__':main()
