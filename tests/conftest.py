import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import db as db_module  # noqa: E402


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    db_module.init_db(db_path)
    return db_path


@pytest.fixture()
def seeded(tmp_db):
    """Initialized DB with one account and three destination folders."""
    account_id = db_module.ensure_account(tmp_db, name="Test", provider="test")
    financial_id   = db_module.add_folder(tmp_db, account_id, "Financial",   "fin-001")
    newsletter_id  = db_module.add_folder(tmp_db, account_id, "Newsletters", "nl-001")
    review_id      = db_module.add_folder(tmp_db, account_id, "For Review",  "rv-001")
    return {
        "db":            tmp_db,
        "account_id":    account_id,
        "financial_id":  financial_id,
        "newsletter_id": newsletter_id,
        "review_id":     review_id,
    }
