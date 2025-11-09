#!/usr/bin/env python3
"""Initialize knowledge base directory structure for Clinical Research Crew.

This script creates the directory structure for all 10 medical specialties
and adds README files to guide the user in populating the knowledge bases.
"""

import os
from pathlib import Path


# Define all medical specialties
SPECIALTIES = [
    "cardiology",
    "pharmacology",
    "neurology",
    "emergency",
    "gynecology",
    "internal_medicine",
    "surgery",
    "nutrition",
    "prevention",
    "epidemiology",
]

# Specialty information for README generation
SPECIALTY_INFO = {
    "cardiology": {
        "spanish": "Cardiología",
        "description": "Cardiovascular diseases, risk assessment, ECG interpretation",
        "key_topics": [
            "ACC/AHA Guidelines",
            "ESC Guidelines",
            "Framingham Risk Score",
            "SCORE cardiovascular risk",
            "CHA₂DS₂-VASc",
            "Heart failure guidelines",
            "Hypertension management",
            "Arrhythmia protocols",
        ],
    },
    "pharmacology": {
        "spanish": "Farmacología",
        "description": "Drug interactions, dosing, pharmacokinetics/pharmacodynamics",
        "key_topics": [
            "Drug interaction databases",
            "Dosing guidelines",
            "Pharmacokinetics",
            "Pharmacodynamics",
            "Contraindications",
            "Special populations (pediatric, geriatric, renal, hepatic)",
        ],
    },
    "neurology": {
        "spanish": "Neurología",
        "description": "Neurological disorders, stroke, seizures, neurological scales",
        "key_topics": [
            "NIHSS (stroke scale)",
            "Glasgow Coma Scale",
            "Stroke protocols",
            "Seizure management",
            "Dementia guidelines",
            "Headache classification",
        ],
    },
    "emergency": {
        "spanish": "Urgencias",
        "description": "Emergency medicine, ACLS/ATLS, triage, acute care",
        "key_topics": [
            "ACLS protocols",
            "ATLS protocols",
            "Triage guidelines",
            "qSOFA criteria",
            "Sepsis management",
            "Trauma protocols",
        ],
    },
    "gynecology": {
        "spanish": "Ginecología",
        "description": "Women's health, obstetrics, gynecologic conditions",
        "key_topics": [
            "ACOG bulletins",
            "Prenatal care guidelines",
            "Contraception",
            "Menopause management",
            "Gynecologic oncology",
            "High-risk pregnancy",
        ],
    },
    "internal_medicine": {
        "spanish": "Medicina Interna",
        "description": "Comprehensive adult medicine, chronic disease management",
        "key_topics": [
            "Diabetes management",
            "Chronic kidney disease",
            "Liver disease",
            "Endocrine disorders",
            "Rheumatologic conditions",
            "Infectious diseases",
        ],
    },
    "surgery": {
        "spanish": "Cirugía",
        "description": "Surgical indications, perioperative care, risk assessment",
        "key_topics": [
            "ASA classification",
            "Perioperative management",
            "Surgical site infection prevention",
            "Postoperative complications",
            "Surgical indications",
        ],
    },
    "nutrition": {
        "spanish": "Nutrición",
        "description": "Medical nutrition therapy, dietary guidelines, nutritional assessment",
        "key_topics": [
            "Medical nutrition therapy",
            "Dietary guidelines",
            "Nutritional assessment",
            "Enteral/parenteral nutrition",
            "Disease-specific nutrition",
        ],
    },
    "prevention": {
        "spanish": "Prevención",
        "description": "Preventive medicine, screening guidelines, immunizations",
        "key_topics": [
            "USPSTF screening recommendations",
            "Immunization schedules",
            "Cancer screening",
            "Cardiovascular prevention",
            "Risk reduction strategies",
        ],
    },
    "epidemiology": {
        "spanish": "Epidemiología",
        "description": "Population health, risk calculation, health disparities",
        "key_topics": [
            "Population-based risk assessment",
            "Incidence and prevalence data",
            "Health disparities",
            "Social determinants of health",
            "Local epidemiological context",
        ],
    },
}


