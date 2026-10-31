"""Instagram Graph API publishing (Instagram professional account, single image post)."""
import os, json, time, urllib.request, urllib.error

HOST = os.environ.get("IG_HOST", "https://graph.instagram.com")
VER = os.environ.get("IG_API_VERSION", "v25.0")
FOOTER = "\n\n🤖 AI-generated influencer (fictional character)"

def _call(method, path, token, body=None):
    req = urllib.request.Request(f"{HOST}/{VER}/{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Instagram API error {e.code}: {e.read().decode()[:300]}")
    except OSError as e:
        raise RuntimeError(f"Cannot reach Instagram API: {e}")

def publish_image(ig_user_id, token, image_url, caption):
    """image_url must be publicly reachable: Meta downloads it. Two steps: create container, publish it."""
    cid = _call("POST", f"{ig_user_id}/media", token,
                {"image_url": image_url, "caption": (caption + FOOTER)[:2200]})["id"]
    for _ in range(10):
        status = _call("GET", f"{cid}?fields=status_code", token).get("status_code")
        if status in (None, "FINISHED"):
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram rejected the media (status {status})")
        time.sleep(2)
    return _call("POST", f"{ig_user_id}/media_publish", token, {"creation_id": cid})
