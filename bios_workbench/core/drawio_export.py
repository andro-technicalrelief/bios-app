"""Generate deterministic left-to-right draw.io XML exports with swimlanes (cycle-safe)."""
from typing import Optional, Dict, Any, List
from xml.sax.saxutils import escape
from collections import deque, defaultdict

COL_WIDTH = 180
ROW_HEIGHT = 80
LANE_HEIGHT = 100
LANE_GAP = 20


def export_drawio_xml(engine, sub_process: Optional[str] = None) -> str:
    """
    Export a draw.io XML string for the whole model (or a single Sub Process).

    IMPORTANT:
    - This version is cycle-safe (won't infinite-loop on processes with loops).
    - Layout is approximated using BFS levels from start nodes.
    """
    df = engine.get_dataframe()
    if sub_process:
        df = df[df["Sub Process"] == sub_process]

    # --- compute lanes (responsibility display) ---
    lanes = list(df["resp_display"].unique()) if "resp_display" in df.columns else list(df["Responsibility"].unique())
    # order: human first, then system
    human_lanes = [l for l in lanes if not str(l).lower().startswith("system:")]
    system_lanes = [l for l in lanes if str(l).lower().startswith("system:")]
    lanes = human_lanes + system_lanes
    lane_index = {l: i for i, l in enumerate(lanes)}

    # --- build nodes ---
    nodes: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        uid = str(row["Step_UID"])
        nodes[uid] = {
            "type": str(row.get("Step_Type", "")).lower(),
            "label": str(row.get("Activity", "")),
            "lane": row.get("resp_display", row.get("Responsibility", "")),
        }

    # --- build edges (only within the current node set) ---
    edges: List[Dict[str, Any]] = []
    for f, t, lbl in engine.get_edges():
        f = str(f)
        t = str(t)
        if f in nodes and t in nodes:
            edges.append({"from": f, "to": t, "label": lbl})

    # Deterministic ordering
    edges.sort(key=lambda e: (e["from"], e["to"], "" if e["label"] is None else str(e["label"])))

    # --- cycle-safe level computation (BFS) ---
    adj = defaultdict(list)
    in_deg = defaultdict(int)

    for e in edges:
        adj[e["from"]].append(e["to"])
        in_deg[e["to"]] += 1
        in_deg.setdefault(e["from"], 0)

    # pick starts: Step_Type == "start" if present, else in-degree 0, else any node
    starts = [uid for uid, info in nodes.items() if str(info.get("type", "")).lower() == "start"]
    if not starts:
        starts = [u for u in nodes.keys() if in_deg.get(u, 0) == 0]
    if not starts and nodes:
        starts = [sorted(nodes.keys())[0]]

    level = {u: 0 for u in nodes.keys()}
    q = deque(starts)
    seen = set(starts)

    while q:
        u = q.popleft()
        for v in adj.get(u, []):
            # cycle-safe: levels only move upward but traversal does not loop endlessly
            level[v] = max(level.get(v, 0), level[u] + 1)
            if v not in seen:
                seen.add(v)
                q.append(v)

    # --- assign positions ---
    positions: Dict[str, Any] = {}
    # deterministic node ordering for placement
    for uid in sorted(nodes.keys(), key=lambda x: (level.get(x, 0), x)):
        info = nodes[uid]
        x = level.get(uid, 0) * COL_WIDTH + 50
        y = lane_index.get(info["lane"], 0) * (LANE_HEIGHT + LANE_GAP) + 50
        positions[uid] = (x, y)

    # --- build XML cells ---
    cells: List[str] = []
    vertex_id = 2  # 0 and 1 are reserved root cells below
    id_map: Dict[str, str] = {}

    # vertices
    for uid in sorted(nodes.keys(), key=lambda x: (level.get(x, 0), x)):
        info = nodes[uid]
        x, y = positions[uid]
        w, h = 120, 60

        if info["type"] in {"start", "end"}:
            shape_style = "shape=ellipse;whiteSpace=wrap;html=1;"
        elif info["type"] == "decision":
            shape_style = "shape=rhombus;whiteSpace=wrap;html=1;"
        else:
            shape_style = "rounded=1;whiteSpace=wrap;html=1;"

        label = escape(info.get("label", ""))
        lane = escape(str(info.get("lane", "")))
        value = f"{escape(uid)}: {label}"
        if lane:
            value += f"&#10;{lane}"

        cells.append(
            f'<mxCell id="{vertex_id}" value="{value}" style="{shape_style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
            f"</mxCell>"
        )
        id_map[uid] = str(vertex_id)
        vertex_id += 1

    # edges
    for e in edges:
        src = id_map.get(e["from"])
        tgt = id_map.get(e["to"])
        if not src or not tgt:
            continue

        edge_label = "" if e.get("label") is None else escape(str(e["label"]))

        cells.append(
            f'<mxCell id="{vertex_id}" value="{edge_label}" style="edgeStyle=orthogonalEdgeStyle;html=1;" '
            f'edge="1" parent="1" source="{src}" target="{tgt}">'
            f'<mxGeometry relative="1" as="geometry"/>'
            f"</mxCell>"
        )
        vertex_id += 1

    # wrap
    xml = (
        "<mxfile><diagram>"
        '<mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
        'fold="1" page="1" pageScale="1" pageWidth="850" pageHeight="1100" math="0" shadow="0">'
        "<root>"
        '<mxCell id="0"/>'
        '<mxCell id="1" parent="0"/>'
        + "".join(cells) +
        "</root></mxGraphModel></diagram></mxfile>"
    )
    return xml
