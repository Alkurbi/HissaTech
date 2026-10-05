"""Deterministic inference double for tests. Not available through application entry points."""

import json

from hissatech.domain import canonical


class TemplateModel:
    def generate(self, prompt: str) -> str:
        context = json.loads(prompt.split("INPUT_JSON\n", 1)[1])["context"]
        if prompt.startswith("CLASSIFY"):
            text = context["request"].lower()
            if text.lstrip().startswith("{"):
                try:
                    supplied = json.loads(text)
                except ValueError:
                    supplied = None
                if isinstance(supplied, dict) and "message" in supplied:
                    return canonical({"department": "customer_service", "clarification": None})
            terms = {
                "tech": ("incident", "triage", "intake", "i01", "i02", "i03", "i04", "عطل", "سجل"),
                "product": ("feedback", "backlog", "product", "f01", "f02", "ملاحظات", "منتج"),
                "customer_service": ("ticket", "customer", "payment", "s01", "s02", "s03", "s04", "دفع", "تذكرة"),
                "marketing": ("lead", "marketing", "investment", "عملاء", "تسويق"),
            }
            matches = [department for department, words in terms.items() if any(word in text for word in words)]
            if "tech" in matches and "marketing" in matches and "intake" in text:
                matches.remove("marketing")
            department = matches[0] if len(matches) == 1 else None
            return canonical({"department": department, "clarification": None if department else "Which department should handle this request?"})
        text = "شكرًا لتواصلك، سنراجع طلبك دون الوعد بموعد للحل." if context["language"] == "Arabic" else "Draft prepared from the supplied, role-scoped facts."
        return canonical({"text": text, "source_ids": context["allowed_source_ids"]})
