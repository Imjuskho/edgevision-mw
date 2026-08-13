export interface LabelClass {
  label: string;
  name: string;
  edgeCases?: string;
}

export interface LabelCategory {
  id: string;
  name: string;
  icon: string;
  color: string;
  classes: LabelClass[];
}

export interface SceneAttribute {
  id: string;
  name: string;
  description: string;
}

export const CATEGORY_COLORS: Record<string, string> = {
  motorized: "#ef4444",
  non_motorized: "#f97316",
  pedestrians: "#eab308",
  animals: "#22c55e",
  agricultural: "#10b981",
  static: "#6366f1",
  regulatory_signs: "#3b82f6",
  warning_signs: "#8b5cf6",
  info_signs: "#a855f7",
  informal_signs: "#d946ef",
  traffic_control: "#ec4899",
  road_surface: "#14b8a6",
  other_scene: "#64748b",
};

export const TAXONOMY_CATEGORIES: LabelCategory[] = [
  {
    id: "motorized",
    name: "Motorized Vehicles",
    icon: "\u{1F697}",
    color: CATEGORY_COLORS.motorized,
    classes: [
      { label: "car_private", name: "Car (private)", edgeCases: "Overloaded with passengers/cargo, roof-rack loads exceeding vehicle width." },
      { label: "taxi", name: "Taxi (private hire)", edgeCases: "Often indistinguishable from private car; may function as shared taxi bus on rural routes." },
      { label: "minibus", name: "Minibus / Matola", edgeCases: "Passengers hanging out of open doors, roof cargo, conductor hanging off the side." },
      { label: "bus", name: "Bus (intercity coach)", edgeCases: "Overtaking on blind corners, parked roadside blocking a lane." },
      { label: "pickup_passenger", name: "Pickup / Lorry (with passengers)", edgeCases: "Open truck bed carrying standing/seated passengers — high-risk, flag distinctly from cargo-only." },
      { label: "truck_freight", name: "Truck (freight)", edgeCases: "Overloaded with agricultural produce extending beyond bed limits." },
      { label: "tuktuk", name: "Tuktuk / auto-rickshaw", edgeCases: "Mostly urban/border towns." },
      { label: "motorcycle_kabaza", name: "Motorcycle — kabaza (commercial)", edgeCases: "No helmets, passenger riding side-saddle, cargo strapped across the back." },
      { label: "motorcycle_private", name: "Motorcycle — private", edgeCases: "Single rider, no passenger transport." },
      { label: "tractor_road", name: "Tractor (on-road)", edgeCases: "Slow-moving, may lack lights/reflectors, often centered in lane." },
      { label: "gov_ngo_vehicle", name: "Government/NGO vehicle", edgeCases: "Irregular stopping patterns, may ignore normal traffic behavior in rural areas." },
      { label: "emergency_vehicle", name: "Emergency vehicle", edgeCases: "Police, ambulance, fire — flag separately for priority behavior." },
    ],
  },
  {
    id: "non_motorized",
    name: "Non-Motorized Vehicles",
    icon: "\u{1F6B2}",
    color: CATEGORY_COLORS.non_motorized,
    classes: [
      { label: "bicycle_kabaza", name: "Bicycle — kabaza (commercial, passenger)", edgeCases: "Passenger riding side-saddle, sometimes two passengers." },
      { label: "bicycle_private", name: "Bicycle — private/utility", edgeCases: "Single rider, no passenger." },
      { label: "bicycle_cargo", name: "Bicycle — cargo-laden", edgeCases: "Charcoal sacks, firewood, produce stacked far above rider's head — major edge case for width/height misjudgment." },
      { label: "handcart", name: "Handcart / wheelbarrow", edgeCases: "Pushed manually, sometimes on roadway rather than shoulder." },
      { label: "ox_cart", name: "Ox-cart / animal-drawn cart", edgeCases: "Very slow speed, unpredictable animal behavior, often no lights at dusk." },
      { label: "improvised_cart", name: "Improvised cart", edgeCases: "Small carts pulled by children or by hand — low profile, easy to miss." },
    ],
  },
  {
    id: "pedestrians",
    name: "Pedestrians",
    icon: "\u{1F6B6}",
    color: CATEGORY_COLORS.pedestrians,
    classes: [
      { label: "pedestrian_roadside", name: "Adult pedestrian — roadside", edgeCases: "Walking on shoulder/verge." },
      { label: "pedestrian_carriageway", name: "Adult pedestrian — on carriageway", edgeCases: "Walking directly in traffic lane where no sidewalk exists." },
      { label: "pedestrian_head_load", name: "Pedestrian carrying head-load", edgeCases: "Balancing buckets, firewood, produce on head — affects silhouette and turning behavior." },
      { label: "pedestrian_child_wrap", name: "Pedestrian carrying child", edgeCases: "Chitenje/baby wrap — affects mobility and reaction time." },
      { label: "child_pedestrian", name: "Child pedestrian (unaccompanied)", edgeCases: "Higher-risk — may dart or behave unpredictably." },
      { label: "pedestrian_group", name: "Group/cluster of pedestrians", edgeCases: "Common near markets, schools, bus stops, borders." },
      { label: "street_vendor_mobile", name: "Street vendor (mobile)", edgeCases: "Walking between vehicles at junctions/traffic stops selling goods." },
      { label: "person_pushing_vehicle", name: "Person pushing a bicycle/cart", edgeCases: "Not riding but walking alongside a non-motorized vehicle." },
      { label: "person_crossing_midblock", name: "Person crossing mid-block", edgeCases: "No formal crossings — flag as default crossing behavior, not an anomaly." },
    ],
  },
  {
    id: "animals",
    name: "Animals (Loose or Herded)",
    icon: "\u{1F41E}",
    color: CATEGORY_COLORS.animals,
    classes: [
      { label: "cattle", name: "Cattle (herded or loose)", edgeCases: "Common on rural roads, can occupy full lane width, herder may or may not be visible." },
      { label: "goat_sheep", name: "Goats/sheep", edgeCases: "Small, low to ground, often in groups, fast unpredictable movement." },
      { label: "dog", name: "Dogs", edgeCases: "Frequently roadside or crossing, often unaccompanied." },
      { label: "chicken_poultry", name: "Chickens/poultry", edgeCases: "Low-profile, hard to detect, common near village roadside." },
      { label: "draft_animal_harness", name: "Draft animals in harness", edgeCases: "Distinguish from loose livestock — attached to cart or plough." },
    ],
  },
  {
    id: "agricultural",
    name: "Agricultural Road Users",
    icon: "\u{1F33E}",
    color: CATEGORY_COLORS.agricultural,
    classes: [
      { label: "tractor_implement", name: "Tractor with towed implement", edgeCases: "Plough, trailer, or seeder being towed on the road." },
      { label: "produce_transport", name: "Produce transport (informal)", edgeCases: "Bicycles, carts, or truck beds piled high with produce — exceeding normal vehicle envelope." },
      { label: "roadside_drying", name: "Roadside drying/threshing", edgeCases: "Maize, tobacco, or grain laid out on road surface to dry — unique to rural Malawi." },
      { label: "grazing_encroachment", name: "Grazing encroachment", edgeCases: "Animals grazing on road verges, may step into carriageway." },
    ],
  },
  {
    id: "static",
    name: "Static / Roadside Objects",
    icon: "\u{1F3EC}",
    color: CATEGORY_COLORS.static,
    classes: [
      { label: "market_stall_encroach", name: "Informal market stalls encroaching", edgeCases: "Common at trading centers; narrows effective road width." },
      { label: "roadblock_checkpoint", name: "Roadblock / checkpoint", edgeCases: "Vehicles queuing, pedestrians moving between stopped vehicles." },
      { label: "unmarked_speed_bump", name: "Unmarked speed bump", edgeCases: "Frequent in trading centers, often unpainted/unsigned." },
      { label: "pothole_cluster", name: "Pothole cluster / degraded road edge", edgeCases: "Affects vehicle swerving behavior — useful as a scene tag." },
      { label: "parked_informal", name: "Parked vehicle (informal)", edgeCases: "Minibuses stopping mid-road to load passengers rather than pulling over." },
      { label: "roadside_vendor_fixed", name: "Roadside vendor stand (fixed)", edgeCases: "Fruit stands, firewood stacks — can obstruct sightlines." },
    ],
  },
  {
    id: "regulatory_signs",
    name: "Traffic Signs (Regulatory)",
    icon: "\u{1F6D1}",
    color: CATEGORY_COLORS.regulatory_signs,
    classes: [
      { label: "stop_sign", name: "Stop sign", edgeCases: "Faded, bent, or obscured by vegetation — very common." },
      { label: "yield_sign", name: "Give way / yield", edgeCases: "" },
      { label: "speed_limit_sign", name: "Speed limit sign", edgeCases: "Often missing, damaged, or inconsistent with actual road condition." },
      { label: "no_overtaking", name: "No overtaking", edgeCases: "Frequently ignored — still label for scene context." },
      { label: "no_entry_oneway", name: "No entry / one-way", edgeCases: "Mostly urban (Blantyre, Lilongwe city centers)." },
      { label: "weight_height_restriction", name: "Weight/height restriction", edgeCases: "Near bridges, border posts." },
      { label: "police_checkpoint_sign", name: "Police/checkpoint sign", edgeCases: "Formal or informal, sometimes just a painted board or cone." },
    ],
  },
  {
    id: "warning_signs",
    name: "Traffic Signs (Warning)",
    icon: "\u{26A0}\u{FE0F}",
    color: CATEGORY_COLORS.warning_signs,
    classes: [
      { label: "curve_bend_warning", name: "Curve/bend warning", edgeCases: "" },
      { label: "pedestrian_crossing_warning", name: "Pedestrian crossing warning", edgeCases: "Rarely paired with an actual marked crossing." },
      { label: "animal_crossing_warning", name: "Animal crossing warning", edgeCases: "Near game parks and rural livestock areas." },
      { label: "uneven_road_warning", name: "Uneven road / pothole warning", edgeCases: "" },
      { label: "speed_bump_warning", name: "Speed bump warning", edgeCases: "Often absent even where bumps exist — mismatch is itself an edge case." },
      { label: "school_zone_warning", name: "School zone warning", edgeCases: "" },
      { label: "narrow_bridge_warning", name: "Narrow bridge warning", edgeCases: "Common on secondary roads." },
    ],
  },
  {
    id: "info_signs",
    name: "Traffic Signs (Informational)",
    icon: "\u{2139}\u{FE0F}",
    color: CATEGORY_COLORS.info_signs,
    classes: [
      { label: "place_name_sign", name: "Place-name / distance sign", edgeCases: "" },
      { label: "route_number_marker", name: "Route number marker (M1, S-roads)", edgeCases: "" },
      { label: "border_directional_sign", name: "Border post / checkpoint sign", edgeCases: "" },
      { label: "fuel_services_sign", name: "Fuel/services sign", edgeCases: "" },
    ],
  },
  {
    id: "informal_signs",
    name: "Informal Signage (Malawi-specific)",
    icon: "\u{1F4DD}",
    color: CATEGORY_COLORS.informal_signs,
    classes: [
      { label: "hand_painted_board", name: "Hand-painted warning board", edgeCases: "Community-made signs — visually distinct from manufactured but functionally equivalent." },
      { label: "ad_board_mimicking_sign", name: "Ad board mimicking a sign", edgeCases: "Billboards near junctions that resemble regulatory signs — potential false-positive source." },
      { label: "faded_sun_bleached_sign", name: "Faded/sun-bleached sign", edgeCases: "Sign shape/pole present but content unreadable." },
      { label: "sign_obscured", name: "Sign obscured by stall/vegetation", edgeCases: "Partial occlusion is the norm in trading centers." },
      { label: "repurposed_sign_post", name: "Repurposed sign post (no sign)", edgeCases: "Bare pole, sign missing/stolen — still relevant as infrastructure cue." },
    ],
  },
  {
    id: "traffic_control",
    name: "Traffic Control Infrastructure",
    icon: "\u{1F6A6}",
    color: CATEGORY_COLORS.traffic_control,
    classes: [
      { label: "traffic_light", name: "Traffic light", edgeCases: "Only in major cities; rare and sometimes non-functional/flashing amber." },
      { label: "roundabout", name: "Roundabout", edgeCases: "Common in urban centers; poorly marked lane discipline." },
      { label: "zebra_crossing", name: "Zebra crossing (painted)", edgeCases: "Often faded; pedestrians rarely restrict crossing to marked zones." },
      { label: "speed_bump_physical", name: "Speed bump / rumble strip", edgeCases: "Distinguish 'marked' vs 'unmarked' as an attribute." },
      { label: "boom_gate", name: "Boom gate / border barrier", edgeCases: "At border posts, weighbridges." },
      { label: "toll_gate", name: "Toll gate", edgeCases: "On select national routes." },
      { label: "railway_crossing", name: "Railway crossing", edgeCases: "Rare but present; often unmarked." },
    ],
  },
  {
    id: "road_surface",
    name: "Road Surface & Lane Markings",
    icon: "\u{1F6E3}\u{FE0F}",
    color: CATEGORY_COLORS.road_surface,
    classes: [
      { label: "paved_marked", name: "Paved road — marked lanes", edgeCases: "Mostly on M1 and major routes." },
      { label: "paved_unmarked", name: "Paved road — unmarked/faded lanes", edgeCases: "Very common; center line and edge lines often invisible." },
      { label: "unpaved_gravel", name: "Unpaved/gravel/dirt road", edgeCases: "Majority of rural network; affects vehicle dynamics and dust occlusion." },
      { label: "road_edge_dropoff", name: "Road edge — no shoulder", edgeCases: "Common failure mode for lane-keeping systems." },
      { label: "flooded_segment", name: "Flooded/washed-out road segment", edgeCases: "Seasonal (rainy season), may require detection as a hazard region." },
    ],
  },
  {
    id: "other_scene",
    name: "Other Scene Elements",
    icon: "\u{1F3D7}\u{FE0F}",
    color: CATEGORY_COLORS.other_scene,
    classes: [
      { label: "streetlight", name: "Streetlight (functional/non-functional)", edgeCases: "Many rural roads unlit at night — flag lighting condition as scene attribute." },
      { label: "bridge_culvert", name: "Bridge/culvert", edgeCases: "Narrow, sometimes single-lane with informal priority negotiation." },
      { label: "utility_pole", name: "Utility pole in/near roadway", edgeCases: "Common obstruction close to carriageway edge." },
      { label: "parked_abandoned", name: "Parked/abandoned vehicle (breakdown)", edgeCases: "Often unlit, unmarked with hazard triangles — at night a major hazard." },
      { label: "debris_landslide", name: "Debris/rockfall/landslide zone", edgeCases: "Rainy-season hazard, especially in highland routes." },
    ],
  },
];

