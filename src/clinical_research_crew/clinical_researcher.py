"""Main LangGraph implementation for the Clinical Research Crew agent.

This module implements a multi-agent medical consultation system that simulates 
the traditional medical interconsultation workflow (interconsulta/contrarreferencia).

Architecture:
- General Practitioner (GP): Coordinates consultations and integrates responses
- 10 Medical Specialists: Domain experts that respond to consultations
- RAG System: Specialty-specific knowledge bases
- Clinical Tools: PubMed search, calculators, diagnostic criteria

Workflow:
1. User (physician) asks clinical question
2. GP analyzes and determines if specialist consultation needed
3. GP generates consultation notes (interconsultas) for specialists
4. Specialists research using RAG + PubMed + clinical tools
5. Specialists respond with counter-referral notes (contrarreferencias)
6. GP integrates all responses into clinical record (expediente clínico)
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    filter_messages,
    get_buffer_string,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from clinical_research_crew.configuration import Configuration
from clinical_research_crew.medical_notes import (
    ClinicalRecord,
    ConsultationNote,
    CounterReferralNote,
    format_clinical_record,
)
from clinical_research_crew.medical_tools import get_tools_for_specialty
from clinical_research_crew.prompts_medical import (
    clinical_record_generation_prompt,
    general_practitioner_system_prompt,
    get_specialty_prompt,
)
from clinical_research_crew.state_medical import (
    AgentState,
    ConsultSpecialist,
    ConsultationComplete,
    DirectAnswer,
    GPState,
    SpecialistOutputState,
    SpecialistState,
    all_consultations_complete,
    create_consultation_note_from_tool,
    get_consultation_for_specialty,
    get_pending_consultations,
)
from clinical_research_crew.utils import (
    get_api_key_for_model,
    get_today_str,
    is_token_limit_exceeded,
    think_tool,
)

# Initialize a configurable model for all agents
configurable_model = init_chat_model(
    configurable_fields=("model", "max_tokens", "api_key", "temperature"),
)


# ============================================================================
# GENERAL PRACTITIONER (COORDINATOR AGENT)
# ============================================================================

async def general_practitioner(
    state: GPState, config: RunnableConfig
) -> Command[Literal["gp_tools"]]:
    """General Practitioner agent that coordinates medical consultations.
    
    The GP acts as the coordinator, analyzing clinical questions from users
    (practicing physicians) and determining the appropriate course of action:
    1. Answer directly if the question is straightforward
    2. Consult one or more specialists for complex cases
    3. Request additional patient information if needed
    
    Args:
        state: Current GP state with messages and consultation context
        config: Runtime configuration with model settings
        
    Returns:
        Command to proceed to gp_tools for tool execution
    """
    # Step 1: Configure the GP model
    configurable = Configuration.from_runnable_config(config)
    gp_model_config = {
        "model": configurable.general_practitioner_model,
        "max_tokens": configurable.research_model_max_tokens,
        "api_key": get_api_key_for_model(
            configurable.general_practitioner_model, config
        ),
        "temperature": 0.2,  # Moderate temperature for clinical reasoning
        "tags": ["langsmith:nostream"],
    }
    
    # Available tools: consult specialists, complete consultation, answer directly
    gp_tools = [ConsultSpecialist, ConsultationComplete, DirectAnswer, think_tool]
    
    # Configure model with tools and retry logic
    gp_model = (
        configurable_model
        .bind_tools(gp_tools)
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        .with_config(gp_model_config)
    )
    
    # Step 2: Prepare system prompt with clinical context
    gp_system_message = general_practitioner_system_prompt.format(
        date=get_today_str(),
        available_specialties=", ".join(configurable.available_specialties),
        max_specialists=configurable.max_specialists_per_consultation,
    )
    
    # Step 3: Build conversation with pending consultations context
    gp_messages = state.get("gp_messages", [])
    
    # Add context about pending consultations if any
    pending_consultations = get_pending_consultations(state)
    if pending_consultations:
        context_message = (
            f"Consultas pendientes de respuesta: "
            f"{', '.join(pending_consultations)}\n\n"
            f"Una vez que recibas todas las respuestas de los especialistas, "
            f"usa la herramienta ConsultationComplete para finalizar."
        )
        gp_messages.append(HumanMessage(content=context_message))
    
    # Step 4: Generate GP response
    messages = [SystemMessage(content=gp_system_message)] + gp_messages
    response = await gp_model.ainvoke(messages)
    
    # Step 5: Update state and proceed to tool execution
    return Command(
        goto="gp_tools",
        update={
            "gp_messages": [response],
            "consultation_iterations": state.get("consultation_iterations", 0) + 1,
        },
    )


async def gp_tools(
    state: GPState, config: RunnableConfig
) -> Command[Literal["general_practitioner", "clinical_record_generation", "__end__"]]:
    """Execute tools called by the General Practitioner.
    
    Handles:
    1. think_tool - Clinical reasoning reflection
    2. ConsultSpecialist - Delegate to specialist agents
    3. DirectAnswer - Answer without specialist consultation
    4. ConsultationComplete - All specialist responses received
    
    Args:
        state: Current GP state with messages and consultation context
        config: Runtime configuration with consultation limits
        
    Returns:
        Command to continue GP loop, generate record, or end
    """
    # Step 1: Extract current state and check exit conditions
    configurable = Configuration.from_runnable_config(config)
    gp_messages = state.get("gp_messages", [])
    consultation_iterations = state.get("consultation_iterations", 0)
    most_recent_message = gp_messages[-1]
    
    # Define exit criteria
    exceeded_iterations = (
        consultation_iterations > configurable.max_researcher_iterations
    )
    no_tool_calls = not most_recent_message.tool_calls
    
    # Check for completion signals
    consultation_complete = any(
        tool_call["name"] == "ConsultationComplete"
        for tool_call in most_recent_message.tool_calls
    )
    
    direct_answer = any(
        tool_call["name"] == "DirectAnswer"
        for tool_call in most_recent_message.tool_calls
    )
    
    # Exit conditions
    if exceeded_iterations or no_tool_calls:
        # Force generation of clinical record
        return Command(goto="clinical_record_generation")
    
    if consultation_complete:
        # All consultations complete, generate final record
        return Command(goto="clinical_record_generation")
    
    if direct_answer:
        # GP provided direct answer, end without specialist consultation
        direct_answer_call = next(
            tool_call
            for tool_call in most_recent_message.tool_calls
            if tool_call["name"] == "DirectAnswer"
        )
        answer_content = direct_answer_call["args"]["answer"]
        
        return Command(
            goto=END,
            update={
                "messages": [AIMessage(content=answer_content)],
                "final_response": answer_content,
            },
        )
    
    # Step 2: Process tool calls
    all_tool_messages = []
    update_payload = {"gp_messages": []}
    
    # Handle think_tool calls (clinical reasoning)
    think_tool_calls = [
        tool_call
        for tool_call in most_recent_message.tool_calls
        if tool_call["name"] == "think_tool"
    ]
    
    for tool_call in think_tool_calls:
        reflection_content = tool_call["args"]["reflection"]
        all_tool_messages.append(
            ToolMessage(
                content=f"Razonamiento clínico registrado: {reflection_content}",
                name="think_tool",
                tool_call_id=tool_call["id"],
            )
        )
    
    # Handle ConsultSpecialist calls (delegate to specialists)
    consult_specialist_calls = [
        tool_call
        for tool_call in most_recent_message.tool_calls
        if tool_call["name"] == "ConsultSpecialist"
    ]
    
    if consult_specialist_calls:
        try:
            # Limit concurrent specialist consultations
            allowed_consult_calls = consult_specialist_calls[
                : configurable.max_concurrent_research_units
            ]
            overflow_consult_calls = consult_specialist_calls[
                configurable.max_concurrent_research_units :
            ]
            
            # Execute specialist consultations in parallel
            specialist_tasks = [
                specialist_subgraph.ainvoke(
                    {
                        "specialty": tool_call["args"]["specialty"],
                        "consultation_note": create_consultation_note_from_tool(
                            tool_call["args"]
                        ),
                        "specialist_messages": [],
                    },
                    config,
                )
                for tool_call in allowed_consult_calls
            ]
            
            specialist_results = await asyncio.gather(*specialist_tasks)
            
            # Create tool messages with specialist responses
            for result, tool_call in zip(specialist_results, allowed_consult_calls):
                counter_referral = result.get("counter_referral_note")
                if counter_referral:
                    formatted_response = f"""
