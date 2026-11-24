"""One bounded Codex model call; no credential extraction or API key copying."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',default='gpt-6-luna')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Choose a new output directory')
    args.output.mkdir(parents=True)
    schema={'type':'object','properties':{'opinion':{'type':'number'},'message':{'type':'string'}},
            'required':['opinion','message'],'additionalProperties':False}
    schema_path=args.output/'schema.json';schema_path.write_text(json.dumps(schema),encoding='utf-8')
    executable=shutil.which('codex')
    if not executable:raise SystemExit('Codex executable not found')
    command=[executable,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check',
        '--sandbox','read-only','--model',args.model,'--json','--color','never',
        '--output-schema',str(schema_path.resolve()),'-o',str((args.output/'answer.json').resolve()),'-']
    prompt='Do not use any tools. Compute 0.7*(-0.4)+0.3*0.8. Return JSON with the result as opinion and a one-sentence message.'
    started=time.perf_counter()
    try:
        result=subprocess.run(command,input=prompt,encoding='utf-8',capture_output=True,timeout=180,
            cwd=args.output.resolve(),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        # Keep raw launcher logs private; publish only typed event summaries.
        (ROOT/'reports/qa/codex-probe.stdout.txt').write_text(result.stdout,encoding='utf-8')
        (ROOT/'reports/qa/codex-probe.stderr.txt').write_text(result.stderr,encoding='utf-8')
        events=[]
        for line in result.stdout.splitlines():
            try:events.append(json.loads(line))
            except ValueError:pass
        summary={'requested_model':args.model,'exit_code':result.returncode,'seconds':time.perf_counter()-started,
            'event_types':[e.get('type') for e in events],
            'usage':[e.get('usage') for e in events if e.get('usage')],
            'tool_items':[e.get('item',{}).get('type') for e in events if e.get('item',{}).get('type') in ('command_execution','mcp_tool_call')],
            'status':'ok' if result.returncode==0 and (args.output/'answer.json').is_file() else 'failed',
            'note':'A CLI turn is not guaranteed to equal one server-side inference request. Authentication was used in place, never copied.'}
    except subprocess.TimeoutExpired:
        summary={'requested_model':args.model,'status':'timeout','seconds':time.perf_counter()-started}
    (args.output/'result.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))
    answer=args.output/'answer.json'
    if summary['status']=='ok':print(json.dumps(json.loads(answer.read_text(encoding='utf-8')),ensure_ascii=True))


if __name__=='__main__':main()
