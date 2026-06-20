from __future__ import annotations
import copy
from domain.models import Conflict, Drug, PatientProfile
from agents import risk
from tools.datasource import DataSource


def conflict_key(c: Conflict) -> str:
    return c.flag_type.value + "|" + "+".join(sorted(c.drugs))


def _resolve(names, ds) -> list[Drug]:
    out = []
    for n in names:
        d = ds.resolve_drug(n)
        if d:
            out.append(d)
    return out


def compute_delta(prev: PatientProfile | None, curr: PatientProfile, ds: DataSource) -> dict:
    curr_conf = risk.analyze(curr, ds)
    if prev is None:
        return {"first_visit": True, "added_drugs": [d.name for d in curr.drugs],
                "removed_drugs": [], "new_conflicts": curr_conf, "resolved_conflicts": []}
    prev_conf = risk.analyze(prev, ds)
    prev_keys = {conflict_key(c) for c in prev_conf}
    curr_keys = {conflict_key(c) for c in curr_conf}
    prev_names = {d.name for d in prev.drugs}
    curr_names = {d.name for d in curr.drugs}
    return {
        "first_visit": False,
        "added_drugs": sorted(curr_names - prev_names),
        "removed_drugs": sorted(prev_names - curr_names),
        "new_conflicts": [c for c in curr_conf if conflict_key(c) not in prev_keys],
        "resolved_conflicts": [c for c in prev_conf if conflict_key(c) not in curr_keys],
    }


def simulate_whatif(profile: PatientProfile, ds: DataSource,
                    add_names: list[str] | None = None,
                    remove_names: list[str] | None = None) -> dict:
    add_names = add_names or []
    remove_names = remove_names or []
    before = risk.analyze(profile, ds)
    after_p = copy.deepcopy(profile)
    after_p.drugs = [d for d in after_p.drugs if d.name not in set(remove_names)]
    after_p.drugs += _resolve(add_names, ds)
    after = risk.analyze(after_p, ds)
    before_keys = {conflict_key(c) for c in before}
    after_keys = {conflict_key(c) for c in after}
    return {
        "before": before, "after": after,
        "newly_introduced": [c for c in after if conflict_key(c) not in before_keys],
        "resolved": [c for c in before if conflict_key(c) not in after_keys],
    }
