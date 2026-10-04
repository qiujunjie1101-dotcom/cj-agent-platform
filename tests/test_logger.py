import io
import json
import logging
import unittest
from contextlib import redirect_stdout

from src.core.logger import configure_logging


class LoggerTests(unittest.TestCase):
    def tearDown(self) -> None:
        configure_logging(level="INFO", log_format="text", force=True)

    def test_json_logging(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            configure_logging(level="INFO", log_format="json", force=True)
            logging.getLogger("tests.logger").info("日志测试")

        payload = json.loads(output.getvalue().strip())
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "tests.logger")
        self.assertEqual(payload["message"], "日志测试")

    def test_repeated_configuration_does_not_add_handlers(self) -> None:
        configure_logging(level="INFO", log_format="text", force=True)
        handler_count = len(logging.getLogger().handlers)

        configure_logging(level="INFO", log_format="text")

        self.assertEqual(len(logging.getLogger().handlers), handler_count)


if __name__ == "__main__":
    unittest.main()
