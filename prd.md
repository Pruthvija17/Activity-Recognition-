# BAS Activity Intelligence

## Product Requirements Document

**Project:** AI Human Activity Recognition for On-Board BAS Experiments
**SIH Problem Statement:** SIH26174
**Product:** BAS Activity Intelligence
**Version:** 1.0
**Status:** SIH Prototype Specification

---

# 1. Product Overview

BAS Activity Intelligence is an AI-powered video analysis and experiment-monitoring platform designed for **On-Board BAS (Biological/Basic Activity System) experiments and simulated spacecraft environments**.

The system analyzes video from a fixed RGB camera and automatically recognizes predefined human activities, tracks one or more people, detects unexpected activities, generates timestamped activity events, monitors expected experiment workflows, and produces structured experiment records.

The platform supports both:

1. **Recorded Video Analysis**
2. **Real-Time Camera Monitoring**

The product transforms raw experiment video into structured, searchable and reviewable experimental evidence.

### Product tagline

> **Observe. Understand. Record.**

---

# 2. Problem Statement

Experiment operators and researchers currently need to manually review experiment videos to determine:

* what activities occurred
* when each activity started
* when it ended
* how long it lasted
* who performed the activity
* whether unexpected actions occurred
* whether the expected experimental sequence was followed

Manual video review is time-consuming, difficult to scale and prone to human oversight.

The proposed system automates this process using computer vision, human pose understanding, temporal activity recognition and experiment intelligence.

---

# 3. Product Vision

Build an AI assistant for BAS experiments that continuously observes experiment video and converts it into a structured experimental record.

The system should answer:

> **Who did what, when did they do it, how long did they do it, how confident is the AI, and did the observed activity sequence match the expected experiment workflow?**

---

# 4. Target Users

## Primary Users

### Experiment Operators

Need real-time monitoring, alerts and quick review of unusual events.

### Researchers

Need structured activity logs, analytics and experiment comparisons.

### Mission / Experiment Supervisors

Need high-level experiment status, workflow deviations and reports.

### AI / Computer Vision Engineers

Need model performance, confidence, review data and evaluation metrics.

---

# 5. Core Activity Classes

The prototype must recognize these seven predefined activities:

| ID     | Activity                        |
| ------ | ------------------------------- |
| ACT-01 | Standing                        |
| ACT-02 | Sitting                         |
| ACT-03 | Walking                         |
| ACT-04 | Reaching                        |
| ACT-05 | Picking Up an Object            |
| ACT-06 | Placing an Object               |
| ACT-07 | Handling Experimental Equipment |

Any action that does not confidently belong to these categories should be eligible for **Unknown / Unexpected Activity** detection.

---

# 6. Core Product Capabilities

The prototype must provide:

1. Recorded video analysis
2. Real-time camera analysis
3. Person detection
4. Multi-person tracking
5. Seven-class activity recognition
6. Temporal activity recognition
7. Unknown / unexpected activity detection
8. Activity start/end timestamps
9. Activity duration
10. Confidence score
11. Person-specific activity timelines
12. Experiment workflow monitoring
13. Workflow deviation detection
14. Human-in-the-loop review
15. Searchable activity events
16. Video jump-to-event
17. Experiment analytics
18. Automatic experiment reports
19. CSV/JSON/PDF export

---

# 7. Input Modes

## 7.1 Uploaded Video

User can upload an experiment video.

Supported examples:

* MP4
* AVI
* MOV
* WebM

Flow:

```text
Upload Video
      ↓
Video Validation
      ↓
AI Processing
      ↓
Person Detection + Tracking
      ↓
Activity Recognition
      ↓
Unknown Detection
      ↓
Event Segmentation
      ↓
Workflow Analysis
      ↓
Results Dashboard
```

The user must see processing progress.

---

# 7.2 Real-Time Camera

The system must support real-time monitoring from a connected RGB camera.

Flow:

```text
Camera
   ↓
Video Stream
   ↓
Frame Processing
   ↓
Person Detection
   ↓
Multi-Person Tracking
   ↓
Activity Recognition
   ↓
Unknown Detection
   ↓
Live Dashboard
```

The dashboard must display:

* live video
* person IDs
* current activity
* confidence
* activity duration
* alerts
* live event timeline

---

# 8. Multi-Person Tracking

The system must support multiple people appearing in the camera view.

Each detected person receives a persistent temporary identifier:

```text
Person 01
Person 02
Person 03
```

The system must associate activities with the correct person.

Example:

