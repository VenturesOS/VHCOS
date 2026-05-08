# Local LLM Implementation Plan - VHC Platform

## 💰 Business Case

### Current API Costs (Projected)
- **Monthly**: $178
- **Yearly**: $2,136

### Planned AI Features
1. ✅ Candidate Enrichment (Current - Groq)
2. 🔜 Resume Parsing (100s/day)
3. 🔜 Job Description Generation
4. 🔜 Interview Question Generation
5. 🔜 Email Drafting for Recruiters
6. 🔜 Candidate Summarization
7. 🔜 Chatbot (Candidates + Recruiters)

### Investment & ROI

**Hardware Investment: $2,500**
- GPU: RTX 4090 (24GB VRAM) - $1,600
- CPU: AMD Ryzen 7 / Intel i7 - $300
- RAM: 64GB DDR4 - $150
- Storage: 2TB NVMe SSD - $100
- PSU: 1000W - $150
- Case + Cooling: $200

**Operating Costs:**
- Electricity: ~$30/month
- Net Monthly Savings: $148 (API avoided - electricity)
- **Break-even: 17 months**
- **3-year savings: $2,828**

---

## 🖥️ Recommended Model

**Gemma 4 26B A4B (Mixture-of-Experts)**

**Specifications:**
- Total Parameters: 23.2B
- Active Parameters: 3.8B (MoE)
- VRAM Required: 17 GB
- Context Window: 256K tokens
- Modalities: Text, Image
- License: Apache 2.0

**Performance:**
- Speed: 2-4 seconds per inference
- Quality: GPT-4 class
- Throughput: 15-20 requests/minute

**Why This Model?**
- ✅ Fits RTX 4090 (24GB VRAM)
- ✅ Fast inference (MoE architecture)
- ✅ Handles long documents (256K context)
- ✅ Multimodal (can process resume PDFs with images)
- ✅ Open-source (Apache 2.0)

---

## 🛠️ Implementation Phases

### Phase 1: Infrastructure Setup (Week 1)

**Hardware:**
1. Order/build GPU server with RTX 4090
2. Install Ubuntu 22.04 LTS
3. Install NVIDIA drivers + CUDA 12.x
4. Network setup (static IP, firewall rules)

**Software:**
1. Install LM Studio (GUI) or vLLM (CLI)
2. Download Gemma 4 26B A4B model (GGUF format)
3. Test inference speed and quality
4. Set up FastAPI wrapper for API access

**Integration:**
1. Create `/api/local-llm` endpoint
2. Add health checks and monitoring
3. Set up logging and error tracking

### Phase 2: Migration from Groq (Week 2)

**Backend Changes:**
1. Create `backend/services/local_llm_service.py`
   - Same interface as `groq_service.py`
   - Connect to LM Studio API (localhost:1234)
   - Add retry logic and timeouts

2. Update `backend/routes/extension.py`
   - Replace `groq_service` with `local_llm_service`
   - Keep Groq as fallback for high availability

3. Testing:
   - Test candidate enrichment with 100 profiles
   - Compare quality: Local Gemma vs Groq
   - Measure speed and accuracy

### Phase 3: New Features (Weeks 3-6)

#### Week 3: Resume Parsing
**API Endpoint:** `POST /api/ai/parse-resume`
**Input:** PDF/DOCX resume file
**Output:** Structured JSON (name, email, skills, experience, education)
**Volume:** 100-200 resumes/day

#### Week 4: Job Description Generator
**API Endpoint:** `POST /api/ai/generate-jd`
**Input:** Job title, requirements, company info
**Output:** Formatted job description
**Volume:** 50-100 JDs/month

#### Week 5: Email Drafter & Interview Questions
**APIs:**
- `POST /api/ai/draft-email` - Generate recruiter emails
- `POST /api/ai/interview-questions` - Generate interview Q&A

**Volume:** 2,000 emails/month, 500 question sets/month

#### Week 6: Chatbots
**API:** `WebSocket /api/ai/chat`
**Types:**
- Candidate chatbot (job search, application help)
- Recruiter chatbot (candidate search, workflow help)
**Volume:** 7,000 conversations/month

---

## 💻 Technical Architecture

```
┌─────────────────────────────────────────────┐
│         VHC Platform (AWS Server)           │
│                                             │
│  ┌──────────────┐      ┌─────────────────┐ │
│  │   FastAPI    │──────│  Local LLM API  │ │
│  │   Backend    │      │  (Port 8002)    │ │
│  └──────────────┘      └─────────────────┘ │
│         │                      │            │
│         │                      ▼            │
│         │              ┌──────────────────┐ │
│         │              │  LM Studio       │ │
│         │              │  Gemma 4 26B A4B │ │
│         │              │  (RTX 4090)      │ │
│         │              └──────────────────┘ │
│         │                                    │
│         ▼                                    │
│  ┌──────────────┐                          │
│  │   Groq API   │◄─── Fallback only        │
│  │  (Backup)    │                           │
│  └──────────────┘                          │
└─────────────────────────────────────────────┘
```

### Component Details

**1. Local LLM API Server:**
- Framework: FastAPI
- Port: 8002 (internal)
- Features:
  - Queue management (handle concurrent requests)
  - Request timeout: 30 seconds
  - Automatic retry on failure
  - Metrics tracking (response time, success rate)

