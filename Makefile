CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -pedantic
TARGET := aftershock_ml
SOURCE := ml.cpp

.PHONY: all run event clean

all: $(TARGET)

$(TARGET): $(SOURCE)
	$(CXX) $(CXXFLAGS) $< -o $@

run: $(TARGET)
	./$(TARGET)

event: $(TARGET)
	./$(TARGET) --event --seconds 15

clean:
	$(RM) $(TARGET)
