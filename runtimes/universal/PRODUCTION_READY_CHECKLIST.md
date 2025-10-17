# Production Ready Checklist - Universal Runtime

## TL;DR for Production

Your code **already works** for production. To optimize performance:

1. **Must Do** (30 min): Convert EncoderModel to ONNX → 3x faster embeddings
2. **Optional** (2 hours): Convert CausalLM/Vision to ONNX → 1.5-2x faster
3. **Don't Do**: Convert Diffusion to ONNX (keep PyTorch, use torch.compile)

## Current Architecture Review

### ✅ What's Production-Ready Now

- **API Design** - OpenAI-compatible REST endpoints
- **Model Loading** - Lazy loading, cached instances
- **Error Handling** - Proper exception handling
- **Hardware Detection** - Auto-detects CUDA/MPS/CPU
- **Code Quality** - Well-tested, documented

### ⚠️ What Needs Optimization for Scale

- **Embedding Performance** - PyTorch is 3x slower than ONNX
- **Memory Management** - No model unloading strategy
- **Concurrency** - Single request processing
- **Monitoring** - No metrics/logging for production

## Production Optimization Roadmap

### Phase 1: ONNX for Embeddings (CRITICAL)

**Why:** Embeddings are the bottleneck in RAG systems

**Time:** 30 minutes
**Impact:** 3x faster
**Difficulty:** Easy

**Action:**
```python
# Add to encoder_model.py
if os.getenv("RUNTIME_BACKEND") == "onnx":
    from optimum.onnxruntime import ORTModelForFeatureExtraction
    self.model = ORTModelForFeatureExtraction.from_pretrained(
        self.model_id, export=True
    )
```

**Deploy:**
```bash
export RUNTIME_BACKEND=onnx
docker-compose up
```

### Phase 2: Add Production Monitoring (IMPORTANT)

**Time:** 1-2 hours
**Impact:** Visibility into performance

**Add:**
- Prometheus metrics (request latency, model load time)
- Structured logging (JSON format)
- Health check endpoint enhancements
- Request tracing

### Phase 3: Concurrency & Batching (IF NEEDED)

**Time:** 4-6 hours
**Impact:** 10x throughput

**Only if:**
- Handling >100 requests/second
- Models support batching well

**Approach:**
- Use AsyncIO batching for embeddings
- Add request queuing
- Implement dynamic batch sizing

### Phase 4: Model Management (OPTIONAL)

**Time:** 2-3 hours
**Impact:** Better resource usage

**Add:**
- Model unloading after idle timeout
- Model warmup on startup
- Version management

## Production Deployment Scenarios

### Scenario A: RAG-Heavy Workload (Most Common)

**Characteristics:**
- Lots of embedding requests
- Some text generation
- Rare image operations

**Optimization Priority:**
1. ✅ EncoderModel → ONNX (CRITICAL)
2. ✅ Add monitoring
3. ⚠️ Consider CausalLM → ONNX (if high volume)
4. ❌ Skip others

**Expected Results:**
- Embedding: 15ms → 5ms per request
- Can handle 3x more concurrent requests
- 50% reduction in GPU/CPU usage for embeddings

### Scenario B: Text Generation Heavy

**Characteristics:**
- Mostly chat/completion requests
- Some embeddings for RAG
- No images

**Optimization Priority:**
1. ✅ EncoderModel → ONNX
2. ✅ CausalLM → ONNX
3. ✅ Add batching for generation
4. ✅ Consider vLLM for text generation instead

**Expected Results:**
- Embeddings: 3x faster
- Generation: 1.4x faster
- Better throughput with batching

### Scenario C: Multi-Modal Workload

**Characteristics:**
- Image generation (Stable Diffusion)
- Image classification
- Some text/embeddings

**Optimization Priority:**
1. ✅ EncoderModel → ONNX
2. ✅ VisionModel → ONNX (classification only)
3. ✅ Use torch.compile() for Diffusion
4. ❌ Don't convert Diffusion to ONNX

**Expected Results:**
- Embeddings: 3x faster
- Vision classification: 2x faster
- Diffusion: 1.5x faster with torch.compile

## Hardware Recommendations

### For RAG (Embeddings + Text)

**CPU-Only (Budget)**
- 8-core CPU, 16GB RAM
- ONNX encoder: ~5ms/request
- Good for: <100 req/min
- Cost: ~$50-100/month cloud

**GPU (Recommended)**
- NVIDIA T4 or better, 16GB VRAM
- ONNX encoder: ~2ms/request
- Good for: <1000 req/min
- Cost: ~$300-500/month cloud

**High Scale**
- NVIDIA A100, 40GB+ VRAM
- ONNX encoder: ~1ms/request
- Good for: >1000 req/min
- Cost: ~$1500+/month cloud

### For Image Generation

**Minimum**
- NVIDIA RTX 3060 (12GB) or T4 (16GB)
- SDXL: 10-15s per image
- Cost: ~$300-500/month cloud

**Recommended**
- NVIDIA A10G (24GB) or RTX 4090
- SDXL: 5-8s per image
- Cost: ~$800-1200/month cloud

**High Performance**
- NVIDIA A100 (40-80GB)
- SDXL: 2-4s per image
- Cost: ~$1500+/month cloud

## Cost Analysis

### Current Setup (PyTorch)

**Example workload:** 10,000 embedding requests/day
- Instance: g4dn.xlarge (T4 GPU) = $0.526/hour
- Throughput: ~500 requests/hour with 1 GPU
- Hours needed: 20 hours/day
- **Monthly cost: $315**

### With ONNX Optimization

**Same workload:** 10,000 embedding requests/day
- Instance: g4dn.xlarge (T4 GPU) = $0.526/hour
- Throughput: ~1500 requests/hour (3x faster)
- Hours needed: 7 hours/day
- **Monthly cost: $110** ✅ **65% savings**

OR run on smaller/cheaper CPU instance:
- Instance: c6i.2xlarge (CPU) = $0.34/hour
- Throughput: ~800 requests/hour (ONNX is fast on CPU)
- Hours needed: 13 hours/day
- **Monthly cost: $133** ✅ **58% savings**

## Pre-Deployment Checklist

### Code & Testing
- [ ] All tests passing (`./run_tests.sh --slow`)
- [ ] Load testing completed (see below)
- [ ] Error scenarios handled
- [ ] Logging configured for production

### ONNX (if using)
- [ ] ONNX models converted and tested
- [ ] Accuracy verified (embeddings match within 1e-4)
- [ ] Performance benchmarked
- [ ] Fallback to PyTorch configured

### Infrastructure
- [ ] Docker image built and tested
- [ ] Environment variables configured
- [ ] Health checks working
- [ ] Resource limits set (memory, CPU)

### Monitoring
- [ ] Metrics endpoint configured
- [ ] Logging aggregation setup
- [ ] Alerting rules defined
- [ ] Dashboard created

### Security
- [ ] API authentication enabled (if needed)
- [ ] Rate limiting configured
- [ ] HTTPS/TLS configured
- [ ] Network policies applied

## Load Testing

### Test 1: Embedding Performance

```python
# load_test_embeddings.py
import asyncio
import aiohttp
import time

async def test_embedding_load():
    texts = ["Test document " + str(i) for i in range(1000)]
    url = "http://localhost:11540/v1/embeddings"

    start = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        tasks = []
        for text in texts:
            task = session.post(url, json={
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "input": text
            })
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - start
    print(f"1000 embeddings in {elapsed:.2f}s")
    print(f"Throughput: {1000/elapsed:.1f} req/s")

asyncio.run(test_embedding_load())
```

**Expected results:**
- PyTorch: ~15-20 req/s
- ONNX: ~40-60 req/s

### Test 2: Concurrent Requests

```bash
# Using Apache Bench
ab -n 1000 -c 10 \
  -p embedding_request.json \
  -T application/json \
  http://localhost:11540/v1/embeddings
```

**Monitor:**
- Request latency (p50, p95, p99)
- Error rate
- Memory usage
- GPU utilization

## Deployment Options

### Option 1: Docker Compose (Simple)

```yaml
# docker-compose.yml
version: '3.8'
services:
  universal-runtime:
    build: .
    environment:
      - RUNTIME_BACKEND=onnx
      - ONNX_PROVIDER=CUDAExecutionProvider
    ports:
      - "11540:11540"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### Option 2: Kubernetes (Scale)

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: universal-runtime
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: runtime
        image: universal-runtime:latest
        env:
        - name: RUNTIME_BACKEND
          value: "onnx"
        resources:
          limits:
            nvidia.com/gpu: 1
```

### Option 3: Serverless (Spot workloads)

Consider Modal, Banana, or RunPod for:
- Bursty traffic
- Cost optimization
- Auto-scaling

## Monitoring Dashboard

### Key Metrics to Track

**Request Metrics:**
- `http_requests_total` - Total requests
- `http_request_duration_seconds` - Latency histogram
- `http_requests_in_flight` - Current concurrent requests

**Model Metrics:**
- `model_load_duration_seconds` - Model loading time
- `model_inference_duration_seconds` - Inference time per model
- `model_memory_usage_bytes` - Memory per model

**System Metrics:**
- `process_cpu_usage` - CPU utilization
- `process_memory_usage` - RAM usage
- `gpu_utilization` - GPU usage %
- `gpu_memory_used` - VRAM usage

### Sample Grafana Queries

```promql
# P95 embedding latency
histogram_quantile(0.95,
  rate(model_inference_duration_seconds_bucket{model_type="encoder"}[5m])
)

# Requests per second
rate(http_requests_total[1m])

# Error rate
rate(http_requests_total{status=~"5.."}[5m]) /
rate(http_requests_total[5m])
```

## Troubleshooting Production Issues

### Issue: High Latency

**Symptoms:** Slow response times

**Check:**
1. GPU utilization - should be >60% under load
2. Model backend - ensure ONNX is being used
3. Batch size - increase for better throughput
4. Network - check for bandwidth issues

### Issue: Out of Memory

**Symptoms:** OOM errors, crashes

**Solutions:**
1. Reduce concurrent requests
2. Implement model unloading
3. Use smaller models
4. Add more VRAM/RAM

### Issue: Low Throughput

**Symptoms:** Can't handle request volume

**Solutions:**
1. Enable ONNX backend
2. Add horizontal scaling (more instances)
3. Implement request batching
4. Optimize model loading

## Success Metrics

After deploying to production, track:

✅ **Performance:**
- Embedding latency <10ms (p95)
- Text generation latency <100ms (p95)
- Image generation <10s (p95)

✅ **Reliability:**
- Uptime >99.9%
- Error rate <0.1%
- No OOM crashes

✅ **Efficiency:**
- GPU utilization >60%
- Cost per 1M requests <$X target
- Models load in <30s

✅ **Scale:**
- Handle target RPS
- Auto-scale working
- No rate limiting needed

## Quick Wins Summary

| Optimization | Time | Impact | Do It? |
|--------------|------|--------|--------|
| ONNX Encoder | 30 min | 3x faster | ✅ YES |
| Monitoring | 2 hours | Visibility | ✅ YES |
| torch.compile Diffusion | 5 min | 1.5x faster | ✅ YES |
| ONNX CausalLM | 2 hours | 1.4x faster | ⚠️ Maybe |
| Batching | 6 hours | 10x throughput | ⚠️ If needed |
| ONNX Diffusion | Days | Unknown | ❌ NO |

## Final Recommendation

For LlamaFarm's RAG use case:

**Week 1:**
1. Convert EncoderModel to ONNX (30 min)
2. Deploy to staging (1 hour)
3. Load test and verify (1 hour)
4. Deploy to production (1 hour)

**Week 2:**
1. Add monitoring (2 hours)
2. Set up alerts (1 hour)
3. Optimize based on metrics (ongoing)

**Result:** 3x faster embeddings, production-ready monitoring, <1 day of work.

You don't need to do everything at once. Start with encoder ONNX, monitor, and iterate based on real usage patterns.
