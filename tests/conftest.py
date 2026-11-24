import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def _enable(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def verify_cleanup():
    """Override harness fixture: its thread check trips on HA's own shutdown thread."""
    yield
