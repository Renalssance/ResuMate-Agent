#!/usr/bin/env python3
"""Offline backup/restore for one explicit local MySQL Compose project.

Leaves the source API/worker stopped. Restore requires a fresh project and volumes.
Environment files stay outside the archive; SQL contains private account data.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess

WRITERS = ['web', 'api', 'api2', 'scheduler', 'worker']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup', 'restore'])
    parser.add_argument('directory', type=Path)
    parser.add_argument('--project', required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('-f', '--compose-file', action='append', default=[], help='Additional Compose override')
    args = parser.parse_args()
    docker = shutil.which('docker') or 'docker'
    command = [docker, 'compose', '--env-file', str(args.env_file.resolve()), '-p', args.project,
               '-f', str(Path(__file__).with_name('compose.yaml'))]
    for override in args.compose_file:
        command += ['-f', str(Path(override).resolve())]
    os.umask(0o077)
    directory = args.directory.resolve()

    def compose(*parts, **kwargs):
        return subprocess.run(command + list(parts), check=True, timeout=180, **kwargs)

    def services():
        return set(compose('ps', '--status', 'running', '--services', capture_output=True, text=True).stdout.split())

    if args.operation == 'backup':
        if 'mysql' not in services():
            parser.error('The source MySQL service must already be running')
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        compose('stop', 'web', 'api', 'api2')
        compose('stop', '-t', '130', 'scheduler', 'worker')
        if set(WRITERS) & services():
            raise RuntimeError('Writers are still running; no backup was produced')
        with (directory / 'mysql.sql').open('wb') as output:
            compose('exec', '-T', 'mysql', 'sh', '-c',
                    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction '
                    '--routines --triggers --events --set-gtid-purged=OFF resumate', stdout=output)
        for name, mount in [('backend-data', '/app/data'), ('agent-state', '/app/agent-state')]:
            with (directory / (name + '.tar.gz')).open('wb') as output:
                compose('run', '--rm', '--no-deps', '-T', '--entrypoint', 'tar', 'worker',
                        '-czf', '-', '-C', mount, '.', stdout=output)
        (directory / 'backup.json').write_text(json.dumps({
            'source_project': args.project, 'created_at': datetime.now(timezone.utc).isoformat(),
            'writers_stopped': WRITERS, 'archives': ['mysql.sql', 'backend-data.tar.gz', 'agent-state.tar.gz'],
        }, indent=2))
        print(f'Backup completed: {directory}. Source API, scheduler and worker remain stopped.')
    else:
        for name in ['backup.json', 'mysql.sql', 'backend-data.tar.gz', 'agent-state.tar.gz']:
            if not (directory / name).is_file():
                parser.error('Incomplete backup directory: missing ' + name)
        containers = compose('ps', '-a', '-q', capture_output=True, text=True).stdout.strip()
        volumes = subprocess.run([docker, 'volume', 'ls', '-q', '--filter',
                                  'label=com.docker.compose.project=' + args.project],
                                 check=True, capture_output=True, text=True, timeout=30).stdout.strip()
        if containers or volumes:
            parser.error('Restore requires a fresh project with no existing containers or volumes')
        compose('up', '-d', '--no-build', '--wait', 'mysql', 'redis')
        with (directory / 'mysql.sql').open('rb') as source:
            compose('exec', '-T', 'mysql', 'sh', '-c',
                    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot resumate', stdin=source)
        for name, mount in [('backend-data', '/app/data'), ('agent-state', '/app/agent-state')]:
            with (directory / (name + '.tar.gz')).open('rb') as source:
                compose('run', '--rm', '--no-deps', '-T', '--entrypoint', 'tar', 'worker',
                        '-xzf', '-', '-C', mount, stdin=source)
        compose('up', '-d', '--no-build', '--wait')
        print(f'Restored into project {args.project}; SQL recovery redispatches unfinished Runs.')


if __name__ == '__main__':
    main()
