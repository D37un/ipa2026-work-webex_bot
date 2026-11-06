"""Part 4: เลือก backend ตาม method/action ของคำขอที่ผ่านการตรวจแล้ว"""

from app.backends import ansible, netconf, netmiko_textfsm, restconf


def dispatch_request(data):
    """
    รับคำขอที่ validate แล้ว (Part 1) แล้วเรียกฟังก์ชันของ backend ที่ตรงกัน
    - status / delete  -> ส่ง (router, ชื่อ interface)
    - plan / apply     -> ส่ง (router, dict ของ interface ที่ต้องการ)
    คืนผลของ backend ตามเดิม ไม่แก้ไขรูปแบบ
    """
    method = data["method"]
    action = data["action"]
    router = data["router"]
    interface = data["desired"]["interface"]
    name = interface["name"]

    # ใช้ lambda เพื่อให้ค้นหาฟังก์ชันจากโมดูล "ตอนเรียก" (เทสใช้ monkeypatch แทนฟังก์ชันได้)
    routes = {
        ("restconf", "status"): lambda: restconf.get_interface_state(router, name),
        ("restconf", "plan"): lambda: restconf.plan_interface(router, interface),
        ("restconf", "apply"): lambda: restconf.apply_interface(router, interface),
        ("netconf", "status"): lambda: netconf.get_interface_state(router, name),
        ("netconf", "plan"): lambda: netconf.plan_interface(router, interface),
        ("netconf", "apply"): lambda: netconf.apply_interface(router, interface),
        ("ansible", "apply"): lambda: ansible.apply_interface(router, interface),
        ("netmiko-textfsm", "status"): lambda: netmiko_textfsm.get_interface_state(
            router, name
        ),
        ("netmiko-textfsm", "delete"): lambda: netmiko_textfsm.delete_interface(
            router, name
        ),
    }

    route = routes.get((method, action))
    if route is None:
        # ไม่ควรเกิดถ้า validate_request ผ่านแล้ว แต่กันไว้เพื่อไม่ให้ระบบล้ม
        return {"status": "error", "result": "invalid_action"}
    return route()
