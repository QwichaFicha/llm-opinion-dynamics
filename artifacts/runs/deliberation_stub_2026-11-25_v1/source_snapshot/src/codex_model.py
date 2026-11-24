"""Concordia adapter for the explicitly requested Codex CLI route."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from concordia.language_model.language_model import LanguageModel
from .deliberation import SYSTEM

SCHEMA={'type':'object','properties':{
    'opinion':{'type':'number'},'message':{'type':'string'},'reason':{'type':'string'},
    'evidence_ids':{'type':'array','items':{'type':'string'}},
    'beliefs':{'type':'object','properties':{'digital_offline':{'type':'boolean'},
        'digital_cost':{'type':'number'},'printed_cost':{'type':'number'}},
        'required':['digital_offline','digital_cost','printed_cost'],'additionalProperties':False}},
    'required':['opinion','message','reason','evidence_ids','beliefs'],'additionalProperties':False}


class CodexModel(LanguageModel):
    def __init__(self,max_calls=36,model='gpt-6-luna',workdir=None,executable=None):
        self.calls=[];self.context={};self.max_calls=max_calls;self.model=model
        self.executable=executable or shutil.which('codex')
        if not self.executable:raise ValueError('Codex CLI is not installed')
        self.workdir=Path(workdir or Path(__file__).resolve().parents[1]/'reports/qa/codex-calls')
        self.workdir.mkdir(parents=True,exist_ok=True)

    def sample_text(self,prompt,**kwargs):
        if len(self.calls)>=self.max_calls:raise RuntimeError('CLI invocation budget exhausted')
        record={**self.context,'backend':'codex','requested_model':self.model,'prompt':prompt,
            'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
            'sampling_note':'Codex controls its own system context and generation settings; temperature is not matched to the gateway.',
            'system_message':SYSTEM}
        self.calls.append(record);started=time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix='call-',dir=self.workdir) as folder:
                folder=Path(folder);schema=folder/'schema.json';answer=folder/'answer.json'
                schema.write_text(json.dumps(SCHEMA),encoding='utf-8')
                command=[self.executable,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check',
                    '--sandbox','read-only','--model',self.model,'--json','--color','never',
                    '--output-schema',str(schema),'-o',str(answer),'-']
                proc=subprocess.run(command,input=SYSTEM+'\n'+prompt,encoding='utf-8',capture_output=True,
                    timeout=180,cwd=folder,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                events=[]
                for line in proc.stdout.splitlines():
                    try:events.append(json.loads(line))
                    except ValueError:pass
                record['cli_exit_code']=proc.returncode
                record['usage']=next((e['usage'] for e in reversed(events) if e.get('usage')),None)
                record['tool_items']=[e['item'].get('type') for e in events
                    if e.get('item',{}).get('type') not in (None,'agent_message','reasoning')]
                if proc.returncode or not answer.is_file():
                    raise RuntimeError('Codex invocation failed; private launcher output omitted')
                if record['tool_items']:raise RuntimeError('Unexpected Codex tool activity')
                raw=answer.read_text(encoding='utf-8');record.update(status='ok',response=raw)
                return raw
        except Exception as exc:
            record.update(status='error',error_type=type(exc).__name__);raise
        finally:record['latency_seconds']=time.perf_counter()-started

    def sample_choice(self,prompt,responses,**kwargs):raise NotImplementedError('Only free actions are used')
