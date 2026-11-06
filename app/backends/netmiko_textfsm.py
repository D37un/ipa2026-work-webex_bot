"""Part 3: Netmiko + TextFSM backend (status / delete)

status: รัน 2 คำสั่งอ่านอย่างเดียวแล้วให้ TextFSM แปลงผลเป็น list ของ dict
    show ip interface <name>       -> interface, ip, prefix, สถานะ admin
    show interfaces description    -> description (IOS ย่อชื่อ เช่น Lo123)
delete: ส่ง `no interface <name>` ด้วย Netmiko แล้วตรวจซ้ำว่าหายไปแล้ว
"""

import re

from app.backends.common import (
    TRANSPORT_TIMEOUT,
    error_code_for,
    error_response,
    found_response,
    get_credentials,
    not_found_response,
)

# คำย่อชื่อ interface ที่ IOS ใช้ใน `show interfaces description`
_ABBREVIATIONS = {
    "lo": "Loopback",
    "loopback": "Loopback",
    "gi": "GigabitEthernet",
    "gigabitethernet": "GigabitEthernet",
    "fa": "FastEthernet",
    "fastethernet": "FastEthernet",
    "te": "TenGigabitEthernet",
    "tengigabitethernet": "TenGigabitEthernet",
    "tu": "Tunnel",
    "tunnel": "Tunnel",
    "vl": "Vlan",
    "vlan": "Vlan",
}


def expand_interface_name(name):
    """'Lo123' -> 'Loopback123' (ชื่อที่ไม่รู้จักคืนค่าเดิม)"""
    match = re.fullmatch(r"([A-Za-z]+)([\d/.:]+)", name.strip())
    if not match:
        return name.strip()
    prefix, rest = match.groups()
    return _ABBREVIATIONS.get(prefix.lower(), prefix) + rest


def _same_interface(left, right):
    """เทียบชื่อ interface แบบไม่สนตัวพิมพ์เล็ก/ใหญ่ และขยายคำย่อก่อน"""
    return expand_interface_name(left).lower() == expand_interface_name(right).lower()


def _parse_table(output):
    """
    ผลของ send_command(use_textfsm=True) เป็น list ถ้า TextFSM แปลงได้
    ถ้าเป็น string: IOS ตอบ error (เช่น interface ไม่มี) -> ถือว่าไม่มีข้อมูล,
    ข้อความอื่นที่ parse ไม่ได้ -> RuntimeError (backend_failed)
    """
    if isinstance(output, list):
        return output
    if "Invalid input" in output or "not found" in output.lower():
        return []
    raise RuntimeError("TextFSM could not parse the command output")


def _connect(router):
    """เปิด SSH session ด้วย Netmiko (แปลง exception ของ Netmiko เป็นแบบในตัว Python)"""
    from netmiko import ConnectHandler
    from netmiko.exceptions import (
        NetmikoAuthenticationException,
        NetmikoTimeoutException,
    )

    username, password = get_credentials()
    try:
        return ConnectHandler(
            device_type="cisco_ios",
            host=router,
            username=username,
            password=password,
            timeout=TRANSPORT_TIMEOUT,
            conn_timeout=TRANSPORT_TIMEOUT,
            auth_timeout=TRANSPORT_TIMEOUT,
        )
    except NetmikoAuthenticationException as exc:
        raise PermissionError(str(exc)) from exc
    except (NetmikoTimeoutException, OSError) as exc:
        raise ConnectionError(str(exc)) from exc
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def _send_parsed(connection, command):
    """
    ส่งคำสั่งแล้วให้ TextFSM แปลงผลเป็น list ของ dict
    อ่านผลดิบก่อน: ถ้า IOS ตอบ error (ขึ้นต้นด้วย % เช่น interface ไม่มี) ให้คืน list ว่าง
    เพราะ template ของ TextFSM จะ error ถ้าเจอบรรทัดแปลก ๆ อย่าง `^` ของ % Invalid input
    """
    from netmiko.utilities import get_structured_data_textfsm
    from textfsm import TextFSMError

    raw = connection.send_command(command)
    if "Invalid input" in raw or raw.lstrip().startswith("%"):
        return []

    try:
        parsed = get_structured_data_textfsm(
            raw, platform="cisco_ios", command=command
        )
    except TextFSMError as exc:
        raise RuntimeError(f"TextFSM could not parse: {exc}") from exc
    return _parse_table(parsed)


