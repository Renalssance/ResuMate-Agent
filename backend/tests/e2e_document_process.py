"""Browser-only provider stubs in the real bounded document subprocess."""
from backend.tests import e2e_legacy_fixture  # noqa: F401
from backend.services.document_process import main

if __name__ == '__main__':
    main()
