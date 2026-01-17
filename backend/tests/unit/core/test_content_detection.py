import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# --- Module Mocking Support (Crucial for isolated testing) ---
# We mock these BEFORE importing processor to handle top-level imports

if "imdb" not in sys.modules:
    dummy_imdb = types.ModuleType("imdb")

    class _DummyIMDb:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

    dummy_imdb.IMDb = _DummyIMDb
    sys.modules["imdb"] = dummy_imdb

if "rapidfuzz" not in sys.modules:
    dummy_rapidfuzz = types.ModuleType("rapidfuzz")
    dummy_rapidfuzz.fuzz = types.SimpleNamespace(ratio=lambda *_args, **_kwargs: 0)
    sys.modules["rapidfuzz"] = dummy_rapidfuzz

if "qbittorrentapi" not in sys.modules:
    dummy_qbittorrentapi = types.ModuleType("qbittorrentapi")

    class _DummyClient:
        pass

    class _DummyLoginFailed(Exception):
        pass

    dummy_qbittorrentapi.Client = _DummyClient
    dummy_qbittorrentapi.LoginFailed = _DummyLoginFailed
    dummy_qbittorrentapi.exceptions = types.SimpleNamespace(
        APIConnectionError=Exception,
        APIError=Exception,
        NotFound404Error=Exception,
    )
    sys.modules["qbittorrentapi"] = dummy_qbittorrentapi

if "chardet" not in sys.modules:
    dummy_chardet = types.ModuleType("chardet")
    dummy_chardet.detect = lambda *_args, **_kwargs: {"encoding": "utf-8"}
    sys.modules["chardet"] = dummy_chardet

if "rarfile" not in sys.modules:
    dummy_rarfile = types.ModuleType("rarfile")
    dummy_rarfile.UNRAR_TOOL = "unrar"
    dummy_rarfile.RarFile = object
    sys.modules["rarfile"] = dummy_rarfile

