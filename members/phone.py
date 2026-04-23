"""Normalize phone numbers for lookup (digits-only, basic HU-friendly rules)."""


def normalize_phone(raw: str) -> str:
    if not raw:
        return ""
    digits = "".join(c for c in raw if c.isdigit())
    if not digits:
        return ""
    # Common HU input: 06 30 ... -> 3630...
    if digits.startswith("06") and len(digits) >= 10:
        digits = "36" + digits[2:]
    # 9-digit national mobile without country code
    if len(digits) == 9 and not digits.startswith("36"):
        digits = "36" + digits
    return digits
