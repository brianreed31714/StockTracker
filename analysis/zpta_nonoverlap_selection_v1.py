"""Deterministic non-overlap and chronological holdout selection for ZPTA research.

Research-only utilities; do not imply executable fills or portfolio performance.
Events require integer signal_index and exit_index from the PR #6 engine.
"""
from __future__ import annotations


def select_nonoverlapping(events):
    """Greedily take earliest signal; permit new entry only AFTER prior exit.

    Same-day exits and new entries are conservatively treated as conflicting.
    Deterministic tie breaking avoids sensitivity to input ordering.
    Returns new dictionaries, leaving the source events unchanged.
    """
    ordered = sorted(events, key=lambda e: (e["signal_index"], e["exit_index"], str(e.get("signal_date", ""))))
    chosen = []
    last_exit = -1
    for event in ordered:
        signal, exit_ = event["signal_index"], event["exit_index"]
        if not isinstance(signal, int) or not isinstance(exit_, int) or signal >= exit_:
            raise ValueError("Event requires integer signal_index < exit_index")
        if signal <= last_exit:
            continue
        chosen.append(dict(event))
        last_exit = exit_
    return chosen


def embargoed_split(events, cutoff):
    """Split by signal index; drop train trades crossing cutoff.

    Test positions must originate on/after cutoff. Apply selection separately
    within each split; do not use test returns for signal calibration.
    """
    if not isinstance(cutoff, int) or cutoff < 0:
        raise ValueError("Invalid chronological cutoff")
    training = [e for e in events if e["signal_index"] < cutoff and e["exit_index"] < cutoff]
    holdout = [e for e in events if e["signal_index"] >= cutoff]
    return {"training": select_nonoverlapping(training),
            "holdout": select_nonoverlapping(holdout)}
