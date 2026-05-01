---
name: mail-matrix-setup
description: >
  Set up MailMatrix email routing for the first time or reconfigure it. Use when the user
  says "set up mail matrix", "configure mail matrix", "initialize mail matrix",
  "first time setup", or "run mail matrix setup". Also use when the user says
  the database is missing or folders have changed. Walks through initializing the
  database, syncing folders from the mail provider, optionally migrating from a
  legacy MailMatrix database, and running a first sort.
---

# MailMatrix Setup

Guide the user through a complete MailMatrix setup. By the end, the database
will be initialized, folders synced, routing rules in place, and the inbox
ready to sort.

## Variables

- **PLUGIN_ROOT**: `${CLAUDE_PLUGIN_ROOT}`
- **DB_PATH**: Ask the user where to store the database. Default: `~/Documents/Claude/mailmatrix/mailmatrix.db`
- **SCRIPTS**: `${CLAUDE_PLUGIN_ROOT}/scripts`

## Phase 1 — Initialize database

1. Create the database directory if needed:
   ```bash
   mkdir -p "$(dirname DB_PATH)"
   ```
2. Initialize the schema:
   ```bash
   python3 SCRIPTS/db.py init --db DB_PATH
   ```
3. Create the default account record:
   ```bash
   python3 - <<'EOF'
   import sys; sys.path.insert(0, "SCRIPTS")
   import db; db.ensure_account("DB_PATH", name="My Account", provider="~~email")
   EOF
   ```

## Phase 2 — Sync folders from mail provider

Use ~~email to list all mailboxes/folders. For each folder that belongs to
the user's sorting hierarchy (typically subfolders of a root category folder),
register it in the database.

For each folder discovered:
```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, "SCRIPTS")
import db
db.add_folder("DB_PATH", account_id=1, name="FOLDER_NAME", provider_id="PROVIDER_ID")
EOF
```

At minimum, register:
- The inbox folder
- All destination/category folders the user sorts into
- A "For Review" folder (create it via ~~email if it doesn't exist)

After syncing, confirm the folder list with the user.

## Phase 3 — Migrate from legacy MailMatrix (optional)

Ask the user: "Do you have a legacy MailMatrix.sqlite3 database you'd like to
import routing history from?"

If yes, ask for the path to the legacy database, then run:
```bash
python3 SCRIPTS/migrate_from_legacy.py \
    --legacy-db LEGACY_DB_PATH \
    --new-db DB_PATH \
    --min-messages 2
```

Show the migration stats. If any folders are listed under `folders_missing`,
inform the user which legacy folders weren't found in the new DB (they may have
been renamed) and offer to map them manually.

## Phase 4 — Create initial manual rules (optional)

Ask: "Would you like to add any routing rules now, or skip to the first sort?"

If the user wants to add rules, follow the manage-rules skill workflow.

## Phase 5 — Save configuration

Write a config file so other skills know where to find the database:
```bash
python3 - <<'EOF'
import json, pathlib
config = {"db_path": "DB_PATH", "account_id": 1}
pathlib.Path("${CLAUDE_PLUGIN_ROOT}/data/config.json").write_text(json.dumps(config, indent=2))
EOF
```

## Phase 6 — First sort (optional)

Ask: "Ready to sort the inbox now?" If yes, invoke the sort-inbox skill.

## Error handling

- If `~~email` tools are unavailable, explain that an email connector must be
  installed and connected before setup can proceed, and show the CONNECTORS.md
  guidance.
- If the database already exists and has data, confirm with the user before
  reinitializing (offer to just re-sync folders instead).
