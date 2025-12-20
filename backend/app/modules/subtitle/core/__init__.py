# src/core/strategies/__init__.py
"""Makes strategy classes easily importable."""

from .strategies.base import ProcessingContext, ProcessingStrategy
from .strategies.embed_scanner import EmbedScanner
from .strategies.final_selector import FinalSelector
from .strategies.local_scanner import LocalScanner
from .strategies.online_fetcher import OnlineFetcher
from .strategies.pipeline import SubtitlePipeline
from .strategies.standard_checker import StandardFileChecker
from .strategies.synchronizer import Synchronizer
from .strategies.translator import Translator

__all__ = [
    "EmbedScanner",
    "FinalSelector",
    "LocalScanner",
    "OnlineFetcher",
    "ProcessingContext",
    "ProcessingStrategy",
    "StandardFileChecker",
    "SubtitlePipeline",
    "Synchronizer",
    "Translator",
]
