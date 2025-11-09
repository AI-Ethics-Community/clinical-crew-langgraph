"""Medical tools for Clinical Research Crew.

This module provides medical-specific tools including PubMed search,
clinical calculators, diagnostic criteria lookup, and RAG integration.
"""

import math
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

# Import RAG system
from clinical_research_crew.rag_system import query_knowledge_base


# ==============================================================================
# RAG Knowledge Base Tool
# ==============================================================================

@tool
def rag_query_specialty_knowledge(
    specialty: str,
    query: str,
    top_k: int = 3
) -> str:
    """Query specialty-specific knowledge base using RAG.
    
    This tool searches through clinical guidelines, protocols, and medical
    documents specific to a medical specialty.
    
    Args:
        specialty: Medical specialty (cardiology, pharmacology, neurology, etc.)
        query: Clinical question or search query
        top_k: Number of relevant documents to retrieve (default: 3)
        
    Returns:
        Formatted string with retrieved documents and citations
        
    Example:
        >>> rag_query_specialty_knowledge(
        ...     specialty="cardiology",
        ...     query="ACC/AHA guidelines for heart failure management",
        ...     top_k=3
        ... )
    """
    try:
        results = query_knowledge_base(specialty, query, top_k)
        return results
    except Exception as e:
        return f"Error querying knowledge base: {str(e)}"


# ==============================================================================
# PubMed Search Tool
# ==============================================================================

@tool
def pubmed_search(
    query: str,
    max_results: int = 5,
    years_back: int = 10
) -> str:
    """Search PubMed for medical literature.
    
    Searches PubMed/MEDLINE database for relevant medical literature with
    filters for recent, high-quality evidence.
    
    Args:
        query: Search query (medical terms, conditions, interventions)
        max_results: Maximum number of results to return (default: 5)
        years_back: How many years back to search (default: 10)
        
    Returns:
        Formatted string with article titles, abstracts, and PubMed IDs
        
    Filters applied:
    - Last N years (default: 10)
    - Preference for: Clinical trials, meta-analyses, systematic reviews
    - English or Spanish language
    
    Example:
        >>> pubmed_search("heart failure beta blockers", max_results=3)
    """
    try:
        from Bio import Entrez
        import datetime
        
        # Set email for Entrez (required by NCBI)
        Entrez.email = "clinical.research.crew@example.com"
        
        # Calculate date range
        current_year = datetime.datetime.now().year
        min_date = f"{current_year - years_back}/01/01"
        max_date = f"{current_year}/12/31"
        
        # Build search query with filters
        # Prefer high-quality evidence
        search_query = f"{query} AND ({min_date}:{max_date}[PDAT])"
        search_query += " AND (Clinical Trial[PT] OR Meta-Analysis[PT] OR Systematic Review[PT] OR Review[PT])"
        search_query += " AND (English[LA] OR Spanish[LA])"
        
        # Search PubMed
        handle = Entrez.esearch(
            db="pubmed",
            term=search_query,
            retmax=max_results,
            sort="relevance"
        )
        record = Entrez.read(handle)
        handle.close()
        
        id_list = record["IdList"]
        
        if not id_list:
            return f"No recent articles found for query: {query}"
        
        # Fetch details
        handle = Entrez.efetch(
            db="pubmed",
            id=id_list,
            rettype="abstract",
            retmode="xml"
        )
        articles = Entrez.read(handle)
        handle.close()
        
        # Format results
        results = []
        for i, article in enumerate(articles['PubmedArticle'], 1):
            try:
                medline = article['MedlineCitation']
                article_data = medline['Article']
                
                title = article_data.get('ArticleTitle', 'No title')
                pmid = medline['PMID']
                
                # Get abstract
                abstract = "No abstract available"
                if 'Abstract' in article_data:
                    abstract_texts = article_data['Abstract'].get('AbstractText', [])
                    if abstract_texts:
                        abstract = ' '.join([str(text) for text in abstract_texts])
                
                # Get authors
                authors = "Authors not listed"
                if 'AuthorList' in article_data:
                    author_list = article_data['AuthorList'][:3]  # First 3 authors
                    author_names = []
                    for author in author_list:
                        if 'LastName' in author and 'Initials' in author:
                            author_names.append(f"{author['LastName']} {author['Initials']}")
                    if author_names:
                        authors = ', '.join(author_names)
                        if len(article_data['AuthorList']) > 3:
                            authors += ", et al."
                
                # Get journal and year
                journal = article_data.get('Journal', {}).get('Title', 'Unknown journal')
                pub_date = article_data.get('Journal', {}).get('JournalIssue', {}).get('PubDate', {})
                year = pub_date.get('Year', 'Unknown year')
                
                results.append(
                    f"[{i}] {title}\n"
                    f"Authors: {authors}\n"
                    f"Journal: {journal} ({year})\n"
                    f"PMID: {pmid}\n"
                    f"URL: https://pubmed.ncbi.nlm.nih.gov/{pmid}/\n"
                    f"Abstract: {abstract[:500]}{'...' if len(abstract) > 500 else ''}\n"
                    f"{'-'*80}\n"
                )
            except Exception as e:
                continue
        
        if not results:
            return f"Error parsing PubMed results for query: {query}"
        
        return f"PubMed Search Results for: {query}\n{'='*80}\n" + '\n'.join(results)
        
    except ImportError:
        return (
            "Error: BioPython not installed. "
            "Install with: pip install biopython\n"
            "Falling back to query without PubMed search."
        )
    except Exception as e:
        return f"Error searching PubMed: {str(e)}"


