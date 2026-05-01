---
name: mail-matrix-manage-rules
description: >
  Create, view, edit, and delete MailMatrix routing rules. Use when the user says
  "add a routing rule", "show my rules", "list mail matrix rules", "delete a rule",
  "edit a rule", "route everything from X to Y", "emails with subject Z go to folder W",
  "add a date range to a rule", "route emails sent to my alias", or any request to
  configure how email is automatically sorted. Supports sender, domain, recipient/alias,
  subject keyword, and date-range matching.
---

# MailMatrix — Manage Routing Rules

Create, list, update, and disable routing rules in the MailMatrix database.

## Setup

Load config to get DB_PATH and ACCOUNT_ID:
```bash
python3 -c "
import json, pathlib
cfg = json.loads(pathlib.Path('${CLAUDE_PLUGIN_ROOT}/data/config.json').read_text())
print(cfg['db_path'], cfg['account_id'])
"
```

## Commands

### List rules

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/db.py list-rules \
    --db DB_PATH --account ACCOUNT_ID
```

Present rules in a readable format grouped by destination folder. Show the
rule ID, matching criteria, priority, source, and confidence. Omit technical
fields unless the user asks.

### Add a rule

Parse the user's natural-language request into rule fields:

| What the user says | Field |
|---|---|
| "from alice@example.com" | `--sender-email alice@example.com` |
| "from anyone at amazon.com" | `--sender-domain amazon.com` |
| "sent to my alias dan@work.com" | `--recipient dan@work.com` |
| "subject contains 'invoice'" | `--keywords invoice` |
| "subject has 'receipt' or 'order'" | `--keywords "receipt,order" --keywords-mode ANY` |
| "subject must have both 'urgent' and 'action'" | `--keywords "urgent,action" --keywords-mode ALL` |
| "only after Jan 1 2025" | `--active-after 2025-01-01` |
| "only before March 2025" | `--active-before 2025-03-31` |
| "higher priority than others" | `--priority 50` (lower number = higher priority) |

First confirm the available folders:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/db.py list-folders \
    --db DB_PATH --account ACCOUNT_ID
```

Then add the rule:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/db.py add-rule \
    --db DB_PATH \
    --account ACCOUNT_ID \
    --folder "FOLDER_NAME" \
    [--sender-email EMAIL] \
    [--sender-domain DOMAIN] \
    [--recipient RECIPIENT] \
    [--keywords "kw1,kw2"] \
    [--keywords-mode ANY|ALL] \
    [--active-after YYYY-MM-DD] \
    [--active-before YYYY-MM-DD] \
    [--priority 100] \
    [--notes "Human-readable description"]
```

After adding, confirm to the user: "Rule created (ID: N) — emails from X will
go to Y."

### Disable / delete a rule

Rules are never hard-deleted; they are deactivated so routing history is preserved.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/db.py disable-rule \
    --db DB_PATH --rule-id RULE_ID
```

If the user asks to "delete" a rule, explain that it will be deactivated (not
permanently removed) so history is preserved. Confirm before proceeding.

### Edit a rule

Editing is done by disabling the old rule and creating a new one with the
updated fields. Show the user the existing rule values and confirm the changes
before applying.

### Show statistics

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/db.py stats \
    --db DB_PATH --account ACCOUNT_ID
```

## Rule priority guidance

Explain to the user when asked:
- Priority is a number; **lower = evaluated first** (default 100)
- More specific rules should have lower priority numbers than broad ones
- Example: a rule matching an exact email address (priority 50) should beat
  a rule matching a whole domain (priority 100)
- AI-recommended rules are created at priority 150; migrated/learned rules
  at priority 200

## Validation

Before creating a rule, check that it has at least one matching criterion
(sender_email, sender_domain, recipient_email, or subject_keywords).
A rule with no criteria would match every email — warn the user and ask
for clarification.

If the user adds a date range, verify that active_after is before active_before.
