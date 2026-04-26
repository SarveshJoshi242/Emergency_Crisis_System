# 🔥 InfernoGuard — AI Fire Risk Prediction System

> **Real-time fire hazard detection using Computer Vision + Rule-based AI**  
> Built for hackathon demonstration · Python · YOLOv8 · FastAPI · OpenCV

---

## 🧠 How It Works

```
Webcam / Video
      │
      ▼
 [detector.py]  ──── YOLOv8s ──────► people_count
                ──── InfernoGuard ──► fire_conf, has_fire, has_smoke
      │
 [movement.py]  ──── Frame Diff ───► movement_score  (0–1)
      │
  [density.py]  ──── people / 50 ──► density_label  (LOW/MEDIUM/HIGH)
      │
[risk_engine.py] ─── Rule Engine ──► CRITICAL / HIGH / MEDIUM / LOW
      │
 [pipeline.py]  ──── Log + Display
 [api.py]       ──── REST API
```

---

## ⚡ Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2a. Run full system (webcam + API)
python main.py

# 2b. Run with real fire model (InfernoGuard)
$env:FIRE_MODEL_PATH='infernoguard_best.pt'; python main.py   # PowerShell
set FIRE_MODEL_PATH=infernoguard_best.pt && python main.py    # CMD

# 2c. Simulate fire at 80% confidence
python main.py --fire-sim 0.8

# 3. Offline demo (no camera needed)
python demo.py

# 4. API only
python main.py --api-only
```

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/predict` | Evaluate risk from signals |
| `GET` | `/test/no_people` | Demo: LOW |
| `GET` | `/test/crowd_no_fire` | Demo: LOW |
| `GET` | `/test/fire_crowd` | Demo: HIGH |
| `GET` | `/test/critical` | Demo: CRITICAL |

**Swagger UI:** http://localhost:8000/docs

**Example request:**
```json
POST /predict
{ "people_count": 40, "fire_conf": 0.85, "movement_score": 0.75 }

→ { "risk": "CRITICAL", "score": 81.5, "action": "EVACUATE" }
```

---

## 🧪 Risk Rules

| Level | Condition | Action |
|---|---|---|
| 🔴 **CRITICAL** | fire > 0.7 AND density == HIGH AND movement > 0.6 | EVACUATE |
| 🟠 **HIGH** | fire > 0.6 AND density ∈ {MEDIUM, HIGH} | ALERT |
| 🟡 **MEDIUM** | fire > 0.5 OR movement > 0.6 | NOTIFY_STAFF |
| 🟢 **LOW** | None of the above | MONITOR |

**Score formula:** `(fire × 50) + (density × 30) + (movement × 20)`

---

## 📁 Project Structure

```
fire_risk/
├── main.py              ← Entry point
├── pipeline.py          ← Real-time webcam loop
├── detector.py          ← YOLO person + fire/smoke detection
├── movement.py          ← Frame differencing movement score
├── density.py           ← Crowd density calculator
├── risk_engine.py       ← Rule-based risk evaluator
├── api.py               ← FastAPI REST endpoint
├── demo.py              ← Offline demo (no camera needed)
├── requirements.txt     ← Dependencies
├── yolov8s.pt           ← Person detection model (COCO)
└── infernoguard_best.pt ← Fire/smoke model (mAP 77.3%)
```

---

## 🔥 Fire Model — InfernoGuard

| Metric | Value |
|---|---|
| Architecture | YOLOv8 Nano |
| Dataset | D-Fire (21,527 images) |
| Overall mAP50 | 77.3% |
| Smoke mAP50 | 82.9% |
| Fire mAP50 | 71.7% |
| Classes | smoke (0), fire (1) |

---

## 📌 Tech Stack

`Python 3.9` · `Ultralytics YOLOv8` · `OpenCV` · `FastAPI` · `Uvicorn` · `NumPy` · `Pydantic`