def create_specialty_readme(specialty: str, specialty_path: Path) -> None:
    """Create a README file for a specific specialty."""
    info = SPECIALTY_INFO[specialty]
    
    readme_content = f"""# {info['spanish']} ({specialty.replace('_', ' ').title()})

## Descripción
{info['description']}

## Temas Clave para esta Base de Conocimiento

"""
    
    for topic in info['key_topics']:
        readme_content += f"- {topic}\n"
    
    readme_content += """

## Formatos Soportados

- **PDF**: Guías clínicas, protocolos, artículos de investigación
- **DOCX**: Políticas hospitalarias, procedimientos locales
- **TXT/MD**: Documentos de texto formateado

## Convención de Nombres de Archivo

Para mejor organización y rastreabilidad, usa el siguiente formato:

```
[YYYY]_[FUENTE]_[TEMA]_[VERSION].ext
```

**Ejemplos:**
- `2023_AHA_heart_failure_guidelines_v1.pdf`
- `2024_ESC_atrial_fibrillation_management.pdf`
- `2023_hospital_cardiology_protocol.docx`

## Metadatos Recomendados

Cuando agregues documentos, intenta incluir la siguiente información (si está disponible):

- **Fecha de publicación**: Año de publicación del documento
- **Fuente**: Organización o journal (ACC, AHA, ESC, ACOG, etc.)
- **Nivel de evidencia**: A (alto), B (moderado), C (bajo) si aplica
- **Tipo de documento**: Guía clínica, protocolo, estudio, revisión sistemática

## Cómo Agregar Documentos

1. **Copia tus documentos a esta carpeta**
2. **Renombra según la convención** (opcional pero recomendado)
3. **Ejecuta el script de indexación**:
   ```bash
   python scripts/index_knowledge_base.py --specialty {specialty}
   ```

## Verificación

Para verificar que tus documentos fueron indexados correctamente:

```bash
python scripts/verify_rag_system.py --specialty {specialty}
```

---

**Nota**: Esta base de conocimiento será consultada automáticamente por el especialista
de {info['spanish']} cuando procese interconsultas médicas.
"""
    
    readme_path = specialty_path / "README.md"
    readme_path.write_text(readme_content, encoding='utf-8')
    print(f"  ✓ Created README for {info['spanish']}")


def create_sample_file(specialty: str, specialty_path: Path) -> None:
    """Create a sample .gitkeep file to ensure directory is tracked."""
    sample_path = specialty_path / ".gitkeep"
    sample_path.write_text(
        f"# This directory contains knowledge base documents for {specialty}\n",
        encoding='utf-8'
    )


def initialize_knowledge_bases(base_path: Path = None) -> None:
    """Initialize all knowledge base directories."""
    if base_path is None:
        # Default to knowledge_bases in project root
        base_path = Path(__file__).parent.parent / "knowledge_bases"
    
    print(f"Initializing knowledge bases at: {base_path}\n")
    
    # Create base directory if it doesn't exist
    base_path.mkdir(parents=True, exist_ok=True)
    
    # Create main README
    main_readme = base_path / "README.md"
    if not main_readme.exists():
        print("Creating main knowledge base README...")
        # The main README was already created in Phase 2, but we ensure it exists
        if not main_readme.exists():
            main_readme.write_text("# Medical Knowledge Bases\n\nSee individual specialty directories for details.\n")
    
    # Create directories for each specialty
    print("Creating specialty directories:\n")
    
    for specialty in SPECIALTIES:
        specialty_path = base_path / specialty
        specialty_path.mkdir(parents=True, exist_ok=True)
        
        info = SPECIALTY_INFO[specialty]
        print(f"📁 {info['spanish']} ({specialty})")
        
        # Create README for the specialty
        create_specialty_readme(specialty, specialty_path)
        
        # Create .gitkeep to ensure directory is tracked
        create_sample_file(specialty, specialty_path)
        
        print()
    
    print("=" * 70)
    print("✅ Knowledge base structure initialized successfully!")
    print("=" * 70)
    print(f"\nDirectory structure created at: {base_path}")
    print(f"\nTotal specialties: {len(SPECIALTIES)}")
    print("\nNext steps:")
    print("1. Add your medical documents to the appropriate specialty directories")
    print("2. Follow the naming conventions in each specialty's README.md")
    print("3. Run indexing script: python scripts/index_knowledge_base.py")
    print("4. Verify setup: python scripts/verify_rag_system.py")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Initialize knowledge base directory structure"
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Custom path for knowledge bases (default: ./knowledge_bases)",
    )
    
    args = parser.parse_args()
    
    initialize_knowledge_bases(args.path)
