# Connectors

## How tool references work

Plugin files use `~~email` as a placeholder for whatever email connector the user
has installed. MailMatrix is mail-provider-agnostic — it describes operations in
terms of what needs to happen (list inbox, move a message) rather than which
specific tool to call.

## Connectors for this plugin

| Category | Placeholder | Tested options |
|----------|-------------|----------------|
| Email    | `~~email`   | Fastmail MCP, Gmail MCP |

## Fastmail setup

Install the official Fastmail MCP connector. Once connected, the following
tools are available and map to MailMatrix operations:

| MailMatrix operation | Fastmail tool |
|---|---|
| List inbox messages | `fastmail_list_emails` (mailboxId = inbox ID) |
| List folders/mailboxes | `fastmail_list_mailboxes` |
| Move a message | `fastmail_move_email` |
| Mark as read | `fastmail_mark_read` |
| Search messages | `fastmail_search_emails` |

When running setup, use `fastmail_list_mailboxes` to discover folder IDs, then
register each folder in the MailMatrix database with both its name and its
Fastmail mailbox ID as the `provider_id`.

## Gmail setup

Install a Gmail MCP connector. Map Gmail operations to MailMatrix operations:

| MailMatrix operation | Gmail operation |
|---|---|
| List inbox messages | List messages with label INBOX |
| List folders | List labels |
| Move a message | Modify message labels (remove INBOX, add destination label) |

Gmail uses labels rather than folders; MailMatrix treats them equivalently.
The `provider_id` field in `mm_folders` stores the Gmail label ID.

## Adding a new provider

To support a new mail provider:
1. Connect its MCP server to Cowork
2. Run the MailMatrix setup skill — it will walk you through mapping the
   provider's folder/mailbox IDs into the MailMatrix database
3. When the sort-inbox skill references `~~email` operations, substitute the
   correct tool names for your provider
