"""Medical note data structures for clinical consultation workflow.

This module defines Pydantic models for medical consultation notes, counter-referral
notes, and complete clinical records (expediente clínico). It also provides markdown
formatting functions for generating professional clinical documentation.
"""

from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field


class ConsultationNote(BaseModel):
    """Nota de interconsulta sent from general practitioner to specialist.
    
    This represents the initial consultation request with clinical context and
    specific questions for the specialist to address.
    """
    
    consultation_id: str = Field(default_factory=lambda: str(uuid4()))
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
    ] = Field(description="Medical specialty being consulted")
    patient_context: str = Field(
        description="Relevant clinical context about the patient/case"
    )
    clinical_question: str = Field(
        description="Specific question or concern for the specialist"
    )
    expected_response: str = Field(
        description="What the GP expects the specialist to address"
    )
    urgency_level: Literal["routine", "urgent", "emergency"] = Field(
        default="routine",
        description="Priority level of the consultation"
    )
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "specialty": "cardiology",
                "patient_context": "58-year-old male with type 2 diabetes, hypertension, and dyslipidemia",
                "clinical_question": "Patient reports chest pain on exertion. Should I refer for cardiac evaluation?",
                "expected_response": "Cardiovascular risk assessment and recommendation for further workup",
                "urgency_level": "urgent"
            }
        }


class CounterReferralNote(BaseModel):
    """Nota de contrarreferencia from specialist back to general practitioner.
    
    This represents the specialist's evidence-based response with clinical assessment,
    recommendations, and relevant diagnostic criteria.
    """
    
    consultation_id: str = Field(
        description="ID of the original consultation being responded to"
    )
    specialty: str = Field(description="Medical specialty providing the response")
    clinical_assessment: str = Field(
        description="Detailed clinical evaluation and reasoning"
    )
    evidence_used: List[str] = Field(
        default_factory=list,
        description="Citations to guidelines, studies, or clinical criteria used"
    )
    recommendations: str = Field(
        description="Evidence-based clinical recommendations"
    )
    diagnostic_criteria_met: Optional[Dict[str, bool]] = Field(
        default=None,
        description="Specific diagnostic criteria evaluated (met/not met)"
    )
    additional_info_needed: Optional[List[str]] = Field(
        default=None,
        description="Additional information needed for better assessment"
    )
    evidence_level: Optional[Literal["A", "B", "C", "D"]] = Field(
        default=None,
        description="Evidence level for primary recommendations (A=highest, D=lowest)"
    )
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "consultation_id": "123e4567-e89b-12d3-a456-426614174000",
                "specialty": "cardiology",
                "clinical_assessment": "Based on patient's risk factors and symptoms...",
                "evidence_used": [
                    "ACC/AHA 2019 Primary Prevention Guidelines",
                    "Framingham Risk Score"
                ],
                "recommendations": "Recommend stress test and cardiology referral within 48 hours",
                "diagnostic_criteria_met": {
                    "Typical angina": True,
                    "High cardiovascular risk": True
                },
                "evidence_level": "A"
            }
        }


class ClinicalRecord(BaseModel):
    """Complete clinical record (expediente clínico) with all consultations.
    
    This represents the final integrated clinical record containing the original
    question, all consultation/counter-referral pairs, and the GP's integrated
    response.
    """
    
    case_id: str = Field(default_factory=lambda: str(uuid4()))
    original_question: str = Field(
        description="Original clinical question from user"
    )
    general_practitioner_summary: str = Field(
        description="GP's integrated summary of all specialist consultations"
    )
    consultations: List[Tuple[ConsultationNote, CounterReferralNote]] = Field(
        default_factory=list,
        description="List of consultation/counter-referral pairs"
    )
    integrated_response: str = Field(
        description="Final evidence-based answer integrating all specialist input"
    )
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        """Pydantic configuration."""
        arbitrary_types_allowed = True


# Markdown formatting functions

