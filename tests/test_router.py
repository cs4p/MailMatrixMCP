import sqlite3

import db as db_module
import router as router_module


def make_email(message_id="msg1", sender_email="alice@example.com",
               recipients=None, subject="Hello", date_sent="2025-01-15",
               sender_domain=None):
    e = {
        "message_id":   message_id,
        "sender_email": sender_email,
        "recipients":   recipients or [],
        "subject":      subject,
        "date_sent":    date_sent,
    }
    if sender_domain is not None:
        e["sender_domain"] = sender_domain
    return e


def route_one(db, account_id, email):
    return router_module.route_emails(db, [email], account_id)[0]


# ---------------------------------------------------------------------------
# No rules
# ---------------------------------------------------------------------------

class TestNoRules:
    def test_flags_for_ai_review(self, seeded):
        s = seeded
        d = route_one(s["db"], s["account_id"], make_email())
        assert d["needs_ai_review"] is True
        assert d["folder_name"] is None
        assert d["folder_provider_id"] is None
        assert d["matched_rule_id"] is None
        assert d["confidence"] == 0.0
        assert d["message_id"] == "msg1"


# ---------------------------------------------------------------------------
# Sender email matching
# ---------------------------------------------------------------------------

class TestSenderEmail:
    def test_exact_match_routes(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_email="alice@example.com")
        d = route_one(s["db"], s["account_id"], make_email())
        assert d["needs_ai_review"] is False
        assert d["folder_name"] == "Financial"
        assert d["folder_provider_id"] == "fin-001"

    def test_case_insensitive(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_email="alice@example.com")
        d = route_one(s["db"], s["account_id"], make_email(sender_email="ALICE@EXAMPLE.COM"))
        assert d["needs_ai_review"] is False

    def test_different_address_no_match(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_email="alice@example.com")
        d = route_one(s["db"], s["account_id"], make_email(sender_email="bob@example.com"))
        assert d["needs_ai_review"] is True


# ---------------------------------------------------------------------------
# Sender domain matching
# ---------------------------------------------------------------------------

class TestSenderDomain:
    def test_domain_match_routes(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="paypal.com")
        d = route_one(s["db"], s["account_id"], make_email(sender_email="noreply@paypal.com"))
        assert d["folder_name"] == "Financial"

    def test_domain_auto_derived_from_sender_email(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="amazon.com")
        d = route_one(s["db"], s["account_id"], make_email(sender_email="orders@amazon.com"))
        assert d["needs_ai_review"] is False

    def test_subdomain_does_not_match_parent_domain(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="amazon.com")
        d = route_one(s["db"], s["account_id"],
                      make_email(sender_email="x@seller.amazon.com"))
        assert d["needs_ai_review"] is True


# ---------------------------------------------------------------------------
# Recipient / alias matching
# ---------------------------------------------------------------------------

class TestRecipient:
    def test_alias_in_recipients_routes(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["newsletter_id"],
                           recipient_email="newsletters@mybox.com")
        d = route_one(s["db"], s["account_id"],
                      make_email(recipients=["newsletters@mybox.com", "me@mybox.com"]))
        assert d["folder_name"] == "Newsletters"

    def test_alias_absent_no_match(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["newsletter_id"],
                           recipient_email="newsletters@mybox.com")
        d = route_one(s["db"], s["account_id"],
                      make_email(recipients=["me@mybox.com"]))
        assert d["needs_ai_review"] is True


# ---------------------------------------------------------------------------
# Subject keyword matching
# ---------------------------------------------------------------------------

class TestSubjectKeywords:
    def test_any_mode_single_keyword(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           subject_keywords=["invoice"], subject_keywords_mode="ANY")
        d = route_one(s["db"], s["account_id"], make_email(subject="Your invoice is ready"))
        assert d["folder_name"] == "Financial"

    def test_any_mode_one_of_many_matches(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           subject_keywords=["invoice", "receipt", "payment"],
                           subject_keywords_mode="ANY")
        d = route_one(s["db"], s["account_id"], make_email(subject="Payment confirmation"))
        assert d["needs_ai_review"] is False

    def test_any_mode_no_keyword_no_match(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           subject_keywords=["invoice", "receipt"],
                           subject_keywords_mode="ANY")
        d = route_one(s["db"], s["account_id"], make_email(subject="Hello from Alice"))
        assert d["needs_ai_review"] is True

    def test_all_mode_all_present(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           subject_keywords=["order", "shipped"],
                           subject_keywords_mode="ALL")
        d = route_one(s["db"], s["account_id"],
                      make_email(subject="Your order has been shipped"))
        assert d["folder_name"] == "Financial"

    def test_all_mode_partial_no_match(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           subject_keywords=["order", "shipped"],
                           subject_keywords_mode="ALL")
        d = route_one(s["db"], s["account_id"],
                      make_email(subject="Your order is processing"))
        assert d["needs_ai_review"] is True

    def test_keywords_case_insensitive(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           subject_keywords=["invoice"])
        d = route_one(s["db"], s["account_id"], make_email(subject="INVOICE #1234"))
        assert d["needs_ai_review"] is False


# ---------------------------------------------------------------------------
# Date range constraints
# ---------------------------------------------------------------------------

