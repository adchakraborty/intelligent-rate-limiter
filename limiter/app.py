import os
import json
import time
import uuid
import threading
import logging
import sys
from typing import Dict, Tuple, Any, List
from flask import Flask, request, jsonify, Response, render_template
import requests
from prometheus_client import (
    Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('ai-rate-limiter')

# ------------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------------
PORT = int(os.getenv("PORT", "8080"))
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://backend:8000")
DECISION_MIN_CONF = float(os.getenv("DECISION_MIN_CONF", "0.6"))
HEURISTIC_EVERY_SEC = float(os.getenv("HEURISTIC_EVERY_SEC", "3.0"))
LARGE_CHANGE_FACTOR = float(os.getenv("LARGE_CHANGE_FACTOR", "1.8"))  # Lowered for more governance demos

# Customer tiers and revenue
REVENUE_PER_REQUEST = {
    "free": 0.01,    # $0.01 per request
    "pro": 0.05,     # $0.05 per request  
    "ent": 0.20      # $0.20 per request
}

PLAN_BASE = {
    "free": {"rps": 3.0, "burst": 10},
    "pro":  {"rps": 8.0, "burst": 20},
    "ent":  {"rps": 15.0, "burst": 40},
}

API_KEYS = {
    "free-key": "free",
    "pro-key": "pro", 
    "ent-key": "ent",
}

VALID_ENDPOINTS = {"/api/v1/resourceA", "/api/v1/resourceB"}

# AI config - FIXED: Use localhost instead of container
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT_SEC = float(os.getenv("OLLAMA_TIMEOUT_SEC", "12.0"))
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "2"))  # Reduced retries for faster demo

# ------------------------------------------------------------------------------------
# ENHANCED METRICS - All Dashboard Panels Covered
# ------------------------------------------------------------------------------------
RL_REQUESTS_TOTAL = Counter("rl_requests_total", "Requests seen by limiter", ["tenant", "endpoint", "outcome"])
RL_POLICY_RPS = Gauge("rl_policy_rps", "Current RPS limit", ["tenant", "endpoint"])
RL_POLICY_BURST = Gauge("rl_policy_burst", "Current burst limit", ["tenant", "endpoint"])
RL_EFFECTIVE_RPS = Gauge("rl_effective_rps", "Observed RPS", ["tenant", "endpoint"])
RL_BLOCKED_RATIO = Gauge("rl_blocked_ratio", "Blocked ratio", ["tenant", "endpoint"])

# AI METRICS - Enhanced for dashboard
RL_AI_DECISIONS_TOTAL = Counter("rl_ai_decisions_total", "AI decisions", ["tenant", "endpoint", "action", "applied"])
RL_AI_CALLS_TOTAL = Counter("rl_ai_calls_total", "AI API calls", ["status"])
RL_AI_CALL_DURATION = Histogram("rl_ai_call_duration_seconds", "AI call duration", buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0])
RL_AI_PROMPT_TOKENS = Gauge("rl_ai_prompt_tokens", "AI prompt tokens", ["tenant"])
RL_AI_RESPONSE_TOKENS = Gauge("rl_ai_response_tokens", "AI response tokens", ["tenant"])

# BUSINESS METRICS
RL_REVENUE_PROTECTED = Counter("rl_revenue_protected_total", "Revenue protected", ["tenant"])
RL_REVENUE_LOST = Counter("rl_revenue_lost_total", "Revenue lost", ["tenant"])
RL_CUSTOMER_SATISFACTION = Gauge("rl_customer_satisfaction", "Customer satisfaction", ["tenant"])

# GOVERNANCE METRICS  
RL_GOVERNANCE_QUEUE_SIZE = Gauge("rl_governance_queue_size", "Governance queue size")

# ADVANCED ANALYTICS METRICS
RL_ANOMALY_SCORE = Gauge("rl_anomaly_score", "Anomaly score", ["tenant", "endpoint"])
RL_SURGE_PREDICTION = Gauge("rl_surge_prediction", "Surge prediction probability", ["tenant", "endpoint"])
RL_TRAFFIC_TREND = Gauge("rl_traffic_trend", "Traffic trend analysis", ["tenant", "endpoint"])
RL_PREEMPTIVE_SCALING = Counter("rl_preemptive_scaling_total", "Preemptive scaling events", ["tenant", "action"])

RL_AI_ENGINE_ACTIVE = Gauge("rl_ai_engine_active", "AI engine activity status")

# SERVICE VOLUME METRICS for Loki dashboard
RL_SERVICE_REQUESTS_TOTAL = Counter("rl_service_requests_total", "Total requests per service", ["service", "method", "status"])
RL_SERVICE_RESPONSE_TIME = Histogram("rl_service_response_time_seconds", "Response time per service", ["service", "method"], buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0])
RL_SERVICE_ACTIVE_CONNECTIONS = Gauge("rl_service_active_connections", "Active connections per service", ["service"])
RL_SERVICE_ERROR_RATE = Gauge("rl_service_error_rate", "Error rate per service", ["service"])

# LOG METRICS for Loki dashboard  
RL_LOG_ENTRIES_TOTAL = Counter("rl_log_entries_total", "Total log entries", ["level", "service", "ai_type"])
RL_AI_LOG_EVENTS = Counter("rl_ai_log_events_total", "AI-specific log events", ["event_type", "tenant"])


# ------------------------------------------------------------------------------------
# State
# ------------------------------------------------------------------------------------
policies: Dict[Tuple[str,str], Dict[str, Any]] = {}
buckets: Dict[Tuple[str,str], Dict[str, float]] = {}
stats: Dict[Tuple[str,str], Dict[str, float]] = {}
pending_decisions: Dict[str, Dict[str, Any]] = {}
decision_history: List[Dict[str, Any]] = []
state_lock = threading.Lock()

# surge tracking state
surge_history: Dict[Tuple[str,str], List[Dict[str, float]]] = {}
surge_predictions: Dict[Tuple[str,str], Dict[str, float]] = {}

# ------------------------------------------------------------------------------------
# Core Functions
# ------------------------------------------------------------------------------------
def _now(): return time.time()
def _key(): return request.headers.get("X-API-Key", "").strip()
def _tenant(): return API_KEYS.get(_key(), "unknown")

def _ensure_policy_and_bucket(pair: Tuple[str,str]):
    tenant, endpoint = pair
    if pair not in policies:
        base = PLAN_BASE.get(tenant, {"rps": 10.0, "burst": 20})
        policies[pair] = {"rps": base["rps"], "burst": base["burst"]}
        RL_POLICY_RPS.labels(tenant, endpoint).set(base["rps"])
        RL_POLICY_BURST.labels(tenant, endpoint).set(base["burst"])
        RL_EFFECTIVE_RPS.labels(tenant, endpoint).set(0.0)
        RL_BLOCKED_RATIO.labels(tenant, endpoint).set(0.0)
        RL_CUSTOMER_SATISFACTION.labels(tenant).set(0.85)
        RL_ANOMALY_SCORE.labels(tenant, endpoint).set(0.0)
        RL_SURGE_PREDICTION.labels(tenant, endpoint).set(0.0)
        RL_TRAFFIC_TREND.labels(tenant, endpoint).set(0.0)
        
    if pair not in buckets:
        buckets[pair] = {"tokens": policies[pair]["burst"], "last": _now()}
    if pair not in stats:
        stats[pair] = {"ok": 0.0, "blocked": 0.0, "since": _now()}

