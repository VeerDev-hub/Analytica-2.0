"""Password strength rules, shared by registration and password changes.

The same rules are mirrored in the frontend (src/lib/password.js) so the strength meter
shows exactly what the server will accept.
"""

from __future__ import annotations

import re

from app.core.errors import ValidationFailed

MIN_LENGTH = 8
MAX_LENGTH = 128

# Most-used passwords (lower-cased, digits stripped before comparison too).
COMMON = {
    "password",
    "passw0rd",
    "p@ssword",
    "p@ssw0rd",
    "letmein",
    "welcome",
    "admin",
    "administrator",
    "qwerty",
    "qwertyuiop",
    "asdfgh",
    "asdfghjkl",
    "zxcvbn",
    "zxcvbnm",
    "iloveyou",
    "monkey",
    "dragon",
    "sunshine",
    "princess",
    "football",
    "baseball",
    "superman",
    "batman",
    "master",
    "shadow",
    "michael",
    "jennifer",
    "jordan",
    "hunter",
    "trustno1",
    "abc",
    "abcd",
    "abcdef",
    "abcdefg",
    "abcdefgh",
    "login",
    "secret",
    "freedom",
    "whatever",
    "starwars",
    "computer",
    "internet",
    "hello",
    "charlie",
    "donald",
    "access",
    "flower",
    "cheese",
    "summer",
    "winter",
    "spring",
    "autumn",
    "soccer",
    "hockey",
    "killer",
    "pepper",
    "ginger",
    "cookie",
    "mustang",
    "pokemon",
    "minecraft",
    "fortnite",
    "samsung",
    "google",
    "facebook",
    "twitter",
    "youtube",
    "analytica",
    "analytics",
    "studio",
    "welcome1",
    "changeme",
    "default",
    "temp",
    "test",
    "testing",
    "guest",
    "user",
    "root",
    "toor",
    "pass",
    "password1",
    "password12",
    "password123",
    "qwerty123",
    "abc123",
    "aa123456",
    "india",
    "pakistan",
    "london",
    "newyork",
    "chocolate",
}

_SEQUENCES = ("abcdefghijklmnopqrstuvwxyz", "qwertyuiopasdfghjklzxcvbnm", "0123456789")


def _is_sequential(s: str) -> bool:
    s = s.lower()
    if len(s) < 6:
        return False
    return any(s in seq or s in seq[::-1] for seq in _SEQUENCES)


def problems(password: str, *, email: str | None = None, name: str | None = None) -> list[str]:
    """Return human-readable reasons the password is not acceptable (empty = fine)."""
    out: list[str] = []
    pw = password or ""
    if len(pw) < MIN_LENGTH:
        return [f"Use at least {MIN_LENGTH} characters."]
    if len(pw) > MAX_LENGTH:
        return [f"Use at most {MAX_LENGTH} characters."]

    low = pw.lower()
    stripped = re.sub(r"[^a-z]", "", low)
    if low in COMMON or stripped in COMMON or re.sub(r"[\d\W_]+$", "", low) in COMMON:
        out.append("That password is too common.")
    if len(set(low)) <= 2 or _is_sequential(low):
        out.append("That password is too predictable (repeated or sequential characters).")

    personal: list[str] = []
    if email:
        local = email.split("@")[0].lower()
        personal += [p for p in re.split(r"[._\-+]", local) if len(p) >= 4]
        if len(local) >= 4:
            personal.append(local)
    if name:
        personal += [p for p in re.split(r"\s+", name.lower()) if len(p) >= 4]
    if any(p in low for p in personal):
        out.append("Don't use your name or email address in the password.")

    classes = sum(bool(re.search(p, pw)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    strong = len(pw) >= 16 or (len(pw) >= 12 and classes >= 2) or classes >= 3
    if not strong:
        out.append("Make it longer (12+ characters), or mix letters, numbers and symbols.")
    return out


def score(password: str, *, email: str | None = None, name: str | None = None) -> int:
    """0 (unusable) to 4 (strong), for display."""
    pw = password or ""
    if problems(pw, email=email, name=name):
        return 0 if len(pw) < MIN_LENGTH else 1
    classes = sum(bool(re.search(p, pw)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if len(pw) >= 16 and classes >= 3:
        return 4
    if len(pw) >= 12 and classes >= 3 or len(pw) >= 16:
        return 3
    return 2


def validate(password: str, *, email: str | None = None, name: str | None = None) -> None:
    issues = problems(password, email=email, name=name)
    if issues:
        raise ValidationFailed(
            "Choose a stronger password. " + " ".join(issues),
            code="WEAK_PASSWORD",
            details=[{"message": m} for m in issues],
        )
