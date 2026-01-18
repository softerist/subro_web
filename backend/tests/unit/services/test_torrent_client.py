# backend/tests/unit/services/test_torrent_client.py
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

if "qbittorrentapi" not in sys.modules:

    class _DummyAPIError(Exception):
        pass

    dummy_exceptions = SimpleNamespace(
        APIError=_DummyAPIError,
        APIConnectionError=_DummyAPIError,
        NotFound404Error=_DummyAPIError,
    )
    sys.modules["qbittorrentapi"] = SimpleNamespace(
        exceptions=dummy_exceptions,
        LoginFailed=_DummyAPIError,
        Client=object,
    )

from app.modules.subtitle.services import torrent_client


def test_get_completed_torrents_requires_login() -> None:
    client = MagicMock()
    client.is_logged_in = False

    result = torrent_client.get_completed_torrents(client)

    assert result == []
    client.torrents_info.assert_not_called()


def test_get_completed_torrents_filters_and_dedupes() -> None:
    client = MagicMock()
    client.is_logged_in = True

    t1 = MagicMock()
    t1.hash = "h1"
    t1.progress = 1.0
    t1.amount_left = 0
    t1.name = "Movie 1"
    t1.save_path = "/downloads/movie1"

    t2 = MagicMock()
    t2.hash = "h2"
    t2.progress = 0.5
    t2.amount_left = 100

    t3 = MagicMock()
    t3.hash = "h1"
    t3.progress = 1.0
    t3.amount_left = 0
    t3.name = "Movie 1 Duplicate"
    t3.save_path = "/downloads/movie1"

    t4 = MagicMock()
    t4.hash = "h3"
    t4.progress = None
    t4.amount_left = 0

    client.torrents_info.return_value = [t1, t2, t3, t4]

    result = torrent_client.get_completed_torrents(client)

    client.torrents_info.assert_called_once_with()
    assert len(result) == 2
    assert t3 in result
    assert t4 in result
    assert t2 not in result
