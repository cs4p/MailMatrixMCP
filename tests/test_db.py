import sqlite3

import db as db_module


class TestInitDb:
    def test_creates_all_tables(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert {"mm_accounts", "mm_folders", "mm_routing_rules",
                "mm_processed_emails"}.issubset(tables)

    def test_idempotent(self, tmp_db):
        db_module.init_db(tmp_db)  # second call must not raise


class TestEnsureAccount:
    def test_creates_account(self, tmp_db):
        account_id = db_module.ensure_account(tmp_db, name="Test", provider="fastmail")
        assert isinstance(account_id, int) and account_id > 0

    def test_returns_existing_account_on_second_call(self, tmp_db):
        id1 = db_module.ensure_account(tmp_db)
        id2 = db_module.ensure_account(tmp_db, name="Different Name")
        assert id1 == id2

    def test_does_not_create_duplicate(self, tmp_db):
        db_module.ensure_account(tmp_db)
        db_module.ensure_account(tmp_db)
        conn = sqlite3.connect(tmp_db)
        count = conn.execute("SELECT COUNT(*) FROM mm_accounts").fetchone()[0]
        conn.close()
        assert count == 1


class TestFolderManagement:
    def test_add_folder_returns_positive_id(self, seeded):
        assert seeded["financial_id"] > 0

    def test_add_folder_idempotent(self, seeded):
        s = seeded
        id1 = db_module.add_folder(s["db"], s["account_id"], "Financial", "fin-001")
        id2 = db_module.add_folder(s["db"], s["account_id"], "Financial", "fin-001")
        assert id1 == id2

    def test_list_folders_returns_all(self, seeded):
        s = seeded
        names = {f["name"] for f in db_module.list_folders(s["db"], s["account_id"])}
        assert {"Financial", "Newsletters", "For Review"}.issubset(names)

    def test_get_folder_id_correct(self, seeded):
        s = seeded
        assert db_module.get_folder_id(s["db"], s["account_id"], "Financial") == s["financial_id"]

    def test_get_folder_id_missing_returns_none(self, seeded):
        s = seeded
        assert db_module.get_folder_id(s["db"], s["account_id"], "Nonexistent") is None


class TestRuleManagement:
    def test_add_rule_returns_positive_id(self, seeded):
        s = seeded
        rule_id = db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                                     sender_domain="paypal.com")
        assert isinstance(rule_id, int) and rule_id > 0

    def test_add_rule_lowercases_email(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_email="Alice@EXAMPLE.COM")
        conn = sqlite3.connect(s["db"])
        row = conn.execute("SELECT sender_email FROM mm_routing_rules").fetchone()
        conn.close()
        assert row[0] == "alice@example.com"

    def test_list_rules_active_only_by_default(self, seeded):
        s = seeded
        rule_id = db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                                     sender_domain="paypal.com")
        db_module.add_rule(s["db"], s["account_id"], s["newsletter_id"],
                           sender_domain="substack.com")
        db_module.disable_rule(s["db"], rule_id)

        rules = db_module.list_rules(s["db"], s["account_id"])
        assert len(rules) == 1
        assert rules[0]["sender_domain"] == "substack.com"

    def test_list_rules_include_inactive(self, seeded):
        s = seeded
        rule_id = db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                                     sender_domain="paypal.com")
        db_module.disable_rule(s["db"], rule_id)

        rules = db_module.list_rules(s["db"], s["account_id"], include_inactive=True)
        assert len(rules) == 1

    def test_disable_rule_sets_inactive(self, seeded):
        s = seeded
        rule_id = db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                                     sender_domain="paypal.com")
        assert db_module.disable_rule(s["db"], rule_id) is True

        conn = sqlite3.connect(s["db"])
        row = conn.execute("SELECT is_active FROM mm_routing_rules WHERE id=?",
                           (rule_id,)).fetchone()
        conn.close()
        assert row[0] == 0

    def test_disable_nonexistent_rule_returns_false(self, seeded):
        assert db_module.disable_rule(seeded["db"], 9999) is False

    def test_update_rule_notes(self, seeded):
        s = seeded
        rule_id = db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                                     sender_domain="paypal.com")
        db_module.update_rule(s["db"], rule_id, notes="Updated note")

        conn = sqlite3.connect(s["db"])
        row = conn.execute("SELECT notes FROM mm_routing_rules WHERE id=?",
                           (rule_id,)).fetchone()
        conn.close()
        assert row[0] == "Updated note"

    def test_update_rule_unknown_fields_returns_false(self, seeded):
        s = seeded
        rule_id = db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                                     sender_domain="paypal.com")
        assert db_module.update_rule(s["db"], rule_id, nonexistent="bad") is False


class TestStats:
    def test_stats_reflect_db_state(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="paypal.com")
        db_module.add_rule(s["db"], s["account_id"], s["newsletter_id"],
                           sender_domain="substack.com")

        stats = db_module.get_stats(s["db"], s["account_id"])
        assert stats["active_rules"] == 2
        assert stats["folders"] == 3
        assert stats["emails_routed"] == 0
        assert stats["known_senders"] == 0
