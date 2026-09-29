# BAS Activity Intelligence - Implementation Plan

This document outlines the step-by-step implementation plan for building the BAS Activity Intelligence platform, adhering to the PRD (SIH26174) and Brand Design System.

## User Review Required

> [!IMPORTANT]
> Please review this plan to ensure the phased approach aligns with your priorities. Specifically, confirm if you would like to start with the **Frontend scaffolding** (Phase 1/2) to visualize the dashboard, or the **Backend/AI scaffolding** (Phase 3/4) to get the video processing pipeline running first.

## Open Questions

> [!WARNING]
> 1. Do you already have a preferred object detection/tracking model (e.g., YOLOv8 + ByteTrack) ready to be integrated, or should we build the system with placeholder AI modules (that still process video but use lightweight/dummy models) so you can replace them later with your trained models?
> 2. Should we prioritize the **Recorded Video Analysis** flow or the **Real-Time Camera Monitoring** flow for the initial MVP?

## Proposed Architecture and Phases

### Phase 1: Repository Foundation & Setup

**Frontend Setup (React + Vite + Tailwind)**
- Initialize a Vite React TypeScript project in a `frontend` folder.
- Configure Tailwind CSS with the official BAS AI brand colors (Sky Blue, Deep Blue, Ice Blue background, etc.).
- Add Inter and Manrope fonts to the project.
- Set up React Router for navigation (Dashboard, Live Monitor, Experiments, Review Queue, Analytics, Reports).
- Integrate `lucide-react` for clean, thin line icons.

**Backend Setup (Python + FastAPI)**
- Initialize a Python FastAPI project in a `backend` folder.
- Set up a virtual environment and `requirements.txt`.
- Configure a local SQLite (for MVP) database using SQLAlchemy.
- Set up WebSocket routing for live telemetry.

### Phase 2: Frontend Layout & Core UI System

- **Layout Structure:** Build the main application shell with a sidebar navigation and a top header showing system status (e.g., 🟢 AI Active).
- **Dashboard Widgets:** Create reusable white cards with subtle borders (`#E0F2FE`), soft shadows, and 12–16px border radii on an Ice Blue (`#EFF9FF`) background.
- **Activity Timeline Component:** Build the visual timeline to track activities for multiple participants over time.
- **Event Table:** Develop a data table with columns for Person, Activity, Start, End, Duration, Confidence, and Status.
- **Review Queue UI:** Build the human-in-the-loop review interface for handling "Unknown" or low-confidence activities.

### Phase 3: Backend Core API & Data Models

- **Database Schemas:**
  - `Experiment` (ID, name, expected_workflow, status)
  - `Participant` (ID, experiment_id, tracked_id)
  - `ActivityEvent` (ID, experiment_id, person_id, activity_type, start_time, end_time, confidence, status, zone)
- **REST Endpoints:** Create CRUD endpoints for uploading videos, retrieving experiment logs, and fetching analytics data.
- **Workflow Intelligence Engine:** Implement a utility to compare an observed sequence of activities against a pre-configured expected workflow to detect deviations.

### Phase 4: AI Pipeline Architecture (No Mock AI)

- **Video Processing Service:** Create a background worker (e.g., using Python multiprocessing) to process uploaded videos frame-by-frame.
- **Pipeline Stages (Modular Interfaces):**
  1. **Person Detection:** Detect bounding boxes around humans.
  2. **Multi-Person Tracking:** Assign persistent IDs to tracked people.
  3. **Temporal Activity Recognition:** Run an activity classifier on temporal windows to output 1 of 7 known activities or "Unknown".
  4. **Event Segmentation:** Apply debouncing and smoothing to group frame-level predictions into continuous events.
- **Live Stream Handling:** Implement frame grabbing from a live camera stream (via OpenCV) and stream processed metadata over WebSockets.

### Phase 5: Analytics & Reporting

- **Analytics Charts:** Integrate `recharts` to display activity distribution (pie charts), event frequency, and workflow progress in the dashboard.
- **Automatic Reports:** Implement an export function (JSON/CSV and UI print-to-PDF) summarizing an experiment's activity log and deviations.

## Verification Plan

### Automated Verification
- Unit tests for the Workflow Deviation Engine (ensuring expected vs. observed sequences are compared correctly).
- API endpoint testing (via FastAPI TestClient) for event ingestion and retrieval.

### Manual Verification
- Deploy the frontend locally and verify it strictly adheres to the "Light Blue + White + Deep Blue" NASA-inspired aesthetic from `brand.md`.
- Run a sample MP4 experiment video through the backend pipeline and verify that events are surfaced in the React frontend via WebSocket.
- Test the Human Review loop: confirm that reclassifying an "Unknown" event to "Reaching" updates the database and timeline UI correctly.
