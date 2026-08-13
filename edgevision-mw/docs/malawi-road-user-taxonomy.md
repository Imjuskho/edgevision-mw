# Malawi Road User Taxonomy — Annotation Reference

A working class list for labeling road users on Malawian roads (urban, rural, and agricultural contexts). Organized by category with edge cases flagged for annotators.

---

## 1. Motorized Vehicles

| Class | Notes / Edge Cases |
|---|---|
| **Car (private)** | Sedans, hatchbacks. Edge case: overloaded with passengers/cargo, roof-rack loads exceeding vehicle width. |
| **Taxi (private hire)** | Often indistinguishable from private car without signage. Edge case: functioning as a shared "taxi bus" on rural routes — annotate occupancy if visible. |
| **Minibus / Matola (shared van)** | Toyota Hiace-style. Edge case: passengers hanging out of open doors, roof cargo, conductor hanging off the side while moving. |
| **Bus (intercity coach)** | Larger, scheduled. Edge case: overtaking on blind corners, parked roadside for boarding blocking a lane. |
| **Pickup truck / Lorry (matola use)** | Open truck bed carrying standing/seated passengers. Edge case: passengers standing and holding onto rails — high-risk class, flag distinctly from cargo-only trucks. |
| **Truck (freight, no passengers)** | Includes flatbeds, tankers. Edge case: overloaded with agricultural produce (maize sacks, tobacco bales) extending beyond bed limits. |
| **Tuktuk / auto-rickshaw** | Less common; mostly urban/border towns. |
| **Motorcycle — kabaza (commercial)** | Passenger-carrying, often 2–3 riders including passengers. Edge case: no helmets, passenger riding side-saddle, cargo (firewood, produce) strapped across the back. |
| **Motorcycle — private** | Single rider, no passenger transport. |
| **Tractor (on-road)** | Agricultural tractor traveling between fields, sometimes towing a trailer or plough. Edge case: slow-moving, may lack lights/reflectors, often unmarked and centered in lane. |
| **Government/NGO vehicle** | 4x4s (branded), ambulances. Edge case: irregular stopping patterns, may ignore normal traffic behavior in rural areas. |
| **Emergency vehicle** | Police, ambulance, fire. Rare but flag separately for priority behavior. |

---

## 2. Non-Motorized Vehicles

| Class | Notes / Edge Cases |
|---|---|
| **Bicycle — kabaza (commercial, passenger)** | Cushioned rear seat for paying passenger. Edge case: passenger riding side-saddle, sometimes two passengers. |
| **Bicycle — private/utility** | Single rider, no passenger. |
| **Bicycle — cargo-laden** | Carrying charcoal sacks, firewood bundles, produce, or goods stacked far above rider's head — very common and a major edge case for width/height misjudgment. |
| **Handcart / wheelbarrow** | Pushed manually, often loaded with goods, sometimes on the roadway itself rather than the shoulder. |
| **Ox-cart / animal-drawn cart** | Wooden cart pulled by oxen, common in rural/agricultural zones. Edge case: very slow speed, unpredictable animal behavior, often no lights at dusk. |
| **Improvised cart (child-pulled or hand-pulled)** | Small carts pulled by children or by hand, low profile, easy to miss in detection. |

---

## 3. Pedestrians

| Class | Notes / Edge Cases |
|---|---|
| **Adult pedestrian — roadside** | Walking on shoulder/verge. |
| **Adult pedestrian — on carriageway** | Walking directly in the traffic lane (common where no sidewalk exists). |
| **Pedestrian carrying head-load** | Balancing buckets, firewood, produce on head — affects visible silhouette and turning behavior. |
| **Pedestrian carrying child (chitenje/baby wrap)** | Common; affects mobility and reaction time. |
| **Child pedestrian (unaccompanied)** | Higher-risk class, may dart or behave unpredictably. |
| **Group/cluster of pedestrians** | Common near markets, schools, bus stops, borders. |
| **Street vendor (mobile)** | Walking between vehicles at junctions/traffic stops selling goods. |
| **Person pushing a bicycle/cart** | Not riding but walking alongside a non-motorized vehicle. |
| **Person crossing mid-block** | No formal crossings in most areas — flag as default crossing behavior, not an anomaly. |

