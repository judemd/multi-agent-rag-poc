import re

def validate_citations(answer, evidence, insufficient=False):
    cited = set(re.findall(r"\[([^\[\]\n]+)\]", answer))
    valid = {e["citation"] for e in evidence}
    if cited - valid:
        raise ValueError("Answer contains unknown citation references")
    if not insufficient and (not cited or not answer.strip()):
        raise ValueError("A supported answer requires valid source citations")
    return cited

def review_reasons(result, evidence, always, threshold, question):
    reasons = []
    if always:
        reasons.append("Always review answers is enabled")
    if not evidence or min(e["distance"] for e in evidence) > threshold:
        reasons.append("No close retrieval match (distance threshold)")
    if result.get("conflict"):
        reasons.append("Agent reported conflicting sources")
    if re.search(r"\b(total|average|sum|count|how many|percentage)\b", question, re.I):
        reasons.append("Exact aggregation is outside this demo's scope")
    if result.get("insufficient"):
        reasons.append("Insufficient evidence")
    return reasons
