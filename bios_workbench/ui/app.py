"""Flask entry point for BIOS Workbench (replaces Streamlit)."""
import os
import json
import traceback

from flask import Flask, request, jsonify, render_template, send_from_directory
import pandas as pd

from bios_workbench.core.engine import BIOSProcessEngine
from bios_workbench.core import view_builders, drawio_export
from bios_workbench.core.architecture_diagram import export_value_chain_architecture_xml
from bios_workbench.core.intelligence import (
    classify_loops,
    compute_complexity,
    compute_system_dependency,
    compute_fragility,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

template_dir = os.path.join(os.path.dirname(__file__), "templates")
asset_dir = os.path.join(os.path.dirname(__file__), "assets")

app = Flask(
    __name__,
    template_folder=template_dir,
    static_folder=asset_dir,
    static_url_path="/static",
)
app.secret_key = "bios-workbench-secret-key"

# Module-level engine singleton (suitable for single-user shared hosting)
_engine = BIOSProcessEngine()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine_loaded():
    return _engine.df is not None


def _uid_map():
    df = _engine.get_dataframe()
    df = df.copy()
    df["Step_UID"] = df["Step_UID"].astype(str)
    return df.set_index("Step_UID").to_dict(orient="index")


def _strip_prefix(s):
    if not s:
        return ""
    s = str(s).strip()
    if s.lower().startswith("human:"):
        return s.split(":", 1)[1].strip()
    if s.lower().startswith("system:"):
        return s.split(":", 1)[1].strip()
    return s


def _make_serializable(obj):
    """Recursively convert sets to lists for JSON serialization."""
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(i) for i in obj]
    return obj


# ---------------------------------------------------------------------------
# Routes – Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/assets/<path:filename>")
def serve_asset(filename):
    return send_from_directory(asset_dir, filename)


# ---------------------------------------------------------------------------
# Routes – API
# ---------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Upload CSV/XLSX and initialise the engine."""
    global _engine
    file = request.files.get("file")
    if not file:
        return jsonify({"ok": False, "error": "No file provided"}), 400

    try:
        filename = file.filename
        _engine = BIOSProcessEngine()
        
        # Determine if it's CSV or Excel and load appropriately
        if filename.lower().endswith('.csv'):
            # Load CSV from the file stream
            import pandas as pd
            df = pd.read_csv(file)
            _engine.load(df)
        elif filename.lower().endswith(('.xls', '.xlsx')):
            # Load Excel from the file stream
            import pandas as pd
            df = pd.read_excel(file, engine="openpyxl")
            _engine.load(df)
        else:
            return jsonify({"ok": False, "error": "Unsupported file type. Please upload a CSV or XLSX file."}), 400
            
        issues = _engine.validate()
        return jsonify({"ok": True, "issues": issues})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/status")
def api_status():
    return jsonify({"loaded": _engine_loaded()})


# -------- Flow Studio --------
@app.route("/api/flow-studio/diagram")
def api_flow_diagram():
    if not _engine_loaded():
        return jsonify({"ok": False, "error": "No contract loaded"}), 400
    mode = request.args.get("mode", "operational")
    if mode == "architecture":
        xml = export_value_chain_architecture_xml(_engine)
    else:
        xml = drawio_export.export_drawio_xml(_engine)
    return jsonify({"ok": True, "xml": xml})


# -------- Process Architecture --------
@app.route("/api/architecture")
def api_architecture():
    if not _engine_loaded():
        return jsonify({"ok": False, "error": "No contract loaded"}), 400

    # Validation
    issues = _engine.validate()

    # Loops
    loops_raw = classify_loops(_engine)
    uid_map = _uid_map()
    loops_out = []
    for loop in loops_raw:
        readable_nodes = []
        for uid in loop["nodes"]:
            row = uid_map.get(str(uid), {})
            readable_nodes.append(row.get("Activity", uid))
        loops_out.append({
            "sub_process": loop["sub_process"],
            "type": loop["type"],
            "nodes_readable": readable_nodes,
            "node_string": " → ".join(readable_nodes),
        })

    # Complexity
    complexity = compute_complexity(_engine)
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
            "Complexity Score": data["score"],
        })
    comp_rows.sort(key=lambda r: r["Complexity Score"], reverse=True)

    # System Dependency
    system_dep = compute_system_dependency(_engine)
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
    sys_rows.sort(key=lambda r: r["Dependency Score"], reverse=True)

    # Hierarchy
    views = view_builders.build_process_architecture(_engine)
    arch = views["architecture"]
    rollups = _make_serializable(views["rollups"])

    # Build hierarchy with step details
    hierarchy = {}
    for outcome, vcs in arch.items():
        hierarchy[outcome] = {}
        for vc, cps in vcs.items():
            hierarchy[outcome][vc] = {}
            for cp, sps in cps.items():
                hierarchy[outcome][vc][cp] = {}
                for sp, step_uids in sps.items():
                    steps = []
                    for uid in step_uids:
                        row = uid_map.get(str(uid), {})
                        act = row.get("Activity", str(uid))
                        resp = _strip_prefix(row.get("resp_display", row.get("Responsibility", "")))
                        sys_ = row.get("System", "")
                        meta_bits = [b for b in [resp, sys_] if b]
                        meta = f" — {' • '.join(meta_bits)}" if meta_bits else ""
                        steps.append(f"{act}{meta}")
                    hierarchy[outcome][vc][cp][sp] = steps

    # Diagram XML
    arch_xml = export_value_chain_architecture_xml(_engine)

    return jsonify({
        "ok": True,
        "issues": issues,
        "loops": loops_out,
        "complexity": comp_rows,
        "system_dependency": sys_rows,
        "hierarchy": hierarchy,
        "rollups": rollups,
        "diagram_xml": arch_xml,
    })


