"""
Agent Tracing Module

Provides tracing and observability for agent operations via Opik.
"""

from .opik import AgentTracer, trace_feature, get_tracer, DummySpan

__all__ = ["AgentTracer", "trace_feature", "get_tracer", "DummySpan"]
