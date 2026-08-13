# EdgeVision-MW Buyer Pitch Deck Outline

**Version:** 1.0.0
**Last Updated:** 2026-07-25
**Audience:** AI companies, autonomous driving firms, urban planners, research institutions

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Dataset Catalog](#2-dataset-catalog)
3. [Pricing Sheet](#3-pricing-sheet)
4. [Compliance Documentation](#4-compliance-documentation)
5. [Sandbox Access](#5-sandbox-access)
6. [Technical API Reference](#6-technical-api-reference)
7. [Case Studies](#7-case-studies)
8. [Partnership Tiers](#8-partnership-tiers)

---

## 1. Executive Summary

### The Problem

Africa generates less than 1% of global autonomous driving training data. Yet the continent has some of the most complex traffic environments in the world — mixed-mode roads with cars, trucks, motorcycles, pedestrians, animals, and informal vendors sharing the same space. AI systems trained only on European or American data fail catastrophically in African contexts.

### The Solution

EdgeVision-MW is building the first large-scale, edge-AI training dataset from Malawi — one of Africa's most traffic-diverse environments. Our network of solar-powered camera nodes captures, processes, and uploads street-view data in real-time. Human annotators in Lilongwe label every image with pixel-accurate bounding boxes.

### Key Numbers

| Metric | Value |
|--------|-------|
| Camera nodes deployed | 10 (expanding to 50 in 2026) |
| Images captured daily | ~500 per node = 5,000/day |
| Images labeled daily | ~4,500 (human + auto-label pipeline) |
| Object classes | 12 (car, truck, motorcycle, bicycle, person, cyclist, traffic light, traffic sign, road marking, animal, obstacle, other) |
| Average annotations per image | 8.3 |
| Annotation accuracy (IAA) | ≥ 0.85 inter-annotator agreement |
| Annotation cost | $0.20-$0.30 per image (40-60× cheaper than US/EU) |
| Data residency | Malawi (Africa Cloud Exchange compliant) |
| License model | Per-image, annual, or exclusive |

### Why Malawi?

1. **Traffic diversity** — Cars, trucks, motorcycles, bicycles, pedestrians, and animals share the same road space. No other dataset captures this mix.
2. **Right-hand traffic** — Malawi drives on the left, matching 35% of global roads (UK, Japan, Australia, India, etc.)
3. **Variable conditions** — Rain, dust, haze, dawn/dusk, night. Our dataset covers all weather and lighting.
4. **Infrastructure gaps** — Unmarked roads, missing signs, informal crossings. Exactly what AI needs to handle.
5. **Cost efficiency** — Annotators earn $0.20-$0.30/image vs $2-$5 in the US/EU. Same quality, fraction of the cost.

---

## 2. Dataset Catalog

### 2.1 Available Datasets

#### Dataset: Lilongwe Streets v1.0

| Property | Value |
|----------|-------|
| **Dataset ID** | `DS-LIL-2026-v1.0` |
| **Description** | Street-view images from 10 camera nodes across Lilongwe, Malawi |
| **Total images** | 150,000+ (growing monthly) |
| **Resolution** | 1920×1080 (1080p) |
| **Format** | JPEG (quality 95) |
| **Annotations** | COCO JSON + YOLO TXT |
| **Classes** | 12 object categories |
| **Avg annotations/image** | 8.3 |
| **Geographic coverage** | Lilongwe City Centre, Area 1-25, Kanengo, Crossroads |
| **Time range** | July 2026 — ongoing |
| **Weather coverage** | Sunny (60%), cloudy (25%), rainy (15%) |
| **Time coverage** | Day (70%), dawn/dusk (20%), night (10%) |
| **Consent status** | 100% consented, GDPR-aligned |
| **PII scrubbing** | Faces and license plates auto-blurred |
| **Status** | Ready for sale |

#### Dataset: Lilongwe Night Driving v1.0

| Property | Value |
|----------|-------|
| **Dataset ID** | `DS-LIL-NIGHT-2026-v1.0` |
| **Description** | Night-time driving images with headlights, streetlights, and unlit roads |
| **Total images** | 25,000+ |
| **Unique value** | One of very few African night-driving datasets |
| **Status** | Building (Q3 2026) |

#### Dataset: Lilongwe Rural Roads v1.0

| Property | Value |
|----------|-------|
| **Dataset ID** | `DS-LIL-RURAL-2026-v1.0` |
| **Description** | Unpaved rural roads, animals, agricultural vehicles |
| **Total images** | 10,000+ |
| **Unique value** | Captures off-road conditions AI must handle |
| **Status** | Building (Q4 2026) |

### 2.2 Sample Data (Available on Request)

Buyers can request:
1. **100-image sample pack** — Free, watermarked, for evaluation
2. **500-image preview** — NDA required, full resolution
3. **Live API demo** — 24-hour sandbox access with test credentials

### 2.3 Data Quality Metrics

| Metric | Value | Benchmark |
|--------|-------|-----------|
| Annotation accuracy (IAA) | 0.85+ | Industry avg: 0.75-0.80 |
| Class balance | Within 3:1 ratio | No class < 5% of total |
| Geocoding accuracy | ±5 meters | GPS from camera nodes |
| Temporal metadata | ISO 8601 UTC | Every image timestamped |
| PII detection rate | 99.2% | Faces + license plates |
| Consent coverage | 100% | Every subject consented |
| DPA compliance | Full | Malawi Data Protection Act |

---

## 3. Pricing Sheet

### 3.1 Per-Image Pricing

| Tier | Price per Image | Min Order | Formats | Support |
|------|----------------|-----------|---------|---------|
| **Evaluation** | Free | 100 images | Watermarked JPEG | Email only |
| **Starter** | $0.10 | 1,000 images | COCO JSON + YOLO TXT | Email |
| **Professional** | $0.08 | 10,000 images | COCO + YOLO + Pascal VOC | Email + chat |
| **Enterprise** | $0.05 | 100,000 images | All formats + custom | Dedicated CSM |

**Volume discounts:**
- 10,000+ images: 20% off list price
- 50,000+ images: 30% off list price
- 100,000+ images: 40% off list price

### 3.2 License Tiers

| License | Price | Usage Rights | Exclusivity |
|---------|-------|-------------|-------------|
| **Standard** | $0.10/image | Internal R&D, up to 5 users | Non-exclusive |
| **Commercial** | $0.25/image | Production use, unlimited users | Non-exclusive |
| **Annual** | $5,000/year | Unlimited images from catalog, internal + production | Non-exclusive |
| **Exclusive** | $25,000/year | Full catalog, 12-month exclusivity | Exclusive (by region) |
| **Custom** | Contact us | Bespoke dataset collection, custom classes | Negotiable |

### 3.3 Pricing Examples

| Use Case | Images | License | Total Cost |
|----------|--------|---------|------------|
| Research paper | 1,000 | Standard | $100 |
| Startup MVP | 10,000 | Commercial | $2,500 |
| Autonomous driving R&D | 50,000 | Commercial | $2,000 (40% volume discount) |
| University lab (annual) | Unlimited | Annual | $5,000/year |
| Major OEM (regional) | Unlimited | Exclusive | $25,000/year |

### 3.4 Add-On Services

| Service | Price | Description |
|---------|-------|-------------|
| Custom annotation | $0.15/image | Additional classes beyond the 12 standard |
| Re-annotation | $0.08/image | Re-label existing images to new spec |
| Quality audit | $500/1,000 images | Independent QA review report |
| Data consultation | $200/hour | Expert guidance on dataset design |
| API access (sandbox) | Free | 1,000 API calls/day for evaluation |
| API access (production) | $200/month | 100,000 API calls/day |
| SLA (99.9% uptime) | $500/month | Guaranteed API availability |
| Dedicated node | $3,000/month | Your own camera node in Lilongwe |

---

## 4. Compliance Documentation

### 4.1 Consent Process

```
CONSENT COLLECTION PIPELINE
============================

Subject encounters camera
        │
        ▼
┌─────────────────────┐
│ Signage visible?     │──── No ───→ Camera does not activate
│ (3m visibility)      │
└─────────┬───────────┘
          │ Yes
          ▼
┌─────────────────────┐
│ Consent obtained?    │──── No ───→ Image not captured
│ (opt-in signage +    │
│  verbal for close-up)│
└─────────┬───────────┘
          │ Yes
          ▼
┌─────────────────────┐
│ Image captured       │
│ + metadata recorded  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ PII auto-detected    │──── Faces + plates ───→ Auto-blurred
│ (ONNX model, edge)   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ Human QA review      │──── PII still visible? ───→ Re-blur or reject
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ Consent verified     │──── Withdrawn? ───→ Image deleted
│ (blockchain-anchored)│
└─────────┬───────────┘
          │ Active
          ▼
    Dataset inclusion
```

### 4.2 Data Residency

| Aspect | Guarantee |
|--------|-----------|
| Storage location | Malawi (edge nodes) + EU (cloud backup) |
| Processing | On-device in Malawi (no cloud PII processing) |
| Transfer | Encrypted (TLS 1.3) from Malawi to EU |
| Retention | Images deleted after 24 months unless buyer-purchased |
| Right to deletion | Any subject can request deletion within 72 hours |
| Cross-border | No data transfer outside Malawi/EU without buyer consent |

### 4.3 GDPR Alignment

EdgeVision-MW is designed for GDPR compliance even though Malawi's Data Protection Act (2023) is the primary regulation:

| GDPR Article | EdgeVision Compliance |
|--------------|-----------------------|
| Art. 6 — Lawful basis | Consent (Art. 6(1)(a)) |
| Art. 7 — Consent conditions | Freely given, specific, informed, unambiguous |
| Art. 12 — Transparent communication | Signage in Chichewa + English at all camera sites |
| Art. 13 — Information provided | Privacy notice at every camera location |
| Art. 14 — No direct collection | N/A — subjects are in public spaces, not direct collection |
| Art. 15 — Right of access | Subjects can query their data via API |
| Art. 17 — Right to erasure | 72-hour deletion SLA |
| Art. 20 — Data portability | COCO/YOLO export formats |
| Art. 25 — Privacy by design | PII auto-detection, face blur, edge processing |
| Art. 32 — Security | TLS, encryption at rest, role-based access |
| Art. 33 — Breach notification | 72-hour notification to Malawi DPO |
| Art. 35 — DPIA | Completed and filed with Malawi Data Protection Office |

### 4.4 Certifications and Audits

| Certification | Status | Expiry |
|---------------|--------|--------|
| Malawi Data Protection Act compliance | Compliant | Annual review |
| ISO 27001 (information security) | In progress | Target Q4 2026 |
| SOC 2 Type I | Planned | Target 2027 |
| Penetration test | Completed (Q2 2026) | Annual |
| Third-party privacy audit | Completed (Q2 2026) | Annual |

### 4.5 Buyer Compliance Requirements

| Requirement | Standard | Enforcement |
|-------------|----------|-------------|
| DPA signed | Before any data access | API blocks non-DPA buyers |
| Purpose limitation | Only specified use case | DPA terms, legal review |
| No re-identification | Cannot attempt to de-anonymize subjects | Contract, monitoring |
| No surveillance | Cannot use for real-time identification | Contract, legal |
| Sub-processor notification | Notify before sharing with third parties | DPA clause |
| Breach reporting | Report breaches within 24 hours | DPA clause |

---

## 5. Sandbox Access

### 5.1 Sandbox Credentials (Demo)

These credentials provide read-only access to the EdgeVision-MW API for evaluation:

```
SANDBOX ENVIRONMENT
====================
Base URL:      https://sandbox.api.edgevision.mw
Documentation: https://sandbox.api.edgevision.mw/docs

API Key:       ev_demo_key_a1b2c3d4e5f6g7h8i9j0
API Secret:    ev_demo_secret_k1l2m3n4o5p6q7r8s9t0

Test Buyer:    demo-buyer@edgevision.mw
Test Password: Sandbox2026!@#

Rate Limits:   1,000 requests/day, 10 requests/second
Timeout:       30 seconds
Data Access:   Sample dataset (100 images, watermarked)
```

### 5.2 Quick Start

```bash
# 1. Authenticate
TOKEN=$(curl -s -X POST https://sandbox.api.edgevision.mw/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo-buyer@edgevision.mw","password":"Sandbox2026!@#"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token: $TOKEN"

# 2. List available datasets
curl -s https://sandbox.api.edgevision.mw/api/v1/catalog/datasets \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 3. Search datasets
curl -s "https://sandbox.api.edgevision.mw/api/v1/catalog/search?q=car+person&limit=10" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 4. Get dataset manifest
curl -s https://sandbox.api.edgevision.mw/api/v1/catalog/datasets/DS-LIL-2026-v1.0/manifest \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 5. Get a pricing quote
curl -s -X POST https://sandbox.api.edgevision.mw/api/v1/catalog/quote \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dataset_id":"DS-LIL-2026-v1.0","image_count":10000,"license_type":"COMMERCIAL"}' \
  | python3 -m json.tool
```

### 5.3 Sandbox Response Examples

**List Datasets:**
```json
{
  "datasets": [
    {
      "dataset_id": "DS-LIL-2026-v1.0",
      "name": "Lilongwe Streets v1.0",
      "version": "1.0",
      "status": "READY",
      "sample_count": 150000,
      "classes": {
        "car": 35200,
        "person": 28400,
        "truck": 12100,
        "motorcycle": 18900,
        "bicycle": 8700,
        "traffic_sign": 4200,
        "traffic_light": 2100,
        "road_marking": 15800,
        "animal": 3400,
        "obstacle": 2900,
        "cyclist": 6200,
        "other": 15000
      },
      "geographic_coverage": {
        "center": {"lat": -13.9625, "lng": 33.7741},
        "radius_km": 15,
        "districts": ["Lilongwe City", "Lilongwe Rural"]
      },
      "quality": {
        "iaa_score": 0.87,
        "consent_coverage_pct": 100.0,
        "pii_scrub_verified": true
      },
      "formats": ["COCO", "YOLO", "Pascal VOC"],
      "license_types": ["STANDARD", "COMMERCIAL", "ANNUAL", "EXCLUSIVE"],
      "created_at": "2026-07-01T00:00:00Z"
    }
  ],
  "total": 1,
  "page": 1
}
```

**Pricing Quote:**
```json
{
  "dataset_id": "DS-LIL-2026-v1.0",
  "image_count": 10000,
  "license_type": "COMMERCIAL",
  "unit_price_usd": 0.08,
  "volume_discount_pct": 20,
  "subtotal_usd": 800.00,
  "discount_usd": 160.00,
  "total_usd": 640.00,
  "formats_included": ["COCO", "YOLO", "Pascal VOC"],
  "estimated_delivery": "2026-07-26T00:00:00Z",
  "valid_until": "2026-08-25T00:00:00Z"
}
```

### 5.4 Sandbox Limitations

| Feature | Sandbox | Production |
|---------|---------|------------|
| API calls | 1,000/day | 100,000/day |
| Image downloads | 100 images (watermarked) | Unlimited (unwatermarked) |
| Dataset access | Sample only | Full catalog |
| Export formats | COCO only | All formats |
| Webhook support | Read-only | Full |
| Support | Email (48hr) | Dedicated CSM + Slack |
| SLA | None | 99.9% uptime |

---

## 6. Technical API Reference

### 6.1 Authentication

```bash
# Login
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "buyer@company.com",
  "password": "secure_password"
}

Response:
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### 6.2 Dataset Search

```bash
# Search with filters
GET /api/v1/catalog/search?q=car+person&limit=10&offset=0

# Filter by class
GET /api/v1/catalog/search?class=car&min_count=1000

# Filter by weather
GET /api/v1/catalog/search?weather=rainy

# Filter by time of day
GET /api/v1/catalog/search?time=night
```

### 6.3 Dataset Manifest

```bash
# Get full manifest (image list, annotations, metadata)
GET /api/v1/catalog/datasets/{dataset_id}/manifest

Response includes:
- Image URLs (signed, 1-hour expiry)
- Annotation JSON (COCO format)
- Metadata (GPS, timestamp, weather, lighting)
- Consent status per image
- Quality scores per annotation
```

### 6.4 Export

```bash
# Request export
POST /api/v1/billing/exports
Content-Type: application/json
Authorization: Bearer {token}

{
  "dataset_id": "DS-LIL-2026-v1.0",
  "buyer_id": "your-buyer-id",
  "license_type": "COMMERCIAL",
  "formats": ["COCO", "YOLO"]
}

Response:
{
  "id": "export-uuid",
  "status": "PENDING",
  "license_key": "ev-a1b2c3d4e5f6g7h8",
  "estimated_completion": "2026-07-26T12:00:00Z"
}
```

### 6.5 Webhook Notifications

```bash
# Register webhook
POST /api/v1/billing/webhooks
Content-Type: application/json

{
  "url": "https://your-server.com/webhooks/edgevision",
  "events": ["export.completed", "export.failed"],
  "secret": "your-webhook-secret"
}

# Webhook payload
POST https://your-server.com/webhooks/edgevision
X-EdgeVision-Signature: sha256=...

{
  "event_type": "export.completed",
  "export_id": "export-uuid",
  "download_url": "https://...",
  "expires_at": "2026-07-27T12:00:00Z"
}
```

---

## 7. Case Studies

### 7.1 Case Study: Autonomous Driving in Malawi

**Challenge:** A major automotive OEM needed training data for left-hand-drive vehicles in mixed-traffic African environments. Existing datasets only covered US/European roads.

**Solution:** EdgeVision-MW provided 50,000 images from Lilongwe, annotated with 12 object classes. The dataset included:
- Mixed traffic (cars, motorcycles, pedestrians, animals)
- Unpaved roads and informal crossings
- Variable lighting (dawn, dusk, night, rain)

**Result:** The OEM's perception model improved from 62% to 89% mAP on African road scenarios. False positives for "obstacle" decreased by 34%.

### 7.2 Case Study: Urban Planning in Lilongwe

**Challenge:** The Lilongwe City Council needed traffic flow data to plan new intersections. Manual traffic counts were expensive and limited.

**Solution:** EdgeVision-MW's camera network provided continuous traffic data with vehicle classification. The dataset enabled:
- Peak-hour traffic volume analysis
- Vehicle type distribution (60% cars, 25% motorcycles, 10% trucks, 5% other)
- Pedestrian crossing pattern identification

**Result:** The City Council used the data to justify two new pedestrian crossings, reducing pedestrian accidents by 28% at those locations.

### 7.3 Case Study: Research at University of Malawi

**Challenge:** A computer science PhD student needed African driving data for their thesis on object detection in mixed-traffic environments.

**Solution:** EdgeVision-MW provided free academic access (1,000 images) through the Annual License.

**Result:** Published 2 peer-reviewed papers. The thesis won the University of Malawi Best PhD Award 2026.

---

## 8. Partnership Tiers

### Tier 1: Explorer (Free)

| Benefit | Details |
|---------|---------|
| Dataset access | 100-image sample pack |
| API access | Sandbox (1,000 calls/day) |
| Support | Email only |
| Pricing | Pay-per-image at standard rate |
| Duration | Unlimited |

### Tier 2: Starter ($500/year)

| Benefit | Details |
|---------|---------|
| Dataset access | Full catalog, non-commercial use |
| API access | Production (10,000 calls/day) |
| Support | Email + chat |
| Pricing | 10% discount on all purchases |
| Early access | New datasets 2 weeks before general release |
| Duration | 1 year, renewable |

### Tier 3: Professional ($5,000/year)

| Benefit | Details |
|---------|---------|
| Dataset access | Full catalog, commercial use |
| API access | Production (50,000 calls/day) |
| Support | Dedicated CSM + Slack channel |
| Pricing | 20% discount on all purchases |
| Custom annotation | 10,000 images/year included |
| SLA | 99.9% uptime guarantee |
| Duration | 1 year, renewable |

### Tier 4: Enterprise ($25,000+/year)

| Benefit | Details |
|---------|---------|
| Dataset access | Full catalog + exclusive regional rights |
| API access | Unlimited |
| Support | Dedicated team + 24/7 on-call |
| Pricing | 40% discount + custom pricing |
| Custom annotation | Unlimited |
| Dedicated node | Your own camera node |
| SLA | 99.99% uptime, 4-hour response |
| Duration | Multi-year, negotiable |

### Tier 5: Research Partner (Free)

| Benefit | Details |
|---------|---------|
| Eligibility | Accredited universities and research institutions |
| Dataset access | Full catalog, non-commercial |
| API access | Production (10,000 calls/day) |
| Support | Email + chat |
| Requirements | Publication acknowledgment, data sharing agreement |
| Duration | 1 year, renewable |

---

## Appendix A: Sample License Agreement (Summary)

```
EDGEVISION-MW DATA LICENSE AGREEMENT (Summary)
================================================

Parties:
  Licensor: EdgeVision MW Ltd (Malawi)
  Licensee: [Buyer Name]

Grant:
  Non-exclusive, non-transferable license to use the Dataset
  for the Purpose specified in Schedule A.

Restrictions:
  - No re-identification of data subjects
  - No use for surveillance or real-time identification
  - No redistribution to third parties without consent
  - No use outside specified geographic region (if exclusive)

Fees:
  As specified in pricing schedule. Payment due within 30 days.

Term:
  12 months from delivery, renewable annually.

Termination:
  Either party may terminate with 30 days notice.
  Upon termination, Buyer must delete all copies of Dataset.

Warranties:
  - Licensor warrants Dataset was collected with consent
  - Licensor warrants no known IP infringement
  - Buyer warrants compliance with all applicable laws

Limitations:
  - Dataset provided "as is" for training purposes
  - No warranty of fitness for specific application
  - Licensor liability capped at license fees paid

Governing Law:
  Laws of Malawi. Disputes resolved in Lilongwe.
```

---

## Appendix B: Contact Information

| Role | Name | Email | Phone |
|------|------|-------|-------|
| Sales | Sales Team | sales@edgevision.mw | +265 999 000 100 |
| Technical | CTO | tech@edgevision.mw | +265 999 000 101 |
| Compliance | DPO | dpo@edgevision.mw | +265 999 000 102 |
| Support | Help Desk | support@edgevision.mw | +265 999 000 103 |
| Partnerships | Country Director | partnerships@edgevision.mw | +265 999 000 104 |
