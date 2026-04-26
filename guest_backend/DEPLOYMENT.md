# Deployment Guide - Guest Backend

## Production Deployment Checklist

### Pre-Deployment

- [ ] MongoDB Atlas cluster created and connection string verified
- [ ] Staff backend URL configured and accessible
- [ ] Environment variables set correctly
- [ ] DEBUG=False in production
- [ ] All tests passing
- [ ] Code reviewed and security scanned

### Environment Setup

```bash
# Set production environment variables
export MONGODB_URL="mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority"
export MONGODB_DB_NAME="emergency_system_guest"
export STAFF_BACKEND_URL="https://staff-backend.example.com"
export DEBUG=False
export PYTHONUNBUFFERED=1
```

### Server Setup

#### Option 1: Using Gunicorn + Uvicorn (Recommended)

```bash
# Install gunicorn
pip install gunicorn

# Run with 4 workers (adjust based on CPU cores)
gunicorn -w 4 \
  -k uvicorn.workers.UvicornWorker \
  -b 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile - \
  app.main:app
```

#### Option 2: Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t guest-backend:1.0 .
docker run -p 8000:8000 \
  -e MONGODB_URL="..." \
  -e STAFF_BACKEND_URL="..." \
  guest-backend:1.0
```

#### Option 3: Kubernetes

Create `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: guest-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: guest-backend
  template:
    metadata:
      labels:
        app: guest-backend
    spec:
      containers:
      - name: guest-backend
        image: guest-backend:1.0
        ports:
        - containerPort: 8000
        env:
        - name: MONGODB_URL
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: mongodb_url
        - name: STAFF_BACKEND_URL
          value: "http://staff-backend:8001"
        - name: DEBUG
          value: "False"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: guest-backend
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 8000
  selector:
    app: guest-backend
```

Deploy:

```bash
kubectl apply -f deployment.yaml
```

### Reverse Proxy Setup (Nginx)

```nginx
server {
    listen 80;
    server_name guest-api.example.com;

    client_max_body_size 10M;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /health {
        proxy_pass http://localhost:8000/health;
        proxy_read_timeout 5s;
    }
}
```

### Database Optimization

#### MongoDB Atlas Settings

1. **Connection**: Enable connection pooling
   - Min pool size: 10
   - Max pool size: 50

2. **Indexes**: Create recommended indexes

```javascript
// Index on session_id for fast lookups
db.guest_sessions.createIndex({ "session_id": 1 })

// Index on floor_id for floor-based queries
db.floor_graphs.createIndex({ "floor_id": 1 })

// Index for emergency state queries
db.emergency_state.createIndex({ "updated_at": -1 })

// Index for guest logs queries
db.guest_logs.createIndex({ "session_id": 1, "timestamp": -1 })
```

3. **Backup**: Enable autamatic backups
   - Frequency: Daily
   - Retention: 30 days

### Monitoring & Logging

#### Application Logging

Configure structured logging:

```python
import logging
import json

# JSON logging for ELK stack
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
```

#### Health Check Endpoint

Monitor with:

```bash
curl http://guest-api.example.com/health
```

Expected response:

```json
{
  "status": "healthy",
  "service": "guest-backend"
}
```

### Performance Tuning

1. **Connection Pooling**: Already handled by Motor
2. **Response Compression**: Enable gzip in reverse proxy
3. **Caching Headers**: Set appropriate cache headers for floor graphs
4. **Database**: Use indexes as shown above

### Security Hardening

- [ ] Enable HTTPS/TLS
- [ ] Set CORS appropriately (not *)
- [ ] Rate limiting on public endpoints
- [ ] Input validation and sanitization
- [ ] SQL injection protection (using Pydantic models)
- [ ] Regular security updates
- [ ] Monitor for suspicious activity

### Scaling

For high load:

1. **Horizontal Scaling**: Run multiple instances behind load balancer
2. **Database**: MongoDB sharding if needed
3. **Caching**: Consider Redis for floor graphs (optional)
4. **CDN**: Serve floor plans from CDN

### Troubleshooting

#### MongoDB Connection Issues

```bash
# Test connection
mosquitto_pub -h ... -u user -P pass ...

# Check connection string format
mongodb+srv://user:password@cluster.mongodb.net/dbname?retryWrites=true&w=majority
```

#### Performance Issues

```bash
# Check API response times
curl -I http://localhost:8000/health

# Monitor error rates
# Check application logs for stack traces
```

#### Staff Backend Communication

```bash
# Test connectivity
curl http://staff-backend:8001/health

# Check request/response logs
```

### Rollback Plan

1. Keep previous version running on separate port
2. Update load balancer to old version
3. Investigate issue
4. Deploy fix to new version
5. Gradual rollout (canary deployment)

### Documentation

- [ ] Deployment runbook created
- [ ] Emergency contact list prepared
- [ ] Known issues documented
- [ ] Incident response plan ready

---

**For production support and updates, refer to the main README.md**
