"""ฟังก์ชันที่ใช้ร่วมกันทุก backend ของ Part 3

- สร้าง response แบบ ok / error ตาม specs/backend-spec-v1.md
- แปลง exception เป็น error code (authentication_failed / connection_failed / backend_failed)
- อ่าน username/password ของ router จาก environment
- แปลงข้อมูล interface (netmask, ชื่อ Loopback) ที่หลาย backend ใช้ซ้ำ
"""

import os
from ipaddress import IPv4Interface, IPv4Network

# เวลารอสูงสุดต่อการเชื่อมต่อ router (วินาที) ใน Live test ระบบรอคำตอบแค่ 20 วินาที
TRANSPORT_TIMEOUT = 10


def error_response(code):
    """response แบบ error: {"status": "error", "result": code}"""
    return {"status": "error", "result": code}


def not_found_response():
    """interface ไม่มีบน router (ไม่ใช่ error)"""
    return {"status": "ok", "result": "not_found", "interface": None}


def found_response(interface):
    """interface พบบน router พร้อมค่า normalized"""
    return {"status": "ok", "result": "found", "interface": interface}


def applied_response():
    return {"status": "ok", "result": "applied"}


def error_code_for(exc):
    """
    แปลง exception เป็น error code ตามกติกาในสเปก
    - PermissionError                       -> authentication_failed
    - ConnectionError / TimeoutError        -> connection_failed
    - อย่างอื่น (RuntimeError, ValueError ...) -> backend_failed
    หมายเหตุ: PermissionError ไม่ใช่ลูกของ ConnectionError จึงเช็กแยกกันได้
    """
    if isinstance(exc, PermissionError):
        return "authentication_failed"
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return "connection_failed"
    return "backend_failed"


def get_credentials():
    """
    อ่านชื่อผู้ใช้/รหัสผ่านของ router จาก environment (ห้ามเขียนลงโค้ดหรือ repo)
    ถ้าไม่ได้ตั้งค่า ถือว่าพิสูจน์ตัวตนไม่ได้ -> PermissionError
    """
    username = os.environ.get("ROUTER_USER")
    password = os.environ.get("ROUTER_PASS")
    if not username or not password:
        raise PermissionError("ROUTER_USER / ROUTER_PASS is not set")
    return username, password


def split_ipv4(cidr):
    """
    '172.23.123.1/32' -> ('172.23.123.1', '255.255.255.255')
    ใช้กับการ apply ที่ต้องส่ง address กับ netmask แยกกัน
    """
    interface = IPv4Interface(cidr)
    return str(interface.ip), str(interface.network.netmask)


def to_cidr(ip, netmask):
    """
    '172.23.123.1' + '255.255.255.255' -> '172.23.123.1/32'
    netmask ที่ไม่ใช่รูปแบบ mask ที่ถูกต้องจะเกิด ValueError
    """
    prefix = IPv4Network(f"0.0.0.0/{netmask}").prefixlen
    return f"{ip}/{prefix}"


def loopback_number(interface_name):
    """
    'Loopback123' -> 123  (ใช้เป็น key ของ Cisco-IOS-XE-native)
    ชื่ออื่นที่ไม่ใช่ Loopback<ตัวเลข> เกิด ValueError
    """
    prefix = "Loopback"
    if not interface_name.startswith(prefix):
        raise ValueError(f"not a Loopback interface: {interface_name}")
    return int(interface_name[len(prefix):])
