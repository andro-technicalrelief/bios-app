"""Core engine that handles ingestion, normalization, validation and graph operations."""
from __future__ import annotations
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional, Set
from . import contract, utils


class ValidationIssue(Exception):
    pass


class BIOSProcessEngine:
    def __init__(self):
        self.raw_df: Optional[pd.DataFrame] = None
        self.df: Optional[pd.DataFrame] = None
        # edges stored as list of (from, to, label)
        self.edges: List[Tuple[str, str, Optional[str]]] = []
        # mapping step_uid -> row index
        self.uid_index: Dict[str, int] = {}
        # helpers per sub process
        self.subprocesses: Dict[str, Set[str]] = {}

    def load(self, source: Any) -> None:
        """Load from CSV/XLSX path or file-like or DataFrame."""
        if isinstance(source, pd.DataFrame):
            df = source.copy()
        else:
            # assume path-like or file-like
            try:
                df = pd.read_csv(source)
            except Exception:
                df = pd.read_excel(source, engine="openpyxl")
        self.raw_df = df
        self.normalize()
        self.build_graph()

    def normalize(self) -> None:
        """Apply normalization rules to raw_df and populate self.df."""
        if self.raw_df is None:
            raise ValueError("No data loaded")
        df = self.raw_df.copy()
        # ensure headers exist
        missing = [h for h in contract.HEADERS if h not in df.columns]
        if missing:
            raise ValidationIssue(f"Missing headers: {missing}")
        # trim whitespace for string columns
        for col in contract.HEADERS:
            df[col] = df[col].fillna("").astype(str).apply(lambda x: x.strip())
        # normalize step_type
        df["Step_Type"] = df["Step_Type"].apply(contract.normalize_step_type)
        # canonical responsibility
        df["resp_canon"] = df["Responsibility"].apply(contract.canonical_responsibility)
        df["resp_display"] = df["Responsibility"].apply(contract.display_responsibility)
        # parse next steps
        df["parsed_next"] = df["Next_Step_UIDs"].apply(contract.parse_next_steps)
        # build uid index
        self.uid_index = {}
        duplicates = []
        for idx, uid in df["Step_UID"].items():
            if uid in self.uid_index:
                duplicates.append(uid)
            else:
                self.uid_index[uid] = idx
        if duplicates:
            raise ValidationIssue(f"Duplicate Step_UIDs: {duplicates}")
        self.df = df

    def build_graph(self) -> None:
        """Populate edges list and subprocess grouping."""
        if self.df is None:
            raise ValueError("Data not normalized")
        self.edges = []
        self.subprocesses = {}
        for _, row in self.df.iterrows():
            uid = row["Step_UID"]
            sp = row["Sub Process"]
            self.subprocesses.setdefault(sp, set()).add(uid)
            for to_uid, lbl in row["parsed_next"]:
                self.edges.append((uid, to_uid, lbl))

    def _get_edges_for_sub(self, subproc: str) -> List[Tuple[str, str, Optional[str]]]:
        return [(f, t, l) for (f, t, l) in self.edges if self.df.loc[self.uid_index[f], "Sub Process"] == subproc]

    def validate(self, strict: bool = False) -> List[Dict[str, Any]]:
        """Perform validation rules, return list of issue dicts."""
        issues: List[Dict[str, Any]] = []
        if self.df is None:
            raise ValueError("No data loaded")
        df = self.df
        # rule 2: required fields
        for idx, row in df.iterrows():
            for col in ["Outcome", "Value Chain", "Core Process", "Sub Process", "Step_UID", "Step_Type", "Activity", "Responsibility"]:
                if not row[col] or str(row[col]).strip() == "":
                    issues.append({
                        "severity": "error",
                        "code": "missing_required",
                        "message": f"{col} is required",
                        "row_hint": idx + 2,  # account for header
                        "column": col,
                        "step_uid": row.get("Step_UID"),
                    })
        # rule 3: start count per subproc
        for sp, uids in self.subprocesses.items():
            starts = [u for u in uids if df.loc[self.uid_index[u], "Step_Type"] == "start"]
            if len(starts) == 0:
                issues.append({"severity": "error", "code": "no_start", "message": f"Sub Process '{sp}' has no start step"})
            elif len(starts) > 1:
                issues.append({"severity": "warning", "code": "multiple_starts", "message": f"Sub Process '{sp}' has multiple start steps"})
        # rule 4: every next uid exists
        for f, t, _ in self.edges:
            if t not in self.uid_index:
                issues.append({"severity": "error", "code": "unknown_next", "message": f"Next step '{t}' referenced from '{f}' does not exist", "step_uid": f})
        # rule 5: dead-ends
        for idx, row in df.iterrows():
            uid = row["Step_UID"]
            typ = row["Step_Type"]
            outs = row["parsed_next"]
            if typ in {"task", "decision", "event", "subprocess", "start"} and len(outs) == 0:
                issues.append({"severity": "error", "code": "dead_end", "message": f"Step '{uid}' of type '{typ}' has no outgoing edges", "step_uid": uid})
            if typ == "end" and len(outs) > 0:
                issues.append({"severity": "warning", "code": "end_has_outgoing", "message": f"End step '{uid}' has outgoing edges", "step_uid": uid})
        # rule 6: decision requirements
        for idx, row in df.iterrows():
            if row["Step_Type"] == "decision":
                outs = row["parsed_next"]
                if len(outs) < 2:
                    issues.append({"severity": "error", "code": "decision_branches", "message": f"Decision '{row['Step_UID']}' has fewer than 2 branches", "step_uid": row['Step_UID']})
                for to_uid, lbl in outs:
                    if lbl is None:
                        issues.append({"severity": "warning", "code": "decision_no_label", "message": f"Decision edge to '{to_uid}' missing label", "step_uid": row['Step_UID']})
        # rule 7 & 8: per sub process cycle and reachability
        for sp in self.subprocesses:
            uids = list(self.subprocesses[sp])
            # build adjacency
            adj: Dict[str, List[str]] = {u: [] for u in uids}
            for f, t, _ in self._get_edges_for_sub(sp):
                if f in adj:
                    adj[f].append(t)
            # detect cycles via DFS
            visited = set()
            recstack = set()

            def dfs(v):
                visited.add(v)
                recstack.add(v)
                for nei in adj.get(v, []):
                    if nei not in visited:
                        if dfs(nei):
                            return True
                    elif nei in recstack:
                        return True
                recstack.remove(v)
                return False

            for u in uids:
                if u not in visited:
                    if dfs(u):
                        issues.append({"severity": "error", "code": "cycle", "message": f"Cycle detected in Sub Process '{sp}'", "step_uid": u})
                        break
            # reachability
            starts = [u for u in uids if df.loc[self.uid_index[u], "Step_Type"] == "start"]
            reachable = set()
            def walk(u):
                if u in reachable:
                    return
                reachable.add(u)
                for nei in adj.get(u, []):
                    walk(nei)
            for s in starts:
                walk(s)
            for u in uids:
                if u not in reachable:
                    issues.append({"severity": "warning", "code": "unreachable", "message": f"Step '{u}' in Sub Process '{sp}' is unreachable from start", "step_uid": u})
        return issues

    # helper retrieval methods for view builders
    def get_dataframe(self) -> pd.DataFrame:
        if self.df is None:
            raise ValueError("No data loaded")
        return self.df.copy()

    def get_edges(self) -> List[Tuple[str, str, Optional[str]]]:
        return list(self.edges)

    def get_subprocesses(self) -> List[str]:
        return list(self.subprocesses.keys())

    def get_steps_for_role(self, resp_canon: str) -> pd.DataFrame:
        df = self.get_dataframe()
        return df[df["resp_canon"] == resp_canon]

    def get_steps_for_system(self, system: str) -> pd.DataFrame:
        df = self.get_dataframe()
        # system field or responsibilities with system:
        mask = (df["System"].str.lower() == system.lower())
        mask |= df["resp_canon"].str.startswith(f"system:{system.lower()}")
        return df[mask]
