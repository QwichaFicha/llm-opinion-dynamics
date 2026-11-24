"""Bounded v2 study: new partners, fact updates, ablations and model route comparison."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.deliberation import DiscussionConfig, EvidenceStub, SYSTEM, simulate, diagnostic_plan, run_diagnostics
from src.codex_model import CodexModel
from src.experiment import dump
from src.models import TracedModel


def conditions(suite,rounds):
    options=[DiscussionConfig(rounds=rounds)]
    if suite=='full':options += [
        DiscussionConfig(name='fixed_text',rounds=rounds,partner_mode='fixed'),
        DiscussionConfig(name='rotating_no_own',rounds=rounds,own_history=False),
        DiscussionConfig(name='rotating_numeric',rounds=rounds,peer_numbers=True),
        DiscussionConfig(name='rotating_role_only',rounds=rounds,rich_profiles=False)]
    return options


def configure_gateway(path):
    # One provider per process. Explicit file validation prevents using the other key by fallback.
    values={}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        name,sep,value=line.partition('=')
        if sep and name.strip().startswith('LLM_'):values[name.strip()]=value.strip().strip('\"').strip("'")
    if not all(values.get(k) for k in ('LLM_API_KEY','LLM_BASE_URL','LLM_MODEL')):
        raise ValueError('Selected environment file has incomplete credentials; no request made')
    os.environ.update(values)
    os.environ['LLM_MAX_TOKENS']='600'
    os.environ['LLM_TEMPERATURE']='0'
    return {'model':values['LLM_MODEL'],'base_url':values['LLM_BASE_URL'],'max_tokens':600,'temperature':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=['stub','bonsai','codex','compare-api'],default='stub')
    parser.add_argument('--suite',choices=['smoke','compare','full'],default='compare')
    parser.add_argument('--env-file',type=Path)
    parser.add_argument('--codex-model',default='gpt-6-luna')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise FileExistsError('Use a new output folder')
    rounds=1 if args.suite=='smoke' else 5
    plan=conditions(args.suite,rounds)
    cap=sum(6*(c.rounds+1) for c in plan)+(0 if args.suite=='smoke' else len(diagnostic_plan()))
    provider={'model':'evidence_stub','external_calls':0}
    if args.backend in ('bonsai','compare-api'):
        env_path=args.env_file or ROOT/('.env.compare' if args.backend=='compare-api' else '.env')
        provider=configure_gateway(env_path)
        if args.backend=='bonsai' and (provider['model']!='bonsai2-27b' or provider['base_url'].rstrip('/')!='https://ftii.llm.actcognitive.org/v1'):
            raise ValueError('Unexpected bonsai endpoint/model')
    if args.backend=='codex':
        provider={'requested_model':args.codex_model,'route':'Codex exec, ephemeral read-only, no tools',
            'caveat':'CLI invocations, not a direct API comparison; Codex system context and sampling differ.'}
    out.mkdir(parents=True)
    source_hashes={}
    for folder in ('src','tests','scripts'):
        for f in (ROOT/folder).glob('*.py'):
            target=out/'source_snapshot'/folder/f.name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(f,target);source_hashes[f.relative_to(ROOT).as_posix()]=hashlib.sha256(f.read_bytes()).hexdigest()
    protocol={'created_utc':datetime.now(timezone.utc).isoformat(),'backend':args.backend,'provider':provider,
        'invocation_cap':cap,'plan':[asdict(c) for c in plan],
        'diagnostics':[] if args.suite=='smoke' else diagnostic_plan(),'source_sha256':source_hashes,
        'hypotheses':[
            'Latest official correction is represented in beliefs; no prescribed target opinion.',
            'Irrelevant facade news should not change tracked factual beliefs.',
            'Rotating versus fixed pairs changes only partner scheduling.',
            'Own-history, peer-number and role-only ablations differ from full rotating one factor at a time.'
        ],
        'limits':'No application retries; one call at a time per process. Gateway uses existing 20RPM/100kTPM gate. CLI may retry internally.',
        'interpretation':'Engineering and sensitivity pilot, one profile permutation. No human validation or pure model ranking.'}
    dump(out/'protocol.json',protocol)
    def factory(calls):
        if args.backend=='stub':return EvidenceStub(calls)
        if args.backend=='codex':return CodexModel(calls,args.codex_model)
        return TracedModel('live',calls,system_message=SYSTEM)
    completed=[];total=0
    if args.suite!='smoke':
        model=factory(len(diagnostic_plan()))
        print(json.dumps({'event':'start','run':'diagnostics','planned_calls':24}),flush=True)
        try:
            def progress(data):
                dump(out/'diagnostics.checkpoint.json',data)
                if len(data['calls'])%6==0:print(json.dumps({'event':'diagnostic_progress','calls':len(data['calls'])}),flush=True)
            result=run_diagnostics(model,progress)
        except Exception as exc:
            result={'status':'error','error_type':type(exc).__name__,'calls':model.calls}
        dump(out/'diagnostics.json',result);total+=len(model.calls)
        completed.append({'run':'diagnostics','status':result['status'],'calls':len(model.calls)})
        if result['status']!='ok':
            dump(out/'execution.json',{'status':'stopped_on_error','calls':total,'completed':completed})
            raise SystemExit('Diagnostics stopped; traces preserved. No automatic retry.')
    for config in plan:
        label=config.name;model=factory(6*(config.rounds+1))
        print(json.dumps({'event':'start','run':label,'planned_calls':model.max_calls}),flush=True)
        def progress(data):
            dump(out/(label+'.checkpoint.json'),data)
            if len(data['calls'])%6==0:print(json.dumps({'event':'round','run':label,'round':data['round'],'calls':len(data['calls'])}),flush=True)
        result=simulate(config,model,progress)
        dump(out/(label+'.json'),result);total+=len(model.calls)
        completed.append({'run':label,'status':result['status'],'calls':len(model.calls)})
        dump(out/'execution.json',{'status':'running' if result['status']=='ok' else 'stopped_on_error','calls':total,'completed':completed})
        if result['status']!='ok':raise SystemExit('Simulation stopped; traces preserved. No automatic retry.')
    dump(out/'execution.json',{'status':'ok','calls':total,'completed':completed,
        'finished_utc':datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'event':'complete','calls':total,'cap':cap}),flush=True)


if __name__=='__main__':main()
