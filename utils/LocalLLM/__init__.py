"""
LocalLMM: Local LLM Inference Framework

Simple usage:
    import LocalLMM
    llm = LocalLMM()
    llm.run()
    response = llm.trigger_inference("Your prompt here")
"""

from utils.LocalLLM.core.application import LocalLMM
from utils.LocalLLM.utils.logger import LoggerWrapper, NoOpLogger

__all__ = ["LocalLMM", "LoggerWrapper", "NoOpLogger"]
__version__ = "0.1.0"