# ==============================================================================
# Clinical Calculators
# ==============================================================================

@tool
def calculate_gfr(
    creatinine_mg_dl: float,
    age: int,
    sex: str,
    race: str = "other"
) -> Dict[str, Any]:
    """Calculate Glomerular Filtration Rate (eGFR) using CKD-EPI equation.
    
    Args:
        creatinine_mg_dl: Serum creatinine in mg/dL
        age: Patient age in years
        sex: "male" or "female"
        race: "black" or "other" (note: 2021 equation removes race)
        
    Returns:
        Dictionary with eGFR value and CKD stage
        
    Example:
        >>> calculate_gfr(1.2, 65, "male")
        {'egfr': 65.3, 'stage': 'G2 - Mildly decreased', 'stage_number': 2}
    """
    sex = sex.lower()
    race = race.lower()
    
    # CKD-EPI 2021 equation (race-free)
    kappa = 0.7 if sex == "female" else 0.9
    alpha = -0.241 if sex == "female" else -0.302
    sex_factor = 1.012 if sex == "female" else 1.0
    
    min_factor = min(creatinine_mg_dl / kappa, 1.0)
    max_factor = max(creatinine_mg_dl / kappa, 1.0)
    
    egfr = 142 * (min_factor ** alpha) * (max_factor ** -1.200) * (0.9938 ** age) * sex_factor
    
    # Determine CKD stage
    if egfr >= 90:
        stage = "G1 - Normal or high"
        stage_number = 1
    elif egfr >= 60:
        stage = "G2 - Mildly decreased"
        stage_number = 2
    elif egfr >= 45:
        stage = "G3a - Mild to moderate decrease"
        stage_number = 3
    elif egfr >= 30:
        stage = "G3b - Moderate to severe decrease"
        stage_number = 3
    elif egfr >= 15:
        stage = "G4 - Severely decreased"
        stage_number = 4
    else:
        stage = "G5 - Kidney failure"
        stage_number = 5
    
    return {
        "egfr": round(egfr, 1),
        "stage": stage,
        "stage_number": stage_number,
        "units": "mL/min/1.73m²"
    }


@tool
def calculate_bmi(weight_kg: float, height_cm: float) -> Dict[str, Any]:
    """Calculate Body Mass Index (BMI).
    
    Args:
        weight_kg: Weight in kilograms
        height_cm: Height in centimeters
        
    Returns:
        Dictionary with BMI value and classification
        
    Example:
        >>> calculate_bmi(70, 170)
        {'bmi': 24.2, 'classification': 'Normal weight'}
    """
    height_m = height_cm / 100
    bmi = weight_kg / (height_m ** 2)
    
    if bmi < 18.5:
        classification = "Underweight"
    elif bmi < 25:
        classification = "Normal weight"
    elif bmi < 30:
        classification = "Overweight"
    elif bmi < 35:
        classification = "Obesity Class I"
    elif bmi < 40:
        classification = "Obesity Class II"
    else:
        classification = "Obesity Class III"
    
    return {
        "bmi": round(bmi, 1),
        "classification": classification,
        "weight_kg": weight_kg,
        "height_cm": height_cm
    }


