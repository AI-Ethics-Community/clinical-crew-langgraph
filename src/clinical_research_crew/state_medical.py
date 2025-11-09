"""State definitions for Clinical Research Crew medical consultation workflow.

This module defines state structures for the multi-agent medical consultation
system, including states for the general practitioner, specialists, and the
overall consultation workflow.
"""

import operator
from typing import Annotated, Any, Dict, List, Literal, Optional

from langchain_core.messages import MessageLikeRepresentation
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

# Import medical note structures
from clinical_research_crew.medical_notes import (
    ConsultationNote,
    CounterReferralNote,
    ClinicalRecord,
)


# ==============================================================================
# Structured Tool Outputs
# ==============================================================================

class ConsultSpecialist(BaseModel):
    """Call this tool to consult a medical specialist.
    
    This tool generates a consultation note (interconsulta) and routes
    the question to the appropriate specialist for expert evaluation.
    """
    
    specialty: Literal[
        "cardiology",
        "pharmacology",
        "neurology",
        "emergency",
        "gynecology",
        "internal_medicine",
        "surgery",
        "nutrition",
        "prevention",
        "epidemiology"
    ] = Field(description="Medical specialty to consult")
    
    patient_context: str = Field(
        description="Relevant clinical context (age, sex, comorbidities, symptoms, labs, etc.)"
    )
    
    clinical_question: str = Field(
        description="Specific, focused clinical question for the specialist"
    )
    
    expected_response: str = Field(
        description="What you expect the specialist to address or evaluate"
    )
    
    urgency_level: Literal["routine", "urgent", "emergency"] = Field(
        default="routine",
        description="Priority level for this consultation"
    )


class ConsultationComplete(BaseModel):
    """Call this tool to indicate that all consultations are complete.
    
    Use this when you have received sufficient specialist input and are
    ready to generate the integrated clinical record.
    """
    
    pass


class DirectAnswer(BaseModel):
    """Call this tool to provide a direct answer without specialist consultation.
    
    Use this when you can confidently answer the clinical question yourself
    based on general medical knowledge without needing specialist input.
    """
    
    answer: str = Field(
        description="Your complete, evidence-based answer to the clinical question"
    )


# ==============================================================================
# Reducer Functions
# ==============================================================================

def override_reducer(current_value, new_value):
    """Reducer that allows overriding values in state."""
    if isinstance(new_value, dict) and new_value.get("type") == "override":
        return new_value.get("value", new_value)
    else:
        return operator.add(current_value, new_value)


def dict_reducer(current_value: Dict, new_value: Dict) -> Dict:
    """Reducer for dictionary fields that merges values."""
    if current_value is None:
        return new_value
    result = current_value.copy()
    result.update(new_value)
    return result


# ==============================================================================
# State Definitions
# ==============================================================================

class AgentInputState(MessagesState):
    """Input state for the clinical consultation system.
    
    This is the entry point state containing only the user's messages.
    """
    pass


class AgentState(MessagesState):
    """Main agent state for the entire clinical consultation workflow.
    
    This state tracks the complete consultation process from initial question
    through specialist consultations to final clinical record generation.
    """
    
    # General Practitioner coordination
    gp_messages: Annotated[List[MessageLikeRepresentation], override_reducer] = []
    
    # Clinical question and context
    original_question: Optional[str] = None
    patient_context: Optional[str] = None
    
    # Consultation workflow
    consultation_notes: Annotated[List[ConsultationNote], operator.add] = []
    specialist_responses: Annotated[Dict[str, CounterReferralNote], dict_reducer] = {}
    
    # Final output
    clinical_record: Optional[ClinicalRecord] = None
    
    # Evidence and notes (for evaluation/debugging)
    raw_evidence: Annotated[List[str], operator.add] = []
    
    # Workflow tracking
    active_specialty: Optional[str] = None
    consultation_iteration: int = 0


