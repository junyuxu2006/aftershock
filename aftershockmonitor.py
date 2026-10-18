import os
import time
import math
import json
import queue
import threading
import urllib.request
import urllib.error
from collections import deque
import numpy as np
from arduino.router_bridge import Bridge

# Dashboard Endpoint Configuration
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://127.0.0.1:5000/api/telemetry")
telemetry_queue = queue.Queue(maxsize=100)
led_queue = queue.Queue(maxsize=1)

# Sampling & Window Configuration
FREQUENCY_HZ = 50
WINDOW_SAMPLES = 50         # 1.0 second window (50 samples at 50 Hz)
STRIDE_SAMPLES = 5          # Run embedding search every 5 samples (10 Hz)

# Calibration & Alert Thresholds
CALIBRATION_WINDOWS = 80    # ~8 seconds of ambient baseline calibration
REQUIRED_ANOMALY_PERCENT = 50
TRACKING_WINDOW_SEC = 5.0
LOW_RMS_LIMIT = 0.45
MEDIUM_RMS_LIMIT = 1.20
LOW_PEAK_LIMIT = 1.80
MEDIUM_PEAK_LIMIT = 3.80

# Sliding buffers storing (ax, ay, az) tuples for both sensors
buffer_mpu1 = deque(maxlen=WINDOW_SAMPLES)
buffer_mpu2 = deque(maxlen=WINDOW_SAMPLES)
samples_since_last_inference = 0

# Embedding Memory Bank (Centroids learned + anchored at calibration)
is_calibrated = False
baseline_noise_floor = 0.05
shape_prototypes = {}       # Unit vectors for Cosine Similarity (Wave Shape)
magnitude_centroids = {}    # Energy vectors for Magnitude Tier (Low / Med / High)

# Tracking Statistics
tracking_window_start = time.time()
total_inferences = 0
anomaly_count = 0
window_mag_counts = {"BASELINE": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0}


def dashboard_sender_worker():
    """Background worker that POSTs telemetry to dashboard.py without blocking the STM32 bridge."""
    while True:
        payload = telemetry_queue.get()
        if payload is None:
            break
        try:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                DASHBOARD_URL,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=0.4) as response:
                if response.status != 201:
                    print(
                        f"Dashboard rejected telemetry: HTTP {response.status} "
                        f"({DASHBOARD_URL})"
                    )
        except urllib.error.HTTPError as error:
            print(f"Dashboard telemetry HTTP error {error.code}: {DASHBOARD_URL}")
        except urllib.error.URLError as error:
            print(f"Dashboard telemetry connection failed: {error.reason}")
        finally:
            telemetry_queue.task_done()


def push_to_dashboard(peak_accel, rms_val, cosine_val, mag_label, is_event, status_text):
    payload = {
        "acceleration": round(float(peak_accel), 4),
        "threshold": 1.80,
        "event": bool(is_event),
        "rms": round(float(rms_val), 4),
        "cosine": round(float(cosine_val), 2),
        "magnitude": str(mag_label),
        "status": status_text,
    }
    try:
        telemetry_queue.put_nowait(payload)
    except queue.Full:
        pass


def set_magnitude_led(magnitude):
    try:
        led_queue.put_nowait(str(magnitude))
    except queue.Full:
        try:
            led_queue.get_nowait()
            led_queue.task_done()
        except queue.Empty:
            pass
        try:
            led_queue.put_nowait(str(magnitude))
        except queue.Full:
            pass


def led_worker():
    while True:
        magnitude = led_queue.get()
        if magnitude is None:
            led_queue.task_done()
            return
        try:
            bridge.call("set_magnitude_led", magnitude)
        except Exception as error:
            print(f"Error setting RGB LED: {error}")
        finally:
            led_queue.task_done()


sender_thread = threading.Thread(target=dashboard_sender_worker, daemon=True)
sender_thread.start()

bridge = Bridge()
bridge.connect()
led_thread = threading.Thread(target=led_worker, daemon=True)
led_thread.start()


