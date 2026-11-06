"""ลงทะเบียน (หรืออัปเดต) Webex webhook ให้ชี้ไปที่ URL ภายนอกของบอท

ใช้:  python scripts/register_webhook.py https://xxxx.trycloudflare.com
ต้องตั้ง WEBEX_BOT_TOKEN ใน environment ก่อน (ห้ามเขียน token ลงไฟล์นี้)

webhook ชุดเดียวแบบไม่ใส่ roomId filter: บอทจะได้รับข้อความที่ mention บอทจาก
ทุกห้องที่บอทอยู่ (ทั้ง IPA2026 และ IPA2026 Exam Room) และตอบกลับห้องที่ส่งมา
"""

import os
import sys

import requests

API = "https://webexapis.com/v1"
WEBHOOK_NAME = "ipa2026-bot"
TIMEOUT = 10


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/register_webhook.py https://<external-url>")

    token = os.environ.get("WEBEX_BOT_TOKEN")
    if not token:
        sys.exit("WEBEX_BOT_TOKEN is not set")

    target = sys.argv[1].rstrip("/")
    if not target.startswith("https://"):
        sys.exit("the URL must start with https://")
    if not target.endswith("/webhook"):
        target += "/webhook"

    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(f"{API}/webhooks", headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    mine = [h for h in response.json().get("items", []) if h.get("name") == WEBHOOK_NAME]

    body = {
        "name": WEBHOOK_NAME,
        "targetUrl": target,
        "resource": "messages",
        "event": "created",
    }

    if mine:
        # มีอยู่แล้ว -> อัปเดต URL ตัวแรก และลบตัวที่เหลือ (กันซ้ำ)
        first, extra = mine[0], mine[1:]
        response = requests.put(
            f"{API}/webhooks/{first['id']}", headers=headers, json=body, timeout=TIMEOUT
        )
        response.raise_for_status()
        for hook in extra:
            requests.delete(
                f"{API}/webhooks/{hook['id']}", headers=headers, timeout=TIMEOUT
            ).raise_for_status()
        print("updated webhook ->", target)
    else:
        response = requests.post(
            f"{API}/webhooks", headers=headers, json=body, timeout=TIMEOUT
        )
        response.raise_for_status()
        print("created webhook ->", target)

    print("status:", response.json().get("status"))


if __name__ == "__main__":
    main()