---

## 4. Animals (Loose or Herded)

| Class | Notes / Edge Cases |
|---|---|
| **Cattle (herded or loose)** | Common on rural roads, can occupy full lane width, herder may or may not be visible nearby. |
| **Goats/sheep** | Small, low to ground, often in groups, fast unpredictable movement. |
| **Dogs** | Frequently roadside or crossing, often unaccompanied. |
| **Chickens/poultry** | Low-profile, hard to detect, common near village roadside. |
| **Draft animals in harness (oxen, donkeys)** | Distinguish from loose livestock — attached to cart or plough. |

---

## 5. Agricultural Road Users / Objects

| Class | Notes / Edge Cases |
|---|---|
| **Tractor with towed implement** | Plough, trailer, or seeder being towed on the road between fields. |
| **Produce transport (informal)** | Bicycles, carts, or truck beds piled high with maize, tobacco, tomatoes, etc. — often exceeding normal vehicle envelope. |
| **Roadside drying/threshing activity** | Maize, tobacco, or grain laid out on the road surface or shoulder to dry — a static "obstacle" class unique to rural Malawi. |
| **Grazing encroachment** | Animals grazing directly on road verges, may step into the carriageway without warning. |

---

## 6. Static / Roadside Edge Cases (context objects, not "users" but affect behavior)

| Class | Notes |
|---|---|
| **Informal market stalls encroaching on shoulder/lane** | Common at trading centers; narrows effective road width. |
| **Roadblock / checkpoint (police or informal)** | Vehicles queuing, pedestrians moving between stopped vehicles. |
| **Unmarked speed bump** | Frequent in trading centers, often unpainted/unsigned. |
| **Pothole cluster / degraded road edge** | Affects vehicle swerving behavior — useful as a scene tag. |
| **Parked vehicle (informal roadside parking/loading)** | Minibuses/matolas stopping mid-road to load passengers rather than pulling over. |
| **Roadside vendor stand (fixed)** | Fruit stands, firewood stacks, tables — static but can obstruct sightlines. |

---

## 7. Traffic Signs (Regulatory)

| Class | Notes / Edge Cases |
|---|---|
| **Stop sign** | Malawi follows UK/SADC-style signage (left-hand drive). Edge case: faded, bent, or obscured by vegetation — very common. |
| **Give way / yield** | |
| **Speed limit sign** | Often missing, damaged, or inconsistent with actual road condition. |
| **No overtaking** | Frequently ignored in practice — still label for scene context. |
| **No entry / one-way** | Mostly urban (Blantyre, Lilongwe city centers). |
| **Weight/height restriction** | Near bridges, border posts. |
| **Police/checkpoint sign** | Formal or informal, sometimes just a painted board or cone. |

---

## 8. Traffic Signs (Warning)

| Class | Notes / Edge Cases |
|---|---|
| **Curve/bend warning** | |
| **Pedestrian crossing warning** | Rarely paired with an actual marked crossing. |
| **Animal crossing warning** | Cattle/wildlife — present near game parks and rural livestock areas. |
| **Uneven road / pothole warning** | |
| **Speed bump warning** | Often absent even where bumps exist — mismatch is itself an edge case worth tagging. |
| **School zone warning** | |
| **Narrow bridge / one-lane bridge** | Common on secondary roads. |

---

## 9. Traffic Signs (Informational / Directional)

| Class | Notes / Edge Cases |
|---|---|
| **Place-name / distance sign** | |
| **Route number marker (M1, S-roads, etc.)** | |
| **Border post / checkpoint directional sign** | |
| **Fuel/services sign** | |

---

## 10. Non-Standard / Informal Signage (Malawi-specific edge cases)

| Class | Notes / Edge Cases |
|---|---|
| **Hand-painted warning board** | Community-made signs (e.g., "Speed Bump Ahead" painted on a wooden board or tire) — visually distinct from manufactured signs, but functionally equivalent. |
| **Advertising board mimicking a sign shape** | Billboards near junctions that resemble regulatory signs — potential false-positive source. |
| **Faded/sun-bleached sign (near-blank)** | Common due to weathering — sign shape/pole present but content unreadable. |
| **Sign obscured by vendor stall or vegetation** | Partial occlusion is the norm rather than the exception in trading centers. |
| **Repurposed sign post (no sign attached)** | Bare pole, sign missing/stolen — still relevant as an infrastructure cue. |

