#!/usr/bin/env python3
"""
MailMatrix Database Management

Create and manage the MailMatrix SQLite database: initialize schema,
manage folders and routing rules, and query statistics.

Usage:
    python3 db.py init --db mailmatrix.db
    python3 db.py stats --db mailmatrix.db
    python3 db.py list-rules --db mailmatrix.db
    python3 db.py list-folders --db mailmatrix.db
    python3 db.py add-rule --db mailmatrix.db --folder "MailMatrixCategories/Financial" \
        --sender-domain "paypal.com" --notes "PayPal receipts"
    python3 db.py disable-rule --db mailmatrix.db --rule-id 42
"""
import argparse
import json
import sqlite3
from pathlib import Path


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> None:
    """Create all MailMatrix tables if they don't already exist."""
    schema_path = Path(__file__).parent / "schema.sql"
    conn = sqlite3.connect(db_path)
    conn.executescript(schema_path.read_text())
    conn.commit()
    conn.close()
    print(f"Database ready at {db_path}")


def ensure_account(db_path: str, name: str = "Default",
                   provider: str = "generic") -> int:
    """Return the account ID, creating a default account if none exists."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id FROM mm_accounts LIMIT 1")
    row = cur.fetchone()
    if row:
        conn.close()
        return row[0]
    cur.execute("INSERT INTO mm_accounts (name, provider) VALUES (?, ?)",
                (name, provider))
    conn.commit()
    account_id = cur.lastrowid
    conn.close()
    return account_id


# ---------------------------------------------------------------------------
# Folder management
# ---------------------------------------------------------------------------

def add_folder(db_path: str, account_id: int, name: str,
               provider_id: str = None) -> int:
    """Add a folder; return its ID (idempotent)."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO mm_folders (account_id, name, provider_id)
        VALUES (?, ?, ?)
    """, (account_id, name, provider_id))
    conn.commit()
    cur.execute("SELECT id FROM mm_folders WHERE account_id = ? AND name = ?",
                (account_id, name))
    folder_id = cur.fetchone()[0]
    conn.close()
    return folder_id


def list_folders(db_path: str, account_id: int) -> list:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, provider_id
        FROM mm_folders
        WHERE account_id = ?
        ORDER BY name
    """, (account_id,))
    folders = [dict(row) for row in cur.fetchall()]
    conn.close()
    return folders


def get_folder_id(db_path: str, account_id: int, name: str) -> int | None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id FROM mm_folders WHERE account_id = ? AND name = ?",
                (account_id, name))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Routing rule management
# ---------------------------------------------------------------------------

