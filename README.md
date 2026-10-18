# Aftershock

## Dashboard

The dashboard runs on the UNO Q's Debian Linux side. From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python dashboard.py
```

Open `http://127.0.0.1:5000` on the UNO Q itself. The Overview page includes a
computer plot of acceleration, a configurable detection threshold, and event
markers. Until telemetry arrives, it displays a clearly labeled demo stream.

## Accessing the dashboard from another laptop

The dashboard listens on all UNO Q network interfaces by default. Find the
UNO Q's LAN/Wi-Fi address on its Debian terminal:

```bash
hostname -I
```

If it prints `192.168.1.42`, open this URL from another laptop connected to the
same network:

```text
http://192.168.1.42:5000
```

Use the UNO Q's current IP address, not `127.0.0.1`. The IP may change after
reconnecting to Wi-Fi, so reserve an address in the router or configure a
static address if this is a permanent setup.

For a laptop on a different network, a private address such as `192.168.x.x`
is not reachable directly. Use a VPN/mesh VPN (for example, Tailscale or
WireGuard) on both devices, then open the UNO Q's VPN address:

```text
http://<UNO-Q-VPN-IP>:5000
```

Do not expose Flask's development server directly to the public Internet with
router port forwarding. If public access is required, put the dashboard behind
an authenticated production reverse proxy and HTTPS.

## Sending UNO Q telemetry

The dashboard accepts JSON samples at `POST /api/telemetry`:

```bash
curl -X POST http://127.0.0.1:5000/api/telemetry \
  -H "Content-Type: application/json" \
  -d '{"acceleration": 1.82, "threshold": 1.50, "event": true}'
```

`acceleration` and `threshold` are measured in g. `event` is optional; when omitted, the server marks the sample as an event when acceleration is at or above the threshold. The latest 240 samples are retained in memory.

To override the default listener or port:

```bash
AFTERSHOCK_HOST=0.0.0.0 AFTERSHOCK_PORT=5000 python dashboard.py
```

## Debian ML monitor

`ml.cpp` is a standalone C++17 program and does not require Arduino libraries:

```bash
sudo apt update
sudo apt install -y g++
make
./aftershock_ml --seconds 15
```

The program runs continuously when `--seconds` is omitted and stops with
`Ctrl-C`. Use `--event` to exercise the sustained-event alert using simulated
accelerometer data:

```bash
make event
```

The sensor input and inference function are isolated in `ml.cpp` so they can
be replaced with the UNO Q sensor and deployed model without changing the
sampling and temporal tracking logic.

Use `make clean` to remove the compiled executable.