def extract_sensor_stats(window_tuples):
    """Extracts 7 physical & spectral features from a single MPU6050 1-second window."""
    data = np.array(window_tuples, dtype=np.float64)
    # Subtract mean per axis to isolate dynamic motion from 9.8 m/s^2 gravity
    dynamic_xyz = data - np.mean(data, axis=0)
    mag = np.linalg.norm(dynamic_xyz, axis=1)

    rms = float(np.sqrt(np.mean(mag ** 2)))
    std = float(np.std(mag))
    peak = float(np.max(mag))
    p2p = float(np.ptp(mag))
    # Crest factor: ratio of Peak to RMS (Low ~1.5-2.5 = rolling wave, High >4.0 = sharp knock/tap)
    crest_factor = float(peak / (rms + 1e-4))

    jerk = np.linalg.norm(np.diff(dynamic_xyz, axis=0), axis=1)
    jerk_mean = float(np.mean(jerk))

    # FFT Spectral Centroid (Dominant Frequency in Hz)
    fft_vals = np.abs(np.fft.rfft(mag))[1:]
    fft_freqs = np.fft.rfftfreq(len(mag), d=1.0 / FREQUENCY_HZ)[1:]
    if len(fft_vals) > 0 and np.sum(fft_vals) > 1e-5:
        dom_freq = float(np.sum(fft_freqs * fft_vals) / np.sum(fft_vals))
        low_band_ratio = float(np.sum(fft_vals[fft_freqs <= 12.0]) / np.sum(fft_vals))
    else:
        dom_freq = 0.0
        low_band_ratio = 0.5

    return mag, [rms, std, peak, p2p, crest_factor, jerk_mean, dom_freq, low_band_ratio]


def build_seismic_embedding(buf1, buf2):
    """
    Creates the 16-Dimensional Seismic Fingerprint (Embedding) from both MPU6050s:
      - 8 features from MPU1
      - 7 features from MPU2
      - 1 Cross-Sensor Spatial Coherence feature (do both sensors feel the exact same wave?)
    Also splits out a 'Shape Embedding' (for Cosine Similarity) and 'Energy Embedding' (for Magnitude).
    """
    mag1, f1 = extract_sensor_stats(buf1)
    mag2, f2 = extract_sensor_stats(buf2)

    # Cross-sensor coherence: 1.0 if both sensors experience identical intensity & timing
    energy_symmetry = 1.0 - abs(f1[0] - f2[0]) / (f1[0] + f2[0] + 1e-4)
    if np.std(mag1) > 1e-4 and np.std(mag2) > 1e-4:
        corr = float(np.corrcoef(mag1, mag2)[0, 1])
        coherence = max(0.0, (corr + 1.0) / 2.0) * energy_symmetry
    else:
        coherence = energy_symmetry

    # Full 16-D Seismic Fingerprint
    full_16d = np.array(f1 + f2[:7] + [coherence], dtype=np.float64)

    # Averages across both sensors for interpretable sub-spaces
    rms_avg = (f1[0] + f2[0]) / 2.0
    std_avg = (f1[1] + f2[1]) / 2.0
    peak_avg = (f1[2] + f2[2]) / 2.0
    p2p_avg = (f1[3] + f2[3]) / 2.0
    crest_avg = (f1[4] + f2[4]) / 2.0
    jerk_avg = (f1[5] + f2[5]) / 2.0
    freq_avg = (f1[6] + f2[6]) / 2.0
    low_band_avg = (f1[7] + f2[7]) / 2.0

    # 1. SHAPE EMBEDDING (Scale-Invariant features normalized to unit sphere for Cosine Similarity)
    # Captures: [Sustained Ratio (RMS/Peak), Crest Factor, Low-Freq Seismic Ratio, Spatial Coherence]
    sustained_ratio = rms_avg / (peak_avg + 1e-4)
    raw_shape = np.array([
        sustained_ratio * 2.5,          # High for rolling seismic waves, low for single taps
        1.0 / (crest_avg + 0.5),        # Inverse crest factor (penalizes sharp transient spikes)
        low_band_avg,                   # Earthquakes concentrate energy in 1 - 12 Hz band
        coherence,                      # Dual-sensor spatial agreement
    ], dtype=np.float64)
    shape_unit_emb = raw_shape / (np.linalg.norm(raw_shape) + 1e-8)

    # 2. ENERGY EMBEDDING (For Low / Medium / High Magnitude clustering up to 6.0 m/s^2)
    energy_emb = np.array([peak_avg, rms_avg, std_avg, p2p_avg, jerk_avg], dtype=np.float64)

    meta = {
        "rms": rms_avg,
        "peak": peak_avg,
        "freq": freq_avg,
        "crest": crest_avg,
        "coherence": coherence,
    }
    return full_16d, shape_unit_emb, energy_emb, meta


