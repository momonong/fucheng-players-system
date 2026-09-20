"""Read-only inventory/fingerprints. Never picks a production source or exposes rows."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def inventory():
    databases = {}
    for path in sorted((ROOT / "data").glob("*.db")):
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            tables = [x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            values = {}
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                rows = db.execute(f"SELECT * FROM {quoted}").fetchall()
                hashes = sorted(hashlib.sha256(repr(row).encode()).hexdigest() for row in rows)
                values[table] = {"count": len(rows), "rows_sha256": hashlib.sha256("".join(hashes).encode()).hexdigest()}
            revision = db.execute("SELECT version_num FROM alembic_version").fetchone() if "alembic_version" in tables else None
            databases[path.name] = {"revision": revision[0] if revision else None, "tables": values}
    files = {}
    for pattern in ["frontend/dist-public/**/*", "frontend/dist-delete/**/*", "frontend/dist-levels/**/*", "data/*admin*.json"]:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file():
                files[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"databases": databases, "protected_files": files, "authoritative_source": "UNDECIDED; requires owner confirmation"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Inventory output exists")
    args.output.write_text(json.dumps(inventory(), indent=2), encoding="utf-8")
    print(f"Read-only inventory saved: {args.output}; no member rows or credentials exported")
