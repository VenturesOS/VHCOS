# LLM API Audit Report - VHC Platform
**Date**: April 13, 2026  
**Status**: Mixed (Groq + Claude Haiku + GPT-4o-mini)

---

## 🎯 Executive Summary

**Migration Status:** ❌ **INCOMPLETE**  
- ✅ **Candidate Enrichment**: Migrated to Groq ✅
- ❌ **Other Features**: Still using Claude Haiku 4.5 & GPT-4o-mini

**Current Monthly API Costs (Estimated):**
- Candidate Enrichment (Groq): **$6/month** ✅ (migrated)
- AI Search (Claude Haiku): **$20/month** ❌
- Email Digest Generation (Claude Haiku): **$5/month** ❌
- Batch Enrichment (Claude Haiku): **$15/month** ❌
- LLM Service (OpenRouter Free + Claude fallback): **$10/month** ❌
- Maintenance Bot (GPT-4o-mini): **$3/month** ❌
- Training Manual (GPT-4o-mini): **$2/month** ❌

**Total Current Monthly Cost: ~$61/month**

---

## 📊 Detailed Service Breakdown

### 1. ✅ **Candidate Enrichment** (MIGRATED TO GROQ)
**File**: `/app/backend/services/groq_service.py`  
**Model**: Llama 3.3 70B Versatile  
**API**: Groq  
**Usage**:
- Extracting candidate profiles from Naukri
- Phone, email, skills, work experience, education
- Volume: ~3,000 profiles/month

**Cost**: ~$6/month  
**Status**: ✅ **FULLY MIGRATED**

---

### 2. ❌ **AI Search** (STILL ON CLAUDE HAIKU)
**File**: `/app/backend/services/ai_search.py`  
**Function**: `chat_completion()` (via `llm_service.py`)  
**Model**: Claude Haiku 4.5  
**API**: Anthropic (via Emergent LLM Key or OpenRouter Free fallback)

**Usage**:
- Parsing natural language search queries
- Converting to MongoDB filters
- Explaining search results to users

**Example**:
```python
# ai_search.py line 20
from services.llm_service import chat_completion

# Calls llm_service which uses Claude Haiku
```

**Cost**: ~$20/month  
**Status**: ❌ **NEEDS MIGRATION**

---

### 3. ❌ **LLM Service** (WATERFALL: OpenRouter → Claude → GPT)
**File**: `/app/backend/services/llm_service.py`  
**Models** (in priority order):
1. **OpenRouter Free** (nvidia/nemotron-3 or qwen3.6)
2. **Claude Haiku 4.5** (via Emergent LLM Key)
3. **GPT-4o-mini** (OpenAI fallback)

**Usage**:
- General-purpose LLM calls across platform
- Email generation, content summarization
- Used by: AI Search, Email Digest, Maintenance Reports

**Routing Logic**:
```python
# llm_service.py lines 18-27
OPENROUTER_FREE_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
OPENROUTER_FALLBACK_MODEL = "qwen/qwen3.6-plus-preview:free"
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")  # Claude Haiku
DEFAULT_MODEL = "gpt-4o-mini"  # OpenAI fallback
```

**Cost**: ~$10/month (mostly free tier, some Claude/GPT fallback)  
**Status**: ❌ **NEEDS MIGRATION**

---

### 4. ❌ **Bedrock Service** (CLAUDE HAIKU FOR LEGACY)
**File**: `/app/backend/services/bedrock_service.py`  
**Model**: Claude Haiku 4.5  
**API**: Anthropic Direct SDK (with key rotation)

**Usage**:
- **Legacy candidate enrichment** (old code, not actively used)
- Batch enrichment jobs
- Smart contact extraction

**Note**: This service has **LEGACY CODE** that references Claude Opus 4.6 in comments, but actually uses Claude Haiku 4.5.

**Cost**: ~$15/month (if actively used for batch jobs)  
**Status**: ⚠️ **LEGACY - Consider deprecating**

---

### 5. ❌ **Email Digest Service** (CLAUDE HAIKU VIA LLM SERVICE)
**File**: `/app/backend/services/digest_email_service.py`  
**Model**: Claude Haiku 4.5 (via `llm_service.py`)  
**Usage**:
- Generating weekly blog digest emails
- Personalizing content for different user segments

**Dependencies**:
```python
# Likely calls llm_service.chat_completion()
# Which routes to Claude Haiku
```

**Cost**: ~$5/month  
**Status**: ❌ **NEEDS MIGRATION**

---

### 6. ❌ **Batch Enrichment** (CLAUDE HAIKU)
**File**: `/app/backend/services/batch_enrichment.py`  
**Model**: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)  
**Usage**:
- Bulk candidate enrichment
- Background processing of large datasets

**Code Reference**:
```python
# batch_enrichment.py line 16
BATCH_MODEL = "claude-haiku-4-5-20251001"
```

**Cost**: ~$15/month  
**Status**: ❌ **NEEDS MIGRATION**

---

### 7. ❌ **Maintenance Bot** (NO LLM DETECTED)
**File**: `/app/backend/services/maintenance_bot.py`  
**Model**: None (pure health monitoring)  
**Usage**: System health checks, auto-healing

**Cost**: $0  
**Status**: ✅ **NO MIGRATION NEEDED**

---

