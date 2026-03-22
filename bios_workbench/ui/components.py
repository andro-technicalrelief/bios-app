"""Streamlit UI components for BIOS Workbench tabs (v2.0 architecture + diagram toggle + intelligence)."""

import os
import json
import streamlit as st
import pandas as pd
from typing import Any, Dict

from bios_workbench.core import view_builders, drawio_export
from bios_workbench.core.architecture_diagram import export_value_chain_architecture_xml
from bios_workbench.core.intelligence import (
    classify_loops,
    compute_complexity,
    compute_system_dependency,
    compute_fragility
)


# -----------------------------
# Helpers
# -----------------------------

def _uid_map(engine) -> Dict[str, Dict[str, Any]]:
    df = engine.get_dataframe()
    df = df.copy()
    df["Step_UID"] = df["Step_UID"].astype(str)
    return df.set_index("Step_UID").to_dict(orient="index")


def _strip_prefix(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip()
    if s.lower().startswith("human:"):
        return s.split(":", 1)[1].strip()
    if s.lower().startswith("system:"):
        return s.split(":", 1)[1].strip()
    return s


def _render_drawio_editor_from_xml(xml: str, height: int = 720):
    asset_path = os.path.join(os.path.dirname(__file__), "assets", "drawio_embed.html")
    with open(asset_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("__XML__", json.dumps(xml)[1:-1])
    st.components.v1.html(html, height=height, scrolling=False)


# -----------------------------
# Tabs
# -----------------------------

def render_flow_studio(engine):
    st.header("Flow Studio")
    st.markdown(
        """Create or paste your process text and export a BIOS Process Contract.
Use the built-in page below or upload an existing CSV/XLSX."""
    )

    asset_path = os.path.join(os.path.dirname(__file__), "assets", "flow_studio.html")
    with open(asset_path, "r", encoding="utf-8") as f:
        html = f.read()
    st.components.v1.html(html, height=650, scrolling=True)

    st.divider()

    uploaded = st.file_uploader("Upload a BIOS Contract CSV/XLSX", type=["csv", "xlsx"])
    if uploaded is not None:
        try:
            engine.load(uploaded)
            st.success("Contract loaded and normalized")

            issues = engine.validate()
            if issues:
                for issue in [i for i in issues if i.get("severity") == "error"]:
                    st.error(issue.get("message", "Validation error"))
                for issue in [i for i in issues if i.get("severity") != "error"]:
                    st.warning(issue.get("message", "Validation warning"))

            st.session_state.engine = engine
        except Exception as e:
            st.error(f"Failed to load: {e}")

    if engine.df is not None:
        st.divider()
        st.subheader("Diagram Viewer")

        diagram_mode = st.radio(
            "Select Diagram Type",
            ["Operational Flow", "Value Chain Architecture"],
            horizontal=True
        )

        if diagram_mode == "Operational Flow":
            xml = drawio_export.export_drawio_xml(engine)
            _render_drawio_editor_from_xml(xml, height=760)
        else:
            arch_xml = export_value_chain_architecture_xml(engine)
            _render_drawio_editor_from_xml(arch_xml, height=760)


def render_architecture(engine):
    st.header("Process Architecture")

    if engine.df is None:
        st.warning("Please load a contract first.")
        return

    # Value Chain Diagram
    st.subheader("Value Chain Architecture Diagram")
    arch_xml = export_value_chain_architecture_xml(engine)
    _render_drawio_editor_from_xml(arch_xml, height=760)

    st.divider()

    # Validation
    issues = engine.validate()
    if issues:
        with st.expander("Validation Messages", expanded=False):
            for issue in [i for i in issues if i.get("severity") == "error"]:
                st.error(issue.get("message", "Validation error"))
            for issue in [i for i in issues if i.get("severity") != "error"]:
                st.warning(issue.get("message", "Validation warning"))

    # 🔵 LOOP INTELLIGENCE
    loops = classify_loops(engine)
    if loops:
        st.divider()
        st.subheader("Loop Analysis")

        uid_map = _uid_map(engine)

        for loop in loops:
            readable_nodes = []
            for uid in loop["nodes"]:
                row = uid_map.get(str(uid), {})
                readable_nodes.append(row.get("Activity", uid))

            node_string = " → ".join(readable_nodes)

            if loop["type"] == "controlled":
                st.info(f"Controlled Loop in '{loop['sub_process']}'")
                st.caption(node_string)
            else:
                st.error(f"Structural Cycle in '{loop['sub_process']}'")
                st.caption(node_string)

        st.divider()

    # 🔵 COMPLEXITY SCORING (v2)
    complexity = compute_complexity(engine)
    if complexity:
        st.subheader("Process Complexity")

        comp_rows = []
        for sp, data in complexity.items():
            comp_rows.append({
                "Sub Process": sp,
                "Steps": data["step_count"],
                "Decisions": data["decision_count"],
                "Roles": data["roles"],
                "Systems": data["systems"],
                "Loops": data["loop_count"],
                "Structural Loops": data["structural_loops"],
                "Complexity Score": data["score"]
            })

        comp_df = pd.DataFrame(comp_rows).sort_values("Complexity Score", ascending=False)
        st.dataframe(comp_df, use_container_width=True)

    # 🔵 SYSTEM DEPENDENCY (v2)
    system_dep = compute_system_dependency(engine)
    if system_dep:
        st.divider()
        st.subheader("System Dependency")

        sys_rows = []
        for sp, data in system_dep.items():
            sys_rows.append({
                "Sub Process": sp,
                "Total Steps": data["total_steps"],
                "System Steps": data["system_steps"],
                "System Utilization %": data["system_utilization_pct"],
                "Unique Systems": data["unique_systems"],
                "Dominant System": data["dominant_system"],
                "Dependency Score": data["score"],
            })

        sys_df = pd.DataFrame(sys_rows).sort_values("Dependency Score", ascending=False)
        st.dataframe(sys_df, use_container_width=True)

    st.divider()

    # Hierarchy
    views = view_builders.build_process_architecture(engine)
    arch = views["architecture"]
    rollups = views["rollups"]
    uid_map = _uid_map(engine)

    for outcome, vcs in arch.items():
        with st.expander(f"[Outcome] {outcome}", expanded=False):
            for vc, cps in vcs.items():
                with st.expander(f"[Value Chain] {vc}", expanded=False):
                    for cp, sps in cps.items():
                        with st.expander(f"[Core Process] {cp}", expanded=False):
                            for sp, step_uids in sps.items():
                                with st.expander(f"[Sub Process] {sp}", expanded=False):
                                    lines = []
                                    for uid in step_uids:
                                        row = uid_map.get(str(uid), {})
                                        act = row.get("Activity", str(uid))
                                        resp = _strip_prefix(row.get("resp_display", row.get("Responsibility", "")))
                                        sys_ = row.get("System", "")
                                        meta_bits = [b for b in [resp, sys_] if b]
                                        meta = f" — {' • '.join(meta_bits)}" if meta_bits else ""
                                        lines.append(f"- {act}{meta}")
                                    if lines:
                                        st.markdown("\n".join(lines))
                                    else:
                                        st.caption("No steps found.")

    with st.expander("Rollups", expanded=False):
        st.json(rollups)


def render_people_roles(engine):
    st.header("People & Roles")

    if engine.df is None:
        st.warning("Please load a contract first.")
        return

    roles = view_builders.build_people_roles(engine)
    uid_map = _uid_map(engine)

    # Role picker (hide human:)
    human_keys = [k for k in roles.keys() if not str(k).lower().startswith("system:")]
    options = {k: _strip_prefix(roles[k].get("display", k)) for k in human_keys}

    sel = st.selectbox("Select Role", human_keys, format_func=lambda k: options.get(k, k))
    if not sel:
        return

    info = roles[sel]

    # -----------------
    # Responsibilities
    # -----------------
    st.subheader("Responsibilities")

    resp_rows = []
    for step in info.get("steps", []):
        uid = str(step.get("Step_UID"))
        src = uid_map.get(uid, {})
        resp_rows.append({
            "Core Process": src.get("Core Process", ""),
            "Activity": step.get("Activity", ""),
            "System": step.get("System", ""),
            "Metric": step.get("Metric", ""),
            "KPI": step.get("KPI", ""),
            "Report": step.get("Report", ""),
        })

    st.dataframe(pd.DataFrame(resp_rows), use_container_width=True)

    # -----------------
    # Decisions
    # -----------------
    st.divider()
    st.subheader("Decisions")

    decision_rows = []
    for dec in info.get("decisions", []):
        dec_uid = str(dec.get("Step_UID"))
        dec_act = uid_map.get(dec_uid, {}).get("Activity", dec_uid)

        branches = []
        for to_uid, label in dec.get("branches", []):
            to_act = uid_map.get(str(to_uid), {}).get("Activity", to_uid)
            if label:
                branches.append(f"{label} → {to_act}")
            else:
                branches.append(to_act)

        decision_rows.append({
            "Decision": dec_act,
            "Branches": " | ".join(branches)
        })

    if decision_rows:
        st.dataframe(pd.DataFrame(decision_rows), use_container_width=True)
    else:
        st.caption("No decisions for this role.")

    # -----------------
    # Handovers
    # -----------------
    st.divider()
    st.subheader("Handovers")

    df = engine.get_dataframe().copy()
    df["Step_UID"] = df["Step_UID"].astype(str)

    handover_rows = []

    for step in info.get("steps", []):
        current_uid = str(step.get("Step_UID"))
        current_resp = _strip_prefix(step.get("Responsibility", ""))

        next_raw_series = df[df["Step_UID"] == current_uid]["Next_Step_UIDs"]
        if next_raw_series.empty:
            continue

        next_raw = next_raw_series.iloc[0]
        if not next_raw or str(next_raw).strip().lower() in {"", "nan"}:
            continue

        next_uids = [n.split("=")[-1].strip() for n in str(next_raw).split(";") if n.strip()]

        for next_uid in next_uids:
            next_row = uid_map.get(str(next_uid), {})
            next_resp = _strip_prefix(next_row.get("Responsibility", ""))

            if next_resp and current_resp and next_resp != current_resp:
                handover_rows.append({
                    "From": current_resp,
                    "To": next_resp,
                    "From Activity": step.get("Activity", ""),
                    "To Activity": next_row.get("Activity", "")
                })

    if handover_rows:
        st.dataframe(pd.DataFrame(handover_rows), use_container_width=True)
    else:
        st.caption("No cross-role handovers.")

    # -----------------
    # KPIs (simple)
    # -----------------
    st.divider()
    st.subheader("KPIs")

    kpi_rows = []
    for step in info.get("steps", []):
        if step.get("KPI"):
            uid = str(step.get("Step_UID"))
            src = uid_map.get(uid, {})
            kpi_rows.append({
                "Outcome": src.get("Outcome", ""),
                "Sub Process": src.get("Sub Process", ""),
                "KPI": step.get("KPI", ""),
                "Metric": step.get("Metric", ""),
                "System": step.get("System", ""),
            })

    if kpi_rows:
        st.dataframe(pd.DataFrame(kpi_rows), use_container_width=True)
    else:
        st.caption("No KPIs for this role.")


def render_system_catalogues(engine):
    st.header("System Catalogues")

    if engine.df is None:
        st.warning("Please load a contract first.")
        return

    systems = view_builders.build_system_catalogues(engine)
    uid_map = _uid_map(engine)

    sel = st.selectbox("Select system", list(systems.keys()))
    if not sel:
        return

    info = systems[sel]

    # Steps
    st.subheader("Steps")
    step_rows = []
    for s in info.get("steps", []):
        uid = str(s.get("Step_UID"))
        src = uid_map.get(uid, {})
        step_rows.append({
            "Core Process": src.get("Core Process", ""),
            "Activity": src.get("Activity", s.get("Activity", "")),
            "Process Owner": src.get("Process Owner", ""),
            "Responsibility": _strip_prefix(src.get("resp_display", src.get("Responsibility", ""))),
        })
    st.dataframe(pd.DataFrame(step_rows), use_container_width=True)

    # System Dependency view (for selected system)
    st.divider()
    st.subheader("System Dependency (where this system is dominant)")

    system_dep = compute_system_dependency(engine)
    dep_rows = []
    for sp, data in system_dep.items():
        if str(data.get("dominant_system", "")).strip().lower() == str(sel).strip().lower():
            dep_rows.append({
                "Sub Process": sp,
                "System Utilization %": data.get("system_utilization_pct", 0),
                "Unique Systems": data.get("unique_systems", 0),
                "Dependency Score": data.get("score", 0),
            })

    if dep_rows:
        dep_df = pd.DataFrame(dep_rows).sort_values("Dependency Score", ascending=False)
        st.dataframe(dep_df, use_container_width=True)
    else:
        st.caption("No subprocesses found where this system is the dominant system.")

    # Indicators + Roles
    with st.expander("Performance Indicators", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Metrics**")
            st.write(sorted(info.get("metrics", [])) or "—")
        with c2:
            st.markdown("**KPIs**")
            st.write(sorted(info.get("kpis", [])) or "—")
        with c3:
            st.markdown("**Reports**")
            st.write(sorted(info.get("reports", [])) or "—")

    with st.expander("Roles interacting with this system", expanded=False):
        roles_list = sorted({_strip_prefix(r) for r in info.get("roles", []) if r})
        st.write(roles_list or "—")


def render_metrics(engine):
    # Combined KPI + Metric Catalogue as requested:
    # Outcome, Sub-Process, KPI, Metric, System
    st.header("Performance Catalogue")

    if engine.df is None:
        st.warning("Please load a contract first.")
        return

    df = engine.get_dataframe().copy()

    # Only rows where KPI is present (KPI implies a metric context)
    view = df[df["KPI"].notna() & (df["KPI"] != "")][
        ["Outcome", "Sub Process", "KPI", "Metric", "System"]
    ].drop_duplicates()

    st.dataframe(view, use_container_width=True)


def render_executive_summary(engine):
    st.header("Executive Summary")

    if engine.df is None:
        st.warning("Please load a contract first.")
        return

    complexity = compute_complexity(engine)
    system_dep = compute_system_dependency(engine)
    fragility = compute_fragility(engine)
    loops = classify_loops(engine)

    st.subheader("Top Risk Sub Processes")

    frag_df = pd.DataFrame([
        {
            "Sub Process": sp,
            "Complexity": complexity.get(sp, {}).get("score", 0),
            "System Dependency": system_dep.get(sp, {}).get("score", 0),
            "Fragility Score": fragility.get(sp, 0)
        }
        for sp in fragility
    ]).sort_values("Fragility Score", ascending=False)

    st.dataframe(frag_df, use_container_width=True)

    st.subheader("Loop Health")

    total_loops = len(loops)
    structural = len([l for l in loops if l["type"] == "structural"])
    controlled = len([l for l in loops if l["type"] == "controlled"])

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Loops", total_loops)
    col2.metric("Controlled Loops", controlled)
    col3.metric("Structural Loops", structural)

    st.subheader("Executive Insight")

    if not frag_df.empty:
        top = frag_df.iloc[0]
        sp = top["Sub Process"]

        narrative = f"""
The subprocess **{sp}** currently exhibits the highest fragility score.

• Complexity Score: {top['Complexity']}
• System Dependency Score: {top['System Dependency']}
• Composite Fragility: {top['Fragility Score']}

Recommendation:
Review governance controls, system redundancy, and loop structures within this subprocess.
        """.strip()

        st.markdown(narrative)