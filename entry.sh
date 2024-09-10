#!/bin/bash
# if otel is set then run the entrypoint with opentelemetry otherwise just run it
if [ -n "$OTEL_EXPORTER_OLTP_ENDPOINT" ]; then
    echo "Running with OpenTelemetry"
    exec opentelemetry-instrument --logs_exporter otlp --service_name "usfm-scanner" python listener.py
    else
    echo "Running without OpenTelemetry"
    python listener.py
fi