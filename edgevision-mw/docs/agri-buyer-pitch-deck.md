# EdgeVision-MW Agriculture Buyer Pitch Deck

**Version:** 1.0.0
**Last Updated:** 2026-07-30
**Audience:** Agri-tech companies, crop insurers, research institutions, government agricultural agencies, precision agriculture firms

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Data Catalog](#2-data-catalog)
3. [Pricing Sheet](#3-pricing-sheet)
4. [Technical API Reference](#4-technical-api-reference)
5. [Compliance & Privacy](#5-compliance--privacy)
6. [Case Studies](#6-case-studies)
7. [Partnership Tiers](#7-partnership-tiers)

---

## 1. Executive Summary

### The Problem

Sub-Saharan Africa contributes less than 2% of global agricultural AI training data, despite being home to 60% of the world's uncultivated arable land. Crop models trained on US/European satellite and drone imagery fail in African contexts — different crop varieties, intercropping patterns, soil types, pest species, and weather conditions. Insurance companies, agri-tech platforms, and government agencies lack ground-truth data to build accurate yield prediction, disease detection, and crop classification models for the region.

### The Solution

EdgeVision-MW's agriculture data platform provides high-resolution, ground-level crop imagery from Malawi's major agricultural regions. Our network of solar-powered edge nodes captures field imagery through the full growing cycle — planting, vegetative growth, flowering, and harvest. Every image is annotated by trained Malawian agronomists with crop type, health status, growth stage, and pest/disease markers.

### Key Numbers

| Metric | Value |
|--------|-------|
| Active agri nodes | 8 (expanding to 25 in 2027) |
| Fields monitored | 40+ across 3 regions |
| Images captured weekly | ~3,000 per node = 24,000/week |
| Annotated weekly | ~20,000 (human + AI pipeline) |
| Crop classes | 8 (maize, tobacco, rice, groundnut, cassava, soybean, cotton, pigeon pea) |
| Health classes | 6 (healthy, stressed, diseased, pest-infested, nutrient-deficient, senescent) |
| Annotation accuracy (IAA) | ≥ 0.88 inter-annotator agreement |
| Annotation cost | $0.25-$0.35 per image (30-50× cheaper than drone/aerial survey) |
| Growth cycle coverage | Full season (120-180 days depending on crop) |
| Weather conditions | Sunny (55%), cloudy (30%), rainy (15%) |

### Why Malawi?

1. **Crop diversity** — Malawi grows 15+ commercial crops across distinct agro-ecological zones (highlands, plateau, lakeshore, rift valley). Maize alone has 30+ locally adapted varieties.
2. **Smallholder majority** — 80% of farms are <2 hectares, representing the global smallholder reality that satellite/AI models struggle with.
3. **Climate stress** — Recurrent drought, cyclone damage, and pest outbreaks (fall armyworm, locusts) provide training data for extreme conditions.
4. **Intercropping complexity** — Maize-bean-pumpkin intercropping is the norm, challenging AI models trained on monoculture.
5. **Cost efficiency** — Local agronomist annotators at $0.25-0.35/image vs $8-12 in US/EU for equivalent botanical expertise.

---

## 2. Data Catalog

### 2.1 Available Datasets

#### Dataset: Malawi Crop Health v1.0

| Property | Value |
|----------|-------|
| **Dataset ID** | `DS-AGRI-HEALTH-DEMO-001` |
| **Description** | Field-level crop health imagery from Lilongwe, Dedza, and Machinga districts |
| **Total images** | 50,000+ (growing monthly) |
| **Resolution** | 1920×1080 (1080p) |
| **Format** | JPEG (quality 95) |
| **Annotations** | COCO JSON + YOLO TXT segmentation masks |
| **Crop classes** | Maize, Tobacco, Rice, Groundnut, Cassava, Soybean, Cotton, Pigeon Pea |
| **Health classes** | Healthy, Water-Stressed, Nutrient-Deficient, Pest-Infested, Diseased, Senescent |
| **Growth stage labels** | Vegetative, Flowering, Grain-Fill, Mature, Harvest |
| **Annotators** | Certified agronomists (2 independent labels per image, IAA-scored) |
| **Geographic coverage** | 3 districts (Lilongwe, Dedza, Machinga) — 40+ fields |
| **Time range** | October 2025 (planting) — ongoing |
| **Temporal coverage** | Each field photographed every 7 days through full growing cycle |
| **Weather coverage** | Sunny (55%), cloudy (30%), rain (15%) |
| **Consent status** | 100% landowner consented |
| **PII scrubbing** | Faces auto-blurred, geolocation generalized to field level |
| **Status** | Ready for sale |

#### Dataset: Malawi Crop Type Maps v1.0

| Property | Value |
|----------|-------|
| **Dataset ID** | `DS-AGRI-CROP-DEMO-001` |
| **Description** | Crop type identification across Central and Southern Malawi |
| **Total images** | 35,000+ |
| **Unique value** | Intercropping patterns annotated (e.g., maize + pigeon pea) |
| **Status** | Ready for sale |

#### Dataset: Malawi Pest & Disease Atlas v1.0

| Property | Value |
|----------|-------|
| **Dataset ID** | `DS-AGRI-PEST-DEMO-001` |
| **Description** | Pest and disease images with severity ratings |
| **Total images** | 12,000+ |
| **Included pests** | Fall armyworm, maize stalk borer, aphids, termites |
| **Included diseases** | Maize streak virus, cassava mosaic, rice blast, groundnut rosette |
| **Severity scale** | Mild / Moderate / Severe per image |
| **Status** | Building (Q1 2027) |

### 2.2 Sample Data

Buyers can request:
1. **50-image sample pack** — Free, watermarked, full resolution
2. **Seasonal preview** — 500 images from one growth stage, NDA required
3. **Live API demo** — 24-hour sandbox with test credentials

### 2.3 Data Quality Metrics

| Metric | Value | Benchmark |
|--------|-------|-----------|
| Crop classification accuracy | 94.2% (human-labeled) | Industry baseline: 82% |
| Health classification accuracy | 89.7% (human-labeled) | Industry baseline: 75% |
| IAA (crop type) | 0.92 | Industry: 0.85 |
| IAA (health status) | 0.88 | Industry: 0.80 |
| Temporal consistency | Every 7 days | Full growth cycle |
| Geolocation accuracy | ±5m (generalized to ±50m for privacy) | Industry: ±10m |
| PII detection rate | 99.2% | GDPR compliance |

---

## 3. Pricing Sheet

### 3.1 Image Pricing

| Tier | Price per Image | Min Order | Annotation Format | Support |
|------|----------------|-----------|-------------------|---------|
| **Evaluation** | Free | 50 images | COCO JSON | Email only |
| **Starter** | $0.30 | 1,000 images | COCO + YOLO | Email |
| **Professional** | $0.22 | 10,000 images | COCO + YOLO + Pascal VOC | Email + chat |
| **Enterprise** | $0.15 | 50,000 images | All formats + custom | Dedicated CSM |

**Volume discounts:**
- 10,000+ images: 15% off list price
- 50,000+ images: 30% off list price
- 100,000+ images: 50% off list price

### 3.2 License Tiers

| License | Price | Usage Rights |
|---------|-------|-------------|
| **Standard** | $0.30/image | Internal R&D, non-commercial |
| **Commercial** | $0.50/image | Production use, unlimited users |
| **Annual** | $8,000/year | Unlimited catalog access, internal + production |
| **Regional Exclusive** | $30,000/year | Exclusive rights for Malawi/Southern Africa |
| **Custom Collection** | Contact us | Bespoke field selection, custom classes |

### 3.3 Add-On Services

| Service | Price | Description |
|---------|-------|-------------|
| Phenology timeline | $0.10/image | Growth stage labels per image |
| Pest severity scoring | $0.15/image | Severity rating + treatment recommendation |
| Yield estimation model | $5,000/crop | Custom model trained on your regions |
| Weather overlay | $0.05/image | Merged weather station data per image timestamp |
| Custom class training | $2,000/class | Train annotators on custom crop/disease classes |
| Dedicated agri node | $3,500/month | Your own camera node in target district |

---

## 4. Technical API Reference

### 4.1 Authentication

```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "buyer@agrifirm.com",
  "password": "secure_password"
}

Response:
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 4.2 Dataset Search

```bash
# Search agri datasets
GET /api/v1/catalog/search?q=malawi+crop+health&category=agriculture

# Filter by crop
GET /api/v1/catalog/search?class=maize&min_count=1000

# Filter by health status
GET /api/v1/catalog/search?health_status=diseased

# Filter by growth stage
GET /api/v1/catalog/search?growth_stage=flowering
```

### 4.3 AI Inference Endpoints

```bash
# Crop classification
POST /api/v1/agri/segment
{
  "image_id": "annotation-uuid",
  "conf_threshold": 0.35,
  "segmentation_type": "crop"  # "crop" or "health"
}

# Field health analysis
POST /api/v1/agri/analyze
{
  "dataset_id": "DS-AGRI-HEALTH-DEMO-001",
  "region": "dedza"
}

# Batch processing
POST /api/v1/agri/segment/batch
{
  "image_ids": ["uuid-1", "uuid-2"],
  "segmentation_type": "health"
}
```

### 4.4 AI-Assisted Labeling (Studio)

```bash
# Auto-label an image
POST /api/v1/studio/label/ai-assist
{
  "image_id": "annotation-uuid",
  "prompt_type": "full_image",
  "return_polygons": true
}
```

### 4.5 Output Format

```json
{
  "instances": [
    {
      "class_id": 0,
      "class_name": "maize",
      "confidence": 0.94,
      "bbox": [0.12, 0.34, 0.45, 0.67],
      "mask_rle": "base64-encoded-rle",
      "polygon": [[0.12, 0.34], [0.45, 0.34], [0.45, 0.67], [0.12, 0.67]]
    }
  ]
}
```

---

## 5. Compliance & Privacy

### 5.1 Data Residency

| Aspect | Guarantee |
|--------|-----------|
| Storage location | Malawi (edge nodes) + EU (cloud backup) |
| Processing | On-device in Malawi |
| Transfer | Encrypted (TLS 1.3) Malawi → EU |
| Geolocation | Generalized to ±50m for landowner privacy |
| Retention | Raw images deleted after 24 months |

### 5.2 Consent Process

- Landowner opt-in consent recorded before field monitoring begins
- Consent can be withdrawn at any time (72-hour deletion SLA)
- No identifiable people or livestock in field-level imagery
- All faces/plates in field-access roads auto-blurred by edge AI

### 5.3 GDPR & Malawi Data Protection Act Alignment

- Lawful basis: Consent (Art. 6(1)(a))
- Privacy by design: PII auto-detection and blurring
- Right to erasure: 72-hour deletion SLA
- Data portability: COCO/YOLO/VOC export formats

---

## 6. Case Studies

### 6.1 Case Study: Pest Detection for Smallholder Insurance

**Challenge:** A crop insurance startup needed ground-truth data to train models for automated field damage assessment. Fall armyworm outbreaks were causing 30-60% yield losses in uninsured smallholder farms.

**Solution:** EdgeVision-MW provided 8,000 images of fall armyworm-infested maize fields from 15 sites across Central Malawi, with severity ratings per image.

**Result:** The insurer's damage assessment model reached 91% accuracy, enabling micro-insurance products for 5,000+ smallholder farmers. Claims processing time reduced from 14 days to 48 hours.

### 6.2 Case Study: Tobacco Yield Prediction

**Challenge:** Malawi's Tobacco Commission needed yield estimates for the 2025-26 growing season. Traditional survey methods took 3 months and covered only 60% of growing areas.

**Solution:** EdgeVision-MW deployed 3 additional agri nodes in Machinga district, capturing weekly field images through the growing cycle. Agronomist annotations included crop health, plant count, and maturity stage.

**Result:** Yield estimates were available 2 months before harvest, with 94% accuracy compared to final auction floor data. The Commission expanded the program to cover 80% of tobacco-growing areas in 2026-27.

### 6.3 Case Study: Drought Impact Assessment

**Challenge:** An international development organization needed rapid damage assessment after the 2026 dry spell. Satellite imagery had limited resolution for smallholder plots.

**Solution:** EdgeVision-MW ran a 10-day rapid collection campaign covering 200 fields across 4 districts. Images were annotated for crop stress, stunting, and leaf wilting within 72 hours.

**Result:** The organization produced a district-level drought impact report in 3 weeks (vs typical 3 months), securing emergency fertilizer distribution for 12,000 affected households.

---

## 7. Partnership Tiers

| Benefit | Explorer (Free) | Starter ($500/yr) | Professional ($5,000/yr) | Enterprise ($25,000+/yr) |
|---------|-----------------|-------------------|--------------------------|---------------------------|
| Sample data | 50 images | Full catalog, non-commercial | Full catalog, commercial | Full catalog + exclusive |
| API access | 1,000/day | 10,000/day | 50,000/day | Unlimited |
| Support | Email only | Email + chat | Dedicated CSM + Slack | 24/7 team |
| Discount | None | 10% | 20% | 40% + custom |
| Custom annotation | — | — | 5,000 images/yr | Unlimited |
| Dedicated node | — | — | — | Available |
| SLA | None | Standard | 99.9% | 99.99% |

### Research Partner Tier (Free)

Accredited universities and research institutions get free full-catalog access for non-commercial research, with publication acknowledgment required.

---

## Appendix A: Crop Taxonomy Reference

| Class ID | Crop Type | Varieties Covered |
|----------|-----------|-------------------|
| 0 | Maize | SC403, SC513, MH26, DKC90-89 |
| 1 | Tobacco | Flue-cured, Burley, Oriental |
| 2 | Rice | Faya, Kilombero, Supa |
| 3 | Groundnut | CG7, ICGV 90704, Nsinjiro |
| 4 | Cassava | Mbundumali, Sauti, Gomani |
| 5 | Soybean | Tikolore, Nasoko, Makwacha |
| 6 | Cotton | Stams Upland, Deltapine |
| 7 | Pigeon Pea | ICP 8863, Mthawajuni, Sadabo |

## Appendix B: Health Status Definitions

| Status | Description | Visual Indicators |
|--------|-------------|-------------------|
| Healthy | Optimal growth | Deep green color, erect leaves, uniform canopy |
| Water-Stressed | Moisture deficit | Wilting, leaf curling, yellowing lower leaves |
| Nutrient-Deficient | Nitrogen/phosphorus deficiency | Chlorosis, purple stems, stunted growth |
| Pest-Infested | Insect damage | Holes in leaves, frass, visible insects, defoliation |
| Diseased | Pathogen infection | Lesions, mildew, rust spots, mosaic patterns, rot |
| Senescent | Natural aging/near harvest | Yellowing, drying, leaf drop, ripe cobs/pods |

---

## Appendix C: Contact Information

| Role | Name | Email | Phone |
|------|------|-------|-------|
| Agriculture Lead | Agri Team | agri@edgevision.mw | +265 999 000 200 |
| Sales | Sales Team | sales@edgevision.mw | +265 999 000 100 |
| Technical | CTO | tech@edgevision.mw | +265 999 000 101 |
| Compliance | DPO | dpo@edgevision.mw | +265 999 000 102 |
