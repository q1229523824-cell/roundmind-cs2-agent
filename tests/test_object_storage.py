import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chapter07_cs2_coach.object_storage import (
    LocalDemoObjectStore,
    ObjectStorageConfigurationError,
    S3DemoObjectStore,
    object_store_from_environment,
)


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def upload_file(self, source, bucket, key, ExtraArgs=None):
        self.objects[(bucket, key)] = Path(source).read_bytes()

    def download_file(self, bucket, key, destination):
        Path(destination).write_bytes(self.objects[(bucket, key)])

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


class DemoObjectStorageTests(unittest.TestCase):
    def test_local_store_moves_materializes_and_deletes_demo(self):
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            source = root / "upload.dem"
            source.write_bytes(b"PBDEMS2\x00demo")
            store = LocalDemoObjectStore(root / "objects")

            key = store.put(source)

            self.assertFalse(source.exists())
            self.assertNotIn("upload.dem", key)
            with store.materialize(key) as materialized:
                self.assertEqual(materialized.read_bytes(), b"PBDEMS2\x00demo")
            store.delete(key)
            with self.assertRaises(FileNotFoundError):
                with store.materialize(key):
                    pass

    def test_local_store_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as workspace:
            store = LocalDemoObjectStore(Path(workspace))
            with self.assertRaisesRegex(ValueError, "非法"):
                with store.materialize("../secret.dem"):
                    pass

    def test_s3_store_round_trip_uses_private_random_key(self):
        with tempfile.TemporaryDirectory() as workspace:
            source = Path(workspace) / "named-by-user.dem"
            source.write_bytes(b"PBDEMS2\x00demo")
            client = FakeS3Client()
            store = S3DemoObjectStore(bucket="private-demos", client=client)

            key = store.put(source)

            self.assertFalse(source.exists())
            self.assertTrue(key.startswith("incoming/"))
            self.assertNotIn("named-by-user", key)
            with store.materialize(key) as materialized:
                self.assertEqual(materialized.read_bytes(), b"PBDEMS2\x00demo")
            store.delete(key)
            self.assertEqual(client.objects, {})

    def test_environment_factory_defaults_to_local(self):
        with patch.dict("os.environ", {}, clear=True):
            store = object_store_from_environment()
        self.assertEqual(store.backend_name, "local")

    def test_environment_factory_rejects_unknown_mode(self):
        with patch.dict(
            "os.environ", {"ROUNDMIND_OBJECT_STORAGE": "ftp"}, clear=True
        ):
            with self.assertRaises(ObjectStorageConfigurationError):
                object_store_from_environment()


if __name__ == "__main__":
    unittest.main()
