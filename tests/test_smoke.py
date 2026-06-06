from tests.conftest import collect_events, event_types


def test_pytest_runs():
    assert True


def test_helpers_importable():
    assert callable(collect_events)
    assert callable(event_types)
