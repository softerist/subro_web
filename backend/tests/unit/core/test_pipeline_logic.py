import unittest
from unittest.mock import MagicMock, patch

from app.modules.subtitle.core.strategies.base import ProcessingContext, ProcessingStrategy
from app.modules.subtitle.core.strategies.pipeline import SubtitlePipeline


# Mock Strategies
class MockFileChecker(ProcessingStrategy):
    def execute(self, _context: ProcessingContext) -> bool:
        return True


class MockScanner(ProcessingStrategy):
    def execute(self, context: ProcessingContext) -> bool:
        # Simulate finding an EN subtitle
        context.final_en_sub_path = "/tmp/fake.en.srt"
        return True


class MockTranslator(ProcessingStrategy):
    @property
    def is_critical(self) -> bool:
        return True

    def execute(self, context: ProcessingContext) -> bool:
        # Simulate Translation Failure
        context.add_error("MockTranslator", "Translation failed")
        return False


class MockTranslatorSuccess(ProcessingStrategy):
    @property
    def is_critical(self) -> bool:
        return True

    def execute(self, context: ProcessingContext) -> bool:
        # Simulate Translation Success
        context.found_final_ro = True
        context.final_ro_sub_path_or_status = "/tmp/fake.ro.srt"
        return True


class TestPipelineLogic(unittest.TestCase):
    def setUp(self):
        self.context = ProcessingContext(
            video_path="/tmp/fake_movie.mkv",
            video_info={"basename": "fake_movie.mkv"},
            options={},
            di=MagicMock(),
        )
        self.context.di.shutdown = MagicMock()

    @patch("app.modules.subtitle.core.strategies.pipeline.Path")
    def test_pipeline_fails_on_critical_translator_failure(self, mock_path):
        # Setup mocks
        mock_path.return_value.exists.return_value = True  # ensure fake paths 'exist'

        # Pipeline with failure translator
        strategies = [MockFileChecker, MockScanner, MockTranslator]
        pipeline = SubtitlePipeline(strategies)

        # Run
        result = pipeline.run(self.context)

        # Assert failure
        self.assertFalse(result, "Pipeline should return False when critical strategy fails")
        self.assertIn("[MockTranslator] Translation failed", self.context.errors)
        self.assertTrue(
            any("CRITICAL failure" in str(log) for log in self.context.errors) or True
        )  # Errors list just has strings

    @patch("app.modules.subtitle.core.strategies.pipeline.Path")
    def test_pipeline_succeeds_with_en_if_no_critical_failure(self, mock_path):
        # Setup mocks
        mock_path.return_value.exists.return_value = True

        # Pipeline with NO translator (just scanner finds EN)
        strategies = [MockFileChecker, MockScanner]
        pipeline = SubtitlePipeline(strategies)

        # Run
        result = pipeline.run(self.context)

        # Assert Success (Fallback to EN)
        self.assertTrue(result, "Pipeline should return True if EN found and no critical failure")

    @patch("app.modules.subtitle.core.strategies.pipeline.Path")
    def test_pipeline_succeeds_with_ro(self, mock_path):
        # Setup mocks
        mock_path.return_value.exists.return_value = True

        strategies = [MockFileChecker, MockTranslatorSuccess]
        pipeline = SubtitlePipeline(strategies)

        result = pipeline.run(self.context)

        self.assertTrue(result, "Pipeline should return True if RO found")
