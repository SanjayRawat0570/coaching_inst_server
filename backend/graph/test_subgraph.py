"""Test subgraph — generation + reviewer loop + HITL teacher approval.

Compile with a checkpointer to enable the interrupt/resume HITL flow:

    from langgraph.checkpoint.sqlite import SqliteSaver
    graph = get_test_graph(SqliteSaver.from_conn_string(":memory:"))
    config = {"configurable": {"thread_id": test_id}}
    graph.invoke(initial_state, config)        # pauses before 'hitl'
    graph.update_state(config, {"test_questions": approved_qs, "review_passed": True})
    graph.invoke(None, config)                 # resumes to END
"""

from langgraph.graph import StateGraph, END

from graph.state import CoachingState
from agents.test_generator import test_generator_node
from agents.reviewer_agent import reviewer_node, should_continue
from graph.coaching_graph import hitl_node


def build_test_graph(checkpointer=None):
    builder = StateGraph(CoachingState)
    builder.add_node("test_generator", test_generator_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("hitl", hitl_node)

    builder.set_entry_point("test_generator")
    builder.add_edge("test_generator", "reviewer")
    builder.add_conditional_edges(
        "reviewer",
        should_continue,
        {"approved": "hitl", "regenerate": "test_generator"},
    )
    builder.add_edge("hitl", END)

    kwargs = {}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
        kwargs["interrupt_before"] = ["hitl"]
    return builder.compile(**kwargs)


def get_test_graph(checkpointer=None):
    return build_test_graph(checkpointer)
