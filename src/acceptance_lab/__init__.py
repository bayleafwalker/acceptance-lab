"""Acceptance Lab: executable acceptance records for agent systems."""

from acceptance_lab.adapters import (
    TraceAdapterError,
    adapt_candidate_from_trace,
    adapt_trace_to_candidate,
    candidate_from_trace,
)

__all__ = [
    "__version__",
    "TraceAdapterError",
    "candidate_from_trace",
    "adapt_trace_to_candidate",
    "adapt_candidate_from_trace",
]
__version__ = "0.1.0"
