"""Part 3: RESTCONF backend (status / plan / apply)

อ่านสถานะด้วย ietf-interfaces + ietf-ip และเขียนด้วย Cisco-IOS-XE-native
ตาม specs/backend-spec-v1.md
"""

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

YANG_JSON = "application/yang-data+json"


def _quiet_tls_warnings():
    """ปิดคำเตือน InsecureRequestWarning เพราะเราตั้งใจใช้ verify=False กับ router ในแล็บ"""
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _make_session():
    """
    สร้าง requests.Session ที่ยอมคุยกับ router รุ่นเก่า
    router IOS XE บางรุ่นไม่รองรับ secure renegotiation ทำให้ OpenSSL 3 / Python 3.12+
    ปฏิเสธด้วยข้อผิดพลาด UNSAFE_LEGACY_RENEGOTIATION_DISABLED
    จึงเปิด OP_LEGACY_SERVER_CONNECT และลดระดับความปลอดภัยของ cipher ลงเฉพาะ session นี้
    """
    import ssl

    import requests
    from requests.adapters import HTTPAdapter

    class LegacyTLSAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            context.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
            try:
                context.set_ciphers("DEFAULT:@SECLEVEL=1")
            except ssl.SSLError:
                pass
            kwargs["ssl_context"] = context
            return super().init_poolmanager(*args, **kwargs)

    session = requests.Session()
    session.mount("https://", LegacyTLSAdapter())
    return session


def _real_http_get(url):
    """GET จริงด้วย requests (ใช้เมื่อไม่ได้ส่ง http_get เข้ามา)"""
    import requests

    _quiet_tls_warnings()
    username, password = get_credentials()
    try:
        return _make_session().get(
            url,
            auth=(username, password),
            headers={"Accept": YANG_JSON},
            verify=False,  # router ในแล็บใช้ self-signed certificate
            timeout=TRANSPORT_TIMEOUT,
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        # requests.ConnectionError ไม่ใช่ลูกของ ConnectionError ในตัว Python จึงแปลงเอง
        raise ConnectionError(str(exc)) from exc


def _real_http_put(url, json):
    """PUT จริงด้วย requests (ใช้เมื่อไม่ได้ส่ง http_put เข้ามา)"""
    import requests

    _quiet_tls_warnings()
    username, password = get_credentials()
    try:
        return _make_session().put(
            url,
            json=json,
            auth=(username, password),
            headers={"Accept": YANG_JSON, "Content-Type": YANG_JSON},
            verify=False,
            timeout=TRANSPORT_TIMEOUT,
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise ConnectionError(str(exc)) from exc


def _normalize(raw, interface_name):
    """แปลง JSON ของ ietf-interfaces เป็น {name, ipv4, description, admin_state}"""
    data = raw["ietf-interfaces:interface"]

    # ipv4: ip + netmask -> CIDR (ไม่มี address -> None)
    addresses = data.get("ietf-ip:ipv4", {}).get("address", [])
    if isinstance(addresses, dict):
        addresses = [addresses]
    ipv4 = None
    if addresses:
        ipv4 = to_cidr(addresses[0]["ip"], addresses[0]["netmask"])

    # enabled: true -> up, false -> down (ค่า default ของ IETF คือ true)
    admin_state = "up" if data.get("enabled", True) else "down"

    return {
        "name": data.get("name", interface_name),
        "ipv4": ipv4,
        "description": data.get("description"),
        "admin_state": admin_state,
    }


def get_interface_state(
    router,
    interface_name,
    http_get=None,
):
    """Return normalized interface status using RESTCONF."""
    http_get = http_get or _real_http_get
    url = (
        f"https://{router}/restconf/data/"
        f"ietf-interfaces:interfaces/interface={interface_name}"
    )

    try:
        response = http_get(url)
        code = response.status_code

        if code == 404:
            return not_found_response()
        if code in (401, 403):
            return error_response("authentication_failed")
        if code != 200:
            return error_response("backend_failed")

        return found_response(_normalize(response.json(), interface_name))
    except Exception as exc:  # แปลงทุกความล้มเหลวเป็น error code ตามสเปก
        return error_response(error_code_for(exc))


def plan_interface(
    router,
    desired_interface,
    http_get=None,
):
    """Return create/update/no_change plan using RESTCONF status."""
    return planning.plan_interface(
        router,
        desired_interface,
        lambda r, name: get_interface_state(r, name, http_get),
    )


def apply_interface(
    router,
    desired_interface,
    http_put=None,
):
    """Apply complete desired interface state using RESTCONF."""
    http_put = http_put or _real_http_put

    try:
        number = loopback_number(desired_interface["name"])
        address, mask = split_ipv4(desired_interface["ipv4"])

        loopback = {
            "name": number,
            "description": desired_interface["description"],
            "ip": {"address": {"primary": {"address": address, "mask": mask}}},
        }
        # admin_state down -> ต้องมี shutdown, up -> ไม่ใส่ shutdown
        if desired_interface["admin_state"] == "down":
            loopback["shutdown"] = [None]

        url = (
            f"https://{router}/restconf/data/"
            f"Cisco-IOS-XE-native:native/interface/Loopback={number}"
        )
        response = http_put(url, json={"Cisco-IOS-XE-native:Loopback": loopback})
        code = response.status_code

        if code in (200, 201, 204):
            return applied_response()
        if code in (401, 403):
            return error_response("authentication_failed")
        return error_response("backend_failed")
    except Exception as exc:
        return error_response(error_code_for(exc))
