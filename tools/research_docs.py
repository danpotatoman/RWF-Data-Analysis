"""Download public Blizzard documentation; never downloads credentials."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
from datetime import datetime, timezone

ROOT = "https://community.developer.battle.net/api/pages/content/documentation/"
PAGES = ["world-of-warcraft/profile-apis", "world-of-warcraft/game-data-apis",
         "guides/getting-started", "guides/using-oauth/client-credentials-flow",
         "world-of-warcraft/guides/namespaces",
         "guides/using-oauth"]

def main(folder=Path("data/research"), fetch=urlopen):
    folder.mkdir(parents=True, exist_ok=True)
    manifest = []
    for page in PAGES:
        url = ROOT + page + ".json"
        try:
            with fetch(url, timeout=30) as response:
                raw = response.read()
            name = page.replace("/", "_") + ".json"
            (folder / name).write_bytes(raw)
            manifest.append(dict(url=url, file=name, sha256=hashlib.sha256(raw).hexdigest(),
                                 fetched_at=datetime.now(timezone.utc).isoformat()))
            value = json.loads(raw)
            if "resources" in value:
                for resource in value["resources"]:
                    if any(term in resource["name"] for term in ("Equipment", "Character Profile", "Guild", "Realm", "Item", "Journal", "Achievement")):
                        for method in resource["methods"]:
                            print(method["name"], method["path"])
            else:
                print(page, "saved")
        except Exception as error:
            print(page, type(error).__name__)
            manifest.append(dict(url=url, error=type(error).__name__, fetched_at=datetime.now(timezone.utc).isoformat()))
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
