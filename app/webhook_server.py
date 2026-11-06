"""Part 4: webhook server ของ Webex bot (รับ event -> ประมวลผล -> ตอบกลับห้องเดิม)"""

import json

import logging

import os

from concurrent.futures import ThreadPoolExecutor

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from tempfile import TemporaryDirectory

from app.integration import process_request

from app.webex_client import WEBEX_API_BASE, WebexClient

logger = logging.getLogger("ipa2026.webhook")

MAX_BODY_BYTES = 1_000_000


class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def handle_event(self, event):
        """
        ประมวลผล 1 event คืน dict ที่ตอบกลับ หรือ None ถ้า event ถูกข้าม (ไม่ตอบ)
        """
        # 1) รับเฉพาะ messages/created ที่มี message id
        if not isinstance(event, dict):
            return None
        if event.get("resource") != "messages" or event.get("event") != "created":
            return None
        data = event.get("data")
        if not isinstance(data, dict):
            return None
        message_id = data.get("id")
        if not isinstance(message_id, str) or not message_id:
            return None

        # 2) ข้ามข้อความของบอทเองก่อนเรียก API (กันตอบวนลูป)
        if data.get("personId") == self.bot_person_id:
            return None

        # 3) ดึงข้อความจริง และเช็กผู้เขียนอีกชั้น
        message = self.client.get_message(message_id)
        if message.get("personId") == self.bot_person_id:
            return None

        room_id = message.get("roomId")
        if not room_id:
            return None

        # 4) จัดการไฟล์แนบ
        files = message.get("files") or []
        if len(files) > 1:
            result = {"status": "error", "result": "multiple_attachments"}
        else:
            result = self._process(message, files)

        # 5) ตอบกลับห้องที่ส่งคำขอมา (JSON เป็นข้อความ)
        self.client.send_message(room_id, json.dumps(result))
        return result

    def _process(self, message, files):
        mentioned_people = message.get("mentionedPeople")
        try:
            if not files:
                return self.processor(mentioned_people, None, self.bot_person_id)

            content = self.client.download_file(files[0])
            # TemporaryDirectory ลบโฟลเดอร์และไฟล์ให้เสมอ แม้ processor จะ error
            with TemporaryDirectory() as directory:
                path = Path(directory) / "request.yaml"
                path.write_bytes(content)
                return self.processor(mentioned_people, path, self.bot_person_id)
        except Exception:
            logger.exception("request processing failed")
            return {"status": "error", "result": "backend_failed"}


def make_http_handler(submit_event):
    """สร้างคลาส handler ของ HTTP server; submit_event(event) ถูกเรียกเมื่อรับ /webhook ได้"""

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status, body):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _path(self):
            return self.path.split("?", 1)[0]

        def do_GET(self):
            if self._path() == "/health":
                self._send_json(200, {"status": "ok", "result": "healthy"})
            else:
                self._send_json(404, {"status": "error", "result": "not_found"})

        def do_POST(self):
            if self._path() != "/webhook":
                self._send_json(404, {"status": "error", "result": "not_found"})
                return

            invalid = {"status": "error", "result": "invalid_event"}

            # ความยาว body ต้องเป็นตัวเลข 1..1,000,000
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = 0
            if length < 1 or length > MAX_BODY_BYTES:
                self.close_connection = True
                self._send_json(400, invalid)
                return

            try:
                event = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, invalid)
                return
            if not isinstance(event, dict):
                self._send_json(400, invalid)
                return

            # ส่งไปประมวลผลเบื้องหลัง แล้วตอบรับทันที (ไม่รอ router)
            submit_event(event)
            self._send_json(200, {"status": "ok", "result": "accepted"})

        def log_message(self, format, *args):
            logger.info("%s - %s", self.address_string(), format % args)

    return Handler


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", "8000"))

    client = WebexClient()
    bot_person_id = client.get_me()["id"]
    handler = WebexEventHandler(client, bot_person_id)

    # worker เดียว = ประมวลผลทีละคำขอ ไม่ให้แก้ router ซ้อนกัน
    executor = ThreadPoolExecutor(max_workers=1)

    def run(event):
        try:
            handler.handle_event(event)
        except Exception:
            logger.exception("event handling failed")

    def submit_event(event):
        executor.submit(run, event)

    server = ThreadingHTTPServer((host, port), make_http_handler(submit_event))
    logger.info("listening on %s:%s (bot %s)", host, port, bot_person_id)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        executor.shutdown(wait=False)


if __name__ == "__main__":
    main()