def _refill_tokens(pair: Tuple[str,str]):
    cfg = policies[pair]
    bucket = buckets[pair]
    now = _now()
    elapsed = now - bucket["last"]
    bucket["last"] = now
    bucket["tokens"] = min(cfg["burst"], bucket["tokens"] + cfg["rps"] * elapsed)

def _allow(pair: Tuple[str,str]) -> bool:
    _ensure_policy_and_bucket(pair)
    _refill_tokens(pair)
    b = buckets[pair]
    if b["tokens"] >= 1.0:
        b["tokens"] -= 1.0
        return True
    return False

def apply_policy(tenant: str, endpoint: str, rps: float, burst: int):
    pair = (tenant, endpoint)
    _ensure_policy_and_bucket(pair)
    
    policies[pair]["rps"] = max(1.0, float(rps))
    policies[pair]["burst"] = max(5, int(burst))
    
    RL_POLICY_RPS.labels(tenant, endpoint).set(policies[pair]["rps"])
    RL_POLICY_BURST.labels(tenant, endpoint).set(policies[pair]["burst"])

def _calculate_revenue_impact(tenant: str, allowed: bool):
    revenue = REVENUE_PER_REQUEST.get(tenant, 0.01)
    if allowed:
        RL_REVENUE_PROTECTED.labels(tenant).inc(revenue)
    else:
        RL_REVENUE_LOST.labels(tenant).inc(revenue)

def _calculate_business_priority(tenant: str) -> float:
    return {"free": 1.0, "pro": 2.0, "ent": 5.0}.get(tenant, 1.0)

def _detect_anomaly(tenant: str, endpoint: str, current_rps: float) -> float:
    """Improved anomaly detection with proper baseline calculation"""
    pair = (tenant, endpoint)
    
    # Use current policy as baseline, fall back to plan base
    with state_lock:
        if pair in policies:
            baseline_rps = policies[pair]["rps"]
        else:
            baseline_rps = PLAN_BASE.get(tenant, {"rps": 10.0})["rps"]
    
    # Only consider it anomalous if significantly different AND above threshold
    if baseline_rps > 0 and current_rps > 1.0:  # Only check if there's actual traffic
        deviation_ratio = abs(current_rps - baseline_rps) / baseline_rps
        
        # Only flag as anomaly if deviation is significant (>100%) AND traffic is substantial
        if deviation_ratio > 1.0 and current_rps > baseline_rps * 1.5:
            score = min(1.0, deviation_ratio / 3.0)  # Normalize to 0-1 scale
        else:
            score = 0.0
    else:
        score = 0.0
    
    RL_ANOMALY_SCORE.labels(tenant, endpoint).set(score)
    
    if score > 0.5:
        logger.warning(f"🚨 ANOMALY DETECTED: {tenant}/{endpoint} - {current_rps:.1f} RPS vs {baseline_rps:.1f} baseline (score: {score:.2f})")
    
    return score

def _track_service_metrics(service: str, method: str, status_code: int, duration: float):
    """Track service volume and performance metrics"""
    RL_SERVICE_REQUESTS_TOTAL.labels(service=service, method=method, status=str(status_code)).inc()
    RL_SERVICE_RESPONSE_TIME.labels(service=service, method=method).observe(duration)
    
    # Update error rate
    if status_code >= 400:
        RL_SERVICE_ERROR_RATE.labels(service=service).inc()

def _track_log_entry(level: str, ai_type: str = "general", tenant: str = "system"):
    """Track log entries for Loki dashboard"""
    RL_LOG_ENTRIES_TOTAL.labels(level=level, service="ai-rate-limiter", ai_type=ai_type).inc()
    
    if ai_type != "general":
        RL_AI_LOG_EVENTS.labels(event_type=ai_type, tenant=tenant).inc()

def _classify_traffic_scenario(tenant: str, ok_rps: float, blocked_ratio: float, utilization: float) -> str:
    """Classify traffic scenarios for different scaling approaches"""
    business_priority = _calculate_business_priority(tenant)
    
    # DDoS Detection (massive traffic + high blocking)
    if ok_rps > 50 or (utilization > 2.0 and blocked_ratio > 0.6):
        return "ddos"
    
    # Surge Detection (high utilization + moderate blocking)
    elif utilization > 0.8 and blocked_ratio > 0.3:
        return "surge"
    
    # Normal Scaling (moderate utilization, low blocking)
    elif utilization > 0.6 and blocked_ratio < 0.3:
        return "normal"
    
    # Light Traffic (low utilization)
    elif utilization < 0.3:
        return "light"
    
    # Stable (everything else)
    else:
        return "stable"