def add_rule(db_path: str, account_id: int, destination_folder_id: int,
             sender_email: str = None, sender_domain: str = None,
             recipient_email: str = None,
             subject_keywords: list = None,
             subject_keywords_mode: str = "ANY",
             active_after: str = None, active_before: str = None,
             priority: int = 100, source: str = "manual",
             confidence: float = 1.0, notes: str = None) -> int:
    """Insert a routing rule and return its ID."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO mm_routing_rules
            (account_id, sender_email, sender_domain, recipient_email,
             subject_keywords, subject_keywords_mode,
             active_after, active_before,
             destination_folder_id, priority, source, confidence, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        account_id,
        sender_email.lower()   if sender_email   else None,
        sender_domain.lower()  if sender_domain  else None,
        recipient_email.lower() if recipient_email else None,
        json.dumps(subject_keywords) if subject_keywords else None,
        subject_keywords_mode,
        active_after,
        active_before,
        destination_folder_id,
        priority,
        source,
        confidence,
        notes,
    ))
    conn.commit()
    rule_id = cur.lastrowid
    conn.close()
    return rule_id


def update_rule(db_path: str, rule_id: int, **fields) -> bool:
    """
    Update specific fields on a routing rule.
    Allowed fields: sender_email, sender_domain, recipient_email,
    subject_keywords (list), subject_keywords_mode, active_after,
    active_before, destination_folder_id, priority, confidence,
    is_active, notes.
    """
    allowed = {
        "sender_email", "sender_domain", "recipient_email",
        "subject_keywords", "subject_keywords_mode",
        "active_after", "active_before",
        "destination_folder_id", "priority", "confidence",
        "is_active", "notes",
    }
    updates = {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "subject_keywords" and isinstance(v, list):
            v = json.dumps(v)
        if k in ("sender_email", "sender_domain", "recipient_email") and v:
            v = v.lower()
        updates[k] = v

    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [rule_id]
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"UPDATE mm_routing_rules SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        values
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def disable_rule(db_path: str, rule_id: int) -> bool:
    return update_rule(db_path, rule_id, is_active=0)


def list_rules(db_path: str, account_id: int,
               include_inactive: bool = False) -> list:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    where = "r.account_id = ?"
    if not include_inactive:
        where += " AND r.is_active = 1"
    cur.execute(f"""
        SELECT r.*, f.name AS folder_name
        FROM mm_routing_rules r
        LEFT JOIN mm_folders f ON r.destination_folder_id = f.id
        WHERE {where}
        ORDER BY r.priority ASC, r.created_at ASC
    """, (account_id,))
    rules = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rules


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def get_stats(db_path: str, account_id: int) -> dict:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    stats = {}
    cur.execute("SELECT COUNT(*) FROM mm_routing_rules WHERE account_id=? AND is_active=1",
                (account_id,))
    stats["active_rules"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM mm_processed_emails WHERE account_id=?",
                (account_id,))
    stats["emails_routed"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT sender_email) FROM mm_processed_emails WHERE account_id=?",
                (account_id,))
    stats["known_senders"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM mm_folders WHERE account_id=?", (account_id,))
    stats["folders"] = cur.fetchone()[0]

    cur.execute("""
        SELECT f.name, COUNT(*) AS cnt
        FROM mm_processed_emails pe
        JOIN mm_folders f ON pe.destination_folder_id = f.id
        WHERE pe.account_id = ?
        GROUP BY f.id ORDER BY cnt DESC LIMIT 5
    """, (account_id,))
    stats["top_folders"] = [{"folder": r[0], "count": r[1]}
                            for r in cur.fetchall()]
    conn.close()
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MailMatrix database management")
    parser.add_argument("command",
        choices=["init", "stats", "list-rules", "list-folders",
                 "add-rule", "disable-rule"])
    parser.add_argument("--db",      required=True)
    parser.add_argument("--account", type=int, default=1)

    # add-rule args
    parser.add_argument("--folder",           help="Destination folder name")
    parser.add_argument("--sender-email",     help="Exact from-address to match")
    parser.add_argument("--sender-domain",    help="Sender domain to match")
    parser.add_argument("--recipient",        help="Recipient address to match")
    parser.add_argument("--keywords",         help="Comma-separated subject keywords")
    parser.add_argument("--keywords-mode",    default="ANY", choices=["ANY", "ALL"])
    parser.add_argument("--active-after",     help="YYYY-MM-DD start date")
    parser.add_argument("--active-before",    help="YYYY-MM-DD end date")
    parser.add_argument("--priority",         type=int, default=100)
    parser.add_argument("--source",           default="manual")
    parser.add_argument("--confidence",       type=float, default=1.0)
    parser.add_argument("--notes")

    # disable-rule args
    parser.add_argument("--rule-id", type=int)

    args = parser.parse_args()

    if args.command == "init":
        init_db(args.db)

    elif args.command == "stats":
        print(json.dumps(get_stats(args.db, args.account), indent=2))

    elif args.command == "list-rules":
        rules = list_rules(args.db, args.account)
        print(json.dumps(rules, indent=2, default=str))

    elif args.command == "list-folders":
        print(json.dumps(list_folders(args.db, args.account), indent=2))

    elif args.command == "add-rule":
        if not args.folder:
            print("--folder is required for add-rule", file=sys.stderr)
            sys.exit(1)
        folder_id = get_folder_id(args.db, args.account, args.folder)
        if folder_id is None:
            print(f"Folder '{args.folder}' not found. Run list-folders to see available folders.",
                  file=sys.stderr)
            sys.exit(1)
        keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else None
        rule_id = add_rule(
            db_path=args.db, account_id=args.account,
            destination_folder_id=folder_id,
            sender_email=args.sender_email,
            sender_domain=args.sender_domain,
            recipient_email=args.recipient,
            subject_keywords=keywords,
            subject_keywords_mode=args.keywords_mode,
            active_after=args.active_after,
            active_before=args.active_before,
            priority=args.priority, source=args.source,
            confidence=args.confidence, notes=args.notes,
        )
        print(json.dumps({"rule_id": rule_id, "status": "created"}))

    elif args.command == "disable-rule":
        if not args.rule_id:
            print("--rule-id is required", file=sys.stderr)
            sys.exit(1)
        ok = disable_rule(args.db, args.rule_id)
        print(json.dumps({"rule_id": args.rule_id, "disabled": ok}))
