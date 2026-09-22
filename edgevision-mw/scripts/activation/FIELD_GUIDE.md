# FIELD DATA COLLECTION GUIDE — Lilongwe
## Phone Camera + Car Workflow

---

## What You Need

| Item | Notes |
|------|-------|
| Phone (iPhone or Android) | Camera app, 1080p minimum |
| Car with phone mount | Dashboard or windshield mount |
| Power bank or car charger | Phone drains fast recording video |
| 30 min free driving time | One route per session |
| Laptop with edgevision-mw cloned | For processing |

---

## Step 1: Capture Data (15 minutes)

### Option A: Video Recording (Recommended)
1. Mount phone on dashboard facing forward
2. Open camera app → Video mode → 1080p or 4K
3. Start recording
4. Drive your route at normal speed (30–50 km/h)
5. Stop recording when you arrive
6. **Tip:** Record 3–5 separate videos (one per road segment)

### Option B: Burst Photos
1. Mount phone on dashboard
2. Open camera app → Photo mode
3. Use burst mode or tap every 2–3 seconds
4. Drive your route
5. **Tip:** Take 100+ photos per route

### Recommended Routes (First Week)
| Route | Why | Est. Time |
|-------|-----|-----------|
| City Centre → Area 18 | Mixed traffic, pedestrians, minibuses | 15 min |
| Kanengo Road | Industrial, trucks, wide road | 10 min |
| Cross Road Roundabout | High congestion, near-miss hotspot | 10 min |
| Bwaila Hospital Road | Emergency vehicles, pedestrians | 8 min |
| Area 23 → Connectivity | Residential, bicycles, vendors | 12 min |

---

## Step 2: Copy Files to Laptop (2 minutes)

### iPhone
```
# Connect phone via USB
# Open Finder → select your phone → "Files" tab
# Navigate to DCIM/ folder
# Copy all .MOV and .HEIC files to a folder:
mkdir -p ~/edgevision-field/Tuesday_morning
cp /path/to/phone/DCIM/* ~/edgevision-field/Tuesday_morning/
```

### Android
```
# Connect phone via USB → File Transfer mode
# Copy from DCIM/Camera/:
mkdir -p ~/edgevision-field/Tuesday_morning
cp /path/to/phone/DCIM/Camera/* ~/edgevision-field/Tuesday_morning/
```

---

## Step 3: Process Data (5 minutes)

```bash
cd edgevision-mw

# 1. Extract frames + GPS + create batch + auto-label
POSTGRES_HOST=localhost SECRET_KEY=test-secret-key-for-testing-only-32chars!! \
  REDIS_PASSWORD=edgevision_redis \
  CELERY_BROKER_URL="redis://:edgevision_redis@localhost:6379/1" \
  .venv/bin/python scripts/activation/collect_field_data.py \
    --input ~/edgevision-field/Tuesday_morning/ \
    --node LIL-TRUST-001 \
    --route "City Centre → Area 18" \
    --interval 2.0 \
    --dedup
```

**What this does:**
- Extracts frames from video (every 2 seconds)
- Reads GPS from photo EXIF data
- Removes duplicate frames
- Creates an IngestionBatch in the database
- Dispatches YOLO auto-labeling via Celery
- Produces a manifest with all frame metadata

**Output:**
```
/tmp/field_frames/
├── *.jpg                    # Extracted frames
├── field_manifest.json      # Full metadata + GPS coords
└── (Celery auto-labels in DB)
```

---

## Step 4: Validate (5 minutes)

```bash
# Run YOLO validation on extracted frames
POSTGRES_HOST=localhost .venv/bin/python scripts/activation/validate_yolo.py \
    --frames /tmp/field_frames/ \
    --model yolov8x.pt

# Check daily numbers
POSTGRES_HOST=localhost .venv/bin/python scripts/activation/daily_check.py
```

---

## Step 5: Repeat

| Day | Route | Frames Target |
|-----|-------|---------------|
| Monday | City Centre loop | 100 |
| Tuesday | Kanengo Road | 100 |
| Wednesday | Cross Road area | 100 |
| Thursday | Bwaila Hospital | 80 |
| Friday | Area 23 residential | 100 |
| Saturday | Mix of all | 200 |
| **Total** | **5 routes** | **~680 frames** |

---

## Troubleshooting

### "No GPS data found"
- Phone GPS must be ON during capture
- iPhone: Settings → Privacy → Location Services → Camera = "While Using"
- Android: Settings → Location → On
- Some phones don't embed GPS in video, only photos

### "Video won't extract frames"
- Ensure video is .MOV (iPhone) or .MP4 (Android)
- If codec is unsupported: convert first
  ```bash
  ffmpeg -i input.MOV -codec:v libx264 -codec:a copy output.mp4
  ```

### "Celery worker not running"
```bash
POSTGRES_HOST=localhost SECRET_KEY=test-secret-key-for-testing-only-32chars!! \
  REDIS_PASSWORD=edgevision_redis \
  CELERY_BROKER_URL="redis://:edgevision_redis@localhost:6379/1" \
  .venv/bin/celery -A app.workers.celery_app worker --loglevel=info --concurrency=2
```

### "Node not found"
```bash
POSTGRES_HOST=localhost SECRET_KEY=test-secret-key-for-testing-only-32chars!! \
  .venv/bin/python scripts/activation/register_node.py
```

---

## Quick Reference — All Commands

```bash
# Setup (one time)
POSTGRES_HOST=localhost SECRET_KEY=test-secret-key-for-testing-only-32chars!! \
  .venv/bin/python scripts/activation/register_node.py

# Start Celery worker
POSTGRES_HOST=localhost SECRET_KEY=test-secret-key-for-testing-only-32chars!! \
  REDIS_PASSWORD=edgevision_redis \
  CELERY_BROKER_URL="redis://:edgevision_redis@localhost:6379/1" \
  .venv/bin/celery -A app.workers.celery_app worker --loglevel=info --concurrency=2 &

# Collect data (after each drive)
POSTGRES_HOST=localhost SECRET_KEY=test-secret-key-for-testing-only-32chars!! \
  REDIS_PASSWORD=edgevision_redis \
  CELERY_BROKER_URL="redis://:edgevision_redis@localhost:6379/1" \
  .venv/bin/python scripts/activation/collect_field_data.py \
    --input ~/edgevision-field/SESSION/ \
    --node LIL-TRUST-001 \
    --route "Route Name" \
    --interval 2.0

# Daily check (every morning)
POSTGRES_HOST=localhost SECRET_KEY=test-secret-key-for-testing-only-32chars!! \
  .venv/bin/python scripts/activation/daily_check.py

# YOLO validation (after collecting enough data)
POSTGRES_HOST=localhost SECRET_KEY=test-secret-key-for-testing-only-32chars!! \
  .venv/bin/python scripts/activation/validate_yolo.py \
    --frames /tmp/field_frames/ \
    --model yolov8x.pt

# Generate report (weekly)
POSTGRES_HOST=localhost SECRET_KEY=test-secret-key-for-testing-only-32chars!! \
  .venv/bin/python scripts/activation/generate_report.py \
    --node LIL-TRUST-001 \
    --days 7
```

---

## Data Flow

```
Phone (record video/photos)
  ↓
Laptop (copy files)
  ↓
collect_field_data.py
  ├── Extract video frames (every 2s)
  ├── Read GPS from photo EXIF
  ├── Dedup by perceptual hash
  ├── Create IngestionBatch
  └── Dispatch auto_label_task (Celery)
        ↓
YOLO Detection → Annotations → Events → Scenario Cards
        ↓
Daily Check → Reports → Municipal Dashboard
```