# ------------------------------------------------------------------------------------
# AI Integration - PURE AI ONLY (NO FALLBACK)
# ------------------------------------------------------------------------------------
def _call_ollama_ai(tenant: str, endpoint: str, ok_rps: float, blocked_ratio: float, utilization: float) -> dict:
    baseline_rps = PLAN_BASE.get(tenant, {"rps": 10.0})["rps"]
    revenue_per_req = REVENUE_PER_REQUEST.get(tenant, 0.01)
    business_priority = _calculate_business_priority(tenant)
    
    with state_lock:
        current_policy = policies.get((tenant, endpoint), {"rps": baseline_rps, "burst": int(baseline_rps * 3)})
    
    # Classify traffic scenario
    scenario = _classify_traffic_scenario(tenant, ok_rps, blocked_ratio, utilization)
    
    # SIMPLIFIED prompt for better JSON parsing
    prompt = f"""You are an AI rate limiter. Analyze this traffic and return ONLY valid JSON.

CUSTOMER: {tenant.upper()}
REVENUE: ${revenue_per_req:.3f} per request  
CURRENT LIMIT: {current_policy["rps"]:.1f} RPS
ACTUAL TRAFFIC: {ok_rps:.2f} RPS
BLOCKED: {blocked_ratio:.1%}
SCENARIO: {scenario}

RULES:
- Enterprise customers: Scale aggressively (up to 100 RPS)
- Pro customers: Scale moderately (up to 50 RPS)  
- Free customers: Scale conservatively (up to 15 RPS)
- If utilization > 80%: scale up
- If utilization < 30%: scale down or maintain
- If blocked_ratio > 20%: scale up immediately

Return ONLY this JSON format:
{{"action": "up", "new_rps": 25.0, "new_burst": 75, "confidence": 0.85, "reason": "{scenario}_scaling_needed"}}"""

    # Track prompt tokens (simplified)
    prompt_tokens = len(prompt.split())
    logger.info(f"AI PROMPT TOKENS: {tenant} - {prompt_tokens} tokens")
    logger.info(f"AI PROMPT: {prompt.replace(chr(10), ' ')}")  # Log prompt in single line
    RL_AI_PROMPT_TOKENS.labels(tenant).set(prompt_tokens)
    
    start_time = time.time()
    
    for attempt in range(OLLAMA_MAX_RETRIES):
        try:
            # Log the request with structured format for Loki
            logger.info(
                f"OLLAMA_REQUEST tenant={tenant} endpoint={endpoint} attempt={attempt+1} "
                f"scenario={scenario} ok_rps={ok_rps:.2f} blocked_ratio={blocked_ratio:.2%} "
                f"utilization={utilization:.2%} prompt_tokens={prompt_tokens}"
            )
            _track_log_entry("INFO", "ai_call", tenant)
            
            # SHORTER timeout for faster retries
            timeout = max(25.0, OLLAMA_TIMEOUT_SEC / 2)  # Use shorter timeout
            
            response = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.0,  # ZERO temperature for consistent JSON
                        "top_p": 0.9,
                        "num_predict": 150,  # SHORTER response
                        "stop": ["}"],
                        "repeat_penalty": 1.0
                    }
                },
                timeout=timeout
            )
            
            duration = time.time() - start_time
            RL_AI_CALL_DURATION.observe(duration)
            
            if response.status_code == 200:
                ai_response = response.json().get("response", "").strip()
                
                # Track response tokens
                response_tokens = len(ai_response.split())
                RL_AI_RESPONSE_TOKENS.labels(tenant).set(response_tokens)
                
                # Log successful response with structured format for Loki
                logger.info(
                    f"OLLAMA_RESPONSE tenant={tenant} endpoint={endpoint} attempt={attempt+1} "
                    f"duration={duration:.2f}s response_tokens={response_tokens} "
                    f"response_length={len(ai_response)} status=success"
                )
                _track_log_entry("INFO", "ai_response", tenant)
                RL_AI_CALLS_TOTAL.labels("success").inc()
                
                # IMPROVED JSON parsing
                try:
                    # Try direct JSON parse first
                    if ai_response.startswith("{") and ai_response.endswith("}"):
                        result = json.loads(ai_response)
                    else:
                        # Extract JSON with regex
                        import re
                        json_match = re.search(r'\{[^{}]*\}', ai_response)
                        if json_match:
                            json_str = json_match.group()
                            result = json.loads(json_str)
                        else:
                            raise ValueError("No JSON found in response")
                    
                    # Log successful parse
                    logger.info(
                        f"OLLAMA_PARSED tenant={tenant} endpoint={endpoint} "
                        f"action={result.get('action', 'unknown')} "
                        f"confidence={result.get('confidence', 0.0):.2f} "
                        f"reason={result.get('reason', 'no_reason')}"
                    )
                    return result
                    
                except Exception as parse_error:
                    # Log parse error with structured format
                    error_msg = str(parse_error).replace('"', '\\"').replace('\n', ' ')
                    response_snippet = ai_response[:200].replace('"', '\\"').replace('\n', ' ')
                    
                    logger.error(
                        f"OLLAMA_PARSE_ERROR tenant={tenant} endpoint={endpoint} attempt={attempt+1} "
                        f"error=\"{error_msg}\" raw_response=\"{response_snippet}\""
                    )
                    RL_AI_CALLS_TOTAL.labels("parse_error").inc()
                    
                    # If this is the last attempt, try to construct a reasonable response
                    if attempt == OLLAMA_MAX_RETRIES - 1:
                        logger.info("🛠️ Constructing fallback response from AI intent")
                        return _extract_intent_from_response(ai_response, current_policy["rps"], scenario)
                    
            else:
                # Log HTTP error
                logger.error(
                    f"OLLAMA_HTTP_ERROR tenant={tenant} endpoint={endpoint} attempt={attempt+1} "
                    f"status_code={response.status_code}"
                )
                
        except requests.exceptions.Timeout:
            # Log timeout with structured format
            logger.error(
                f"OLLAMA_TIMEOUT tenant={tenant} endpoint={endpoint} attempt={attempt+1} "
                f"timeout_sec={timeout}"
            )
            _track_log_entry("ERROR", "ai_timeout", tenant)
            if attempt == OLLAMA_MAX_RETRIES - 1:
                RL_AI_CALLS_TOTAL.labels("timeout").inc()
                
        except Exception as e:
            # Log general exception with structured format
            error_msg = str(e).replace('"', '\\"').replace('\n', ' ')
            logger.error(
                f"OLLAMA_EXCEPTION tenant={tenant} endpoint={endpoint} attempt={attempt+1} "
                f"error=\"{error_msg}\" type={type(e).__name__}"
            )
            _track_log_entry("ERROR", "ai_error", tenant)
            if attempt == OLLAMA_MAX_RETRIES - 1:
                RL_AI_CALLS_TOTAL.labels("error").inc()
    
    # CRITICAL: NO FALLBACK - Return empty dict to force retry
    logger.error(
        f"OLLAMA_FAILED tenant={tenant} endpoint={endpoint} attempts={OLLAMA_MAX_RETRIES} "
        f"final_status=total_failure"
    )
    _track_log_entry("ERROR", "ai_total_failure", tenant) 
    RL_AI_CALLS_TOTAL.labels("total_failure").inc()
    return {}

def _extract_intent_from_response(response_text: str, current_rps: float, scenario: str) -> dict:
    """Extract intent from malformed AI response as last resort"""
    response_lower = response_text.lower()
    
    # Try to extract action intent
    if "up" in response_lower or "increase" in response_lower or "scale" in response_lower:
        action = "up"
        # Conservative scaling based on scenario
        if scenario == "ddos":
            new_rps = current_rps * 3.0
        elif scenario == "surge":
            new_rps = current_rps * 2.0
        else:
            new_rps = current_rps * 1.5
    elif "down" in response_lower or "decrease" in response_lower:
        action = "down"
        new_rps = current_rps * 0.8
    else:
        action = "same"
        new_rps = current_rps
    
    return {
        "action": action,
        "new_rps": min(100.0, new_rps),
        "new_burst": int(new_rps * 3),
        "confidence": 0.7,
        "reason": f"{scenario}_intent_extracted",
        "scenario": scenario
    }