```text
Person 01 → Walking → Reaching → Picking
Person 02 → Standing → Walking → Handling Equipment
```

Every activity event must contain:

* person ID
* activity
* start timestamp
* end timestamp
* duration
* confidence

### Tracking requirements

The system should:

* maintain identity across consecutive frames
* handle short occlusions where possible
* prevent activity events from being incorrectly assigned to another person
* recover tracking after temporary disappearance where possible

Recommended technologies:

* YOLO / RT-DETR for detection
* ByteTrack / BoT-SORT for tracking

---

# 9. Activity Recognition

Activity recognition must use temporal information.

Single-frame classification is insufficient for motion-based activities.

Recommended architecture:

```text
Video Frames
     ↓
Person Detection
     ↓
Tracking
     ↓
Pose / Spatial Features
     ↓
Temporal Window
     ↓
Activity Model
     ↓
7 Activity Classes
```

Potential temporal models:

* LSTM
* GRU
* Temporal CNN / TCN
* Lightweight Transformer

The final implementation may choose the most suitable model based on accuracy and inference speed.

---

# 10. Activity Event Generation

The system should convert frame-level predictions into meaningful events.

Example:

```text
Frames:
Walking
Walking
Walking
Walking
Reaching
Reaching
Reaching
```

Output:

```text
Walking
Start: 00:01:12
End:   00:01:18
Duration: 6 sec

Reaching
Start: 00:01:18
End:   00:01:22
Duration: 4 sec
```

The system should use temporal smoothing, hysteresis and minimum-duration/debounce logic to avoid excessive event fragmentation.

---

# 11. Unknown / Unexpected Activity Detection

Unknown detection is a core feature.

The system must not force every frame into one of the seven predefined classes.

If the observed behavior does not sufficiently match known classes, the system should produce:

> **UNKNOWN / UNEXPECTED ACTIVITY**

Example:

```text
00:02:34 – 00:02:39
Person 01
UNKNOWN
Confidence: 0.41
Status: REVIEW REQUIRED
```

Unknown detection should use more than a simple classification threshold where possible.

Possible methods:

* confidence thresholding
* feature embedding distance
* class prototype similarity
* anomaly scoring
* open-set recognition techniques

The final implementation should document the selected method.

---

# 12. Human-in-the-Loop Review

Unknown or low-confidence events must enter a review queue.

Operator interface:

```text
UNKNOWN ACTIVITY

Person: 01
Time: 00:02:34 – 00:02:39
Confidence: 41%

[Watch Event]

Classify as:

[Standing]
[Sitting]
[Walking]
[Reaching]
[Picking]
[Placing]
[Handling Equipment]
[Keep Unknown]

[Confirm]
```

Corrections should be stored.

Future versions may use corrected events to improve the training dataset.

---

# 13. Searchable Video Review

Every generated event must be linked to its corresponding video timestamp.

The operator can:

* click an event
* jump to the relevant timestamp
* play a short event clip
* inspect the original video
* review AI confidence
* correct the prediction

Example:

```text
00:03:42  Picking Up Object  94%  [Review]
```

Clicking Review should jump to approximately `00:03:42`.

---

# 14. Experiment Workflow Intelligence

The system should support an expected experiment workflow.

Example:

```text
Walking
   ↓
Reaching
   ↓
Picking Up Object
   ↓
Handling Equipment
   ↓
Placing Object
```

The system compares:

### Expected

```text
Walk → Reach → Pick → Handle → Place
```

### Observed

```text
Walk → Reach → Unknown → Handle → Place
```

The system generates:

> **Workflow Deviation Detected**

and identifies the relevant timestamp.

The system must not automatically claim that an experiment has failed.

Use:

> **Observed sequence deviates from expected workflow — operator review required.**

---

# 15. Experiment Workflow Configuration

Operators should be able to configure expected sequences.

Example:

```text
Experiment: Equipment Transfer

Step 1: Walking
Step 2: Reaching
Step 3: Picking Up Object
Step 4: Handling Experimental Equipment
Step 5: Placing Object
```

Future versions may support:

* optional steps
* repeated steps
* allowed alternative activities
* maximum expected durations
* required zones

---

# 16. Experiment Analytics

After processing an experiment, the dashboard should display:

### Summary

* total experiment duration
* number of detected people
* total activities
* unknown events
* workflow deviations
* average confidence

### Activity Distribution

Example:

```text
Walking              24%
Standing             18%
Reaching             12%
Picking               8%
Placing               7%
Handling Equipment   31%
```

### Additional Metrics

