"""Part 3: Ansible backend (apply เท่านั้น)

แปลง desired state เป็นตัวแปร แล้วรัน ansible/apply_interface.yml
ซึ่งใช้ cisco.ios.ios_config (defaults: true) ผ่าน network_cli
"""

import json
import os
import subprocess
from pathlib import Path

from app.backends.common import (
    applied_response,
    error_code_for,
    error_response,
    get_credentials,
    split_ipv4,
)

# โฟลเดอร์ ansible/ อยู่ระดับเดียวกับ app/ (ใน Docker คือ /opt/ipa2026/ansible)
ANSIBLE_DIR = Path(__file__).resolve().parents[2] / "ansible"
PLAYBOOK = ANSIBLE_DIR / "apply_interface.yml"
INVENTORY = ANSIBLE_DIR / "inventory.ini"

PLAYBOOK_TIMEOUT = 60

# ข้อความใน output ที่บอกว่ารหัสผ่าน/สิทธิ์ถูกปฏิเสธ
_AUTH_MARKERS = (
    "authentication failed",
    "invalid username or password",
    "permission denied",
    "incorrect username or password",
)


def _real_run_playbook(variables):
    """
    รัน ansible-playbook จริง
    ส่ง username/password ผ่าน environment (ไม่ใส่บน command line ที่คนอื่นเห็นได้)
    exit code: 0 สำเร็จ, 4 เชื่อมต่อ host ไม่ได้ (รวมกรณีรหัสผ่านผิด), อื่นๆ = task ล้มเหลว
    """
    username, password = get_credentials()

    env = dict(os.environ)
    env["ROUTER_USER"] = username
    env["ROUTER_PASS"] = password
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    env["ANSIBLE_NOCOLOR"] = "1"

    command = [
        "ansible-playbook",
        "-i", str(INVENTORY),
        str(PLAYBOOK),
        "--extra-vars", json.dumps(variables),
    ]

    try:
        completed = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            timeout=PLAYBOOK_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConnectionError("ansible-playbook timed out") from exc
    except FileNotFoundError as exc:  # ไม่ได้ติดตั้ง ansible (เช่นบน Windows)
        raise RuntimeError("ansible-playbook is not installed") from exc

    if completed.returncode == 0:
        return

    output = (completed.stdout + completed.stderr).lower()
    if any(marker in output for marker in _AUTH_MARKERS):
        raise PermissionError("router rejected the credentials")
    if completed.returncode == 4 or "unreachable" in output:
        raise ConnectionError("router is unreachable")
    raise RuntimeError(f"ansible-playbook failed (exit code {completed.returncode})")


def apply_interface(
    router,
    desired_interface,
    run_playbook=None,
):
    """Apply complete desired interface state using Ansible."""
    run_playbook = run_playbook or _real_run_playbook

    try:
        address, mask = split_ipv4(desired_interface["ipv4"])

        variables = {
            "router": router,
            "interface_name": desired_interface["name"],
            "description": desired_interface["description"],
            "ipv4_address": address,
            "netmask": mask,
            "shutdown": desired_interface["admin_state"] == "down",
        }

        run_playbook(variables)
        return applied_response()
    except Exception as exc:
        return error_response(error_code_for(exc))
