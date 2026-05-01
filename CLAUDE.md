# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

MailMatrix is a **Cowork (Claude plugin) skill set** for intelligent email routing. It uses a SQLite rules database to move inbox emails into folders automatically, with Claude handling unknown senders as a fallback. Skills are defined as markdown files in `skills/` — they are instructions Claude executes, not code Claude calls.

## Commands

No build step required. Pure Python, no external dependencies.

```bash
# Initialize database
python3 scripts/db.py init --db ~/mailmatrix.db

# Add a routing rule
python3 scripts/db.py add-rule --db ~/mailmatrix.db \
    --folder "Financial" --sender-domain "paypal.com" --notes "PayPal receipts"

# List rules / folders / stats
python3 scripts/db.py list-rules --db ~/mailmatrix.db
python3 scripts/db.py list-folders --db ~/mailmatrix.db
python3 scripts/db.py stats --db ~/mailmatrix.db

# Disable a rule
python3 scripts/db.py disable-rule --db ~/mailmatrix.db --rule-id 42

# Run the routing engine (stdin → stdout JSON)
echo '[{"message_id":"123","sender_email":"alice@example.com","recipients":[],"subject":"Hi","date_sent":"2025-01-15"}]' | \
    python3 scripts/router.py --db ~/mailmatrix.db

# Route and record decisions
python3 scripts/router.py --db ~/mailmatrix.db --account 1 --record < emails.json > decisions.json

# Migrate from legacy Django MailMatrix
python3 scripts/migrate_from_legacy.py --legacy-db ~/old.db --new-db ~/mailmatrix.db
```

## Architecture

### Components

**`scripts/db.py`** — Database management CLI. All CRUD for accounts, folders, and routing rules. Also exposes Python functions (`init_db`, `ensure_account`, `add_folder`, etc.) that skills import directly via `sys.path.insert`.

**`scripts/router.py`** — Routing engine. Reads email metadata JSON from stdin, evaluates each email against active rules in priority order, and writes decisions to stdout. Also exposes `suggest_from_history()` for history-based folder hints on unknown senders. The `--record` flag writes decisions back to `mm_processed_emails`.

**`scripts/schema.sql`** — Single source of truth for the database schema.

**`scripts/migrate_from_legacy.py`** — One-shot importer from the old Django-based MailMatrix. Converts sender→folder history into learned rules with confidence scores.

**`skills/*/SKILL.md`** — Markdown instruction files that Claude executes as a Cowork plugin. Each skill is a complete workflow description with embedded bash commands. The `~~email` placeholder maps to the user's installed mail MCP connector (Fastmail or Gmail).

### Skill workflows

| Skill | Trigger phrase | What it does |
|---|---|---|
| `setup` | "set up MailMatrix" | Init DB, sync folders from mail provider, optional legacy import |
| `sort-inbox` | "sort my inbox" | Fetch inbox → route via rules → AI fallback → move emails → report |
| `manage-rules` | "manage rules" | CRUD for routing rules |
| `review-unknowns` | "review unknowns" | Triage the "For Review" folder, create rules, clear backlog |

### Routing logic

Rules are evaluated in ascending `priority` order (lower number wins). A rule matches when **all** its non-null criteria match: `sender_email`, `sender_domain`, `recipient` (alias), `subject_keywords`, and date range. Subject keywords use OR logic by default.

Confidence thresholds in `sort-inbox`:
- **≥ 0.8** → auto-move + create `ai_recommended` rule
- **< 0.8** → move to "For Review", no rule created

### Database key conventions

- Rules are **never hard-deleted** — only deactivated (`is_active = 0`). This preserves history.
- All email addresses are lowercased before storage/comparison.
- `subject_keywords` is stored as a JSON array in a TEXT column.
- `source` values: `manual`, `learned`, `ai_recommended`, `legacy_imported`.
- Default priorities: manual rules = 100, AI-recommended = 150, legacy = 200. Exact-email matches are typically set at 50, domain matches at 100.

### Provider abstraction

Skills reference `~~email` for all mail operations. The `CONNECTORS.md` file documents how `~~email` maps to Fastmail MCP tools (`fastmail_list_emails`, `fastmail_move_email`, etc.) and Gmail label operations. `provider_id` in `mm_folders` stores the provider-specific mailbox/label ID.

### Runtime environment

When executing as a Cowork plugin, `${CLAUDE_PLUGIN_ROOT}` resolves to the plugin installation directory. Config is stored at `${CLAUDE_PLUGIN_ROOT}/data/config.json` with keys `db_path` and `account_id`. Skills load this config at the start of each run.
