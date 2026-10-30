import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str((Path(__file__).parents[1] / "app")))
import freellm_gateway as g
import failure_center


class GatewayErrors(unittest.TestCase):
    def error(self, status=502, body=None):
        raw = json.dumps(body).encode() if isinstance(body, dict) else body or b""
        return urllib.error.HTTPError(
            g.BASE + "/chat/completions", status, "Bad Gateway", {}, io.BytesIO(raw)
        )

    def test_generic_502_does_not_claim_no_providers(self):
        error = g.http_failure(self.error())
        self.assertIn("causa não foi confirmada", str(error))
        self.assertNotIn("nenhum provedor disponível", str(error))
        self.assertTrue(failure_center.transient(error))

    def test_confirmed_unavailable_pool_has_actionable_guidance(self):
        error = g.http_failure(
            self.error(
                body={
                    "error": {
                        "code": "no_providers_available",
                        "message": "No available providers",
                    }
                }
            )
        )
        self.assertIn("não encontrou um provedor elegível", str(error))
        self.assertIn("registro desta requisição", str(error))
        self.assertTrue(failure_center.transient(error))

    def test_wrapped_quota_and_key_errors_do_not_trigger_retry_storm(self):
        for code in (
            "quota_exceeded",
            "insufficient_quota",
            "invalid_api_key",
            "authentication_error",
        ):
            error = g.http_failure(self.error(body={"error": {"code": code}}))
            self.assertFalse(failure_center.transient(error), str(error))

    def test_upstream_body_and_secrets_are_never_echoed(self):
        secret = "sk-private-key and user prompt"
        error = g.http_failure(
            self.error(body={"error": {"code": secret, "message": secret}})
        )
        self.assertNotIn(secret, str(error))
        self.assertNotIn("sk-private", str(error))

    def test_bad_or_oversized_error_body_keeps_generic_summary(self):
        for body in (
            b"<html>502</html>",
            b"x" * 20000,
            b"[]",
            b"null",
            b'{"error":"bad"}',
        ):
            self.assertIn(
                "causa não foi confirmada", str(g.http_failure(self.error(body=body)))
            )

    def test_timeout_keeps_separate_from_local_connection_failure(self):
        opener = MagicMock()
        opener.open.side_effect = TimeoutError()
        with patch.object(g.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(ValueError, "timeout") as error:
                g.request(g.BASE, "private", "/chat/completions", {})
        self.assertNotIn("Abra o aplicativo", str(error.exception))

    def test_transport_closes_http_error_and_uses_classifier(self):
        original = self.error(body={"error": {"code": "quota_exceeded"}})
        opener = MagicMock()
        opener.open.side_effect = original
        with patch.object(g.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(ValueError, "cota ou saldo"):
                g.request(g.BASE, "private", "/chat/completions", {})
        self.assertTrue(original.fp.closed)

    def test_reliable_router_strategy_is_accepted(self):
        self.assertIn("auto:reliable", g.MODELS)
