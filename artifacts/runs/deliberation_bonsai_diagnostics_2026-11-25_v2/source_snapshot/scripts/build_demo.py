"""Embed preserved real trajectories in a standalone, network-free replay."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    records={}
    source=ROOT/'artifacts/runs/robustness_study_2026-11-23_v1'
    original=ROOT/'artifacts/runs/live_pilot_2026-11-23_v1'
    for seed in (11,22,33):
        for condition in ('control','news_only','peers_only','combined'):
            path=original/(condition+'.json') if seed==11 else source/f'{condition}_{seed}.json'
            records[f'{condition}_{seed}']=compact(path)
    for condition in ('combined_memory4','combined_no_initial','combined_memory4_no_initial'):
        records[f'{condition}_11']=compact(source/f'{condition}_11.json')
    target=ROOT/'demo';target.mkdir(exist_ok=True)
    payload=json.dumps(records,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    template=(target/'replay.template.html').read_text(encoding='utf-8')
    if template.count('__RECORDED_DATA__')!=1:raise ValueError('Expected one data placeholder')
    (target/'replay.html').write_text(template.replace('__RECORDED_DATA__',payload),encoding='utf-8')
    (target/'data.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(records),'source':'preserved real LLM runs','new_api_calls':0,
        'html_bytes':(target/'replay.html').stat().st_size},indent=2))


def compact(path):
    r=json.loads(path.read_text(encoding='utf-8'))
    if r['status']!='ok':raise ValueError('Only completed runs can be demonstrated')
    actions=[{'round':c['round'],'agent':c['agent'],**json.loads(c['response'])} for c in r['calls']]
    return {'config':r['config'],'profiles':r['profiles'],'edges':r['edges'],
        'trajectory':r['trajectory'],'actions':actions,'source':path.relative_to(ROOT).as_posix()}


if __name__=='__main__':main()
