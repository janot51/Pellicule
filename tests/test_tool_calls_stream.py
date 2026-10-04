from pellicule.tool_extract import (
    merge_stream_chunk,
    tool_calls_from_fold,
    tool_calls_from_response,
)


def test_sse_tool_call_delta_assembly():
    fold: dict = {}
    merge_stream_chunk(
        fold,
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_abc",
                                "function": {"name": "read", "arguments": '{"path":'},
                            }
                        ]
                    }
                }
            ]
        },
    )
    merge_stream_chunk(
        fold,
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {"arguments": ' "note.txt"}'},
                            }
                        ]
                    }
                }
            ]
        },
    )
    calls = tool_calls_from_fold(fold)
    assert len(calls) == 1
    assert calls[0]["id"] == "call_abc"
    assert calls[0]["function"]["name"] == "read"
    assert calls[0]["function"]["arguments"] == '{"path": "note.txt"}'


def test_non_stream_tool_calls():
    body = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_x",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": '{"command":"echo hi"}',
                            },
                        }
                    ],
                }
            }
        ]
    }
    calls = tool_calls_from_response(body)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "bash"