CONTRARREFERENCIA - {counter_referral.specialty.upper()}

Evaluación Clínica:
{counter_referral.clinical_assessment}

Recomendaciones:
{counter_referral.recommendations}

Evidencia Utilizada:
{chr(10).join(f'- {evidence}' for evidence in counter_referral.evidence_used)}

Criterios Diagnósticos:
{counter_referral.diagnostic_criteria_met}

Información Adicional Necesaria:
{counter_referral.additional_info_needed or 'Ninguna'}
"""
                    all_tool_messages.append(
                        ToolMessage(
                            content=formatted_response,
                            name=tool_call["name"],
                            tool_call_id=tool_call["id"],
                        )
                    )
                    
                    # Update specialist_responses in state
                    specialty = tool_call["args"]["specialty"]
                    if "specialist_responses" not in update_payload:
                        update_payload["specialist_responses"] = {}
                    update_payload["specialist_responses"][specialty] = counter_referral
                else:
                    all_tool_messages.append(
                        ToolMessage(
                            content="Error: No se pudo generar la contrarreferencia",
                            name=tool_call["name"],
                            tool_call_id=tool_call["id"],
                        )
                    )
            
            # Handle overflow consultation calls
            for overflow_call in overflow_consult_calls:
                all_tool_messages.append(
                    ToolMessage(
                        content=f"Error: No se ejecutó esta consulta porque se excedió el límite de {configurable.max_concurrent_research_units} consultas concurrentes.",
                        name="ConsultSpecialist",
                        tool_call_id=overflow_call["id"],
                    )
                )
            
        except Exception as e:
            # Handle consultation execution errors
            return Command(
                goto="clinical_record_generation",
                update={"error": str(e)},
            )
    
    # Step 3: Return command with all tool results
    update_payload["gp_messages"] = all_tool_messages
    return Command(goto="general_practitioner", update=update_payload)


# ============================================================================
# SPECIALIST AGENTS
# ============================================================================

async def specialist_agent(
    state: SpecialistState, config: RunnableConfig
) -> Command[Literal["specialist_tools"]]:
    """Individual specialist agent that responds to medical consultations.
    
    Each specialist:
    1. Reviews the consultation note from the GP
    2. Queries their specialty-specific knowledge base (RAG)
    3. Searches medical literature (PubMed) if needed
    4. Uses clinical calculators and diagnostic criteria
    5. Generates evidence-based counter-referral note
    
    Args:
        state: Current specialist state with consultation and messages
        config: Runtime configuration with model settings
        
    Returns:
        Command to proceed to specialist_tools for tool execution
    """
    # Step 1: Configure the specialist model
    configurable = Configuration.from_runnable_config(config)
    specialty = state["specialty"]
    consultation_note = state["consultation_note"]
    
    specialist_model_config = {
        "model": configurable.specialist_model,
        "max_tokens": configurable.research_model_max_tokens,
        "api_key": get_api_key_for_model(configurable.specialist_model, config),
        "temperature": configurable.specialist_temperature,
        "tags": ["langsmith:nostream"],
    }
    
    # Get specialty-specific tools
    specialist_tools = get_tools_for_specialty(
        specialty,
        enable_pubmed=configurable.enable_pubmed_search,
        enable_calculators=configurable.enable_clinical_calculators,
    )
    
    # Add think_tool for clinical reasoning
    specialist_tools.append(think_tool)
    
    # Configure model with tools
    specialist_model = (
        configurable_model
        .bind_tools(specialist_tools)
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        .with_config(specialist_model_config)
    )
    
    # Step 2: Prepare system prompt with specialty context
    specialist_system_message = get_specialty_prompt(specialty).format(
        date=get_today_str(),
        consultation_note=consultation_note.model_dump_json(indent=2),
        min_evidence_level=configurable.min_evidence_level,
        require_citations=configurable.require_citations,
    )
    
    # Step 3: Build conversation
    specialist_messages = state.get("specialist_messages", [])
    messages = [SystemMessage(content=specialist_system_message)] + specialist_messages
    
    # Step 4: Generate specialist response
    response = await specialist_model.ainvoke(messages)
    
    # Step 5: Update state and proceed to tool execution
    return Command(
        goto="specialist_tools",
        update={
            "specialist_messages": [response],
            "tool_call_iterations": state.get("tool_call_iterations", 0) + 1,
        },
    )


# Tool execution helper
async def execute_tool_safely(tool, args, config):
    """Safely execute a tool with error handling."""
    try:
        return await tool.ainvoke(args, config)
    except Exception as e:
        return f"Error ejecutando herramienta: {str(e)}"


async def specialist_tools(
    state: SpecialistState, config: RunnableConfig
) -> Command[Literal["specialist_agent", "generate_counter_referral"]]:
    """Execute tools called by specialist agents.
    
    Handles:
    1. think_tool - Clinical reasoning
    2. rag_query_specialty_knowledge - Query knowledge base
    3. pubmed_search - Search medical literature
    4. Clinical calculators (GFR, BMI, CHADS2-VASc, etc.)
    5. lookup_diagnostic_criteria - Retrieve diagnostic criteria
    
    Args:
        state: Current specialist state with messages and iteration count
        config: Runtime configuration with tool limits
        
    Returns:
        Command to continue specialist loop or generate counter-referral
    """
    # Step 1: Extract current state and check exit conditions
    configurable = Configuration.from_runnable_config(config)
    specialty = state["specialty"]
    specialist_messages = state.get("specialist_messages", [])
    most_recent_message = specialist_messages[-1]
    
    # Early exit if no tool calls
    if not most_recent_message.tool_calls:
        return Command(goto="generate_counter_referral")
    
    # Step 2: Get specialty-specific tools
    specialist_tools = get_tools_for_specialty(
        specialty,
        enable_pubmed=configurable.enable_pubmed_search,
        enable_calculators=configurable.enable_clinical_calculators,
    )
    specialist_tools.append(think_tool)
    
    tools_by_name = {
        tool.name if hasattr(tool, "name") else tool.get("name", "tool"): tool
        for tool in specialist_tools
    }
    
    # Step 3: Execute all tool calls in parallel
    tool_calls = most_recent_message.tool_calls
    tool_execution_tasks = [
        execute_tool_safely(tools_by_name.get(tool_call["name"]), tool_call["args"], config)
        for tool_call in tool_calls
    ]
    observations = await asyncio.gather(*tool_execution_tasks)
    
    # Create tool messages from execution results
    tool_outputs = [
        ToolMessage(
            content=str(observation),
            name=tool_call["name"],
            tool_call_id=tool_call["id"],
        )
        for observation, tool_call in zip(observations, tool_calls)
    ]
    
    # Step 4: Check exit conditions
    exceeded_iterations = (
        state.get("tool_call_iterations", 0) >= configurable.max_react_tool_calls
    )
    
    if exceeded_iterations:
        # End research and generate counter-referral
        return Command(
            goto="generate_counter_referral",
            update={"specialist_messages": tool_outputs},
        )
    
    # Continue specialist loop with tool results
    return Command(
        goto="specialist_agent", update={"specialist_messages": tool_outputs}
    )


async def generate_counter_referral(
    state: SpecialistState, config: RunnableConfig
) -> Dict:
    """Generate counter-referral note (contrarreferencia) from specialist findings.
    
    Synthesizes all the specialist's research, tool outputs, and clinical reasoning
    into a structured counter-referral note with evidence citations.
    
    Args:
        state: Current specialist state with accumulated messages
        config: Runtime configuration with model settings
        
    Returns:
        Dictionary containing the counter-referral note
    """
    # Step 1: Configure the synthesis model
    configurable = Configuration.from_runnable_config(config)
    synthesis_model = configurable_model.with_config(
        {
            "model": configurable.specialist_model,
            "max_tokens": configurable.compression_model_max_tokens,
            "api_key": get_api_key_for_model(configurable.specialist_model, config),
            "temperature": 0.1,  # Low temperature for precise synthesis
            "tags": ["langsmith:nostream"],
        }
    )
    
    # Step 2: Extract consultation context and specialist findings
    specialty = state["specialty"]
    consultation_note = state["consultation_note"]
    specialist_messages = state.get("specialist_messages", [])
    
    # Build synthesis prompt
    synthesis_prompt = f"""
