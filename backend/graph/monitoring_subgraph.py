"""Monitoring subgraph — at-risk detection + parent reporting.

Used by scheduled jobs to run a single student through the monitoring path. The
heavy "for ALL students" loops live in the agents' run_nightly() / run_weekly().
"""

from langgraph.graph import StateGraph, END

from graph.state import CoachingState
from agents.at_risk_agent import at_risk_node
from agents.parent_report_agent import parent_report_node


def build_monitoring_graph():
    builder = StateGraph(CoachingState)
    builder.add_node("at_risk", at_risk_node)
    builder.add_node("parent_report", parent_report_node)

    builder.set_entry_point("at_risk")
    builder.add_edge("at_risk", "parent_report")
    builder.add_edge("parent_report", END)
    return builder.compile()


_MONITORING_GRAPH = None


def get_monitoring_graph():
    global _MONITORING_GRAPH
    if _MONITORING_GRAPH is None:
        _MONITORING_GRAPH = build_monitoring_graph()
    return _MONITORING_GRAPH
