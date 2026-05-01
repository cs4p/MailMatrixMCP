# MailMatrix

Intelligent, rule-based email routing for Claude Cowork. MailMatrix automatically
sorts your inbox by applying a database of routing rules — using sender address,
domain, recipient alias, subject keywords, and date ranges — then falls back to
Claude's own judgment for anything it hasn't seen before.

## How it works

1. **Rules engine** — A SQLite database stores routing rules. When you sort your
   inbox, email metadata (sender, subject, recipients, date) is matched against
   rules in priority order. Matched emails are moved automatically with no AI
   token cost.

2. **AI fallback** — Emails from unknown senders are evaluated by Claude, which
   suggests a folder based on context. High-confidence decisions are applied
   automatically and a new rule is created. Low-confidence emails go to a
   "For Review" folder.

3. **Learning** — Every routing decision is recorded. Over time the rules database
   grows, and less work falls to the AI fallback.

## Skills

| Skill | What it does |
|---|---|
| **setup** | First-time configuration: initialize DB, sync folders, optional migration |
| **sort-inbox** | Sort the inbox using rules + AI fallback |
| **manage-rules** | Add, view, edit, and disable routing rules |
| **review-unknowns** | Work through the For Review folder, create rules, clear the backlog |

## Routing rule features

- **Sender email** — exact from-address match
- **Sender domain** — match all email from a domain (e.g. `amazon.com`)
- **Recipient/alias** — route based on which of your addresses the email was sent to
- **Subject keywords** — match ANY or ALL keywords in the subject line
- **Date range** — rules that apply only within a specific date window
- **Priority** — control which rule wins when multiple rules match

## Getting started

1. Install the MailMatrix plugin in Cowork
2. Connect your email MCP server (see CONNECTORS.md)
3. Say: **"Set up MailMatrix"**
4. Say: **"Sort my inbox"**

## Migrating from legacy MailMatrix

If you have an existing MailMatrix (Django) database, the setup skill can import
your sender→folder routing history automatically. Your historical routing data
becomes learned rules in the new database.

## Provider support

MailMatrix is provider-agnostic. Tested with Fastmail. Gmail support is
documented in CONNECTORS.md. Any mail provider with a Cowork MCP connector
can be supported.

## Database

MailMatrix uses a plain SQLite database — no server required. The schema is in
`scripts/schema.sql`. The database stores:
- Accounts and folders
- Routing rules (with full history — rules are deactivated, never deleted)
- A log of every routing decision made

## License

MIT
