"""Firefox utilities for cookie handling.

This module provides functions to read cookies from Firefox's cookies.sqlite
database while Firefox is running. This is useful for authenticating web
requests with session cookies.

Key Design Decisions:
--------------------

1. Why copy to temp directory?
   Firefox uses EXCLUSIVE locking mode, meaning other processes cannot open
   the database directly. By copying to a temp location, we avoid locking
   issues and also avoid filesystem errors on certain mounts (like 9p).

2. Why copy WAL (Write-Ahead Log) files?
   SQLite in WAL mode stores committed transactions in a separate WAL file
   (-wal), not in the main database file. The main database is only updated
   during a checkpoint (default: every 1000 pages or ~4MB of writes).

   If we don't copy the WAL file, we would miss ALL cookies added since
   the last checkpoint - which could be hours or even days if Firefox
   doesn't write much.

   Reference: https://sqlite.org/wal.html

   Note: We do NOT copy the SHM file (wal-index). The SHM file is a
   performance optimization with no persistent data - SQLite will simply
   scan the WAL directly if SHM is missing. This is slower but correct.

   Reference: https://sqlite.org/tempfiles.html#shared-memory_files

3. Race condition considerations:
   - The theoretical race condition is minimal because we copy to a temp
     directory first, isolating from Firefox's active writes
   - SQLite readers can detect and handle incomplete WAL frames gracefully
   - The code filters cookies by expiry time, providing additional safety
   - Worst case: slightly stale cookies, not corrupted data

4. Alternative approaches considered:
   - Forcing checkpoint: Requires write access and closing Firefox
   - Read-only mode: Still conflicts with Firefox's exclusive lock

The current implementation balances data freshness (integrity) with safe
read operations (robustness).
"""

import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from requests.cookies import RequestsCookieJar


def read_firefox_cookies(profile_dir: Path) -> RequestsCookieJar:
    """Read cookies from Firefox profile directory and return a CookieJar.

    Uses read-only mode to allow reading while Firefox is running.
    Copies the database to a temp location to avoid locking issues.

    Args:
        profile_dir: Path to Firefox profile directory

    Returns:
        RequestsCookieJar with valid (non-session, non-expired) cookies
    """
    cookies_db = profile_dir / "cookies.sqlite"

    if not cookies_db.exists():
        raise FileNotFoundError(cookies_db)

    jar = RequestsCookieJar()

    # Copy cookies.sqlite and WAL file to temp location.
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_cookies = Path(tmpdir) / "cookies.sqlite"
        shutil.copy(cookies_db, tmp_cookies)

        # Copy WAL file if it exists
        if (wal_file := profile_dir / "cookies.sqlite-wal").exists():
            shutil.copy(wal_file, tmp_cookies.with_suffix(".sqlite-wal"))

        # Connect to the copied database
        conn = sqlite3.connect(str(tmp_cookies))
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).timestamp()

        # Directly query the columns we need (works for modern Firefox)
        cursor.execute("""
            SELECT name, value, host, path, expiry, isSecure
            FROM moz_cookies
        """)

        for row in cursor.fetchall():
            name, value, host, path, expiry, is_secure = row

            # Skip session cookies (expiry <= 0)
            if expiry is None or expiry <= 0:
                continue

            # Skip expired cookies
            # Firefox stores expiry in milliseconds since Unix epoch
            try:
                exp_ts = expiry / 1e3  # Convert to seconds
                if exp_ts < now:
                    continue
            except (OSError, OverflowError, ValueError):
                continue

            # Add cookie to jar
            # domain should not have leading dot for requests
            domain = host.lstrip(".") if host else ""
            cookie_path = path if path else "/"

            jar.set(
                name=name,
                value=value,
                domain=domain,
                path=cookie_path,
                secure=bool(is_secure),
            )

        conn.close()

    return jar
