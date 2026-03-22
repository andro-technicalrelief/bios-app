"""Builders for UI views based on the normalized contract."""
from typing import Any, Dict, List, Set
import pandas as pd


def build_process_architecture(engine) -> Dict[str, Any]:
    df = engine.get_dataframe()
    arch: Dict[str, Any] = {}
    # build hierarchy
    for _, row in df.iterrows():
        outc = row["Outcome"]
        vc = row["Value Chain"]
        cp = row["Core Process"]
        sp = row["Sub Process"]
        arch.setdefault(outc, {}).setdefault(vc, {}).setdefault(cp, {}).setdefault(sp, []).append(row["Step_UID"])
    # rollups
    rollups: Dict[str, Dict[str, Any]] = {"core": {}, "sub": {}}
    # compute counts
    for _, row in df.iterrows():
        cp = row["Core Process"]
        sp = row["Sub Process"]
        rollups["core"].setdefault(cp, {"steps": 0, "roles": set(), "systems": set(), "metrics": 0, "kpis": 0})
        rollups["sub"].setdefault(sp, {"steps": 0, "roles": set(), "systems": set(), "metrics": 0, "kpis": 0, "start": None, "end": None})
        rollups["core"][cp]["steps"] += 1
        rollups["core"][cp]["roles"].add(row["resp_display"])
        if row["System"]:
            rollups["core"][cp]["systems"].add(row["System"])
        if row["Metric"]:
            rollups["core"][cp]["metrics"] += 1
        if row["KPI"]:
            rollups["core"][cp]["kpis"] += 1
        rollups["sub"][sp]["steps"] += 1
        rollups["sub"][sp]["roles"].add(row["resp_display"])
        if row["System"]:
            rollups["sub"][sp]["systems"].add(row["System"])
        if row["Metric"]:
            rollups["sub"][sp]["metrics"] += 1
        if row["KPI"]:
            rollups["sub"][sp]["kpis"] += 1
        if row["Step_Type"] == "start":
            rollups["sub"][sp]["start"] = row["Step_UID"]
        if row["Step_Type"] == "end":
            rollups["sub"][sp]["end"] = row["Step_UID"]
    # convert sets to lists
    for cp in rollups["core"]:
        rollups["core"][cp]["roles"] = list(rollups["core"][cp]["roles"])
        rollups["core"][cp]["systems"] = list(rollups["core"][cp]["systems"])
    for sp in rollups["sub"]:
        rollups["sub"][sp]["roles"] = list(rollups["sub"][sp]["roles"])
        rollups["sub"][sp]["systems"] = list(rollups["sub"][sp]["systems"])
    return {"architecture": arch, "rollups": rollups}


def build_people_roles(engine) -> Dict[str, Any]:
    df = engine.get_dataframe()
    roles: Dict[str, Any] = {}
    for _, row in df.iterrows():
        can = row["resp_canon"]
        disp = row["resp_display"]
        roles.setdefault(can, {"display": disp, "steps": [], "decisions": [], "kpis": set()})
        roles[can]["steps"].append({
            "Step_UID": row["Step_UID"],
            "Step_Type": row["Step_Type"],
            "Activity": row["Activity"],
            "System": row["System"],
            "Metric": row["Metric"],
            "KPI": row["KPI"],
            "Report": row["Report"],
            "next": row["parsed_next"],
        })
        if row["Step_Type"] == "decision":
            roles[can]["decisions"].append({"Step_UID": row["Step_UID"], "branches": row["parsed_next"]})
        if row["KPI"]:
            roles[can]["kpis"].add(row["KPI"])
    # convert kpis to list
    for can in roles:
        roles[can]["kpis"] = list(roles[can]["kpis"])
    return roles


def build_system_catalogues(engine) -> Dict[str, Any]:
    df = engine.get_dataframe()
    systems: Dict[str, Any] = {}
    for _, row in df.iterrows():
        # include from System field
        sysnames = []
        if row["System"]:
            sysnames.append(row["System"])
        # include from responsibility if system
        resp = row["resp_display"]
        if resp.lower().startswith("system:"):
            sysnames.append(resp.split(":",1)[1])
        for sys in sysnames:
            systems.setdefault(sys, {"steps": [], "metrics": set(), "kpis": set(), "reports": set(), "roles": set()})
            systems[sys]["steps"].append({
                "Step_UID": row["Step_UID"],
                "Activity": row["Activity"],
            })
            if row["Metric"]:
                systems[sys]["metrics"].add(row["Metric"])
            if row["KPI"]:
                systems[sys]["kpis"].add(row["KPI"])
            if row["Report"]:
                systems[sys]["reports"].add(row["Report"])
            systems[sys]["roles"].add(resp)
    # convert sets
    for sys in systems:
        systems[sys]["metrics"] = list(systems[sys]["metrics"])
        systems[sys]["kpis"] = list(systems[sys]["kpis"])
        systems[sys]["reports"] = list(systems[sys]["reports"])
        systems[sys]["roles"] = list(systems[sys]["roles"])
    return systems


def build_metrics_catalogues(engine) -> Dict[str, Any]:
    df = engine.get_dataframe()
    metrics = []
    kpis = []
    reports = {}
    for _, row in df.iterrows():
        context = {
            "Activity": row["Activity"],
            "Sub Process": row["Sub Process"],
            "Core Process": row["Core Process"],
            "Value Chain": row["Value Chain"],
            "Outcome": row["Outcome"],
            "Owner": row["Owner"],
            "System": row["System"],
            "Step_UID": row["Step_UID"],
        }
        if row["Metric"]:
            metrics.append({"Metric": row["Metric"], **context})
        if row["KPI"]:
            kpis.append({"KPI": row["KPI"], "Metric": row["Metric"], **context})
        if row["Report"]:
            reports.setdefault(row["Report"], {"steps": [], "systems": set(), "owners": set()})
            reports[row["Report"]]["steps"].append(row["Step_UID"])
            if row["System"]:
                reports[row["Report"]]["systems"].add(row["System"])
            reports[row["Report"]]["owners"].add(row["Owner"])
    # convert sets in reports
    for r in reports.values():
        r["systems"] = list(r["systems"])
        r["owners"] = list(r["owners"])
    return {"metrics": metrics, "kpis": kpis, "reports": reports}
