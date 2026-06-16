"""Master LangGraph — supervisor routing across all agent flows.

Routes on state['action_type']:
  doubt     -> doubt_node -> END
  test      -> test_generator -> reviewer (loop up to 3x) -> HITL interrupt -> END
  evaluate  -> evaluator -> { progress ∥ rank ∥ flashcard } -> aggregator -> END
  rank      -> rank_predictor -> END

Post-test fan-out runs the three agents in PARALLEL (per the spec). LangGraph forbids
two concurrent branches writing the same state key without a reducer, so each branch
node below returns only its own DISJOINT delta keys (progress->weakness_update,
rank->air_rank/score, flashcard->side-effects only). The aggregator is the join point.
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
    return {**state, "review_passed": True}


# ── Parallel post-test branches (return DISJOINT keys only) ───────────────────
def progress_branch(state: CoachingState) -> dict:
    out = progress_tracker_node(state)
    return {"weakness_update": out.get("weakness_update")}


def rank_branch(state: CoachingState) -> dict:
    out = rank_predictor_node(state)
    return {"air_rank": out.get("air_rank"), "score": out.get("score")}


def flashcard_branch(state: CoachingState) -> dict:
    flashcard_gen_node(state)  # side effects only (creates flashcards in DB)
    # langgraph requires every node to write at least one channel; use a disjoint
    # key so this parallel branch never collides with progress/rank.
    return {"flashcards_generated": True}


def aggregator_node(state: CoachingState) -> CoachingState:
    """Join point after the parallel branches complete."""
    return state


# Fan-out targets after evaluation. Returning a LIST from a conditional edge is the
# langgraph 0.1.x way to run several nodes in parallel (multiple static add_edge()
# calls from one node are rejected in this version).
POST_TEST_BRANCHES = ["progress", "rank", "flashcard"]


def fan_out_post_test(state: CoachingState) -> list[str]:
    return POST_TEST_BRANCHES


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
    builder.add_node("progress", progress_branch)
    builder.add_node("rank", rank_branch)
    builder.add_node("flashcard", flashcard_branch)
    builder.add_node("aggregator", aggregator_node)
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

    # Evaluate flow: evaluator fans out to 3 PARALLEL agents, then joins at aggregator
    builder.add_conditional_edges("evaluator", fan_out_post_test, POST_TEST_BRANCHES)
    builder.add_edge("progress", "aggregator")
    builder.add_edge("rank", "aggregator")
    builder.add_edge("flashcard", "aggregator")
    builder.add_edge("aggregator", END)

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

    Pass a checkpointer explicitly when you need HITL interrupt/resume or time-travel.
    """
    global _GRAPH
    if checkpointer is not None:
        return build_graph(checkpointer)
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH
