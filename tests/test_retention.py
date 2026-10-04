from pellicule.retention import HEAD_MAX_BYTES, retain_text_body


def test_retain_text_body_full_on_deny():
    from pellicule.retention import retain_for_policy_verdict

    text = "y" * 3000
    info = retain_for_policy_verdict("deny", text)
    assert "full" in info
    assert len(info["full"]) == len(text)


def test_retain_text_body_head_and_hash():
    text = "x" * (HEAD_MAX_BYTES + 50)
    info = retain_text_body(text)
    assert info["size_bytes"] == len(text.encode("utf-8"))
    assert len(info["head"]) <= HEAD_MAX_BYTES
    assert len(info["sha256"]) == 64