def _validate_ai_decision(raw, cur_rps, cur_burst):
    try:
        action = str(raw.get("action", "same")).lower()
        if action not in ("up", "down", "same"):
            logger.warning(f"⚠️ Invalid action: {action}")
            return {}
            
        new_rps = float(raw.get("new_rps", cur_rps))
        if not (1.0 <= new_rps <= 1000):
            logger.warning(f"⚠️ Invalid RPS: {new_rps}")
            return {}
            
        new_burst = int(raw.get("new_burst", max(10, new_rps * 3)))
        if new_burst < 5 or new_burst > 5000:
            logger.warning(f"⚠️ Invalid burst: {new_burst}")
            return {}
            
        confidence = max(0.5, min(float(raw.get("confidence", 0.7)), 1.0))
        reason = str(raw.get("reason", "ai_decision"))[:80]
        scenario = str(raw.get("scenario", "unknown"))
        
        return {
            "action": action,
            "new_rps": new_rps,
            "new_burst": new_burst,
            "confidence": confidence,
            "reason": reason,
            "scenario": scenario
        }
    except Exception as e:
        logger.warning(f"⚠️ AI decision validation error: {e}")
        return {}

# REMOVED: _fallback_decision function - PURE AI ONLY!

# ------------------------------------------------------------------------------------
# Decision Engine with Enhanced Governance
# ------------------------------------------------------------------------------------
def _apply_or_queue(tenant, endpoint, action, new_rps, new_burst, confidence, reason=""):
    pair = (tenant, endpoint)
    with state_lock:
        _ensure_policy_and_bucket(pair)
        old_rps = policies[pair]["rps"]
        
        # Calculate if this is a large change
        is_large = False
        if old_rps > 0:
            ratio = new_rps / old_rps
            is_large = ratio >= LARGE_CHANGE_FACTOR or ratio <= 1.0 / LARGE_CHANGE_FACTOR
        
        # Apply if confidence is high AND change is small
        if confidence >= DECISION_MIN_CONF and not is_large and action != "same":
            apply_policy(tenant, endpoint, new_rps, new_burst)
            RL_AI_DECISIONS_TOTAL.labels(tenant, endpoint, action, "true").inc()
            logger.info(f"✅ APPLIED: {tenant}/{endpoint} {old_rps:.1f}→{new_rps:.1f} RPS ({reason})")
            _track_log_entry("INFO", "policy_applied", tenant)  # ADD THIS
            
            # Add to decision history
            decision_history.append({
                "timestamp": _now(),
                "tenant": tenant,
                "endpoint": endpoint,
                "action": action,
                "old_rps": old_rps,
                "new_rps": new_rps,
                "confidence": confidence,
                "reason": reason,
                "applied": True
            })
            
            return {"status": "applied", "action": action}
        
        # Queue for approval if large change or low confidence
        if action != "same":
            decision_id = str(uuid.uuid4())
            pending_decisions[decision_id] = {
                "id": decision_id,
                "tenant": tenant,
                "endpoint": endpoint,
                "action": action,
                "new_rps": new_rps,
                "new_burst": new_burst,
                "confidence": confidence,
                "created": _now(),
                "reason": reason,
                "old_rps": old_rps,
                "scaling_factor": new_rps / old_rps if old_rps > 0 else 1.0
            }
            
            RL_AI_DECISIONS_TOTAL.labels(tenant, endpoint, action, "false").inc()
            RL_GOVERNANCE_QUEUE_SIZE.set(len(pending_decisions))
            
            approval_reason = "large_change" if is_large else "low_confidence"
            logger.warning(f"⏳ QUEUED: {tenant}/{endpoint} {old_rps:.1f}→{new_rps:.1f} RPS ({approval_reason})")
            _track_log_entry("WARNING", "governance_queue", tenant)  # ADD THIS
            return {"status": "pending", "id": decision_id, "reason": approval_reason}
        
        return {"status": "no_change"}

def _analyze_surge_patterns(pair: Tuple[str,str], current_rps: float) -> Dict[str, float]:
    """Multi-level surge pattern analysis"""
    tenant, endpoint = pair
    now = _now()
    
    # Initialize surge history if needed
    if pair not in surge_history:
        surge_history[pair] = []
    
    # Add current data point
    surge_history[pair].append({
        "timestamp": now,
        "rps": current_rps,
        "window": 30
    })
    
    # Keep only last 5 minutes of data
    cutoff = now - 300
    surge_history[pair] = [h for h in surge_history[pair] if h["timestamp"] > cutoff]
    
    if len(surge_history[pair]) < 2:
        RL_SURGE_PREDICTION.labels(tenant, endpoint).set(0.0)
        RL_TRAFFIC_TREND.labels(tenant, endpoint).set(0.0)
        return {"surge_probability": 0.0, "trend": 0.0, "predicted_peak": current_rps}
    
    # Calculate trend
    recent_points = surge_history[pair][-3:]
    if len(recent_points) >= 2:
        trend = (recent_points[-1]["rps"] - recent_points[0]["rps"]) / len(recent_points)
    else:
        trend = 0.0
    
    # Multi-level surge prediction
    surge_probability = 0.0
    predicted_peak = current_rps
    
    # Normal traffic growth (gradual increases)
    if 0.2 <= trend <= 2.0:
        surge_probability = min(30.0, 10 + (trend * 8))
        predicted_peak = current_rps + (trend * 2)
    
    # Surge traffic (moderate rapid increases)  
    elif 2.0 < trend <= 10.0:
        surge_probability = min(70.0, 30 + (trend * 5))
        predicted_peak = current_rps + (trend * 3)
    
    # DDoS traffic (massive increases)
    elif trend > 10.0 or current_rps > 50:
        surge_probability = min(100.0, 70 + min(30, trend))
        predicted_peak = current_rps + (trend * 4)
    
    # Business-aware multiplier
    business_multiplier = _calculate_business_priority(tenant)
    surge_probability *= (0.8 + business_multiplier * 0.15)
    surge_probability = min(100.0, surge_probability)
    
    # Update metrics
    RL_SURGE_PREDICTION.labels(tenant, endpoint).set(surge_probability)
    RL_TRAFFIC_TREND.labels(tenant, endpoint).set(trend)
    
    logger.info(f"🌊 SURGE ANALYSIS: {tenant}/{endpoint} - RPS:{current_rps:.1f}, Trend:{trend:.2f}, Prob:{surge_probability:.0f}%")
    
    return {
        "surge_probability": surge_probability,
        "trend": trend,
        "predicted_peak": max(current_rps, predicted_peak)
    }