* activity duration
* activity frequency
* transition frequency
* average confidence
* unknown-event frequency
* person-wise statistics
* workflow completion
* time spent in defined zones

---

# 17. Person-Specific Analytics

For multiple people:

```text
Person 01
Total Active Time: 12:42
Activities: 18
Unknown Events: 1

Person 02
Total Active Time: 09:31
Activities: 14
Unknown Events: 0
```

The operator can filter the dashboard by person.

---

# 18. Automatic Experiment Report

After an experiment, the system should generate a structured report.

Report contents:

### Experiment Information

* experiment ID
* session ID
* date/time
* video source
* duration

### Participants

* number of detected people
* person IDs

### Activity Log

* person ID
* activity
* start
* end
* duration
* confidence

### Exceptions

* unknown activities
* low-confidence events
* workflow deviations

### Analytics

* activity distribution
* activity durations
* transitions
* person-wise statistics

### Review Status

* reviewed events
* corrected events
* unresolved unknowns

Exports:

* PDF
* CSV
* JSON

---

# 19. Real-Time Alerts

During live monitoring, the system may display:

### Yellow

**Low Confidence Activity**

### Orange

**Unknown Activity**

### Red

**Workflow Deviation**

Alerts should be visible without overwhelming the operator.

---

# 20. Activity Timeline

The primary monitoring interface should contain a timeline.

Example:

```text
00:00 ─────────────────────────────── 05:00

Person 01
[Standing][Walking][Reaching][Picking][Handling][Placing]

Person 02
[Standing──────][Walking][Unknown ⚠]
```

Users should be able to click timeline events.

---

# 21. Dashboard

Main navigation:

```text
Dashboard
Live Monitor
Experiments
Activity Logs
Analytics
Review Queue
Reports
Settings
```

### Dashboard widgets

* current experiment
* live camera status
* people detected
* current activities
* confidence
* recent events
* unknown events
* workflow status
* alerts
* experiment progress

---

# 22. Experiment Management

Users should be able to:

* create experiment
* assign experiment ID
* upload video
* configure expected workflow
* configure zones
* start real-time monitoring
* review results
* generate report
* export results
* archive experiment

---

# 23. Zone Awareness

The system may support configurable zones.

Example:

```text
┌─────────────────────────────┐
│ Storage Zone | Work Zone    │
│                             │
│                             │
│ Movement Zone               │
└─────────────────────────────┘
```

Events may include:

```text
Person 01
Handling Equipment
Zone: Work Zone
Duration: 13.6 sec
```

Zone detection should be implemented after the core recognition pipeline is stable.

---

# 24. AI Architecture

Recommended architecture:

```text
                 ┌─────────────────────┐
                 │ RGB Camera / Video  │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ Video Preprocessing │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ Person Detection    │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ Multi-Person        │
                 │ Tracking            │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ Pose / Spatial      │
                 │ Feature Extraction  │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ Temporal Activity   │
                 │ Recognition         │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ Known / Unknown     │
                 │ Detection           │
                 └──────────┬──────────┘
                            ↓
                 ┌─────────────────────┐
                 │ Temporal Event      │
                 │ Segmentation        │
                 └──────────┬──────────┘
                            ↓
              ┌─────────────┴─────────────┐
              ↓                           ↓
     Workflow Intelligence        Activity Database
              ↓                           ↓
       Review / Alerts              Dashboard / Reports
```

---

# 25. Backend

Recommended:

* Python
* FastAPI
* OpenCV
* PyTorch
* PostgreSQL or SQLite for prototype
* WebSocket for live updates

---

# 26. Frontend

Recommended:

* React
* TypeScript
* Tailwind CSS
* Charting library
* Video player with timestamp controls
* WebSocket client

A lightweight alternative such as Streamlit may be used for early prototyping, but the final SIH demonstration should preferably use a polished web interface.

---

# 27. Data Model

Every activity event should contain:

```json
{
  "event_id": "evt_001",
  "experiment_id": "EXP_001",
  "person_id": "person_01",
  "activity": "handling_equipment",
  "start_time": "00:02:14.2",
  "end_time": "00:02:27.8",
  "duration": 13.6,
  "confidence": 0.94,
  "status": "confirmed",
  "zone": "work_zone"
}
```

Unknown example:

```json
{
  "event_id": "evt_002",
  "experiment_id": "EXP_001",
  "person_id": "person_01",
  "activity": "unknown",
  "start_time": "00:02:34.1",
  "end_time": "00:02:39.0",
  "duration": 4.9,
  "confidence": 0.41,
  "status": "review_required"
}
```

