import urllib.parse
from typing import FrozenSet

class PrivacyGuard:
    """
    Enforces domain restrictions to prevent Ghost Cursor from executing
    on sensitive websites (e.g., banking, health, authentication).
    """

    DENY_LIST: FrozenSet[str] = frozenset({
        "chase.com", "bankofamerica.com", "wellsfargo.com",
        "citi.com", "capitalone.com",
        "accounts.google.com", "appleid.apple.com",
        "login.microsoft.com", "login.live.com",
        "irs.gov", "ssa.gov",
    })

    def check(self, url: str) -> bool:
        """
        Returns True if the URL is blocked by the deny list.
        """
        if not url:
            return False

        try:
            parsed = urllib.parse.urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                # Fallback: some URLs might not have a scheme (e.g. "chase.com/login")
                # Try parsing with a dummy scheme if parsing failed to yield a hostname
                parsed = urllib.parse.urlparse(f"http://{url}")
                hostname = parsed.hostname
                
            if not hostname:
                return False
                
            return self.is_domain_blocked(hostname)
        except Exception:
            return False

    def is_domain_blocked(self, hostname: str) -> bool:
        """
        Internal check against the deny list. Performs suffix matching.
        """
        hostname = hostname.lower()
        
        # Exact match
        if hostname in self.DENY_LIST:
            return True
            
        # Suffix match (e.g., secure.chase.com)
        for denied_domain in self.DENY_LIST:
            if hostname.endswith("." + denied_domain):
                return True
                
        return False