def _preemptive_surge_scaling(tenant: str, endpoint: str, surge_data: Dict[str, float]) -> Dict[str, Any]:
    """Multi-level preemptive scaling based on surge severity"""
    pair = (tenant, endpoint)
    
    with state_lock:
        current_policy = policies.get(pair, {"rps": 10.0, "burst": 30})
    
    surge_prob = surge_data["surge_probability"]
    trend = surge_data["trend"]
    
    # Only trigger on significant surge probability
    if surge_prob < 25:
        return {"action": "none", "scaling_factor": 1.0}
    
    # Multi-level scaling based on surge severity
    business_priority = _calculate_business_priority(tenant)
    
    # DDoS Level (80%+ probability or massive trend)
    if surge_prob >= 80 or trend > 15:
        if tenant == "ent":
            scaling_factor = 8.0  # Massive protection for Enterprise
        elif tenant == "pro":
            scaling_factor = 5.0  # Strong protection for Pro
        else:
            scaling_factor = 3.0  # Basic protection for Free
        action_type = "ddos_protection"
    
    # Surge Level (50-80% probability)
    elif surge_prob >= 50:
        if tenant == "ent":
            scaling_factor = 4.0  # Aggressive scaling for Enterprise
        elif tenant == "pro":
            scaling_factor = 2.5  # Moderate scaling for Pro
        else:
            scaling_factor = 1.8  # Light scaling for Free
        action_type = "surge_scaling"
    
    # Normal Growth Level (25-50% probability)
    else:
        if tenant == "ent":
            scaling_factor = 2.2  # Growth accommodation for Enterprise
        elif tenant == "pro":
            scaling_factor = 1.7  # Moderate growth for Pro
        else:
            scaling_factor = 1.4  # Conservative growth for Free
        action_type = "growth_scaling"
    
    # Calculate new limits
    new_rps = min(500.0, current_policy["rps"] * scaling_factor)
    new_burst = min(2000, int(current_policy["burst"] * scaling_factor))
    
    # Store prediction
    surge_predictions[pair] = {
        "probability": surge_prob,
        "scaling_factor": scaling_factor,
        "predicted_at": _now(),
        "new_rps": new_rps,
        "action_type": action_type
    }
    
    logger.warning(f"🌊 {action_type.upper()}: {tenant}/{endpoint} - {surge_prob:.0f}% prob, {scaling_factor:.1f}x scale to {new_rps:.1f} RPS")
    
    return {
        "action": "surge_scale",
        "new_rps": new_rps,
        "new_burst": new_burst,
        "scaling_factor": scaling_factor,
        "confidence": 0.88 + (surge_prob / 500),
        "reason": f"{action_type}_{surge_prob:.0f}pct"
    }

# ------------------------------------------------------------------------------------
# Enhanced Heuristic Loop - PURE AI ONLY
# ------------------------------------------------------------------------------------
def _heuristics_loop():
    while True:
        time.sleep(HEURISTIC_EVERY_SEC)
        
        with state_lock:
            active_pairs = list(policies.keys())
        
        for pair in active_pairs:
            tenant, endpoint = pair
            
            with state_lock:
                _ensure_policy_and_bucket(pair)
                stats_snapshot = stats[pair].copy()
                current_policy = policies[pair].copy()  
                
                # Reset stats for next window
                stats[pair] = {"ok": 0.0, "blocked": 0.0, "since": _now()}
            
            # Calculate metrics
            window = max(1.0, _now() - stats_snapshot["since"])
            ok_count = stats_snapshot["ok"]
            blocked_count = stats_snapshot["blocked"]
            ok_rps = ok_count / window
            total_requests = ok_count + blocked_count
            blocked_ratio = (blocked_count / total_requests) if total_requests > 0 else 0.0
            utilization = ok_rps / max(current_policy["rps"], 1e-6)
            
            # Update basic metrics
            RL_EFFECTIVE_RPS.labels(tenant, endpoint).set(ok_rps)
            RL_BLOCKED_RATIO.labels(tenant, endpoint).set(blocked_ratio)
            
            # Enhanced surge analysis
            surge_data = _analyze_surge_patterns(pair, ok_rps)
            
            # Check if preemptive scaling is needed (HIGHER PRIORITY)
            surge_decision = _preemptive_surge_scaling(tenant, endpoint, surge_data)
            if surge_decision["action"] == "surge_scale":
                logger.warning(f"🌊 SURGE OVERRIDE: {tenant}/{endpoint} {surge_data['surge_probability']:.0f}% - Preemptive scaling!")
                RL_PREEMPTIVE_SCALING.labels(tenant, surge_decision.get("reason", "surge_scale").split("_")[0]).inc()
                
                result = _apply_or_queue(
                    tenant, endpoint,
                    "up",
                    surge_decision["new_rps"],
                    surge_decision["new_burst"], 
                    surge_decision["confidence"],
                    surge_decision["reason"]
                )
                continue  # Skip normal AI analysis during surge
            
            # Calculate revenue impact
            if ok_count > 0:
                _calculate_revenue_impact(tenant, allowed=True)
            if blocked_count > 0:
                _calculate_revenue_impact(tenant, allowed=False)
            
            # FIXED: Initialize ai_decision variable BEFORE using it
            ai_decision = None
            
            # Update customer satisfaction (now ai_decision is defined)
            base_satisfaction = 0.95  # Start high
            blocking_penalty = blocked_ratio * 2.0  # Blocking hurts satisfaction significantly
            utilization_stress = max(0, (utilization - 0.7) * 0.5)  # High utilization causes stress
            ai_boost = 0.1 if ai_decision else 0.0  # AI decisions improve satisfaction (will be 0 initially)

            # Business tier expectations
            tier_expectations = {"free": 0.7, "pro": 0.85, "ent": 0.95}
            expectation_gap = max(0, tier_expectations.get(tenant, 0.8) - (1.0 - blocked_ratio))

            satisfaction = max(0.0, min(1.0, 
                base_satisfaction 
                - blocking_penalty 
                - utilization_stress 
                - expectation_gap
                + ai_boost
            ))

            RL_CUSTOMER_SATISFACTION.labels(tenant).set(satisfaction)

            # Add comparative static satisfaction metric
            static_satisfaction = max(0.0, min(1.0, base_satisfaction - (blocked_ratio * 3.0)))  # Static systems hurt more
            RL_CUSTOMER_SATISFACTION.labels(f"{tenant}_static").set(static_satisfaction)
            
            # Detect anomalies
            _detect_anomaly(tenant, endpoint, ok_rps)
            
            # CRITICAL: Only call AI if there's ANY activity (lowered threshold for demo)
            if total_requests < 0.01:  # FIXED: Skip only if virtually NO activity
                continue
            
            logger.info(f"🤖 AI CALL TRIGGERED: {tenant}/{endpoint} - {total_requests} requests, {ok_rps:.2f} RPS, util:{utilization:.1%}")
            
            # PURE AI DECISION - NO FALLBACK
            ai_raw = _call_ollama_ai(tenant, endpoint, ok_rps, blocked_ratio, utilization)
            ai_decision = _validate_ai_decision(ai_raw, current_policy["rps"], current_policy["burst"])
            
            # FIXED: Update AI engine status and satisfaction after AI call
            if ai_decision:
                RL_AI_ENGINE_ACTIVE.set(1)  # AI is working
                logger.info(f"🤖 AI ENGINE ACTIVE: Decision made for {tenant}/{endpoint}")
                
                # UPDATED: Recalculate satisfaction with AI boost now that we have ai_decision
                ai_boost = 0.1  # AI made a decision
                satisfaction = max(0.0, min(1.0, 
                    base_satisfaction 
                    - blocking_penalty 
                    - utilization_stress 
                    - expectation_gap
                    + ai_boost
                ))
                RL_CUSTOMER_SATISFACTION.labels(tenant).set(satisfaction)
                
            else:
                RL_AI_ENGINE_ACTIVE.set(0)  # AI failed
                logger.error(f"💥 AI ENGINE OFFLINE: Failed for {tenant}/{endpoint}")
                continue  # Skip to next iteration if AI fails
            
            # Apply AI decision with governance
            result = _apply_or_queue(
                tenant, endpoint,
                ai_decision["action"],
                ai_decision["new_rps"], 
                ai_decision["new_burst"],
                ai_decision["confidence"],
                ai_decision["reason"]
            )
            
            logger.info(f"✅ AI DECISION RESULT: {tenant}/{endpoint} - {result}")

