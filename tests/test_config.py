import unittest
from unittest.mock import patch

from pydantic import ValidationError

from src.core.config import PROJECT_ROOT, Settings


class SettingsTests(unittest.TestCase):
    def test_loads_env_file_and_process_overrides(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(
                _env_file=PROJECT_ROOT / ".env.example",
                mysql_port=3308,
                redis_db=2,
            )

        self.assertEqual(settings.mysql_port, 3308)
        self.assertEqual(settings.mysql_database, "cj")
        self.assertTrue(settings.app_debug)
        self.assertTrue(settings.debug)
        self.assertEqual(settings.redis_db, 2)
        self.assertEqual(settings.minio_server, "127.0.0.1:9000")

    def test_builds_urls_and_hides_secrets(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(
                _env_file=None,
                mysql_host="mysql.local",
                mysql_port=3307,
                mysql_database="cj_test",
                mysql_user="cj_user",
                mysql_password="p@ss word",
                redis_host="redis.local",
                redis_db=2,
                redis_password="",
                minio_endpoint="minio.local:9000",
                minio_root_user="access-key",
                minio_root_password="secret-key",
                minio_secure=False,
            )

        self.assertEqual(
            settings.database_url,
            "mysql+aiomysql://cj_user:p%40ss%20word@mysql.local:3307/"
            "cj_test?charset=utf8mb4",
        )
        self.assertEqual(settings.redis_url, "redis://redis.local:6379/2")
        self.assertEqual(settings.minio_endpoint, "http://minio.local:9000")
        self.assertEqual(settings.minio_server, "minio.local:9000")
        self.assertEqual(settings.minio_access_key, "access-key")
        self.assertEqual(settings.minio_secret_key, "secret-key")
        self.assertNotIn("secret-key", repr(settings))
        self.assertNotIn("p@ss word", repr(settings))

    def test_rejects_invalid_values(self) -> None:
        invalid_cases = (
            ({"mysql_port": 70000}, "mysql_port"),
            ({"redis_db": "not-a-number"}, "redis_db"),
            ({"log_level": "TRACE"}, "LOG_LEVEL"),
            (
                {
                    "minio_endpoint": "http://127.0.0.1:9000",
                    "minio_secure": True,
                },
                "MINIO_SECURE",
            ),
        )

        for environment, message in invalid_cases:
            with self.subTest(environment=environment):
                with patch.dict("os.environ", {}, clear=True):
                    with self.assertRaisesRegex(ValidationError, message):
                        Settings(_env_file=None, **environment)

    def test_normalizes_short_environment_name(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None, app_env="dev")

        self.assertEqual(settings.app_env, "development")


if __name__ == "__main__":
    unittest.main()
