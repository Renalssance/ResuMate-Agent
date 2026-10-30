from pathlib import Path
import json,os,signal,subprocess,time,shutil
p=Path(__file__).parent
os.environ['PATH']='/Applications/Docker.app/Contents/Resources/bin:'+os.environ.get('PATH','')
e={'source':str(p/'source'),'frontend_image':'resumate-t19-frontend:5cd2b8fd52','frontend_built':False,'initial_free_bytes':shutil.disk_usage('/tmp').free,'minimum_free_bytes':shutil.disk_usage('/tmp').free,'disk_stop_threshold_bytes':2*2**30,'previous_attempt':'build.json'}
def save(): (p/'frontend-retry.json').write_text(json.dumps(e,indent=2))
save()
cmd=['/Applications/Docker.app/Contents/Resources/bin/docker','compose','--env-file',str(p/'build.env'),'-p','resumate-t19-build-5cd2b8fd52','-f',str(p/'source/deploy/compose.yaml'),'build','web']
with (p/'frontend-build-resume.txt').open('w') as log:
 proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 while proc.poll() is None:
  free=shutil.disk_usage('/tmp').free; e['minimum_free_bytes']=min(e['minimum_free_bytes'],free)
  if free<e['disk_stop_threshold_bytes']:
   e['stopped_for_disk_space']=True; os.killpg(proc.pid,signal.SIGTERM)
   try: proc.wait(timeout=30)
   except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL); proc.wait()
   break
  time.sleep(1)
 e['exit_code']=proc.returncode; e['frontend_built']=proc.returncode==0; save()
 print(json.dumps(e,indent=2),flush=True)
 raise SystemExit(proc.returncode)