@tool
def calculate_chads2vasc(
    age: int,
    sex: str,
    chf: bool = False,
    hypertension: bool = False,
    stroke_tia: bool = False,
    vascular_disease: bool = False,
    diabetes: bool = False
) -> Dict[str, Any]:
    """Calculate CHA₂DS₂-VASc score for stroke risk in atrial fibrillation.
    
    Args:
        age: Patient age in years
        sex: "male" or "female"
        chf: Congestive heart failure
        hypertension: History of hypertension
        stroke_tia: Prior stroke or TIA
        vascular_disease: Vascular disease (MI, PAD, aortic plaque)
        diabetes: Diabetes mellitus
        
    Returns:
        Dictionary with score and anticoagulation recommendation
        
    Example:
        >>> calculate_chads2vasc(75, "male", chf=True, hypertension=True)
        {'score': 4, 'risk': 'High', 'recommendation': 'Oral anticoagulation recommended'}
    """
    score = 0
    
    # C - CHF
    if chf:
        score += 1
    
    # H - Hypertension
    if hypertension:
        score += 1
    
    # A - Age
    if age >= 75:
        score += 2
    elif age >= 65:
        score += 1
    
    # D - Diabetes
    if diabetes:
        score += 1
    
    # S - Stroke/TIA
    if stroke_tia:
        score += 2
    
    # V - Vascular disease
    if vascular_disease:
        score += 1
    
    # Sc - Sex category (female)
    if sex.lower() == "female":
        score += 1
    
    # Recommendation
    if score == 0:
        risk = "Very low"
        recommendation = "No antithrombotic therapy or consider aspirin"
    elif score == 1 and sex.lower() == "male":
        risk = "Low"
        recommendation = "Consider oral anticoagulation or no therapy"
    elif score == 1 and sex.lower() == "female":
        risk = "Low"
        recommendation = "Consider oral anticoagulation or aspirin"
    else:
        risk = "Moderate to High"
        recommendation = "Oral anticoagulation recommended (DOACs preferred over warfarin)"
    
    return {
        "score": score,
        "risk": risk,
        "recommendation": recommendation
    }


@tool
def calculate_framingham_risk(
    age: int,
    sex: str,
    total_cholesterol: float,
    hdl_cholesterol: float,
    systolic_bp: int,
    on_bp_meds: bool = False,
    smoker: bool = False,
    diabetes: bool = False
) -> Dict[str, Any]:
    """Calculate 10-year cardiovascular risk using Framingham Risk Score.
    
    Args:
        age: Age in years (30-74)
        sex: "male" or "female"
        total_cholesterol: Total cholesterol in mg/dL
        hdl_cholesterol: HDL cholesterol in mg/dL
        systolic_bp: Systolic blood pressure in mmHg
        on_bp_meds: Currently on blood pressure medication
        smoker: Current smoker
        diabetes: Has diabetes
        
    Returns:
        Dictionary with 10-year CVD risk percentage and category
        
    Example:
        >>> calculate_framingham_risk(55, "male", 200, 45, 130, smoker=True)
        {'risk_percent': 12.5, 'category': 'Moderate risk', 'recommendation': '...'}
    """
    sex = sex.lower()
    
    # Simplified Framingham calculation (ATP III)
    points = 0
    
    # Age points
    if sex == "male":
        if age < 35:
            points -= 1
        elif age < 40:
            points += 0
        elif age < 45:
            points += 1
        elif age < 50:
            points += 2
        elif age < 55:
            points += 3
        elif age < 60:
            points += 4
        elif age < 65:
            points += 5
        elif age < 70:
            points += 6
        else:
            points += 7
    else:  # female
        if age < 35:
            points -= 9
        elif age < 40:
            points -= 4
        elif age < 45:
            points += 0
        elif age < 50:
            points += 3
        elif age < 55:
            points += 6
        elif age < 60:
            points += 7
        elif age < 65:
            points += 8
        elif age < 70:
            points += 8
        else:
            points += 8
    
    # Total cholesterol points (simplified)
    if total_cholesterol < 160:
        chol_points = 0
    elif total_cholesterol < 200:
        chol_points = 1
    elif total_cholesterol < 240:
        chol_points = 2
    elif total_cholesterol < 280:
        chol_points = 3
    else:
        chol_points = 4
    
    points += chol_points
    
    # HDL points (protective)
    if hdl_cholesterol >= 60:
        points -= 1
    elif hdl_cholesterol < 40:
        points += 1
    
    # Blood pressure points
    if systolic_bp < 120:
        bp_points = 0
    elif systolic_bp < 130:
        bp_points = 1 if on_bp_meds else 0
    elif systolic_bp < 140:
        bp_points = 2 if on_bp_meds else 1
    elif systolic_bp < 160:
        bp_points = 3 if on_bp_meds else 2
    else:
        bp_points = 4 if on_bp_meds else 3
    
    points += bp_points
    
    # Smoking
    if smoker:
        points += 2 if sex == "male" else 2
    
    # Diabetes
    if diabetes:
        points += 2 if sex == "male" else 4
    
    # Convert points to risk (simplified lookup)
    if points < 0:
        risk_percent = 1
    elif points < 5:
        risk_percent = 2
    elif points < 10:
        risk_percent = 6
    elif points < 15:
        risk_percent = 12
    elif points < 20:
        risk_percent = 20
    else:
        risk_percent = 30
    
    # Risk category
    if risk_percent < 10:
        category = "Low risk"
        recommendation = "Lifestyle modifications, consider statin if LDL >190 mg/dL"
    elif risk_percent < 20:
        category = "Moderate risk"
        recommendation = "Lifestyle modifications + statin therapy recommended"
    else:
        category = "High risk"
        recommendation = "Intensive lifestyle modifications + statin therapy + aspirin"
    
    return {
        "risk_percent": risk_percent,
        "category": category,
        "recommendation": recommendation,
        "points": points
    }


