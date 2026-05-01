---
name: mail-matrix-review-unknowns
description: >
  Review and route emails that MailMatrix couldn't sort automatically. Use when the
  user says "review unknowns", "process for review folder", "clear my for review folder",
  "what's in for review", "help me sort unsorted emails", or "create rules for unknown senders".
  Works through unmatched emails one sender at a time, creates routing rules, and clears
  the For Review folder.
---

# MailMatrix — Review Unknowns

Work through emails in the For Review folder, create routing rules for new
senders, and clear the backlog.

## Setup

Load config to get DB_PATH and ACCOUNT_ID:
```bash
python3 -c "
import json, pathlib
cfg = json.loads(pathlib.Path('${CLAUDE_PLUGIN_ROOT}/data/config.json').read_text())
print(cfg['db_path'], cfg['account_id'])
"
```

Get the For Review folder's provider ID from the database:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/db.py list-folders \
    --db DB_PATH --account ACCOUNT_ID
```

## Step 1 — Fetch For Review contents

Use ~~email to list messages in the For Review folder (metadata only:
sender, subject, date, message ID, recipients). Group by sender domain
so related emails are reviewed together.

If the folder is empty, report that and exit.

## Step 2 — Triage by sender group

For each unique sender domain (starting with the highest volume):

1. Show a summary:
   - Sender name and address
   - Number of emails from this sender
   - Subject line samples (up to 3)
   - Date range of emails

2. Use your judgment to suggest a destination folder, considering:
   - Sender domain type (commercial, nonprofit, government, personal)
   - Subject line patterns (transactional, marketing, personal, automated)
   - Recipient addresses (which alias was used — useful for alias-based routing)
   - Whether similar domains already have rules in the database

   Check for routing history:
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
   import router, json
   hint = router.suggest_from_history('DB_PATH', 'SENDER_EMAIL', ACCOUNT_ID)
   print(json.dumps(hint))
   "
   ```

3. Present a recommendation to the user, e.g.:
   "3 emails from newsletters@acme.com (subjects: 'Monthly digest', 'Your update').
   Suggested folder: **vendor**. Create a rule for acme.com? [Yes / Different folder / Skip]"

4. Based on the user's response:
   - **Yes** or folder confirmed: create a rule and move all emails from this sender
   - **Different folder**: ask which folder, then create the rule and move
   - **Skip**: leave in For Review, note it was skipped

## Step 3 — Create rules and move emails

When the user confirms a folder for a sender:

Create the rule (prefer domain-level rule unless the sender is a unique personal address):
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/db.py add-rule \
    --db DB_PATH \
    --account ACCOUNT_ID \
    --folder "FOLDER_NAME" \
    --sender-domain "DOMAIN" \
    --source manual \
    --notes "Created during review session"
```

Then use ~~email to move all messages from this sender in the For Review
folder to the confirmed destination.

Record the routing in the database:
```bash
python3 -c "
import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
import router, json
emails = [PROCESSED_EMAIL_DICTS]
router.record_routing('DB_PATH', ACCOUNT_ID, [DECISION_DICTS], emails)
"
```

## Step 4 — Session summary

After working through the senders (or when the user wants to stop):
- Rules created: N
- Emails moved: N (breakdown by destination)
- Senders skipped: N (still in For Review)

If many senders were skipped, offer to continue in another session.

## Pacing

Do not try to process all senders in one go if there are many. After every
10 senders, check in: "We've reviewed 10 senders. Continue with the next
batch or stop here?"
