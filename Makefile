# Top-level experiment Makefile
# Targets:
#   make submit       - Submit 15-node experiment
#   make build        - Build all firmwares
#   make flash-mqtt   - Flash MQTT-SN firmware
#   make flash-coap   - Flash CoAP firmware
#   make run-mqtt     - Run MQTT-SN experiment + collect
#   make run-coap     - Run CoAP experiment + collect
#   make capture      - Wireshark capture (set NODE=a8-XX)
#   make analyze      - Parse CSVs + generate plots
#   make all-mqtt     - submit + build + flash-mqtt + run-mqtt
#   make all-coap     - flash-coap + run-coap (reuses same experiment)

SCRIPTS := scripts
NODE    ?= a8-18
DURATION ?= 120

.PHONY: submit build flash-mqtt flash-coap run-mqtt run-coap capture analyze all-mqtt all-coap

submit:
	bash $(SCRIPTS)/01_submit.sh $(DURATION)

build:
	bash $(SCRIPTS)/02_build.sh

flash-mqtt: build
	bash $(SCRIPTS)/03_flash.sh mqtt

flash-coap: build
	bash $(SCRIPTS)/03_flash.sh coap

run-mqtt:
	bash $(SCRIPTS)/04_run_mqtt.sh

run-coap:
	bash $(SCRIPTS)/04_run_coap.sh

capture:
	bash $(SCRIPTS)/05_wireshark_capture.sh $(NODE) 60

analyze:
	python3 analysis/parse_metrics.py

all-mqtt: submit build flash-mqtt run-mqtt

all-coap: flash-coap run-coap
