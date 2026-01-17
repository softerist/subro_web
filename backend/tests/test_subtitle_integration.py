import sys
from pathlib import Path

import pytest

# Ensure backend path is in sys.path
backend_path = Path(__file__).parent.parent
sys.path.append(str(backend_path))

from app.core.config import settings  # noqa: E402

try:
    from app.modules.subtitle.core.di import ServiceContainer
    from app.modules.subtitle.core.processor import _run_pipeline_for_file  # noqa: F401
except ImportError as e:
    pytest.fail(f"Failed to import subtitle module: {e}")


@pytest.fixture
def mock_settings():
    # Mock settings where necessary
    # Since we use app.core.config.settings directly, we might need to patch it
    pass


def test_subtitle_module_import() -> None:
    """Simple smoke test to ensure module can be imported and config is accessible."""
    assert settings.APP_NAME is not None
    # Check if a subtitle specific setting exists (assuming we added one)
    # assert hasattr(settings, 'OMDB_API_KEY')
    # Use getattr to avoid MyPy errors if running checking
    assert getattr(settings, "OMDB_API_KEY", "NotFound") != "NotFound"


def test_service_container_init() -> None:
    """Test that DI container initializes services (mocking deps if needed)."""
    # We might need to mock some environment variables or files if they are checked on init
    try:
        container = ServiceContainer()
        assert container.imdb is not None
        assert container.translator is not None
        # container.shutdown()
    except Exception as e:
        pytest.fail(f"ServiceContainer init failed: {e}")
