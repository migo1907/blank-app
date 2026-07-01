"""Web Push sender (VAPID) for the PWA.

Reads VAPID keys from env (set in Railway — never committed):
  VAPID_PRIVATE_KEY   — base64url DER or PEM private key
  VAPID_PUBLIC_KEY    — base64url uncompressed P-256 public key (the one the browser uses)
  VAPID_CLAIMS_EMAIL  — optional, defaults to mailto:admin@snipersignals.app

Graceful no-op when pywebpush or keys are absent — never raises.
Subscriptions live in data/push_subscriptions.json (data branch via db helpers);
dead endpoints (404/410) are pruned automatically.
"""

import json
import os

SUBS_PATH = "data/push_subscriptions.json"


def _keys():
    return (
        os.environ.get("VAPID_PRIVATE_KEY", "").strip(),
        os.environ.get("VAPID_PUBLIC_KEY", "").strip(),
        os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:admin@snipersignals.app").strip(),
    )


def available() -> bool:
    """True when both VAPID keys are set AND pywebpush is importable."""
    priv, pub, _ = _keys()
    if not priv or not pub:
        return False
    try:
        import pywebpush  # noqa: F401
        return True
    except Exception:
        return False


def send_push(title: str, body: str, url: str = "/app/") -> int:
    """Send a push notification to every stored subscription.

    Returns the number of successful sends. Never raises — all errors are
    logged; 404/410 (expired/unsubscribed) endpoints are dropped and the
    pruned list is persisted.
    """
    priv, _pub, email = _keys()
    if not priv:
        print("[push] VAPID_PRIVATE_KEY not set — skipping push")
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except Exception as e:
        print(f"[push] pywebpush unavailable — skipping push: {e}")
        return 0

    try:
        from db import _get_file, _put_file
        subs, sha = _get_file(SUBS_PATH)
    except Exception as e:
        print(f"[push] Could not load subscriptions: {e}")
        return 0
    subs = subs or []
    if not subs:
        return 0

    payload = json.dumps({"title": title, "body": body, "url": url})
    sent, dead = 0, []
    for s in subs:
        try:
            webpush(
                subscription_info=s,
                data=payload,
                vapid_private_key=priv,
                vapid_claims={"sub": email},
            )
            sent += 1
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):
                dead.append(s.get("endpoint", ""))
                print(f"[push] Pruning dead subscription ({code}): {s.get('endpoint','')[:60]}")
            else:
                print(f"[push] Send failed ({code}): {e}")
        except Exception as e:
            print(f"[push] Send failed: {e}")

    if dead:
        try:
            pruned = [s for s in subs if s.get("endpoint", "") not in dead]
            _put_file(SUBS_PATH, pruned, sha, f"data: prune {len(dead)} dead push subscription(s)")
        except Exception as e:
            print(f"[push] Could not persist pruned subscriptions: {e}")

    print(f"[push] Sent {sent}/{len(subs)} — '{title}'")
    return sent
