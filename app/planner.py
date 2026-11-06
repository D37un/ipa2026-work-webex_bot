"""Part 2: เทียบ desired state กับ current state แล้วสร้างแผน (plan)
ตาม specs/plan-spec-v1.md  ไฟล์นี้ไม่ติดต่อ router และไม่แก้ไขข้อมูลที่รับเข้ามา
"""

# ฟิลด์ที่ planner ดูแล (เรียงตามที่ spec ระบุ) ส่วน name เป็นแค่ตัวระบุ interface
MANAGED_FIELDS = ("ipv4", "description", "admin_state")


def _plan(operation, changes):
    """ห่อผลลัพธ์ให้อยู่ในรูปแบบ response ของ plan"""
    return {
        "status": "ok",
        "result": "planned",
        "operation": operation,
        "changes": changes,
    }


def build_plan(desired_interface, current_interface):
    """
    Compare desired interface state with normalized current state
    and return a plan according to specs/plan-spec-v1.md.
    """
    # create: ยังไม่มี interface บน router -> ส่งทุกฟิลด์ โดยมีเฉพาะ "to"
    if current_interface is None:
        changes = {
            field: {"to": desired_interface[field]}
            for field in MANAGED_FIELDS
        }
        return _plan("create", changes)

    # update / no_change: เก็บเฉพาะฟิลด์ที่ค่าต่างกัน พร้อม "from" และ "to"
    changes = {}
    for field in MANAGED_FIELDS:
        current_value = current_interface.get(field)
        desired_value = desired_interface[field]
        if current_value != desired_value:
            changes[field] = {"from": current_value, "to": desired_value}

    if changes:
        return _plan("update", changes)

    # ทุกฟิลด์ตรงกันแล้ว (idempotent) -> changes เป็น dict ว่าง
    return _plan("no_change", {})
