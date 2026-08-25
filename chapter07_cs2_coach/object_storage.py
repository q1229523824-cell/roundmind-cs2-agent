"""Demo 对象存储适配器：本地开发与 S3/R2 共用同一任务接口。"""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Protocol
from uuid import uuid4


class ObjectStorageConfigurationError(RuntimeError):
    """对象存储环境变量不完整或模式不受支持。"""


class DemoObjectStoreProtocol(Protocol):
    backend_name: str

    def put(self, source: Path) -> str: ...

    @contextmanager
    def materialize(self, key: str) -> Iterator[Path]: ...

    def delete(self, key: str) -> None: ...


class LocalDemoObjectStore:
    """用受控目录模拟对象存储，适合单机开发和测试。"""

    backend_name = "local"

    def __init__(self, root: Path | None = None) -> None:
        configured = os.getenv("ROUNDMIND_LOCAL_DEMO_DIR", "").strip()
        self.root = root or (
            Path(configured)
            if configured
            else Path(tempfile.gettempdir()) / "roundmind-demo-objects"
        )
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, source: Path) -> str:
        key = f"incoming/{uuid4().hex}.dem"
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), destination)
        return key

    @contextmanager
    def materialize(self, key: str) -> Iterator[Path]:
        path = self._resolve(key)
        if not path.is_file():
            raise FileNotFoundError("Demo 对象不存在或已过期。")
        yield path

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def _resolve(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("非法 Demo 对象键。")
        return candidate


class S3DemoObjectStore:
    """兼容 AWS S3 与 Cloudflare R2 的私有 Demo 临时对象存储。"""

    backend_name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None = None,
        region: str = "auto",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        client: object | None = None,
    ) -> None:
        if not bucket.strip():
            raise ObjectStorageConfigurationError("S3_BUCKET 不能为空。")
        self.bucket = bucket
        if client is None:
            try:
                import boto3
            except ImportError as error:  # pragma: no cover - 仅依赖缺失时触发
                raise ObjectStorageConfigurationError(
                    "S3/R2 模式需要安装 boto3。"
                ) from error
            client = boto3.client(
                "s3",
                endpoint_url=endpoint_url or None,
                region_name=region,
                aws_access_key_id=access_key_id or None,
                aws_secret_access_key=secret_access_key or None,
            )
        self._client = client

    def put(self, source: Path) -> str:
        key = f"incoming/{uuid4().hex}.dem"
        self._client.upload_file(
            str(source),
            self.bucket,
            key,
            ExtraArgs={"ContentType": "application/octet-stream"},
        )
        source.unlink(missing_ok=True)
        return key

    @contextmanager
    def materialize(self, key: str) -> Iterator[Path]:
        with tempfile.NamedTemporaryFile(
            prefix="roundmind-object-", suffix=".dem", delete=False
        ) as handle:
            path = Path(handle.name)
        try:
            self._client.download_file(self.bucket, key, str(path))
            yield path
        finally:
            path.unlink(missing_ok=True)

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)


def object_store_from_environment() -> DemoObjectStoreProtocol:
    """按环境变量选择后端；默认保持无需云服务的本地模式。"""

    mode = os.getenv("ROUNDMIND_OBJECT_STORAGE", "local").strip().lower()
    if mode == "local":
        return LocalDemoObjectStore()
    if mode not in {"s3", "r2"}:
        raise ObjectStorageConfigurationError(
            "ROUNDMIND_OBJECT_STORAGE 只能是 local、s3 或 r2。"
        )
    return S3DemoObjectStore(
        bucket=os.getenv("S3_BUCKET", ""),
        endpoint_url=os.getenv("S3_ENDPOINT_URL", "").strip() or None,
        region=os.getenv("S3_REGION", "auto").strip() or "auto",
        access_key_id=os.getenv("S3_ACCESS_KEY_ID", "").strip() or None,
        secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY", "").strip() or None,
    )
