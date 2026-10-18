/*
 * Debian/Linux standalone aftershock monitor.
 *
 * Build:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic ml.cpp -lcurl -o aftershock_ml
 *
 * The sensor and model hooks below are self-contained and use the Linux I2C
 * interface, so the program can run on a Debian UNO Q without Arduino headers.
 */

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <csignal>
#include <curl/curl.h>
#include <cstring>
#include <cerrno>
#include <cstdlib>
#include <fcntl.h>
#include <iostream>
#include <linux/i2c-dev.h>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <unistd.h>
#include <sys/ioctl.h>

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

class Mpu6050 {
public:
    Mpu6050(int bus, int address) {
        const std::string device = "/dev/i2c-" + std::to_string(bus);
        fileDescriptor_ = open(device.c_str(), O_RDWR);
        if (fileDescriptor_ < 0) {
            throw std::runtime_error("Cannot open " + device + ": " + std::strerror(errno));
        }
        if (ioctl(fileDescriptor_, I2C_SLAVE, address) < 0) {
            close(fileDescriptor_);
            throw std::runtime_error("Cannot select MPU6050 at I2C address " +
                                     std::to_string(address) + ": " +
                                     std::strerror(errno));
        }

        writeRegister(0x6B, 0x00);  // PWR_MGMT_1: wake the device.
        writeRegister(0x1A, 0x03);  // CONFIG: digital low-pass filter.
        writeRegister(0x19, 0x13);  // SMPLRT_DIV: 1 kHz / (19 + 1) = 50 Hz.
        writeRegister(0x1C, 0x00);  // ACCEL_CONFIG: +/- 2 g, 16384 LSB/g.
    }

    ~Mpu6050() {
        if (fileDescriptor_ >= 0) {
            close(fileDescriptor_);
        }
    }

    Mpu6050(const Mpu6050&) = delete;
    Mpu6050& operator=(const Mpu6050&) = delete;

    Acceleration read() const {
        unsigned char startRegister = 0x3B;
        unsigned char bytes[6]{};
        if (write(fileDescriptor_, &startRegister, 1) != 1 ||
            ::read(fileDescriptor_, bytes, sizeof(bytes)) !=
                static_cast<ssize_t>(sizeof(bytes))) {
            throw std::runtime_error("Failed to read MPU6050 acceleration: " +
                                     std::string(std::strerror(errno)));
        }

        const auto rawValue = [&bytes](std::size_t offset) {
            return static_cast<int16_t>(
                (static_cast<uint16_t>(bytes[offset]) << 8) | bytes[offset + 1]);
        };
        constexpr float metersPerSecondSquaredPerLsb = 9.80665F / 16384.0F;
        return {rawValue(0) * metersPerSecondSquaredPerLsb,
                rawValue(2) * metersPerSecondSquaredPerLsb,
                rawValue(4) * metersPerSecondSquaredPerLsb};
    }

private:
    void writeRegister(unsigned char reg, unsigned char value) {
        const unsigned char data[] = {reg, value};
        if (write(fileDescriptor_, data, sizeof(data)) !=
            static_cast<ssize_t>(sizeof(data))) {
            throw std::runtime_error("Failed to configure MPU6050: " +
                                     std::string(std::strerror(errno)));
        }
    }

    int fileDescriptor_ = -1;
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

void publishTelemetry(CURL* curl, const std::string& url, float acceleration) {
    const bool event = acceleration >= 1.5F;
    const std::string payload =
        "{\"acceleration\":" + std::to_string(acceleration) +
        ",\"threshold\":1.5,\"event\":" + (event ? "true" : "false") + "}";
    struct curl_slist* headers = curl_slist_append(nullptr, "Content-Type: application/json");
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload.c_str());
    curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, 1000L);
    const CURLcode result = curl_easy_perform(curl);
    curl_slist_free_all(headers);
    if (result != CURLE_OK) {
        std::cerr << "Telemetry publish failed: " << curl_easy_strerror(result) << '\n';
    }
}

void printAlert(int density) {
    std::cout << "ALERT: Sustained aftershock / seismic event confirmed "
              << "(density: " << density << "%)\n";
}

int parseIntegerEnvironment(const char* name, int fallback) {
    const char* value = std::getenv(name);
    if (value == nullptr) {
        return fallback;
    }
    return std::strtol(value, nullptr, 0);
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

}  // namespace

int main(int argc, char* argv[]) {
    const int durationSeconds = parseDuration(argc, argv);
    const auto startTime = std::chrono::steady_clock::now();

    std::signal(SIGINT, stopMonitor);
    std::signal(SIGTERM, stopMonitor);

    float featuresBuffer[FRAME_SIZE]{};
    std::size_t bufferIndex = 0;
    auto nextSample = std::chrono::steady_clock::now();
    auto trackingWindowStart = nextSample;
    int totalInferencesInWindow = 0;
    int anomalyCountInWindow = 0;
    const int i2cBus = parseIntegerEnvironment("MPU6050_I2C_BUS", 1);
    const int firstAddress = parseIntegerEnvironment("MPU6050_I2C_ADDRESS_1", 0x68);
    const int secondAddress = parseIntegerEnvironment("MPU6050_I2C_ADDRESS_2", 0x69);
    Mpu6050 firstSensor(i2cBus, firstAddress);
    Mpu6050 secondSensor(i2cBus, secondAddress);
    const std::string dashboardUrl =
        std::getenv("AFTERSHOCK_TELEMETRY_URL") != nullptr
            ? std::getenv("AFTERSHOCK_TELEMETRY_URL")
            : "http://127.0.0.1:5000/api/telemetry";
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        throw std::runtime_error("Failed to initialize libcurl");
    }
    CURL* curl = curl_easy_init();
    if (curl == nullptr) {
        curl_global_cleanup();
        throw std::runtime_error("Failed to initialize telemetry client");
    }

    std::cout << "Aftershock monitor started at " << FREQUENCY_HZ
              << " Hz. Press Ctrl-C to stop.\n";
    std::cout << "Reading MPU6050 sensors from /dev/i2c-" << i2cBus << " at 0x"
              << std::hex << firstAddress << " and 0x" << secondAddress << std::dec << ".\n";

    while (running != 0) {
        const auto now = std::chrono::steady_clock::now();
        if (now >= nextSample) {
            nextSample += std::chrono::milliseconds(INTERVAL_MS);
            const Acceleration first = firstSensor.read();
            const Acceleration second = secondSensor.read();
            const float firstMagnitude = std::sqrt(first.x * first.x + first.y * first.y +
                                                   first.z * first.z) / 9.80665F;
            const float secondMagnitude = std::sqrt(second.x * second.x + second.y * second.y +
                                                    second.z * second.z) / 9.80665F;
            const Acceleration acceleration =
                firstMagnitude >= secondMagnitude ? first : second;
            publishTelemetry(curl, dashboardUrl,
                             std::max(firstMagnitude, secondMagnitude));

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

    curl_easy_cleanup(curl);
    curl_global_cleanup();
    std::cout << "Aftershock monitor stopped.\n";
    return 0;
}