export const SCENE_ATTRIBUTES: SceneAttribute[] = [
  { id: "overloaded", name: "Overloaded", description: "Vehicle/cargo exceeding normal envelope" },
  { id: "no_lights", name: "No lights", description: "Missing lights, especially hazardous at dusk/night" },
  { id: "irregular_stop", name: "Irregular stop", description: "Stopping in unusual position (mid-road, blind corner)" },
  { id: "animal_unattended", name: "Animal unattended", description: "Loose livestock without visible herder" },
  { id: "load_exceeds_envelope", name: "Load exceeds envelope", description: "Cargo extending beyond vehicle width/height" },
  { id: "high_unpredictability", name: "High unpredictability", description: "Children, loose livestock, kabaza, pedestrians on carriageway" },
];

export const ALL_LABELS: { label: string; name: string; category: string; color: string }[] =
  TAXONOMY_CATEGORIES.flatMap((cat) =>
    cat.classes.map((cls) => ({
      label: cls.label,
      name: cls.name,
      category: cat.name,
      color: cat.color,
    }))
  );

export function getCategoryColor(label: string): string {
  for (const cat of TAXONOMY_CATEGORIES) {
    if (cat.classes.some((c) => c.label === label)) return cat.color;
  }
  return "#64748b";
}

export function getCategoryForLabel(label: string): LabelCategory | undefined {
  return TAXONOMY_CATEGORIES.find((cat) =>
    cat.classes.some((c) => c.label === label)
  );
}

export function searchLabels(query: string): { label: string; name: string; category: string; color: string }[] {
  const q = query.toLowerCase();
  return ALL_LABELS.filter(
    (item) =>
      item.label.includes(q) ||
      item.name.toLowerCase().includes(q) ||
      item.category.toLowerCase().includes(q)
  );
}
