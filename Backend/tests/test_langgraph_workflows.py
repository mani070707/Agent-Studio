import pytest

from app.core.config import settings
from app.workflows.checkpoints import encrypted_serializer
from app.workflows.graph import EDGES, NODES, WorkflowGraph, redact_arguments


def test_research_graph_has_bounded_routing():
    assert NODES == [
        "prepare", "plan", "retrieve", "research", "approval",
        "draft", "verify", "repair", "finalize",
    ]
    assert ("approval", "draft") in EDGES
    assert ("repair", "draft") in EDGES
    assert EDGES.count(("repair", "draft")) == 1
    assert WorkflowGraph._after_verify({"validation_errors": ["bad"], "repair_count": 0}) == "repair"
    assert WorkflowGraph._after_verify({"validation_errors": ["bad"], "repair_count": 1}) == "finalize"
    assert WorkflowGraph._after_verify({"validation_errors": [], "repair_count": 0}) == "finalize"


def test_approval_arguments_are_recursively_redacted():
    result = redact_arguments({
        "query": "safe",
        "headers": {"api_token": "secret", "nested": [{"password": "hidden"}]},
    })
    assert result == {
        "query": "safe",
        "headers": {"api_token": "[REDACTED]", "nested": [{"password": "[REDACTED]"}]},
    }


def test_checkpoint_serializer_encrypts_payload(monkeypatch):
    monkeypatch.setattr(settings, "checkpoint_encryption_key", "a" * 32)
    serializer = encrypted_serializer()
    type_name, ciphertext = serializer.dumps_typed({"request": "private research", "budget": 3})
    assert b"private research" not in ciphertext
    assert serializer.loads_typed((type_name, ciphertext)) == {"request": "private research", "budget": 3}


def test_checkpoint_key_is_mandatory(monkeypatch):
    monkeypatch.setattr(settings, "checkpoint_encryption_key", "too-short")
    with pytest.raises(RuntimeError, match="exactly 32"):
        encrypted_serializer()
