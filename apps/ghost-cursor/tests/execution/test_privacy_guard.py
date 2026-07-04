import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from execution.privacy_guard import PrivacyGuard

@pytest.fixture
def guard():
    return PrivacyGuard()

def test_exact_match(guard):
    assert guard.check("https://chase.com") is True
    assert guard.check("http://chase.com/login") is True
    assert guard.check("chase.com") is True

def test_subdomain_match(guard):
    assert guard.check("https://secure.bankofamerica.com") is True
    assert guard.check("https://auth.accounts.google.com/login") is True

def test_allowed_domain(guard):
    assert guard.check("https://github.com") is False
    assert guard.check("https://google.com") is False
    assert guard.check("https://mybank.com") is False # not in deny list

def test_malformed_url_fallback(guard):
    assert guard.check("") is False
    assert guard.check("just-some-string") is False