@tool
def calculate_wells_score_dvt(
    active_cancer: bool = False,
    paralysis_paresis: bool = False,
    recently_bedridden: bool = False,
    localized_tenderness: bool = False,
    entire_leg_swollen: bool = False,
    calf_swelling: bool = False,
    pitting_edema: bool = False,
    collateral_veins: bool = False,
    alternative_diagnosis: bool = False
) -> Dict[str, Any]:
    """Calculate Wells Score for Deep Vein Thrombosis (DVT) probability.
    
    Args:
        active_cancer: Active cancer (treatment within 6 months or palliative)
        paralysis_paresis: Paralysis, paresis, or recent plaster immobilization
        recently_bedridden: Recently bedridden >3 days or major surgery within 12 weeks
        localized_tenderness: Localized tenderness along deep venous system
        entire_leg_swollen: Entire leg swollen
        calf_swelling: Calf swelling >3 cm compared to asymptomatic leg
        pitting_edema: Pitting edema confined to symptomatic leg
        collateral_veins: Collateral superficial veins (non-varicose)
        alternative_diagnosis: Alternative diagnosis at least as likely as DVT
        
    Returns:
        Dictionary with score, probability, and recommendation
        
    Example:
        >>> calculate_wells_score_dvt(localized_tenderness=True, calf_swelling=True)
        {'score': 2, 'probability': 'Moderate', 'recommendation': 'D-dimer + ultrasound'}
    """
    score = 0
    
    if active_cancer:
        score += 1
    if paralysis_paresis:
        score += 1
    if recently_bedridden:
        score += 1
    if localized_tenderness:
        score += 1
    if entire_leg_swollen:
        score += 1
    if calf_swelling:
        score += 1
    if pitting_edema:
        score += 1
    if collateral_veins:
        score += 1
    if alternative_diagnosis:
        score -= 2
    
    # Interpretation
    if score <= 0:
        probability = "Low"
        dvt_risk = "~5%"
        recommendation = "D-dimer; if negative, DVT excluded. If positive, ultrasound."
    elif score <= 2:
        probability = "Moderate"
        dvt_risk = "~17%"
        recommendation = "D-dimer + ultrasound. Consider ultrasound first."
    else:
        probability = "High"
        dvt_risk = "~53%"
        recommendation = "Ultrasound imaging recommended (skip D-dimer)."
    
    return {
        "score": score,
        "probability": probability,
        "dvt_risk": dvt_risk,
        "recommendation": recommendation
    }


# ==============================================================================
# Diagnostic Criteria Lookup (Simplified)
# ==============================================================================

