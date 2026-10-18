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

## Shared MPU6050 telemetry

`ml.cpp` is the single MPU6050 reader. It reads both sensors at 50 Hz, runs
the detector, and publishes the exact selected sensor reading to the
dashboard. This prevents the C++ program and Flask from performing separate
I2C reads at different times. The dashboard only stores and displays the
samples received from `ml.cpp`.

The setup expects sensor `0x68` with `AD0` connected to GND and sensor `0x69`
with `AD0` connected to 3.3V. Install the I2C tools and C++ HTTP library on
the UNO Q:

```bash
sudo apt install -y g++ make libcurl4-openssl-dev i2c-tools
python3 -m pip install -r requirements.txt
sudo i2cdetect -y 1
```

Start the dashboard first:

```bash
python dashboard.py
```

Then build and start the shared reader:

```bash
make
./aftershock_ml
```

The dashboard plots the larger total acceleration from either sensor, in `g`,
and marks values at or above `1.5g` as events. If the dashboard runs on another
computer, set its URL before starting the reader:

```bash
AFTERSHOCK_TELEMETRY_URL=http://<dashboard-ip>:5000/api/telemetry ./aftershock_ml
```

Override the I2C bus or sensor addresses with `MPU6050_I2C_BUS`,
`MPU6050_I2C_ADDRESS_1`, and `MPU6050_I2C_ADDRESS_2`.

## Debian ML monitor

`ml.cpp` is a standalone C++17 program and does not require Arduino libraries:

```bash
sudo apt update
sudo apt install -y g++
make
./aftershock_ml --seconds 15
```

The program runs continuously when `--seconds` is omitted and stops with
`Ctrl-C`. The program reads a real MPU6050 over Linux I2C. Install the I2C tools and
verify that the sensor is visible:

```bash
sudo apt install -y i2c-tools
sudo i2cdetect -y 1
make
./aftershock_ml --seconds 15
```

The default bus is `/dev/i2c-1` and the default MPU6050 address is `0x68`.
For a sensor wired to address `0x69`, run:

```bash
MPU6050_I2C_ADDRESS=0x69 ./aftershock_ml
```

Set `MPU6050_I2C_BUS` if the sensor is on another I2C bus. The sensor input
and inference function are isolated in `ml.cpp`, so the deployed model can be
added without changing the sampling and temporal tracking logic.

Use `make clean` to remove the compiled executable.
