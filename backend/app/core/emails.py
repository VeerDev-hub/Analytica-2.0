"""Email address rules for sign-up.

Three layers decide whether an address may create an account:

1. Blocklist: ~108k known disposable/temporary-mail domains (app/core/data/
   disposable_domains.txt, refreshed with scripts/update_disposable_domains.py) plus any
   extra domains an admin adds in Admin → Settings. Subdomains of a listed domain match too.
2. DNS: the domain must exist and accept mail (have MX records). Then each MX host is checked
   against the blocklist. Temp-mail services register new domains constantly (mail.tm hands
   out a fresh one every few days), but they all point at the service's own mail servers,
   e.g. fldubai.com → in.mail.tm. That catches domains no list has seen yet.
3. Allowlist: major mailbox providers are never blocked, whatever a list says.

Aliases of one mailbox (plus-tags, Gmail dots) count as the same address so one person
can't register many accounts from one inbox; see `canonical()`.

DNS failures (timeouts, resolver down) fail open: sign-up is allowed and a warning is
logged, so an outage never locks real users out. A domain that doesn't exist (NXDOMAIN)
or has no mail servers is rejected.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from functools import lru_cache
from pathlib import Path

from app.core.errors import ValidationFailed

logger = logging.getLogger("app.emails")

_LIST_FILE = Path(__file__).with_name("data") / "disposable_domains.txt"

# Never blocked, even if a third-party list gets one wrong.
ALLOWED_PROVIDERS = frozenset(
    {
        "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
        "yahoo.com", "ymail.com", "rocketmail.com", "icloud.com", "me.com", "mac.com",
        "aol.com", "proton.me", "protonmail.com", "pm.me", "zoho.com", "zohomail.com",
        "gmx.com", "gmx.net", "gmx.de", "web.de", "mail.com", "yandex.com", "yandex.ru",
        "fastmail.com", "tutanota.com", "tuta.io", "hey.com", "rediffmail.com", "qq.com",
        "163.com", "126.com", "naver.com", "daum.net", "orange.fr", "free.fr", "libero.it",
        "t-online.de", "btinternet.com", "comcast.net", "verizon.net", "att.net",
    }
)  # fmt: skip

# Mail hosts of large providers. A domain whose MX points here is a real provider or a
# custom domain on Google Workspace / Microsoft 365 / etc., so the MX layer skips them
# (some temp services forward through these too, but blocking them would block real users).
_SHARED_MX_SUFFIXES = (
    "google.com", "googlemail.com", "outlook.com", "protection.outlook.com", "yahoodns.net",
    "icloud.com", "protonmail.ch", "zoho.com", "zoho.eu", "zoho.in", "messagingengine.com",
    "mx.cloudflare.net", "mimecast.com", "pphosted.com", "mailgun.org", "sendgrid.net",
    "amazonaws.com", "yandex.net", "mail.ru", "gmx.net", "web.de", "ionos.com",
    "secureserver.net", "hostinger.com", "titan.email", "migadu.com", "fastmail.com",
)  # fmt: skip

_GMAIL = {"gmail.com", "googlemail.com"}


# ---------------------------------------------------------------- blocklist
@lru_cache(maxsize=1)
def _builtin_domains() -> frozenset[str]:
    try:
        lines = _LIST_FILE.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:  # pragma: no cover - file ships with the app
        logger.error("disposable domain list missing: %s", _LIST_FILE)
        return frozenset()
    return frozenset(
        ln.strip().lower() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")
    )


def _parse_extra(extra_blocked: str) -> set[str]:
    return {
        d.strip().lower().lstrip("@")
        for d in re.split(r"[\s,;]+", extra_blocked or "")
        if d.strip()
    }


def _suffixes(host: str) -> list[str]:
    """mx1.in.mail.tm → [mx1.in.mail.tm, in.mail.tm, mail.tm] (stops before the TLD)."""
    parts = host.strip(".").lower().split(".")
    return [".".join(parts[i:]) for i in range(len(parts) - 1)]


def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower()


def _listed(host: str, extra: set[str]) -> str | None:
    blocked = _builtin_domains()
    for s in _suffixes(host):
        if s in ALLOWED_PROVIDERS:
            return None
        if s in blocked or s in extra:
            return s
    return None


def is_disposable(email: str, extra_blocked: str = "") -> bool:
    """Blocklist only (no network)."""
    return _listed(domain_of(email), _parse_extra(extra_blocked)) is not None


# ---------------------------------------------------------------- DNS
_DNS_TTL_S = 3600
_dns_cache: dict[str, tuple[float, str, tuple[str, ...]]] = {}
_dns_lock = threading.Lock()


def _resolve_mx(domain: str) -> tuple[str, tuple[str, ...]]:
    """Return (status, mx_hosts). status: ok | nxdomain | nomail | error."""
    now = time.monotonic()
    with _dns_lock:
        hit = _dns_cache.get(domain)
        if hit and hit[0] > now:
            return hit[1], hit[2]
    import dns.exception
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.lifetime = 3.0
    try:
        answer = resolver.resolve(domain, "MX")
        hosts = tuple(
            str(r.exchange).rstrip(".").lower() for r in sorted(answer, key=lambda r: r.preference)
        )
        # RFC 7505 "null MX" (a single "." exchange) means the domain accepts no mail.
        status = "nomail" if not any(hosts) else "ok"
    except dns.resolver.NXDOMAIN:
        status, hosts = "nxdomain", ()
    except dns.resolver.NoAnswer:
        status, hosts = "nomail", ()
    except (dns.resolver.NoNameservers, dns.exception.Timeout):
        status, hosts = "error", ()
    except Exception as exc:  # noqa: BLE001 - never let DNS trouble break sign-up
        logger.warning("MX lookup for %s failed: %s", domain, exc)
        status, hosts = "error", ()
    if status != "error":
        with _dns_lock:
            if len(_dns_cache) > 5000:
                _dns_cache.clear()
            _dns_cache[domain] = (now + _DNS_TTL_S, status, hosts)
    return status, hosts


def _shared_mx(host: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in _SHARED_MX_SUFFIXES)


# ---------------------------------------------------------------- public API
def canonical(email: str) -> str:
    """One mailbox → one string: lower-case, plus-tag removed, Gmail dots removed."""
    local, _, dom = email.strip().lower().rpartition("@")
    local = local.split("+", 1)[0]
    if dom in _GMAIL:
        local = local.replace(".", "")
        dom = "gmail.com"
    return f"{local}@{dom}"


_DISPOSABLE_MSG = (
    "Temporary or disposable email addresses can't be used. Please sign up with your regular email."
)


def check_allowed(email: str, extra_blocked: str = "", *, check_dns: bool = True) -> None:
    """Raise ValidationFailed if this address may not create an account."""
    dom = domain_of(email)
    extra = _parse_extra(extra_blocked)

    if _listed(dom, extra):
        raise ValidationFailed(_DISPOSABLE_MSG, code="DISPOSABLE_EMAIL")
    if not check_dns or dom in ALLOWED_PROVIDERS:
        return

    status, hosts = _resolve_mx(dom)
    if status == "nxdomain":
        raise ValidationFailed(
            f"The domain “{dom}” doesn't exist. Check the email address for typos.",
            code="EMAIL_DOMAIN_INVALID",
        )
    if status == "nomail":
        raise ValidationFailed(
            f"“{dom}” can't receive email. Please use an address you can receive mail at.",
            code="EMAIL_DOMAIN_INVALID",
        )
    if status == "error":
        logger.warning("MX lookup for %s failed; allowing sign-up", dom)
        return
    for host in hosts:
        if _shared_mx(host):
            continue
        hit = _listed(host, extra)
        if hit:
            logger.info("blocked %s: mail handled by %s (%s)", dom, host, hit)
            raise ValidationFailed(_DISPOSABLE_MSG, code="DISPOSABLE_EMAIL")
