"""Safe one-campaign diagnostics; delegates execution to the existing eval worker."""
import json,logging,re,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path('/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent')
sys.path.insert(0,str(ROOT))
logging.disable(logging.CRITICAL)
from evals.records import CallRecorder,write_json
from evals.run import main
request_path=Path(sys.argv[1])
request=json.loads(request_path.read_text())
records=[]
original=CallRecorder.on_llm_error
known_fields={'model','messages','content','role','tools','tool_choice','stream','stream_options','max_tokens','max_completion_tokens','enable_thinking','temperature','parallel_tool_calls'}
def safe_error(self,error,**kwargs):
    body=getattr(error,'body',None)
    detail=body.get('error',body) if isinstance(body,dict) else {}
    code=detail.get('code') if isinstance(detail,dict) else None
    safe_prefixes=('AccessDenied','InvalidParameter','Unsupported','InsufficientQuota','ModelNotFound','ModelNotEnabled','DataInspection','invalid_','unsupported_','insufficient_','model_not_','data_inspection_','Throttling','Arrearage')
    param=detail.get('param') if isinstance(detail,dict) else None
    msg=detail.get('message','') if isinstance(detail,dict) else ''
    record={'type':type(error).__name__,'http_status':getattr(error,'status_code',None),
      'provider_code':code if isinstance(code,str) and code.startswith(safe_prefixes) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]{0,95}',code) else None,
      'parameter':param if param in known_fields else None,
      'message_parameter_mentions':sorted(k for k in known_fields if k in msg),
      'quota_or_billing_message':any(x in msg.lower() for x in ('quota','balance','arrearage','billing','payment')),
      'unsupported_message':any(x in msg.lower() for x in ('unsupported','not support'))}
    records.append(record)
    write_json(Path(request['invocation'])/'diagnostics'/(request['case']['id']+'.json'),records)
    return original(self,error,**kwargs)
with patch.object(CallRecorder,'on_llm_error',safe_error):
    result=main(['--output',request['invocation'],'--_worker',str(request_path)])
raise SystemExit(result)