def format_consultation_note(note: ConsultationNote) -> str:
    """Format consultation note as markdown.
    
    Args:
        note: ConsultationNote instance to format
        
    Returns:
        Markdown formatted consultation note
    """
    urgency_badge = {
        "routine": "🟢 RUTINA",
        "urgent": "🟡 URGENTE",
        "emergency": "🔴 EMERGENCIA"
    }
    
    return f"""### NOTA DE INTERCONSULTA - {note.specialty.upper().replace('_', ' ')}

**ID de Consulta:** `{note.consultation_id}`  
**Urgencia:** {urgency_badge.get(note.urgency_level, note.urgency_level)}  
**Fecha:** {note.timestamp.strftime('%Y-%m-%d %H:%M')}

#### Contexto del Paciente
{note.patient_context}

#### Pregunta Clínica
{note.clinical_question}

#### Respuesta Esperada
{note.expected_response}

---
"""


def format_counter_referral_note(note: CounterReferralNote) -> str:
    """Format counter-referral note as markdown with evidence citations.
    
    Args:
        note: CounterReferralNote instance to format
        
    Returns:
        Markdown formatted counter-referral note with citations
    """
    evidence_badge = {
        "A": "🟢 Nivel A (Alta calidad)",
        "B": "🟡 Nivel B (Moderada calidad)",
        "C": "🟠 Nivel C (Baja calidad)",
        "D": "🔴 Nivel D (Muy baja calidad)"
    }
    
    output = f"""### NOTA DE CONTRARREFERENCIA - {note.specialty.upper().replace('_', ' ')}

**ID de Consulta:** `{note.consultation_id}`  
**Fecha:** {note.timestamp.strftime('%Y-%m-%d %H:%M')}  
"""
    
    if note.evidence_level:
        output += f"**Nivel de Evidencia:** {evidence_badge.get(note.evidence_level, note.evidence_level)}\n"
    
    output += f"""
#### Evaluación Clínica
{note.clinical_assessment}

#### Recomendaciones
{note.recommendations}
"""
    
    if note.diagnostic_criteria_met:
        output += "\n#### Criterios Diagnósticos Evaluados\n"
        for criterion, met in note.diagnostic_criteria_met.items():
            status = "✅" if met else "❌"
            output += f"- {status} {criterion}\n"
    
    if note.additional_info_needed:
        output += "\n#### Información Adicional Requerida\n"
        for info in note.additional_info_needed:
            output += f"- {info}\n"
    
    if note.evidence_used:
        output += "\n#### Referencias y Evidencia Utilizada\n"
        for i, evidence in enumerate(note.evidence_used, 1):
            output += f"{i}. {evidence}\n"
    
    output += "\n---\n"
    return output


def format_clinical_record(record: ClinicalRecord) -> str:
    """Format complete clinical record as markdown expediente clínico.
    
    Args:
        record: ClinicalRecord instance to format
        
    Returns:
        Complete markdown formatted clinical record
    """
    output = f"""# EXPEDIENTE CLÍNICO

**ID de Caso:** `{record.case_id}`  
**Fecha de Generación:** {record.timestamp.strftime('%Y-%m-%d %H:%M')}

---

## PREGUNTA CLÍNICA ORIGINAL

{record.original_question}

---

## NOTA DEL MÉDICO GENERAL

{record.general_practitioner_summary}

---

## INTERCONSULTAS REALIZADAS

"""
    
    for consultation, counter_referral in record.consultations:
        output += format_consultation_note(consultation)
        output += "\n"
        output += format_counter_referral_note(counter_referral)
        output += "\n"
    
    output += f"""---

## RESPUESTA INTEGRADA

{record.integrated_response}

---

*Este expediente clínico fue generado por Clinical Research Crew, un sistema multiagente de apoyo a decisiones clínicas basado en evidencia.*

"""
    
    return output


# Utility functions

def generate_case_id() -> str:
    """Generate a unique case ID for a clinical record.
    
    Returns:
        Unique case ID string
    """
    return str(uuid4())


def create_consultation_note(
    specialty: str,
    patient_context: str,
    clinical_question: str,
    expected_response: str,
    urgency_level: str = "routine"
) -> ConsultationNote:
    """Helper function to create a consultation note.
    
    Args:
        specialty: Medical specialty to consult
        patient_context: Clinical context
        clinical_question: Specific question
        expected_response: What GP expects
        urgency_level: Priority level
        
    Returns:
        ConsultationNote instance
    """
    return ConsultationNote(
        specialty=specialty,
        patient_context=patient_context,
        clinical_question=clinical_question,
        expected_response=expected_response,
        urgency_level=urgency_level
    )