# -------- People & Roles --------
@app.route("/api/people-roles")
def api_people_roles():
    if not _engine_loaded():
        return jsonify({"ok": False, "error": "No contract loaded"}), 400

    roles = view_builders.build_people_roles(_engine)
    uid_map = _uid_map()

    # Build role list (human only)
    human_keys = [k for k in roles.keys() if not str(k).lower().startswith("system:")]
    role_list = [{"key": k, "display": _strip_prefix(roles[k].get("display", k))} for k in human_keys]

    # If a specific role is requested
    sel = request.args.get("role")
    if not sel:
        return jsonify({"ok": True, "roles": role_list})

    if sel not in roles:
        return jsonify({"ok": False, "error": "Role not found"}), 404
    info = roles[sel]

    # Responsibilities
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

    # Decisions
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
            "Branches": " | ".join(branches),
        })

    # Handovers
    df = _engine.get_dataframe().copy()
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
                    "To Activity": next_row.get("Activity", ""),
                })

    # KPIs
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

    return jsonify({
        "ok": True,
        "roles": role_list,
        "responsibilities": resp_rows,
        "decisions": decision_rows,
        "handovers": handover_rows,
        "kpis": kpi_rows,
    })


# -------- System Catalogues --------
@app.route("/api/system-catalogues")
def api_system_catalogues():
    if not _engine_loaded():
        return jsonify({"ok": False, "error": "No contract loaded"}), 400

    systems = view_builders.build_system_catalogues(_engine)
    uid_map = _uid_map()
    system_list = list(systems.keys())

    sel = request.args.get("system")
    if not sel:
        return jsonify({"ok": True, "systems": system_list})

    if sel not in systems:
        return jsonify({"ok": False, "error": "System not found"}), 404
    info = systems[sel]

    # Steps
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

    # System Dependency
    system_dep = compute_system_dependency(_engine)
    dep_rows = []
    for sp, data in system_dep.items():
        if str(data.get("dominant_system", "")).strip().lower() == str(sel).strip().lower():
            dep_rows.append({
                "Sub Process": sp,
                "System Utilization %": data.get("system_utilization_pct", 0),
                "Unique Systems": data.get("unique_systems", 0),
                "Dependency Score": data.get("score", 0),
            })
    dep_rows.sort(key=lambda r: r["Dependency Score"], reverse=True)

    # Indicators & Roles
    metrics = sorted(info.get("metrics", []))
    kpis = sorted(info.get("kpis", []))
    reports = sorted(info.get("reports", []))
    roles_list = sorted({_strip_prefix(r) for r in info.get("roles", []) if r})

    return jsonify({
        "ok": True,
        "systems": system_list,
        "steps": step_rows,
        "dependency": dep_rows,
        "metrics": metrics or [],
        "kpis": kpis or [],
        "reports": reports or [],
        "roles": roles_list or [],
    })


# -------- Metrics & KPIs --------
@app.route("/api/metrics")
def api_metrics():
    if not _engine_loaded():
        return jsonify({"ok": False, "error": "No contract loaded"}), 400

    df = _engine.get_dataframe().copy()
    view = df[df["KPI"].notna() & (df["KPI"] != "")][
        ["Outcome", "Sub Process", "KPI", "Metric", "System"]
    ].drop_duplicates()
    rows = view.to_dict(orient="records")
    return jsonify({"ok": True, "rows": rows})


# -------- Executive Summary --------
@app.route("/api/executive-summary")
def api_executive_summary():
    if not _engine_loaded():
        return jsonify({"ok": False, "error": "No contract loaded"}), 400

    complexity = compute_complexity(_engine)
    system_dep = compute_system_dependency(_engine)
    fragility = compute_fragility(_engine)
    loops = classify_loops(_engine)

    # Top Risk
    frag_rows = []
    for sp in fragility:
        frag_rows.append({
            "Sub Process": sp,
            "Complexity": complexity.get(sp, {}).get("score", 0),
            "System Dependency": system_dep.get(sp, {}).get("score", 0),
            "Fragility Score": fragility.get(sp, 0),
        })
    frag_rows.sort(key=lambda r: r["Fragility Score"], reverse=True)

    # Loop Health
    total_loops = len(loops)
    structural = len([l for l in loops if l["type"] == "structural"])
    controlled = len([l for l in loops if l["type"] == "controlled"])

    # Narrative
    narrative = ""
    if frag_rows:
        top = frag_rows[0]
        sp = top["Sub Process"]
        narrative = (
            f"The subprocess **{sp}** currently exhibits the highest fragility score.\n\n"
            f"• Complexity Score: {top['Complexity']}\n"
            f"• System Dependency Score: {top['System Dependency']}\n"
            f"• Composite Fragility: {top['Fragility Score']}\n\n"
            f"Recommendation:\n"
            f"Review governance controls, system redundancy, and loop structures within this subprocess."
        )

    return jsonify({
        "ok": True,
        "fragility": frag_rows,
        "loop_health": {
            "total": total_loops,
            "controlled": controlled,
            "structural": structural,
        },
        "narrative": narrative,
    })


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
