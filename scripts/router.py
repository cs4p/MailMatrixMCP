#!/usr/bin/env python3
"""
MailMatrix Routing Engine

Provider-agnostic email routing. Reads routing rules from SQLite and
returns folder decisions for a list of email metadata objects.

Usage (CLI):
    echo '[{"message_id": "...", "sender_email": "foo@bar.com", ...}]' | \
        python3 router.py --db mailmatrix.db

    python3 router.py --db mailmatrix.db --record < emails.json

Input JSON (list of email objects):
    message_id      str   Provider's unique message ID (required)
    sender_email    str   From address
    sender_domain   str   Domain part of from (auto-derived if omitted)
    recipients      list  All To + CC addresses
    subject         str   Email subject line
    date_sent       str   ISO-8601 date or datetime

Output JSON (list of decision objects):
    message_id          str   Echoed from input
    folder_name         str|null   Target folder name (null = no rule matched)
    folder_provider_id  str|null   Provider-specific folder ID
    matched_rule_id     int|null   Rule that matched
    confidence          float   0.0–1.0
    needs_ai_review     bool   True when no rule matched
"""
import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Core routing
# ---------------------------------------------------------------------------

def route_emails(db_path: str, emails: list, account_id: int = 1) -> list:
    """
    Given a list of email metadata dicts, return routing decisions.
    Unknown senders are flagged with needs_ai_review=True.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Load all active rules for this account, ordered by priority (lowest first)
    cur.execute("""
        SELECT r.*, f.name AS folder_name, f.provider_id AS folder_provider_id
        FROM mm_routing_rules r
        LEFT JOIN mm_folders f ON r.destination_folder_id = f.id
        WHERE r.account_id = ? AND r.is_active = 1
        ORDER BY r.priority ASC, r.id ASC
    """, (account_id,))
    rules = [dict(row) for row in cur.fetchall()]
    conn.close()

    results = []
    for email in emails:
        decision = _route_single(email, rules)
        results.append(decision)

    return results


def _route_single(email: dict, rules: list) -> dict:
    """Evaluate rules against one email and return a decision dict."""
    sender_email  = (email.get("sender_email") or "").lower().strip()
    sender_domain = (email.get("sender_domain") or
                     (sender_email.split("@")[-1] if "@" in sender_email else ""))
    recipients    = [r.lower().strip() for r in (email.get("recipients") or [])]
    subject       = (email.get("subject") or "").lower()
    date_sent     = _parse_date(email.get("date_sent"))

    for rule in rules:
        if _matches(rule, sender_email, sender_domain, recipients, subject, date_sent):
            return {
                "message_id":         email.get("message_id"),
                "folder_name":        rule["folder_name"],
                "folder_provider_id": rule["folder_provider_id"],
                "matched_rule_id":    rule["id"],
                "confidence":         rule["confidence"],
                "needs_ai_review":    False,
            }

    return {
        "message_id":         email.get("message_id"),
        "folder_name":        None,
        "folder_provider_id": None,
        "matched_rule_id":    None,
        "confidence":         0.0,
        "needs_ai_review":    True,
    }


def _matches(rule: dict, sender_email: str, sender_domain: str,
             recipients: list, subject: str, date_sent) -> bool:
    """Return True if ALL non-null rule conditions are satisfied."""

    # Exact sender email
    if rule["sender_email"]:
        if sender_email != rule["sender_email"].lower():
            return False

    # Sender domain
    if rule["sender_domain"]:
        if sender_domain != rule["sender_domain"].lower():
            return False

    # Recipient (alias routing)
    if rule["recipient_email"]:
        if rule["recipient_email"].lower() not in recipients:
            return False

    # Subject keywords
    if rule["subject_keywords"]:
        try:
            keywords = json.loads(rule["subject_keywords"])
        except (json.JSONDecodeError, TypeError):
            keywords = []
        if keywords:
            mode = (rule.get("subject_keywords_mode") or "ANY").upper()
            hits = [kw.lower() in subject for kw in keywords]
            if mode == "ALL" and not all(hits):
                return False
            if mode == "ANY" and not any(hits):
                return False

    # Date range
    if date_sent:
        if rule["active_after"]:
            after = _parse_date(rule["active_after"])
            if after and date_sent < after:
                return False
        if rule["active_before"]:
            before = _parse_date(rule["active_before"])
            if before and date_sent > before:
                return False

    return True


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        s = str(value)
        if "T" in s or (" " in s and len(s) > 10):
            return datetime.fromisoformat(s).date()
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Recording decisions
# ---------------------------------------------------------------------------

def record_routing(db_path: str, account_id: int,
                   decisions: list, emails: list) -> None:
    """Persist routing decisions to mm_processed_emails."""
    email_map = {str(e["message_id"]): e for e in emails}
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    for d in decisions:
        email = email_map.get(str(d["message_id"]), {})
        sender_email  = (email.get("sender_email") or "").lower()
        sender_domain = (email.get("sender_domain") or
                         (sender_email.split("@")[-1] if "@" in sender_email else ""))

        # Resolve folder_id
        folder_id = None
        if d.get("folder_name"):
            cur.execute("SELECT id FROM mm_folders WHERE account_id = ? AND name = ?",
                        (account_id, d["folder_name"]))
            row = cur.fetchone()
            if row:
                folder_id = row[0]

        cur.execute("""
            INSERT OR IGNORE INTO mm_processed_emails
                (account_id, message_id, sender_email, sender_domain,
                 recipients, subject, date_sent,
                 destination_folder_id, matched_rule_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            account_id,
            d["message_id"],
            sender_email,
            sender_domain,
            json.dumps(email.get("recipients", [])),
            email.get("subject", ""),
            email.get("date_sent", ""),
            folder_id,
            d.get("matched_rule_id"),
        ))

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# History-based suggestion (feeds AI recommendation)
# ---------------------------------------------------------------------------

def suggest_from_history(db_path: str, sender_email: str,
                         account_id: int = 1) -> dict | None:
    """
    Return the folder this sender's email has been routed to most often.
    Used as a hint when Claude is deciding where to put an unknown sender.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT f.name, f.provider_id, COUNT(*) AS cnt
        FROM mm_processed_emails pe
        JOIN mm_folders f ON pe.destination_folder_id = f.id
        WHERE pe.account_id = ? AND pe.sender_email = ?
        GROUP BY f.id
        ORDER BY cnt DESC
        LIMIT 1
    """, (account_id, sender_email.lower()))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MailMatrix routing engine")
    parser.add_argument("--db",      required=True, help="Path to SQLite database")
    parser.add_argument("--account", type=int, default=1, help="Account ID (default 1)")
    parser.add_argument("--record",  action="store_true",
                        help="Record decisions to processed_emails table")
    args = parser.parse_args()

    raw = json.load(sys.stdin)
    emails = raw if isinstance(raw, list) else raw.get("emails", [])

    decisions = route_emails(args.db, emails, args.account)

    if args.record:
        record_routing(args.db, args.account, decisions, emails)

    print(json.dumps(decisions, indent=2))
