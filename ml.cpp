#include <Your_Earthquake_Project_Inferencing.h> // Replace with your actual Edge Impulse header
// #include <Adafruit_MPU6050.h>                 // Uncomment if using a standard MPU6050 sensor

// --- Hardware & ML Configuration ---
#define FREQUENCY_HZ        50      // Match the sampling frequency your ML model was trained on
#define INTERVAL_MS         (1000 / FREQUENCY_HZ) 
#define EI_CLASSIFIER_NN_INPUT_FRAME_SIZE  (EI_CLASSIFIER_RAW_SAMPLE_COUNT) // Total buffer size (e.g., 3 axes * 100 samples)

// --- Sustained Event Logic Parameters ---
const float ANOMALY_THRESHOLD = 0.35;        // Adjust based on your Edge Impulse testing
const unsigned long TRACKING_WINDOW_MS = 5000; // Look at a rolling 5-second window
const int REQUIRED_ANOMALY_PERCENT = 70;     // Event triggers if >70% of windows are abnormal

// --- Global Buffers & States ---
float featuresBuffer[EI_CLASSIFIER_NN_INPUT_FRAME_SIZE];
int bufferIndex = 0;
unsigned long lastSampleTime = 0;

// Temporal tracking variables
unsigned long trackingWindowStart = 0;
int totalInferencesInWindow = 0;
int anomalyCountInWindow = 0;

// Simulated or Real Sensor Hook
void getAccelerometerData(float *x, float *y, float *z) {
    // REPLACE with your real sensor reading, e.g.:
    // sensors_event_t a, g, temp;
    // mpu.getEvent(&a, &g, &temp);
    // *x = a.acceleration.x; *y = a.acceleration.y; *z = a.acceleration.z;
    
    // Fallback simulation (Static baseline)
    *x = 0.00 + ((float)random(-5, 5) / 100.0); 
    *y = 0.00 + ((float)random(-5, 5) / 100.0);
    *z = 9.81 + ((float)random(-5, 5) / 100.0); // Gravity baseline
}

void setup() {
    Serial.begin(115200);
    while (!Serial);
    Serial.println("地震/Aftershock Monitor Initialized. Gathering baseline...");
    
    trackingWindowStart = millis();
}

void loop() {
    unsigned long currentTime = millis();

    // 1. Maintain strict sampling rate to feed the time-series window
    if (currentTime - lastSampleTime >= INTERVAL_MS) {
        lastSampleTime = currentTime;

        float ax, ay, az;
        getAccelerometerData(&ax, &ay, &az);

        // Fill the rolling buffer sequentially: X, Y, Z, X, Y, Z...
        featuresBuffer[bufferIndex++] = ax;
        featuresBuffer[bufferIndex++] = ay;
        featuresBuffer[bufferIndex++] = az;

        // 2. Once the buffer window is completely full, run ML analysis
        if (bufferIndex >= EI_CLASSIFIER_NN_INPUT_FRAME_SIZE) {
            
            // Map buffer to Edge Impulse signal format
            signal_t signal;
            numpy::signal_from_buffer(featuresBuffer, EI_CLASSIFIER_NN_INPUT_FRAME_SIZE, &signal);

            // Run Inference
            ei_impulse_result_t result = { 0 };
            EI_IMPULSE_ERROR res = run_classifier(&signal, &result, false);
            
            if (res == EI_IMPULSE_OK) {
                float anomalyScore = result.anomaly;
                totalInferencesInWindow++;

                if (anomalyScore > ANOMALY_THRESHOLD) {
                    anomalyCountInWindow++;
                    Serial.print("⚠️ Localized Anomaly Detected! Score: "); Serial.println(anomalyScore);
                }
            }

            // Shift the buffer backward (Sliding window logic) 
            // Instead of wiping the buffer to 0, we drop the oldest sample to react faster
            int shiftAmount = 3; // Shift by 1 full X/Y/Z triplet
            memmove(featuresBuffer, &featuresBuffer[shiftAmount], (EI_CLASSIFIER_NN_INPUT_FRAME_SIZE - shiftAmount) * sizeof(float));
            bufferIndex = EI_CLASSIFIER_NN_INPUT_FRAME_SIZE - shiftAmount;
        }
    }

    // 3. Evaluate the temporal window to confirm a "Sustained" Event
    if (currentTime - trackingWindowStart >= TRACKING_WINDOW_MS) {
        if (totalInferencesInWindow > 0) {
            int anomalyPercentage = (anomalyCountInWindow * 100) / totalInferencesInWindow;
            
            Serial.print("[Window Report] Anomaly Density: "); Serial.print(anomalyPercentage); Serial.println("%");

            if (anomalyPercentage >= REQUIRED_ANOMALY_PERCENT) {
                triggerSustainedAftershockAlert(anomalyPercentage);
            }
        }

        // Reset temporal evaluation variables for the next period
        trackingWindowStart = currentTime;
        totalInferencesInWindow = 0;
        anomalyCountInWindow = 0;
    }
}

void triggerSustainedAftershockAlert(int density) {
    Serial.print("🚨 ALERT: Sustained aftershock / seismic event confirmed! (Density: ");
    Serial.print(density);
    Serial.println("%) Shutting down critical systems...");
    // Action items: Open automated emergency doors, cut main gas valves, trigger sirens.
}