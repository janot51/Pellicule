import json

from pellicule.tool_extract import merge_stream_chunk
from pellicule.stream_relay import usage_tokens


def test_merge_stream_usage_and_tokens():
    fold: dict = {}
    chunk = {
        "choices": [{"delta": {"reasoning_content": "think"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 5},
    }
    merge_stream_chunk(fold, chunk)
    assert fold["reasoning_content"] == "think"
    pt, ct = usage_tokens(fold["usage"])
    assert pt == 3 and ct == 5
