"""Part 4: ตัวเรียก Webex REST API (ดึงข้อความ ดาวน์โหลดไฟล์ ส่งข้อความ)"""

import os

import requests

WEBEX_API_BASE = 'https://webexapis.com/v1'

REQUEST_TIMEOUT = 10


class WebexClient:
    def __init__(self, token=None, session=None):
        # ไม่ส่ง token มา -> อ่านจาก environment ถ้าไม่มีเลยถือว่าไม่มีสิทธิ์
        self.token = token or os.environ.get("WEBEX_BOT_TOKEN")
        if not self.token:
            raise PermissionError("WEBEX_BOT_TOKEN is not set")
        # session ส่งเข้ามาได้ (เทสใช้ตัวปลอม)
        self.session = session or requests.Session()

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get_me(self):
        """ข้อมูลของ bot เอง (ใช้หา personId ตอนเริ่มระบบ)"""
        response = self.session.get(
            f"{WEBEX_API_BASE}/people/me",
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def get_message(self, message_id):
        response = self.session.get(
            f"{WEBEX_API_BASE}/messages/{message_id}",
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def download_file(self, file_url):
        response = self.session.get(
            file_url,
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.content

    def send_message(self, room_id, text):
        response = self.session.post(
            f"{WEBEX_API_BASE}/messages",
            headers=self.headers,
            json={"roomId": room_id, "text": text},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
