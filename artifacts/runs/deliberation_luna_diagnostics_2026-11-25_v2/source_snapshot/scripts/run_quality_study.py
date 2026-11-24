"""156-request follow-up: 60 diagnostics + 96 exact-protocol repeat calls."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.experiment import ACTION, conditions, dump, simulate
from src.models import TracedModel, load_env
from src.policy import validate_action
from src.quality_checks import build_diagnostic, diagnostic_plan


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='artifacts/runs/quality_study_2026-11-23_v1')
    args=parser.parse_args();out=Path(args.output)
    if out.exists():raise FileExistsError('Use a new output folder')
    load_env()
    if os.getenv('LLM_BASE_URL','').rstrip('/')!='https://ftii.llm.actcognitive.org/v1' or os.getenv('LLM_MODEL')!='bonsai2-27b':
        raise SystemExit('Unexpected endpoint or model')
    if not os.getenv('LLM_API_KEY'):raise SystemExit('No local key')
    plan=diagnostic_plan();random.Random(20261123).shuffle(plan)
    out.mkdir(parents=True)
    hashes={}
    for folder in ('src','tests'):
        for f in sorted((ROOT/folder).glob('*.py')):
            target=out/'source_snapshot'/folder/f.name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(f,target);hashes[str(f.relative_to(ROOT))]=hashlib.sha256(f.read_bytes()).hexdigest()
    f=Path(__file__);target=out/'source_snapshot/scripts'/f.name;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(f,target);hashes['scripts/'+f.name]=hashlib.sha256(f.read_bytes()).hexdigest()
    protocol={'created_utc':datetime.now(timezone.utc).isoformat(),'model':os.getenv('LLM_MODEL'),
        'base_url':os.getenv('LLM_BASE_URL'),'request_cap':156,'diagnostic_calls':60,'repeat_calls':96,
        'repeat_seed':11,'repeat_conditions':['control','news_only','peers_only','combined'],
        'randomized_diagnostic_order_seed':20261123,'plan':plan,'source_sha256':hashes,
        'generation':{'temperature':os.getenv('LLM_TEMPERATURE','0'),'max_tokens':os.getenv('LLM_MAX_TOKENS','300')},
        'limits':{'rpm':20,'tpm_reserved':100000,'concurrent':1,'min_interval_seconds':3.2,'retries':0},
        'interpretation':'12 tiny objective tasks are basic checks only. News diagnostics have no human-behaviour gold answer. One trajectory repeat estimates repeatability, not statistical significance.'}
    dump(out/'protocol.json',protocol)
    model=TracedModel('live',max_calls=60);results=[];objective_count=0;objective_pass=0
    print(json.dumps({'event':'diagnostics_start','requests':60}),flush=True)
    for item in plan:
        model.context={'diagnostic_id':item['id'],'kind':item['kind'],'variant':item.get('variant'),'agent':item.get('profile',{}).get('id')}
        start=len(model.calls);record={'id':item['id'],'kind':item['kind'],'variant':item.get('variant'),'agent':item.get('profile',{}).get('id')}
        try:
            if item['kind']=='agent':
                raw=build_diagnostic(item['profile'],item['variant'],model).act(ACTION)
            else:raw=model.sample_text(item['prompt'])
            action=validate_action(raw)
            record.update(status='ok',action=action)
            if item['kind']=='objective':
                objective_count+=1;passed=abs(action['opinion']-item['expected_opinion'])<=item['tolerance']
                objective_pass+=int(passed)
                record.update(expected_opinion=item['expected_opinion'],passed=passed)
        except Exception as exc:
            record.update(status='invalid_action',error_type=type(exc).__name__)
            if item['kind']=='objective':objective_count+=1;record['passed']=False
            if not model.calls or model.calls[-1]['status']=='error':
                record['status']='provider_error'
        record['calls']=model.calls[start:];results.append(record)
        dump(out/'diagnostics.json',{'results':results,'requests':len(model.calls)})
        if len(results)%6==0:
            print(json.dumps({'event':'diagnostics_progress','completed':len(results),'objective_passed':objective_pass,'objective_seen':objective_count}),flush=True)
        if record['status']=='provider_error':raise SystemExit('Provider error; partial diagnostics saved')
    if objective_pass < 9:
        dump(out/'execution.json',{'status':'stopped_for_quality_review','requests':60,'objective_passed':objective_pass})
        raise SystemExit('Fewer than 9/12 basic checks passed; inspect before spending more calls')
    done=[];calls=60
    for name in protocol['repeat_conditions']:
        config=replace(next(c for c in conditions() if c.name==name),seed=11)
        print(json.dumps({'event':'repeat_start','condition':name}),flush=True)
        def progress(data):
            dump(out/(name+'.checkpoint.json'),data)
            if len(data['calls'])%6==0:print(json.dumps({'event':'repeat_round','condition':name,'round':data['round']}),flush=True)
        result=simulate(config,'live',max_calls=24,progress=progress)
        dump(out/(name+'.json'),result);calls+=len(result['calls'])
        done.append({'condition':name,'status':result['status'],'requests':len(result['calls'])})
        dump(out/'execution.json',{'status':'running' if result['status']=='ok' else 'stopped_on_error','requests':calls,'repeats':done})
        if result['status']!='ok':raise SystemExit('Failed repeat; partial trace saved')
        print(json.dumps({'event':'repeat_finish',**done[-1]}),flush=True)
    dump(out/'execution.json',{'status':'ok','requests':calls,'repeats':done,'finished_utc':datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'event':'complete','requests':calls,'objective_passed':objective_pass}),flush=True)


if __name__=='__main__':
    main()
