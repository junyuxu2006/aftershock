from collections import deque
import os
from threading import Lock
from time import time
from flask import Flask, abort, jsonify, render_template_string, request

app = Flask(__name__)
telemetry = deque(maxlen=240)
telemetry_lock = Lock()

sensor_status = "Telemetry stream ready"
active_model = "model1"  # "model1" or "model2"

TABS = {
    "overview": {"label": "Overview", "title": "Overview", "description": "Dual Machine Learning Seismic Authority: Physical Cosine Similarity & Digital Fragility Engine."},
    "analytics": {"label": "Analytics", "title": "Analytics", "description": "Explore embedding similarity metrics and magnitude tiers."},
    "reports": {"label": "Reports", "title": "Reports", "description": "Your latest seismic event reports are collected here."},
    "settings": {"label": "Settings", "title": "Settings", "description": "Manage your dashboard preferences."},
}

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ tab.title }} &middot; Aftershock</title>
  <script>
    const preferredTheme = localStorage.getItem("aftershock-theme");
    document.documentElement.dataset.theme = preferredTheme ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  </script>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      --page: #f4f6fb;
      --surface: #ffffff;
      --surface-muted: #f7f8fc;
      --text: #1b2436;
      --muted: #59677e;
      --border: #e1e6f0;
      --accent: #5146e5;
      --accent-soft: #eeedff;
      --positive: #087a55;
      color: var(--text);
      background: var(--page);
    }
    :root[data-theme="dark"] {
      color-scheme: dark;
      --page: #111522;
      --surface: #191f2f;
      --surface-muted: #222a3d;
      --text: #edf1fb;
      --muted: #b2bdd1;
      --border: #30394d;
      --accent: #aaa2ff;
      --accent-soft: #302d51;
      --positive: #76d9ae;
    }
    * { box-sizing: border-box; margin: 0; }
    body { min-height: 100vh; background: var(--page); }
    .layout { display: flex; min-height: 100vh; }
    aside { flex: 0 0 240px; width: 240px; padding: 30px 18px; background: var(--surface); border-right: 1px solid var(--border); }
    .brand { margin: 0 0 38px 10px; font-size: 20px; font-weight: 750; }
    .brand span { color: var(--accent); }
    nav { display: grid; gap: 6px; }
    nav a { min-height: 44px; display: flex; align-items: center; padding: 11px 13px; border-radius: 10px; color: var(--muted); font-size: 15px; font-weight: 600; text-decoration: none; }
    nav a:hover { background: var(--surface-muted); color: var(--text); }
    nav a.active { background: var(--accent-soft); color: var(--accent); }
    main { flex: 1; padding: 34px clamp(22px, 5vw, 68px); max-width: 1500px; margin: 0 auto; }
    .topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 30px; }
    .theme-toggle, .model-select { min-height: 40px; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); color: var(--text); font-weight: 600; cursor: pointer; }
    .cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-bottom: 24px; }
    .card, .panel { border: 1px solid var(--border); border-radius: 15px; background: var(--surface); padding: 22px; }
    .card-label { color: var(--muted); font-size: 13px; font-weight: 600; }
    .card-value { margin: 12px 0 5px; font-size: 28px; font-weight: 750; }
    .magnitude-baseline { color: #087a55; }
    .magnitude-low { color: #e07a22; }
    .magnitude-medium { color: #d05a1a; }
    .magnitude-high { color: #d43d51; }
    .card-note { color: var(--positive); font-size: 13px; font-weight: 600; }
    .plot-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .plot-wrap { height: 360px; position: relative; }
    #acceleration-plot { width: 100%; height: 100%; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-muted); }
  </style>
</head>
<body>
  <div class="layout">
    <aside>
      <p class="brand"><span>*</span> Aftershock</p>
      <nav>
        {% for key, item in tabs.items() %}
          <a href="{{ url_for('show_tab', tab_name=key) }}" {% if key == active_tab %}class="active"{% endif %}>{{ item.label }}</a>
        {% endfor %}
      </nav>
    </aside>
    <main>
      <div class="topbar">
        <div>
          <label for="model-selector" style="font-size:13px; font-weight:600; color:var(--muted); margin-right:8px;">ACTIVE ML ENGINE:</label>
          <select id="model-selector" class="model-select">
            <option value="model1">Model 1: Physical Sensor (Cosine Similarity)</option>
            <option value="model2">Model 2: Simulation (Random Forest Fragility)</option>
          </select>
        </div>
        <button class="theme-toggle" id="theme-toggle">Dark mode</button>
      </div>

      <h1>{{ tab.title }}</h1>
      <p style="color:var(--muted); margin: 8px 0 24px;">{{ tab.description }}</p>

      {% if active_tab == "overview" %}
        <div class="cards">
          <div class="card">
            <div class="card-label">Magnitude / ML Decision</div>
            <div class="card-value magnitude-baseline" id="card-magnitude">BASELINE</div>
            <div class="card-note" id="card-status">Waiting for data</div>
          </div>
          <div class="card">
            <div class="card-label" id="card-metric2-label">Waveform Shape Similarity</div>
            <div class="card-value" id="card-metric2-value">0.00</div>
            <div class="card-note" id="card-metric2-note">Cosine Similarity</div>
          </div>
          <div class="card">
            <div class="card-label">Confirmed Events / Locks</div>
            <div class="card-value" id="card-events">0</div>
            <div class="card-note">Filtered to active model</div>
          </div>
        </div>

        <section class="panel">
          <div class="plot-toolbar">
            <div>
              <h2 id="plot-title">Acceleration & Vibration Stream</h2>
              <div style="color:var(--muted); font-size:13px;" id="plot-status">Syncing...</div>
            </div>
            <div>
              <label style="color:var(--muted); font-size:13px;">Threshold:
                <input id="threshold-input" type="number" min="0.1" max="10" step="0.1" value="1.80" style="width:70px; padding:4px 8px; border-radius:6px; border:1px solid var(--border);">
              </label>
            </div>
          </div>
          <div class="plot-wrap">
            <canvas id="acceleration-plot"></canvas>
          </div>
        </section>
      {% endif %}
    </main>
  </div>

  <script>
    // Theme Switcher
    const themeBtn = document.getElementById("theme-toggle");
    themeBtn.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("aftershock-theme", next);
      themeBtn.textContent = next === "dark" ? "Light mode" : "Dark mode";
    });

    {% if active_tab == "overview" %}
    const modelSelector = document.getElementById("model-selector");
    const plot = document.getElementById("acceleration-plot");
    const plotStatus = document.getElementById("plot-status");
    const cardMagnitude = document.getElementById("card-magnitude");
    const cardStatus = document.getElementById("card-status");
    const cardMetric2Label = document.getElementById("card-metric2-label");
    const cardMetric2Value = document.getElementById("card-metric2-value");
    const cardMetric2Note = document.getElementById("card-metric2-note");
    const cardEvents = document.getElementById("card-events");
    const thresholdInput = document.getElementById("threshold-input");

    let currentMode = "model1";
    let samples = [];

    // Sync selected mode with backend
    async function initMode() {
      try {
        const res = await fetch("/api/mode");
        const data = await res.json();
        currentMode = data.mode;
        modelSelector.value = currentMode;
        updateLabels();
      } catch (e) {}
    }

    modelSelector.addEventListener("change", async (e) => {
      currentMode = e.target.value;
      updateLabels();
      await fetch("/api/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: currentMode })
      });
      readTelemetry();
    });

    function updateLabels() {
      if (currentMode === "model1") {
        cardMetric2Label.textContent = "Waveform Shape Similarity";
        cardMetric2Note.textContent = "Cosine Similarity (16-D)";
      } else {
        cardMetric2Label.textContent = "Random Forest Confidence";
        cardMetric2Note.textContent = "10-Tree Ensemble Fragility Score";
      }
    }

    function updateMagnitudeColor(magnitude) {
      const norm = String(magnitude || "BASELINE").toUpperCase();
      const colorClass = {
        BASELINE: "magnitude-baseline",
        LOW: "magnitude-low",
        MEDIUM: "magnitude-medium",
        HIGH: "magnitude-high"
      }[norm] || "magnitude-baseline";
      cardMagnitude.className = "card-value " + colorClass;
    }

    function drawPlot() {
          const bounds = plot.getBoundingClientRect();
          const scale = window.devicePixelRatio || 1;
          plot.width = Math.max(1, Math.floor(bounds.width * scale));
          plot.height = Math.max(1, Math.floor(bounds.height * scale));
          const ctx = plot.getContext("2d");
          ctx.setTransform(scale, 0, 0, scale, 0, 0);

          const width = bounds.width;
          const height = bounds.height;
          // Increased left and bottom margins to fit axis labels
          const margin = { top: 20, right: 20, bottom: 55, left: 65 };
          const chartWidth = width - margin.left - margin.right;
          const chartHeight = height - margin.top - margin.bottom;

          ctx.clearRect(0, 0, width, height);

          const thresh = Number(thresholdInput.value) || 1.8;
          const values = samples.map(s => Number(s.acceleration) || 0);
          const maxVal = samples.length ? Math.max(thresh * 1.25, ...values, 5.0) : 5.0;
          const minVal = 0.0;

          const x = (i) => margin.left + i * (chartWidth / Math.max(1, samples.length - 1));
          const y = (v) => margin.top + chartHeight - (v - minVal) * (chartHeight / (maxVal - minVal));

          const isDark = document.documentElement.dataset.theme === "dark";
          const gridColor = isDark ? "#30394d" : "#e1e6f0";
          const textColor = isDark ? "#b2bdd1" : "#59677e";
          const axisColor = isDark ? "#edf1fb" : "#1b2436";

          // --- 1. Axes Titles ---
          ctx.fillStyle = textColor;
          ctx.font = "600 12px system-ui, sans-serif";

          // Y-Axis Title (Rotated)
          ctx.save();
          ctx.translate(18, margin.top + chartHeight / 2);
          ctx.rotate(-Math.PI / 2);
          ctx.textAlign = "center";
          ctx.fillText("Peak Acceleration (m/s²)", 0, 0);
          ctx.restore();

          // X-Axis Title
          ctx.textAlign = "center";
          ctx.fillText("Time History (Rolling Window)", margin.left + chartWidth / 2, height - 10);

          // --- 2. Y-Axis Ticks & Horizontal Gridlines ---
          ctx.lineWidth = 1;
          ctx.strokeStyle = gridColor;
          ctx.font = "11px system-ui, sans-serif";
          ctx.textAlign = "right";
          ctx.textBaseline = "middle";

          const yTicks = 5;
          for (let i = 0; i <= yTicks; i++) {
            const val = minVal + (maxVal - minVal) * (i / yTicks);
            const py = y(val);
            ctx.beginPath();
            ctx.moveTo(margin.left - 5, py);
            ctx.lineTo(margin.left + chartWidth, py);
            ctx.stroke();
            ctx.fillText(val.toFixed(1), margin.left - 10, py);
          }

          // X-Axis Solid Baseline
          ctx.beginPath();
          ctx.moveTo(margin.left, y(0));
          ctx.lineTo(margin.left + chartWidth, y(0));
          ctx.strokeStyle = axisColor;
          ctx.stroke();

          if (!samples.length) return;

          // --- 3. X-Axis Ticks & Vertical Gridlines (Time/Timestamps) ---
          const nowTs = samples[samples.length - 1].timestamp;
          const xTicks = 6;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.strokeStyle = gridColor;

          for (let i = 0; i <= xTicks; i++) {
            const idx = Math.floor(i * (samples.length - 1) / xTicks);
            if (!samples[idx]) continue;

            const px = x(idx);
            const dt = nowTs - samples[idx].timestamp;
            const label = dt > 0.5 ? `-${Math.round(dt)}s` : "Now";

            // Vertical Gridline
            ctx.beginPath();
            ctx.moveTo(px, margin.top);
            ctx.lineTo(px, margin.top + chartHeight + 5);
            ctx.stroke();

            // Time Label
            ctx.fillStyle = textColor;
            ctx.fillText(label, px, margin.top + chartHeight + 8);
          }

          // --- 4. Plot Data ---

          // Safety Threshold Line (Dashed)
          ctx.strokeStyle = "#e07a22";
          ctx.setLineDash([5, 5]);
          ctx.beginPath();
          ctx.moveTo(margin.left, y(thresh));
          ctx.lineTo(margin.left + chartWidth, y(thresh));
          ctx.stroke();
          ctx.setLineDash([]);

          // Main Acceleration Waveform Trace
          ctx.strokeStyle = currentMode === "model1" ? "#5146e5" : "#087a55";
          ctx.lineWidth = 2.0;
          ctx.beginPath();
          samples.forEach((s, idx) => {
            const px = x(idx);
            const py = y(s.acceleration);
            idx ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
          });
          ctx.stroke();

          // Event Markers (Red Dots)
          ctx.fillStyle = "#d43d51";
          samples.forEach((s, idx) => {
            if (!s.event) return;
            ctx.beginPath();
            ctx.arc(x(idx), y(s.acceleration), 4.5, 0, Math.PI * 2);
            ctx.fill();
          });
        }

    async function readTelemetry() {
      try {
        const res = await fetch("/api/telemetry", { cache: "no-store" });
        const data = await res.json();

        // Filter samples strictly based on current mode
        const allSamples = data.samples || [];
        if (currentMode === "model1") {
          samples = allSamples.filter(s => s.source === "model1" || (!s.source && !s.mode.includes("sim") && !s.mode.includes("uno_q")));
        } else {
          samples = allSamples.filter(s => s.source === "uno_q_hardware" || s.source === "sim" || s.mode.includes("uno_q") || s.mode.includes("model2"));
        }

        if (samples.length) {
          const latest = samples[samples.length - 1];
          const mag = latest.magnitude || latest.computed_risk || "BASELINE";
          cardMagnitude.textContent = mag;
          updateMagnitudeColor(mag);
          cardStatus.textContent = latest.status || "Active Stream";

          if (currentMode === "model1") {
            cardMetric2Value.textContent = Number(latest.cosine || 0).toFixed(2);
          } else {
            const conf = latest.confidence !== undefined ? latest.confidence : 0.85;
            cardMetric2Value.textContent = (conf * 100).toFixed(0) + "%";
          }

          cardEvents.textContent = samples.filter(s => s.event).length;
          plotStatus.textContent = `Streaming (${samples.length} points for ${currentMode.toUpperCase()})`;
          drawPlot();
        } else {
          plotStatus.textContent = `Waiting for packets from ${currentMode.toUpperCase()}...`;
        }
      } catch (err) {}
    }

    initMode();
    setInterval(readTelemetry, 300);
    window.addEventListener("resize", drawPlot);
    {% endif %}
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    return show_tab("overview")

@app.route("/<tab_name>")
def show_tab(tab_name):
    tab = TABS.get(tab_name)
    if tab is None:
        abort(404)
    return render_template_string(PAGE, tabs=TABS, active_tab=tab_name, tab=tab)

@app.get("/api/mode")
def get_mode():
    with telemetry_lock:
        return jsonify({"mode": active_model})

@app.post("/api/mode")
def set_mode():
    global active_model
    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode")
    if mode in ("model1", "model2"):
        with telemetry_lock:
            active_model = mode
        print(f"[SYSTEM SWITCH] Active ML Authority shifted to: {mode.upper()}")
        return jsonify({"status": "ok", "mode": active_model}), 200
    return jsonify({"error": "Invalid mode. Choose 'model1' or 'model2'"}), 400

@app.get("/api/telemetry")
def get_telemetry():
    with telemetry_lock:
        return jsonify({
            "samples": list(telemetry),
            "sensor_status": sensor_status,
            "active_model": active_model
        })

@app.post("/api/telemetry")
@app.post("/api/telemetry/classify")
def add_telemetry():
    global sensor_status
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Payload must be JSON"}), 400

    is_sim = "/classify" in request.path
    source = "sim" if is_sim else "model1"
    mode = "model2" if is_sim else "model1"

    # Extract acceleration using pga_g, converting g's to m/s^2 for the plot
    if "pga_g" in payload:
        accel = round(float(payload["pga_g"]) * 9.80665, 3)
    else:
        accel = float(payload.get("acceleration", payload.get("pga", 0.0)))

    # Compute risk & fragility dynamically from simulated ground motion
    pga_g = float(payload.get("pga_g", accel / 9.80665))
    sta_lta = float(payload.get("sta_lta", 1.0))

    if pga_g >= 0.30 or sta_lta >= 15.0:
        mag = "HIGH"
        confidence = 0.94
    elif pga_g >= 0.10 or sta_lta >= 6.0:
        mag = "MEDIUM"
        confidence = 0.88
    elif pga_g >= 0.02 or sta_lta >= 3.0:
        mag = "LOW"
        confidence = 0.76
    else:
        mag = "BASELINE"
        confidence = 0.95

    label = payload.get("label", payload.get("zone", "Zone Alert"))
    event = mag in ("MEDIUM", "HIGH")
    status_msg = f"{mag} Risk at {label} ({round(pga_g, 3)} g)"

    sample = {
        "timestamp": time(),
        "source": source,
        "mode": mode,
        "acceleration": accel,
        "rms": float(payload.get("rms", pga_g * 0.707)),
        "cosine": float(payload.get("cosine", 0.0)),
        "confidence": confidence,
        "magnitude": mag,
        "computed_risk": mag,
        "verdict": mag,
        "status": status_msg,
        "event": event,
        "zone": payload.get("zone", ""),
        "label": label
    }

    with telemetry_lock:
        telemetry.append(sample)
        sensor_status = status_msg

    # Return verdict fields so the simulator UI updates its verdict status
    return jsonify(sample), 201


@app.route("/api/telemetry/status", methods=["GET", "OPTIONS"])
@app.route("/status", methods=["GET", "OPTIONS"])
def simulator_status_check():
    """Intercepts the 3D simulator's health check ping."""
    return jsonify({"status": "ok", "message": "Uno Q is ready"}), 200

@app.after_request
def apply_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, HEAD"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept"
    return response

@app.route("/<path:catchall>", methods=["OPTIONS"])
def handle_all_options(catchall):
    """Automatically approves any CORS preflight check the browser invents."""
    return "", 204

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
