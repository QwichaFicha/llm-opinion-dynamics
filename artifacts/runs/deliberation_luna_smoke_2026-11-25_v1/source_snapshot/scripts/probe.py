"""Measure prompt growth and record the inspected framework/runtime."""
import hashlib
import importlib.metadata as md
import inspect
import json
from pathlib import Path
import platform
import statistics
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.experiment import Config, simulate, dump
from concordia.agents import entity_agent
from concordia.components.agent import memory, concat_act_component, observation
from concordia.language_model import language_model
from concordia.environment.engines import sequential

records=[]
for horizon in (1,20):
    config=Config(name=f'growth_memory{horizon}',rounds=20,memory_rounds=horizon)
    result=simulate(config)
    out=Path(f'artifacts/runs/growth_memory{horizon}.json')
    if out.exists():
        raise FileExistsError(out)
    dump(out,result)
    sizes=[len(c['prompt']) for c in result['calls']]
    records.append({'memory_rounds':horizon,'rounds':20,'status':result['status'],
        'calls':len(sizes),'seconds':result['duration_seconds'],
        'first_round_mean_chars':statistics.mean(sizes[:6]),
        'last_round_mean_chars':statistics.mean(sizes[-6:]),
        'total_prompt_chars':sum(sizes),'max_prompt_chars':max(sizes),
        'stored_events_agent0':len(json.loads(result['agent_states'][0]['context_components']['memory']['memory_bank']))})
dump('artifacts/runs/growth_summary.json',records)
modules=[entity_agent,memory,concat_act_component,observation,language_model,sequential]
dump('artifacts/setup/runtime.json',{
    'python':sys.version,'platform':platform.platform(),
    'packages':{p:md.version(p) for p in ('gdm-concordia','reportlab','openai','pypdf','numpy','pandas')},
    'inspected_modules':[{'module':m.__name__,'sha256':hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()} for m in modules],
    'signatures':{'EntityAgent':str(inspect.signature(entity_agent.EntityAgent)),
                  'ListMemory':str(inspect.signature(memory.ListMemory)),
                  'ConcatActComponent':str(inspect.signature(concat_act_component.ConcatActComponent))}})
print(json.dumps(records,indent=2))
