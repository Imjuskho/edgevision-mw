# EdgeVision-MW Annotator Onboarding Guide

**Version:** 1.0.0
**Last Updated:** 2026-07-25
**Target Audience:** New annotators joining the EdgeVision labeling team in Lilongwe

---

## Table of Contents

1. [Welcome and Overview](#1-welcome-and-overview)
2. [Job Description](#2-job-description)
3. [Wage Structure](#3-wage-structure)
4. [Labeling Station Setup](#4-labeling-station-setup)
5. [Training Curriculum](#5-training-curriculum-2-day-program)
6. [Quality Standards](#6-quality-standards)
7. [Inter-Annotator Agreement (IAA)](#7-inter-annotator-agreement-iaa)
8. [Payment Process](#8-payment-process)
9. [Code of Conduct](#9-code-of-conduct)
10. [Support and Escalation](#10-support-and-escalation)

---

## 1. Welcome and Overview

Welcome to the EdgeVision-MW annotation team. You are part of a project building Africa's first large-scale edge-AI training dataset for autonomous driving, urban planning, and public safety.

**What you will do:** Label images captured by our network of cameras across Lilongwe. You will identify and draw bounding boxes around vehicles, pedestrians, cyclists, traffic signs, and other objects.

**Why it matters:** Your labels train AI systems that will improve road safety, help cities plan infrastructure, and support research across the continent. Every accurate box you draw saves lives.

**Your team:**
- **Annotators:** You — draw bounding boxes on images
- **QA Reviewers:** Check your work for quality and consistency
- **Team Lead:** Manages assignments, payments, and training
- **Technical Support:** Helps with tool issues and system problems

---

## 2. Job Description

### Role: Image Annotation Specialist

**Reports to:** Annotation Team Lead
**Location:** EdgeVision labeling station, Lilongwe (or remote with stable internet)
**Type:** Part-time / Full-time (flexible hours, 20-40 hrs/week)
**Duration:** Ongoing, with monthly performance reviews

### Responsibilities

1. **Label images** — Draw accurate bounding boxes around objects in street-view images
2. **Classify objects** — Assign correct category labels (car, person, motorcycle, etc.)
3. **Flag quality issues** — Report blurry, dark, or unusable images
4. **Meet targets** — Complete assigned batches within deadline
5. **Maintain quality** — Achieve >90% QA pass rate
6. **Communicate** — Flag issues, ask questions, participate in team meetings

### What You Need

| Requirement | Details |
|-------------|---------|
| Education | O-Level minimum; A-Level or diploma preferred |
| Computer skills | Basic: mouse, keyboard, web browser |
| Eyesight | Normal or corrected-to-normal vision |
| Languages | Chichewa (fluent); English (conversational) |
| Internet | Stable connection (for remote work) |
| Commitment | Minimum 20 hours/week |

### What You Do NOT Need

- Programming skills
- AI/ML knowledge
- Previous annotation experience (we train you)
- Your own computer (we provide equipment at the station)

---

## 3. Wage Structure

### 3.1 Pay Rates

| Tier | Rate per Image | Requirements | Typical Output |
|------|----------------|--------------|----------------|
| **Trainee** | $0.15/image | First 2 weeks (during training) | 200-300 images/day |
| **Junior** | $0.20/image | QA score ≥ 85%, < 1,000 images completed | 300-400 images/day |
| **Standard** | $0.25/image | QA score ≥ 90%, ≥ 1,000 images completed | 400-500 images/day |
| **Senior** | $0.30/image | QA score ≥ 95%, ≥ 5,000 images completed, IAA ≥ 0.85 | 500-600 images/day |
| **Lead** | $0.35/image | Senior + training new annotators, QA review duties | 300-400 images/day |

### 3.2 Monthly Earnings Estimate

| Tier | Images/Day (22 work days) | Monthly Earnings (USD) | Monthly Earnings (MWK @ 1,700) |
|------|--------------------------|------------------------|-------------------------------|
| Trainee | 200 × 22 = 4,400 | $660 | MWK 1,122,000 |
| Junior | 300 × 22 = 6,600 | $1,320 | MWK 2,244,000 |
| Standard | 450 × 22 = 9,900 | $2,475 | MWK 4,207,500 |
| Senior | 550 × 22 = 12,100 | $3,630 | MWK 6,171,000 |

**Note:** Minimum wage in Malawi is MWK 50,000/month (~$29). EdgeVision annotators earn 20-120× the minimum wage.

### 3.3 Bonuses

| Bonus | Amount | Trigger |
|-------|--------|---------|
| Perfect QA week | $10 bonus | 100% QA pass rate for 5+ consecutive days |
| Batch completion | $5 bonus | Complete assigned batch ahead of deadline |
| Referral bonus | $25 | Refer a new annotator who passes training |
| Monthly top performer | $50 | Highest volume + quality in the month |
| Accuracy champion | $75 | Highest IAA score among all annotators |

### 3.4 Deductions

| Deduction | Rate | Notes |
|-----------|------|-------|
| QA failures | $0.05/image rework | Images rejected by QA requiring redo |
| Missed deadlines | 10% of batch value | Late batch completion |
| No-show | 0 (warning first) | Unexcused absence; 3 no-shows = termination |

---

## 4. Labeling Station Setup

### 4.1 Hardware (Station)

Each labeling station includes:

| Component | Specification | Purpose |
|-----------|---------------|---------|
| Monitor | 27" 1080p IPS display | Image viewing (color accuracy matters) |
| Mouse | Logitech MX Master 3 | Precision drawing |
| Keyboard | Standard USB | Shortcuts and data entry |
| Headset | Optional | For training videos |
| Workstation | Shared desktop PC | Running the annotation tool |
| Internet | 10Mbps fiber (shared) | Image loading and submission |
| UPS | 1500VA | Power backup (load shedding: 2-4hr/day in Lilongwe) |
| Desk + Chair | Adjustable | Ergonomic workstation |

### 4.2 Hardware (Remote/Work-From-Home)

If approved for remote work:

| Component | Specification |
|-----------|---------------|
| Your own computer | Any Windows/Mac/Linux PC with Chrome or Firefox |
| Monitor | Recommended: 24" or larger for comfortable viewing |
| Internet | Minimum 5Mbps download, stable |
| Mouse | Required (trackpad not sufficient for accurate bounding boxes) |
| Power | Your own power solution (inverter, generator, or solar) |

**Note:** Remote annotators must demonstrate stable internet for 3 consecutive test days before approval.

### 4.3 Software Setup

```
BROWSER SETUP (Chrome recommended)
===================================
1. Open Chrome
2. Go to: https://annotate.edgevision.mw
3. Log in with credentials from Team Lead
   Email: [your-email]@edgevision.mw
   Password: [provided in welcome email]
4. You will see the Annotation Dashboard

BROWSER EXTENSIONS (Required)
===================================
- AdBlock: Disable (blocks our tool)
- Dark Reader: Disable (affects image colors)
- Any VPN: Disable (triggers security alerts)
```

### 4.4 Annotation Tool Overview

```
┌─────────────────────────────────────────────────────────────┐
│  EdgeVision Annotation Tool                          [?] [≡]│
├─────────────────────────────────────────────────────────────┤
│ Batch: BATCH-LIL-2026-07-25-001    Progress: 47/200 (23%) │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░░░░░░│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │              IMAGE DISPLAY AREA                     │   │
│  │                                                     │   │
│  │     ┌──────────┐                                    │   │
│  │     │  CAR     │    ┌──────────┐                    │   │
│  │     │  #1      │    │ PERSON   │                    │   │
│  │     └──────────┘    │ #2       │                    │   │
│  │                     └──────────┘                    │   │
│  │  ┌──────────┐                                       │   │
│  │  │CYCLIST #3│                                       │   │
│  │  └──────────┘                                       │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ TOOLS:  [□ Box] [○ Polygon] [◇ Point] [~ Line]  │ Classes │
│                                                     │ ▼ Car  │
│ ┌───────────────────────────────────────────────┐   │   Person│
│ │ Label Panel                                   │   │   Cycle │
│ │ Object #1: Car                                │   │   Sign  │
│ │   Confidence: [High ▼]                        │   │   Road  │
│ │   Occlusion: [None ▼]                         │   │         │
│ │   Truncated: [No ▼]                           │   │         │
│ └───────────────────────────────────────────────┘   │         │
│                                                     │         │
├─────────────────────────────────────────────────────┴────────┤
│ [◄ Previous]  [Skip ▶▶]  [Flag ⚑]  [Submit ✓]    Image 47 │
└─────────────────────────────────────────────────────────────┘
```

### 4.5 Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `B` | Draw bounding box |
| `Ctrl+Z` | Undo last action |
| `Ctrl+S` | Save (auto-saves every 30 seconds) |
| `→` | Next image |
| `←` | Previous image |
| `Space` | Accept and next |
| `F` | Flag image for review |
| `1-9` | Quick-select class label |
| `Tab` | Cycle between objects in image |
| `Delete` | Delete selected object |
| `Esc` | Cancel current drawing |

---

## 5. Training Curriculum (2-Day Program)

### Day 1: Tool Usage and Basic Labeling

**Morning (9:00 - 12:30)**

| Time | Topic | Activities |
|------|-------|------------|
| 9:00-9:30 | Welcome and introductions | Meet team, tour facility |
| 9:30-10:00 | What is EdgeVision? | Project overview, why this matters |
| 10:00-10:30 | Annotation tool walkthrough | Login, navigate interface, use tools |
| 10:30-11:00 | Drawing bounding boxes | Hands-on: draw boxes on 10 practice images |
| 11:00-11:15 | Break | Tea/coffee |
| 11:15-11:45 | Object classes | Learn all 12 classes, when to use each |
| 11:45-12:30 | Practice session 1 | Label 20 images with instructor guidance |

**Afternoon (13:30 - 17:00)**

| Time | Topic | Activities |
|------|-------|------------|
| 13:30-14:00 | Quality expectations | See good vs. bad examples |
| 14:00-14:30 | Common mistakes | Review top 10 beginner errors |
| 14:30-15:00 | Edge cases | Partial objects, crowds, night scenes |
| 15:00-15:15 | Break | Tea/coffee |
| 15:15-16:00 | Practice session 2 | Label 30 images independently |
| 16:00-16:30 | Self-review | Compare your labels to reference |
| 16:30-17:00 | Day 1 Q&A | Questions, feedback, homework assignment |

**Homework:** Label 50 images at home (or station) before Day 2

### Day 2: Quality Standards and IAA

**Morning (9:00 - 12:30)**

| Time | Topic | Activities |
|------|-------|------------|
| 9:00-9:30 | Homework review | Instructor reviews your 50 images |
| 9:30-10:00 | Inter-Annotator Agreement (IAA) | What IAA means, why it matters |
| 10:00-10:30 | IoU explained | Intersection over Union: the math behind accuracy |
| 10:30-11:00 | Hands-on IoU exercise | Calculate IoU for 5 example pairs |
| 11:00-11:15 | Break | Tea/coffee |
| 11:15-11:45 | Quality tiers | Junior → Standard → Senior progression |
| 11:45-12:30 | Practice session 3 | Label 30 images, paired with a peer |

**Afternoon (13:30 - 17:00)**

| Time | Topic | Activities |
|------|-------|------------|
| 13:30-14:00 | QA process | How QA reviewers check your work |
| 14:00-14:30 | Rework process | How to fix rejected images |
| 14:30-15:00 | Payment and earnings | Wage structure, payment schedule |
| 15:00-15:15 | Break | Tea/coffee |
| 15:15-16:00 | Final assessment | Label 50 images (graded) |
| 16:00-16:30 | Results and feedback | Individual results, improvement areas |
| 16:30-17:00 | Welcome to the team | Credentials, first batch assignment |

### Training Materials Provided

- Laminated quick-reference card (classes + shortcuts)
- EdgeVision Annotator Handbook (printed, 20 pages)
- Access to online training module (video + quizzes)
- Discord/WhatsApp group for questions and support

---

## 6. Quality Standards

### 6.1 Object Classes

| ID | Class | Description | When to Label |
|----|-------|-------------|---------------|
| 0 | Car | Sedan, SUV, hatchback, wagon | All 4-wheel passenger vehicles |
| 1 | Truck | Lorry, pickup, van, bus | Commercial vehicles, buses, pickups |
| 2 | Motorcycle | Motorbike, scooter, moped | All 2-wheel motorized vehicles |
| 3 | Bicycle | Pedal bicycle | Non-motorized 2-wheel |
| 4 | Person | Any human figure | Walking, standing, sitting, cycling |
| 5 | Cyclist | Person riding bicycle | Person on bicycle (label person + bicycle separately) |
| 6 | Traffic Light | Vehicle traffic signal | Red/yellow/green signals |
| 7 | Traffic Sign | Road sign, billboard | Speed limit, stop, yield, directional |
| 8 | Road Marking | Lane lines, crosswalk | Painted markings on road surface |
| 9 | Animal | Dog, goat, cattle | Non-human moving objects on road |
| 10 | Obstacle | Debris, pothole, barrier | Hazards on road surface |
| 11 | Other | Anything else of interest | Fallback for important unlabeled objects |

### 6.2 Bounding Box Rules

```
RULE 1: TIGHT FIT
├── Box should fit tightly around the object
├── Include all visible parts (mirrors, antennas, wheels)
├── Do NOT include shadow
└── Do NOT include large gaps between box edge and object

RULE 2: FULLY VISIBLE vs PARTIALLY VISIBLE
├── Fully visible: Entire object in frame → label normally
├── Partially visible: Object cut by image edge → label visible portion
│   └── Mark as "Truncated: Yes" in label panel
├── Heavily occluded: >50% hidden by another object
│   ├── Label if you can determine the class
│   └── Mark as "Occlusion: Heavy"
└── Not visible: Object completely hidden → do not label

RULE 3: MINIMUM SIZE
├── Label objects > 10×10 pixels (roughly 1% of image)
├── Do NOT label tiny distant specks
├── If in doubt, label it (QA can remove)
└── Group of tiny objects (crowd) → 1 box per visible person

RULE 4: CLASSIFICATION ACCURACY
├── Car vs Truck: If unsure, ask "would this carry cargo?" → Truck
├── Person vs Cyclist: Cyclist = person actively riding bicycle
├── Traffic Sign vs Billboard: Sign = government traffic control
└── Obstacle vs Road Marking: Marking = paint; Obstacle = physical object
```

### 6.3 Quality Scoring

Each image you label gets a QA score from 0-100:

| Score | Rating | What It Means |
|-------|--------|---------------|
| 95-100 | Excellent | Near-perfect, publishable |
| 90-94 | Good | Minor issues, acceptable |
| 85-89 | Fair | Some errors, needs rework |
| 80-84 | Poor | Multiple errors, rework required |
| <80 | Fail | Significant errors, training required |

### 6.4 Common Mistakes

| # | Mistake | How to Fix |
|---|---------|------------|
| 1 | Box too large (includes background) | Shrink box to object edges only |
| 2 | Missing objects | Scan image systematically: left→right, top→bottom |
| 3 | Wrong class | Review class definitions; when in doubt, check handbook |
| 4 | Double-labeling same object | Check existing labels before drawing new box |
| 5 | Box on shadow | Shadow is NOT part of the object |
| 6 | Missing cyclists | Cyclist = person + bicycle = TWO separate boxes |
| 7 | Ignoring truncated objects | If >25% visible, label it and mark truncated |
| 8 | Poor box alignment | Boxes must be axis-aligned (horizontal/vertical), not rotated |

---

## 7. Inter-Annotator Agreement (IAA)

### 7.1 What is IAA?

IAA measures how well two annotators agree on the same image. It's the core quality metric for our dataset.

**The math (simplified):** For each object in an image, compare the bounding boxes drawn by two annotators. If their boxes overlap by ≥50% (IoU ≥ 0.5) AND they agree on the class, that's a "match." IAA = (number of matches) / (total objects).

### 7.2 IAA Thresholds

| IAA Score | Rating | Career Impact |
|-----------|--------|---------------|
| ≥ 0.90 | Excellent | Fast-track to Senior tier |
| 0.80-0.89 | Good | Standard progression |
| 0.70-0.79 | Fair | Additional training recommended |
| 0.60-0.69 | Poor | Mandatory retraining before new assignments |
| < 0.60 | Fail | Probation; 2 consecutive fails = termination |

### 7.3 How IAA is Calculated

```
Example: Image with 5 objects

Annotator A draws: [Car#1, Car#2, Person#1, Person#2, Truck#1]
Annotator B draws: [Car#1, Car#2, Person#1, Person#3, Truck#1]

Matching (IoU ≥ 0.5 and same class):
  Car#1 ↔ Car#1  ✓  (IoU = 0.92)
  Car#2 ↔ Car#2  ✓  (IoU = 0.88)
  Person#1 ↔ Person#1  ✓  (IoU = 0.76)
  Truck#1 ↔ Truck#1  ✓  (IoU = 0.95)

Non-matching:
  Person#2 (A only) — missed by B
  Person#3 (B only) — extra detection

IAA = 4 matches / 6 total unique objects = 0.67
(Because 5 + 5 - 4 = 6 unique objects)

Actually, the standard formula uses:
  IAA = 2 × matches / (objects_A + objects_B) = 2 × 4 / (5 + 5) = 0.80
```

### 7.4 Improving Your IAA

1. **Review the reference labels** before starting a batch — they show what "correct" looks like
2. **Be consistent** — if you labeled it one way yesterday, label it the same way today
3. **Don't over-label** — only label clear, visible objects
4. **Check edge cases** — partial objects, night scenes, rain
5. **Ask questions** — when unsure, ask in the team chat
6. **Review your rejections** — QA feedback shows exactly what you got wrong

---

## 8. Payment Process

### 8.1 Payment Schedule

| Item | Frequency | Date |
|------|-----------|------|
| Image count | Real-time | Visible on dashboard |
| QA review | Within 48 hours of submission | Automatic |
| Weekly earnings summary | Every Friday | Emailed to you |
| Payment processing | Every Monday | Transferred to mobile money |
| Payment receipt | Every Monday | SMS + email |

### 8.2 Payment Method

All payments are made via **mobile money** in **Malawian Kwach (MWK)**:

| Option | Provider | Details |
|--------|----------|---------|
| **Airtel Money** | Airtel Malawi | Preferred — fastest processing |
| **TNM Mpamba** | TNM Malawi | Alternative if no Airtel line |
| **Bank transfer** | Any Malawian bank | For amounts > MWK 500,000 (monthly) |

### 8.3 Setting Up Mobile Money

```
STEP 1: Register your mobile money account
==========================================
- Airtel Money: Dial *778# → Follow registration prompts
- TNM Mpamba: Dial *444# → Follow registration prompts
- You need: National ID or passport, phone number

STEP 2: Provide details to Team Lead
=====================================
- Full name (must match mobile money registration)
- Mobile money number
- Provider (Airtel or TNM)
- National ID number (for tax records)

STEP 3: Verification
=====================================
- Team Lead sends MWK 1 test payment
- Confirm receipt
- Your account is now active for payments
```

### 8.4 Payment Calculation Example

```
Week: 14 July - 18 July 2026

Images submitted:           2,200
QA pass rate:               94%
Rejections requiring rework: 132

Earnings calculation:
  Approved images:          2,068 × $0.25 = $517.00
  Rework images:              132 × $0.00 = $0.00 (no pay for rework)
  Perfect QA week bonus:    $10.00

  Gross earnings:           $527.00
  MWK equivalent:           MWK 895,900 (@ 1,700 MWK/USD)

  Sent to Airtel Money:     MWK 895,900
```

### 8.5 Tax Information

- EdgeVision withholds 16.5% withholding tax on payments > MWK 100,000/month
- Tax is remitted to MRA (Malawi Revenue Authority) on your behalf
- You will receive a quarterly tax certificate
- Keep this for your annual tax return
- **Example:** MWK 895,900 → MWK 147,824 tax → MWK 748,076 net payment

---

## 9. Code of Conduct

### 9.1 Professional Standards

1. **Arrive on time** for scheduled shifts (if station-based)
2. **Complete assigned batches** before starting new ones
3. **Maintain quality** — speed without accuracy wastes everyone's time
4. **Communicate proactively** — tell your Team Lead if you'll be late or absent
5. **Keep credentials private** — never share your login with anyone
6. **Respect the data** — images may contain identifiable people; treat with dignity

### 9.2 Data Privacy

- You may see images of real people going about their lives
- **DO NOT** download, share, or screenshot any images
- **DO NOT** attempt to identify people in images
- **DO NOT** discuss specific images outside the annotation tool
- All images are processed under consent agreements (see EdgeVision privacy policy)
- Violations of data privacy are grounds for immediate termination

### 9.3 Grounds for Termination

| Offense | Consequence |
|---------|-------------|
| Sharing login credentials | Immediate termination |
| Downloading/sharing images | Immediate termination + legal action |
| Consistent low quality (< 80% for 2+ weeks) | Retraining → termination if no improvement |
| 3 unexcused absences in a month | Warning → termination |
| Harassment of team members | Immediate termination |
| Fraud (claiming payment for work not done) | Immediate termination + legal action |

---

## 10. Support and Escalation

### 10.1 Support Channels

| Issue | Channel | Response Time |
|-------|---------|---------------|
| Tool not loading | #tech-support (WhatsApp group) | < 1 hour |
| Bug in annotation tool | #tech-support | < 4 hours |
| Image quality issues | #quality-questions | < 2 hours |
| Payment inquiry | Email: payments@edgevision.mw | < 24 hours (business days) |
| Training question | #training | < 4 hours |
| Personal issue (absence, etc.) | Direct message to Team Lead | < 2 hours |
| Urgent (account compromised) | Phone: +265 999 000 111 | Immediate |

### 10.2 Escalation Path

```
Level 1: Team Lead
├── Daily questions, assignments, payments
└── Response: < 2 hours

Level 2: Operations Manager
├── Disputes, policy questions, equipment issues
└── Response: < 24 hours

Level 3: Country Director
├── Serious complaints, contract issues, legal
└── Response: < 48 hours
```

### 10.3 Frequently Asked Questions

**Q: What if I lose internet during a session?**
A: Your work auto-saves every 30 seconds. When you reconnect, you'll resume where you left off. No work is lost.

**Q: What if I spot a serious issue in an image (accident, crime)?**
A: Flag the image using the Flag button. It will be escalated to the operations team. Do not share the image externally.

**Q: Can I work from home?**
A: Yes, after 2 weeks at the station and passing a remote-work assessment (internet speed test + 1-day trial).

**Q: What if I disagree with a QA rejection?**
A: Submit an appeal in the tool (Appeal button on rejected image). A senior reviewer will re-evaluate within 48 hours.

**Q: How do I track my earnings?**
A: The Dashboard shows your daily/weekly/monthly stats: images completed, QA score, earnings estimate, and tier status.

**Q: What happens if I need to take leave?**
A: Notify your Team Lead at least 2 days in advance. No penalty for planned leave. Unplanned leave: notify as early as possible.

---

## Appendix A: Annotator Registration Form

```
EDGEVISION-MW ANNOTATOR REGISTRATION
=====================================

Full Name: _________________________________
National ID: _______________________________
Phone Number: ______________________________
Email: ____________________________________
Date of Birth: _____________________________
Address: ___________________________________
City: ______________________________________

Mobile Money Provider: [ ] Airtel Money  [ ] TNM Mpamba
Mobile Money Number: _______________________

Education Level:
[ ] O-Level  [ ] A-Level  [ ] Diploma  [ ] Degree  [ ] Other: ______

Computer Experience:
[ ] Basic (mouse, keyboard, browser)
[ ] Intermediate (some software experience)
[ ] Advanced (programming, design)

Availability:
[ ] Full-time (40 hrs/week)
[ ] Part-time (20 hrs/week)
[ ] Weekend only

Preferred Work Location:
[ ] EdgeVision Station, Lilongwe
[ ] Remote (work from home)

Emergency Contact:
Name: _________________ Phone: ______________

Signature: _________________ Date: ____________
```

---

## Appendix B: Class Reference Card (Laminated Quick-Reference)

```
┌─────────────────────────────────────────────────────┐
│           EDGEVISION CLASS REFERENCE                │
├─────┬───────────────┬───────────────────────────────┤
│  0  │ Car           │ Sedan, SUV, hatchback         │
│  1  │ Truck         │ Lorry, pickup, bus, van        │
│  2  │ Motorcycle    │ Motorbike, scooter, moped      │
│  3  │ Bicycle       │ Pedal bicycle                   │
│  4  │ Person        │ Any human figure                │
│  5  │ Cyclist       │ Person riding bicycle (2 boxes) │
│  6  │ Traffic Light │ Vehicle signals                 │
│  7  │ Traffic Sign  │ Road signs, speed limits        │
│  8  │ Road Marking  │ Lane lines, crosswalks          │
│  9  │ Animal        │ Dog, goat, cattle               │
│ 10  │ Obstacle      │ Debris, pothole, barrier        │
│ 11  │ Other         │ Important unlabeled objects     │
├─────┴───────────────┴───────────────────────────────┤
│ SHORTCUTS: B=Box  S=Save  F=Flag  →=Next  ←=Prev   │
│            Ctrl+Z=Undo  Tab=Cycle  Del=Delete        │
├─────────────────────────────────────────────────────┤
│ QUALITY: Tight box ✓  Include mirror/wheels ✓       │
│          No shadow ✓   Label truncated ✓            │
│          10px minimum ✓  Axis-aligned ✓             │
└─────────────────────────────────────────────────────┘
```
