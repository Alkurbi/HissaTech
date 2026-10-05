"""Allowlisted local retrieval. Raw leads never leave the aggregation boundary."""

import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .domain import DATA, ROLES
from .policies import RestrictedAccess, check_content


class SourceUnavailable(RuntimeError):
    pass


class Sources:
    def __init__(self, role: str, directory: Path = DATA):
        if role not in ROLES:
            raise RestrictedAccess("Unknown trusted role.")
        self.role, self.directory = role, directory

    def read(self, name: str) -> Any:
        allowed_roles = {
            "policies": ROLES,
            "support_messages": {"customer_service", "ops_reviewer"},
            "feedback": {"product", "ops_reviewer"},
            "incidents": {"tech", "ops_reviewer"},
            "lead_aggregate": {"marketing", "ops_reviewer"},
            "leads": {"ops_reviewer"},
            "spend": {"ops_reviewer"},
        }
        if name not in allowed_roles or self.role not in allowed_roles[name]:
            raise RestrictedAccess("Source access denied under P03.")
        if name == "lead_aggregate":
            return self._aggregate_leads()
        return self._load(name)

    def _load(self, name: str) -> Any:
        try:
            value = json.loads((self.directory / f"{name}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SourceUnavailable(f"The authorized source {name} is unavailable or invalid.") from error
        expected = dict if name in {"policies", "spend"} else list
        if not isinstance(value, expected):
            raise SourceUnavailable(f"The authorized source {name} has an invalid shape.")
        if name == "spend" and isinstance(value, dict) and any(not valid_amount(amount) for amount in value.values()):
            raise SourceUnavailable("Spend must be unknown or finite nonnegative SAR amounts.")
        if name in {"leads", "support_messages", "feedback", "incidents"}:
            seen = set()
            for item in value:
                identifier = "row_id" if name == "leads" else "id"
                prefix = {"leads": "L", "support_messages": "S", "feedback": "F", "incidents": "I"}[name]
                if not isinstance(item, dict) or not isinstance(item.get(identifier), str) or not re.fullmatch(prefix + r"\d+", item[identifier]) or item[identifier] in seen:
                    raise SourceUnavailable(f"The authorized source {name} contains invalid or repeated row IDs.")
                seen.add(item[identifier])
                if name == "leads":
                    if not isinstance(item.get("contact_id"), str) or not item["contact_id"].strip() or any(field not in item for field in ("source", "status", "budget_sar")) or not valid_amount(item["budget_sar"]):
                        raise SourceUnavailable("Lead identity, source, status, or budget fields are invalid.")
                    for field in ("source", "status"):
                        if item[field] is not None:
                            if not isinstance(item[field], str):
                                raise SourceUnavailable("Lead source and status must be text or unknown.")
                            check_content(item[field])
                elif name == "support_messages" and (not isinstance(item.get("text"), str) or not item["text"].strip() or item.get("language") not in ("en", "ar") or "customer_id" not in item or (item["customer_id"] is not None and (not isinstance(item["customer_id"], str) or not item["customer_id"].strip()))):
                    raise SourceUnavailable("Support message text, language, or identity fields are invalid.")
                elif name == "feedback" and (not isinstance(item.get("text"), str) or not item["text"].strip()):
                    raise SourceUnavailable("Feedback must contain nonempty text.")
                elif name == "incidents":
                    if any(not isinstance(item.get(field), str) or not item[field].strip() for field in ("timestamp", "service", "event", "request_id")):
                        raise SourceUnavailable("Incident fields must contain nonempty text.")
                    try:
                        timestamp = datetime.fromisoformat(item["timestamp"])
                        if timestamp.tzinfo is None:
                            raise ValueError("timezone missing")
                    except ValueError as error:
                        raise SourceUnavailable("Incident timestamps require valid ISO timestamps with timezones.") from error
        return value

    def _aggregate_leads(self) -> dict[str, Any]:
        leads, spend = self._load("leads"), self._load("spend")
        unique: dict[str, dict[str, Any]] = {}
        duplicates, conflicts = [], []
        for lead in leads:
            if lead["contact_id"] in unique:
                duplicates.append(lead["row_id"])
                kept = unique[lead["contact_id"]]
                fields = [field for field in ("source", "status", "budget_sar") if lead[field] != kept[field]]
                if fields:
                    conflicts.append({"kept_row_id": kept["row_id"], "duplicate_row_id": lead["row_id"], "fields": fields})
            else:
                unique[lead["contact_id"]] = lead
        groups: dict[str, list[dict[str, Any]]] = {}
        for lead in unique.values():
            groups.setdefault(lead["source"] or "Unknown", []).append(lead)
        by_source = {}
        for source in dict.fromkeys([*groups, *spend]):
            items = groups.get(source, [])
            count = len(items)
            qualified = sum(item["status"] == "Qualified" for item in items)
            by_source[source] = {"unique_leads": count, "qualified_leads": qualified,
                                 "status_counts": dict(Counter(item["status"] or "Unknown" for item in items)),
                                 "spend_sar": spend.get(source),
                                 "qualification_rate": qualified / count if count else None,
                                 "qualification_rate_denominator": "qualified leads / unique leads for this source, deduplicated by contact ID",
                                 "cost_denominator": "source spend / unique leads for this source, deduplicated by contact ID; not cost per investor",
                                 "cost_per_unique_lead_sar": spend[source] / count if count and spend.get(source) is not None else None}
        count = len(unique)
        qualified = sum(lead["status"] == "Qualified" for lead in unique.values())
        return {"unique_leads": count, "qualified_leads": qualified, "duplicates": duplicates,
                "duplicate_conflicts": conflicts,
                "duplicate_resolution": "Retain the first import per contact ID. Metrics are provisional when duplicate conflicts exist.",
                "status_counts": dict(Counter(lead["status"] or "Unknown" for lead in unique.values())),
                "missing_budget_count": sum(lead["budget_sar"] is None for lead in unique.values()),
                "missing_source_count": sum(not lead["source"] for lead in unique.values()),
                "by_source": by_source, "qualification_rate": qualified / count if count else None,
                "qualification_rate_denominator": "qualified leads / unique leads, deduplicated by contact ID",
                "source_ids": [lead["row_id"] for lead in leads]}


def valid_amount(value: Any) -> bool:
    try:
        return value is None or (type(value) in (int, float) and value >= 0 and math.isfinite(value))
    except OverflowError:
        return False
