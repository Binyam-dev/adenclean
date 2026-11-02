"""Write a JSON backup of all AdenClean data (admin password hashes are not included).

    python export_backup.py [output-directory]

Appwrite's free plan has no automatic backups, so run this on a schedule and copy the
file somewhere other than the machine that runs the app. The file contains customer
and cleaner details: store it privately and delete old copies on a schedule.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import store as storage


def main(argv):
    folder = Path(argv[0] if argv else "backups")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = storage.open_store().export_all()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = folder / f"adenclean-{stamp}.json"
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"exported_at": stamp, "tables": data}, handle, indent=2)
    counts = ", ".join(f"{name}={len(rows)}" for name, rows in data.items())
    print(f"Wrote {target} ({counts})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (RuntimeError, storage.StoreError) as error:
        print(f"Error: {error}")
        sys.exit(1)
