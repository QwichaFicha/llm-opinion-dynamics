"""Deterministic controls. These are mathematical rules, never LLM results."""
import json
import math
import statistics


def validate_action(raw):
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"opinion", "message"}:
        raise ValueError("Expected exactly opinion and message")
    x = value["opinion"]
    if isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) or not -1 <= x <= 1:
        raise ValueError("Opinion must be a finite number in [-1, 1]")
    if not isinstance(value["message"], str) or not 1 <= len(value["message"]) <= 800:
        raise ValueError("Message length must be 1..800")
    return {"opinion": float(x), "message": value["message"]}


def rule_update(state):
    x = state["opinion"]
    # Newest time slice gets total weight 1, older slices decay geometrically.
    # Only actual exposures are passed in, never the entire population state.
    slices = sorted({e["round"] for e in state["exposures"]})
    influence = 0.0
    for t in slices:
        entries = [e for e in state["exposures"] if e["round"] == t]
        current_round = state["round"]
        news = [e["value"] for e in entries if e["kind"] == "news"]
        peer = [e["value"] for e in entries if e["kind"] == "peer"]
        shift = (0.25 * state["trust"] * (statistics.mean(news) - x) if news else 0)
        shift += (0.30 * (statistics.mean(peer) - x) if peer else 0)
        influence += (0.5 ** (current_round - t)) * shift
    return round(max(-1.0, min(1.0, x + influence)), 6)


def metrics(initial, final, edges):
    mean = statistics.mean(final)
    return {
        "mean_opinion": mean,
        "variance": statistics.pvariance(final),
        "mean_abs_opinion": statistics.mean(abs(x) for x in final),
        "mean_abs_shift": statistics.mean(abs(x-y) for x,y in zip(initial, final)),
        "a_share": sum(x > 0.1 for x in final) / len(final),
        "b_share": sum(x < -0.1 for x in final) / len(final),
        "undecided_share": sum(-0.1 <= x <= 0.1 for x in final) / len(final),
        "switches": sum((x > 0.1 and y < -0.1) or (x < -0.1 and y > 0.1) for x,y in zip(initial, final)),
        "edge_disagreement": statistics.mean(abs(final[a]-final[b]) for a,b in edges) if edges else 0,
    }