# --- Import System Under Test ---
from app.modules.subtitle.core import processor
from app.modules.subtitle.core.processor import (
    ContentType,
    DetectionConfig,
    DetectionSignals,
    decide_content_type,
    determine_content_type_for_path,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


# --- v2.0 Signal Logic Tests ---


class TestDetectionSignals(unittest.TestCase):
    """Test the signal extraction logic in isolation (Pure Logic)"""

    def test_decide_tv_with_high_confidence(self) -> None:
        signals = DetectionSignals(
            has_tv_episode_pattern=True, has_season_folder=True, in_tv_named_folder=True
        )
        result = decide_content_type(signals, DetectionConfig())
        self.assertEqual(result, ContentType.TV)

    def test_decide_movie_with_high_confidence(self) -> None:
        signals = DetectionSignals(
            in_movie_named_folder=True, movie_file_count=1, tv_episode_count=0
        )
        result = decide_content_type(signals, DetectionConfig())
        self.assertEqual(result, ContentType.MOVIE)

    def test_single_file_fallback_is_movie(self) -> None:
        """User requirement: Single video file without TV patterns should be MOVIE"""
        signals = DetectionSignals(is_file=True, has_tv_episode_pattern=False)
        result = decide_content_type(signals, DetectionConfig())
        self.assertEqual(result, ContentType.MOVIE)

    def test_decide_ignored_folder_always_unknown(self) -> None:
        signals = DetectionSignals(has_tv_episode_pattern=True, in_ignored_folder=True)
        result = decide_content_type(signals, DetectionConfig())
        self.assertEqual(result, ContentType.UNKNOWN)


class TestFilenamePatterns(unittest.TestCase):
    """Test filename pattern matching via determine_content_type_for_path"""

    def setUp(self) -> None:
        self.patcher = patch("app.modules.subtitle.core.processor.Path")
        self.MockPath = self.patcher.start()
        self.mock_path_instance = MagicMock()
        self.MockPath.return_value = self.mock_path_instance
        self.mock_path_instance.exists.return_value = True
        self.mock_path_instance.is_file.return_value = True
        self.mock_path_instance.suffix = ".mkv"
        self.mock_path_instance.resolve.return_value = self.mock_path_instance

    def tearDown(self) -> None:
        self.patcher.stop()

    def test_tv_patterns(self) -> None:
        cases = [
            ("Breaking.Bad.S01E01.mkv", "tvshow"),
            ("show.1x01.mp4", "tvshow"),
            ("Show.S01E01-E02.mkv", "tvshow"),
            ("The.Daily.Show.2024.01.17.mkv", "tvshow"),
            ("Naruto - 001.mp4", "tvshow"),
        ]
        for filename, expected in cases:
            self.mock_path_instance.name = filename
            self.mock_path_instance.parts = ["/test", filename]
            self.mock_path_instance.suffix = Path(filename).suffix
            result = determine_content_type_for_path(f"/test/{filename}")
            self.assertEqual(result, expected, f"Failed for {filename}")

    def test_movie_fallback(self) -> None:
        """Single file with no TV pattern -> Movie (per user requirement)"""
        filename = "random_movie.mkv"
        self.mock_path_instance.name = filename
        self.mock_path_instance.parts = ["/", filename]
        self.mock_path_instance.suffix = ".mkv"

        result = determine_content_type_for_path(f"/{filename}")
        self.assertEqual(result, "movie")

    def test_ignored_folder_returns_none(self) -> None:
        filename = "sample.mkv"
        self.mock_path_instance.name = filename
        self.mock_path_instance.parts = ["/Movie", "Sample", filename]
        self.mock_path_instance.suffix = ".mkv"

        result = determine_content_type_for_path(f"/Movie/Sample/{filename}")
        self.assertIsNone(result)


class TestDirectoryScanning(unittest.TestCase):
    """Test scanning a directory for TV vs Movie patterns"""

    def test_directory_with_tv_episodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "Show"
            _touch(root / "My.Show.S01E01.mkv")
            _touch(root / "My.Show.S01E02.mkv")
            _touch(root / "My.Show.S01E03.mkv")

            result = determine_content_type_for_path(str(root))
            self.assertEqual(result, "tvshow")

    def test_directory_with_movies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "Cinema"
            _touch(root / "My.Movie.2020.mkv")
            _touch(root / "Another.Movie.2021.mp4")

            result = determine_content_type_for_path(str(root))
            self.assertEqual(result, "movie")


def test_process_tv_show_file_runs_pipeline_for_pattern(tmp_path: Path) -> None:
    file_path = tmp_path / "My.Show.S01E02.mkv"
    _touch(file_path)

    captured: dict[str, dict[str, str | None]] = {}

    def _fake_run(*_args: object, **kwargs: object) -> bool:
        captured["details"] = kwargs.get("tv_show_details") or {}
        return True

    with patch.object(processor, "_run_pipeline_for_file", _fake_run):
        assert processor.process_tv_show_file(str(file_path)) == 1

    assert captured["details"].get("season") == "01"
    assert captured["details"].get("episode") == "02"


class TestProcessTvShowFile(unittest.TestCase):
    def test_process_file_success(self) -> None:
        mock_path = MagicMock()
        mock_path.resolve.return_value = mock_path
        mock_path.is_file.return_value = True
        mock_path.suffix = ".mkv"
        mock_path.name = "My.Show.S01E02.mkv"

        with patch("app.modules.subtitle.core.processor.Path", return_value=mock_path):
            with patch.object(
                processor,
                "_infer_tv_show_details_for_file",
                return_value=("My Show", "01", "02", None),
            ):
                with patch.object(processor, "_run_pipeline_for_file", return_value=True):
                    result = processor.process_tv_show_file("/test/My.Show.S01E02.mkv")

        self.assertEqual(result, 1)

    def test_process_file_fallback_to_movie_when_no_episode_patterns(self) -> None:
        """Test that files without TV episode patterns fallback to movie processing."""
        mock_path = MagicMock()
        mock_path.resolve.return_value = mock_path
        mock_path.is_file.return_value = True
        mock_path.suffix = ".mkv"
        mock_path.name = "Some.Movie.2024.mkv"
        mock_path.__str__ = MagicMock(return_value="/test/Some.Movie.2024.mkv")

        with patch("app.modules.subtitle.core.processor.Path", return_value=mock_path):
            with patch.object(
                processor,
                "_infer_tv_show_details_for_file",
                return_value=(None, None, None, None),  # No TV details found
            ):
                with patch.object(
                    processor, "_run_pipeline_for_file", return_value=True
                ) as mock_pipeline:
                    result = processor.process_tv_show_file("/test/Some.Movie.2024.mkv")

        # Should fallback to movie processing and return 1 (success)
        self.assertEqual(result, 1)
        mock_pipeline.assert_called_once()


class TestMovieInTvFolderDetection(unittest.TestCase):
    """Test detection of movies incorrectly placed in TV folders."""

    def test_movie_in_tv_folder_without_episode_pattern_detected_as_tv_with_fallback(
        self,
    ) -> None:
        """Movie file in TV folder is detected as TV, but fallback handles it.

        The detection logic intentionally classifies files in TV folders as TV
        to be safe. When the file lacks episode patterns, `process_tv_show_file`
        falls back to movie processing. This test verifies the classification.
        """
        # Signals: in_tv_named_folder=True, but has_tv_episode_pattern=False
        signals = DetectionSignals(
            in_tv_named_folder=True,
            has_tv_episode_pattern=False,
            has_season_folder=False,
            is_file=True,
        )
        result = decide_content_type(signals, DetectionConfig())
        # Still detected as TV (folder wins), but process_tv_show_file will fallback
        self.assertEqual(result, ContentType.TV)

    def test_tv_episode_in_tv_folder_detected_as_tv(self) -> None:
        """TV episode in TV folder should still be detected as TV."""
        signals = DetectionSignals(
            in_tv_named_folder=True,
            has_tv_episode_pattern=True,
            is_file=True,
        )
        result = decide_content_type(signals, DetectionConfig())
        self.assertEqual(result, ContentType.TV)


if __name__ == "__main__":
    unittest.main()
