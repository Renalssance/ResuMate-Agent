"""Original documents in a classic CloudBase environment's built-in storage."""
from __future__ import annotations

import json
import mimetypes
import os
import shutil
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


class CloudBaseStorage:
    def __init__(self, env_id: str, api_key: str, *, opener=None) -> None:
        self.base_url = f"https://{env_id}.api.tcloudbasegateway.com"
        self.api_key = api_key
        self.opener = opener or urlopen

    @classmethod
    def from_env(cls) -> CloudBaseStorage:
        env_id = os.getenv("CLOUDBASE_ENV_ID", "").strip()
        api_key = os.getenv("CLOUDBASE_APIKEY", "").strip()
        if not env_id or not api_key:
            raise RuntimeError("CloudBase storage requires CLOUDBASE_ENV_ID and CLOUDBASE_APIKEY")
        return cls(env_id, api_key)

    def _api(self, action: str, payload: dict, *, missing_ok: bool = False) -> dict:
        request = Request(
            f"{self.base_url}/v1/storages/{action}",
            data=json.dumps([payload], ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with self.opener(request, timeout=60) as response:
            result = json.load(response)
        item = result[0] if isinstance(result, list) else result
        code = item.get("code")
        if code and not (missing_ok and code == "OBJECT_NOT_EXIST"):
            raise RuntimeError(f"CloudBase storage {code}: {item.get('message', '')}")
        return item

    def upload(self, path: Path, key: str) -> str:
        info = self._api("get-objects-upload-info", {"objectId": key})
        request = Request(
            quote(info["uploadUrl"], safe=":/?&=%@+#"),
            data=path.read_bytes(),
            headers={
                "Authorization": info["authorization"],
                "X-Cos-Security-Token": info["token"],
                "X-Cos-Meta-Fileid": info["cloudObjectMeta"],
                "Content-Type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            },
            method="PUT",
        )
        with self.opener(request, timeout=60):
            pass
        return info["cloudObjectId"]

    def download(self, reference: str, destination: Path) -> None:
        info = self._api("get-objects-download-info", {"cloudObjectId": reference})
        request = Request(info["downloadUrlEncoded"], method="GET")
        with self.opener(request, timeout=60) as response:
            with destination.open("wb") as stream:
                shutil.copyfileobj(response, stream)

    def delete(self, reference: str) -> None:
        self._api("delete-objects", {"cloudObjectId": reference}, missing_ok=True)
