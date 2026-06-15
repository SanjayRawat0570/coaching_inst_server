"""Master LangGraph — supervisor routing across all agent flows.

Routes on state['action_type']:
  doubt     -> doubt_node -> END
  test      -> test_generator -> reviewer (loop up to 3x) -> HITL interrupt -> END
  evaluate  -> evaluator -> progress -> rank -> flashcard -> END
  rank      -> rank_predictor -> END

Note on the post-test fan-out: the spec describes these as parallel edges. LangGraph
parallel branches need per-key reducers to avoid concurrent-write conflicts (every
node here returns the full state dict). To stay correct out of the box they run
sequentially — functionally identical. Switch to fan-out + reducers later if latency
matters.
"""

from langgraph.graph import StateGraph, END

from graph.state import CoachingState
from agents.doubt_agent import doubt_node
from agents.test_generator import test_generator_node
from agents.reviewer_agent import reviewer_node, should_continue
from agents.answer_evaluator import evaluator_node
from agents.progress_tracker import progress_tracker_node
from agents.rank_predictor import rank_predictor_node
from agents.flashcard_agent import flashcard_gen_node


def hitl_node(state: CoachingState) -> CoachingState:
    """Human-in-the-loop checkpoint — teacher approves/edits the test.

    The graph is compiled with interrupt_before=['hitl'], so execution pauses here.
    The teacher's decision is supplied when the run is resumed (update_state):
      {"approved": bool, "edited_questions": [...]}
    """
    decision = state.get("review_feedback")  # placeholder; real decision via resume
    # When resumed, the caller writes 'test_questions' / approval into state directly.
    return {**state, "review_passed": True}


def route_action(state: CoachingState) -> str:
    return state.get("action_type", "doubt")


def build_graph(checkpointer=None):
    """Build and compile the master coaching graph."""
    builder = StateGraph(CoachingState)

    builder.add_node("doubt", doubt_node)
    builder.add_node("test_generator", test_generator_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("hitl", hitl_node)
    builder.add_node("evaluator", evaluator_node)
    builder.add_node("progress", progress_tracker_node)
    builder.add_node("rank", rank_predictor_node)
    builder.add_node("flashcard", flashcard_gen_node)
    builder.add_node("rank_solo", rank_predictor_node)

    builder.set_conditional_entry_point(
        route_action,
        {
            "doubt": "doubt",
            "test": "test_generator",
            "evaluate": "evaluator",
            "rank": "rank_solo",
        },
    )

    # Doubt flow
    builder.add_edge("doubt", END)

    # Test flow: generate -> review -> (loop | approve) -> HITL -> END
    builder.add_edge("test_generator", "reviewer")
    builder.add_conditional_edges(
        "reviewer",
        should_continue,
        {"approved": "hitl", "regenerate": "test_generator"},
    )
    builder.add_edge("hitl", END)

    # Evaluate flow: evaluator -> progress -> rank -> flashcard -> END
    builder.add_edge("evaluator", "progress")
    builder.add_edge("progress", "rank")
    builder.add_edge("rank", "flashcard")
    builder.add_edge("flashcard", END)

    # Standalone rank
    builder.add_edge("rank_solo", END)

    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
        compile_kwargs["interrupt_before"] = ["hitl"]

    return builder.compile(**compile_kwargs)


_GRAPH = None


def get_graph(checkpointer=None):
    """Cached master graph (no checkpointer) for stateless calls like doubts.

    Pass a checkpointer explicitly when you need HITL interrupt/resume for tests.
    """
    global _GRAPH
    if checkpointer is not None:
        return build_graph(checkpointer)
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH
