# Local LLM Setup Guide - For Engineer

**Project:** VHC Talent Management Platform  
**Goal:** Replace cloud AI APIs (Groq, OpenAI) with local Gemma 4 26B model on RTX 4090  
**Business Case:** Save $178/month in API costs, ROI in 17 months

---

## 📋 Quick Overview

**Current State:**
- Using Groq API (llama-3.3-70b) for candidate enrichment
- Hitting rate limits (429 errors)
- Paying ~$178/month projected AI costs
- Need fallback to Emergent LLM Key (uses credit balance)

**Target State:**
- Run Gemma 4 26B locally on RTX 4090 GPU
- Zero recurring API costs
- Full control over AI infrastructure
- Enable 6 new AI features (chatbot, resume parsing, JD generation, etc.)

---

## 🖥️ Hardware Requirements

### Minimum Specs (for Gemma 4 26B A4B):
- **GPU:** NVIDIA RTX 4090 (24GB VRAM) - $1,600
- **CPU:** AMD Ryzen 7 5800X or Intel i7-12700K - $300
- **RAM:** 64GB DDR4 - $150
- **Storage:** 2TB NVMe SSD - $100
- **PSU:** 1000W 80+ Gold - $150
- **Cooling:** Good airflow case + CPU cooler - $200

**Total Investment:** ~$2,500

**Operating Costs:**
- Electricity: ~$30/month (24/7 operation)
- Net Savings: $148/month (API costs avoided)

---

## 🎯 Model Recommendation

**Gemma 4 26B A4B (Mixture-of-Experts)**

| Spec | Value |
|------|-------|
| Total Parameters | 23.2B |
| Active Parameters | 3.8B (MoE - fast!) |
| VRAM Required | 17 GB (fits RTX 4090) |
| Context Window | 256K tokens (handles long resumes) |
| Inference Speed | 2-4 seconds per request |
| Throughput | 15-20 requests/minute |
| Quality | GPT-4 class |
| License | Apache 2.0 (commercial use OK) |

**Why This Model?**
- ✅ Fits RTX 4090 (leaves 7GB VRAM headroom)
- ✅ Fast (MoE architecture = only 3.8B active)
- ✅ Long context (256K = ~400 page resume)
- ✅ Multimodal (can process PDFs with images)
- ✅ Open-source, no licensing fees

---

## 🚀 Phase 1: Server Setup (Week 1)

### Step 1: Build/Order Hardware

**Option A: Pre-built Workstation**
- Order from System Integrator (Puget Systems, Origin PC, etc.)
- Specify: RTX 4090, 64GB RAM, 2TB NVMe
- 2-3 weeks delivery

**Option B: Build Yourself**
- Order parts from local vendor
- Assembly: 2-3 hours
- Cost savings: ~$300

### Step 2: Install Ubuntu Server 22.04 LTS

```bash
# Download Ubuntu Server 22.04 LTS
# Create bootable USB with Rufus/Etcher
# Install with these settings:
# - Hostname: vhc-ai-server
# - Username: vhcadmin
# - OpenSSH: enabled
# - Static IP: 192.168.1.100 (or your network)
```

### Step 3: Install NVIDIA Drivers + CUDA

```bash
# SSH into server
ssh vhcadmin@192.168.1.100

# Update system
sudo apt update && sudo apt upgrade -y

# Install NVIDIA Driver 535 (latest stable)
sudo apt install nvidia-driver-535 -y

# Reboot
sudo reboot

# After reboot, verify GPU
nvidia-smi

# Should show: RTX 4090, 24GB VRAM, Driver 535.xx
```

```bash
# Install CUDA Toolkit 12.3
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-ubuntu2204.pin
sudo mv cuda-ubuntu2204.pin /etc/apt/preferences.d/cuda-repository-pin-600
wget https://developer.download.nvidia.com/compute/cuda/12.3.0/local_installers/cuda-repo-ubuntu2204-12-3-local_12.3.0-545.23.06-1_amd64.deb
sudo dpkg -i cuda-repo-ubuntu2204-12-3-local_12.3.0-545.23.06-1_amd64.deb
sudo cp /var/cuda-repo-ubuntu2204-12-3-local/cuda-*-keyring.gpg /usr/share/keyrings/
sudo apt update
sudo apt install cuda-toolkit-12-3 -y

# Verify CUDA
nvcc --version
```

### Step 4: Install LM Studio (Easiest Option)

**Option A: LM Studio (GUI - Recommended for Testing)**
```bash
# Download LM Studio for Linux
wget https://lmstudio.ai/download/linux -O lmstudio.AppImage
chmod +x lmstudio.AppImage

# Run LM Studio
./lmstudio.AppImage

# In the GUI:
# 1. Go to "Discover" tab
# 2. Search: "gemma-4-26b-a4b"
# 3. Download: "gemma-4-26b-a4b-Q5_K_M.gguf" (17GB)
# 4. Go to "Local Server" tab
# 5. Load the model
# 6. Click "Start Server" (port 1234)
```

**Option B: vLLM (Production - CLI)**
```bash
# Install vLLM (better for production)
pip install vllm

# Download model
huggingface-cli download google/gemma-4-26b-a4b --local-dir /models/gemma-4-26b

# Start vLLM server
vllm serve google/gemma-4-26b-a4b \
  --host 0.0.0.0 \
  --port 1234 \
  --gpu-memory-utilization 0.9 \
  --max-model-len 8192 \
  --dtype float16

# Run as systemd service (optional)
sudo systemctl enable vllm
sudo systemctl start vllm
```

### Step 5: Test the API

```bash
# Test local LLM API
curl http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-26b-a4b",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Extract name and email from: John Doe, john@example.com"}
    ],
    "temperature": 0,
    "max_tokens": 500
  }'

# Should return JSON response in 2-4 seconds
```

---

## 🔌 Phase 2: Integration with VHC Platform (Week 2)

### Architecture

```
VHC AWS Server (13.235.54.45)
    ↓ (HTTP request)
Local AI Server (192.168.1.100:1234)
    ↓ (GPU inference)
Gemma 4 26B on RTX 4090
```

### Step 1: Network Setup

**Option A: VPN Tunnel (Recommended)**
```bash
# On Local AI Server
sudo apt install wireguard -y

# Generate keys
wg genkey | tee privatekey | wg pubkey > publickey

# Configure WireGuard
sudo nano /etc/wireguard/wg0.conf
# [Interface]
# PrivateKey = <local-private-key>
# Address = 10.0.0.2/24
# ListenPort = 51820
# 
# [Peer]
# PublicKey = <aws-public-key>
# AllowedIPs = 10.0.0.1/32
# Endpoint = 13.235.54.45:51820
# PersistentKeepalive = 25

# Start VPN
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0

# Test connectivity
ping 10.0.0.1
```

**Option B: Public IP + Firewall (Simple but less secure)**
```bash
# Open port 1234 on local router (port forward)
# Use UFW firewall to allow only AWS IP

sudo ufw allow from 13.235.54.45 to any port 1234
sudo ufw enable

# AWS server can now access: http://<your-public-ip>:1234
```

**Option C: Cloudflare Tunnel (Zero Trust - Best Security)**
```bash
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Login to Cloudflare
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create vhc-llm

# Route traffic
cloudflared tunnel route dns vhc-llm llm.yourdomain.com

# Start tunnel
cloudflared tunnel run vhc-llm --url http://localhost:1234

# AWS can access: https://llm.yourdomain.com
```

### Step 2: Create Backend Service

```bash
# On VHC AWS Server
cd ~/vhc-platform/backend/services

# Create local LLM service
nano local_llm_service.py
```

```python
# backend/services/local_llm_service.py
import httpx
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Configuration (set in .env)
LOCAL_LLM_URL = "http://10.0.0.2:1234/v1"  # or cloudflare tunnel URL

async def extract_with_local_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0,
    max_tokens: int = 2000
) -> Optional[Dict]:
    """
    Call local Gemma 4 26B for extraction.
    
    Returns dict on success, None on failure.
    """
    try:
        logger.info("[Local-LLM] Sending request...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LOCAL_LLM_URL}/chat/completions",
                json={
                    "model": "gemma-4-26b-a4b",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            )
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            logger.info("[Local-LLM] ✅ Success")
            
            # Parse JSON
            import json
            return json.loads(content.strip())
            
    except Exception as e:
        logger.error(f"[Local-LLM] ❌ Error: {e}")
        return None
```

### Step 3: Update Fallback Chain

