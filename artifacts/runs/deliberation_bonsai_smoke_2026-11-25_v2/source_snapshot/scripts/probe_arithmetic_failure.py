"""Exploratory 12-call follow-up to one observed signed-arithmetic failure."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.models import TracedModel, load_env
from src.experiment import dump
from src.policy import validate_action
from src.quality_checks import objective_cases


class ProbeModel(TracedModel):
    def __init__(self,mode):
        self.mode=mode
        super().__init__('live',max_calls=1)

    def _http(self,payload,timeout):
        if self.mode=='neutral_system':
            payload['messages'][0]['content']='You are an accurate assistant. Follow the requested output format and perform numerical operations carefully.'
        if self.mode=='thinking_medium':
            payload['chat_template_kwargs']={'enable_thinking':True,'reasoning_effort':'medium'}
        self.calls[-1]['request_parameters']={k:v for k,v in payload.items() if k!='messages'}
        self.calls[-1]['system_message']=payload['messages'][0]['content']
        response=super()._http(payload,timeout)
        message=response.get('choices',[{}])[0].get('message',{})
        # Record only presence/length, never hidden reasoning text.
        reasoning=message.get('reasoning_content') or message.get('reasoning') or ''
        self.calls[-1]['reasoning_content_chars']=len(reasoning) if isinstance(reasoning,str) else None
        return response


def main():
    load_env()
    out=Path('artifacts/runs/arithmetic_probe_2026-11-23_v1')
    if out.exists():raise FileExistsError('Probe already exists')
    out.mkdir(parents=True)
    original=next(c for c in objective_cases() if c['id']=='weighted_update')['prompt']
    mirrored=original.replace('0.7*(-0.4) + 0.3*0.8','0.7*0.4 + 0.3*(-0.8)')
    tasks=[{'mode':mode,'repeat':r,'prompt':original,'expected':-.04}
           for mode in ('baseline','stepwise_prompt','neutral_system','thinking_medium') for r in (1,2)]
    tasks += [{'mode':mode,'repeat':r,'prompt':mirrored,'expected':.04,'mirrored':True}
              for mode in ('baseline','thinking_medium') for r in (1,2)]
    protocol={'created_utc':datetime.now(timezone.utc).isoformat(),'request_cap':12,'plan':tasks,
        'type':'Exploratory debugging after a failed benchmark item; not a held-out model benchmark',
        'thinking_budget':2048,'other_budget':300,'temperature':0,
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    dump(out/'protocol.json',protocol);results=[]
    original_limit=os.getenv('LLM_MAX_TOKENS','300')
    for i,task in enumerate(tasks):
        os.environ['LLM_MAX_TOKENS']='2048' if task['mode']=='thinking_medium' else '300'
        model=ProbeModel(task['mode']);model.context={'probe_index':i,'mode':task['mode'],'repeat':task['repeat']}
        prompt=task['prompt']
        if task['mode']=='stepwise_prompt':
            prompt+='\nEvaluate both signed products first, then add them. Verify the sign of the final result before emitting the JSON.'
        record={**task}
        try:
            action=validate_action(model.sample_text(prompt,max_tokens=int(os.environ['LLM_MAX_TOKENS'])))
            record.update(status='ok',action=action,passed=abs(action['opinion']-task['expected'])<=1e-6)
        except Exception as exc:record.update(status='error',passed=False,error_type=type(exc).__name__)
        record['calls']=model.calls;results.append(record)
        dump(out/'results.json',{'results':results})
        print(json.dumps({'index':i+1,'mode':task['mode'],'mirrored':task.get('mirrored',False),
            'status':record['status'],'passed':record['passed'],'opinion':record.get('action',{}).get('opinion')},ensure_ascii=False),flush=True)
        if model.calls[-1]['status']=='error':break
    os.environ['LLM_MAX_TOKENS']=original_limit


if __name__=='__main__':main()
