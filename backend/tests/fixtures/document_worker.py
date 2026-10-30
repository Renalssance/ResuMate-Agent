"""Run the actual worker dispatcher; test-only child command retains model stubs."""
import sys
from backend.tests.fixtures import document_process  # provider boundary only
from backend import worker_tasks

from backend.services import document_process as process
process.DOCUMENT_PARSE_TIMEOUT_SECONDS = 2
process._command = lambda rid, epoch: [sys.executable, '-m', 'backend.tests.fixtures.document_process', rid, str(epoch)]

worker_tasks.execute_run(sys.argv[1])
