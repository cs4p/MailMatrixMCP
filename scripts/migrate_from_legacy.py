#!/usr/bin/env python3
"""
MailMatrix Legacy Migration

Reads sender→folder history from the old Django-based MailMatrix SQLite
database and creates routing rules in the new MailMatrix database.

The old DB uses:
    MailData_emailmessage  (from_email, current_folder_id, date_sent)
    MailData_emailfolder   (name)

Each unique sender is mapped to their most-frequently-used non-inbox folder.
The rule confidence scales with the number of historical messages (capped at 1.0).

Usage:
    python3 migrate_from_legacy.py \
        --legacy-db /path/to/old/MailMatrix.sqlite3 \
        --new-db    /path/to/new/mailmatrix.db \
        [--account 1] \
        [--min-messages 2] \
        [--dry-run]
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db as mm_db


# Folders we do NOT want as migration destinations
SKIP_FOLDERS = {
    "INBOX",
    "MailMatrixCategories/For Review",
    "MailMatrixCategories",
    "MailMatrixCategories/INBOX",
}


def migrate(legacy_db_path: str, new_db_path: str,
            account_id: int = 1, min_messages: int = 2,
            dry_run: bool = False) -> dict:
    """
    Migrate sender→folder mappings from the legacy DB.

    Returns a stats dict:
        senders_found     Total unique senders with enough history
        rules_created     Rules successfully written to new DB
        folders_missing   Folder names from legacy DB not in new DB
        skipped           Senders skipped (folder missing or too few messages)
    """
    legacy = sqlite3.connect(legacy_db_path)
    legacy.row_factory = sqlite3.Row
    cur = legacy.cursor()

    # For each sender, find their most common non-inbox destination
    cur.execute("""
        SELECT
            m.from_email,
            f.name          AS folder_name,
            COUNT(*)        AS msg_count
        FROM MailData_emailmessage m
        JOIN MailData_emailfolder f ON m.current_folder_id = f.id
        WHERE f.name NOT IN ({})
        GROUP BY m.from_email, f.name
        HAVING COUNT(*) >= ?
        ORDER BY m.from_email ASC, msg_count DESC
    """.format(",".join("?" * len(SKIP_FOLDERS))),
        list(SKIP_FOLDERS) + [min_messages]
    )
    rows = cur.fetchall()
    legacy.close()

    # Keep only the top-ranked folder per sender
    sender_best: dict[str, dict] = {}
    for row in rows:
        sender = row["from_email"].lower().strip()
        if sender not in sender_best:
            sender_best[sender] = {
                "folder_name": row["folder_name"],
                "msg_count":   row["msg_count"],
            }

    # Build a lookup of folders already in the new DB
    existing_folders = {f["name"]: f for f in mm_db.list_folders(new_db_path, account_id)}

    stats = {
        "senders_found":   len(sender_best),
        "rules_created":   0,
        "folders_missing": [],
        "skipped":         0,
    }

    missing_set: set[str] = set()

    for sender_email, info in sender_best.items():
        folder_name = info["folder_name"]

        if folder_name not in existing_folders:
            missing_set.add(folder_name)
            stats["skipped"] += 1
            continue

        folder_id  = existing_folders[folder_name]["id"]
        # Confidence grows with message count; 10 messages → 1.0
        confidence = min(1.0, info["msg_count"] / 10.0)

        if dry_run:
            print(json.dumps({
                "sender":     sender_email,
                "folder":     folder_name,
                "messages":   info["msg_count"],
                "confidence": confidence,
            }))
        else:
            mm_db.add_rule(
                db_path=new_db_path,
                account_id=account_id,
                destination_folder_id=folder_id,
                sender_email=sender_email,
                priority=200,           # lower priority than manual rules
                source="learned",
                confidence=confidence,
                notes=f"Migrated from legacy MailMatrix ({info['msg_count']} historical messages)",
            )
        stats["rules_created"] += 1

    stats["folders_missing"] = sorted(missing_set)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate routing history from legacy MailMatrix database"
    )
    parser.add_argument("--legacy-db",    required=True,
                        help="Path to old MailMatrix.sqlite3")
    parser.add_argument("--new-db",       required=True,
                        help="Path to new mailmatrix.db")
    parser.add_argument("--account",      type=int, default=1)
    parser.add_argument("--min-messages", type=int, default=2,
                        help="Minimum historical messages to create a rule (default: 2)")
    parser.add_argument("--dry-run",      action="store_true",
                        help="Print what would be migrated without writing anything")
    args = parser.parse_args()

    stats = migrate(
        legacy_db_path=args.legacy_db,
        new_db_path=args.new_db,
        account_id=args.account,
        min_messages=args.min_messages,
        dry_run=args.dry_run,
    )
    print(json.dumps(stats, indent=2))
