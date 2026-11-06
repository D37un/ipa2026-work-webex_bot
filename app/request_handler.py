"""Part 1: ตรวจ Webex mention และไฟล์แนบ ก่อนตรวจเนื้อหา YAML"""

from app.core import process_request_file


def validate_webex_envelope(
    mentioned_people,
    attachment_path,
    bot_person_id,
):
    """
    Validate the target bot's actual mention and YAML attachment.
    Return an error response, or None when the envelope is valid.
    """
    # 1) bot_person_id ต้องเป็น string ไม่ว่าง และอยู่ใน mentioned_people (ต้องเป็น list)
    if (
        not isinstance(bot_person_id, str)
        or bot_person_id == ""
        or not isinstance(mentioned_people, list)
        or bot_person_id not in mentioned_people
    ):
        return {"status": "error", "result": "missing_bot_mention"}

    # 2) mention ถูกต้องแล้ว แต่ไม่มีไฟล์แนบ
    if attachment_path is None:
        return {"status": "error", "result": "no_yaml"}

    # 3) ผ่านทั้งสองข้อ
    return None


def handle_webex_request(
    mentioned_people,
    attachment_path,
    bot_person_id,
):
    """
    Validate the envelope, then validate the attached YAML request.
    Return a response dictionary. Do not dispatch to a router.
    """
    error = validate_webex_envelope(
        mentioned_people, attachment_path, bot_person_id
    )
    if error is not None:
        return error

    return process_request_file(attachment_path)