---

# 28. Dataset Requirements

Training and evaluation data should include:

* all seven activities
* multiple people where possible
* different body orientations
* different movement speeds
* partial occlusions
* realistic BAS environment
* different lighting conditions
* object interactions
* ambiguous activities
* examples of unknown activities

Dataset splits must be performed by subject/session/video rather than randomly splitting adjacent frames to avoid data leakage.

Recommended:

```text
Dataset
├── train
├── validation
└── test
```

---

# 29. Evaluation Metrics

The system must report:

### Classification

* accuracy
* precision
* recall
* F1 score
* confusion matrix

### Unknown Detection

* unknown precision
* unknown recall
* false unknown rate
* false known rate

### Temporal Performance

* start timestamp error
* end timestamp error
* duration error

### Tracking

* ID consistency
* ID switches
* tracking accuracy

### Runtime

* FPS
* inference latency
* processing time
* CPU/GPU utilization

---

# 30. Performance Targets

Initial prototype targets:

* near-real-time processing where hardware permits
* stable person tracking
* usable activity segmentation
* low-latency dashboard updates
* no fabricated AI outputs

The system should clearly communicate if hardware/model limitations prevent real-time performance.

---

# 31. No-Mock-AI Requirement

This is a mandatory product requirement.

> **All activity recognition shown in the production/demo dashboard must originate from an actual video-processing pipeline.**

Do not use:

* hardcoded activity results
* random confidence scores
* fake timelines
* simulated AI predictions
* predetermined demo events presented as real inference

If the trained model is unavailable:

> **Model Not Connected / Demo Mode**

must be displayed rather than fabricated AI results.

---

# 32. MVP

The SIH prototype MVP must include:

### AI

* person detection
* multi-person tracking
* seven activity classes
* temporal recognition
* unknown detection
* confidence estimation
* event segmentation

### Product

* upload video
* real-time camera
* live activity dashboard
* activity timeline
* event table
* video review
* human correction
* workflow deviation detection
* experiment analytics
* automatic report
* CSV/JSON/PDF export

---

# 33. Future Enhancements

Potential future capabilities:

* equipment-specific object recognition
* improved open-set recognition
* edge-device deployment
* multi-camera fusion
* 3D pose estimation
* advanced anomaly detection
* experiment-to-experiment comparison
* active learning
* automated model retraining
* voice-based operator assistant

These should not compromise the core MVP.

---

# 34. Success Criteria

The prototype is considered successful when it can:

1. Accept a BAS experiment video.
2. Detect one or more people.
3. Track people across the video.
4. Recognize the seven required activities.
5. Generate activity start/end timestamps.
6. Calculate activity durations.
7. Produce confidence scores.
8. Detect activities outside the known classes.
9. Flag unknown events for review.
10. Allow operators to inspect the corresponding video.
11. Allow operators to correct AI predictions.
12. Compare observed activity sequences with an expected workflow.
13. Identify workflow deviations.
14. Produce an experiment activity log.
15. Generate a structured experiment report.
16. Process a live camera stream.
17. Maintain separate activity histories for multiple people.

---

# 35. Product Positioning

BAS Activity Intelligence is not simply a human-action classifier.

It is:

> **An AI-powered experiment observation, activity intelligence and automated logging system for BAS environments.**

The core value proposition is:

> **Turn experiment video into structured, timestamped and reviewable experimental evidence.**

---

# 36. Final Product Flow

```text
                 BAS CAMERA / VIDEO
                         ↓
                PERSON DETECTION
                         ↓
                MULTI-PERSON TRACKING
                         ↓
                 POSE / FEATURES
                         ↓
              TEMPORAL AI RECOGNITION
                         ↓
             ┌───────────┴───────────┐
             ↓                       ↓
        KNOWN ACTIVITY          UNKNOWN ACTIVITY
             ↓                       ↓
       EVENT SEGMENTATION       REVIEW QUEUE
             ↓                       ↓
             └───────────┬───────────┘
                         ↓
                WORKFLOW ANALYSIS
                         ↓
              DEVIATION DETECTION
                         ↓
             EXPERIMENT ACTIVITY LOG
                         ↓
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
      DASHBOARD       ANALYTICS       REPORT
```

---

# 37. One-Line Pitch

> **BAS Activity Intelligence uses AI-powered computer vision to monitor BAS experiments, recognize human activities, track multiple people, detect unexpected behavior, verify experimental workflows, and automatically generate timestamped experiment records.**