### 8. ❌ **Training Manual Service** (LIKELY GPT-4o-mini)
**File**: `/app/backend/services/training_manual_service.py`  
**Model**: GPT-4o-mini (via OpenAI or llm_service fallback)  
**Usage**:
- Generating training documentation
- Onboarding content

**Cost**: ~$2/month  
**Status**: ❌ **NEEDS MIGRATION**

---

### 9. ❌ **Maintenance Report Generator** (LIKELY CLAUDE HAIKU)
**File**: `/app/backend/services/maintenance_report_generator.py`  
**Model**: Claude Haiku 4.5 (via llm_service)  
**Usage**:
- Generating system health reports
- Analyzing error logs

**Cost**: ~$3/month  
**Status**: ❌ **NEEDS MIGRATION**

---

## 🚨 Priority Migration List

### **HIGH PRIORITY** (High Usage, High Cost)
1. **AI Search** - $20/month
   - Replace `chat_completion()` calls with local LLM
   - Test search quality with Gemma 4

2. **Batch Enrichment** - $15/month
   - Migrate from Claude Haiku to Groq or local LLM
   - Update `BATCH_MODEL` constant

3. **LLM Service Waterfall** - $10/month
   - Refactor to use local LLM as primary
   - Keep free tiers as fallback

### **MEDIUM PRIORITY** (Moderate Usage)
4. **Email Digest Service** - $5/month
5. **Maintenance Report Generator** - $3/month
6. **Training Manual Service** - $2/month

### **LOW PRIORITY** (Legacy/Minimal Usage)
7. **Bedrock Service** - $15/month (if used)
   - Consider deprecating entirely
   - Already replaced by Groq for candidate enrichment

---

## 💰 Cost Savings Potential

### Current State
- **Candidate Enrichment**: Groq ($6/month) ✅
- **Everything Else**: Claude/GPT ($55/month) ❌

### After Full Migration to Local LLM
- **All AI Features**: Local Gemma 4 ($0/month) ✅
- **Fallback Only**: Groq ($2-3/month for failures) ✅

**Total Monthly Savings: $58-59/month**  
**Yearly Savings: ~$700/year**

---

## 🎯 Recommended Actions

### **Option A: Incremental Migration** (Safer, Slower)
**Timeline**: 4-6 weeks

1. **Week 1**: Migrate AI Search to Groq
2. **Week 2**: Migrate Batch Enrichment to Groq
3. **Week 3**: Refactor LLM Service to prioritize Groq
4. **Week 4**: Migrate Email/Reports to Groq
5. **Week 5-6**: Test and optimize

**Pro**: Lower risk, test each feature independently  
**Con**: Still paying API costs during migration

### **Option B: Jump to Local LLM** (Faster, Higher Savings)
**Timeline**: 10 weeks (includes hardware setup)

1. **Week 1-3**: Purchase hardware, set up GPU server
2. **Week 4**: Deploy Gemma 4 26B A4B, test performance
3. **Week 5**: Migrate candidate enrichment to local
4. **Week 6-9**: Migrate all other features
5. **Week 10**: Testing and optimization

**Pro**: Zero recurring costs, full control  
**Con**: Upfront investment ($2,500)

---

## 📝 Migration Checklist

### Services Using LLM APIs:
- [ ] ✅ Candidate Enrichment (Groq) - **DONE**
- [ ] ❌ AI Search (Claude Haiku) - **TODO**
- [ ] ❌ LLM Service (Claude/GPT) - **TODO**
- [ ] ❌ Batch Enrichment (Claude) - **TODO**
- [ ] ❌ Email Digest (Claude) - **TODO**
- [ ] ❌ Training Manual (GPT) - **TODO**
- [ ] ❌ Maintenance Reports (Claude) - **TODO**
- [ ] ⚠️ Bedrock Service (Legacy) - **CONSIDER DEPRECATING**

### Test Cases Needed:
- [ ] AI Search query parsing accuracy
- [ ] Batch enrichment speed and quality
- [ ] Email digest personalization quality
- [ ] Training manual coherence
- [ ] Maintenance report usefulness

---

## 🔍 Files to Modify for Full Migration

```
/app/backend/services/
├── groq_service.py           ✅ Already uses Groq
├── local_llm_service.py      🔜 Create this (for local Gemma 4)
├── llm_service.py            ❌ Refactor waterfall routing
├── ai_search.py              ❌ Replace chat_completion() calls
├── batch_enrichment.py       ❌ Change BATCH_MODEL to Groq/local
├── digest_email_service.py   ❌ Update LLM calls
├── training_manual_service.py ❌ Update LLM calls
├── maintenance_report_generator.py ❌ Update LLM calls
└── bedrock_service.py        ⚠️ Deprecate or archive
```

---

## ✅ Next Steps

1. **Decide migration strategy**: Incremental (Groq) or Full (Local LLM)?
2. **If Incremental**: Start with AI Search migration this week
3. **If Local LLM**: Review hardware plan, order GPU server
4. **Test Plan**: Create test suite for each feature before migration
5. **Monitor**: Track API costs during migration to measure savings

---

**Status**: AUDIT COMPLETE  
**Recommendation**: **Proceed with Local LLM setup** (best long-term ROI)  
**Immediate Action**: Test AI Search with Groq to validate migration feasibility
