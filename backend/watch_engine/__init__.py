"""Watch engine — turns analyst free-text into a structured WatchSpec and runs it."""
from .parser import WatchParser
from .registry import WATCH_TEMPLATES

__all__ = ["WATCH_TEMPLATES", "WatchParser"]