class GPState(TypedDict):
    """State for General Practitioner (coordinator) agent.
    
    The GP analyzes questions, determines which specialists to consult,
    and integrates specialist responses into a final clinical assessment.
    """
    
    gp_messages: Annotated[List[MessageLikeRepresentation], override_reducer]
    original_question: str
    patient_context: Optional[str]
    
    # Consultation management
    consultation_notes: Annotated[List[ConsultationNote], operator.add]
    specialist_responses: Dict[str, CounterReferralNote]
    
    # Iteration tracking
    consultation_iteration: int
    max_consultations: int


class SpecialistState(TypedDict):
    """State for individual specialist agents.
    
    Each specialist receives a consultation note, researches using available
    tools (RAG, PubMed, calculators), and provides a counter-referral note.
    """
    
    specialty: Literal[
        "cardiology",
        "pharmacology",
        "neurology",
        "emergency",
        "gynecology",
        "internal_medicine",
        "surgery",
        "nutrition",
        "prevention",
        "epidemiology"
    ]
    
    # Input from GP
    consultation_note: ConsultationNote
    
    # Specialist work
    specialist_messages: Annotated[List[MessageLikeRepresentation], operator.add]
    evidence_gathered: Annotated[List[Dict[str, Any]], operator.add] = []
    reasoning_steps: Annotated[List[str], operator.add] = []
    
    # Output to GP
    counter_referral_note: Optional[CounterReferralNote] = None
    
    # Tool call tracking
    tool_call_iterations: int = 0
    max_tool_calls: int = 10


class SpecialistOutputState(BaseModel):
    """Output state from specialist consultation.
    
    This is what the specialist returns to the general practitioner.
    """
    
    specialty: str
    counter_referral_note: CounterReferralNote
    evidence_gathered: List[Dict[str, Any]] = []


class ClinicalRecordState(TypedDict):
    """State for clinical record generation.
    
    This state is used in the final step to integrate all consultations
    into a comprehensive clinical record (expediente clínico).
    """
    
    original_question: str
    patient_context: Optional[str]
    consultation_notes: List[ConsultationNote]
    specialist_responses: Dict[str, CounterReferralNote]
    clinical_record: Optional[ClinicalRecord]


# ==============================================================================
# Helper Functions
# ==============================================================================

def create_consultation_note_from_tool(
    tool_output: ConsultSpecialist
) -> ConsultationNote:
    """Create a ConsultationNote from ConsultSpecialist tool output.
    
    Args:
        tool_output: Output from ConsultSpecialist tool
        
    Returns:
        Formatted ConsultationNote
    """
    return ConsultationNote(
        specialty=tool_output.specialty,
        patient_context=tool_output.patient_context,
        clinical_question=tool_output.clinical_question,
        expected_response=tool_output.expected_response,
        urgency_level=tool_output.urgency_level,
    )


def get_pending_consultations(state: AgentState) -> List[str]:
    """Get list of specialists that have been consulted but haven't responded yet.
    
    Args:
        state: Current agent state
        
    Returns:
        List of specialty names that are pending response
    """
    consulted_specialties = {note.specialty for note in state.get("consultation_notes", [])}
    responded_specialties = set(state.get("specialist_responses", {}).keys())
    pending = consulted_specialties - responded_specialties
    return list(pending)


def all_consultations_complete(state: AgentState) -> bool:
    """Check if all consultation requests have received responses.
    
    Args:
        state: Current agent state
        
    Returns:
        True if all consultations are complete, False otherwise
    """
    return len(get_pending_consultations(state)) == 0


def get_consultation_for_specialty(
    state: AgentState,
    specialty: str
) -> Optional[ConsultationNote]:
    """Get the consultation note for a specific specialty.
    
    Args:
        state: Current agent state
        specialty: Name of the specialty
        
    Returns:
        ConsultationNote for that specialty, or None if not found
    """
    for note in state.get("consultation_notes", []):
        if note.specialty == specialty:
            return note
    return None
