from pellicule.schema import build_event, event_to_jsonl_line


def test_build_event_stable_null_fields():
    ev = build_event(
        session_id="abc",
        layer="llm",
        turn=1,
        model="provider/model",
        summary="completion",
        latency_ms=10,
        prompt_tokens=None,
        completion_tokens=None,
    )
    assert ev["parent_session_id"] is None
    assert ev["case_dir"] is None
    assert ev["layer"] == "llm"
    line = event_to_jsonl_line(ev)
    assert line.endswith("\n")
    assert '"session_id": "abc"' in line
