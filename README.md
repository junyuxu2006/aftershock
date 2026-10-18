# Aftershock

## Dashboard

The dashboard runs on the UNO Q's Debian Linux side. From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python dashboard.py
```

Open `http://127.0.0.1:5000`. The Overview page includes a computer plot of acceleration, a configurable detection threshold, and event markers. Until telemetry arrives, it displays a clearly labeled demo stream.

## Sending UNO Q telemetry

The dashboard accepts JSON samples at `POST /api/telemetry`:

```bash
curl -X POST http://127.0.0.1:5000/api/telemetry \
  -H "Content-Type: application/json" \
  -d '{"acceleration": 1.82, "threshold": 1.50, "event": true}'
```

`acceleration` and `threshold` are measured in g. `event` is optional; when omitted, the server marks the sample as an event when acceleration is at or above the threshold. The latest 240 samples are retained in memory.

To access the dashboard from another computer on the same network, change the `app.run` call in `dashboard.py` to use `host="0.0.0.0"`, then browse to `http://<UNO-Q-IP>:5000`.

## Debian ML monitor

`ml.cpp` is a standalone C++17 program and does not require Arduino libraries:

```bash
sudo apt update
sudo apt install -y g++
g++ -std=c++17 -O2 -Wall -Wextra -pedantic ml.cpp -o aftershock_ml
./aftershock_ml --seconds 15
```

The program runs continuously when `--seconds` is omitted and stops with
`Ctrl-C`. Use `--event` to exercise the sustained-event alert using simulated
accelerometer data:

```bash
./aftershock_ml --event --seconds 15
```

The sensor input and inference function are isolated in `ml.cpp` so they can
be replaced with the UNO Q sensor and deployed model without changing the
sampling and temporal tracking logic.
