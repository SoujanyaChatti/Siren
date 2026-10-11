"""JSON output schemas, in Gemini responseSchema (OpenAPI subset) form. Validators re-check everything."""
S, N, I, B, A, O = "STRING", "NUMBER", "INTEGER", "BOOLEAN", "ARRAY", "OBJECT"

EXPLANATION = {
    "type": O,
    "properties": {
        "headline": {"type": S},
        "what_is_happening": {"type": S},
        "why": {"type": A, "items": {"type": O, "properties": {"rule_id": {"type": S}, "evidence": {"type": S}},
                                     "required": ["rule_id", "evidence"]}},
        "who_may_be_affected": {"type": S},
        "missing_data": {"type": A, "items": {"type": S}},
        "confidence_note": {"type": S},
    },
    "required": ["headline", "what_is_happening", "why", "who_may_be_affected", "missing_data", "confidence_note"],
}

TRANSLATION = {
    "type": O,
    "properties": {"language": {"type": S}, "text": {"type": S}, "kept_terms": {"type": A, "items": {"type": S}}},
    "required": ["language", "text", "kept_terms"],
}

QA = {
    "type": O,
    "properties": {"answerable": {"type": B}, "answer": {"type": S},
                   "citations": {"type": A, "items": {"type": S}}, "language": {"type": S}},
    "required": ["answerable", "answer", "citations", "language"],
}

DEPTH = {
    "type": O,
    "properties": {
        "reference_objects": {"type": A, "items": {"type": O, "properties": {
            "type": {"type": S}, "typical_height_in": {"type": N}, "waterline_fraction": {"type": N},
            "box": {"type": A, "items": {"type": N}}},
            "required": ["type", "typical_height_in", "waterline_fraction"]}},
        "depth_in": {"type": N}, "depth_low_in": {"type": N}, "depth_high_in": {"type": N},
        "confidence": {"type": N}, "is_road": {"type": B}, "notes": {"type": S},
        "waterline_y": {"type": N},
    },
    "required": ["reference_objects", "depth_in", "depth_low_in", "depth_high_in", "confidence", "is_road", "notes"],
}
