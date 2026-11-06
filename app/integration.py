"""Part 4: ต่อ Part 1 (ตรวจ) เข้ากับ Part 3 (backend) ผ่าน dispatcher"""

from app.core import load_request_file, validate_request
from app.dispatcher import dispatch_request

from app.request_handler import validate_webex_envelope


def process_request(mentioned_people, attachment_path, bot_person_id):
    """
    ลำดับ: ตรวจ mention/ไฟล์แนบ -> โหลด YAML ครั้งเดียว -> ตรวจเนื้อหา -> เรียก backend
    ถ้าขั้นใดไม่ผ่านจะคืน error ทันทีโดยไม่เรียก backend
    """
    envelope_error = validate_webex_envelope(
        mentioned_people, attachment_path, bot_person_id
    )
    if envelope_error is not None:
        return envelope_error

    data, load_error = load_request_file(attachment_path)
    if load_error is not None:
        return load_error

    validation = validate_request(data)
    if validation.get("status") != "ok":
        return validation

    return dispatch_request(data)