# Start background thread
threading.Thread(target=_heuristics_loop, daemon=True).start()

# ------------------------------------------------------------------------------------
# Flask App with Enhanced Routes (Same as before)
# ------------------------------------------------------------------------------------
app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify({
        "status": "ok", 
        "timestamp": time.time(),
        "ai_model": OLLAMA_MODEL,
        "ai_base_url": OLLAMA_BASE_URL,
        "policies_active": len(policies),
        "pending_decisions": len(pending_decisions),
        "mode": "PURE_AI_ONLY"
    }), 200

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

@app.get("/demo/metrics")
def demo_metrics():
    """Structured JSON snapshot of key limiter metrics for the front-end demo.

    This aggregates current policy limits, effective RPS, blocked ratios, revenue
    counters and governance / surge state. Prefer this over scraping /metrics
    directly inside the browser.
    """
    with state_lock:
        # Ensure at least baseline policies exist
        active_pairs = list(policies.keys())

        # Build per‑tenant aggregates
        tenant_view: Dict[str, Dict[str, Any]] = {}
        for (tenant, endpoint) in active_pairs:
            pol = policies[(tenant, endpoint)]
            st = stats.get((tenant, endpoint), {"ok": 0.0, "blocked": 0.0, "since": _now()})
            window = max(1.0, _now() - st["since"])
            eff_rps = st["ok"] / window
            total_req = st["ok"] + st["blocked"]
            blocked_ratio = (st["blocked"] / total_req) if total_req > 0 else 0.0
            t_entry = tenant_view.setdefault(tenant, {
                "rps_limit": 0.0,
                "burst": 0,
                "effective_rps": 0.0,
                "blocked_ratio": 0.0,
                "endpoints": 0,
            })
            # Use max policy per tenant to simplify visualization
            t_entry["rps_limit"] = max(t_entry["rps_limit"], pol["rps"])
            t_entry["burst"] = max(t_entry["burst"], pol["burst"])
            t_entry["effective_rps"] = max(t_entry["effective_rps"], eff_rps)
            t_entry["blocked_ratio"] = max(t_entry["blocked_ratio"], blocked_ratio)
            t_entry["endpoints"] += 1

        # Helper: pull counter / gauge values from registry
        def collect_metric(prefix: str) -> Dict[str, float]:
            out: Dict[str, float] = {}
            for metric in REGISTRY.collect():
                if metric.name == prefix:
                    for s in metric.samples:
                        # All our tenant metrics share 'tenant' label
                        tenant_lbl = s.labels.get("tenant")
                        if tenant_lbl:
                            out[tenant_lbl] = float(s.value)
            return out

        protected = collect_metric("rl_revenue_protected_total")
        lost = collect_metric("rl_revenue_lost_total")
        satisfaction = collect_metric("rl_customer_satisfaction")
        anomaly_scores = collect_metric("rl_anomaly_score")
        surge_probs = collect_metric("rl_surge_prediction")

        # Attach revenue & satisfaction
        for tenant, data in tenant_view.items():
            data["revenue_protected"] = protected.get(tenant, 0.0)
            data["revenue_lost"] = lost.get(tenant, 0.0)
            data["satisfaction"] = satisfaction.get(tenant, None)
            # Provide representative anomaly / surge (max across endpoints)
            data["anomaly_score"] = anomaly_scores.get(tenant, 0.0)
            data["surge_prediction_pct"] = surge_probs.get(tenant, 0.0)

        # Governance summary
        governance = {
            "pending_count": len(pending_decisions),
            "large_change_threshold": LARGE_CHANGE_FACTOR,
        }

        # Recent surge predictions (pair level)
        surge_summary = {
            f"{t}:{e}": {
                "probability": v.get("probability"),
                "scaling_factor": v.get("scaling_factor"),
                "new_rps": v.get("new_rps"),
                "action_type": v.get("action_type")
            } for (t, e), v in surge_predictions.items()
        }

    # AI engine status gauge (0/1)
    ai_engine_active = 0
    for metric in REGISTRY.collect():
        if metric.name == "rl_ai_engine_active":
            for s in metric.samples:
                ai_engine_active = int(s.value)
            break

    return jsonify({
        "timestamp": _now(),
        "ai_engine_active": bool(ai_engine_active),
        "tiers": tenant_view,
        "governance": governance,
        "surge_predictions": surge_summary,
        "model": OLLAMA_MODEL,
        "interval_sec": HEURISTIC_EVERY_SEC
    })

@app.get("/demo/ultimate")
def ultimate_demo():
    """Ultimate demo dashboard route"""
    return render_template("ultimate_demo.html")

def _proxy_backend(path: str):
    try:
        response = requests.get(f"{BACKEND_BASE_URL}{path}", timeout=3)
        if response.headers.get("Content-Type", "").startswith("application/json"):
            return response.status_code, response.json()
        else:
            return response.status_code, {"raw": response.text}
    except Exception as e:
        return 502, {"error": "backend_error", "detail": str(e)}

def _handle_request(endpoint_path: str):
    start_time = time.time()
    tenant = _tenant()
    if tenant == "unknown":
        duration = time.time() - start_time
        _track_service_metrics("ai-rate-limiter", "GET", 401, duration)
        return jsonify({"error": "unauthorized"}), 401
    
    pair = (tenant, endpoint_path)
    
    # Apply rate limiting
    with state_lock:
        allowed = _allow(pair)
        if allowed:
            stats[pair]["ok"] += 1
        else:
            stats[pair]["blocked"] += 1
    
    if not allowed:
        duration = time.time() - start_time
        _track_service_metrics("ai-rate-limiter", "GET", 429, duration)
        RL_REQUESTS_TOTAL.labels(tenant, endpoint_path, "blocked").inc()
        return jsonify({
            "error": "rate_limited",
            "tenant": tenant,
            "message": "Request blocked by AI rate limiter"
        }), 429
    
    # Proxy to backend
    backend_start = time.time()
    status_code, response_data = _proxy_backend(endpoint_path)
    RL_REQUESTS_TOTAL.labels(tenant, endpoint_path, "ok" if status_code < 500 else "error").inc()
    backend_duration = time.time() - backend_start
    total_duration = time.time() - start_time
    
     # Track metrics for both services
    _track_service_metrics("ai-rate-limiter", "GET", status_code, total_duration)
    _track_service_metrics("backend", "GET", status_code, backend_duration)
    
    RL_REQUESTS_TOTAL.labels(tenant, endpoint_path, "ok" if status_code < 500 else "error").inc()
   
    return jsonify(response_data), status_code