@tool
def lookup_diagnostic_criteria(condition: str) -> str:
    """Retrieve diagnostic criteria for common medical conditions.
    
    Args:
        condition: Name of condition (e.g., "diabetes", "heart failure", "sepsis")
        
    Returns:
        String with diagnostic criteria and guidelines
        
    Example:
        >>> lookup_diagnostic_criteria("diabetes")
    """
    # Simplified criteria database (in production, this would query a real database)
    criteria_db = {
        "diabetes": """
**Diabetes Mellitus Diagnostic Criteria (ADA 2023)**

Any one of the following:
1. Fasting plasma glucose ≥126 mg/dL (7.0 mmol/L)
   - Fasting = no caloric intake for at least 8 hours
2. 2-hour plasma glucose ≥200 mg/dL (11.1 mmol/L) during OGTT
   - 75g oral glucose tolerance test
3. HbA1c ≥6.5% (48 mmol/mol)
   - Using standardized assay
4. Random plasma glucose ≥200 mg/dL (11.1 mmol/L) with symptoms
   - Classic symptoms: polyuria, polydipsia, unexplained weight loss

**Prediabetes:**
- Fasting glucose 100-125 mg/dL, OR
- 2-hour glucose 140-199 mg/dL, OR
- HbA1c 5.7-6.4%

*Criteria should be confirmed with repeat testing unless acute hyperglycemia with metabolic decompensation.*
""",
        "heart failure": """
**Heart Failure Diagnostic Criteria**

**Framingham Criteria** (2 major OR 1 major + 2 minor):

*Major criteria:*
- Paroxysmal nocturnal dyspnea
- Neck vein distention
- Rales/crackles
- Radiographic cardiomegaly
- Acute pulmonary edema
- S3 gallop
- Increased central venous pressure (>16 cm H2O)
- Hepatojugular reflux
- Weight loss >4.5 kg in 5 days in response to treatment

*Minor criteria:*
- Bilateral ankle edema
- Nocturnal cough
- Dyspnea on exertion
- Hepatomegaly
- Pleural effusion
- Tachycardia (>120 bpm)

**ESC Criteria:**
Requires: Symptoms + Signs + Objective cardiac dysfunction
+ Response to HF therapy (if diagnosis uncertain)

**BNP/NT-proBNP:**
- BNP >35 pg/mL or NT-proBNP >125 pg/mL suggests HF
- Higher values increase likelihood
""",
        "sepsis": """
**Sepsis-3 Definitions (2016)**

**Sepsis:** Life-threatening organ dysfunction caused by dysregulated host response to infection

*Criteria:*
- Suspected or documented infection, AND
- Acute increase in SOFA score ≥2 points

**qSOFA (Quick SOFA) - Bedside screening:**
≥2 of the following suggests sepsis:
- Respiratory rate ≥22/min
- Altered mentation (GCS <15)
- Systolic BP ≤100 mmHg

**Septic Shock:**
Sepsis with:
- Vasopressor requirement to maintain MAP ≥65 mmHg, AND
- Lactate >2 mmol/L
- Despite adequate fluid resuscitation

*SOFA score components: PaO2/FiO2, platelets, bilirubin, MAP, GCS, creatinine/urine output*
""",
    }
    
    condition_lower = condition.lower().strip()
    
    if condition_lower in criteria_db:
        return criteria_db[condition_lower]
    else:
        # Return generic response
        available = ", ".join(criteria_db.keys())
        return (
            f"Diagnostic criteria for '{condition}' not found in simplified database.\n\n"
            f"Available conditions: {available}\n\n"
            "For specific criteria, please:\n"
            "1. Use rag_query_specialty_knowledge() to search knowledge bases\n"
            "2. Use pubmed_search() to find recent guidelines\n"
            "3. Specify the guideline source (e.g., 'ADA criteria for diabetes')"
        )


# ==============================================================================
# Tool Registry
# ==============================================================================

# All medical tools available to agents
MEDICAL_TOOLS = [
    rag_query_specialty_knowledge,
    pubmed_search,
    calculate_gfr,
    calculate_bmi,
    calculate_chads2vasc,
    calculate_framingham_risk,
    calculate_wells_score_dvt,
    lookup_diagnostic_criteria,
]


def get_medical_tools() -> List:
    """Get list of all medical tools.
    
    Returns:
        List of medical tool functions
    """
    return MEDICAL_TOOLS


def get_tools_for_specialty(specialty: str) -> List:
    """Get recommended tools for a specific specialty.
    
    Args:
        specialty: Medical specialty name
        
    Returns:
        List of relevant tools for that specialty
    """
    # Base tools for all specialties
    base_tools = [rag_query_specialty_knowledge, pubmed_search, lookup_diagnostic_criteria]
    
    specialty_specific = {
        "cardiology": base_tools + [
            calculate_chads2vasc,
            calculate_framingham_risk,
        ],
        "pharmacology": base_tools,
        "neurology": base_tools,
        "emergency": base_tools + [calculate_wells_score_dvt],
        "internal_medicine": base_tools + [
            calculate_gfr,
            calculate_bmi,
            calculate_framingham_risk,
        ],
        "nutrition": base_tools + [calculate_bmi],
        "prevention": base_tools + [calculate_framingham_risk, calculate_bmi],
        "epidemiology": base_tools,
        "surgery": base_tools + [calculate_bmi],
        "gynecology": base_tools + [calculate_bmi],
    }
    
    return specialty_specific.get(specialty, base_tools)
