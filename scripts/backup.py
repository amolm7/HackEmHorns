"""Create or verify an online SQLite backup without overwriting existing files."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote


def verify(path):
    with closing(
        sqlite3.connect(
            "file:" + quote(str(Path(path).resolve())) + "?mode=ro", uri=True
        )
    ) as connection:
        result = connection.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise ValueError("Database integrity check failed.")
        return connection.execute("PRAGMA user_version").fetchone()[0]


def backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError("Source database does not exist.")
    if source == destination:
        raise ValueError("Choose a different destination.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with closing(
            sqlite3.connect("file:" + quote(str(source)) + "?mode=ro", uri=True)
        ) as live:
            with closing(sqlite3.connect(destination)) as copy:
                live.backup(copy)
        verify(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(root / "data" / "workforce.sqlite3"))
    parser.add_argument(
        "--destination",
        default=str(
            root
            / "data"
            / "backups"
            / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + ".sqlite3")
        ),
    )
    parser.add_argument(
        "--verify",
        metavar="DATABASE",
        help="Verify an existing database without creating a backup.",
    )
    args = parser.parse_args()
    if args.verify:
        verify(args.verify)
        print("Database integrity check passed.")
    else:
        output = backup(args.source, args.destination)
        print("Verified backup saved: " + str(output))


if __name__ == "__main__":
    main()
