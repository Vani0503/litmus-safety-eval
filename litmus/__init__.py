"""Litmus - an AI safety & ethics evaluation harness (grader + judge validation + red-team)."""

from .rubric import DIMENSIONS, allowed_scores
from .judge import (
    OpenAIJudge, AnthropicJudge, MockJudgeA, MockJudgeB,
    build_messages, parse_judgement,
)
from .validate import run_validation, print_report, load_golden
from .grader import grade_response
from .redteam import run_redteam, print_product_report
from .redteam_prompts import REDTEAM_PROMPTS, select_prompts, SCOPES
from .target import HTTPTarget, OpenAICompatTarget, CallableTarget, ManualFileTarget
from . import metrics

__all__ = [
    "DIMENSIONS", "allowed_scores",
    "OpenAIJudge", "AnthropicJudge", "MockJudgeA", "MockJudgeB",
    "build_messages", "parse_judgement",
    "run_validation", "print_report", "load_golden",
    "grade_response", "run_redteam", "print_product_report",
    "REDTEAM_PROMPTS", "select_prompts", "SCOPES",
    "HTTPTarget", "OpenAICompatTarget", "CallableTarget", "ManualFileTarget",
    "metrics",
]
__version__ = "0.2.0"
