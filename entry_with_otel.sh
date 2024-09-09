#!/bin/bash
opentelemetry-instrument --logs_exporter otlp --service_name "usfm-scanner" python listener.py 