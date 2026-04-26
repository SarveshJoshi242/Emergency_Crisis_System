# Emergency Crisis System - Setup Guide for Team

## Repository Link
**GitHub:** https://github.com/SarveshJoshi242/Emergency_Crisis_System

---

## STEP 1: Clone the Repository

```bash
git clone https://github.com/SarveshJoshi242/Emergency_Crisis_System.git
cd Emergency_Crisis_System
```

---

## STEP 2: Set Up Environment Files

### For Python Backend Projects

Each backend directory has its own `.env.template` file. Copy it to `.env`:

#### Guest Backend
```bash
cd guest_backend
cp .env.template .env
# Edit .env with your configuration
```

#### Staff Backend
```bash
cd staff\ backend
# Create .env from template or use existing configuration
```

#### Auth Module
```bash
cd auth
# Configure authentication settings
```

---

## STEP 3: Install Dependencies

### Backend (Python)

#### Guest Backend
```bash
cd guest_backend
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### Staff Backend
```bash
cd staff\ backend
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### Fire Risk Module
```bash
cd fire_risk
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Frontend (Node.js)

#### Sign In/Up Frontend
```bash
cd sign\ in_up_frontend
npm install
# or with yarn
yarn install
```

#### Guest Frontend Legacy
```bash
cd guest-frontend-legacy
npm install
```

---

## STEP 4: Run the Project Locally

### Backend Services

#### Guest Backend
```bash
cd guest_backend
python run.py
# Server runs on http://localhost:8000
```

#### Staff Backend
```bash
cd staff\ backend
python run.py
# Server runs on http://localhost:8001
```

### Frontend Services

#### Sign In/Up Frontend
```bash
cd sign\ in_up_frontend
npm run dev
# Server runs on http://localhost:5173
```

#### Guest Frontend
```bash
cd guest-frontend-legacy
npm run dev
# Server runs on http://localhost:5174
```

---

## STEP 5: Database Setup (If Required)

Check the respective backend `README.md` files for database initialization:

- [Guest Backend README](guest_backend/README.md)
- [Staff Backend Documentation](staff\ backend/README.md)

---

## STEP 6: Run Tests

### Python Tests
```bash
cd guest_backend
pytest

# or with coverage
pytest --cov=app tests/
```

```bash
cd staff\ backend
pytest
```

### Frontend Tests
```bash
cd sign\ in_up_frontend
npm run test
```

---

## Project Structure

```
Emergency_Crisis_System/
├── auth/                          # Authentication system
│   ├── jwt_handler.py
│   ├── hashing.py
│   ├── rate_limiter.py
│   └── routes.py
│
├── fire_risk/                     # Fire risk management
│   ├── api.py
│   └── requirements.txt
│
├── guest_backend/                 # Guest application backend
│   ├── app/
│   │   ├── main.py
│   │   ├── models/
│   │   ├── routes/
│   │   └── services/
│   ├── tests/
│   └── requirements.txt
│
├── guest-frontend-legacy/         # Guest dashboard (legacy)
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
│
├── sign in_up_frontend/           # Sign In/Up authentication frontend
│   ├── src/
│   ├── package.json
│   └── vite.config.js
│
├── staff backend/                 # Staff management backend
│   ├── models/
│   ├── routers/
│   ├── services/
│   ├── tests/
│   └── requirements.txt
│
└── start_all.ps1                  # PowerShell startup script
```

---

## Key Integrations

### API Endpoints

- **Guest Backend:** `http://localhost:8000/api/`
- **Staff Backend:** `http://localhost:8001/api/`
- **Fire Risk:** Available via API integration

### Authentication

All protected endpoints use JWT tokens. See [auth/QUICK_START.md](auth/QUICK_START.md) for authentication setup.

---

## Important Notes

⚠️ **DO NOT COMMIT:**
- `.env` files (use `.env.template` as reference)
- `node_modules/` directories
- `__pycache__/` directories
- `.venv/` or other virtual environments
- Build artifacts (`dist/`, `build/`)

✅ **ALWAYS:**
- Create a `.env` file from `.env.template` before running
- Install dependencies in a virtual environment (Python) or with npm (Node.js)
- Keep `.gitignore` up to date
- Test before pushing changes

---

## Troubleshooting

### Port Already in Use
If a port is already in use, you can specify a different port:

```bash
# Python (modify in config.py or run.py)
python run.py --port 8002

# Node.js (modify vite.config.js or use)
npm run dev -- --port 5175
```

### Virtual Environment Issues
```bash
# Remove and recreate virtual environment
rm -r venv  # On macOS/Linux: rm -rf venv
python -m venv venv
source venv/bin/activate  # On macOS/Linux
venv\Scripts\activate     # On Windows
pip install -r requirements.txt
```

### Node Modules Issues
```bash
# Clear cache and reinstall
rm -r node_modules package-lock.json
npm install
```

---

## Team Workflow

1. **Create a branch** for your feature:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Commit changes** with clear messages:
   ```bash
   git commit -m "Add: description of changes"
   ```

3. **Push to remote**:
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create a Pull Request** on GitHub for review

5. **Merge after approval**:
   ```bash
   git checkout main
   git pull origin main
   git merge feature/your-feature-name
   git push origin main
   ```

---

## Support & Documentation

- **Auth System:** [auth/README.md](auth/QUICK_START.md)
- **Guest Backend:** [guest_backend/README.md](guest_backend/README.md)
- **Testing Guide:** [auth/TESTING_GUIDE.md](auth/TESTING_GUIDE.md)
- **Deployment:** [DEPLOYMENT_BEST_PRACTICES.md](auth/DEPLOYMENT_BEST_PRACTICES.md)

---

## Last Updated
- **Repository:** Clean GitHub push ✅
- **Status:** Ready for team development
- **Commit:** `913a012` - Initial clean project setup with frontend-backend integration
