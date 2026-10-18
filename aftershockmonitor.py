import time
import math
from collections import deque
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from arduino.router_bridge import Bridge

# Sampling & Window Configuration
FREQUENCY_HZ = 50
WINDOW_SAMPLES = 50         # 1.0 second window (50 samples at 50 Hz)
STRIDE_SAMPLES = 5          # Run ML inference every 5 new samples (10 Hz inference rate)

# ML & Alert Thresholds
CALIBRATION_WINDOWS = 150   # ~15 seconds of ambient baseline collection for training
ANOMALY_THRESHOLD = 0.50    # Normalized ML anomaly score threshold [0.0 - 1.0]
REQUIRED_ANOMALY_PERCENT = 60
TRACKING_WINDOW_SEC = 5.0

# Sliding buffers storing (ax, ay, az) tuples for both sensors
buffer_mpu1 = deque(maxlen=WINDOW_SAMPLES)
buffer_mpu2 = deque(maxlen=WINDOW_SAMPLES)
samples_since_last_inference = 0

# ML Model State
training_features = []
scaler = StandardScaler()
ml_model = IsolationForest(
    n_estimators=100,
    contamination=0.02,     # Expect ~2% outlier rate in baseline noise
    random_state=42
)
is_model_trained = False

# Tracking Statistics
tracking_window_start = time.time()
last_debug_print = time.time()
total_inferences = 0
anomaly_count = 0

bridge = Bridge()
bridge.connect()


def extract_sensor_features(window_tuples):
    """
    Extracts 8 time-domain and frequency-domain (FFT) vibration features
    from a window of (x, y, z) accelerometer samples.
    """
    data = np.array(window_tuples, dtype=np.float64)  # Shape: (N, 3)

    # 1. Remove static gravity/tilt bias by subtracting the window mean per axis
    dynamic_xyz = data - np.mean(data, axis=0)

    # 2. Compute 3D dynamic vibration magnitude vector
    mag = np.linalg.norm(dynamic_xyz, axis=1)

    # 3. Time-domain statistical features
    rms = float(np.sqrt(np.mean(mag ** 2)))
    std = float(np.std(mag))
    peak = float(np.max(mag))
    p2p = float(np.ptp(mag))
    crest_factor = float(peak / (rms + 1e-6))

    # 4. Jerk features (rate of change of acceleration between samples)
    jerk = np.linalg.norm(np.diff(dynamic_xyz, axis=0), axis=1)
    jerk_mean = float(np.mean(jerk))
    jerk_max = float(np.max(jerk))

    # 5. Frequency-domain (FFT) features
    fft_vals = np.abs(np.fft.rfft(mag))
    fft_freqs = np.fft.rfftfreq(len(mag), d=1.0 / FREQUENCY_HZ)

    # Ignore DC component (index 0)
    if len(fft_vals) > 1:
        fft_vals_ac = fft_vals[1:]
        fft_freqs_ac = fft_freqs[1:]
        spectral_energy = float(np.sum(fft_vals_ac ** 2) / len(fft_vals_ac))
        spectral_centroid = float(
            np.sum(fft_freqs_ac * fft_vals_ac) / (np.sum(fft_vals_ac) + 1e-6)
        )
    else:
        spectral_energy = 0.0
        spectral_centroid = 0.0

    return [
        rms, std, p2p, crest_factor,
        jerk_mean, jerk_max,
        spectral_energy, spectral_centroid
    ]


def extract_dual_features(buf1, buf2):
    """Combines features from MPU1 and MPU2 plus cross-sensor correlation."""
    f1 = extract_sensor_features(buf1)
    f2 = extract_sensor_features(buf2)
    return f1 + f2


