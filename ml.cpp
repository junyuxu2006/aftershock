/*
 * Debian/Linux standalone aftershock monitor.
 *
 * Build:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic ml.cpp -o aftershock_ml
 *
 * The sensor and model hooks below are deliberately self-contained so the
 * program can be run on a Debian UNO Q without Arduino headers. Replace
 * getAccelerometerData() and runInference() with the real sensor/model
 * integration when those components are available.
 */

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <random>
#include <string_view>
#include <thread>

namespace {

constexpr int FREQUENCY_HZ = 50;
constexpr int INTERVAL_MS = 1000 / FREQUENCY_HZ;
constexpr std::size_t AXES = 3;
constexpr std::size_t SAMPLE_COUNT = 100;
constexpr std::size_t FRAME_SIZE = AXES * SAMPLE_COUNT;

constexpr float ANOMALY_THRESHOLD = 0.35F;
constexpr std::chrono::milliseconds TRACKING_WINDOW{5000};
constexpr int REQUIRED_ANOMALY_PERCENT = 70;

volatile std::sig_atomic_t running = 1;

struct Acceleration {
    float x;
    float y;
    float z;
};

void stopMonitor(int) {
    running = 0;
}

class SensorSimulator {
public:
    explicit SensorSimulator(bool eventMode)
        : eventMode_(eventMode), noise_(-0.05F, 0.05F), random_(std::random_device{}()) {}

    Acceleration read() {
        const bool eventSample = eventMode_ && (sampleNumber_ % FREQUENCY_HZ < FREQUENCY_HZ / 2);
        ++sampleNumber_;
        const float vibration = eventSample ? 2.0F : 0.0F;
        return {noise_(random_) + vibration, noise_(random_) + vibration,
                9.81F + noise_(random_)};
    }

private:
    bool eventMode_;
    std::size_t sampleNumber_ = 0;
    std::uniform_real_distribution<float> noise_;
    std::mt19937 random_;
};

// Replace this with the deployed ML model call. The score is normalized to
// the same [0, 1] range used by the original Edge Impulse implementation.
float runInference(const float* features, std::size_t featureCount) {
    float score = 0.0F;
    for (std::size_t index = 0; index + 2 < featureCount; index += AXES) {
        const float horizontalAcceleration =
            std::hypot(features[index], features[index + 1]);
        score = std::max(score, std::min(horizontalAcceleration / 4.0F, 1.0F));
    }
    return score;
}

void printAlert(int density) {
    std::cout << "ALERT: Sustained aftershock / seismic event confirmed "
              << "(density: " << density << "%)\n";
}

int parseDuration(int argc, char* argv[]) {
    for (int index = 1; index + 1 < argc; ++index) {
        if (std::string_view(argv[index]) == "--seconds") {
            const int seconds = std::atoi(argv[index + 1]);
            return std::max(seconds, 0);
        }
    }
    return 0;
}

bool hasArgument(int argc, char* argv[], std::string_view argument) {
    for (int index = 1; index < argc; ++index) {
        if (std::string_view(argv[index]) == argument) {
            return true;
        }
    }
    return false;
}

}  // namespace

int main(int argc, char* argv[]) {
    const int durationSeconds = parseDuration(argc, argv);
    const bool eventMode = hasArgument(argc, argv, "--event");
    const auto startTime = std::chrono::steady_clock::now();

    std::signal(SIGINT, stopMonitor);
    std::signal(SIGTERM, stopMonitor);

    float featuresBuffer[FRAME_SIZE]{};
    std::size_t bufferIndex = 0;
    auto nextSample = std::chrono::steady_clock::now();
    auto trackingWindowStart = nextSample;
    int totalInferencesInWindow = 0;
    int anomalyCountInWindow = 0;
    SensorSimulator sensor(eventMode);

    std::cout << "Aftershock monitor started at " << FREQUENCY_HZ
              << " Hz. Press Ctrl-C to stop.\n";
    if (eventMode) {
        std::cout << "Event simulation enabled.\n";
    }

    while (running != 0) {
        const auto now = std::chrono::steady_clock::now();
        if (now >= nextSample) {
            nextSample += std::chrono::milliseconds(INTERVAL_MS);
            const Acceleration acceleration = sensor.read();

            if (bufferIndex + AXES <= FRAME_SIZE) {
                featuresBuffer[bufferIndex++] = acceleration.x;
                featuresBuffer[bufferIndex++] = acceleration.y;
                featuresBuffer[bufferIndex++] = acceleration.z;
            }

            if (bufferIndex == FRAME_SIZE) {
                const float anomalyScore = runInference(featuresBuffer, FRAME_SIZE);
                ++totalInferencesInWindow;
                if (anomalyScore > ANOMALY_THRESHOLD) {
                    ++anomalyCountInWindow;
                    std::cout << "Anomaly detected. Score: " << anomalyScore << '\n';
                }

                constexpr std::size_t shiftAmount = AXES;
                std::memmove(featuresBuffer, featuresBuffer + shiftAmount,
                             (FRAME_SIZE - shiftAmount) * sizeof(float));
                bufferIndex = FRAME_SIZE - shiftAmount;
            }
        } else {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }

        const auto windowNow = std::chrono::steady_clock::now();
        if (windowNow - trackingWindowStart >= TRACKING_WINDOW) {
            if (totalInferencesInWindow > 0) {
                const int anomalyPercentage =
                    (anomalyCountInWindow * 100) / totalInferencesInWindow;
                std::cout << "Window report: anomaly density " << anomalyPercentage << "%\n";
                if (anomalyPercentage >= REQUIRED_ANOMALY_PERCENT) {
                    printAlert(anomalyPercentage);
                }
            }
            trackingWindowStart = windowNow;
            totalInferencesInWindow = 0;
            anomalyCountInWindow = 0;
        }

        if (durationSeconds > 0 &&
            windowNow - startTime >= std::chrono::seconds(durationSeconds)) {
            running = 0;
        }
    }

    std::cout << "Aftershock monitor stopped.\n";
    return 0;
}
