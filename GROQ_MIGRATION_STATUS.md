# Migration to Groq - Services Updated

## Services Migrated to Groq (Llama 3.3 70B)

This document tracks the migration of all LLM services from Claude Haiku/GPT to Groq for cost optimization.

### Migration Strategy

**New Routing Order:**
1. **Groq (Primary)** - Llama 3.3 70B Versatile
   - Cost: $0.59/M input + $0.79/M output
   - Speed: <2 seconds
   - Reliability: 99.9%

2. **OpenRouter Free (Fallback 1)** - nvidia/nemotron or qwen
   - Cost: $0
   - Rate limited
   - Use for non-critical tasks

3. **Claude Haiku (Fallback 2)** - via Emergent Key
   - Cost: $0.25/M input + $1.25/M output  
   - Use only when Groq/OpenRouter fail

4. **GPT-4o-mini (Last Resort)** - OpenAI
   - Cost: $0.15/M input + $0.60/M out
   - Rarely used

### Estimated Savings

| Service | Before (Claude) | After (Groq) | Monthly Savings |
|---------|----------------|--------------|-----------------|
| AI Search | $20 | $4 | $16 |
| Batch Enrichment | $15 | $3 | $12 |
| Email Digest | $5 | $1 | $4 |
| Training Manual | $2 | $0.50 | $1.50 |
| Maintenance Reports | $3 | $0.70 | $2.30 |
| LLM Service General | $10 | $2 | $8 |
| **TOTAL** | **$55** | **$11.20** | **$43.80** |

**Annual Savings: ~$525**

---

## Files Modified

### 1. `/app/backend/services/llm_service.py`
- **Change**: Groq as primary, removed Anthropic SDK rotation
- **Status**: ✅ IN PROGRESS

### 2. `/app/backend/services/batch_enrichment.py`  
- **Change**: Update BATCH_MODEL from claude-haiku to groq
- **Status**: ⏳ PENDING

### 3. `/app/backend/services/ai_search.py`
- **Change**: Already uses llm_service.chat_completion() - no changes needed
- **Status**: ✅ AUTO-MIGRATED (via llm_service)

### 4. `/app/backend/services/digest_email_service.py`
- **Change**: Uses llm_service - no direct changes needed
- **Status**: ✅ AUTO-MIGRATED

### 5. `/app/backend/services/training_manual_service.py`
- **Change**: Uses llm_service - no direct changes needed
- **Status**: ✅ AUTO-MIGRATED

### 6. `/app/backend/services/maintenance_report_generator.py`
- **Change**: Uses llm_service - no direct changes needed
- **Status**: ✅ AUTO-MIGRATED

---

## Testing Plan

1. **llm_service.py**: Test chat_completion() with sample queries
2. **AI Search**: Test natural language search queries  
3. **Batch Enrichment**: Test with 10 sample candidates
4. **Email Digest**: Generate test digest
5. **Monitor**: Watch API costs for 48 hours

---

## Rollback Plan

If Groq quality is insufficient:
1. Revert llm_service.py priority order
2. Put Claude/OpenRouter back as primary
3. Keep Groq as fallback

---

**Status**: IN PROGRESS  
**Target Completion**: Today  
**Expected Savings**: $43.80/month ($525/year)
