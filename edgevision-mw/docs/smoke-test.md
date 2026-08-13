# EdgeVision Studio — Manual Smoke Test Script

Run these checks after every deploy or major change. All should pass.

## Prerequisites

- Backend running at `http://localhost:8000` (uvicorn)
- Frontend running at `http://localhost:3000` (vite dev server)
- PostgreSQL, Redis, MinIO accessible on localhost
- 20 seeded images in MinIO (run `scripts/seed_minio.py` if not done)

---

## 1. Backend Health

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected: `{"status": "ok", "checks": {"postgres": true, "redis": true, "minio": true}}`

---

## 2. Authentication

### 2a. Login
```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@edgevision.mw","password":"admin123"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('TOKEN:', d['access_token'][:20]+'...')"
```

Expected: JWT token returned.

### 2b. Register (role escalation blocked)
```bash
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"pass123","full_name":"Test","role":"ADMIN"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Role:', d['role'])"
```

Expected: `Role: BUYER` (not ADMIN)

---

## 3. Studio Session & Image Serving

### 3a. Create session
```bash
TOKEN="<paste from 2a>"
curl -s -X POST http://localhost:8000/api/v1/studio/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"dataset_id":"DS-LILONGWE-001"}' | python3 -m json.tool
```

Expected: 200 with `id` (UUID).

### 3b. Serve image
```bash
# Use the annotation_id from session response
ANN_ID="<annotation_id from list-images>"
curl -s -o /dev/null -w "HTTP %{http_code}, %{size_download} bytes, type=%{content_type}" \
  "http://localhost:8000/api/v1/studio/images/${ANN_ID}/serve" \
  -H "Authorization: Bearer $TOKEN"
```

Expected: `HTTP 200`, ~5000+ bytes, `image/png`.

---

## 4. Annotation Save Flow

```bash
SESS_ID="<session id from 3a>"
curl -s -X POST "http://localhost:8000/api/v1/studio/sessions/${SESS_ID}/annotations/save" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"image_index":0,"annotations":[{"class":"vehicle","confidence":0.9,"bbox":[100,100,200,200]}],"annotation_type":"bbox"}' \
  | python3 -m json.tool
```

Expected: 200, `"saved": true`, updated `health.completeness_pct > 0`.

---

## 5. Health Dashboard

```bash
curl -s "http://localhost:8000/api/v1/studio/datasets/ds-fbc362b68ac1/health" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: 200 with `overall_score`, `completeness_pct`, `recommendations`.

---

## 6. Review Queue

```bash
curl -s "http://localhost:8000/api/v1/studio/sessions/${SESS_ID}/review-queue?limit=5" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: 200 with `images[]` array.

---

## 7. Export Flow

```bash
curl -s -X POST http://localhost:8000/api/v1/studio/datasets/ds-fbc362b68ac1/exports \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"format":"coco"}' | python3 -m json.tool
```

Expected: 200 with `id` and `status: "pending"`.

---

## 8. Frontend (Browser)

Open `http://localhost:3000` in Chrome/Edge.

### 8a. Login page
- [ ] Gradient background renders
- [ ] Login form works (admin@edgevision.mw / admin123)
- [ ] Switches to register mode and back

### 8b. Home page
- [ ] Shows dataset info and session creation
- [ ] Creates session, navigates to annotation view

### 8c. Annotation page
- [ ] Image loads in canvas (not broken image icon)
- [ ] Can draw bounding box
- [ ] Label selector shows classes (Vehicle, Pedestrian, etc.)
- [ ] Save button works, status bar shows "Saved!"
- [ ] Prev/Next navigation works

### 8d. Health dashboard
- [ ] Score cards render with ring charts
- [ ] Class distribution pie chart shows
- [ ] Recommendations list renders

### 8e. AI Assist (requires browser + ONNX)
- [ ] "AI Assist" button in toolbar
- [ ] Clicking image triggers inference (may show "Model loading...")
- [ ] After model loads, clicking returns bounding box

### 8f. Turbo Review
- [ ] Navigate to review tab
- [ ] Images listed, can approve/reject
- [ ] Batch submit works

---

## 9. Offline / Service Worker

1. Open DevTools → Application → Service Workers
2. Confirm `sw.js` is registered and active
3. Go to Network tab, check caching:
   - API requests to `/api/v1/studio/` → NetworkFirst strategy
   - Image requests → CacheFirst strategy
4. Disable network (DevTools → Offline), reload — app should still load cached assets

---

## 10. PWA Manifest

1. DevTools → Application → Manifest
2. Confirm:
   - Name: "EdgeVision Studio"
   - Icons present (192x192, 512x512)
   - Display: standalone
   - Theme color: #0f172a

---

## 11. i18n

1. In browser console: `i18next.changeLanguage('ny')`
2. Confirm labels switch to Chichewa:
   - Login: "Lowani" button
   - Sidebar: "Zithunzi"
   - Annotation: "Sungani" button
3. Switch back: `i18next.changeLanguage('en')`

---

## 12. Test Suite

```bash
cd edgevision-mw
source .venv/bin/activate
POSTGRES_HOST=localhost python -m pytest tests/ -v --tb=short
```

Expected: **145 passed**

---

## Quick Reset (if broken)

```bash
# Re-seed MinIO + DB
cd edgevision-mw && source .venv/bin/activate
python scripts/seed_minio.py

# Restart backend
lsof -ti:8000 | xargs kill -9
POSTGRES_HOST=localhost MINIO_ENDPOINT=localhost:9000 \
  REDIS_URL="redis://localhost:6379/0" \
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &

# Restart frontend
cd frontend && npx vite --host
```
