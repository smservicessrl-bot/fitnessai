"""
Workout generation (OpenAI -> strict JSON -> validate -> regenerate).

This package is intentionally focused on the "one-session workout plan" flow:
- prompt construction
- OpenAI Responses API call
- strict JSON parsing
- rule-based validation
- regeneration on validation failure
"""

