"""Session Recorder plugin contracts.

Runtime imports stay behind ``factory`` so authoring contracts remain independent
from optional LangChain and Deep Agents packages.
"""

from .contracts import SessionRecorderBlock

__all__ = ["SessionRecorderBlock"]
