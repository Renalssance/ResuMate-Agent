"""Synthetic provider/stage boundaries inside an otherwise real parsing child."""
import json
import os
from pathlib import Path
import time

from backend.services import document_tasks


def boundary(stage):
    root = Path(os.environ['TEST_DOCUMENT_PROCESS_ROOT'])
    if (root / 'block-stage').read_text() != stage:
        return
    (root / 'started.json').write_text(json.dumps({'pid': os.getpid(), 'stage': stage}))
    while not (root / 'release').exists():
        time.sleep(.02)
    (root / 'continued').write_text(stage)


extract = document_tasks.extract_stored_pages

def controlled_extract(*args, **kwargs):
    boundary('extract')
    return extract(*args, **kwargs)


def controlled_profile(*args, **kwargs):
    boundary('model')
    return {'candidate_name': 'Synthetic candidate'}


class ControlledIndex:
    def replace_document_chunks(self, **kwargs):
        boundary('embedding')
        kwargs['before_write']()


document_tasks.extract_stored_pages = controlled_extract
document_tasks._parse_profile = controlled_profile
document_tasks.get_rag_store = ControlledIndex

if __name__ == '__main__':
    from backend.services.document_process import main
    main()