def init_embedding_database(baseline_energy_list):
    """Initializes the Vector Database of Prototype Embeddings after calibration."""
    global baseline_noise_floor, shape_prototypes, magnitude_centroids

    base_mat = np.array(baseline_energy_list, dtype=np.float64)
    base_centroid = np.mean(base_mat, axis=0)
    baseline_noise_floor = float(max(base_centroid[0] * 2.5, 0.28))

    # --- A. WAVEFORM SHAPE PROTOTYPES (Unit Vectors for Cosine Similarity) ---
    # 1. Rolling Seismic Wave: High sustained RMS/Peak, low crest factor, strong 1-12Hz band, high dual-sensor coherence
    seismic_proto = np.array([1.15, 0.42, 0.85, 0.92], dtype=np.float64)
    # 2. Sharp Impact / Desk Knock: Low sustained ratio, high crest factor, high-freq spike
    impact_proto = np.array([0.45, 0.18, 0.35, 0.55], dtype=np.float64)

    shape_prototypes["SEISMIC_WAVE"] = seismic_proto / np.linalg.norm(seismic_proto)
    shape_prototypes["IMPACT_KNOCK"] = impact_proto / np.linalg.norm(impact_proto)

    # --- B. MAGNITUDE ENERGY CENTROIDS ([Peak, RMS, Std, P2P, Jerk] in m/s^2) ---
    # Anchored across your 0.0 to 6.0 m/s^2 physical test range
    magnitude_centroids["BASELINE"] = base_centroid
    magnitude_centroids["LOW"] = np.array([1.05, 0.45, 0.40, 1.85, 0.32], dtype=np.float64)     # ~0.35 - 1.8 m/s^2
    magnitude_centroids["MEDIUM"] = np.array([2.75, 1.20, 1.05, 4.80, 0.85], dtype=np.float64)  # ~1.80 - 3.8 m/s^2
    magnitude_centroids["HIGH"] = np.array([5.10, 2.30, 2.00, 8.90, 1.65], dtype=np.float64)    # ~3.80 - 6.0+ m/s^2


def query_embedding_space(shape_unit_emb, energy_emb, meta):
    """
    Queries the live window's embedding against our prototype vectors using:
      1. Cosine Similarity (dot product of unit vectors) for Waveform Shape
      2. Embedding Distance for Magnitude Classification (BASELINE, LOW, MEDIUM, HIGH)
    """
    peak = meta["peak"]
    rms = meta["rms"]

    # 1. Dead-still noise gate. Keep the learned baseline in the decision so
    # small movements do not get forced into an anomaly tier.
    baseline_rms = max(float(magnitude_centroids["BASELINE"][1]), 0.08)
    if peak < max(baseline_noise_floor, 0.28) and rms < baseline_rms * 2.5:
        return "BASELINE", "QUIET", 1.0, 0.0

    # 2. Cosine Similarity for Waveform Signature (Dot product of L2-normalized vectors)
    sim_seismic = float(np.dot(shape_unit_emb, shape_prototypes["SEISMIC_WAVE"]))
    sim_impact = float(np.dot(shape_unit_emb, shape_prototypes["IMPACT_KNOCK"]))
    wave_type = "SEISMIC" if sim_seismic >= sim_impact else "IMPACT"

    # 3. Use physical energy bands for magnitude. RMS is the primary measure
    # so one short spike cannot turn a small shake into a HIGH event.
    if rms < LOW_RMS_LIMIT and peak < LOW_PEAK_LIMIT:
        mag_label = "LOW"
        limit = LOW_RMS_LIMIT
    elif rms < MEDIUM_RMS_LIMIT and peak < MEDIUM_PEAK_LIMIT:
        mag_label = "MEDIUM"
        limit = MEDIUM_RMS_LIMIT
    else:
        mag_label = "HIGH"
        limit = MEDIUM_RMS_LIMIT

    confidence = min(max(rms / max(limit, 1e-6), 0.0), 0.99)

    return mag_label, wave_type, min(confidence, 0.99), sim_seismic


baseline_energy_samples = []


