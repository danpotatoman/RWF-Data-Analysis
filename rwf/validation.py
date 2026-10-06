"""Serial feasibility tools. All live evidence is written below ignored data/."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time

from rwf.probe import Archive, Client, ProbeError, blizzard_url, utcnow

ROOT = Path("data/feasibility")
QUERIES = Path(__file__).parent / "queries"
WCL_URL = "https://www.warcraftlogs.com/api/v2/client"


def validate_queries(introspection, directory=QUERIES):
    from graphql import build_client_schema, parse, validate
    schema = build_client_schema(introspection)
    results = {}
    for path in sorted(directory.glob("*.graphql")):
        try:
            errors = validate(schema, parse(path.read_text(encoding="utf-8")))
            results[path.name] = [error.message for error in errors]
        except Exception as error:
            results[path.name] = [str(error)]
    return results


def paginate(fetch, start=1, max_pages=30):
    """Fail closed on incomplete/null/error pages; retain duplicates for inspection."""
    rows, pages = [], []
    for page in range(start, start + max_pages):
        result = fetch(page)
        if (not isinstance(result, dict) or result.get("current_page") != page
                or not isinstance(result.get("data"), list)
                or type(result.get("has_more_pages")) is not bool):
            raise ProbeError("Invalid or unavailable pagination envelope")
        rows.extend(result["data"])
        pages.append({k: v for k, v in result.items() if k != "data"})
        if not result["has_more_pages"]:
            return rows, pages
    raise ProbeError("Page budget reached before terminal page")


def event_pages(fetch, start, end, max_pages=20):
    pages, cursor = [], start
    for _ in range(max_pages):
        page = fetch(cursor)
        if not isinstance(page, dict) or not isinstance(page.get("data"), list) or "nextPageTimestamp" not in page:
            raise ProbeError("Invalid or unavailable event envelope")
        pages.append(page)
        next_cursor = page["nextPageTimestamp"]
        if next_cursor is None:
            return pages
        if (isinstance(next_cursor, bool) or not isinstance(next_cursor, (int, float))
                or not math.isfinite(next_cursor) or not cursor < next_cursor <= end):
            raise ProbeError("Non-advancing or out-of-range event cursor")
        cursor = next_cursor
    raise ProbeError("Event page budget reached before terminal cursor")


def roster_key(name, realm, region):
    # Compare addresses, not human ownership or immutable character identities.
    import unicodedata
    return tuple(unicodedata.normalize("NFC", value).casefold() for value in (region, realm, name))


def compare_rosters(wcl, blizzard, region="us"):
    wkeys = [roster_key(row["name"], row["server"]["slug"], region) for row in wcl]
    bkeys = [roster_key(row["character"]["name"], row["character"]["realm"]["slug"], region) for row in blizzard]
    ws, bs = set(wkeys), set(bkeys)
    def names(rows):
        return sorted({name for _, _, name in rows if "imfiredup" in name})
    return dict(wcl_rows=len(wkeys), blizzard_rows=len(bkeys), wcl_unique=len(ws), blizzard_unique=len(bs),
        overlap=len(ws & bs), wcl_only=len(ws - bs), blizzard_only=len(bs - ws),
        wcl_realms=dict(Counter(realm for _, realm, _ in wkeys)),
        blizzard_realms=dict(Counter(realm for _, realm, _ in bkeys)), regions=[region],
        imfiredup_wcl=names(ws), imfiredup_blizzard=names(bs),
        imfiredup_wcl_characters=sum("imfiredup" in n for _, _, n in ws),
        imfiredup_blizzard_characters=sum("imfiredup" in n for _, _, n in bs),
        imfiredup_addresses=[dict(region=r, realm=s, name=n) for r, s, n in sorted(ws | bs) if "imfiredup" in n],
        wcl_region_names=dict(Counter(row['server'].get('region', {}).get('name', 'unknown') for row in wcl)),
        shared_prefixes={prefix: sum(n.startswith(prefix) for _, _, n in ws | bs)
                         for prefix in ("imfiredup", "thd", "yipz", "jpc", "trill", "scott", "sang")})


def cost_delta(before, after):
    # A reset or other concurrent client activity invalidates single-call attribution.
    delta = after["pointsSpentThisHour"] - before["pointsSpentThisHour"]
    if delta < 0 or after["pointsResetIn"] > before["pointsResetIn"] + 2:
        return None
    return round(delta, 6)


def estimated_target_cost(before, after, observer_cost=1.0):
    """Subtract the calibrated AFTER observer; before is already in its counter.

    This is an estimate for serial calls, not attribution under concurrent use.
    The calibration applies to the September 17 query shape/account observation.
    """
    delta = cost_delta(before, after)
    if delta is None or delta < observer_cost:
        return None
    return round(delta - observer_cost, 6)


class Session:
    def __init__(self, root=ROOT):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.archive = Archive(root / "raw.sqlite")
        self.clients = {}

    def client(self, source):
        if source not in self.clients:
            self.clients[source] = Client(source, self.archive)
        return self.clients[source]

    def save(self, label, value):
        # Append unique artifacts: repeated validation never replaces evidence.
        name = f"{time.time_ns()}-{label}.json"
        (self.root / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        with (self.root / "index.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"label": label, "file": name, "at": utcnow()}) + "\n")
        return value

    def last_response(self):
        row = self.archive.db.execute("""SELECT a.id, a.status, b.content FROM attempt a
          LEFT JOIN body b ON a.body_sha256=b.sha256 ORDER BY a.rowid DESC LIMIT 1""").fetchone()
        if row is None:
            return None, None, None
        try:
            value = json.loads(row[2]) if row[2] else None
        except ValueError:
            value = None
        return row[0], row[1], value

    def rate(self):
        return self.client("wcl").request(WCL_URL, {"query": (QUERIES / "rate-limit.graphql").read_text()})["data"]["rateLimitData"]

    def wcl(self, label, query, variables=None):
        before = self.rate()
        if before["pointsSpentThisHour"] > before["limitPerHour"] * .5:
            raise ProbeError("Feasibility safety budget reached (50% of hourly points)")
        before_id = self.last_response()[0]
        problem = None
        try:
            result = self.client("wcl").request(WCL_URL, {"query": query, "variables": variables or {}})
        except ProbeError as error:
            problem = str(error)
            result = self.last_response()[2] if self.last_response()[0] != before_id else None
        attempt_id, status, _ = self.last_response()
        if attempt_id == before_id:
            # A token failure can happen before an API observation exists.
            raise ProbeError("WCL call failed before a new API observation was archived")
        after = self.rate()
        after_id = self.last_response()[0]
        measurement = dict(label=label, at=utcnow(), before=before, after=after,
            delta=cost_delta(before, after), query_sha256=hashlib.sha256(query.encode()).hexdigest(),
            before_attempt=before_id, attempt=attempt_id, after_attempt=after_id, http_status=status,
            error=problem)
        with (self.root / "costs.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(measurement) + "\n")
        self.save(label, result)
        print(json.dumps({"label": label, "http_status": status, "points_delta": measurement["delta"],
                          "error": problem}), flush=True)
        return result

    def named(self, name, variables=None, label=None):
        return self.wcl(label or name, (QUERIES / (name + ".graphql")).read_text(), variables)

    def blizzard(self, label, kind, **kwargs):
        previous_id = self.last_response()[0]
        try:
            result = self.client("blizzard").request(blizzard_url(kind, **kwargs))
            self.save(label, result)
            print(json.dumps({"label": label, "result": "saved"}), flush=True)
            return result
        except ProbeError as error:
            attempt_id, _, response = self.last_response()
            if attempt_id == previous_id:
                raise ProbeError("Blizzard call failed before a new API observation was archived") from None
            self.save(label, response)
            print(json.dumps({"label": label, "error": str(error)}), flush=True)
            return None

    def close(self):
        self.archive.close()


def latest(label, root=ROOT):
    entries = [json.loads(line) for line in (root / "index.jsonl").read_text().splitlines()]
    path = next(row["file"] for row in reversed(entries) if row["label"] == label)
    return json.loads((root / path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["schema", "check-schema", "identity", "rosters", "query"])
    parser.add_argument("--name", choices=sorted(path.stem for path in QUERIES.glob("*.graphql")))
    parser.add_argument("--variables", type=Path)
    args = parser.parse_args()
    if args.action == "check-schema":
        results = validate_queries(latest("full-schema")["data"])
        print(json.dumps(results, indent=2))
        return int(any(results.values()))
    session = Session()
    try:
        if args.action == "schema":
            from graphql import get_introspection_query
            session.wcl("full-schema", get_introspection_query())
            results = validate_queries(latest("full-schema")["data"])
            session.save("schema-validation", results)
            print(json.dumps(results, indent=2))
            return int(any(results.values()))
        elif args.action == "identity":
            session.wcl("liquid-identity", """query {
              guildData { guild(name:"Liquid", serverSlug:"illidan", serverRegion:"US") {
                id name type competitionMode stealthMode
                server { id slug blizzardID region { id name } }
                parentGuild { id name } teams { id name type } tags { id name }
              } }
            }""")
            session.blizzard("liquid-blizzard-guild", "guild", realm="illidan", name="liquid")
        elif args.action == "rosters":
            def fetch(page):
                value = session.named("guild", dict(name="Liquid", serverSlug="illidan", serverRegion="US", page=page), f"roster-page-{page}")
                if not value or value.get("errors"):
                    raise ProbeError("Roster page failed; cannot claim completeness")
                return value["data"]["guildData"]["guild"]["members"]
            rows, pages = paginate(fetch)
            session.save("wcl-roster", {"rows": rows, "pages": pages})
            b = session.blizzard("blizzard-roster", "roster", realm="illidan", name="liquid")
            if b:
                comparison = compare_rosters(rows, b["members"])
                session.save("roster-comparison", comparison)
                print(json.dumps(comparison, ensure_ascii=True, indent=2))
        else:
            variables = json.loads(args.variables.read_text(encoding="utf-8-sig")) if args.variables else {}
            session.named(args.name, variables)
        return 0
    except ProbeError as error:
        print(str(error))
        return 2
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
