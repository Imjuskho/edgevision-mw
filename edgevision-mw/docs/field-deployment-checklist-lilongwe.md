# EdgeVision-MW Field Deployment Checklist — Lilongwe

**Version:** 1.0.0
**Last Updated:** 2026-07-25
**Deployment Sites:** Lilongwe District, Malawi (10 initial nodes)

---

## Table of Contents

1. [Hardware Procurement Timeline](#1-hardware-procurement-timeline)
2. [Enclosure Fabrication Specs](#2-enclosure-fabrication-specs)
3. [Solar Installation Guide](#3-solar-installation-guide)
4. [4G Modem Configuration](#4-4g-modem-configuration)
5. [First Boot Procedure](#5-first-boot-procedure)
6. [Site Selection Criteria](#6-site-selection-criteria)
7. [Anti-Theft and Security](#7-anti-theft-and-security)
8. [Maintenance Schedule](#8-maintenance-schedule)

---

## 1. Hardware Procurement Timeline

### 1.1 Bill of Materials (Per Node)

| # | Component | Specification | Qty | Est. Unit Cost (USD) | Source | Lead Time |
|---|-----------|---------------|-----|---------------------|--------|-----------|
| 1 | NVIDIA Jetson Orin Nano Developer Kit | 8GB, 40 TOPS | 1 | $249 | NVIDIA Store / Seeed Studio | 2-4 weeks |
| 2 | Industrial microSD card | 256GB A2 V30 (SanDisk Extreme) | 1 | $35 | Amazon / Jumia | 1-2 weeks |
| 3 | Raspberry Pi Camera Module 3 | 12MP, IMX708, wide-angle | 1 | $25 | Adafruit / Seeed | 2-3 weeks |
| 4 | Camera enclosure lens window | 25mm optical glass, AR-coated | 1 | $8 | AliExpress | 3-4 weeks |
| 5 | Huawei E3372-608 4G modem | LTE Cat 4, 150Mbps | 1 | $45 | Jumia Malawi / Amazon | 1-2 weeks |
| 6 | MTN SIM card (prepaid) | IoT data plan | 1 | $5 | MTN Service Centre, Lilongwe | Same day |
| 7 | 100W monocrystalline solar panel | 18V, MC4 connectors | 1 | $80 | SolarSpa Malawi / Jumia | 1-2 weeks |
| 8 | 12V 100Ah LiFePO4 battery | BMS included, IP65 | 1 | $180 | BatteryMalawi / AliExpress | 2-4 weeks |
| 9 | MPPT charge controller | 20A, 12V/24V auto | 1 | $35 | SolarSpa Malawi | 1 week |
| 10 | DC-DC buck converter | 12V→5V/5A, 12V→19V/3A | 1 | $12 | AliExpress | 2-3 weeks |
| 11 | Aluminum enclosure | Custom (see §2) | 1 | $60 | Local fabrication (Lilongwe) | 2 weeks |
| 12 | Anti-tamper bolts | M6 Torx security, stainless | 4 | $8 | Hardware store, Lilongwe | Same day |
| 13 | Cable glands | PG7/PG9, IP68 | 4 | $5 | Hardware store | Same day |
| 14 | Grounding rod | 1.5m copper-clad steel | 1 | $15 | Electrical supplier | 1 week |
| 15 | Mounting hardware | Galvanized steel bracket, U-bolts | 1 set | $20 | Local fabrication | 1 week |

**Per-node total: ~$777**
**10-node deployment total: ~$7,770** (plus spares: add 15% = **~$8,935**)

### 1.2 Procurement Timeline (Gantt)

```
Week 1-2:  Order Jetson Orin Nano + cameras + modems (international)
           Source solar panels + batteries locally
           Engage fabrication shop for enclosures

Week 2-3:  Order microSD cards, DC-DC converters, cable glands (international)
           Purchase grounding rods, bolts locally
           MTN SIM registration (bring national ID)

Week 3-4:  Enclosure fabrication begins (2 weeks)
           Solar panel and battery delivery
           Begin SD card preparation (see §5.1)

Week 4-5:  International shipments arrive
           Flash all SD cards with EdgeVision firmware
           Assemble and bench-test each node

Week 5-6:  Enclosures delivered
           Install hardware into enclosures
           Final bench-test all 10 nodes

Week 6-7:  Site survey and installation (2-3 nodes/day)
           End-to-end verification per node
```

### 1.3 Where to Buy in Malawi

| Item | Local Source | Contact |
|------|-------------|---------|
| Solar panels | SolarSpa Malawi | +265 999 123 456, Area 4, Lilongwe |
| LiFePO4 batteries | BatteryMalawi | +265 888 765 432, Kanengo |
| MTN SIM cards | MTN Service Centre | City Centre, Lilongwe |
| Metal fabrication | Kambuzi Metal Works | +265 991 234 567, Mchesi |
| Electrical supplies | electrical_wholesale_lilongwe | Old Town, Lilongwe |
| Mounting hardware | Hardware store (any) | Mchesi / Area 1 |

### 1.4 Import Notes

- **Customs duty:** Computer equipment (Jetson) is 15% import duty + 16.5% VAT in Malawi
- **Proforma invoice:** Required for customs clearance; get from supplier
- **Shipping:** DHL Express to Lilongwe (4-7 business days from Shenzhen)
- **Total import cost:** Add ~30% to international order value for duties + shipping

---

## 2. Enclosure Fabrication Specs

### 2.1 Dimensions

```
External:  320mm (W) × 240mm (H) × 180mm (D)
Internal:  300mm (W) × 220mm (H) × 160mm (D)
Wall:      3mm aluminum (5052-H32)
```

### 2.2 Material Specification

| Component | Material | Reason |
|-----------|----------|--------|
| Main body | 3mm 5052-H32 aluminum | Corrosion resistant, lightweight |
| Lens window | 25mm BK7 optical glass, AR-coated | UV stable, scratch resistant |
| Gaskets | EPDM rubber, 3mm | UV + water resistant, IP65 |
| Mounting bracket | 3mm galvanized steel | Structural strength |

### 2.3 Drawing

```
         ┌─────────────────────────────────┐
         │            TOP VIEW             │
         │                                 │
         │   ┌───────┐    ┌──────────┐    │
         │   │Camera │    │ 4G Ant.  │    │
         │   │Module │    │  SMA     │    │
         │   └───────┘    └──────────┘    │
         │                                 │
         │   ┌─────────────────────────┐  │
         │   │      Jetson Orin Nano   │  │
         │   │   ┌───────┐ ┌───────┐  │  │
         │   │   │ SD    │ │ USB   │  │  │
         │   │   │ Card  │ │ 4G    │  │  │
         │   │   └───────┘ └───────┘  │  │
         │   └─────────────────────────┘  │
         │                                 │
         │   ┌──────┐ ┌──────┐ ┌───────┐  │
         │   │Buck  │ │MPPT  │ │Battery│  │
         │   │Conv. │ │Ctrl. │ │Comp.  │  │
         │   └──────┘ └──────┘ └───────┘  │
         │                                 │
         └─────────────────────────────────┘

         FRONT (Lens Window Side)
         ┌─────────────────────────────────┐
         │         ┌───────────┐           │
         │         │   LENS    │           │
         │         │  WINDOW   │           │
         │         │  25mm dia │           │
         │         └───────────┘           │
         │                                 │
         │  [LED] [LED] [LED]              │
         │   Power  Net   Err              │
         └──────┬──────────────┬───────────┘
                │   CABLE      │
                │   GLANDS     │
                └──────────────┘
              Solar + Antenna + Ground
```

### 2.4 Fabrication Notes for Kambuzi Metal Works

```markdown
SPECS FOR ENCLOSE FABRICATION (10 UNITS)
-----------------------------------------

Material: 3mm aluminum sheet (5052 grade preferred)
Surface: Powder-coated matte black (RAL 9005)
Sealing: EPDM gasket groove (3mm × 3mm) around lid
Lid: 4× M6 Torx security bolts (tamper-resistant)
Cable entry: 3× PG9 glands (bottom), 1× PG7 gland (side)
Lens window: 25mm hole, counter-bored for glass + O-ring
Mounting: 2× M8 threaded inserts on back panel (for pole mount)
LED windows: 3× 5mm holes with clear silicone seals
Drain: 1× M5 weep hole (bottom, screened)
Thermal: 2× 80mm fan cutouts (top and bottom for convection)
Labels: Laser-etched serial number + "EDGEVISION" on lid

DELIVERY: 2 weeks from deposit
QUANTITY: 10 units + 2 spares
```

### 2.5 Thermal Management

The enclosure must dissipate ~15W (Jetson Orin Nano + peripherals):
- **Passive mode:** Enclosure aluminum body acts as heatsink
- **Active mode:** Two 80mm fans activate at CPU temp > 70°C
- **Operating range:** -10°C to +50°C (Malawi ambient: 15°C–35°C)
- **Ventilation:** Bottom intake, top exhaust (chimney effect)
- **Sun shielding:** Mount enclosure in shade; if not possible, add reflective white coating to top panel

---

## 3. Solar Installation Guide

### 3.1 Power Budget

| Component | Voltage | Current | Power |
|-----------|---------|---------|-------|
| Jetson Orin Nano (active) | 5V/19V | 2.5A/1.5A | 12.5-28.5W |
| Jetson Orin Nano (idle) | 5V/19V | 0.5A/0.3A | 2.5-5.7W |
| 4G modem | 5V | 0.5A | 2.5W |
| Camera module | 3.3V | 0.3A | 1W |
| Charging losses | — | — | 3W |
| **Peak total** | — | — | **35W** |
| **Average (12hr/day)** | — | — | **~15W** |

Daily energy requirement: 15W × 24hr = **360Wh/day** (with capture schedule active 12hr)

### 3.2 Solar Panel Sizing

```
Required daily energy: 360Wh
Panel output (Lilongwe): 100W × 4.5 peak sun hours = 450Wh/day (best case)
                        100W × 2.5 peak sun hours = 250Wh/day (worst case, rainy season)

Safety factor: 1.5×
Required panel: 360Wh × 1.5 / 2.5h = 216W minimum (worst case)
Recommendation: 200W (2× 100W panels in parallel) or single 200W panel
```

**Recommended: 2× 100W monocrystalline panels** (easier to transport, less wind load)

### 3.3 Panel Installation

**Optimal angle for Lilongwe (13.96°S latitude):**
- **Year-round fixed:** 15° from horizontal (slightly steeper than latitude)
- **Optimal seasonal:** 5° (Oct-Mar, sun overhead) to 25° (Apr-Sep, sun north)
- **Azimuth:** True north (0°) — panels must face north in Southern Hemisphere

```
Pole Mount Cross-Section:
                          ╔═══════════════╗
                         ╱║   SOLAR PANEL  ╲
                        ╱ ║   100W × 2     ╲
                       ╱  ╚═══════════════╝  ╲
                      ╱     15° from horiz.    ╲
                     ╱                          ╲
                    ╱  ┌─────────────────────┐   ╲
                   ╱   │   MOUNTING BRACKET  │    ╲
                  ╱    │   Galvanized steel   │     ╲
                 ╱     └──────────┬──────────┘      ╱
                ╱                  │                 ╱
               ╱                   │                ╱
              ╱                    │               ╱
             ╱                     │              ╱
            ╱     ┌────────────────┼────────┐    ╱
           ╱      │    UTILITY POLE │       │   ╱
          ╱       │    3m galv.     │       │  ╱
         ╱        │    steel        │       │ ╱
        ╱         │                 │       │╱
       ╱          │  ┌──────┐      │       │
      ╱           │  │BATT. │      │       │
     ╱            │  │COMP. │      │       │
    ╱             │  └──────┘      │       │
   ╱              │                 │       │
  ╱               └─────────────────┘       │
 ╱                                          │
╱───────────────────────────────────────────┘
GROUND LEVEL
```

### 3.4 Battery Specification

| Parameter | Value |
|-----------|-------|
| Chemistry | LiFePO4 (Lithium Iron Phosphate) |
| Voltage | 12V nominal (12.8V full, 10.0V cutoff) |
| Capacity | 100Ah (1,280Wh) |
| Autonomy | 1,280Wh / 15W = 85 hours (~3.5 days without sun) |
| BMS | Built-in: overcharge, over-discharge, over-current, short circuit |
| Operating temp | -20°C to +60°C |
| Cycle life | 3,000+ cycles at 80% DoD |

### 3.5 Battery Placement

```
Mounting location: Inside enclosure, bottom tray
Orientation: Terminals up (for safety)
Securing: Stainless steel strap + foam padding
Ventilation: 50mm clearance around battery
Temperature: Avoid direct sun; enclosure should be in shade
Wiring: 6 AWG cable, 30A fuse on positive terminal
```

### 3.6 Grounding

```
Grounding System:
├── Rod: 1.5m copper-clad steel, driven 1.4m into earth
├── Resistance target: <25Ω (measure with multimeter)
├── Connection: 6 AWG bare copper wire from enclosure chassis to rod
├── Lightning protection: MOV surge protector on solar panel input
└── Additional: Ground wire to camera cable shield (EMI protection)

Ground Rod Installation:
1. Select location within 1m of pole base
2. Drive rod vertically with sledge hammer
3. Leave 10cm above ground for connection
4. Clean connection point with wire brush
5. Attach grounding clamp + wire
6. Route wire to enclosure chassis bolt
7. Measure resistance: should be <25Ω
8. If >25Ω, drive a second rod 3m away and bond together
```

### 3.7 Wiring Diagram

```
SOLAR PANEL (100W)
    │ MC4 Connector
    │ (+) Red
    │ (-) Black
    ▼
┌──────────────┐
│  MPPT CTRL   │
│  20A, 12V    │──── Battery (12V 100Ah)
│              │──── Load Output (12V)
└──────┬───────┘
       │
       │ 12V DC
       ▼
┌──────────────┐
│  DC-DC BUCK  │
│  12V → 5V    │──── Jetson Orin Nano (5V barrel jack)
│  12V → 19V   │──── (if using 19V input, use 12V→19V converter)
└──────┬───────┘
       │
       │ 5V USB
       ▼
┌──────────────┐
│ 4G MODEM     │
│  Huawei      │
│  E3372       │
└──────────────┘

Ground wire (6 AWG) from enclosure chassis → ground rod
```

---

## 4. 4G Modem Configuration

### 4.1 MTN Malawi APN Settings

| Setting | Value |
|---------|-------|
| APN | internet |
| Username | (leave blank) |
| Password | (leave blank) |
| Auth type | PAP or CHAP |
| Band | B1 (2100), B3 (1800), B7 (2600), B20 (800) |
| Roaming | Disabled |

### 4.2 Huawei E3372 Configuration

```bash
# 1. Insert MTN SIM into E3372
# 2. Connect via USB to Jetson
# 3. Access web interface (first time only)
#    Connect laptop to E3372 WiFi or USB
#    Browse to http://192.168.8.1
#    Default password: admin
#    Go to Settings → Profile Management
#    Create new profile:
#      Name: MTN-Malawi
#      APN: internet
#      Auth: PAP
#      Username: (blank)
#      Password: (blank)
#    Set as default profile

# 4. Auto-connect on boot
#    Settings → System → Prefered Mode → Auto
#    Settings → Network → Auto Register

# 5. Verify connection
curl -s --interface eth1 http://ifconfig.me
# Should return the 4G public IP
```

### 4.3 Signal Testing Procedure

```bash
# Install signal monitoring tool
pip install huawei-lte-api

# Python script for signal monitoring
cat > /opt/edgevision/scripts/signal_check.py << 'EOF'
from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection

url = "http://192.168.8.1"
try:
    with Connection(url) as connection:
        client = Client(connection)
        signal = client.net信号信号
        device = client.device.information

        print(f"Signal: {signal['SignalStrength']} dBm")
        print(f"RSRP: {signal.get('rsrp', 'N/A')}")
        print(f"RSRQ: {signal.get('rsrq', 'N/A')}")
        print(f"SINR: {signal.get('sinr', 'N/A')}")
        print(f"Cell ID: {signal.get('cell_id', 'N/A')}")
        print(f"Operator: {device.get('FullName', 'N/A')}")
        print(f"Network: {device.get('NetworkType', 'N/A')}")

        # Quality assessment
        rssi = int(signal['SignalStrength'])
        if rssi > -65:
            quality = "EXCELLENT"
        elif rssi > -80:
            quality = "GOOD"
        elif rssi > -100:
            quality = "FAIR"
        else:
            quality = "POOR"
        print(f"Quality: {quality}")
except Exception as e:
    print(f"Error: {e}")
EOF
```

### 4.4 Signal Quality Thresholds

| Metric | Excellent | Good | Fair | Poor | Action |
|--------|-----------|------|------|------|--------|
| RSSI (dBm) | > -65 | -65 to -80 | -80 to -100 | < -100 | Relocate antenna |
| RSRP (dBm) | > -80 | -80 to -90 | -90 to -105 | < -105 | Check SIM/antenna |
| RSRQ (dB) | > -3 | -3 to -7 | -7 to -12 | < -12 | Network congestion |
| SINR (dB) | > 20 | 13 to 20 | 0 to 13 | < 0 | Interference |

**Minimum for EdgeVision:** RSSI > -95 dBm (Fair or better)

### 4.5 Data Plan Requirements

| Usage | Monthly Data | Plan |
|-------|-------------|------|
| Heartbeats (every 10min, ~1KB each) | ~45MB | MTN IoT plan |
| Image upload (50 images/day, ~2MB each) | ~3GB | MTN 3GB bundle |
| API calls + metadata | ~500MB | Included |
| System updates (monthly) | ~200MB | Included |
| **Total estimated** | **~4GB/month** | **MTN 5GB monthly @ MWK 15,000 (~$15)** |

### 4.6 Connection Reliability

```bash
# Auto-reconnect script (runs every 5 minutes via cron)
cat > /opt/edgevision/scripts/modem_watchdog.sh << 'EOF'
#!/bin/bash
MODEM_IP="192.168.8.1"

if ! ping -c 1 -W 5 $MODEM_IP > /dev/null 2>&1; then
    echo "$(date): Modem unreachable, attempting USB reset" >> /var/log/modem.log
    # Reset USB device
    echo '1-1' > /sys/bus/usb/drivers/usb/unbind
    sleep 5
    echo '1-1' > /sys/bus/usb/drivers/usb/bind
    sleep 30
    if ping -c 1 -W 10 $MODEM_IP > /dev/null 2>&1; then
        echo "$(date): Modem recovered" >> /var/log/modem.log
    else
        echo "$(date): Modem still unreachable after reset" >> /var/log/modem.log
    fi
fi

# Check internet connectivity
if ! curl -sf --max-time 10 https://api.edgevision.mw/health > /dev/null 2>&1; then
    echo "$(date): API unreachable, checking DNS" >> /var/log/modem.log
    if ! nslookup api.edgevision.mw > /dev/null 2>&1; then
        echo "$(date): DNS failure — 4G connection lost" >> /var/log/modem.log
    fi
fi
EOF
chmod +x /opt/edgevision/scripts/modem_watchdog.sh

# Cron entry
echo "*/5 * * * * root /opt/edgevision/scripts/modem_watchdog.sh" > /etc/cron.d/modem-watchdog
```

---

## 5. First Boot Procedure

### 5.1 SD Card Preparation (Do This at HQ)

```bash
# 1. Download latest EdgeVision firmware
wget https://releases.edgevision.mw/firmware/edgevision-mw-l4t-jp6.2-v1.0.0.img.zip
unzip edgevision-mw-l4t-jp6.2-v1.0.0.img.zip

# 2. Flash to microSD (on workstation)
# macOS:
sudo dd if=edgevision-mw-l4t-jp6.2-v1.0.0.img of=/dev/diskN bs=4M status=progress
# Linux:
sudo dd if=edgevision-mw-l4t-jp6.2-v1.0.0.img of=/dev/sdX bs=4M status=progress

# 3. Mount and configure (Linux)
mkdir -p /mnt/sdboot
sudo mount /dev/sdX1 /mnt/sdboot

# 4. Create node config file
sudo tee /mnt/sdboot/config/node.yaml << 'NODEEOF'
node:
  id: "NODE-LIL-001"        # Unique per node
  district: "Lilongwe"
  hub_id: "HUB-LIL-001"     # Hub grouping
  latitude: -13.9625
  longitude: 33.7741
  category: "ROAD"           # ROAD | AGRI | WILDLIFE | DOC | BIOMETRIC
  pii_mode: "MODERATE"       # STRICT | MODERATE | NONE
  firmware_version: "1.0.0"
  interest_classes:
    - "car"
    - "person"
    - "truck"
    - "motorcycle"
  capture_schedule: "*/10 * * * *"   # Every 10 minutes
  upload_schedule: "*/30 * * * *"    # Every 30 minutes

api:
  base_url: "https://api.edgevision.mw"
  node_key: "<base64-encoded-ed25519-private-key>"

network:
  apn: "internet"
  apn_user: ""
  apn_pass: ""
  modem_ip: "192.168.8.1"

power:
  battery_capacity_ah: 100
  solar_panel_watts: 200
  low_battery_threshold_v: 11.0
  critical_battery_threshold_v: 10.5
NODEEOF

# 5. Copy the first-boot script
sudo tee /mnt/sdboot/scripts/first-boot.sh << 'BEOF'
#!/bin/bash
set -euo pipefail

LOG="/var/log/edgevision-first-boot.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== EdgeVision First Boot $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# 1. Wait for network
echo "Waiting for 4G modem..."
for i in $(seq 1 30); do
    if curl -sf --max-time 5 http://192.168.8.1 > /dev/null 2>&1; then
        echo "Modem reachable"
        break
    fi
    sleep 2
done

# 2. Wait for internet
echo "Waiting for internet..."
for i in $(seq 1 30); do
    if curl -sf --max-time 5 https://api.edgevision.mw/health > /dev/null 2>&1; then
        echo "Internet connected"
        break
    fi
    sleep 5
done

# 3. Register node with API
echo "Registering node..."
CONFIG="/boot/config/node.yaml"
NODE_ID=$(grep 'id:' "$CONFIG" | awk '{print $2}' | tr -d '"')

RESPONSE=$(curl -sf -X POST "https://api.edgevision.mw/api/v1/fleet/register" \
    -H "Content-Type: application/json" \
    -d @"$CONFIG")

echo "Registration response: $RESPONSE"

# 4. Start EdgeVision services
systemctl enable edgevision
systemctl start edgevision

# 5. Verify heartbeat
echo "Waiting for first heartbeat..."
sleep 30
HEALTH=$(curl -sf "https://api.edgevision.mw/api/v1/fleet/nodes/$NODE_ID" \
    -H "Authorization: Bearer <service-token>" 2>/dev/null)

if echo "$HEALTH" | grep -q "ONLINE"; then
    echo "✓ Node is ONLINE — deployment successful"
else
    echo "⚠ Node not yet ONLINE — check logs"
fi

echo "=== First Boot Complete ==="
BEOF
sudo chmod +x /mnt/sdboot/scripts/first-boot.sh

# 6. Set first-boot to run on next boot
sudo tee /mnt/sdboot/etc/systemd/system/first-boot.service << 'SVCEOF'
[Unit]
Description=EdgeVision First Boot Setup
After=network-online.target
Wants=network-online.target
OneShot=true

[Service]
Type=oneshot
ExecStart=/boot/scripts/first-boot.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SVCEOF
sudo ln -sf /etc/systemd/system/first-boot.service /mnt/sdboot/etc/systemd/system/multi-user.target.wants/

# 7. Unmount
sudo umount /mnt/sdboot
echo "SD card ready for node NODE-LIL-001"
```

### 5.2 Field Installation Procedure

```
FIRLD INSTALLATION CHECKLIST
============================
Node ID: ____________
Site: ____________
Date: ____________
Installer: ____________

□ STEP 1: Mount pole/bracket
  □ Verify pole is vertical (level bubble)
  □ Tighten U-bolts (torque: 15 Nm)
  □ Check bracket is secure (push test: 50kg lateral force)

□ STEP 2: Install solar panel
  □ Panel faces TRUE NORTH
  □ Angle is 15° from horizontal
  □ MC4 connectors secure (click + pull test)
  □ Panel is shaded from direct sun on enclosure (if possible)

□ STEP 3: Drive ground rod
  □ Location within 1m of pole base
  □ Rod driven 1.4m into earth
  □ Resistance <25Ω (measure with multimeter)
  □ Ground wire connected to enclosure chassis

□ STEP 4: Connect battery
  □ Positive (+) terminal connected first
  □ Negative (-) terminal connected second
  □ 30A fuse installed on positive line
  □ Battery voltage reads >12.5V

□ STEP 5: Connect solar
  □ Solar panel MC4 connected to MPPT controller
  □ MPPT load output connected to buck converter
  □ Battery connected to MPPT battery terminals
  □ Verify charging LED is ON (if daytime)

□ STEP 6: Insert SIM card
  □ MTN SIM inserted into 4G modem
  □ Modem powered on (USB connected to Jetson)
  □ Wait for signal LED (30 seconds)
  □ Signal strength > -95 dBm

□ STEP 7: Insert SD card
  □ SD card inserted (label facing up)
  □ Power on Jetson (press power button)
  □ Wait for boot (green LED steady, ~2 minutes)

□ STEP 8: Verify connection
  □ First boot script runs (check /var/log/edgevision-first-boot.log)
  □ Node registers with API
  □ First heartbeat sent (wait 10 minutes)
  □ Verify on dashboard: node status = ONLINE

□ STEP 9: Close enclosure
  □ All cables routed through glands
  □ Glands tightened (IP68)
  □ Lid secured with Torx security bolts
  □ Lens window clean and unobstructed
  □ Anti-theft bolts torqued (10 Nm)

□ STEP 10: Final verification
  □ Photo of installed node (wide shot)
  □ Photo of installed node (close-up of label)
  □ Photo of solar panel angle
  □ Record GPS coordinates of node
  □ Record signal strength
  □ Sign off: ____________

INSTALLATION NOTES:
_______________________________________________
_______________________________________________
```

---

## 6. Site Selection Criteria

### 6.1 Location Requirements

| Criterion | Requirement | Why |
|-----------|-------------|-----|
| Solar exposure | 6+ hours direct sun daily | Power generation |
| 4G signal | RSSI > -95 dBm | Connectivity |
| Traffic volume | 50+ vehicles/hour peak | Data value |
| Visibility | Visible from public road | Deterrence |
| Elevation | > ground level (2m+) | Flood avoidance |
| Accessibility | Within 30min drive of Lilongwe | Maintenance |
| Permissions | Landowner consent + Lilongwe City Council approval | Legal compliance |

### 6.2 Priority Sites (Lilongwe)

| # | Site Name | GPS (approx.) | Traffic | Signal | Notes |
|---|-----------|---------------|---------|--------|-------|
| 1 | City Centre Roundabout | -13.9625, 33.7741 | HIGH | GOOD | High visibility, good solar |
| 2 | Area 18 Junction | -13.9580, 33.7650 | HIGH | EXCELLENT | Near BNS |
| 3 | Kanengo Industrial | -13.9350, 33.7850 | MEDIUM | GOOD | Truck traffic |
| 4 | Crossroads Roundabout | -13.9700, 33.7800 | HIGH | GOOD | Major intersection |
| 5 | Lilongwe WECS | -13.9500, 33.7600 | MEDIUM | FAIR | Water authority |
| 6 | Area 3 Market | -13.9650, 33.7700 | HIGH | EXCELLENT | Pedestrian + vehicle |
| 7 | M1 South Junction | -13.9800, 33.7600 | HIGH | GOOD | Highway traffic |
| 8 | Bwaila Hospital | -13.9550, 33.7750 | MEDIUM | GOOD | Emergency vehicle traffic |
| 9 | Lilongwe Golf Club | -13.9700, 33.7900 | LOW | EXCELLENT | Wealthy area, premium data |
| 10 | Capital Hill | -13.9400, 33.7800 | MEDIUM | GOOD | Government vehicles |

---

## 7. Anti-Theft and Security

### 7.1 Physical Security

| Measure | Implementation |
|---------|---------------|
| Tamper bolts | M6 Torx security bolts (require T25 driver to open) |
| Tamper seal | Tamper-evident sticker over lid seam |
| Enclosure lock | Optional padlock hasp for padlock |
| Anti-climb | Mount 2.5m+ above ground on smooth pole |
| GPS tracking | GPS module inside enclosure (last known location on theft) |
| Asset tag | Laser-etched serial number + QR code on enclosure |
| Registration | Photo + GPS + serial number in asset register |

### 7.2 Software Security

| Feature | Implementation |
|---------|---------------|
| Secure boot | Jetson UEFI Secure Boot enabled |
| Encrypted storage | LUKS encryption on SD card (for PII compliance) |
| Remote wipe | API command to wipe SD card if stolen |
| Boot verification | TPM module verifies OS integrity at boot |
| Access logging | All API access logged with IP + timestamp |

### 7.3 Theft Response Protocol

```
1. Node goes OFFLINE → Alert sent to ops team
2. Check last known GPS coordinates
3. If theft suspected:
   a. Send remote wipe command via API
   b. Report to Lilongwe Police (Central Police Station)
   c. File police report (get reference number)
   d. Contact insurance provider
   e. Deploy replacement node
4. Analyze last 24hr of data for evidence
```

---

## 8. Maintenance Schedule

### 8.1 Weekly (Remote)

- [ ] Check all nodes are ONLINE on dashboard
- [ ] Review error logs for anomalies
- [ ] Verify data uploads are completing
- [ ] Check storage utilization per node

### 8.2 Monthly (Field Visit)

- [ ] Clean solar panels (bird droppings, dust)
- [ ] Check all cable connections
- [ ] Verify battery voltage (>12.5V)
- [ ] Inspect enclosure seals (gaskets, cable glands)
- [ ] Check ground rod connection
- [ ] Update firmware if available
- [ ] Verify camera lens is clean and aligned
- [ ] Record signal strength (compare to baseline)

### 8.3 Quarterly (Comprehensive)

- [ ] Full hardware inspection
- [ ] Battery capacity test (discharge to 50%, time recharge)
- [ ] MPPT controller calibration check
- [ ] Firmware update + reboot test
- [ ] Review data quality metrics
- [ ] Clean lens window with isopropyl alcohol
- [ ] Tighten all anti-theft bolts
- [ ] Replace any degraded components

### 8.4 Annual (Overhaul)

- [ ] Replace battery (if capacity < 80% of original)
- [ ] Replace microSD card (wear leveling limit)
- [ ] Re-apply conformal coating on PCB
- [ ] Replace cable glands if cracked
- [ ] Full enclosure re-powder-coat if corroded
- [ ] Update camera calibration targets
- [ ] Conduct site re-assessment (traffic changes, signal changes)

---

## Appendix: Spare Parts Kit (Per 10 Nodes)

| Part | Qty | Notes |
|------|-----|-------|
| Jetson Orin Nano | 1 | Hot-swap replacement |
| microSD card (pre-flashed) | 5 | Pre-configured with node ID |
| Camera module | 2 | In sealed bag |
| 4G modem | 2 | MTN SIM already registered |
| Solar panel (100W) | 1 | Backup panel |
| LiFePO4 battery | 1 | Backup battery |
| MPPT charge controller | 1 | Backup controller |
| DC-DC buck converter | 2 | 12V→5V and 12V→19V |
| Cable glands (assorted) | 10 | PG7 and PG9 |
| Anti-tamper bolts (T25) | 20 | M6 × 12mm, stainless |
| EPDM gasket material | 1m | For resealing enclosures |
| Isopropyl alcohol wipes | 50 | For lens cleaning |
| Torx T25 driver | 2 | For enclosure opening |
| Multimeter | 1 | For field diagnostics |
| Cable ties (UV-resistant) | 100 | For cable management |
| Heat shrink tubing | Assorted | For wire repairs |
| **Total spare parts kit cost** | | **~$800** |
