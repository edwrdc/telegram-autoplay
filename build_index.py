"""Rebuild the catalog after editing the plugin. Uses only the standard library."""

import argparse
import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "plugins/channel_video_autoplay.plugin"
INDEX = ROOT / "extera-plugins.json"


def build_index():
    data = PLUGIN.read_bytes()
    metadata = {}
    for node in ast.parse(data).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = node.targets[0]
            if isinstance(name, ast.Name) and name.id.startswith("__") and name.id.endswith("__"):
                metadata[name.id[2:-2]] = ast.literal_eval(node.value)
    for key in ("id", "name", "version"):
        if not metadata.get(key):
            raise ValueError(f"Missing plugin {key}")
    digest = hashlib.sha256(data).hexdigest()
    previous = json.loads(INDEX.read_text()) if INDEX.exists() else {}
    old = next((p for p in previous.get("plugins", []) if p["id"] == metadata["id"]), {})
    updated = (old.get("updated_at") if old.get("sha256") == digest else None)
    entry = {
        **metadata,
        "file": PLUGIN.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "size": len(data),
        "updated_at": updated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return {
        "schema": 1,
        "name": "Channel video autoplay",
        "description": "AyuGram video autoplay for chats, channels, and forum topics.",
        "homepage": "https://github.com/edwrdc/telegram-autoplay",
        "plugins": [entry],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the catalog is stale")
    args = parser.parse_args()
    rendered = json.dumps(build_index(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not INDEX.exists() or INDEX.read_text(encoding="utf-8") != rendered:
            parser.exit(1, "Catalog is stale. Run python3 build_index.py\n")
    else:
        INDEX.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
