"""Audit frozen trajectories and exact message reuse in preserved real runs; no API."""
import argparse
from difflib import SequenceMatcher
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]


def analyze(record):
    path = ROOT / record['source']
    run = json.loads(path.read_text(encoding='utf-8'))
    actions = {(call['round'], call['agent']): json.loads(call['response']) for call in run['calls']}
    xs = [row['opinions'] for row in run['trajectory']]
    rounds, population = len(xs)-1, len(xs[0])
    assert len(actions) == population*rounds
    assert all(abs(actions[t,i]['opinion']-xs[t][i])<1e-9
               for t in range(1,rounds+1) for i in range(population))
    steps = [sum(abs(b-a) for a,b in zip(xs[t-1],xs[t])) / population for t in range(1,rounds+1)]
    frozen = sum(abs(xs[t][i]-xs[t-1][i]) < 1e-9 for t in range(2,rounds+1) for i in range(population))
    same_message = 0
    copied_peer = 0
    similarities = []
    examples = []
    for t in range(2,rounds+1):
        for i in range(population):
            current, previous = actions[t,i]['message'], actions[t-1,i]['message']
            same_message += current == previous
            similarities.append(SequenceMatcher(None, previous, current, autojunk=False).ratio())
            matches = [e for e in run['events'] if e['recipient']==i and e['round']==t and e['kind']=='peer' and e['message']==current]
            if matches:
                copied_peer += 1
                if len(examples) < 2:
                    examples.append({'round':t,'agent':i,'source_agent':matches[0]['source'],'message':current})
    late_total = population*(rounds-1)
    return {
        'source':record['source'], 'condition':run['config']['name'], 'seed':run['config']['seed'],
        'mean_absolute_step_by_round':steps,
        'first_round_share_of_total_absolute_path':steps[0]/sum(steps) if sum(steps)>0 else None,
        'late_agent_steps':late_total, 'late_unchanged_opinions':frozen,
        'agents_unchanged_after_round_one':sum(all(abs(xs[t][i]-xs[1][i])<1e-9 for t in range(2,rounds+1)) for i in range(population)),
        'late_verbatim_own_message_repeats':same_message,
        'late_verbatim_received_peer_copies':copied_peer,
        'peer_match_caveat':'An exact match with a currently delivered peer message is observed reuse, not proof of its causal origin. Long-memory prompts also contain older observations.',
        'mean_adjacent_character_similarity':statistics.mean(similarities),
        'similarity_caveat':'SequenceMatcher character ratio is lexical, not semantic similarity or a model quality score.',
        'unique_messages_per_agent':[len({actions[t,i]['message'] for t in range(1,rounds+1)}) for i in range(population)],
        'peer_copy_examples':examples
    }


def aggregate(rows):
    denominator = sum(r['late_agent_steps'] for r in rows)
    return {'runs':len(rows), 'late_agent_steps':denominator,
        **{key:sum(r[key] for r in rows) for key in ('late_unchanged_opinions','late_verbatim_own_message_repeats','late_verbatim_received_peer_copies','agents_unchanged_after_round_one')},
        'late_unchanged_opinion_fraction':sum(r['late_unchanged_opinions'] for r in rows)/denominator,
        'late_verbatim_own_message_fraction':sum(r['late_verbatim_own_message_repeats'] for r in rows)/denominator,
        'late_verbatim_peer_copy_fraction':sum(r['late_verbatim_received_peer_copies'] for r in rows)/denominator}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Choose a new output path to preserve prior analyses')
    records = json.loads((ROOT/'demo/data.json').read_text(encoding='utf-8'))
    rows = [{'case':case,**analyze(record)} for case,record in records.items()]
    active = [r for r in rows if r['condition']!='control']
    baseline = [r for r in active if r['condition'] in ('news_only','peers_only','combined')]
    # Same agent and round, compared pairwise across the four baseline conditions.
    cross_total = cross_equal = 0
    for seed in (11,22,33):
        cases = [records[f'{condition}_{seed}'] for condition in ('control','news_only','peers_only','combined')]
        maps = [{(a['round'],a['agent']):a['message'] for a in c['actions']} for c in cases]
        for left in range(len(maps)):
            for right in range(left+1,len(maps)):
                for key in maps[left]:
                    cross_total += 1
                    cross_equal += maps[left][key] == maps[right][key]
    result = {'date':'2026-11-25','new_api_requests':0,
        'scope':'15 recorded cases, without exact repeat runs; control excluded from active summaries. Not independent human or model samples.',
        'active_runs':aggregate(active),'baseline_active_runs':aggregate(baseline),
        'same_agent_round_cross_condition_verbatim':{'equal_pairs':cross_equal,'total_pairs':cross_total},
        'runs':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='runs'},ensure_ascii=True,indent=2))
    for r in rows:
        print(r['case'], 'steps='+','.join(f'{x:.6f}' for x in r['mean_absolute_step_by_round']),
            f"fixed_late={r['late_unchanged_opinions']}/{r['late_agent_steps']}",
            f"same_text={r['late_verbatim_own_message_repeats']}",f"peer_copies={r['late_verbatim_received_peer_copies']}")


if __name__=='__main__':
    main()
