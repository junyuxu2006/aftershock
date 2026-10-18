from collections import deque
import os
from threading import Lock
from time import time

from flask import Flask, abort, jsonify, render_template_string, request

app = Flask(__name__)
telemetry = deque(maxlen=240)

telemetry_lock = Lock()
sensor_status = "Waiting for UNO Q telemetry"

TABS = {
    "overview": {
        "label": "Overview",
        "title": "Overview",
        "description": "Live Dual-MPU6050 Seismic Fingerprint & Vector Embedding Monitor.",
    },
    "analytics": {
        "label": "Analytics",
        "title": "Analytics",
        "description": "Explore embedding similarity metrics and magnitude tiers.",
    },
    "reports": {
        "label": "Reports",
        "title": "Reports",
        "description": "Your latest seismic event reports are collected here.",
    },
    "map": {
        "label": "Map",
        "title": "Map",
        "description": "Explore locations around the world.",
    },
    "settings": {
        "label": "Settings",
        "title": "Settings",
        "description": "Manage your dashboard preferences.",
    },
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
  {% if active_tab == "map" %}
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  {% endif %}
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
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
    @media (prefers-reduced-motion: no-preference) {
      *, *::before, *::after { transition: background-color .18s ease, border-color .18s ease, color .18s ease; }
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: var(--page); }
    a { color: var(--accent); }
    button { font: inherit; }
    :focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
    .skip-link {
      position: fixed;
      z-index: 1000;
      top: 12px;
      left: 12px;
      padding: 12px 16px;
      transform: translateY(-160%);
      border-radius: 9px;
      background: var(--surface);
      color: var(--text);
      box-shadow: 0 4px 16px #10182833;
    }
    .skip-link:focus { transform: translateY(0); }
    .layout { display: flex; min-height: 100vh; }
    aside {
      flex: 0 0 240px;
      width: 230px;
      padding: 30px 18px;
      background: var(--surface);
      border-right: 1px solid var(--border);
    }
    .brand { margin: 0 0 38px 10px; font-size: 20px; font-weight: 750; letter-spacing: -.04em; }
    .brand span { color: var(--accent); }
    .nav-label { margin: 0 0 10px 10px; color: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
    nav { display: grid; gap: 6px; }
    nav a {
      min-height: 44px;
      display: flex;
      align-items: center;
      padding: 11px 13px;
      border-radius: 10px;
      color: var(--muted);
      font-size: 15px;
      font-weight: 600;
      text-decoration: none;
    }
    nav a:hover { background: var(--surface-muted); color: var(--text); }
    nav a.active { background: var(--accent-soft); color: var(--accent); }
    main { flex: 1; min-width: 0; max-width: 1500px; margin: 0 auto; padding: 34px clamp(22px, 5vw, 68px); }
    .topbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-bottom: 40px; }
    .crumb { color: var(--muted); font-size: 14px; }
    .topbar-actions { display: flex; align-items: center; gap: 14px; }
    .theme-toggle {
      display: inline-flex;
      min-height: 42px;
      align-items: center;
      gap: 9px;
      padding: 9px 13px;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: var(--surface);
      color: var(--text);
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
    }
    .theme-toggle:hover { background: var(--surface-muted); }
    .avatar { display: grid; width: 40px; height: 40px; place-items: center; border: 1px solid var(--border); border-radius: 50%; background: var(--accent-soft); color: var(--accent); font-size: 13px; font-weight: 700; }
    h1 { margin: 0; font-size: clamp(28px, 4vw, 36px); letter-spacing: -.04em; }
    .description { margin: 9px 0 30px; color: var(--muted); font-size: 16px; line-height: 1.6; }
    .cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; margin-bottom: 24px; }
    .card, .panel { border: 1px solid var(--border); border-radius: 15px; background: var(--surface); box-shadow: 0 5px 18px #1725540a; }
    .card { padding: 22px; }
    .card-label { color: var(--muted); font-size: 14px; font-weight: 600; }
    .card-value { margin: 14px 0 5px; font-size: 28px; font-weight: 750; letter-spacing: -.04em; }
    .card-note { color: var(--positive); font-size: 13px; font-weight: 600; }
    .panel { padding: 24px; }
    .panel h2 { margin: 0 0 18px; font-size: 18px; }
    .activity { display: grid; grid-template-columns: 1fr auto; gap: 14px; padding: 15px 0; border-top: 1px solid var(--border); font-size: 15px; line-height: 1.5; }
    .activity span:last-child { color: var(--muted); font-size: 14px; }
    .placeholder { padding: 32px; color: var(--muted); line-height: 1.7; }
    .plot-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 16px; }
    .plot-status { color: var(--muted); font-size: 13px; }
    .plot-wrap { position: relative; height: 360px; }
    #acceleration-plot { display: block; width: 100%; height: 100%; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-muted); }
    .plot-legend { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 14px; color: var(--muted); font-size: 13px; }
    .legend-item::before { display: inline-block; width: 18px; height: 3px; margin: 0 7px 3px 0; border-radius: 2px; content: ""; background: var(--legend-color); }
    .legend-event::before { width: 9px; height: 9px; margin-bottom: 0; border-radius: 50%; }
    .plot-empty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); pointer-events: none; }
    .control { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); font-size: 14px; }
    .control input { width: 78px; padding: 7px 8px; border: 1px solid var(--border); border-radius: 7px; background: var(--surface); color: var(--text); }
    .setting-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 16px 0; border-top: 1px solid var(--border); font-size: 15px; line-height: 1.6; }
    .setting-row span { color: var(--muted); }
    #map { height: 560px; min-height: 360px; border-radius: 12px; }
    :root[data-theme="dark"] #map .leaflet-tile {
      filter: brightness(.78) invert(1) hue-rotate(180deg) saturate(.7);
    }
    @media (max-width: 700px) {
      .layout { display: block; }
      aside { width: auto; padding: 18px; border-right: 0; border-bottom: 1px solid var(--border); }
      .brand { margin: 0 0 16px 4px; }
      .nav-label { display: none; }
      nav { display: flex; overflow-x: auto; padding: 2px; }
      nav a { white-space: nowrap; }
      main { padding: 24px 18px; }
      .topbar { margin-bottom: 30px; }
      .cards { grid-template-columns: 1fr; gap: 12px; }
      .card, .panel { padding: 19px; }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <div class="layout">
    <aside aria-label="Sidebar">
      <p class="brand"><span>*</span> Aftershock</p>
      <p class="nav-label">Workspace</p>
      <nav aria-label="Dashboard tabs">
        {% for key, item in tabs.items() %}
          <a href="{{ url_for('show_tab', tab_name=key) }}" {% if key == active_tab %}class="active" aria-current="page"{% endif %}>{{ item.label }}</a>
        {% endfor %}
      </nav>
    </aside>
    <main id="main-content" tabindex="-1">
      <div class="topbar">
        <div class="crumb" aria-label="Breadcrumb">Workspace / {{ tab.label }}</div>
        <div class="topbar-actions">
          <button class="theme-toggle" id="theme-toggle" type="button" aria-label="Switch to dark mode" aria-pressed="false">
            <span aria-hidden="true">[ ]</span><span id="theme-label">Dark mode</span>
          </button>
          <div class="avatar" role="img" aria-label="Jordan Davis profile">JD</div>
        </div>
      </div>
      <h1>{{ tab.title }}</h1>
      <p class="description">{{ tab.description }}</p>
      {% if active_tab == "overview" %}
        <div class="cards">
          <div class="card">
            <div class="card-label">Magnitude Tier</div>
            <div class="card-value" id="card-magnitude">BASELINE</div>
            <div class="card-note" id="card-status">Vector DB Ready</div>
          </div>
          <div class="card">
            <div class="card-label">Waveform Shape Similarity</div>
            <div class="card-value" id="card-cosine">0.00</div>
            <div class="card-note">Cosine Similarity</div>
          </div>
          <div class="card">
            <div class="card-label">Confirmed Shakes</div>
            <div class="card-value" id="card-events">0</div>
            <div class="card-note">Active buffer window</div>
          </div>
        </div>
        <section class="panel" aria-labelledby="plot-title">
          <div class="plot-toolbar">
            <div>
              <h2 id="plot-title">Seismic Fingerprint & Peak Acceleration</h2>
              <div class="plot-status" id="plot-status">Waiting for UNO Q embedding stream</div>
            </div>
            <label class="control" for="threshold-input">
              Threshold
              <input id="threshold-input" type="number" min="0.1" max="10" step="0.1" value="1.80">
            </label>
          </div>
          <div class="plot-wrap">
            <canvas id="acceleration-plot" aria-label="Peak acceleration plot with magnitude thresholds"></canvas>
            <div class="plot-empty" id="plot-empty">Waiting for sensor embeddings...</div>
          </div>
          <div class="plot-legend" aria-label="Plot legend">
            <span class="legend-item" style="--legend-color:#5146e5">Peak Acceleration (m/s^2)</span>
            <span class="legend-item" style="--legend-color:#087a55">RMS Vibration Energy</span>
            <span class="legend-item" style="--legend-color:#e07a22">Medium Threshold</span>
            <span class="legend-item legend-event" style="--legend-color:#d43d51">Shake Event</span>
          </div>
        </section>
      {% elif active_tab == "analytics" %}
        <section class="panel placeholder">
          <h2>Embedding Analytics</h2>
          <p>Real-time telemetry stream processes through 16-D vector projections and cosine similarity matching.</p>
        </section>
      {% elif active_tab == "reports" %}
        <section class="panel">
          <h2>Recent reports</h2>
          <div class="activity"><span>Monthly performance summary</span><span>Oct 15</span></div>
          <div class="activity"><span>Website traffic overview</span><span>Oct 12</span></div>
          <div class="activity"><span>Project status report</span><span>Oct 08</span></div>
        </section>
      {% elif active_tab == "map" %}
        <section class="panel">
          <h2>World map</h2>
          <div id="map" role="region" aria-label="Interactive world map"></div>
        </section>
      {% else %}
        <section class="panel">
          <h2>Preferences</h2>
          <div class="setting-row"><div>Email notifications<br><span>Receive a weekly dashboard summary</span></div><strong>Enabled</strong></div>
          <div class="setting-row"><div>Display name<br><span>Shown on your workspace profile</span></div><strong>Jordan Davis</strong></div>
        </section>
      {% endif %}
    </main>
  </div>
  <script>
    const themeToggle = document.getElementById("theme-toggle");
    const themeLabel = document.getElementById("theme-label");

    function updateThemeButton() {
      const darkMode = document.documentElement.dataset.theme === "dark";
      themeToggle.setAttribute("aria-pressed", String(darkMode));
      themeToggle.setAttribute("aria-label", darkMode ? "Switch to light mode" : "Switch to dark mode");
      themeLabel.textContent = darkMode ? "Light mode" : "Dark mode";
    }

    updateThemeButton();
    themeToggle.addEventListener("click", () => {
      const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = nextTheme;
      localStorage.setItem("aftershock-theme", nextTheme);
      updateThemeButton();
    });
  </script>
  {% if active_tab == "overview" %}
    <script>
      const plot = document.getElementById("acceleration-plot");
      const plotEmpty = document.getElementById("plot-empty");
      const plotStatus = document.getElementById("plot-status");
      const thresholdInput = document.getElementById("threshold-input");
      const cardMagnitude = document.getElementById("card-magnitude");
      const cardStatus = document.getElementById("card-status");
      const cardCosine = document.getElementById("card-cosine");
      const cardEvents = document.getElementById("card-events");

      let samples = [];
      let usingDemoData = true;

      function drawPlot() {
        const bounds = plot.getBoundingClientRect();
        const scale = window.devicePixelRatio || 1;
        plot.width = Math.max(1, Math.floor(bounds.width * scale));
        plot.height = Math.max(1, Math.floor(bounds.height * scale));
        const context = plot.getContext("2d");
        context.setTransform(scale, 0, 0, scale, 0, 0);
        const width = bounds.width;
        const height = bounds.height;
        context.clearRect(0, 0, width, height);
        if (!samples.length) {
          plotEmpty.hidden = false;
          return;
        }
        plotEmpty.hidden = true;

        const values = samples.map((sample) => sample.acceleration);
        const rmsValues = samples.map((sample) => sample.rms || 0);
        const threshold = Number(thresholdInput.value) || 1.8;
        const maximum = Math.max(threshold * 1.25, ...values, ...rmsValues, 6.0);
        const minimum = Math.min(-0.05, ...values);
        const x = (index) => index * width / Math.max(1, samples.length - 1);
        const y = (value) => height - (value - minimum) * height / (maximum - minimum);

        context.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--border");
        context.lineWidth = 1;
        for (let row = 1; row < 4; row++) {
          const gridY = row * height / 4;
          context.beginPath();
          context.moveTo(0, gridY);
          context.lineTo(width, gridY);
          context.stroke();
        }

        // Threshold Line
        context.strokeStyle = "#e07a22";
        context.setLineDash([6, 5]);
        context.beginPath();
        context.moveTo(0, y(threshold));
        context.lineTo(width, y(threshold));
        context.stroke();
        context.setLineDash([]);

        // RMS Line
        if (samples.some((s) => s.rms !== undefined)) {
          context.strokeStyle = "#087a55";
          context.lineWidth = 1.5;
          context.beginPath();
          samples.forEach((sample, index) => {
            const pointX = x(index);
            const pointY = y(sample.rms || 0);
            index ? context.lineTo(pointX, pointY) : context.moveTo(pointX, pointY);
          });
          context.stroke();
        }

        // Peak Acceleration Line
        context.strokeStyle = "#5146e5";
        context.lineWidth = 2.2;
        context.beginPath();
        samples.forEach((sample, index) => {
          const pointX = x(index);
          const pointY = y(sample.acceleration);
          index ? context.lineTo(pointX, pointY) : context.moveTo(pointX, pointY);
        });
        context.stroke();

        // Event Markers
        context.fillStyle = "#d43d51";
        samples.forEach((sample, index) => {
          if (!sample.event) return;
          context.beginPath();
          context.arc(x(index), y(sample.acceleration), 4.5, 0, Math.PI * 2);
          context.fill();
        });
      }

      function addDemoSample() {
        if (!usingDemoData) return;
        const seconds = Date.now() / 1000;
        const event = Math.sin(seconds / 8) > 0.96;
        const acceleration = event
          ? 3.5 + Math.sin(seconds * 16) * 1.2
          : 0.15 + Math.sin(seconds * 4) * 0.05;
        samples.push({ acceleration, rms: acceleration * 0.4, cosine: 0.94, event });
        samples = samples.slice(-180);
        plotStatus.textContent = "Demo stream - waiting for UNO Q embeddings";
        drawPlot();
      }

      async function readTelemetry() {
        try {
          const response = await fetch("/api/telemetry", { cache: "no-store" });
          if (!response.ok) throw new Error("Telemetry request failed");
          const payload = await response.json();
          if (payload.samples.length) {
            samples = payload.samples;
            usingDemoData = false;
            const latest = samples[samples.length - 1];
            const eventCount = samples.filter((s) => s.event).length;

            cardMagnitude.textContent = latest.magnitude || "BASELINE";
            cardStatus.textContent = payload.sensor_status || "Vector DB Active";
            cardCosine.textContent = latest.cosine !== undefined ? Number(latest.cosine).toFixed(2) : "0.00";
            cardEvents.textContent = String(eventCount);
            plotStatus.textContent = `${payload.sensor_status} (${payload.samples.length} samples)`;
            drawPlot();
          } else {
            plotStatus.textContent = payload.sensor_status || "Waiting for telemetry";
            cardStatus.textContent = payload.sensor_status || "Waiting for telemetry";
          }
        } catch (error) {
          plotStatus.textContent = "Telemetry connection unavailable";
        }
      }

      window.addEventListener("resize", drawPlot);
      setInterval(readTelemetry, 500);
      setInterval(addDemoSample, 250);
      readTelemetry();
    </script>
  {% endif %}
  {% if active_tab == "map" %}
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
      const map = L.map("map").setView([20, 0], 2);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(map);
    </script>
  {% endif %}
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

@app.get("/api/telemetry")
def get_telemetry():
    with telemetry_lock:
        samples = list(telemetry)
        status = sensor_status
    return jsonify({"samples": samples, "sensor_status": status})

@app.post("/api/telemetry")
def add_telemetry():
    global sensor_status
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    try:
        acceleration = float(payload["acceleration"])
        threshold = float(payload.get("threshold", 1.8))
        event = bool(payload.get("event", False))
        rms = float(payload.get("rms", 0.0))
        cosine = float(payload.get("cosine", 0.0))
        magnitude = str(payload.get("magnitude", "BASELINE"))
        status_msg = str(payload.get("status", "Vector DB Stream Active"))
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Invalid numeric or string payload"}), 400

    sample = {
        "timestamp": time(),
        "acceleration": acceleration,
        "threshold": threshold,
        "event": event,
        "rms": rms,
        "cosine": cosine,
        "magnitude": magnitude,
    }
    with telemetry_lock:
        telemetry.append(sample)
        sensor_status = status_msg
    return jsonify(sample), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)