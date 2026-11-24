"""Build a standalone replay of the v2 runs, with changing partner edges."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.deliberation import BASE_FACTS, EVENTS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,nargs='+',required=True)
    args=parser.parse_args();cases={}
    for folder in args.input:
        protocol=json.loads((folder/'protocol.json').read_text(encoding='utf-8'))
        for cfg in protocol['plan']:
            path=folder/(cfg['name']+'.json')
            if not path.exists():continue
            r=json.loads(path.read_text(encoding='utf-8'))
            if r['status']!='ok':continue
            key=protocol['backend']+'/'+cfg['name']
            cases[key]={'backend':protocol['backend'],'provider':protocol['provider'],
                **{k:r[k] for k in ('config','profiles','pair_schedule','trajectory','actions')},
                'source':path.resolve().relative_to(ROOT).as_posix()}
    if not cases:raise ValueError('No complete recorded cases')
    payload=json.dumps({'cases':cases,'base_facts':BASE_FACTS,'events':EVENTS},ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    template=(ROOT/'demo/discussion.template.html').read_text(encoding='utf-8')
    if template.count('__DATA__')!=1:raise ValueError('Expected one data placeholder')
    (ROOT/'demo/discussion.html').write_text(template.replace('__DATA__',payload),encoding='utf-8')
    print(json.dumps({'cases':len(cases),'new_model_calls':0}))


if __name__=='__main__':main()