**2. LM Studio:**
- Model: Gemma 4 26B A4B
- API Endpoint: http://localhost:1234/v1/chat/completions
- Max Concurrent Requests: 4-5
- Context Length: 256K tokens
- Temperature: 0 (deterministic for production)

**3. Fallback Strategy:**
- Primary: Local Gemma 4
- Fallback: Groq API (if local fails)
- Trigger: 503 error or timeout (>30s)

---

## 📊 Monitoring & Maintenance

### Metrics to Track:
1. **Performance:**
   - Average response time (target: <4s)
   - P95/P99 latency
   - Throughput (requests/minute)

2. **Quality:**
   - Success rate (target: >95%)
   - Extraction accuracy (manual spot checks)
   - User satisfaction (feedback)

3. **Cost:**
   - GPU utilization (target: 70-90%)
   - Electricity cost (monthly)
   - Downtime (target: <1% per month)

### Maintenance Tasks:
- Weekly: Check GPU temperature and utilization
- Monthly: Review model performance metrics
- Quarterly: Evaluate new Gemma versions
- As needed: Update model if quality improves

---

## 🚀 Quick Start Commands (When Ready)

### Hardware Setup
```bash
# Install NVIDIA drivers
sudo apt update
sudo apt install nvidia-driver-535

# Install CUDA Toolkit
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-ubuntu2204.pin
sudo mv cuda-ubuntu2204.pin /etc/apt/preferences.d/cuda-repository-pin-600
sudo apt install cuda-toolkit-12-3

# Verify GPU
nvidia-smi
```

### LM Studio Installation
```bash
# Download LM Studio
wget https://lmstudio.ai/download/linux -O lmstudio.AppImage
chmod +x lmstudio.AppImage

# Run LM Studio
./lmstudio.AppImage

# In LM Studio:
# 1. Search for "gemma-4-26b-a4b"
# 2. Download GGUF Q5_K_M quantization
# 3. Load model
# 4. Start server (Settings → Server → Start)
```

### Backend Integration
```bash
cd ~/vhc-platform/backend

# Create local LLM service
touch services/local_llm_service.py

# Update requirements
echo "httpx>=0.25.0" >> requirements.txt
pip install -r requirements.txt

# Test connection
curl http://localhost:1234/v1/models
```

---

## 📝 Code Templates

### 1. Local LLM Service (Pseudocode)
```python
# backend/services/local_llm_service.py
import httpx
from typing import Dict, List, Optional

class LocalLLMService:
    def __init__(self):
        self.base_url = "http://localhost:1234/v1"
        self.timeout = 30
        
    async def chat_completion(self, messages: List[Dict], temperature: float = 0):
        """Call local Gemma 4 via LM Studio API"""
        # Implementation here
        
    async def extract_candidate_profile(self, raw_text: str, candidate_name: str):
        """Same interface as groq_service.py"""
        # Use local model instead of Groq
```

### 2. Fallback Strategy
```python
async def enrich_with_fallback(raw_text: str):
    try:
        # Try local first
        return await local_llm_service.extract(raw_text)
    except Exception as e:
        logger.warning(f"Local LLM failed: {e}, falling back to Groq")
        return await groq_service.extract(raw_text)
```

---

## 🎯 Success Criteria

**Phase 1 Complete When:**
- ✅ GPU server running 24/7
- ✅ Gemma 4 26B loaded and responsive
- ✅ API responding in <4 seconds avg
- ✅ 95%+ uptime

**Phase 2 Complete When:**
- ✅ Candidate enrichment using local LLM
- ✅ Quality matches or exceeds Groq
- ✅ Zero API costs for enrichment
- ✅ Groq fallback working

**Phase 3 Complete When:**
- ✅ All 6 new features deployed
- ✅ Users actively using chatbots
- ✅ Resume parsing at 100+ per day
- ✅ Total monthly API costs: **$0**

---

## 💡 Future Enhancements

1. **Model Upgrades:**
   - Monitor for Gemma 5 / newer models
   - A/B test new models against Gemma 4

2. **Multi-Model Setup:**
   - Small model (E4B) for simple tasks (email drafting)
   - Large model (26B) for complex tasks (chatbot)
   - Save GPU memory and improve throughput

3. **Scaling:**
   - Add 2nd GPU if load increases
   - Implement request queuing
   - Load balancer between multiple GPUs

4. **Fine-tuning:**
   - Fine-tune Gemma 4 on VHC-specific data
   - Improve resume parsing accuracy
   - Better job description quality

---

## 📞 Next Steps

**When ready to proceed:**
1. Order GPU hardware (2-3 weeks delivery)
2. Set up server and install software (1 week)
3. Test Gemma 4 with sample data (2-3 days)
4. Migrate candidate enrichment (1 week)
5. Build new features (4 weeks)

**Total Timeline: ~10 weeks from hardware order to full deployment**

**Expected Outcome:**
- ✅ Zero recurring API costs
- ✅ 6 new AI-powered features
- ✅ Full control over AI infrastructure
- ✅ ROI in 17 months

---

**Status**: PLANNED  
**Next Review**: When ready to purchase hardware  
**Owner**: VHC Tech Team  
**Est. Start Date**: TBD
