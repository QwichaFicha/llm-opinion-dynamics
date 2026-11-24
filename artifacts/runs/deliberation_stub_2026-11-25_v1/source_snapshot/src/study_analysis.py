"""Offline analysis of paired profile conditions and memory/anchor cells."""
import csv
from datetime import datetime
import json
from pathlib import Path
import statistics

BASE_NAMES=('control','news_only','peers_only','combined')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def describe(values):
    return {'mean':statistics.mean(values),'sd':statistics.stdev(values) if len(values)>1 else 0,
            'min':min(values),'max':max(values),'values':values}


def run_row(label,result,origin):
    m=result['final_metrics'];calls=result['calls']
    return {'run':label,'condition':result['config']['name'],'seed':result['config']['seed'],
        'origin':origin,'status':result['status'],'memory_rounds':result['config']['memory_rounds'],
        'include_initial_opinion':result['config'].get('include_initial_opinion',True),
        'requests':len(calls),'seconds':result['duration_seconds'],
        'initial_mean':result['trajectory'][0]['mean_opinion'],'initial_variance':result['trajectory'][0]['variance'],
        'mean_opinion':m['mean_opinion'],'variance':m['variance'],'mean_abs_shift':m['mean_abs_shift'],
        'edge_disagreement':m['edge_disagreement'],'switches':m['switches'],
        'prompt_tokens':sum((c.get('usage') or {}).get('prompt_tokens',0) or 0 for c in calls),
        'completion_tokens':sum((c.get('usage') or {}).get('completion_tokens',0) or 0 for c in calls),
        'last_round_prompt_chars_mean':statistics.mean(len(c['prompt']) for c in calls if c['round']==result['config']['rounds']) if result['status']=='ok' else None}


def analyze_study(directory,root):
    out=Path(directory);root=Path(root);protocol=read(out/'protocol.json');execution=read(out/'execution.json')
    new={}
    for config in protocol['plan']:
        label=f'{config["name"]}_{config["seed"]}'
        if (out/(label+'.json')).exists():new[label]=read(out/(label+'.json'))
    old={f'{name}_11':read(root/'artifacts/runs/live_pilot_2026-11-23_v1'/f'{name}.json') for name in BASE_NAMES}
    runs={**old,**new}
    rows=[run_row(label,r,'historical' if label in old else 'new') for label,r in runs.items()]
    contrasts=[];agent_contrasts=[]
    for seed in (11,22,33):
        labels=[f'{name}_{seed}' for name in BASE_NAMES]
        if not all(label in runs and runs[label]['status']=='ok' for label in labels):continue
        cells={name:runs[f'{name}_{seed}'] for name in BASE_NAMES}
        reference=cells['control']['profiles']
        if not all(r['profiles']==reference for r in cells.values()):raise ValueError('Unpaired profiles')
        for name in BASE_NAMES[1:]:
            control=cells['control']['final_metrics'];m=cells[name]['final_metrics']
            contrasts.append({'seed':seed,'condition':name,
                'mean_minus_control':m['mean_opinion']-control['mean_opinion'],
                'variance_minus_control':m['variance']-control['variance'],
                'abs_shift_minus_control':m['mean_abs_shift']-control['mean_abs_shift'],
                'individual_final_abs_difference':statistics.mean(abs(a-b) for a,b in zip(m['opinions'],control['opinions']))})
            for i,profile in enumerate(reference):
                agent_contrasts.append({'seed':seed,'condition':name,'agent':i,'role':profile['role'],
                    'initial_opinion':profile['initial_opinion'],'control_final':control['opinions'][i],
                    'treatment_final':m['opinions'][i],
                    'treatment_minus_control':m['opinions'][i]-control['opinions'][i]})
    aggregated=[]
    for name in BASE_NAMES[1:]:
        selected=[r for r in contrasts if r['condition']==name]
        if selected:
            aggregated.append({'condition':name,'profile_sets':len(selected),
                **{key:describe([r[key] for r in selected]) for key in ('mean_minus_control','variance_minus_control','abs_shift_minus_control','individual_final_abs_difference')}})
    factorial_labels={'m1_anchor':'combined_11','m4_anchor':'combined_memory4_11',
        'm1_no_anchor':'combined_no_initial_11','m4_no_anchor':'combined_memory4_no_initial_11'}
    factorial={key:runs[label] for key,label in factorial_labels.items() if label in runs}
    factorial_contrasts={}
    factorial_changed_agents={}
    if len(factorial)==4 and all(r['status']=='ok' for r in factorial.values()):
        for metric in ('mean_opinion','variance','mean_abs_shift','edge_disagreement'):
            f={key:r['final_metrics'][metric] for key,r in factorial.items()}
            factorial_contrasts[metric]={'memory_effect_anchor':f['m4_anchor']-f['m1_anchor'],
                'memory_effect_no_anchor':f['m4_no_anchor']-f['m1_no_anchor'],
                'remove_anchor_memory1':f['m1_no_anchor']-f['m1_anchor'],
                'remove_anchor_memory4':f['m4_no_anchor']-f['m4_anchor'],
                'interaction':f['m4_no_anchor']-f['m1_no_anchor']-f['m4_anchor']+f['m1_anchor']}
        baseline=factorial['m1_anchor']['final_metrics']['opinions']
        for key,result in factorial.items():
            factorial_changed_agents[key]=[{'agent':i,'role':result['profiles'][i]['role'],
                'difference':x-baseline[i]} for i,x in enumerate(result['final_metrics']['opinions']) if abs(x-baseline[i])>1e-9]
    calls=[c for r in new.values() for c in r['calls']]
    successful=[c for c in calls if c['status']=='ok']
    network=[c['network_seconds'] for c in calls if 'network_seconds' in c]
    started=datetime.fromisoformat(protocol['created_utc'])
    finished=datetime.fromisoformat(execution['finished_utc']) if execution.get('finished_utc') else None
    summary={'status':execution['status'],'new_runs':len(new),'historical_baseline_runs':4,
        'new_requests':len(calls),'successful_responses':len(successful),
        'new_prompt_tokens':sum((c.get('usage') or {}).get('prompt_tokens',0) or 0 for c in successful),
        'new_completion_tokens':sum((c.get('usage') or {}).get('completion_tokens',0) or 0 for c in successful),
        'new_total_tokens':sum((c.get('usage') or {}).get('total_tokens',0) or 0 for c in successful),
        'new_simulation_seconds':sum(r['duration_seconds'] for r in new.values()),
        'wall_seconds':(finished-started).total_seconds() if finished else None,
        'network_seconds_median':statistics.median(network) if network else None,
        'network_seconds_p95':sorted(network)[round((len(network)-1)*.95)] if network else None,
        'rate_wait_seconds':sum(c.get('rate_limit_wait_seconds',0) for c in calls),
        'http_errors':[c.get('http_status') for c in calls if c.get('http_status')],
        'conditions':rows,'paired_profile_contrasts':contrasts,'aggregated_profile_contrasts':aggregated,
        'individual_profile_contrasts':agent_contrasts,
        'factorial_labels':factorial_labels,'factorial_contrasts':factorial_contrasts,
        'factorial_changed_agents':factorial_changed_agents,
        'scope':'Three profile parameter sets; only one model and one prompt wording. Memory/anchor factorial uses seed11 only.'}
    (out/'analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    for filename,data in [('summary.csv',rows),('paired_contrasts.csv',contrasts),('individual_contrasts.csv',agent_contrasts)]:
        if data:
            with (out/filename).open('w',encoding='utf-8',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    return summary,runs,factorial
