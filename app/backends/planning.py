"""Part 3: ตัวกลางสำหรับ plan_interface ของ RESTCONF และ NETCONF

ไม่มีตรรกะเปรียบเทียบของตัวเอง: อ่านสถานะจาก backend แล้วส่งให้ build_plan (Part 2)
"""

from app.planner import build_plan


def plan_interface(
    router,
    desired_interface,
    get_interface_state,
):
    """Build a Part 2 plan from backend status."""
    status = get_interface_state(router, desired_interface["name"])

    # backend error -> ส่งกลับตามเดิม ไม่แก้ไข
    if status.get("status") != "ok":
        return status

    # found -> ใช้ interface ที่อ่านได้, not_found -> None
    if status.get("result") == "found":
        current_interface = status.get("interface")
    else:
        current_interface = None

    return build_plan(desired_interface, current_interface)
