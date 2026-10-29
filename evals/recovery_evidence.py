"""Accept actual process evidence only for this explicit evaluation and exact input."""
import json
from pathlib import Path


def read_context(path, cases):
    context=json.loads(Path(path).read_text())
    expected=[{'id':case['id'],'input':case['input']} for case in cases if case.get('runner')=='compose']
    if not isinstance(context.get('invocation_id'),str) or not context['invocation_id'] or context.get('cases')!=expected:
        raise ValueError('Recovery context must contain this suite\'s exact four process cases and inputs')
    return context


def merge_case(case, context, evidence):
    if context is None or evidence.get('invocation_id')!=context['invocation_id']:
        return None
    matches=[row for row in evidence.get('results',[]) if row.get('case_id')==case['id']]
    if len(matches)!=1:
        return None
    row=matches[0]
    if (row.get('invocation_id')!=context['invocation_id'] or row.get('input')!=case['input']
        or row.get('executed') is not True or row.get('status') not in ('pass','fail')):
        return None
    observed=row.get('observed',{})
    after=observed.get('run_after',{})
    before=observed.get('run_before',{})
    checks=[]
    def check(name,passed,reason):
        checks.append(dict(name=name,passed=bool(passed),reason=reason,evidence_refs=['compose.observed']))
    check('actual_process_kill',observed.get('kill_signal')=='SIGKILL','Worker was killed at the named boundary')
    check('sql_converged',after.get('status')=='succeeded','The same persisted Run converged to success')
    check('one_saved_unit',len(observed.get('version_ids',[]))==len(observed.get('operation_rows',[]))==1
          and sum(event.get('type')=='artifact.created' for event in observed.get('events',[]))==1,
          'Exactly one draft version, operation and artifact event survived')
    if case['id']!='recovery-answer-before-delivery':
        check('execution_advanced',after.get('attempt',0)>before.get('attempt',0)
              and after.get('execution_epoch',0)>before.get('execution_epoch',0),'Recovery claimed a new attempt and epoch')
    if case['id']=='recovery-model-before-return':
        check('interrupted_call_repeated',observed.get('model_starts_after',0)>observed.get('model_starts_before',0)>=1,
              'Started interrupted model call repeated; its usage remains unknown')
    if case['id']=='recovery-answer-before-delivery':
        check('answer_persisted',any(action.get('status')=='answered' and action.get('response') for action in observed.get('action_rows',[])),
              'Committed answer remained available when delivery resumed')
    if case['id']=='recovery-checkpoint-before-terminal':
        check('checkpoint_no_new_model',observed.get('model_starts_after')==observed.get('model_starts_before')
              and bool(observed.get('checkpoint')),'Reopening completed checkpoint required no new model call')
    passed=row['status']=='pass' and all(item['passed'] for item in checks)
    return dict(case_id=case['id'],category=case['category'],mode='stub',status='pass' if passed else 'fail',
        input=case,compose={'invocation_id':context['invocation_id'],'source':evidence.get('source'),
                           'started_at':evidence.get('started_at'),'completed_at':evidence.get('completed_at'),**row},
        verdict={'passed':passed,'checks':checks,'limitations':[
            'Process recovery evidence uses a deterministic model; interrupted provider usage is unknown.']},
        semantic={'status':'not_applicable','reason':'Deterministic process recovery does not evaluate model semantics.'})
