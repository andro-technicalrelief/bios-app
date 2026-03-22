"""Schema constants and normalization helpers for BIOS Process Contract v1."""
from typing import List, Tuple, Optional

# Header definitions
HEADERS = [
    "Outcome",
    "Value Chain",
    "Core Process",
    "Sub Process",
    "Process Owner",
    "Step_UID",
    "Step_Type",
    "Activity",
    "Owner",
    "Responsibility",
    "System",
    "Metric",
    "KPI",
    "Report",
    "Ref",
    "Next_Step_UIDs",
]

# valid step types
STEP_TYPES = {"start", "task", "decision", "end", "event", "subprocess"}


def normalize_step_type(raw: str) -> str:
    if raw is None:
        return ""
    return str(raw).strip().lower()


def parse_next_steps(raw: str) -> List[Tuple[str, Optional[str]]]:
    """
    Parse Next_Step_UIDs into list of (to_uid, label).
    Supports:
        T2
        yes=T3
        yes=T3;no=T4
    """
    if raw is None:
        return []

    raw_str = str(raw).strip()

    if raw_str == "" or raw_str.lower() == "nan":
        return []

    out: List[Tuple[str, Optional[str]]] = []

    tokens = raw_str.split(";")
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue

        if "=" in tok:
            label, uid = tok.split("=", 1)
            out.append((uid.strip(), label.strip()))
        else:
            out.append((tok.strip(), None))

    return out


def canonical_responsibility(raw: str) -> str:
    if raw is None:
        return ""
    return str(raw).strip().lower()


def display_responsibility(raw: str) -> str:
    if raw is None:
        return ""

    raw = str(raw).strip()

    if ":" in raw:
        typ, name = raw.split(":", 1)
        return f"{typ.lower()}:{name.title()}"

    return raw.title()


def is_system_lane(resp: str) -> bool:
    if not resp:
        return False
    return resp.strip().lower().startswith("system:")


def is_human_lane(resp: str) -> bool:
    if not resp:
        return False
    return resp.strip().lower().startswith("human:")