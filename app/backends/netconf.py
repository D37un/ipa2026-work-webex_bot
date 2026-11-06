"""Part 3: NETCONF backend (status / plan / apply)

อ่านสถานะด้วย ietf-interfaces + ietf-ip (get-config + subtree filter)
เขียนด้วย Cisco-IOS-XE-native (edit-config, nc:operation="replace")
"""

import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from app.backends import planning
from app.backends.common import (
    TRANSPORT_TIMEOUT,
    applied_response,
    error_code_for,
    error_response,
    found_response,
    get_credentials,
    loopback_number,
    not_found_response,
    split_ipv4,
    to_cidr,
)

IF_NS = "urn:ietf:params:xml:ns:yang:ietf-interfaces"
IP_NS = "urn:ietf:params:xml:ns:yang:ietf-ip"


def _connect(router):
    """เปิด NETCONF session ผ่าน SSH port 830 ด้วย ncclient (แปลง exception เป็นแบบในตัว Python)"""
    from ncclient import manager
    from ncclient.transport.errors import AuthenticationError, TransportError

    username, password = get_credentials()
    try:
        return manager.connect(
            host=router,
            port=830,
            username=username,
            password=password,
            hostkey_verify=False,
            allow_agent=False,
            look_for_keys=False,
            timeout=TRANSPORT_TIMEOUT,
        )
    except AuthenticationError as exc:  # ต้องเช็กก่อน เพราะเป็นลูกของ TransportError
        raise PermissionError(str(exc)) from exc
    except (OSError, TransportError) as exc:
        # OSError = socket timeout/refused/unreachable, TransportError = SSH/session ล่ม
        raise ConnectionError(str(exc)) from exc
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def _real_get_config(router, filter_xml):
    """get-config จริง คืน XML เป็น string"""
    from ncclient.operations import RPCError

    with _connect(router) as session:
        try:
            reply = session.get_config(source="running", filter=("subtree", filter_xml))
        except RPCError as exc:
            raise RuntimeError(str(exc)) from exc
        return reply.data_xml


def _real_edit_config(router, config_xml):
    """edit-config จริง (target running)"""
    from ncclient.operations import RPCError

    with _connect(router) as session:
        try:
            session.edit_config(target="running", config=config_xml)
        except RPCError as exc:
            raise RuntimeError(str(exc)) from exc


def _text(element, path, namespaces):
    """ข้อความของ element ลูก (ตัดช่องว่าง) หรือ None ถ้าไม่มี"""
    child = element.find(path, namespaces)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _normalize(xml_text, interface_name):
    """แปลง XML ที่ router ตอบเป็น interface ที่ normalize แล้ว หรือ None ถ้าไม่พบ"""
    root = ET.fromstring(xml_text)
    ns = {"if": IF_NS, "ip": IP_NS}

    for interface in root.iter(f"{{{IF_NS}}}interface"):
        if _text(interface, "if:name", ns) != interface_name:
            continue

        # ipv4: ip + netmask (หรือ prefix-length) -> CIDR
        ipv4 = None
        address = interface.find("ip:ipv4/ip:address", ns)
        if address is not None:
            ip = _text(address, "ip:ip", ns)
            netmask = _text(address, "ip:netmask", ns)
            prefix = _text(address, "ip:prefix-length", ns)
            if ip and netmask:
                ipv4 = to_cidr(ip, netmask)
            elif ip and prefix:
                ipv4 = f"{ip}/{prefix}"

        # enabled: true -> up, false -> down (ไม่มี = true ตาม IETF)
        enabled = _text(interface, "if:enabled", ns)
        admin_state = "down" if enabled == "false" else "up"

        return {
            "name": interface_name,
            "ipv4": ipv4,
            "description": _text(interface, "if:description", ns),
            "admin_state": admin_state,
        }

    return None


def get_interface_state(
    router,
    interface_name,
    netconf_get_config=None,
):
    """Return normalized interface status using NETCONF."""
    netconf_get_config = netconf_get_config or _real_get_config

    filter_xml = (
        f'<interfaces xmlns="{IF_NS}">'
        f"<interface><name>{escape(interface_name)}</name></interface>"
        "</interfaces>"
    )

    try:
        xml_text = netconf_get_config(router, filter_xml)
        interface = _normalize(xml_text, interface_name)
        if interface is None:
            return not_found_response()
        return found_response(interface)
    except Exception as exc:  # ET.ParseError ฯลฯ -> backend_failed
        return error_response(error_code_for(exc))


def plan_interface(
    router,
    desired_interface,
    netconf_get_config=None,
):
    """Return create/update/no_change plan using NETCONF status."""
    return planning.plan_interface(
        router,
        desired_interface,
        lambda r, name: get_interface_state(r, name, netconf_get_config),
    )


def apply_interface(
    router,
    desired_interface,
    netconf_edit_config=None,
):
    """Apply complete desired interface state using NETCONF."""
    netconf_edit_config = netconf_edit_config or _real_edit_config

    try:
        number = loopback_number(desired_interface["name"])
        address, mask = split_ipv4(desired_interface["ipv4"])
        description = escape(desired_interface["description"])

        # admin_state down -> <shutdown/>, up -> ไม่ใส่
        shutdown = "<shutdown/>" if desired_interface["admin_state"] == "down" else ""

        config_xml = (
            '<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" '
            'xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">'
            '<native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">'
            "<interface>"
            '<Loopback nc:operation="replace">'
            f"<name>{number}</name>"
            f"<description>{description}</description>"
            "<ip><address><primary>"
            f"<address>{address}</address><mask>{mask}</mask>"
            "</primary></address></ip>"
            f"{shutdown}"
            "</Loopback>"
            "</interface>"
            "</native>"
            "</config>"
        )

        netconf_edit_config(router, config_xml)
        return applied_response()
    except Exception as exc:
        return error_response(error_code_for(exc))
