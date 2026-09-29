# BAS Activity Intelligence – AI Model Weights Directory

This directory stores the trained neural network model weights for the **SIH26174 BAS Activity Recognition** pipeline.

## Required Model Weights

| Component | Expected Filename | Architecture | Format | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Person Detector** | `yolov8n.pt` or `person_detector.onnx` | YOLOv8 / YOLO-NAS / RT-DETR | PyTorch (`.pt`) or ONNX (`.onnx`) | Person localization & bounding box prediction |
| **Activity Classifier** | `activity_cnn.pt` or `activity_classifier.onnx` | Temporal CNN / TCN / Video-Transformer | PyTorch (`.pt`) or ONNX (`.onnx`) | 7-Class BAS activity recognition |

## 7 Core BAS Activity Classes

1. `Standing`
2. `Sitting`
3. `Walking`
4. `Reaching`
5. `Picking up an object`
6. `Placing an object`
7. `Handling experimental equipment`

*Detections below the confidence threshold (configured in `model_config.json`, default `0.60`) or with high entropy are flagged as `Unknown` for human-in-the-loop operator review.*

## Configuration

Settings including confidence thresholds, window sizes, and tracking parameters are configured in [`model_config.json`](./model_config.json).
