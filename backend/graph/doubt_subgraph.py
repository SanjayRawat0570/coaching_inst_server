"""Doubt subgraph — isolated doubt flow (single node).

Kept as its own compiled graph so the doubt path can be tested / streamed
independently of the master supervisor graph.
"""

from langgraph.graph import StateGraph, END

from graph.state import CoachingState
from agents.doubt_agent import doubt_node


def build_doubt_graph():
    builder = StateGraph(CoachingState)
    builder.add_node("doubt", doubt_node)
    builder.set_entry_point("doubt")
    builder.add_edge("doubt", END)
    return builder.compile()


_DOUBT_GRAPH = None


def get_doubt_graph():
    global _DOUBT_GRAPH
    if _DOUBT_GRAPH is None:
        _DOUBT_GRAPH = build_doubt_graph()
    return _DOUBT_GRAPH
