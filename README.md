# 🚨 Rapid Crisis Response System (Hospitality AI)

> **An AI-powered, centralized emergency management platform for the hospitality industry — built for speed, reliability, and lives.**

---

## 🧩 Problem Statement

Hotels and resorts rely on fragmented, siloed systems to handle emergencies — walkie-talkies for staff, paper evacuation plans, manual fire alarms, and disconnected guest communication channels. In a crisis, every second counts. The lack of a unified, intelligent response platform leads to:

- Delayed emergency notifications to guests and staff
- No real-time situational awareness across floors
- Inability to dynamically route evacuation paths around hazards
- No AI triage of incoming distress signals
- Zero audit trail for incident reporting

---

## 💡 Solution Overview

**Rapid Crisis Response System** is a full-stack, AI-augmented emergency management platform that unifies guest distress signals, staff response workflows, fire detection, and dynamic evacuation routing into a single cohesive system.

Key capabilities:
- **Guests** can raise emergency alerts, request help, and receive real-time broadcast messages via WebSocket
- **Staff** monitor a live dashboard, triage AI-analyzed incidents, manage floor plans, and coordinate evacuations
- **InfernoGuard** (YOLOv8) detects fire/smoke in real-time from video feeds and auto-triggers evacuation protocols
- **AI (Gemini 1.5 Pro)** analyzes uploaded incident images and generates actionable triage recommendations
- **Dynamic pathfinding** (Dijkstra's algorithm) computes optimal evacuation routes around blocked exits

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GUEST SIDE                                   │
│                                                                       │
│   ┌──────────────────────┐        ┌───────────────────────────────┐  │
│   │  React Frontend       │◄──────►│  Guest Backend (FastAPI :8000)│  │
│   │  (Vite + TailwindCSS) │  JWT   │  • Auth (Register/Login)      │  │
│   │  • Login / Register   │        │  • Help Requests              │  │
│   │  • Guest Dashboard    │        │  • Real-time Broadcasts (WS)  │  │
│   │  • Evacuation Map     │        │  • Pathfinding (Dijkstra)     │  │
│   └──────────────────────┘        └──────────────┬────────────────┘  │
│                                                   │                   │
└───────────────────────────────────────────────────┼───────────────────┘
                                                    │ Shared MongoDB
                                    ┌───────────────▼────────────────┐
                                    │       MongoDB Atlas              │
                                    │  • guests           • alerts    │
                                    │  • help_requests    • staff     │
                                    │  • floor_plans      • incidents │
                                    └───────────────┬────────────────┘
                                                    │
┌───────────────────────────────────────────────────┼───────────────────┐
│                         STAFF SIDE                │                   │
│                                                   │                   │
│   ┌──────────────────────┐        ┌──────────────▼────────────────┐  │
│   │  Staff Dashboard      │◄──────►│  Staff Backend (FastAPI :8001)│  │
│   │  (React / Vite)       │  JWT   │  • Auth (Staff Login)         │  │
│   │  • Live Alerts Feed   │        │  • Emergency Management       │  │
│   │  • Floor Plan Editor  │        │  • AI Triage (Gemini)         │  │
│   │  • Incident Triage    │        │  • Broadcast Messaging        │  │
│   │  • Broadcast Console  │        │  • Floor Plan CRUD            │  │
│   └──────────────────────┘        └──────────────┬────────────────┘  │
│                                                   │                   │
└───────────────────────────────────────────────────┼───────────────────┘
                                                    │
                                    ┌───────────────▼────────────────┐
                                    │    InfernoGuard (YOLOv8)        │
                                    │  Fire / Smoke Detection          │
                                    │  • Medium risk → Staff confirm  │
                                    │  • High risk   → Auto-evacuate  │
                                    └────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Layer            | Technology                          |
|------------------|-------------------------------------|
| **Frontend**     | React 19, Vite, TailwindCSS         |
| **Guest API**    | FastAPI, Uvicorn, Python 3.11+      |
| **Staff API**    | FastAPI, Uvicorn, Python 3.11+      |
| **Database**     | MongoDB Atlas (Motor async driver)  |
| **Auth**         | JWT (PyJWT + bcrypt)                |
| **AI / Vision**  | Gemini 1.5 Pro, YOLOv8 (Ultralytics)|
| **Pathfinding**  | Dijkstra's algorithm (custom impl)  |
| **Real-time**    | WebSockets (FastAPI native)         |
| **Deployment**   | Render (backend), Vercel (frontend) |

---

## 📁 Project Structure

```
Emergency_Crisis_System/
│
├── guest_backend/              # FastAPI backend — guest-facing APIs
│   ├── app/
│   │   ├── routers/            # auth, alerts, help_requests, pathfinding, ws
│   │   ├── models/             # Pydantic schemas
│   │   └── services/           # business logic
│   ├── requirements.txt
│   ├── run.py                  # entry point
│   └── .env.example
│
├── staff backend/              # FastAPI backend — staff/admin APIs
│   ├── routers/                # auth, emergencies, floor_plans, broadcasts, AI
│   ├── models/                 # Pydantic schemas
│   ├── services/               # AI triage, YOLO bridge
│   ├── utils/
│   ├── requirements.txt
│   ├── main.py                 # entry point
│   └── .env.example
│
├── sign in_up_frontend/        # React + Vite frontend (guests + staff)
│   ├── src/
│   │   ├── views/              # GuestDashboard, StaffDashboard, Landing, etc.
│   │   ├── api/                # Axios API clients
│   │   └── components/
│   ├── package.json
│   └── vite.config.js
│
├── fire_risk/                  # InfernoGuard — YOLOv8 fire detection pipeline
│   ├── infernoguard/
│   └── run_all_tests.py
│
├── render.yaml                 # Render deployment config
├── start_all.ps1               # Windows: start all services at once
└── README.md
```

---

## ⚙️ Local Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB Atlas account (or local MongoDB)
- Git

---

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/rapid-crisis-response.git
cd rapid-crisis-response/Emergency_Crisis_System
```

---

### 2. Setup Guest Backend (Port 8000)

```bash
cd guest_backend

# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and fill in your MONGODB_URI, JWT_SECRET, etc.

# Run the server
python run.py
# API available at: http://localhost:8000
# Docs at:         http://localhost:8000/docs
```

---

### 3. Setup Staff Backend (Port 8001)

```bash
cd ../staff\ backend

# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and fill in your MONGODB_URI, JWT_SECRET, GEMINI_API_KEY, etc.

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
# API available at: http://localhost:8001
# Docs at:         http://localhost:8001/docs
```

---

### 4. Setup Frontend

```bash
cd "../sign in_up_frontend"

# Install dependencies
npm install

# Configure environment
cp .env.example .env.local
# Edit .env.local to point to your local backends

# Run development server
npm run dev
# Available at: http://localhost:5173
```

---

### 5. (Optional) Run Everything at Once (Windows)

```powershell
# From the Emergency_Crisis_System directory
.\start_all.ps1
```

---

## 🔐 Environment Variables

Both backends require a `.env` file. Copy the respective `.env.example` and fill in your values.

### Guest Backend (`guest_backend/.env.example`)
See [`guest_backend/.env.example`](./guest_backend/.env.example)

### Staff Backend (`staff backend/.env.example`)
See [`staff backend/.env.example`](./staff%20backend/.env.example)

> ⚠️ **Never commit `.env` files.** They are excluded via `.gitignore`.

---

## 🚀 Deployment (Render)

The project includes a [`render.yaml`](./render.yaml) for one-click deployment.

### Manual Deployment Steps

#### Staff Backend on Render
1. Create a new **Web Service** on [render.com](https://render.com)
2. Connect your GitHub repository
3. Set **Root Directory** to `staff backend`
4. **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
5. **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add all environment variables from `.env.example` in the Render dashboard
7. Set `PYTHONPATH` = `/opt/render/project/src`

#### Guest Backend on Render
1. Create another **Web Service**
2. Set **Root Directory** to `guest_backend`
3. **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
4. **Start Command**: `python run.py`
5. Add all environment variables from `.env.example`
6. Update `STAFF_BACKEND_URL` to point to your deployed staff backend URL

#### Frontend on Vercel / Render
1. Connect your repository
2. Set **Root Directory** to `sign in_up_frontend`
3. **Build Command**: `npm run build`
4. **Output Directory**: `dist`
5. Set `VITE_GUEST_API_URL` and `VITE_STAFF_API_URL` to your deployed backend URLs

---

## ✨ Features

### Guest-Facing
- [x] Secure registration and login (JWT)
- [x] Real-time emergency broadcast reception (WebSocket)
- [x] One-tap SOS / help request submission
- [x] Dynamic evacuation route display (Dijkstra pathfinding)
- [x] Polling fallback if WebSocket is unavailable
- [x] SMS alert integration

### Staff-Facing
- [x] Secure staff authentication
- [x] Live emergency alert feed with status management
- [x] AI-powered incident image analysis (Gemini 1.5 Pro)
- [x] Interactive floor plan editor (node/edge graph)
- [x] Broadcast messaging to all guests
- [x] YOLO fire detection integration with auto-evacuation trigger
- [x] Help request triage and assignment

### InfernoGuard (Fire Detection)
- [x] YOLOv8-based real-time fire/smoke detection
- [x] Sliding window buffer for false-positive reduction
- [x] Medium risk: manual staff confirmation required
- [x] High risk: automatic evacuation trigger
- [x] Cooldown system to prevent alert flooding

---

## 🎬 Demo

> 🔗 **Live Demo**: _[Link to be added after deployment]_

> 📹 **Demo Video**: [`MKBAAG.mp4`](./MKBAAG.mp4)

---

## 👥 Team

| Name | Role |
|------|------|
| _(Team Member 1)_ | Backend Lead |
| _(Team Member 2)_ | Frontend Developer |
| _(Team Member 3)_ | AI / ML Engineer |
| _(Team Member 4)_ | DevOps / Deployment |

---

## 🔮 Future Improvements

- [ ] Multi-hotel / multi-property support with tenant isolation
- [ ] Mobile app (React Native) for guests and staff
- [ ] Integration with physical IoT fire sensors and door lock systems
- [ ] Predictive risk scoring based on historical incident data
- [ ] Multi-language support for international guests
- [ ] Automated post-incident PDF reporting
- [ ] Push notification support (FCM)
- [ ] Integration with hotel PMS (Property Management System)

---

## 📄 License

This project was built for a hackathon. All rights reserved by the team.

---

<div align="center">
  <sub>Built with ❤️ for safer hospitality experiences</sub>
</div>