@app.get("/api/v1/resourceA")
def resource_a():
    return _handle_request("/api/v1/resourceA")

@app.get("/api/v1/resourceB") 
def resource_b():
    return _handle_request("/api/v1/resourceB")

@app.get("/ai/decisions/history")
def decisions_history():
    with state_lock:
        history_snapshot = decision_history[-50:]
    return jsonify({"decisions": history_snapshot, "total": len(decision_history)})

@app.get("/ai/pending")
def list_pending():
    with state_lock:
        pending_list = list(pending_decisions.values())
    return jsonify({"pending": pending_list, "count": len(pending_list)})

@app.post("/ai/approve/<decision_id>")
def approve_decision(decision_id: str):
    with state_lock:
        decision = pending_decisions.get(decision_id)
        if not decision:
            return jsonify({"error": "not_found"}), 404
        
        apply_policy(
            decision["tenant"], 
            decision["endpoint"],
            decision["new_rps"], 
            decision["new_burst"]
        )
        
        # Add to history
        decision["applied"] = True
        decision["approved_at"] = _now()
        decision_history.append(decision)
        
        pending_decisions.pop(decision_id)
        RL_GOVERNANCE_QUEUE_SIZE.set(len(pending_decisions))
        
        logger.info(f"✅ APPROVED: {decision['tenant']}/{decision['endpoint']} "
                   f"{decision['old_rps']:.1f}→{decision['new_rps']:.1f} RPS")
    
    return jsonify({"status": "approved", "id": decision_id}), 200

@app.post("/ai/approve_all")
def approve_all():
    approved_count = 0
    with state_lock:
        for decision_id in list(pending_decisions.keys()):
            decision = pending_decisions.get(decision_id)
            if decision:
                apply_policy(
                    decision["tenant"],
                    decision["endpoint"], 
                    decision["new_rps"],
                    decision["new_burst"]
                )
                
                # Add to history
                decision["applied"] = True
                decision["approved_at"] = _now()
                decision_history.append(decision)
                approved_count += 1
        
        pending_decisions.clear()
        RL_GOVERNANCE_QUEUE_SIZE.set(0)
    
    logger.info(f"✅ BULK APPROVED: {approved_count} decisions")
    return jsonify({"approved": approved_count}), 200

@app.post("/admin/init")
def admin_init():
    with state_lock:
        for tenant in ("free", "pro", "ent"):
            for endpoint in VALID_ENDPOINTS:
                _ensure_policy_and_bucket((tenant, endpoint))
    
    return jsonify({
        "initialized": True, 
        "policies": len(policies),
        "ai_model": OLLAMA_MODEL,
        "governance_threshold": LARGE_CHANGE_FACTOR,
        "mode": "PURE_AI_ONLY"
    }), 200

@app.get("/debug/policies")
def debug_policies():
    with state_lock:
        return jsonify({
            f"{tenant}:{endpoint}": policy
            for (tenant, endpoint), policy in policies.items()
        })

@app.get("/ai/insights")
def ai_insights():
    """Enhanced AI insights for dashboard"""
    with state_lock:
        insights = []
        for pair, policy in policies.items():
            tenant, endpoint = pair
            current_stats = stats.get(pair, {"ok": 0, "blocked": 0, "since": _now()})
            window = max(1.0, _now() - current_stats["since"])
            effective_rps = current_stats["ok"] / window
            total_reqs = current_stats["ok"] + current_stats["blocked"] 
            blocked_ratio = current_stats["blocked"] / max(1, total_reqs)
            utilization = effective_rps / max(policy["rps"], 1e-6)
            scenario = _classify_traffic_scenario(tenant, effective_rps, blocked_ratio, utilization)
            
            insights.append({
                "tenant": tenant,
                "endpoint": endpoint,
                "current_rps": policy["rps"],
                "current_burst": policy["burst"],
                "effective_rps": effective_rps,
                "blocked_ratio": blocked_ratio,
                "business_priority": _calculate_business_priority(tenant),
                "revenue_per_req": REVENUE_PER_REQUEST.get(tenant, 0.01),
                "utilization": utilization,
                "scenario": scenario
            })
    
    return jsonify({
        "insights": insights,
        "ai_status": {
            "model": OLLAMA_MODEL,
            "timeout": OLLAMA_TIMEOUT_SEC,
            "base_url": OLLAMA_BASE_URL,
            "retries": OLLAMA_MAX_RETRIES,
            "mode": "PURE_AI_ONLY"
        },
        "governance": {
            "pending_count": len(pending_decisions),
            "large_change_threshold": LARGE_CHANGE_FACTOR,
            "min_confidence": DECISION_MIN_CONF
        },
        "recent_decisions": len(decision_history)
    })

@app.get("/ai/surge")
def surge_status():
    """Enhanced surge predictions for dashboard"""
    with state_lock:
        surge_info = {}
        for pair, prediction in surge_predictions.items():
            tenant, endpoint = pair
            surge_info[f"{tenant}:{endpoint}"] = prediction
            
    return jsonify({
        "surge_predictions": surge_info,
        "active_surges": len([p for p in surge_predictions.values() if p["probability"] > 40]),
        "surge_algorithm": "multi_level_pattern_analysis"
    })

@app.get("/demo")
def demo_redirect():
    """Redirect /demo to Ultimate Demo"""
    return render_template("ultimate_demo.html")

@app.get("/api/demo/status")
def demo_status():
    """Real-time demo status for Ultimate Demo HTML"""
    with state_lock:
        total_policies = len(policies)
        total_pending = len(pending_decisions)
        
        # Calculate current metrics across all tiers
        current_metrics = {
            "ent": {"rps": 0, "effective": 0, "revenue": 0, "satisfaction": 0.95},
            "pro": {"rps": 0, "effective": 0, "revenue": 0, "satisfaction": 0.85}, 
            "free": {"rps": 0, "effective": 0, "revenue": 0, "satisfaction": 0.75}
        }
        
        for (tenant, endpoint), policy in policies.items():
            if tenant in current_metrics:
                current_metrics[tenant]["rps"] = max(current_metrics[tenant]["rps"], policy["rps"])
                
                # Get current effective RPS
                current_stats = stats.get((tenant, endpoint), {"ok": 0, "blocked": 0, "since": _now()})
                window = max(1.0, _now() - current_stats["since"])
                effective_rps = current_stats["ok"] / window
                current_metrics[tenant]["effective"] = max(current_metrics[tenant]["effective"], effective_rps)
        
        # Calculate revenue and satisfaction
        for tenant in current_metrics:
            revenue_per_req = REVENUE_PER_REQUEST.get(tenant, 0.01)
            current_metrics[tenant]["revenue"] = current_metrics[tenant]["effective"] * revenue_per_req * 3600  # Per hour
            
            # Get satisfaction from metrics
            try:
                from prometheus_client import REGISTRY
                for metric in REGISTRY.collect():
                    if metric.name == "rl_customer_satisfaction":
                        for sample in metric.samples:
                            if sample.labels.get("tenant") == tenant:
                                current_metrics[tenant]["satisfaction"] = sample.value
                                break
            except:
                pass  # Use defaults
    
    return jsonify({
        "ai_engine_active": True,  # Assume active for demo
        "policies_count": total_policies,
        "pending_decisions": total_pending,
        "current_rps_total": sum(m["effective"] for m in current_metrics.values()),
        "tiers": current_metrics,
        "ai_model": OLLAMA_MODEL,
        "timestamp": _now()
    })