```python
# Update llm_fallback_service.py to add Local LLM as primary

async def extract_with_fallback(system_prompt, user_prompt, ...):
    # Tier 1: Local Gemma 4 (if available)
    result = await _try_local_llm(system_prompt, user_prompt, ...)
    if result:
        return {"success": True, "data": result, "source": "local_gemma_4"}
    
    # Tier 2: Groq API (existing)
    result = await _try_groq(system_prompt, user_prompt, ...)
    if result:
        return {"success": True, "data": result, "source": "groq"}
    
    # Tier 3: Emergent LLM Key (existing)
    result = await _try_emergent_openai(system_prompt, user_prompt, ...)
    if result:
        return {"success": True, "data": result, "source": "emergent_llm"}
    
    # Tier 4: Raw text fallback
    return {"success": False, ...}
```

### Step 4: Test Integration

```bash
# On AWS server
cd ~/vhc-platform/backend
python3 test_fallback_system.py

# Should see:
# [Fallback] Attempting Local Gemma 4...
# [Local-LLM] ✅ Success
# [Fallback] ✅ Success via local_gemma_4
```

---

## 📊 Phase 3: Monitoring & Optimization

### Metrics to Track

**1. GPU Monitoring**
```bash
# Install nvidia-smi monitoring
watch -n 1 nvidia-smi

# Or use btop for better UI
sudo apt install btop -y
btop
```

**2. Application Metrics**
```python
# Add to backend
from prometheus_client import Counter, Histogram

llm_requests = Counter('local_llm_requests_total', 'Total LLM requests')
llm_latency = Histogram('local_llm_latency_seconds', 'LLM response time')

# Track in local_llm_service.py
llm_requests.inc()
with llm_latency.time():
    result = await call_local_llm(...)
```

**3. Grafana Dashboard**
- GPU utilization (target: 70-90%)
- Response time (target: <4s)
- Success rate (target: >95%)
- Requests/minute (target: 15-20)

---

## 🔒 Security Checklist

- [ ] Firewall configured (UFW or iptables)
- [ ] VPN/Tunnel for AWS ↔ Local communication
- [ ] No public internet access to port 1234
- [ ] HTTPS if using public endpoints
- [ ] Regular security updates: `sudo apt update && sudo apt upgrade`
- [ ] Backup model files (17GB) to S3/NAS

---

## 🐛 Troubleshooting

### GPU Not Detected
```bash
# Check PCI
lspci | grep NVIDIA

# Reinstall driver
sudo apt purge nvidia-* -y
sudo apt install nvidia-driver-535 -y
sudo reboot
```

### Out of Memory Errors
```bash
# Reduce context length
vllm serve ... --max-model-len 4096

# Or use smaller quantization
# Q5_K_M (current, 17GB) → Q4_K_M (13GB, slightly lower quality)
```

### Slow Inference (>10s)
```bash
# Check GPU utilization
nvidia-smi

# Reduce concurrent requests
# LM Studio: Settings → Server → Max Parallel: 2

# Check CPU bottleneck
htop
```

### Connection Refused from AWS
```bash
# Test locally first
curl http://localhost:1234/v1/models

# Check firewall
sudo ufw status

# Test VPN
ping 10.0.0.2

# Check LM Studio is running
ps aux | grep lmstudio
```

---

## 📞 Questions for Discussion

**Before Hardware Purchase:**
1. Where will the GPU server be located? (Office, data center, home?)
2. Who will manage hardware (power, cooling, physical security)?
3. Network setup: VPN, public IP, or Cloudflare Tunnel?
4. Budget approval for $2,500 hardware?
5. Timeline: When to start? (Order now = delivery in 2-3 weeks)

**Technical Decisions:**
1. LM Studio (GUI, easy) or vLLM (CLI, production)?
2. Start with Phase 1 only, or full migration plan?
3. Keep Groq as fallback or remove completely?
4. Who monitors GPU server 24/7?

**Success Metrics:**
1. How to measure ROI? Track monthly API costs saved?
2. Quality benchmarks: Compare local vs Groq extractions?
3. Uptime SLA: 99% acceptable? Or need redundancy?

---

## 🎯 Next Steps

1. **Review this plan** with your tech team
2. **Get budget approval** for $2,500 hardware
3. **Decide on network setup** (VPN/Tunnel/Public IP)
4. **Order hardware** (2-3 weeks delivery)
5. **Schedule setup** (engineer to help with Phase 1)

**Estimated Timeline:**
- Hardware delivery: 2-3 weeks
- Setup & testing: 1 week
- Integration: 1 week
- **Total: 5-6 weeks to zero API costs**

---

**Contact:** Share this document with your engineer  
**Next Review:** After hardware is ordered  
**Goal:** Cut $178/month API costs to $0 🚀
