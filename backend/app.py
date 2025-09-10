import time
import random
from flask import Flask, jsonify, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
REQS = Counter("backend_requests_total", "Backend requests", ["endpoint"])
LAT = Histogram("backend_latency_ms", "Backend latency", ["endpoint"])

@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

@app.route("/api/v1/resourceA")
def resource_a():
    start = time.perf_counter()
    time.sleep(random.uniform(0.02, 0.08))  # Simulate work
    
    ms = (time.perf_counter() - start) * 1000.0
    REQS.labels("/api/v1/resourceA").inc()
    LAT.labels("/api/v1/resourceA").observe(ms)
    
    return jsonify({"ok": True, "resource": "A"})

@app.route("/api/v1/resourceB")
def resource_b():
    start = time.perf_counter()
    time.sleep(random.uniform(0.1, 0.3))  # Simulate heavier work
    
    ms = (time.perf_counter() - start) * 1000.0
    REQS.labels("/api/v1/resourceB").inc()
    LAT.labels("/api/v1/resourceB").observe(ms)
    
    return jsonify({"ok": True, "resource": "B"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)