"""Code-owned data access and authority rules for the assessment."""

import re
import unicodedata


class RestrictedAccess(PermissionError):
    pass


class UnsafeContent(ValueError):
    pass


def normalized(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return " ".join("".join(char for char in value if unicodedata.category(char) != "Cf").split())


def check_content(text: str) -> None:
    value = normalized(text)
    if re.search(r"hr\s*0?1|salary|monthly_salary|راتب|رواتب", value):
        raise RestrictedAccess("Access denied under P03. Restricted salary data is excluded.")
    if re.search(r"ignore.{0,30}(?:polic|instruction)|switch.{0,30}ops reviewer|(?:become|act as).{0,30}ops reviewer|bypass.{0,20}approval|تجاهل.{0,30}(?:سياس|تعليمات)", value):
        raise UnsafeContent("Untrusted authority-changing instructions are blocked under P03.")
    for clause in re.split(r"[.!?;]", value):
        if ("fractional" in clause or "الملكية الجزئية" in clause) and re.search(r"publish|campaign|promote|نشر|حملة|ترويج", clause) and not re.search(r"paused|prohibited|must not|cannot|متوقف|محظور", clause):
            raise UnsafeContent("Fractional ownership publication and promotion are blocked under P01.")
    refund = re.search(r"\b(?:approve|issue|process)\s+(?:a |the |my )?refund", value)
    if refund and not re.search(r"(?:cannot|can't|do not|must not|never)\s*$", value[:refund.start()]):
        raise UnsafeContent("Refund operations are unavailable under P02.")
    if re.search(r"\b(?:ticket|task|refund|campaign)\s+(?:(?:has been|was|is)\s+)?(?:successfully\s+)?(?:created|sent|issued|published|approved)\b|\b(?:created|sent|issued|published|approved)\s+(?:a |the )?(?:ticket|task|refund|campaign)\b|تم\s+(?:إنشاء|انشاء|إرسال|ارسال|اعتماد|نشر)\s+(?:التذكرة|تذكرة|المهمة|مهمة|الحملة|حملة)", value):
        raise UnsafeContent("Unsupported action or execution claim is blocked under P01 to P03.")


def check_request_scope(role: str, text: str) -> None:
    check_content(text)
    scopes = {"L": "marketing", "S": "customer_service", "F": "product", "I": "tech"}
    for prefix in re.findall(r"\b([LSFI])\d+\b", unicodedata.normalize("NFKC", text).upper()):
        if role not in {scopes[prefix], "ops_reviewer"}:
            raise RestrictedAccess("Access denied for this trusted role under P03.")


def check_draft(text: str) -> None:
    check_content(text)
    value = normalized(text)
    if re.search(r"as per our records|our records (?:show|confirm)|we (?:have )?(?:verified|confirmed|checked) (?:your |the )?(?:payment|account)|expect (?:an? )?update (?:shortly|soon)|تؤكد سجلاتنا|تم التحقق من (?:الدفع|حسابك)", value):
        raise UnsafeContent("Invented account verification or update timing is unsupported by the supplied sources.")
    pattern = (
        r"\bwill\s+(?:be\s+)?(?:refund|resolve|resolved|fix|fixed|approve|approved|guarantee)\b"
        r"|\b(?:guarantee|promise)\b[^.!?;]{0,40}?\b(?:refund|resolution|returns?|approval|confirmation)\b"
        r"|\bwill\b[^.!?;]{0,20}?\b(?:receive|send|provide|see)\b[^.!?;]{0,20}?\bconfirmation\b"
        r"|\b(?:refund|resolution|returns?|approval|confirmation)\b[^.!?;]{0,20}?\bguaranteed\b"
        r"|(?:سنحل|سنعيد|سنرد|سنضمن|سوف نحل|سوف نعيد|نضمن).{0,30}(?:المشكلة|المبلغ|الأموال|الاموال|عائد|موافقة)"
    )
    for match in re.finditer(pattern, value):
        prefix = value[:match.start()]
        negative_list = not match.group().startswith("will") and re.search(r"(?:must not|cannot|can't|do not|never)\s+[^.!?;]*,\s*$", prefix)
        if negative_list or re.search(r"(?:cannot|can't|do not|must not|never|no|لا)\s*$", prefix) or re.match(r"will (?:not|never)\b", match.group()):
            continue
        raise UnsafeContent("Unsupported resolution, refund, or investment promise is blocked under P01 and P02.")