class TestDateRange:
    def test_before_active_after_no_match(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="paypal.com", active_after="2025-06-01")
        d = route_one(s["db"], s["account_id"],
                      make_email(sender_email="x@paypal.com", date_sent="2025-01-01"))
        assert d["needs_ai_review"] is True

    def test_after_active_after_matches(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="paypal.com", active_after="2025-01-01")
        d = route_one(s["db"], s["account_id"],
                      make_email(sender_email="x@paypal.com", date_sent="2025-06-01"))
        assert d["needs_ai_review"] is False

    def test_after_active_before_no_match(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="paypal.com", active_before="2025-01-01")
        d = route_one(s["db"], s["account_id"],
                      make_email(sender_email="x@paypal.com", date_sent="2025-06-01"))
        assert d["needs_ai_review"] is True

    def test_before_active_before_matches(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="paypal.com", active_before="2025-12-31")
        d = route_one(s["db"], s["account_id"],
                      make_email(sender_email="x@paypal.com", date_sent="2025-06-01"))
        assert d["needs_ai_review"] is False


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

class TestPriority:
    def test_lower_priority_number_wins(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["newsletter_id"],
                           sender_domain="example.com", priority=200)
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="example.com", priority=50)
        d = route_one(s["db"], s["account_id"],
                      make_email(sender_email="anyone@example.com"))
        assert d["folder_name"] == "Financial"

    def test_exact_email_rule_at_lower_priority_beats_domain(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["newsletter_id"],
                           sender_domain="example.com", priority=100)
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_email="alice@example.com", priority=50)
        d = route_one(s["db"], s["account_id"], make_email())
        assert d["folder_name"] == "Financial"


# ---------------------------------------------------------------------------
# Disabled rules
# ---------------------------------------------------------------------------

class TestDisabledRules:
    def test_disabled_rule_not_matched(self, seeded):
        s = seeded
        rule_id = db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                                     sender_domain="paypal.com")
        db_module.disable_rule(s["db"], rule_id)
        d = route_one(s["db"], s["account_id"],
                      make_email(sender_email="x@paypal.com"))
        assert d["needs_ai_review"] is True


# ---------------------------------------------------------------------------
# AND logic (combined criteria)
# ---------------------------------------------------------------------------

class TestCombinedCriteria:
    def test_both_criteria_must_match(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="amazon.com", subject_keywords=["shipped"])
        # domain matches but keyword doesn't
        d = route_one(s["db"], s["account_id"],
                      make_email(sender_email="x@amazon.com", subject="Your order"))
        assert d["needs_ai_review"] is True

    def test_both_criteria_match(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="amazon.com", subject_keywords=["shipped"])
        d = route_one(s["db"], s["account_id"],
                      make_email(sender_email="x@amazon.com", subject="Your order shipped"))
        assert d["needs_ai_review"] is False


# ---------------------------------------------------------------------------
# Batch routing
# ---------------------------------------------------------------------------

class TestBatchRouting:
    def test_multiple_emails_routed_independently(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_domain="paypal.com")
        emails = [
            make_email("msg1", sender_email="x@paypal.com"),
            make_email("msg2", sender_email="x@unknown.com"),
        ]
        results = router_module.route_emails(s["db"], emails, s["account_id"])
        assert results[0]["folder_name"] == "Financial"
        assert results[1]["needs_ai_review"] is True
        assert results[0]["message_id"] == "msg1"
        assert results[1]["message_id"] == "msg2"


# ---------------------------------------------------------------------------
# History-based suggestion
# ---------------------------------------------------------------------------

class TestSuggestFromHistory:
    def test_returns_most_common_folder(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_email="alice@example.com")
        emails = [make_email(f"msg{i}") for i in range(3)]
        decisions = router_module.route_emails(s["db"], emails, s["account_id"])
        router_module.record_routing(s["db"], s["account_id"], decisions, emails)

        hint = router_module.suggest_from_history(
            s["db"], "alice@example.com", s["account_id"]
        )
        assert hint is not None
        assert hint["name"] == "Financial"

    def test_returns_none_for_unknown_sender(self, seeded):
        s = seeded
        assert router_module.suggest_from_history(
            s["db"], "stranger@nowhere.com", s["account_id"]
        ) is None


# ---------------------------------------------------------------------------
# Recording decisions
# ---------------------------------------------------------------------------

class TestRecordRouting:
    def test_records_decision(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_email="alice@example.com")
        e = [make_email()]
        decisions = router_module.route_emails(s["db"], e, s["account_id"])
        router_module.record_routing(s["db"], s["account_id"], decisions, e)

        hint = router_module.suggest_from_history(
            s["db"], "alice@example.com", s["account_id"]
        )
        assert hint["name"] == "Financial"

    def test_idempotent_same_message_id(self, seeded):
        s = seeded
        db_module.add_rule(s["db"], s["account_id"], s["financial_id"],
                           sender_email="alice@example.com")
        e = [make_email()]
        decisions = router_module.route_emails(s["db"], e, s["account_id"])
        router_module.record_routing(s["db"], s["account_id"], decisions, e)
        router_module.record_routing(s["db"], s["account_id"], decisions, e)

        conn = sqlite3.connect(s["db"])
        count = conn.execute(
            "SELECT COUNT(*) FROM mm_processed_emails"
        ).fetchone()[0]
        conn.close()
        assert count == 1