---

## 11. Traffic Control Infrastructure

| Class | Notes / Edge Cases |
|---|---|
| **Traffic light** | Only in major cities (Blantyre, Lilongwe, Mzuzu); rare and sometimes non-functional. Edge case: powered off/flashing amber acting as a give-way. |
| **Roundabout** | Common in urban centers; poorly marked lane discipline. |
| **Zebra crossing (painted)** | Often faded; pedestrians rarely restrict crossing to marked zones regardless. |
| **Speed bump / rumble strip (physical)** | Distinguish "marked" vs "unmarked" as an attribute. |
| **Boom gate / border barrier** | At border posts, weighbridges. |
| **Toll gate** | On select national routes. |
| **Railway crossing (marked/unmarked)** | Rare but present near rail corridors; often unmarked. |

---

## 12. Road Surface & Lane Markings

| Class | Notes / Edge Cases |
|---|---|
| **Paved road — marked lanes** | Mostly on M1 and major routes. |
| **Paved road — unmarked/faded lanes** | Very common; center line and edge lines often invisible. |
| **Unpaved/gravel/dirt road** | Majority of rural network; affects vehicle dynamics and dust occlusion. |
| **Road edge — no shoulder (drop-off)** | Common failure mode for lane-keeping systems. |
| **Flooded/washed-out road segment** | Seasonal (rainy season), may require detection as a hazard region rather than a sign. |

---

## 13. Other Scene Elements Relevant to Vision Systems

| Class | Notes / Edge Cases |
|---|---|
| **Streetlight (functional/non-functional)** | Many rural/peri-urban roads unlit at night — flag lighting condition as a scene attribute rather than per-object. |
| **Bridge/culvert** | Narrow, sometimes single-lane with informal priority negotiation. |
| **Utility pole in/near roadway** | Common obstruction close to the carriageway edge. |
| **Parked/abandoned vehicle (breakdown)** | Often unlit, unmarked with hazard triangles, at night a major hazard. |
| **Debris/rockfall/landslide zone** | Rainy-season hazard, especially in highland routes. |

---

## Scene-Level Attribute Tags

Apply these as secondary tags on annotations rather than as standalone classes:

| Attribute | Description |
|---|---|
| **overloaded** | Vehicle/cargo exceeding normal envelope |
| **no-lights** | Missing lights, especially hazardous at dusk/night |
| **irregular-stop** | Stopping in unusual position (mid-road, blind corner) |
| **animal-unattended** | Loose livestock without visible herder |
| **load-exceeds-envelope** | Cargo extending beyond vehicle width/height |
| **high-unpredictability** | Children, loose livestock, kabaza, pedestrians on carriageway |

---

## Suggested Annotation Priorities

1. **Occlusion/edge risk classes** worth flagging with an attribute tag rather than a new class: *overloaded*, *no-lights*, *irregular-stop*, *animal-unattended*, *load-exceeds-envelope*.
2. **Behavioral unpredictability** is higher for: children, loose livestock, kabaza (both bicycle and motorcycle), and pedestrians on carriageway — consider a shared "high-unpredictability" attribute across classes rather than only relying on class label.
3. **Kabaza is ambiguous by design** — since it spans bicycle and motorcycle, keep them as two separate base classes (bicycle-kabaza, motorcycle-kabaza) but consider a shared parent label "kabaza" in your taxonomy hierarchy for downstream flexibility.
4. **Signage condition is itself a signal, not noise** — in Malawi, faded/occluded/hand-painted/missing signs are the majority case, not the exception. Recommend a `condition` attribute (standard / faded / occluded / hand-painted / absent-post-only) on every sign class rather than dropping degraded signs as unlabeled background.
5. **Formal vs informal traffic control** should be a first-class distinction (e.g., marked speed bump vs. unmarked, manned police checkpoint vs. informal roadblock) since model behavior expectations differ significantly between the two.
6. **Lighting/road-surface condition as scene-level tags** (unlit road, unpaved surface, flooded segment) will likely matter more for model performance than adding more object classes — consider tagging these at the frame/scene level in addition to your object taxonomy.