def on_accel_sample(ax1, ay1, az1, ax2, ay2, az2):
    global samples_since_last_inference, is_calibrated
    global tracking_window_start, total_inferences, anomaly_count, window_mag_counts

    now = time.time()

    buffer_mpu1.append((ax1, ay1, az1))
    buffer_mpu2.append((ax2, ay2, az2))
    samples_since_last_inference += 1

    if len(buffer_mpu1) < WINDOW_SAMPLES or samples_since_last_inference < STRIDE_SAMPLES:
        return

    samples_since_last_inference = 0
    _, shape_emb, energy_emb, meta = build_seismic_embedding(buffer_mpu1, buffer_mpu2)

    # --- PHASE 1: BASELINE EMBEDDING CALIBRATION ---
    if not is_calibrated:
        baseline_energy_samples.append(energy_emb)
        collected = len(baseline_energy_samples)

        push_to_dashboard(
            peak_accel=meta["peak"],
            rms_val=meta["rms"],
            cosine_val=0.0,
            mag_label="CALIBRATING",
            is_event=False,
            status_text=(
                f"Learning Baseline Embedding "
                f"({collected}/{CALIBRATION_WINDOWS})"
            ),
        )
        set_magnitude_led("BASELINE")

        if collected % 20 == 0 or collected == CALIBRATION_WINDOWS:
            print(f"[Embedding Calibration] Sampling ambient room vector... "
                  f"{collected}/{CALIBRATION_WINDOWS}")

        if collected >= CALIBRATION_WINDOWS:
            init_embedding_database(baseline_energy_samples)
            is_calibrated = True
            tracking_window_start = time.time()
            print(f"[Embeddings Ready] Noise floor: {baseline_noise_floor:.2f} m/s^2 | "
                  f"Vector Search Active (LOW / MEDIUM / HIGH)")
        return

    # --- PHASE 2: LIVE VECTOR SIMILARITY SEARCH ---
    mag_label, wave_type, conf, cosine_sim = query_embedding_space(shape_emb, energy_emb, meta)
    is_anomaly = mag_label != "BASELINE"

    total_inferences += 1
    window_mag_counts[mag_label] += 1

    status_str = (
        f"{mag_label} ({wave_type} | Cosine Sim: {cosine_sim:.2f}) - Peak: {meta['peak']:.2f} m/s^2"
        if is_anomaly
        else f"BASELINE (Cosine Sim: {cosine_sim:.2f}) - Peak: {meta['peak']:.2f} m/s^2"
    )

    push_to_dashboard(
        peak_accel=meta["peak"],
        rms_val=meta["rms"],
        cosine_val=cosine_sim,
        mag_label=mag_label,
        is_event=is_anomaly,
        status_text=status_str,
    )
    set_magnitude_led(mag_label)

    if is_anomaly:
        anomaly_count += 1
        print(
            f"[{mag_label} | {wave_type}] CosineSim: {cosine_sim:.2f} | "
            f"Conf: {conf*100:.0f}% | Peak: {meta['peak']:.2f} m/s^2 | "
            f"RMS: {meta['rms']:.2f} | Freq: {meta['freq']:.1f} Hz | "
            f"Coherence: {meta['coherence']:.2f}"
        )

    # Evaluate 5-second tracking window
    if now - tracking_window_start >= TRACKING_WINDOW_SEC:
        if total_inferences > 0:
            density = (anomaly_count * 100) // total_inferences
            dominant_mag = "BASELINE"
            if anomaly_count > 0:
                dominant_mag = max(["LOW", "MEDIUM", "HIGH"], key=lambda k: window_mag_counts[k])

            print(
                f"Window report: Density {density}% ({anomaly_count}/{total_inferences}) | "
                f"Magnitude: {dominant_mag} "
                f"[Low:{window_mag_counts['LOW']} Med:{window_mag_counts['MEDIUM']} High:{window_mag_counts['HIGH']}]"
            )

            if density >= REQUIRED_ANOMALY_PERCENT:
                print(f"ALERT: Sustained {dominant_mag} aftershock confirmed (density: {density}%)")
                try:
                    bridge.call("trigger_alert", True)
                except Exception as e:
                    print(f"Error calling trigger_alert: {e}")
            else:
                try:
                    bridge.call("trigger_alert", False)
                except Exception:
                    pass

        tracking_window_start = now
        total_inferences = 0
        anomaly_count = 0
        window_mag_counts = {"BASELINE": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0}


# Cleanly release the route if a previous run left it registered
try:
    bridge.unprovide("accel_sample")
except Exception:
    pass

bridge.provide("accel_sample", on_accel_sample)

print(
    f"Starting Dual-MPU6050 Seismic Fingerprint Monitor "
    f"({FREQUENCY_HZ} Hz) -> {DASHBOARD_URL}"
)
print("Keep sensors still for ~8 seconds to learn the room's baseline embedding.")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping seismic monitor...")
finally:
    led_queue.put(None)
    led_thread.join(timeout=1.0)
    try:
        bridge.unprovide("accel_sample")
    except Exception:
        pass
    bridge.disconnect()