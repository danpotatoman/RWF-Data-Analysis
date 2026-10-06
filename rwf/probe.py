"""Dependency-free, raw-preserving probes for public WoW and WCL APIs."""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class ProbeError(Exception):
    """Safe diagnostic: never contains provider bodies or credentials."""


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward Authorization to a redirect destination.


def send(method, url, headers, body):
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            return Response(response.status, dict(response.headers), response.read())
    except HTTPError as error:
        with error:
            return Response(error.code, dict(error.headers), error.read())


class Archive:
    """One SQLite transaction stores exact entity-body bytes and attempt metadata.

    Equal bodies share storage; each HTTP attempt is a distinct observation.
    Replaying the same attempt UUID is idempotent; a conflicting replay fails.
    This probe archive is deliberately separate from the proposed analytical model.
    """
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS body (
            sha256 TEXT PRIMARY KEY, content BLOB NOT NULL);
          CREATE TABLE IF NOT EXISTS attempt (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, request_json TEXT NOT NULL,
            started_at TEXT NOT NULL, received_at TEXT NOT NULL, status INTEGER,
            response_headers TEXT NOT NULL, body_sha256 TEXT REFERENCES body(sha256),
            error_kind TEXT);
        """)

    def save(self, attempt_id, source, request, started, response=None, error=None):
        digest = hashlib.sha256(response.body).hexdigest() if response else None
        allowed = {"date", "last-modified", "etag", "retry-after", "content-type",
                   "content-encoding", "cache-control", "age", "x-request-id"}
        headers = {k.lower(): v for k, v in response.headers.items()
                   if k.lower() in allowed or k.lower().startswith("x-ratelimit")} if response else {}
        row = (source, json.dumps(request, sort_keys=True), started,
               response.status if response else None, json.dumps(headers, sort_keys=True), digest, error)
        with self.db:
            existing = self.db.execute("""SELECT source, request_json, started_at,
                status, response_headers, body_sha256, error_kind FROM attempt WHERE id=?""",
                (attempt_id,)).fetchone()
            if existing:
                if tuple(existing) != row:
                    raise ProbeError("Conflicting attempt replay")
                return
            if response:
                self.db.execute("INSERT OR IGNORE INTO body VALUES (?, ?)", (digest, response.body))
            self.db.execute("INSERT INTO attempt VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (attempt_id, row[0], row[1], row[2], utcnow(), *row[3:]))

    def close(self):
        self.db.close()


def retry_delay(value, attempt, now=None):
    """Honor seconds and HTTP-date; leave long delays to a future scheduler."""
    if value is not None:
        try:
            delay = float(value)
            if math.isfinite(delay):
                return max(0, delay)
        except ValueError:
            try:
                when = parsedate_to_datetime(value)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                return max(0, when.timestamp() - (time.time() if now is None else now))
            except (ValueError, TypeError, OverflowError):
                pass
    return min(30, 2 ** attempt) + random.random()


class Client:
    TOKEN_URLS = {"blizzard": "https://oauth.battle.net/token",
                  "wcl": "https://www.warcraftlogs.com/oauth/token"}

    def __init__(self, source, archive, transport=send, sleep=time.sleep, clock=time.monotonic,
                 environ=None):
        self.source, self.archive = source, archive
        self.transport, self.sleep, self.clock = transport, sleep, clock
        env = os.environ if environ is None else environ
        prefix = source.upper()
        self.client_id = env.get(prefix + "_CLIENT_ID")
        self.secret = env.get(prefix + "_CLIENT_SECRET")
        if not self.client_id or not self.secret:
            raise ProbeError(f"Set {prefix}_CLIENT_ID and {prefix}_CLIENT_SECRET in the environment")
        self.token, self.expires, self.last_sent = None, 0, None

    def _send(self, method, url, headers, body, before_send=None):
        if self.last_sent is not None:
            self.sleep(max(0, 1 - (self.clock() - self.last_sent)))
        self.last_sent = self.clock()
        if before_send:
            before_send()
        return self.transport(method, url, headers, body)

    def _token(self):
        if self.token and self.clock() < self.expires:
            return self.token
        basic = base64.b64encode(f"{self.client_id}:{self.secret}".encode()).decode()
        try:
            response = self._send("POST", self.TOKEN_URLS[self.source],
                {"Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"}, b"grant_type=client_credentials")
        except (URLError, OSError):
            raise ProbeError("OAuth transport failed; no token response was archived") from None
        if response.status != 200:
            raise ProbeError(f"OAuth HTTP {response.status}; no token response was archived")
        try:
            payload = json.loads(response.body)
            token, lifetime = payload["access_token"], float(payload["expires_in"])
            if not isinstance(token, str) or not token or not math.isfinite(lifetime) or lifetime <= 0:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ProbeError("Unexpected OAuth response; not archived") from None
        self.token, self.expires = token, self.clock() + max(0, lifetime - 60)
        return token

    def request(self, url, payload=None, *, before_attempt=None, context=None, max_attempts=4):
        """Optional pilot hook reserves each API send; OAuth bodies remain memory-only.

        With max_attempts=1, the pilot owns durable retry timing instead of blocking
        this client. The default probe behavior is unchanged.
        """
        if not 1 <= max_attempts <= 4:
            raise ProbeError("Invalid retry allowance")
        # Callers only construct approved provider endpoints; no arbitrary URLs.
        if self.source == "wcl":
            valid = url == "https://www.warcraftlogs.com/api/v2/client"
        else:
            valid = any(url.startswith(f"https://{r}.api.blizzard.com/") for r in ("us", "eu", "kr", "tw"))
        if not valid:
            raise ProbeError("Unexpected API destination")
        method = "GET" if payload is None else "POST"
        body = None if payload is None else json.dumps(payload).encode()
        descriptor = {"method": method, "url": url, "payload": payload, "probe_version": 1}
        if context is not None:
            descriptor["pilot"] = context
        refreshed = False
        for attempt in range(max_attempts):
            token = self._token()
            attempt_id, started = str(uuid.uuid4()), utcnow()
            try:
                response = self._send(method, url, {"Authorization": "Bearer " + token,
                    "Accept": "application/json", "Content-Type": "application/json"}, body,
                    before_send=(lambda: before_attempt(attempt_id, descriptor)) if before_attempt else None)
            except (URLError, OSError) as error:
                self.archive.save(attempt_id, self.source, descriptor, started, error=type(error).__name__)
                if attempt == max_attempts - 1:
                    raise ProbeError("API transport failed after retry allowance") from None
                self.sleep(retry_delay(None, attempt))
                continue
            self.archive.save(attempt_id, self.source, descriptor, started, response)
            if response.status == 401:
                self.token = None
                if not refreshed and attempt < max_attempts - 1:
                    refreshed = True
                    continue
            if response.status in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                headers = {k.lower(): v for k, v in response.headers.items()}
                delay = retry_delay(headers.get("retry-after"), attempt)
                if delay > 60:
                    raise ProbeError(f"Provider requests {delay:.0f}s delay; response saved, rerun later")
                self.sleep(delay)
                continue
            if not 200 <= response.status < 300:
                raise ProbeError(f"API HTTP {response.status}; raw response saved")
            try:
                result = json.loads(response.body)
            except (ValueError, UnicodeError):
                raise ProbeError("Non-JSON API response saved; parser needs investigation") from None
            if self.source == "wcl":
                if not isinstance(result, dict) or result.get("errors") or "data" not in result:
                    raise ProbeError("GraphQL error or invalid envelope; full response including partial data saved")
            return result
        raise ProbeError("Retry budget exhausted")


def blizzard_url(kind, region="us", locale="en_US", realm=None, name=None, item_id=None):
    if region not in ("us", "eu", "kr", "tw"):
        raise ProbeError("Probe supports us/eu/kr/tw; CN access needs separate validation")
    if kind in ("equipment", "character", "status", "raids", "specializations", "guild", "roster", "activity"):
        if not realm or not name:
            raise ProbeError("This endpoint requires --realm and --name")
        realm, name = quote(realm, safe=""), quote(name.lower(), safe="")
        if kind in ("guild", "roster", "activity"):
            path = f"/data/wow/guild/{realm}/{name}" + ("" if kind == "guild" else "/" + kind)
        else:
            suffix = {"character": "", "raids": "/encounters/raids"}.get(kind, "/" + kind)
            path = f"/profile/wow/character/{realm}/{name}{suffix}"
        namespace = "profile"
    elif kind in ("item", "item-set", "journal-encounter"):
        if item_id is None or item_id <= 0:
            raise ProbeError("This endpoint requires a positive --id")
        path, namespace = f"/data/wow/{kind}/{item_id}", "static"
    elif kind == "realms":
        path, namespace = "/data/wow/realm/index", "dynamic"
    else:
        raise ProbeError("Unknown Blizzard probe")
    return f"https://{region}.api.blizzard.com{path}?" + urlencode({"namespace": f"{namespace}-{region}", "locale": locale})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", default="data/probes.sqlite")
    subs = parser.add_subparsers(dest="source", required=True)
    blz = subs.add_parser("blizzard")
    blz.add_argument("kind", choices=["equipment", "character", "status", "raids", "specializations",
        "guild", "roster", "activity", "item", "item-set", "journal-encounter", "realms"])
    blz.add_argument("--region", default="us")
    blz.add_argument("--locale", default="en_US")
    blz.add_argument("--realm")
    blz.add_argument("--name", help="Lowercase character name or documented guild slug")
    blz.add_argument("--id", type=int)
    wcl = subs.add_parser("wcl")
    queries = Path(__file__).parent / "queries"
    wcl.add_argument("query", choices=sorted(p.stem for p in queries.glob("*.graphql")))
    wcl.add_argument("--variables", type=Path, help="Path to a JSON variables object")
    args = parser.parse_args(argv)
    archive = None
    try:
        payload = None
        if args.source == "blizzard":
            url = blizzard_url(args.kind, args.region, args.locale, args.realm, args.name, args.id)
        else:
            variables = json.loads(args.variables.read_text(encoding="utf-8-sig")) if args.variables else {}
            if not isinstance(variables, dict):
                raise ProbeError("Variables file must contain a JSON object")
            payload = {"query": (queries / (args.query + ".graphql")).read_text(), "variables": variables}
            url = "https://www.warcraftlogs.com/api/v2/client"
        Path(args.archive).parent.mkdir(parents=True, exist_ok=True)
        archive = Archive(args.archive)
        client = Client(args.source, archive)
        result = client.request(url, payload)
        # Bodies (including character data) stay in ignored local storage.
        print(json.dumps({"result": "saved", "archive": args.archive,
                          "top_level_keys": sorted(result) if isinstance(result, dict) else None}))
        return 0
    except ProbeError as error:
        print(str(error))
        return 2
    except (OSError, ValueError, sqlite3.Error):
        print("Local input or archive error; check paths, JSON and disk availability")
        return 2
    finally:
        if archive:
            archive.close()


if __name__ == "__main__":
    raise SystemExit(main())