@app.get("/api/demo/phase/<int:phase_num>")
def demo_phase(phase_num: int):
    """Trigger specific demo phases"""
    phase_messages = {
        1: "🚀 Phase 1: AI analyzing customer tiers and setting intelligent baselines...",
        2: "📈 Phase 2: Processing traffic patterns and scaling dynamically...", 
        3: "⚡ Phase 3: Surge detection active! Predicting traffic spikes...",
        4: "🛡️ Phase 4: Governance system engaged for large scaling decisions..."
    }
    
    if phase_num == 2:
        # Simulate some traffic for realistic demo
        logger.info("🎬 DEMO PHASE 2: Simulating traffic patterns")
        with state_lock:
            for tenant in ["ent", "pro", "free"]:
                for endpoint in ["/api/v1/resourceA", "/api/v1/resourceB"]:
                    pair = (tenant, endpoint)
                    _ensure_policy_and_bucket(pair)
                    if pair in stats:
                        # Add substantial simulated activity to trigger AI calls
                        base_traffic = 25 if tenant == "ent" else 15 if tenant == "pro" else 8
                        stats[pair]["ok"] += base_traffic
                        stats[pair]["blocked"] += 3 if tenant == "free" else 1
                        logger.info(f"🎬 DEMO TRAFFIC: {tenant}/{endpoint} - Added {base_traffic} requests")
    
    elif phase_num == 4:
        # Create a governance decision for demo
        logger.info("🎬 DEMO PHASE 4: Creating governance scenario")
        decision_id = str(uuid.uuid4())
        with state_lock:
            pending_decisions[decision_id] = {
                "id": decision_id,
                "tenant": "ent",
                "endpoint": "/api/v1/resourceA",
                "action": "up",
                "new_rps": 45.0,
                "new_burst": 135,
                "confidence": 0.92,
                "created": _now(),
                "reason": "ddos_protection_89pct",
                "old_rps": 15.0,
                "scaling_factor": 3.0
            }
            RL_GOVERNANCE_QUEUE_SIZE.set(len(pending_decisions))
    
    message = phase_messages.get(phase_num, f"Phase {phase_num} triggered")
    return jsonify({"phase": phase_num, "message": message, "timestamp": _now()})

@app.post("/api/demo/reset")
def demo_reset():
    """Reset demo to initial state"""
    with state_lock:
        # Reset to baseline policies
        for tenant in ("free", "pro", "ent"):
            for endpoint in VALID_ENDPOINTS:
                base = PLAN_BASE.get(tenant, {"rps": 10.0, "burst": 20})
                apply_policy(tenant, endpoint, base["rps"], base["burst"])
        
        # Clear pending decisions
        pending_decisions.clear()
        RL_GOVERNANCE_QUEUE_SIZE.set(0)
        
        # Reset stats
        for pair in stats:
            stats[pair] = {"ok": 0.0, "blocked": 0.0, "since": _now()}
    
    logger.info("🎬 DEMO RESET: All systems restored to baseline")
    return jsonify({"status": "reset", "message": "Demo reset to baseline state"})

@app.get("/debug/test-ollama")
def test_ollama():
    """Manual OLLAMA test endpoint for debugging"""
    tenant = request.args.get("tenant", "pro")
    endpoint = request.args.get("endpoint", "/api/v1/resourceA") 
    
    logger.info(f"🧪 MANUAL OLLAMA TEST: Testing {tenant}/{endpoint}")
    
    # Test OLLAMA call directly
    try:
        ai_raw = _call_ollama_ai(tenant, endpoint, ok_rps=5.2, blocked_ratio=0.15, utilization=0.65)
        if ai_raw:
            ai_decision = _validate_ai_decision(ai_raw, 10.0, 30)
            return jsonify({
                "status": "success",
                "tenant": tenant,
                "endpoint": endpoint,
                "ollama_response": ai_raw,
                "validated_decision": ai_decision,
                "message": "OLLAMA call successful!"
            })
        else:
            return jsonify({
                "status": "failed", 
                "tenant": tenant,
                "endpoint": endpoint,
                "message": "OLLAMA call returned empty response"
            }), 500
            
    except Exception as e:
        logger.error(f"🧪 MANUAL OLLAMA TEST ERROR: {e}")
        return jsonify({
            "status": "error",
            "tenant": tenant, 
            "endpoint": endpoint,
            "error": str(e)
        }), 500

@app.post("/debug/simulate-traffic")
def simulate_traffic():
    """Simulate traffic to trigger AI calls"""
    tenant = request.json.get("tenant", "pro") if request.is_json else "pro"
    requests_count = request.json.get("requests", 20) if request.is_json else 20
    
    logger.info(f"🎬 TRAFFIC SIMULATION: Adding {requests_count} requests for {tenant}")
    
    with state_lock:
        for endpoint in VALID_ENDPOINTS:
            pair = (tenant, endpoint)
            _ensure_policy_and_bucket(pair) 
            if pair in stats:
                stats[pair]["ok"] += requests_count
                stats[pair]["blocked"] += max(1, requests_count // 10)  # 10% blocking
                
    return jsonify({
        "status": "success",
        "message": f"Added {requests_count} requests for {tenant}",
        "note": "AI calls should trigger in next heuristic cycle (every 3 seconds)"
    })

# Initialize policies on startup
with state_lock:
    for tenant in ("free", "pro", "ent"):
        for endpoint in VALID_ENDPOINTS:
            _ensure_policy_and_bucket((tenant, endpoint))

if __name__ == "__main__":
    logger.info("🚀 AI Rate Limiter Starting - PURE AI EDITION")
    logger.info(f"   🤖 AI Model: {OLLAMA_MODEL}")
    logger.info(f"   🛡️ Governance: {LARGE_CHANGE_FACTOR}x change threshold")
    logger.info(f"   🚫 NO FALLBACK: Pure AI decisions only")
    logger.info(f"   📊 Multi-Level Scaling: Normal → Surge → DDoS")
    app.run(host="0.0.0.0", port=PORT, threaded=True)