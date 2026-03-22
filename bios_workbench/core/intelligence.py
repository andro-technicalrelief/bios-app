from collections import defaultdict


def classify_loops(engine):
    """
    Detect cycles and classify them as:
    - controlled (contains decision node)
    - structural (no decision node)

    Returns:
        [
            {
                "sub_process": str,
                "nodes": [uids],
                "type": "controlled" | "structural"
            }
        ]
    """

    df = engine.get_dataframe()
    edges = engine.edges

    # Build adjacency
    adj = defaultdict(list)
    for f, t, _ in edges:
        adj[f].append(t)

    visited = set()
    stack = []
    loops = []

    def dfs(node):
        if node in stack:
            # cycle detected
            cycle_start = stack.index(node)
            cycle_nodes = stack[cycle_start:].copy()
            loops.append(cycle_nodes)
            return

        if node in visited:
            return

        visited.add(node)
        stack.append(node)

        for nei in adj.get(node, []):
            dfs(nei)

        stack.pop()

    for uid in df["Step_UID"].astype(str):
        if uid not in visited:
            dfs(uid)

    # Classify loops
    results = []
    uid_lookup = df.set_index("Step_UID").to_dict("index")

    for loop in loops:
        step_types = [uid_lookup.get(uid, {}).get("Step_Type", "") for uid in loop]
        sub_processes = {uid_lookup.get(uid, {}).get("Sub Process", "") for uid in loop}

        if any(t == "decision" for t in step_types):
            loop_type = "controlled"
        else:
            loop_type = "structural"

        for sp in sub_processes:
            results.append({
                "sub_process": sp,
                "nodes": loop,
                "type": loop_type
            })

    return results
def compute_complexity(engine):
    """
    Computes structural complexity per Sub Process.

    Returns:
        {
            sub_process: {
                step_count: int,
                decision_count: int,
                roles: int,
                systems: int,
                loop_count: int,
                structural_loops: int,
                score: float (0-100)
            }
        }
    """

    df = engine.get_dataframe()
    loops = classify_loops(engine)

    results = {}

    # Ensure Step_UID treated consistently as string
    df = df.copy()
    df["Step_UID"] = df["Step_UID"].astype(str)

    for sp in df["Sub Process"].dropna().unique():

        sp_df = df[df["Sub Process"] == sp]

        step_count = len(sp_df)
        decision_count = len(sp_df[sp_df["Step_Type"] == "decision"])
        roles = sp_df["Responsibility"].nunique()
        systems = sp_df["System"].replace("", None).dropna().nunique()

        sp_loops = [l for l in loops if l["sub_process"] == sp]
        loop_count = len(sp_loops)
        structural_loops = len([l for l in sp_loops if l["type"] == "structural"])

        # Initial weighted scoring model (v2 baseline)
        raw_score = (
            step_count * 1.5 +
            decision_count * 3 +
            roles * 2 +
            systems * 2 +
            loop_count * 4 +
            structural_loops * 8
        )

        score = min(round(raw_score, 1), 100)

        results[sp] = {
            "step_count": step_count,
            "decision_count": decision_count,
            "roles": roles,
            "systems": systems,
            "loop_count": loop_count,
            "structural_loops": structural_loops,
            "score": score
        }

    return results
def compute_system_dependency(engine):
    """
    Computes system dependency per Sub Process.

    Returns:
        {
            sub_process: {
                total_steps: int,
                system_steps: int,
                system_utilization_pct: float,
                unique_systems: int,
                dominant_system: str | None,
                score: float (0-100)
            }
        }
    """

    df = engine.get_dataframe().copy()
    df["Step_UID"] = df["Step_UID"].astype(str)

    results = {}

    for sp in df["Sub Process"].dropna().unique():

        sp_df = df[df["Sub Process"] == sp]

        total_steps = len(sp_df)
        system_steps = len(sp_df[sp_df["System"].notna() & (sp_df["System"] != "")])

        unique_systems = sp_df["System"].replace("", None).dropna().nunique()

        # Dominant system (most frequent) if systems exist
        if unique_systems > 0:
            dominant_system = (
                sp_df["System"]
                .replace("", None)
                .dropna()
                .value_counts()
                .idxmax()
            )
        else:
            dominant_system = None

        utilization_pct = round((system_steps / total_steps) * 100, 1) if total_steps else 0.0

        # Scoring model (simple + explainable baseline)
        raw_score = (
            utilization_pct * 0.6 +   # % of steps touching systems
            unique_systems * 10       # number of distinct systems
        )

        score = min(round(raw_score, 1), 100)

        results[sp] = {
            "total_steps": total_steps,
            "system_steps": system_steps,
            "system_utilization_pct": utilization_pct,
            "unique_systems": unique_systems,
            "dominant_system": dominant_system,
            "score": score
        }

    return results
def compute_fragility(engine):
    """
    Composite fragility score combining:
    - Complexity
    - System Dependency
    - Structural loop penalty
    """

    complexity = compute_complexity(engine)
    system_dep = compute_system_dependency(engine)
    loops = classify_loops(engine)

    results = {}

    structural_counts = {}
    for l in loops:
        if l["type"] == "structural":
            structural_counts[l["sub_process"]] = structural_counts.get(l["sub_process"], 0) + 1

    for sp in complexity.keys():

        comp_score = complexity.get(sp, {}).get("score", 0)
        sys_score = system_dep.get(sp, {}).get("score", 0)
        structural_penalty = structural_counts.get(sp, 0) * 10

        fragility = (
            comp_score * 0.4 +
            sys_score * 0.4 +
            structural_penalty * 0.2
        )

        results[sp] = round(min(fragility, 100), 1)

    return results