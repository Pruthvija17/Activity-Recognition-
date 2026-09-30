"""Compare an observed activity sequence with an expected experiment workflow.

The observed events (sorted by time, rejected events excluded, consecutive repeats collapsed)
are aligned with the expected steps using a longest-common-subsequence alignment, which keeps as
many expected steps in order as possible. Differences are reported as:

  missing       an expected step never happened
  out_of_order  an expected step happened, but not in its expected position
  unexpected    an observed activity that is not part of the workflow
  unknown       an Unknown / unexpected activity was observed
  repeated      (informational) a workflow activity occurred again outside its step

The result never claims the experiment failed: deviations mean "operator review required".
"""
from dataclasses import dataclass
from typing import List, Optional, Sequence

from services.activity.rules import UNKNOWN

# PRD example workflow (Equipment Transfer), used when an experiment has none configured.
DEFAULT_WORKFLOW = [
    "Walking",
    "Reaching",
    "Picking up an object",
    "Handling experimental equipment",
    "Placing an object",
]

DEVIATION_TYPES = ("missing", "out_of_order", "unexpected", "unknown")


@dataclass
class ObservedStep:
    activity: str
    start: float
    end: float
    person: str


def collapse(events: Sequence[ObservedStep]) -> List[ObservedStep]:
    """Merge consecutive observations of the same activity into one step."""
    out: List[ObservedStep] = []
    for e in sorted(events, key=lambda e: e.start):
        if out and out[-1].activity == e.activity:
            out[-1].end = max(out[-1].end, e.end)
        else:
            out.append(ObservedStep(e.activity, e.start, e.end, e.person))
    return out


def _lcs_pairs(expected: List[str], observed: List[str]) -> List[tuple]:
    n, m = len(expected), len(observed)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if expected[i] == observed[j] else max(dp[i + 1][j], dp[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if expected[i] == observed[j]:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def evaluate(expected: List[str], events: Sequence[ObservedStep]) -> dict:
    observed = collapse(events)
    exp_l = [s.lower() for s in expected]
    obs_l = [o.activity.lower() for o in observed]
    pairs = _lcs_pairs(exp_l, obs_l)
    matched_exp = {i: j for i, j in pairs}
    matched_obs = {j for _, j in pairs}

    steps, deviations = [], []
    consumed = set(matched_obs)
    for i, step in enumerate(expected):
        if i in matched_exp:
            o = observed[matched_exp[i]]
            steps.append({"index": i, "activity": step, "status": "done", "time": o.start, "person": o.person})
            continue
        # Happened somewhere else in the sequence -> out of order; otherwise missing.
        elsewhere = next((j for j, a in enumerate(obs_l) if a == exp_l[i] and j not in consumed), None)
        if elsewhere is not None:
            consumed.add(elsewhere)
            o = observed[elsewhere]
            steps.append({"index": i, "activity": step, "status": "out_of_order", "time": o.start, "person": o.person})
            deviations.append({"type": "out_of_order", "step_index": i, "activity": step, "time": o.start,
                               "person": o.person,
                               "detail": f"'{step}' occurred at {o.start:.1f}s but not in its expected position."})
        else:
            # Expected around the next matched step after it (or at the end).
            after = [observed[matched_exp[k]].start for k in range(i + 1, len(expected)) if k in matched_exp]
            when = after[0] if after else (observed[-1].end if observed else None)
            steps.append({"index": i, "activity": step, "status": "missing", "time": when, "person": None})
            deviations.append({"type": "missing", "step_index": i, "activity": step, "time": when, "person": None,
                               "detail": f"Expected step '{step}' was not observed."})

    expected_set = set(exp_l)
    notes = []
    for j, o in enumerate(observed):
        if j in consumed:
            continue
        if o.activity == UNKNOWN:
            deviations.append({"type": "unknown", "step_index": None, "activity": o.activity, "time": o.start,
                               "person": o.person, "detail": f"Unknown / unexpected activity at {o.start:.1f}s."})
        elif obs_l[j] in expected_set:
            notes.append({"type": "repeated", "activity": o.activity, "time": o.start, "person": o.person})
        else:
            deviations.append({"type": "unexpected", "step_index": None, "activity": o.activity, "time": o.start,
                               "person": o.person,
                               "detail": f"'{o.activity}' at {o.start:.1f}s is not part of the expected workflow."})

    deviations.sort(key=lambda d: (d["time"] is None, d["time"] or 0.0))
    done = sum(1 for s in steps if s["status"] == "done")
    next_step: Optional[str] = next((s["activity"] for s in steps if s["status"] != "done"), None)
    compliant = not deviations
    return {
        "expected_sequence": list(expected),
        "observed_sequence": [o.activity for o in observed],
        "steps": steps,
        "deviations": deviations,
        "notes": notes,
        "deviation_count": len(deviations),
        "completed_steps": done,
        "completion": round(done / len(expected), 3) if expected else 1.0,
        "next_expected_step": next_step,
        "is_compliant": compliant,
        "message": (
            "Observed sequence matches the expected workflow."
            if compliant else
            "Observed sequence deviates from expected workflow - operator review required."
        ),
    }
