import importlib.util


def test_rag_pipeline_alias_resolves():
    assert importlib.util.find_spec("rag_pipeline") is not None
    assert importlib.util.find_spec("rag_pipeline.api") is not None


def test_rag_serving_alias_resolves():
    assert importlib.util.find_spec("rag_serving") is not None
    assert importlib.util.find_spec("rag_serving.api") is not None


def test_rag_sync_monitor_alias_resolves():
    assert importlib.util.find_spec("rag_sync_monitor") is not None
    assert importlib.util.find_spec("rag_sync_monitor.scheduler") is not None