def run_ml_inference(feature_vector):
    """
    Runs the trained Isolation Forest model and maps its output to a
    normalized [0.0, 1.0] anomaly score.
    """
    X = np.array([feature_vector], dtype=np.float64)
    X_scaled = scaler.transform(X)

    # decision_function returns positive values for normal inliers,
    # and negative values for anomalies/outliers.
    raw_decision = float(ml_model.decision_function(X_scaled)[0])

    # Also measure Euclidean distance in standardized feature space (Z-score magnitude)
    z_distance = float(np.linalg.norm(X_scaled[0]) / math.sqrt(len(feature_vector)))

    # Map decision boundary + feature Z-score into a [0.0, 1.0] anomaly probability
    # When raw_decision < 0 (outlier), score rises above 0.50
    ml_score = 1.0 / (1.0 + math.exp(5.0 * raw_decision))

    # Blend with physical vibration gate so micro-quantization noise when dead still stays < 0.2
    rms_avg = (feature_vector[0] + feature_vector[8]) / 2.0
    if rms_avg < 0.03:
        return 0.0

    return min(max(ml_score, min(z_distance / 10.0, 1.0)), 1.0)


def on_accel_sample(ax1, ay1, az1, ax2, ay2, az2):
    global samples_since_last_inference, is_model_trained
    global tracking_window_start, last_debug_print, total_inferences, anomaly_count

    now = time.time()

    buffer_mpu1.append((ax1, ay1, az1))
    buffer_mpu2.append((ax2, ay2, az2))
    samples_since_last_inference += 1

    # Wait until sliding window is full and stride step is reached
    if len(buffer_mpu1) < WINDOW_SAMPLES or samples_since_last_inference < STRIDE_SAMPLES:
        return

    samples_since_last_inference = 0
    features = extract_dual_features(buffer_mpu1, buffer_mpu2)

    # --- PHASE 1: SELF-CALIBRATION / ML TRAINING ---
    if not is_model_trained:
        training_features.append(features)
        collected = len(training_features)

        if collected % 25 == 0 or collected == CALIBRATION_WINDOWS:
            print(f"[ML Calibration] Collecting baseline vibration... "
                  f"{collected}/{CALIBRATION_WINDOWS} windows")

        if collected >= CALIBRATION_WINDOWS:
            print("[ML Calibration] Fitting StandardScaler and IsolationForest (100 trees)...")
            X_train = np.array(training_features, dtype=np.float64)
            # Add tiny jitter to prevent zero-variance division if sensor is completely frozen
            X_train += np.random.normal(0, 1e-5, X_train.shape)
            X_train_scaled = scaler.fit_transform(X_train)
            ml_model.fit(X_train_scaled)

            is_model_trained = True
            tracking_window_start = time.time()
            print("[ML Ready] Isolation Forest trained! Live seismic monitoring active.")
        return

    # --- PHASE 2: LIVE ML INFERENCE ---
    anomaly_score = run_ml_inference(features)
    total_inferences += 1

    if anomaly_score > ANOMALY_THRESHOLD:
        anomaly_count += 1
        rms1, rms2 = features[0], features[8]
        freq1, freq2 = features[7], features[15]
        print(f"[ML Anomaly] Score: {anomaly_score:.2f} | "
              f"RMS: ({rms1:.2f}, {rms2:.2f}) m/s^2 | "
              f"Dom Freq: ({freq1:.1f}, {freq2:.1f}) Hz")

    # Evaluate 5-second tracking window
    if now - tracking_window_start >= TRACKING_WINDOW_SEC:
        if total_inferences > 0:
            density = (anomaly_count * 100) // total_inferences
            print(f"Window report: ML anomaly density {density}% "
                  f"({anomaly_count}/{total_inferences} inferences)")

            if density >= REQUIRED_ANOMALY_PERCENT:
                print(f"ALERT: Sustained aftershock confirmed (ML density: {density}%)")
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


bridge.provide("accel_sample", on_accel_sample)

print(f"Starting Dual-MPU6050 ML Monitor ({FREQUENCY_HZ} Hz)...")
print("Keep sensors still for ~15 seconds during baseline ML calibration.")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping ML seismic monitor...")
finally:
    bridge.disconnect()