-- MailMatrix Database Schema
-- Provider-agnostic email routing engine

CREATE TABLE IF NOT EXISTS mm_accounts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'generic',  -- 'fastmail', 'gmail', etc.
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mm_folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES mm_accounts(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,          -- Human-readable folder name
    provider_id TEXT,                   -- Provider-specific ID (e.g. Fastmail mailbox ID)
    UNIQUE(account_id, name)
);

-- Routing rules: all non-null conditions must match (AND logic)
-- Multiple rules can match the same email; the one with the lowest priority number wins.
CREATE TABLE IF NOT EXISTS mm_routing_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES mm_accounts(id) ON DELETE CASCADE,

    -- Matching criteria (all specified fields must match)
    sender_email            TEXT,   -- Exact from-address match (e.g. "alice@example.com")
    sender_domain           TEXT,   -- Domain of from-address (e.g. "amazon.com")
    recipient_email         TEXT,   -- Must appear in To or CC (useful for aliases)
    subject_keywords        TEXT,   -- JSON array, e.g. ["invoice","receipt"]
    subject_keywords_mode   TEXT    DEFAULT 'ANY',  -- 'ANY' (default) or 'ALL'

    -- Date constraints
    active_after    DATE,   -- Rule only applies to emails sent after this date
    active_before   DATE,   -- Rule only applies to emails sent before this date

    -- Destination
    destination_folder_id INTEGER REFERENCES mm_folders(id) ON DELETE SET NULL,

    -- Rule metadata
    priority    INTEGER DEFAULT 100,    -- Lower number = evaluated first
    is_active   INTEGER DEFAULT 1,
    source      TEXT    DEFAULT 'manual',   -- 'manual', 'learned', 'ai_recommended'
    confidence  REAL    DEFAULT 1.0,        -- 0.0–1.0; used by AI-recommended rules
    notes       TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- History of every routing decision made
CREATE TABLE IF NOT EXISTS mm_processed_emails (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES mm_accounts(id) ON DELETE CASCADE,
    message_id  TEXT NOT NULL,          -- Provider's unique message ID
    sender_email    TEXT,
    sender_domain   TEXT,
    recipients      TEXT,               -- JSON array of all To + CC addresses
    subject         TEXT,
    date_sent       DATETIME,
    destination_folder_id   INTEGER REFERENCES mm_folders(id) ON DELETE SET NULL,
    matched_rule_id         INTEGER REFERENCES mm_routing_rules(id) ON DELETE SET NULL,
    routed_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, message_id)
);

-- Indexes for fast rule lookups
CREATE INDEX IF NOT EXISTS idx_rules_sender_email
    ON mm_routing_rules(sender_email) WHERE sender_email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rules_sender_domain
    ON mm_routing_rules(sender_domain) WHERE sender_domain IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rules_recipient
    ON mm_routing_rules(recipient_email) WHERE recipient_email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_processed_sender
    ON mm_processed_emails(account_id, sender_email);
CREATE INDEX IF NOT EXISTS idx_processed_message
    ON mm_processed_emails(account_id, message_id);
