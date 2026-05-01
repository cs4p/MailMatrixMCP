---
name: mail-matrix-sort-inbox
description: >
  Sort the inbox using MailMatrix routing rules. Use when the user says "sort my inbox",
  "run mail matrix", "file my email", "process my inbox", "clean up my inbox",
  or "sort new email". Also runs automatically as a scheduled task. Fetches inbox
  email metadata, applies routing rules from the database, moves matched emails
  automatically, and uses AI reasoning for any unmatched senders.
---

# MailMatrix — Sort Inbox

Fetch inbox messages, route known senders automatically via the rules database,
and handle unknown senders with AI judgment.

## Setup

Load config:
```bash
python3 -c "
import json, pathlib
cfg = json.loads(pathlib.Path('${CLAUDE_PLUGIN_ROOT}/data/config.json').read_text())
print(cfg['db_path'], cfg['account_id'])
"
```
Use the printed values as DB_PATH and ACCOUNT_ID throughout. If config is missing,
instruct the user to run the setup skill first.

## Step 1 — Fetch inbox metadata

Use ~~email to list messages in the inbox. Request **metadata only** (no body):
sender address, sender name, subject, date sent, message ID, and all recipient
addresses (To + CC). Fetch up to 200 messages per run (configurable).

Build a JSON array:
```json
[
  {
    "message_id": "...",
    "sender_email": "alice@example.com",
    "sender_domain": "example.com",
    "recipients": ["me@myaddress.com"],
    "subject": "Your invoice is ready",
    "date_sent": "2025-01-15"
  }
]
```

Write the array to `/tmp/mm_inbox.json`.

## Step 2 — Run the routing engine

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/router.py \
    --db DB_PATH \
    --account ACCOUNT_ID \
    --record \
    < /tmp/mm_inbox.json \
    > /tmp/mm_decisions.json
```

Read `/tmp/mm_decisions.json`. Each entry has:
- `message_id` — the message to act on
- `folder_name` — destination (null if unmatched)
- `folder_provider_id` — provider-specific folder ID
- `matched_rule_id` — which rule matched
- `confidence` — 0.0–1.0
- `needs_ai_review` — true when no rule matched

## Step 3 — Move matched emails

For every decision where `needs_ai_review` is false and `folder_name` is set:
use ~~email to move `message_id` to `folder_provider_id` (or `folder_name` if
the provider uses names). Do this efficiently — batch where the provider allows.

Track counts: how many moved to each folder.

## Step 4 — Handle unmatched emails (AI review)

For each email where `needs_ai_review` is true:

1. **Check routing history** — the sender may have been routed before without
   a formal rule:
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
   import router, json
   hint = router.suggest_from_history('DB_PATH', 'SENDER_EMAIL', ACCOUNT_ID)
   print(json.dumps(hint))
   "
   ```
   If history exists, use that folder with high confidence.

2. **AI reasoning** — Using sender name, domain, subject, and your knowledge
   of the user's folder taxonomy, determine the most appropriate folder.
   Consider:
   - Is this transactional (receipts, shipping, bills) → Financial/Amazon/etc.
   - Is this a newsletter or marketing → vendor/Unsubscribe
   - Is this from a person the user knows → Family/VIP/For Review
   - Is this automated notification → Notifications
   - When uncertain → For Review

3. **High confidence** (≥ 0.8): Move the email and create a learned rule:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/db.py add-rule \
       --db DB_PATH \
       --account ACCOUNT_ID \
       --folder "FOLDER_NAME" \
       --sender-domain "DOMAIN" \
       --source ai_recommended \
       --confidence 0.85 \
       --notes "AI-routed: REASON"
   ```

4. **Low confidence** (< 0.8): Move to For Review folder. Do NOT create a rule.

## Step 5 — Report

Summarize the run:
- Total inbox messages processed
- Moved by rule: N (breakdown by folder)
- Moved by AI: N (breakdown by folder)
- Sent to For Review: N
- New rules created: N

If any high-volume senders went to For Review (5+ emails from same domain),
flag them — they're good candidates for a manual rule.

## Notes

- Never read full email bodies unless absolutely necessary for AI routing
  decisions on ambiguous messages. Metadata is almost always sufficient.
- If the inbox is empty, report that and exit cleanly.
- If ~~email returns an error, report it and do not attempt partial moves.
