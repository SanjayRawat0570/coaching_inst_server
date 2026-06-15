"""Shared LangGraph state passed between every agent node."""

from typing import TypedDict, List, Optional, Literal


class CoachingState(TypedDict):
    student_id:            str
    institute_id:          str
    action_type:           Literal["doubt", "test", "evaluate", "progress", "rank"]
    input_text:            Optional[str]
    input_image:           Optional[str]       # base64
    subject:               Optional[str]
    student_level:         Optional[str]       # beginner | intermediate | advanced
    conversation_history:  List[dict]          # working memory [{role, content}]
    current_topic:         Optional[str]
    rag_context:           Optional[str]
    rag_sources:           Optional[List[str]]
    rag_confidence:        Optional[float]
    search_queries:        Optional[List[str]]
    agent_output:          Optional[str]
    test_questions:        Optional[List[dict]]
    test_id:               Optional[str]
    evaluation_result:     Optional[dict]
    weakness_update:       Optional[dict]
    air_rank:              Optional[str]
    score:                 Optional[float]
    review_passed:         Optional[bool]
    review_feedback:       Optional[str]
    iteration_count:       int
    stream_tokens:         Optional[bool]
    error:                 Optional[str]
