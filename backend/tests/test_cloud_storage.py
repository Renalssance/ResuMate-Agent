import json
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote

import pytest
from fastapi import UploadFile

from backend.services import documents


def _json_response(value):
    return BytesIO(json.dumps(value).encode())


def test_storage_round_trip_uses_classic_signatures_and_native_file_id(tmp_path):
    from backend.services.cloud_storage import CloudBaseStorage

    requests = []
    payload = b"Candidate original resume content."
    reference = "cloud://test-env.default-bucket/documents/简历 1.txt"
    upload_url = "https://default-bucket.cos.ap-shanghai.myqcloud.com/documents/%E7%AE%80%E5%8E%86%201.txt"
    download_url = upload_url + "?sign=temporary-download"

    def opener(request, *, timeout):
        requests.append(request)
        if request.full_url.endswith("get-objects-upload-info"):
            return _json_response([{
                "objectId": "documents/简历 1.txt", "uploadUrl": upload_url,
                "authorization": "q-sign-algorithm=sha1&q-ak=temporary",
                "token": "temporary-token", "cloudObjectMeta": "file-metadata",
                "downloadUrl": download_url, "downloadUrlEncoded": download_url,
                "cloudObjectId": reference,
            }])
        if request.method == "PUT":
            return BytesIO()
        if request.full_url.endswith("get-objects-download-info"):
            return _json_response([{
                "cloudObjectId": reference, "downloadUrl": download_url,
                "downloadUrlEncoded": download_url,
            }])
        if request.method == "GET":
            return BytesIO(payload)
        return _json_response([{"cloudObjectId": reference}])

    storage = CloudBaseStorage("test-env", "server-key", opener=opener)
    original = tmp_path / "resume.txt"
    original.write_bytes(payload)
    returned_reference = storage.upload(original, "documents/简历 1.txt")
    downloaded = tmp_path / "download.txt"
    storage.download(returned_reference, downloaded)
    storage.delete(returned_reference)

    assert returned_reference == reference
    assert downloaded.read_bytes() == payload
    assert [request.method for request in requests] == ["POST", "PUT", "POST", "GET", "POST"]
    assert json.loads(requests[0].data) == [{"objectId": "documents/简历 1.txt"}]
    for request, action in zip((requests[0], requests[2], requests[4]), (
        "get-objects-upload-info", "get-objects-download-info", "delete-objects",
    )):
        assert request.full_url == f"https://test-env.api.tcloudbasegateway.com/v1/storages/{action}"
        assert request.get_header("Authorization") == "Bearer server-key"
        assert request.get_header("Content-type") == "application/json"
    assert json.loads(requests[2].data) == [{"cloudObjectId": reference}]
    assert json.loads(requests[4].data) == [{"cloudObjectId": reference}]
    assert requests[1].full_url == upload_url
    assert requests[1].data == payload
    assert requests[1].get_header("Authorization") == "q-sign-algorithm=sha1&q-ak=temporary"
    assert requests[1].get_header("X-cos-security-token") == "temporary-token"
    assert requests[1].get_header("X-cos-meta-fileid") == "file-metadata"
    assert requests[3].full_url == download_url
    assert requests[3].get_header("Authorization") is None


def test_storage_missing_credentials_fails_before_upload(monkeypatch):
    from backend.services.cloud_storage import CloudBaseStorage

    monkeypatch.setenv("CLOUDBASE_ENV_ID", "test-env")
    monkeypatch.delenv("CLOUDBASE_APIKEY", raising=False)
    with pytest.raises(RuntimeError, match="CLOUDBASE_APIKEY"):
        CloudBaseStorage.from_env()


@pytest.mark.parametrize("action", ["upload", "download", "delete"])
@pytest.mark.parametrize("top_level", [False, True])
def test_storage_rejects_api_errors_even_with_http_200(tmp_path, action, top_level):
    from backend.services.cloud_storage import CloudBaseStorage

    error = {"code": "STORAGE_EXCEED_AUTHORITY", "message": "Operation not permitted."}
    response = {**error, "requestId": "test-request"} if top_level else [error]
    storage = CloudBaseStorage("test-env", "server-key", opener=lambda request, **kwargs: _json_response(response))
    with pytest.raises(RuntimeError, match="STORAGE_EXCEED_AUTHORITY"):
        if action == "upload":
            storage.upload(tmp_path / "resume.txt", "resume.txt")
        elif action == "download":
            storage.download("cloud://test-env.default-bucket/resume.txt", tmp_path / "download.txt")
        else:
            storage.delete("cloud://test-env.default-bucket/resume.txt")


def test_storage_delete_missing_object_is_idempotent(tmp_path):
    from backend.services.cloud_storage import CloudBaseStorage

    reference = "cloud://test-env.default-bucket/documents/resume.txt"
    response = [{"cloudObjectId": reference, "code": "OBJECT_NOT_EXIST", "message": "Storage object not exists."}]
    storage = CloudBaseStorage("test-env", "server-key", opener=lambda request, **kwargs: _json_response(response))
    storage.delete(reference)
    with pytest.raises(RuntimeError, match="OBJECT_NOT_EXIST"):
        storage.download(reference, tmp_path / "unused")


@pytest.fixture
def cloud_storage(monkeypatch):
    from backend.services import cloud_storage

    monkeypatch.setenv("CLOUDBASE_ENV_ID", "test-env")
    monkeypatch.setenv("CLOUDBASE_APIKEY", "server-key")
    objects = {}
    requests = []

    def opener(request, *, timeout):
        requests.append(request)
        if request.full_url.endswith("get-objects-upload-info"):
            key = json.loads(request.data)[0]["objectId"]
            url = f"https://default-bucket.cos.ap-shanghai.myqcloud.com/{quote(key, safe='/')}"
            return _json_response([{
                "objectId": key, "uploadUrl": url, "authorization": "temporary-cos-signature",
                "token": "temporary-token", "cloudObjectMeta": "file-metadata",
                "downloadUrl": url, "downloadUrlEncoded": url,
                "cloudObjectId": f"cloud://test-env.default-bucket/{key}",
            }])
        if request.method == "PUT":
            objects[request.full_url] = request.data
            return BytesIO()
        if request.full_url.endswith("get-objects-download-info"):
            reference = json.loads(request.data)[0]["cloudObjectId"]
            key = reference.partition("default-bucket/")[2]
            url = f"https://default-bucket.cos.ap-shanghai.myqcloud.com/{quote(key, safe='/')}"
            return _json_response([{"cloudObjectId": reference, "downloadUrl": url, "downloadUrlEncoded": url}])
        if request.method == "GET":
            return BytesIO(objects[request.full_url])
        if request.full_url.endswith("delete-objects"):
            reference = json.loads(request.data)[0]["cloudObjectId"]
            key = reference.partition("default-bucket/")[2]
            objects.pop(f"https://default-bucket.cos.ap-shanghai.myqcloud.com/{quote(key, safe='/')}", None)
            return _json_response([{"cloudObjectId": reference}])
        raise AssertionError(f"Unexpected storage request: {request.method} {request.full_url}")

    monkeypatch.setattr(cloud_storage, "urlopen", opener)
    return objects, requests


@pytest.mark.asyncio
async def test_cloud_upload_reparses_original_after_scratch_removal(tmp_path, cloud_storage):
    objects, requests = cloud_storage
    payload = "候选人张三，Python 开发工程师，负责后端服务和业务开发。".encode()
    stored = await documents.store_upload(UploadFile(filename="简历.txt", file=BytesIO(payload)), tmp_path)
    reference = documents.persisted_upload_path(stored)

    assert reference.startswith("cloud://test-env.default-bucket/")
    assert stored.path.read_bytes() == payload
    documents.cleanup_upload_cache(stored)
    assert not stored.path.exists()
    assert list(objects.values()) == [payload]

    extracted_paths = []
    original_extract = documents._extract_text_file

    def record_extract(path, filename):
        extracted_paths.append(path)
        return original_extract(path, filename)

    from unittest.mock import patch
    with patch.object(documents, "_extract_text_file", record_extract):
        pages = documents.extract_stored_pages(reference, stored.filename)
    assert pages[0].text == payload.decode()
    assert extracted_paths and not extracted_paths[0].exists()

    documents.delete_stored_file(reference)
    assert objects == {}
    assert [request.method for request in requests] == ["POST", "PUT", "POST", "GET", "POST"]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["signing", "cos-upload"])
async def test_cloud_upload_failure_removes_local_scratch(tmp_path, cloud_storage, monkeypatch, phase):
    from backend.services import cloud_storage as storage_module

    original_opener = storage_module.urlopen

    def unavailable(request, *, timeout):
        if phase == "signing" or request.method == "PUT":
            raise HTTPError(request.full_url, 503, "Unavailable", {}, BytesIO())
        return original_opener(request, timeout=timeout)

    monkeypatch.setattr(storage_module, "urlopen", unavailable)
    with pytest.raises(HTTPError):
        await documents.store_upload(UploadFile(filename="resume.txt", file=BytesIO(b"original bytes")), tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_cloud_parse_failure_removes_remote_original_and_local_scratch(tmp_path, cloud_storage):
    objects, requests = cloud_storage
    with pytest.raises(documents.UnsupportedDocumentError, match="no extractable text"):
        await documents.store_and_extract_upload(UploadFile(filename="empty.txt", file=BytesIO(b"   \n")), tmp_path)
    assert objects == {}
    assert list(tmp_path.iterdir()) == []
    assert [request.method for request in requests] == ["POST", "PUT", "POST"]


@pytest.mark.asyncio
async def test_local_persisted_path_keeps_original_after_cache_cleanup(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUDBASE_ENV_ID", raising=False)
    stored = await documents.store_upload(
        UploadFile(filename="resume.txt", file=BytesIO(b"Candidate original resume content.")), tmp_path
    )
    assert documents.persisted_upload_path(stored) == str(stored.path)
    documents.cleanup_upload_cache(stored)
    assert stored.path.exists()
