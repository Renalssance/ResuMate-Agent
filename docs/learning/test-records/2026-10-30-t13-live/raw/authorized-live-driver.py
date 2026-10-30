"""One authorized 3 CNY campaign; reuses existing eval workers and one durable ledger."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path('/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent')
CAMPAIGN = Path('/tmp/resumate-t13-live-3cny-20261030')
sys.path.insert(0, str(ROOT))
os.environ.update(DATABASE_URL='sqlite:///:memory:', AGENT_STATE_DIR=str(CAMPAIGN/'parent-state'), PYTHON_DOTENV_DISABLED='1')
logging.disable(logging.CRITICAL)
from evals.run import isolated_environment, load_model_env, write_report
from evals.records import write_json
from evals.fixtures import load_cases
from evals.budget import BudgetConfig


def read(path):
    return json.loads(path.read_text())


def ledger_summary(config):
    path=CAMPAIGN/'budget.json'
    ledger=read(path) if path.exists() else {'calls':{},'stop_reason':None}
    entries=list(ledger['calls'].values())
    observed=sum((Decimal(x['observed_cost']) for x in entries if x['observed_cost'] is not None),Decimal(0))
    reserved=sum((Decimal(x['reserved_cost']) for x in entries if x['observed_cost'] is None),Decimal(0))
    return {'model_calls':len(entries),'observed_upper_cost':str(observed),'reserved_unknown_cost':str(reserved),
            'committed_cost':str(observed+reserved),'currency':'CNY','max_total_cost':config.max_total_cost,
            'unknown_usage_calls':sum(x['observed_cost'] is None for x in entries),'stop_reason':ledger['stop_reason']}


def run_case(case,config,model_env):
    result_path=CAMPAIGN/'cases'/(case['id']+'.json')
    if result_path.exists():
        raise RuntimeError('Refusing an implicit paid rerun of '+case['id'])
    state=CAMPAIGN/'state'/case['id']
    state.mkdir(parents=True,exist_ok=False)
    request=state/'request.json'
    write_json(request,{'case':case,'mode':'live','config':config.public(),'invocation':str(CAMPAIGN)})
    print('START '+case['id'],flush=True)
    process=subprocess.run([sys.executable,'/tmp/resumate-t13-live-diagnostic-worker.py',str(request)],
                           cwd=ROOT,env=isolated_environment(state,model_env),capture_output=True,text=True)
    # Match the CLI's live retention: no raw checkpoint/provider metadata is archived.
    for path in (state/'agent').glob('checkpoints.sqlite*'):
        path.unlink()
    if result_path.exists():
        detail=read(result_path)
        item={k:detail[k] for k in ('case_id','category','status')}
        item['error_code']=detail.get('error_code') or detail.get('output',{}).get('error_code')
        item['artifact']='cases/'+result_path.name
    else:
        item={'case_id':case['id'],'category':case['category'],'status':'incomplete','error_code':'worker_failed'}
        write_json(result_path,item)
    # Never print or persist captured dependency/provider stdout or stderr.
    print('END '+json.dumps({'result':item,'shared_budget':ledger_summary(config)},ensure_ascii=False),flush=True)
    return item,process.returncode


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['init','smoke','core-first','core'])
    args=parser.parse_args()
    cases=[c for c in load_cases() if c.get('runner') not in ('durable','compose')]
    assert len(cases)==12
    if args.stage=='init':
        CAMPAIGN.mkdir(exist_ok=False)
        c=read(Path('/tmp/resumate-t13-live-config.example.json'))
        c.update(max_total_cost='3',max_case_cost='1.5',max_model_calls=120,max_case_model_calls=30)
        config=BudgetConfig.from_dict(c)
        # Check the installed adapter's actual serialization without any network call.
        from langchain_openai import ChatOpenAI
        model=ChatOpenAI(model=config.model,api_key='synthetic-preflight-only',base_url='http://127.0.0.1:1/v1',
                         max_tokens=config.max_output_tokens,max_retries=0,extra_body={'enable_thinking':False})
        payload=model._get_request_payload('synthetic preflight')
        assert payload['max_completion_tokens']==4096 and 'max_tokens' not in payload
        assert payload['extra_body']['enable_thinking'] is False
        write_json(CAMPAIGN/'config.json',config.public())
        write_json(CAMPAIGN/'budget.json',{'currency':'CNY','calls':{},'stop_reason':None})
        manifest={'invocation_id':str(uuid4()),'created_at':datetime.now(timezone.utc).isoformat(),'mode':'live',
          'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'dependencies':{name:importlib.metadata.version(name) for name in ('deepagents','langchain-core','langchain-openai','langgraph','openai')},
          'authorized_total':'3 CNY for smoke plus initial 12 cases and any later reruns; never reset',
          'config':config.public(),'preflight':'passed','synthetic_inputs':True,'tracing':'disabled',
          'credential_policy':'Only explicit model environment whitelist in child process; no credentials retained',
          'smoke_source_case':'normal-api','smoke_case_id':'smoke-normal-api','core_case_ids':[c['id'] for c in cases],
          'ledger':'budget.json','output_parameter_checked':'max_completion_tokens=4096; thinking=false; no provider call',
          'pricing_checked_at':'2026-10-30','pricing_tiers_cny_per_million':[
            {'input_max':32000,'input':'0.2','output':'0.8'},
            {'input_max':256000,'input':'0.6','output':'2.4'},
            {'input_max':1000000,'input':'1.2','output':'4.8'}],
          'sources':{'pricing':'https://help.aliyun.com/zh/model-studio/model-pricing',
            'capacity':'https://help.aliyun.com/zh/model-studio/qwen3-7-flash',
            'all_billed_output':'https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions',
            'endpoint_region':'https://help.aliyun.com/zh/model-studio/beijing-access-information'},
          'reserve_per_call_cny':str(config.reserve),'note':'Highest tier conservative usage cost; not a settled invoice. No paid calls during preflight.'}
        write_json(CAMPAIGN/'manifest.json',manifest)
        print(json.dumps({'preflight':'passed','campaign':str(CAMPAIGN),'reserve':str(config.reserve)},ensure_ascii=False))
        return 0
    config=BudgetConfig.from_dict(read(CAMPAIGN/'config.json'))
    assert config.max_total_cost=='3' and config.max_case_cost=='1.5'
    model_env=load_model_env('/Users/bono/Desktop/code/ResuMate-Agent/.env')
    assert model_env.get('LLM_MODEL',model_env.get('MODEL'))==config.model
    assert model_env.get('OPENAI_API_KEY') or model_env.get('ARK_API_KEY')
    stage_results=[]
    if args.stage=='smoke':
        selected=deepcopy(next(c for c in cases if c['id']=='normal-api'))
        selected['id']='smoke-normal-api'
        item,code=run_case(selected,config,model_env)
        stage_results.append(item)
        write_json(CAMPAIGN/'smoke-results.json',stage_results)
        write_report(CAMPAIGN,'live',stage_results)
        return 0 if item['status']=='pass' and code==0 and not ledger_summary(config)['unknown_usage_calls'] else 2
    smoke=read(CAMPAIGN/'smoke-results.json')
    if args.stage=='core-first':
        item,code=run_case(next(c for c in cases if c['id']=='normal-api'),config,model_env)
        write_json(CAMPAIGN/'core-results.json',[item])
        return write_report(CAMPAIGN,'live',smoke+[item])
    if smoke[0]['status']!='pass' or ledger_summary(config)['unknown_usage_calls']:
        raise RuntimeError('Smoke has not cleared the live protocol/usage gate')
    stop=ledger_summary(config)['stop_reason']
    for case in cases:
        if stop:
            item={'case_id':case['id'],'category':case['category'],'status':'not_run','error_code':stop}
        else:
            item,code=run_case(case,config,model_env)
            stop=ledger_summary(config)['stop_reason'] or ('harness_error' if code else None)
        stage_results.append(item)
        write_json(CAMPAIGN/'core-results.json',stage_results)
        write_report(CAMPAIGN,'live',smoke+stage_results)
    return write_report(CAMPAIGN,'live',smoke+stage_results)

if __name__=='__main__':
    raise SystemExit(main())
