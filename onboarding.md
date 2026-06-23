# Onboarding — Meridian Sentinel

Welcome to the **Meridian Sentinel** project team! We are building a Real-Time Threat Detection & Mitigation prototype combining Elastic SIEM and an LSTM anomaly detection engine.

This file provides a quick map to help you get up to speed with the project.

## 1. Start Here
- Read the **[README.md](README.md)** for a high-level project overview and instructions to spin up the local environment using Docker Compose.

## 2. Project Documentation (`/docs`)
All major project documentation has been organized into the `docs/` directory:

- **[Architecture](docs/architecture.md):** Detailed breakdown of the hybrid system (LSTM + SIEM), data pipeline, and infrastructure choices.
- **[Development Guide](docs/development-guide-2weeks.md):** The step-by-step 14-day execution checklist. Use this to track granular tasks.
- **[Implementation Plan](docs/implementation-plan.md):** Contains the official User Stories (US-01 through 10) and acceptance criteria logic.
- **[Project Board](docs/PROJECT_BOARD.md):** The simulated Kanban board to track task status.

## 3. Local Development
We are actively building inside the `feature/data-pipeline` branch currently.
To get started:
1. Copy `.env.example` to `.env`.
2. Review the folder structure (e.g., `/src`, `/tests`, `/data`).
3. Make sure to download the PaySim dataset into `/data/` as per the development guide for Day 1.

## 4. AI & Assistant Context
If you are developing with an AI assistant (e.g., GitHub Copilot or Claude), please ensure it is initialized using the contexts provided in:
- **[Agent Configuration](docs/agent.md)**
- **[Claude Interaction Guide](docs/claude.md)**

Happy coding!
