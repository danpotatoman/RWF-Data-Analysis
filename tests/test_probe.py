"""Synthetic transport fixtures; these are NOT captured provider responses."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from rwf.probe import Archive, Client, NoRedirect, ProbeError, Response, blizzard_url, main, retry_delay


def response(value, status=200, headers=None):
    return Response(status, headers or {}, json.dumps(value).encode())


TOKEN = response({"access_token": "secret-token", "expires_in": 3600})
URL = "https://www.warcraftlogs.com/api/v2/client"
PAYLOAD = {"query": "query { rateLimitData { limitPerHour } }", "variables": {}}


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.archive = Archive(":memory:")
        self.addCleanup(self.archive.close)
        self.calls, self.sleeps = [], []

    def client(self, sequence, source="wcl"):
        iterator = iter(sequence)
        def transport(*args):
            self.calls.append(args)
            value = next(iterator)
            if isinstance(value, Exception):
                raise value
            return value
        return Client(source, self.archive, transport, self.sleeps.append,
                      environ={source.upper() + "_CLIENT_ID": "private-id",
                               source.upper() + "_CLIENT_SECRET": "private-secret"})

    def count(self, table):
        return self.archive.db.execute("SELECT count(*) FROM " + table).fetchone()[0]

    def test_repeated_payload_preserves_both_observations_and_reuses_token(self):
        client = self.client([TOKEN, response({"data": {}}), response({"data": {}})])
        client.request(URL, PAYLOAD)
        client.request(URL, PAYLOAD)
        self.assertEqual(self.count("attempt"), 2)
        self.assertEqual(self.count("body"), 1)
        self.assertEqual(len(self.calls), 3)
        self.assertNotIn("secret-token", "\n".join(self.archive.db.iterdump()))
        self.assertNotIn("private-secret", "\n".join(self.archive.db.iterdump()))
        self.assertNotIn("private-id", "\n".join(self.archive.db.iterdump()))

    def test_partial_graphql_data_and_errors_survive(self):
        raw = response({"data": {"reportData": None}, "errors": [{"message": "private report"}]})
        client = self.client([TOKEN, raw])
        with self.assertRaisesRegex(ProbeError, "GraphQL"):
            client.request(URL, PAYLOAD)
        self.assertEqual(self.archive.db.execute("SELECT content FROM body").fetchone()[0], raw.body)
        self.assertEqual(len(self.calls), 2)

    def test_unknown_fields_and_exact_bytes_survive(self):
        raw = Response(200, {}, b'{ "data": {"future": [null, {"new": 42}]}}\n')
        self.client([TOKEN, raw]).request(URL, PAYLOAD)
        self.assertEqual(self.archive.db.execute("SELECT content FROM body").fetchone()[0], raw.body)

    def test_malformed_response_saved_before_parser_failure(self):
        client = self.client([TOKEN, Response(200, {}, b"<html>outage</html>")])
        with self.assertRaisesRegex(ProbeError, "Non-JSON"):
            client.request(URL, PAYLOAD)
        self.assertEqual(self.count("body"), 1)

    def test_rate_limit_retry_keeps_error_and_honors_delay(self):
        client = self.client([TOKEN, response({}, 429, {"Retry-After": "7"}), response({"data": {}})])
        client.request(URL, PAYLOAD)
        self.assertIn(7, self.sleeps)
        self.assertEqual(self.count("attempt"), 2)

    def test_long_retry_after_defers_without_early_retry(self):
        with self.assertRaisesRegex(ProbeError, "rerun later"):
            self.client([TOKEN, response({}, 429, {"Retry-After": "120"})]).request(URL, PAYLOAD)
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn(120, self.sleeps)

    def test_retry_after_http_date_and_invalid_value(self):
        self.assertEqual(retry_delay("Thu, 01 Jan 1970 00:02:00 GMT", 0, now=100), 20)
        self.assertEqual(retry_delay("-1", 0), 0)
        self.assertTrue(4 <= retry_delay("invalid", 2) <= 5)
        self.assertTrue(1 <= retry_delay("NaN", 0) <= 2)

    def test_unauthorized_refreshes_once(self):
        client = self.client([TOKEN, response({}, 401), TOKEN, response({}, 401)])
        with self.assertRaisesRegex(ProbeError, "HTTP 401"):
            client.request(URL, PAYLOAD)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(self.count("attempt"), 2)

    def test_expired_token_reacquired(self):
        client = self.client([TOKEN, response({"data": {}}), TOKEN, response({"data": {}})])
        client.request(URL, PAYLOAD)
        client.expires = 0
        client.request(URL, PAYLOAD)
        self.assertEqual(len(self.calls), 4)

    def test_not_found_does_not_retry_or_become_empty_equipment(self):
        client = self.client([TOKEN, response({}, 404)], "blizzard")
        with self.assertRaisesRegex(ProbeError, "HTTP 404"):
            client.request(blizzard_url("equipment", realm="test", name="test"))
        self.assertEqual(self.count("attempt"), 1)

    def test_server_failures_have_bounded_retries(self):
        client = self.client([TOKEN] + [response({}, 503)] * 4)
        with self.assertRaisesRegex(ProbeError, "HTTP 503"):
            client.request(URL, PAYLOAD)
        self.assertEqual(self.count("attempt"), 4)

    def test_transport_failures_saved_without_exception_secret(self):
        client = self.client([TOKEN] + [URLError("sensitive-exception-text")] * 4)
        with self.assertRaisesRegex(ProbeError, "transport failed"):
            client.request(URL, PAYLOAD)
        self.assertEqual(self.count("attempt"), 4)
        self.assertEqual(self.count("body"), 0)
        self.assertNotIn("sensitive-exception-text", "\n".join(self.archive.db.iterdump()))

    def test_oauth_failure_not_archived_or_printed(self):
        client = self.client([response({"error": "sensitive-server-message"}, 401)])
        with self.assertRaisesRegex(ProbeError, "OAuth HTTP 401") as caught:
            client.request(URL, PAYLOAD)
        self.assertNotIn("sensitive", str(caught.exception))
        self.assertEqual(self.count("attempt"), 0)

    def test_missing_credentials_fail_without_network(self):
        with self.assertRaisesRegex(ProbeError, "WCL_CLIENT_ID"):
            Client("wcl", self.archive, environ={})

    def test_redirects_and_unapproved_hosts_rejected(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere"))
        with self.assertRaisesRegex(ProbeError, "destination"):
            self.client([]).request("https://www.warcraftlogs.com.evil.example/", PAYLOAD)
        self.assertEqual(self.calls, [])

    def test_header_allowlist_drops_cookies(self):
        self.archive.save("a", "wcl", {}, "now", response({}, headers={
            "Set-Cookie": "session=secret", "ETag": "abc", "Date": "today", "X-RateLimit-Remaining": "1"}))
        headers = json.loads(self.archive.db.execute("SELECT response_headers FROM attempt").fetchone()[0])
        self.assertEqual(headers, {"etag": "abc", "date": "today", "x-ratelimit-remaining": "1"})

    def test_idempotent_archive_replay_and_conflict(self):
        for _ in range(2):
            self.archive.save("a", "wcl", {}, "now", response({"data": {}}))
        self.assertEqual(self.count("attempt"), 1)
        with self.assertRaisesRegex(ProbeError, "Conflicting"):
            self.archive.save("a", "wcl", {}, "now", response({"changed": True}))
        self.assertEqual(self.count("body"), 1)

    def test_archive_survives_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            first = Archive(path)
            first.save("a", "wcl", {}, "now", response({"data": {}}))
            first.close()
            second = Archive(path)
            try:
                second.save("a", "wcl", {}, "now", response({"data": {}}))
                self.assertEqual(second.db.execute("SELECT count(*) FROM attempt").fetchone()[0], 1)
            finally:
                second.close()

    def test_unicode_and_namespace_paths(self):
        url = blizzard_url("equipment", "eu", "en_GB", "silvermoon", "Äbc/def")
        self.assertIn("%C3%A4bc%2Fdef/equipment", url)
        self.assertEqual(parse_qs(urlsplit(url).query)["namespace"], ["profile-eu"])
        self.assertIn("/data/wow/guild/realm/guild/roster?namespace=profile-us",
                      blizzard_url("roster", realm="realm", name="guild"))
        self.assertIn("namespace=static-us", blizzard_url("item", item_id=1))
        self.assertIn("namespace=dynamic-us", blizzard_url("realms"))
        with self.assertRaises(ProbeError):
            blizzard_url("equipment", region="cn", realm="realm", name="name")

    def test_invalid_cli_variables_is_safe_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vars.json"
            path.write_text("[]")
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = main(["wcl", "rate-limit", "--variables", str(path)])
            self.assertEqual(code, 2)
            self.assertIn("JSON object", output.getvalue())


if __name__ == "__main__":
    unittest.main()
