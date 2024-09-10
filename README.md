# usfm-scanner



## Configuration

### Using local open telemetry

You should set the following environment variables:

- OTEL_EXPORTER_OTLP_ENDPOINT=http://server:4317
- OTEL_EXPORTER_OLTP_INSECURE=true
- OTEL_EXPORTER_OTLP_PROTOCOL=grpc

Granted this is for the gRPC exporter, refer to the [OpenTelemetry documentation](https://opentelemetry.io/docs/) for more information on using other transports

### Using Azure Monitor

In Progress