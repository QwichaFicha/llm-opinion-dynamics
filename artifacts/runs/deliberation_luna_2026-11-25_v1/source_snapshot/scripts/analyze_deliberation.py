"""Describe preserved v2 runs. Factual checks are not social-quality scores."""
import argparse
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.deliberation import BASE_FACTS, EVENTS, current_beliefs
from src.experiment import dump


def usage(calls):
    rows=[c.get('usage') or {} for c in calls]
    return {'input_tokens':sum(x.get('prompt_tokens',x.get('input_tokens',0)) for x in rows),
        'output_tokens':sum(x.get('completion_tokens',x.get('output_tokens',0)) for x in rows),
        'cached_input_tokens':sum(x.get('cached_input_tokens',0) for x in rows),
        'reasoning_output_tokens':sum(x.get('reasoning_output_tokens',0) for x in rows)}


def analyze_run(path):
    r=json.loads(path.read_text(encoding='utf-8'))
    if r.get('status')!='ok':return {'file':path.name,'status':r.get('status'),'calls':len(r.get('calls',[]))}
    rows=[];old_messages=None;known=list(BASE_FACTS);total_exact=total_peers=0
    for t,actions in enumerate(r['actions']):
        if t and r['config']['events']:known.append(EVENTS[t-1])
        target=current_beliefs(known);ids={f['id'] for f in known}
        matched=sum(a['beliefs']==target for a in actions)
        xs=[a['opinion'] for a in actions]
        step=statistics.mean(abs(x-y) for x,y in zip(xs,r['trajectory'][t-1]['opinions'])) if t else None
        exact=sum(a['message']==old_messages[i] for i,a in enumerate(actions)) if t else 0
        peers=sum(any(e['message']==a['message'] for e in r['events'] if e['kind']=='peer' and e['round']==t and e['recipient']==i)
            for i,a in enumerate(actions)) if t else 0
        rows.append({'round':t,'mean_opinion':statistics.mean(xs),'variance':statistics.pvariance(xs),
            'mean_abs_step':step,'beliefs_correct':matched,'belief_targets':target,
            'unknown_citation_count':sum(len(set(a['evidence_ids'])-ids) for a in actions),
            'verbatim_own_repeats':exact,'verbatim_peer_matches':peers,
            'answers_exceeding_requested_length':sum(len(a['message'])>600 or len(a['reason'])>350 for a in actions),
            'unchanged_opinions':sum(abs(x-y)<1e-9 for x,y in zip(xs,r['trajectory'][t-1]['opinions'])) if t else None})
        old_messages=[a['message'] for a in actions];total_exact+=exact;total_peers+=peers
    meetings=[tuple(pair) for round_ in r['pair_schedule'] for pair in round_]
    return {'file':path.name,'status':'ok','config':r['config'],'calls':len(r['calls']),
        'usage':usage(r['calls']),'seconds':r['duration_seconds'],'unique_pairs':len(set(meetings)),
        'pair_slots':len(meetings),'rounds':rows,'beliefs_correct':sum(x['beliefs_correct'] for x in rows),
        'beliefs_total':len(r['calls']),'verbatim_own_repeats':total_exact,'verbatim_peer_matches':total_peers,
        'answers_exceeding_requested_length':sum(x['answers_exceeding_requested_length'] for x in rows),
        'late_unchanged_opinions':sum(x['unchanged_opinions'] for x in rows if x['round']>=2),
        'late_agent_steps':6*max(0,len(rows)-2)}


def analyze_folder(folder):
    protocol=json.loads((folder/'protocol.json').read_text(encoding='utf-8'))
    runs=[analyze_run(folder/(c['name']+'.json')) for c in protocol['plan'] if (folder/(c['name']+'.json')).exists()]
    result={'folder':folder.relative_to(ROOT).as_posix(),'backend':protocol['backend'],'provider':protocol['provider'],'runs':runs}
    diag=folder/'diagnostics.json'
    calls=[]
    if diag.exists():
        raw=json.loads(diag.read_text(encoding='utf-8'));calls+=raw.get('calls',[])
        cases=raw.get('results',[])
        result['diagnostics']={'status':raw['status'],'cases':len(cases),'calls':len(raw.get('calls',[])),
            'beliefs_correct':sum(c['beliefs_correct'] for c in cases),
            'cases_with_unknown_citations':sum(bool(c['unknown_citations']) for c in cases),
            'answers_exceeding_requested_length':sum(len(c['action']['message'])>600 or len(c['action']['reason'])>350 for c in cases),
            'by_variant':{v:{'correct':sum(c['beliefs_correct'] for c in cases if c['variant']==v),
                'total':sum(c['variant']==v for c in cases)} for v in ('none','relevant','irrelevant','correction')},
            'paired_irrelevant_opinion_changes':[],
            'usage':usage(raw.get('calls',[]))}
        mapping={c['id']:c for c in cases}
        for i in range(6):
            if f'none_agent{i}' in mapping and f'irrelevant_agent{i}' in mapping:
                result['diagnostics']['paired_irrelevant_opinion_changes'].append(
                    mapping[f'irrelevant_agent{i}']['action']['opinion']-mapping[f'none_agent{i}']['action']['opinion'])
    for c in protocol['plan']:
        p=folder/(c['name']+'.json')
        if p.exists():calls+=json.loads(p.read_text(encoding='utf-8')).get('calls',[])
    result['calls']=len(calls);result['usage']=usage(calls)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Use a new analysis file')
    result={'date':'2026-11-25','new_model_calls':0,
        'note':'Knowledge extraction checks are mechanical. Evidence citation alone does not prove understanding. CLI and direct API routes differ.',
        'studies':[analyze_folder(p.resolve()) for p in args.input]}
    dump(args.output,result)
    for s in result['studies']:
        print(json.dumps({k:v for k,v in s.items() if k not in ('runs','diagnostics')},ensure_ascii=True))
        if 'diagnostics' in s:print(json.dumps(s['diagnostics']))
        for r in s['runs']:
            print(json.dumps({k:v for k,v in r.items() if k not in ('rounds','config')},ensure_ascii=True))


if __name__=='__main__':main()
