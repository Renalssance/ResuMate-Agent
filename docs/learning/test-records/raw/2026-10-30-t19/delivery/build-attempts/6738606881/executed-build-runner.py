from pathlib import Path
import json,os,shutil,signal,subprocess,time,uuid
repo=Path('/Users/bono/.codex/worktrees/resumate-fullstack-learning/ResuMate-Agent')
id=uuid.uuid4().hex[:10]
root=Path('/tmp')/('task-19-build-'+id)
root.mkdir(mode=0o700)
source=root/'source'; source.mkdir()
ignore=shutil.ignore_patterns('node_modules','dist','__pycache__','.pytest_cache','*.pyc','.env','.env.local')
for name in ['backend','deploy','frontend']:
 shutil.copytree(repo/name,source/name,ignore=ignore)
for name in ['Dockerfile','.dockerignore','.env.example','pyproject.toml','uv.lock','README.md','compose.redis-integration.yaml']:
 shutil.copy2(repo/name,source/name)
shutil.copy2(__file__,root/'executed-build-runner.py')
backend='resumate-t19-backend:'+id; frontend='resumate-t19-frontend:'+id
cfg={'MYSQL_PASSWORD':uuid.uuid4().hex,'MYSQL_ROOT_PASSWORD':uuid.uuid4().hex,'JWT_SECRET_KEY':uuid.uuid4().hex,'RESUMATE_BACKEND_IMAGE':backend,'RESUMATE_FRONTEND_IMAGE':frontend}
env=root/'build.env'; env.write_text('\n'.join(k+'='+v for k,v in cfg.items())+'\n'); env.chmod(0o600)
evidence={'source':str(source),'backend_image':backend,'frontend_image':frontend,'backend_built':False,'frontend_built':False,'previous_failed_build':'/tmp/task-19-build-1c9d135ffa','disk_stop_threshold_bytes':2*2**30,'initial_free_bytes':shutil.disk_usage('/tmp').free,'minimum_free_bytes':shutil.disk_usage('/tmp').free}
def save(): (root/'build.json').write_text(json.dumps(evidence,indent=2))
save(); Path('/tmp/task-19-build-current.txt').write_text(str(root)); print(root,flush=True)
cmd=['/Applications/Docker.app/Contents/Resources/bin/docker','compose','--env-file',str(env),'-p','resumate-t19-build-'+id,'-f',str(source/'deploy/compose.yaml')]
for service,kind in [('api','backend'),('web','frontend')]:
 with (root/(kind+'-build.txt')).open('w') as out:
  proc=subprocess.Popen(cmd+['build',service],stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
  while proc.poll() is None:
   free=shutil.disk_usage('/tmp').free
   evidence['minimum_free_bytes']=min(evidence['minimum_free_bytes'],free)
   if free<evidence['disk_stop_threshold_bytes']:
    evidence['stopped_for_disk_space']=kind
    os.killpg(proc.pid,signal.SIGTERM)
    try: proc.wait(timeout=30)
    except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL); proc.wait()
    break
   time.sleep(1)
  evidence[kind+'_exit_code']=proc.returncode; evidence[kind+'_built']=proc.returncode==0; save()
  print(kind,'exit',proc.returncode,flush=True)
  if proc.returncode: raise SystemExit(1)
print('fresh build completed',flush=True)
