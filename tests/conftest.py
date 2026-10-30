import pytest


@pytest.fixture(scope="session", autouse=True)
def _close_ai_model():
    """Close the shared MediaPipe model before Python shuts down (it complains noisily otherwise)."""
    yield
    from doppleganger import segment
    if segment._instance is not None:
        segment._instance.close()
        segment._instance = None