def _read(connection, interface_name):
    """อ่าน (ip_info, descriptions) ด้วย session ที่เปิดอยู่"""
    ip_info = _send_parsed(connection, f"show ip interface {interface_name}")
    descriptions = _send_parsed(connection, "show interfaces description")
    return ip_info, descriptions


def _real_netmiko_get(router, interface_name):
    """อ่านข้อมูลจริงจาก router คืน (ip_info, descriptions)"""
    with _connect(router) as connection:
        return _read(connection, interface_name)


def _real_netmiko_delete(router, interface_name):
    """
    ลบจริง: ถ้าไม่มี -> 'not_found'
    ถ้ามี -> ส่ง `no interface <name>` แล้วอ่านซ้ำ ถ้ายังอยู่ให้ RuntimeError
    """
    with _connect(router) as connection:
        ip_info, descriptions = _read(connection, interface_name)
        if _normalize(ip_info, descriptions, interface_name) is None:
            return "not_found"

        connection.send_config_set([f"no interface {interface_name}"])

        ip_info, descriptions = _read(connection, interface_name)
        if _normalize(ip_info, descriptions, interface_name) is not None:
            raise RuntimeError(f"{interface_name} is still present after delete")
        return "deleted"


def _normalize(ip_info, descriptions, interface_name):
    """รวมผลสองคำสั่งเป็น interface ที่ normalize แล้ว หรือ None ถ้าไม่พบ"""
    record = next(
        (r for r in ip_info if _same_interface(r.get("interface", ""), interface_name)),
        None,
    )
    if record is None:
        return None

    # ipv4: ที่อยู่แรกคู่กับ prefix แรก
    addresses = record.get("ip_address") or []
    prefixes = record.get("prefix_length") or []
    ipv4 = f"{addresses[0]}/{prefixes[0]}" if addresses and prefixes else None

    # administratively down -> down, อย่างอื่น -> up
    link_status = str(record.get("link_status", "")).lower()
    admin_state = "down" if "administratively down" in link_status else "up"

    # description จากอีกคำสั่ง (จับคู่หลังขยายชื่อย่อ Lo123 -> Loopback123)
    description = None
    for row in descriptions:
        if _same_interface(row.get("port", ""), interface_name):
            description = row.get("description") or None
            break

    return {
        "name": interface_name,
        "ipv4": ipv4,
        "description": description,
        "admin_state": admin_state,
    }


def get_interface_state(
    router,
    interface_name,
    netmiko_get=None,
):
    """Return normalized interface status using Netmiko + TextFSM."""
    netmiko_get = netmiko_get or _real_netmiko_get

    try:
        ip_info, descriptions = netmiko_get(router, interface_name)
        interface = _normalize(ip_info, descriptions, interface_name)
        if interface is None:
            return not_found_response()
        return found_response(interface)
    except Exception as exc:
        return error_response(error_code_for(exc))


def delete_interface(
    router,
    interface_name,
    netmiko_delete=None,
):
    """Delete an interface using Netmiko."""
    netmiko_delete = netmiko_delete or _real_netmiko_delete

    try:
        outcome = netmiko_delete(router, interface_name)
        if outcome == "deleted":
            return {"status": "ok", "result": "deleted"}
        if outcome == "not_found":
            return not_found_response()
        return error_response("backend_failed")
    except Exception as exc:
        return error_response(error_code_for(exc))
