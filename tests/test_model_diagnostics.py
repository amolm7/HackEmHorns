import io
import unittest
import urllib.error
from unittest.mock import patch
from backend.contracts import Error
from backend.runtime import model


class MetaFailureLoggingTests(unittest.TestCase):
    def test_failed_meta_call_logs_model_and_key_length_but_never_the_key(self):
        key = "sk-secret-value-123"
        settings = {"MODEL_API_KEY": key, "META_MODEL": "muse-spark-1.3 "}  # trailing space on purpose
        failure = urllib.error.HTTPError("https://api.meta.ai", 404, "Not Found", {}, io.BytesIO(b'{"error":"model not found"}'))
        with patch.object(model.urllib.request, "urlopen", side_effect=failure):
            with self.assertLogs("backend.model", level="WARNING") as logs:
                with self.assertRaises(Error) as raised:
                    model.meta_generate(settings, [{"role": "user", "parts": [{"text": "hi"}]}], "system")
        line = "\n".join(logs.output)
        self.assertIn("'muse-spark-1.3 '", line)  # repr makes the stray space visible
        self.assertIn(f"key_length={len(key)}", line)
        self.assertIn("HTTPError 404", line)
        self.assertNotIn(key, line)
        self.assertNotIn(key, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
