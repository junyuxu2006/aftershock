from flask import Flask, abort, render_template_string

app = Flask(__name__)

TABS = {
    "overview": {
        "label": "Overview",
        "title": "Overview",
        "description": "A quick look at how things are going.",
    },
    "analytics": {
        "label": "Analytics",
        "title": "Analytics",
        "description": "Explore activity and performance at a glance.",
    },
    "reports": {
        "label": "Reports",
        "title": "Reports",
        "description": "Your latest reports are collected here.",
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
  <title>{{ tab.title }} · Aftershock</title>
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
    .card-value { margin: 14px 0 5px; font-size: 30px; font-weight: 750; letter-spacing: -.04em; }
    .card-note { color: var(--positive); font-size: 13px; font-weight: 600; }
    .panel { padding: 24px; }
    .panel h2 { margin: 0 0 18px; font-size: 18px; }
    .activity { display: grid; grid-template-columns: 1fr auto; gap: 14px; padding: 15px 0; border-top: 1px solid var(--border); font-size: 15px; line-height: 1.5; }
    .activity span:last-child { color: var(--muted); font-size: 14px; }
    .placeholder { padding: 32px; color: var(--muted); line-height: 1.7; }
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
    @media (max-width: 430px) {
      .topbar { align-items: flex-start; }
      .topbar-actions { gap: 8px; }
      .theme-toggle { padding-inline: 10px; }
      .crumb { max-width: 100px; line-height: 1.5; }
      .activity { grid-template-columns: 1fr; gap: 3px; }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <div class="layout">
    <aside aria-label="Sidebar">
      <p class="brand"><span>◆</span> Aftershock</p>
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
            <span aria-hidden="true">◐</span><span id="theme-label">Dark mode</span>
          </button>
          <div class="avatar" role="img" aria-label="Jordan Davis profile">JD</div>
        </div>
      </div>
      <h1>{{ tab.title }}</h1>
      <p class="description">{{ tab.description }}</p>
      {% if active_tab == "overview" %}
        <section class="cards" aria-label="Key metrics">
          <article class="card"><div class="card-label">Total visitors</div><div class="card-value">12,486</div><div class="card-note">↑ 8.2% this month</div></article>
          <article class="card"><div class="card-label">Active projects</div><div class="card-value">24</div><div class="card-note">↑ 3 added this week</div></article>
          <article class="card"><div class="card-label">Completion rate</div><div class="card-value">82%</div><div class="card-note">↑ 4.6% this month</div></article>
        </section>
        <section class="panel">
          <h2>Recent activity</h2>
          <div class="activity"><span>Website redesign moved to review</span><span>10 min ago</span></div>
          <div class="activity"><span>Monthly report was generated</span><span>2 hours ago</span></div>
          <div class="activity"><span>New team member joined</span><span>Yesterday</span></div>
        </section>
      {% elif active_tab == "analytics" %}
        <section class="panel placeholder">
          <h2>Analytics snapshot</h2>
          <p>Your analytics workspace is ready. Connect a data source to replace these sample dashboard metrics with live data.</p>
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
  {% if active_tab == "map" %}
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
      const map = L.map("map").setView([20, 0], 2);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
      }).addTo(map);
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

    return render_template_string(
        PAGE,
        tabs=TABS,
        active_tab=tab_name,
        tab=tab,
    )


if __name__ == "__main__":
    app.run(debug=True)