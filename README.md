# Clinical Research Crew 🏥

Multi-agent medical consultation system that simulates the traditional medical interconsultation workflow using LangGraph, RAG, and specialized AI agents.

## 🚀 Quick Start

```bash
# 1. Initialize knowledge bases
python scripts/initialize_knowledge_bases.py

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Add medical documents to knowledge_bases/

# 4. Run with LangGraph Studio
langgraph up
```

## 📖 Full Documentation

See **[PROJECT_STATUS.md](PROJECT_STATUS.md)** for complete documentation including:

- ✅ Implementation progress (9/14 phases complete)
- 🏗️ Architecture details
- 📝 Medical note formats
- 🎯 10 medical specialties
- 🛠️ Clinical tools (RAG, PubMed, calculators)
- 📊 Project structure

## 🎯 What It Does

Simulates professional medical consultation workflow:

1. **GP analyzes** clinical question
2. **Consults specialists** as needed (10 specialties available)
3. **Generates** evidence-based clinical records in Spanish

## 🏥 Available Specialists

- Cardiología • Farmacología • Neurología • Urgencias • Ginecología
- Medicina Interna • Cirugía • Nutrición • Prevención • Epidemiología

## 🔧 Key Features

- 🤖 11 specialized AI agents (1 GP + 10 specialists)
- 📚 RAG-powered specialty knowledge bases
- 🔬 PubMed literature integration
- 🧮 Clinical calculators (GFR, BMI, CHADS2-VASc, etc.)
- 📋 Evidence-based with citations required
- 🇪🇸 Spanish medical terminology

## 📁 Project Structure

```
clinical_crew_deep_research/
├── src/clinical_research_crew/   # Core implementation
├── knowledge_bases/               # Medical knowledge (10 specialties)
├── scripts/                       # Utility scripts
├── PROJECT_STATUS.md              # 📖 Full documentation
└── README.md                      # This file
```

## ⚠️ Important

- **For clinical decision support and education only**
- Not cleared for direct patient care
- Requires physician review
- Not HIPAA-compliant without additional safeguards

---

**Status**: ✅ Core complete (64%) • Ready for testing  
**Docs**: See [PROJECT_STATUS.md](PROJECT_STATUS.md)  
**Last Updated**: 2025-01-23