Genera una contrarreferencia médica (counter-referral note) basada en la siguiente información:

NOTA DE INTERCONSULTA RECIBIDA:
{consultation_note.model_dump_json(indent=2)}

TU INVESTIGACIÓN Y ANÁLISIS:
{get_buffer_string(filter_messages(specialist_messages, include_types=["tool", "ai"]))}

INSTRUCCIONES:
1. Proporciona una evaluación clínica clara y concisa
2. Genera recomendaciones específicas basadas en evidencia
3. Lista TODAS las fuentes de evidencia que utilizaste (guidelines, estudios, criterios diagnósticos)
4. Especifica qué criterios diagnósticos se cumplen o no se cumplen
5. Indica si se necesita información adicional del paciente
6. Nivel de evidencia requerido: {configurable.min_evidence_level}
7. Sé preciso, profesional y orientado a la acción clínica

Responde en formato JSON con los siguientes campos:
{{
    "specialty": "{specialty}",
    "consultation_id": "{consultation_note.consultation_id}",
    "clinical_assessment": "Tu evaluación clínica detallada",
    "recommendations": "Tus recomendaciones específicas",
    "evidence_used": ["Lista", "de", "fuentes", "de", "evidencia"],
    "diagnostic_criteria_met": {{"criterio": true/false}},
    "additional_info_needed": ["Info", "adicional"] o null,
    "timestamp": "{datetime.now().isoformat()}"
}}
"""
    
    # Step 3: Generate counter-referral with retry logic
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            response = await synthesis_model.ainvoke([HumanMessage(content=synthesis_prompt)])
            
            # Parse JSON response into CounterReferralNote
            import json
            counter_referral_data = json.loads(response.content)
            counter_referral = CounterReferralNote(**counter_referral_data)
            
            return {"counter_referral_note": counter_referral}
            
        except Exception as e:
            if attempt == max_attempts - 1:
                # Last attempt failed, return error
                return {
                    "counter_referral_note": CounterReferralNote(
                        specialty=specialty,
                        consultation_id=consultation_note.consultation_id,
                        clinical_assessment=f"Error al generar contrarreferencia: {str(e)}",
                        recommendations="No se pudieron generar recomendaciones",
                        evidence_used=["Error en síntesis"],
                        diagnostic_criteria_met={},
                        additional_info_needed=None,
                        timestamp=datetime.now(),
                    )
                }
            continue


# ============================================================================
# SPECIALIST SUBGRAPH
# ============================================================================

# Build specialist subgraph (used by GP to consult each specialty)
specialist_builder = StateGraph(
    SpecialistState, output=SpecialistOutputState, config_schema=Configuration
)

specialist_builder.add_node("specialist_agent", specialist_agent)
specialist_builder.add_node("specialist_tools", specialist_tools)
specialist_builder.add_node("generate_counter_referral", generate_counter_referral)

specialist_builder.add_edge(START, "specialist_agent")
specialist_builder.add_edge("generate_counter_referral", END)

specialist_subgraph = specialist_builder.compile()


# ============================================================================
# CLINICAL RECORD GENERATION
# ============================================================================

async def clinical_record_generation(
    state: AgentState, config: RunnableConfig
) -> Dict:
    """Generate final clinical record (expediente clínico) integrating all consultations.
    
    This function:
    1. Collects all consultation/counter-referral pairs
    2. Generates an integrated clinical assessment
    3. Formats the complete clinical record in Spanish markdown
    4. Returns the final response to the user
    
    Args:
        state: Agent state containing all consultations and responses
        config: Runtime configuration with model settings
        
    Returns:
        Dictionary containing the final clinical record and response
    """
    # Step 1: Extract all consultations and specialist responses
    consultation_notes = state.get("consultation_notes", [])
    specialist_responses = state.get("specialist_responses", {})
    
    # Build consultation pairs
    consultations = []
    for consultation_note in consultation_notes:
        specialty = consultation_note.specialty
        counter_referral = specialist_responses.get(specialty)
        if counter_referral:
            consultations.append((consultation_note, counter_referral))
    
    # Step 2: Generate integrated summary with LLM
    configurable = Configuration.from_runnable_config(config)
    integration_model = configurable_model.with_config(
        {
            "model": configurable.general_practitioner_model,
            "max_tokens": configurable.final_report_model_max_tokens,
            "api_key": get_api_key_for_model(
                configurable.general_practitioner_model, config
            ),
            "temperature": 0.2,
            "tags": ["langsmith:nostream"],
        }
    )
    
    integration_prompt = clinical_record_generation_prompt.format(
        original_question=state.get("messages", [{}])[0].content if state.get("messages") else "No especificada",
        consultations="\n\n".join([
            f"ESPECIALIDAD: {c.specialty}\n"
            f"PREGUNTA: {c.clinical_question}\n"
            f"EVALUACIÓN: {cr.clinical_assessment}\n"
            f"RECOMENDACIONES: {cr.recommendations}\n"
            f"EVIDENCIA: {', '.join(cr.evidence_used)}"
            for c, cr in consultations
        ]),
        date=get_today_str(),
    )
    
    integrated_response = await integration_model.ainvoke([
        HumanMessage(content=integration_prompt)
    ])
    
    # Step 3: Create ClinicalRecord object
    clinical_record = ClinicalRecord(
        case_id=str(uuid.uuid4())[:8],
        original_question=state.get("messages", [{}])[0].content if state.get("messages") else "No especificada",
        general_practitioner_summary=integrated_response.content,
        consultations=consultations,
        integrated_response=integrated_response.content,
        timestamp=datetime.now(),
    )
    
    # Step 4: Format as markdown
    formatted_record = format_clinical_record(clinical_record)
    
    return {
        "clinical_record": clinical_record,
        "final_response": formatted_record,
        "messages": [AIMessage(content=formatted_record)],
    }


# ============================================================================
# MAIN CLINICAL RESEARCH CREW GRAPH
# ============================================================================

# Build the main clinical consultation graph
clinical_researcher_builder = StateGraph(AgentState, config_schema=Configuration)

# Add main workflow nodes
clinical_researcher_builder.add_node("general_practitioner", general_practitioner)
clinical_researcher_builder.add_node("gp_tools", gp_tools)
clinical_researcher_builder.add_node(
    "clinical_record_generation", clinical_record_generation
)

# Define workflow edges
clinical_researcher_builder.add_edge(START, "general_practitioner")
clinical_researcher_builder.add_edge("clinical_record_generation", END)

# Compile the complete clinical researcher workflow
clinical_researcher = clinical_researcher_builder.compile()
