# Meridian Sentinel

Real-Time Threat Detection & Mitigation prototype combining Elastic SIEM and an LSTM anomaly detection engine for Meridian Financial Services.

## Overview
Meridian Sentinel is a hybrid cybersecurity threat detection prototype. It integrates:
- **Elastic SIEM:** Rule-based log ingestion, event correlation, and automated incident playbooks.
- **LSTM Anomaly Detection Engine:** A neural network that flags statistical deviations that rule-based systems cannot detect.

Compliance mapping includes APRA CPS 234, PCI DSS v4.0, and the Australian Privacy Act 1988.

## Getting Started
Please refer to the `docs/` directory for detailed documentation on architecture, compliance, and deployment runbooks.

1. Create a `.env` file based on `.env.example`.
2. Ensure you have Docker and Docker Compose installed.
3. Bring up the infrastructure: `docker-compose up -d`.
