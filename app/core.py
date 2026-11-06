"""Part 1: ตรวจสอบ YAML request ตาม specs/desired-state-spec-v1.md"""

import yaml

# router ที่อนุญาตตาม spec (หัวข้อ "Allowed routers")
ALLOWED_ROUTERS = {
    "10.0.29.101",
    "10.0.29.102",
    "10.0.29.103",
    "10.0.29.104",
    "10.0.29.105",
}

# ตารางว่า method ไหนรองรับ action อะไร (หัวข้อ "Methods and actions")
METHOD_ACTIONS = {
    "restconf": {"status", "plan", "apply"},
    "netconf": {"status", "plan", "apply"},
    "ansible": {"apply"},
    "netmiko-textfsm": {"status", "delete"},
}

# action ที่ต้องมี interface ครบ 4 ช่อง (plan และ apply เท่านั้น)
FULL_STATE_ACTIONS = {"plan", "apply"}

ALLOWED_ADMIN_STATES = {"up", "down"}


def _error(code):
    """สร้าง response แบบ error ตาม response-spec"""
    return {"status": "error", "result": code}


def _is_missing(mapping, key):
    """key ไม่มีใน mapping, ค่าเป็น None (เช่นเขียน `router:` เฉยๆ) หรือเป็น string ว่าง"""
    value = mapping.get(key)
    return value is None or value == ""


def validate_request(data):
    """
    Validate one IPA2026 desired-state request.

    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    # ราก YAML ต้องเป็น mapping (dict) เท่านั้น
    if not isinstance(data, dict):
        return _error("invalid_yaml")

    # 1) version ต้องเป็น int 1 เท่านั้น
    #    ใช้ type(...) is int เพราะ True == 1 ใน Python (bool เป็น subclass ของ int)
    version = data.get("version")
    if type(version) is not int or version != 1:
        return _error("invalid_version")

    # 2) router
    if _is_missing(data, "router"):
        return _error("missing_router")
    router = data["router"]
    if not isinstance(router, str) or router not in ALLOWED_ROUTERS:
        return _error("invalid_router")

    # 3) method
    if _is_missing(data, "method"):
        return _error("missing_method")
    method = data["method"]
    if not isinstance(method, str) or method not in METHOD_ACTIONS:
        return _error("invalid_method")

    # 4) action ต้องเข้าคู่กับ method (ตรวจก่อนฟิลด์เฉพาะ action)
    if _is_missing(data, "action"):
        return _error("missing_action")
    action = data["action"]
    if not isinstance(action, str) or action not in METHOD_ACTIONS[method]:
        return _error("invalid_action")

    # 5) desired -> interface -> name
    desired = data.get("desired")
    if not isinstance(desired, dict):
        return _error("missing_desired")
    interface = desired.get("interface")
    if not isinstance(interface, dict):
        return _error("missing_interface")
    if _is_missing(interface, "name"):
        return _error("missing_interface_name")

    # 6) เฉพาะ plan และ apply ต้องมี ipv4, description, admin_state ครบ
    if action in FULL_STATE_ACTIONS:
        if _is_missing(interface, "ipv4"):
            return _error("missing_ipv4")
        if _is_missing(interface, "description"):
            return _error("missing_description")
        if _is_missing(interface, "admin_state"):
            return _error("missing_admin_state")
        admin_state = interface["admin_state"]
        if not isinstance(admin_state, str) or admin_state not in ALLOWED_ADMIN_STATES:
            return _error("invalid_admin_state")

    return {"status": "ok", "result": "accepted"}


def load_request_file(path):
    """
    อ่านและแปลง YAML จากไฟล์ คืนค่าเป็น tuple (data, error)
    - สำเร็จ: (data, None)
    - อ่านไม่ได้ / parse ไม่ได้ / ราก YAML ไม่ใช่ mapping: (None, invalid_yaml)
    แยกเป็นฟังก์ชันของตัวเองเพื่อให้ Part 4 โหลดไฟล์ครั้งเดียวแล้วนำไปใช้ต่อได้
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None, _error("invalid_yaml")

    if not isinstance(data, dict):
        return None, _error("invalid_yaml")

    return data, None


def process_request_file(path):
    """
    Read a YAML request file, validate it,
    and return a response dictionary.
    """
    data, error = load_request_file(path)
    if error is not None:
        return error
    return validate_request(data)
