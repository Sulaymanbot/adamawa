"""Print fresh production secrets to paste into your hosting dashboard.

Usage: python scripts/gen_secrets.py
Never commit these values. VOTE_ENCRYPTION_KEY must stay the same for the life of
the database, because changing it makes every stored ballot unreadable.
"""

import base64
import secrets

print(f"SECRET_KEY={secrets.token_hex(32)}")
print(f"VOTE_ENCRYPTION_KEY={base64.b64encode(secrets.token_bytes(32)).decode()}")
print(f"IDENTIFIER_PEPPER={secrets.token_hex(32)}")
