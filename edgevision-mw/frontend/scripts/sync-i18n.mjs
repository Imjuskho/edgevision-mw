#!/usr/bin/env node
/**
 * Sync ny.json with en.json — add missing keys with Chichewa translations.
 * Also ensures Phase 12 keys exist in both locale files.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const LOCALES_DIR = join(__dirname, "../src/i18n/locales");
const EN_PATH = join(LOCALES_DIR, "en.json");
const NY_PATH = join(LOCALES_DIR, "ny.json");

/** Phase 12 keys — added to en.json and ny.json when missing. */
const PHASE12_EN = {
  "app.skipToContent": "Skip to content",
  "app.search": "Search",
  "app.accessDenied": "You don't have access to this area.",
  "nav.logout": "Logout",
  "settings.theme_system": "System",
  "settings.theme_dark": "Dark",
  "settings.theme_light": "Light",
  "settings.theme_high-contrast": "High contrast",
  "settings.lowDataOn": "Enable low data mode",
  "settings.lowDataOff": "Disable low data mode",
  "settings.appearance": "Appearance",
};

const PHASE12_NY = {
  "app.skipToContent": "Pitani ku zomwe zili mkati",
  "app.search": "Sakani",
  "app.accessDenied": "Mulibe ulamuliro wa malo awa.",
  "nav.logout": "Tulukani",
  "settings.theme_system": "Dongosolo",
  "settings.theme_dark": "Mdima",
  "settings.theme_light": "Kuwala",
  "settings.theme_high-contrast": "Kusiyana kwakukulu",
  "settings.lowDataOn": "Yambitsani njira ya data yochepa",
  "settings.lowDataOff": "Letsani njira ya data yochepa",
  "settings.appearance": "Maonekedwe",
};

/** Chichewa translations for keys present in en but missing from ny. */
const CHICHEWA = {
  "views.settings": "Zokonda",
  "settings.subtitle":
    "Sinthani zinthu, kuoneka, ndi zosankha zapamwamba pa malo anu ogwira ntchito.",
  "settings.dedupDefaults": "Zokhazikika za dedup",
  "settings.dedupThreshold": "Mlingo wofanana",
  "settings.featuresTitle": "Zinthu",
  "settings.featuresDesc":
    "Letsani ma module osafunika — zinthu zobisika zimachotsedwa ku sidebar.",
  "settings.displayTitle": "Kuoneka ndi ntchito",
  "settings.showDashboardHealthDesc":
    "Onetsani magoli a thanzi la dataset pa dashboard yoyambira.",
  "settings.compactSidebarDesc": "Kuyenda kwachidule pa zowonera zazing'ono.",
  "settings.reducedMotionDesc": "Chepetsani zochita ndi kusintha.",
  "settings.resetDesc":
    "Bwezerani zokonda zonse kuzokhazikika. Chiyankhulo sichisinthidwa.",
  "settings.featureDisabled": "Chinthu ichi chaletsedwa mu Zokonda.",
  "settings.features.liveAnnotateDesc":
    "Kusanthula ndi kamera munthawi yeniyeni ndi AI.",
  "settings.features.trainingDesc": "Phunzitsani ndi kugwiritsa ntchito ma model pa ma dataset.",
  "settings.features.exportDesc": "Pangani kutumiza kwa COCO, YOLO, kapena Pascal VOC.",
  "settings.features.fleetDesc": "Yang'anirani ndi kukonza zida zojambula m'minda.",
  "settings.features.roadAnalysisDesc": "Dashboard yowunika mkhalidwe wa misewu.",
  "settings.features.agriAnalysisDesc": "Dashboard yowunika za ulimi.",
  "settings.features.dedupDesc": "Pezani ndi kukonza zithunzi zofanana.",
  "settings.features.healthDashboardDesc":
    "Ma metric a ubwino ndi michart pa dataset iliyonse.",
  "settings.features.roadTaxonomyDesc":
    "Mawu othandizira a mtundu wa msewu ndi mkhalidwe.",
  "settings.features.agriTaxonomyDesc":
    "Mawu othandizira a mtundu wa zomera ndi thanzi la zomera.",
  "home.eyebrow": "Kusanthula m'minda ku Malawi",
  "home.quickActionsHint":
    "Lowani mu ntchito — zagawidwa mwa mtundu wa ntchito.",
  "home.stepBrowseTitle": "Onani ma dataset",
  "home.stepBrowseDesc":
    "Pezani misewu, ulimi, kapena msonkhano womwe wajambulidwa m'minda.",
  "home.stepSelectTitle": "Sankhani dataset",
  "home.stepSelectDesc":
    "Gwiritsani ntchito dropdown ya sidebar kapena mndandanda wa ma dataset kuti mukhazikitse ntchito.",
  "home.stepWorkTitle": "Yambani kusintha mawu",
  "home.stepWorkDesc":
    "Santhulani, gawani misewu, jambulani moyo, kapena phunzitsani ma model pa deta yanu.",
  "home.imageCount": "Zithunzi {{count}}",
  "datasets.pageLabel": "Sankhani Dataset",
  "datasets.heading": "Pezani dataset yomwe mukufuna kugwira ntchito",
  "datasets.subtitle":
    "Sefa, sanjani, ndi sankhani dataset yoyenera ntchito yanu yosanthula kapena kuphunzitsa.",
  "datasets.searchPlaceholder": "Sakani ma dataset...",
  "datasets.searchAria": "Sakani ma dataset",
  "datasets.refreshing": "Ikutsitsanso...",
  "datasets.refresh": "Tsitsani",
  "datasets.typeSync": "Kufananitsa",
  "datasets.typePhoto": "Chithunzi",
  "datasets.typeStudio": "Studio",
  "datasets.typePhase": "Gawo",
  "datasets.found": "Ma dataset {{count}} apezeka",
  "datasets.page": "Tsamba {{page}}",
  "datasets.emptyTitle": "Palibe ma dataset omwe akugwirizana ndi sefa yanu",
  "datasets.emptyBody":
    "Yesani kusintha mawu osakira kapena sefa kuti muone ma dataset ambiri.",
  "datasets.unknownStatus": "Osadziwika",
  "datasets.images": "zithunzi",
  "datasets.noIaa": "Palibe IAA",
  "datasets.iaaScore": "{{score}}% IAA",
  "datasets.loadMore": "Tsitsani ma dataset onse",
  "health.subtitle":
    "Ma metric a ubwino, kulingana kwa magulu, ndi zoyenera kuchita.",
  "dedup.analyzing": "Ikufufuza...",
  "dedup.configTitle": "Kukonzekera Kufufuza",
  "dedup.methodPhash": "pHash (zofanana kwathunthu ndi pang'ono)",
  "dedup.methodClip": "CLIP (kufanana kwa tanthauzo)",
  "dedup.methodGps": "GPS + Nthawi (malo/nthawi yofanana)",
  "dedup.startFailed": "Zalephera kuyambitsa kufufuza",
  "dedup.analysisFailed": "Kufufuza kwalephera",
  "dedup.analysisTimeout": "Kufufuza kunatha nthawi. Yesaninso.",
  "dedup.pollFailed": "Kulumikizana kwalephera pa kuyang'ana momwe kufufuza kukuchitikira.",
  "dedup.clustering": "Ikukwerengera ma embedding ndi kugawana...",
  "dedup.groups": "magulu",
  "dedup.resolved": "zatheka",
  "dedup.groupsReviewed": "Magulu {{done}} / {{total}} aonetsedwa",
  "dedup.prev": "Zapitazo",
  "dedup.next": "Zotsatira",
  "dedup.groupOf": "Gulu {{current}} la {{total}}",
  "dedup.similar": "zofanana",
  "dedup.unknownTime": "Osadziwika",
  "dedup.keepFirstOnly": "Sungani Yoyamba Yokha",
  "dedup.autoResolveAll": "Konza zonse: Sungani Yoyamba",
  "dedup.applyCount": "Gwiritsani Ntchito Zisankho {{count}}",
  "dedup.emptyHint":
    "Dataset yanu ndi yoyera. Yesani kutsitsa mlingo kapena kuyambitsa njira zina.",
  "dedup.computeEmbeddings": "Kwerengera CLIP Embeddings",
  "dedup.computing": "Ikukwerengera...",
  "dedup.cancelEmbed": "Letsani",
  "dedup.embedStatus": "Ikukwerengera CLIP embeddings pa zithunzi za dataset...",
  "dedup.embedComplete": "Zakwerengera CLIP embeddings pa zithunzi {{done}}/{{total}}",
  "dedup.embedFailed": "Zalephera kukwerengera embeddings",
  "dedup.embedPartial": "{{done}}/{{total}} zidakwerengedwa ({{failed}} zalephera)",
  "dedup.embedCancelled": "Kukwerengera kwaletsedwa",
  "dedup.resolveFailed": "Zalephera kugwiritsa ntchito zisankho za dedup",
  "dedup.resolveSuccess": "Zisankho za dedup zagwiritsidwa ntchito",
  "export.basicAugHint":
    "Yambitsani Expert mode mu Zokonda kuti muwongole zosintha zithunzi zapamwamba.",
  "taxonomy.roadSubtitle":
    "Mawu othandizira a mkhalidwe wa njira ndi magulu a msewu.",
  "taxonomy.agriSubtitle":
    "Mitundu ya zomera ndi mkhalidwe wa thanzi la zomera pa kusanthula ulimi.",
  "taxonomy.loadFailed":
    "Zalephera kutsegula mitundu. Onani kulumikizana kwanu ndipo yesaninso.",
  "training.title": "Kuphunzitsa Modeli",
  "training.subtitle": "Konzani ndi kuyambitsa ntchito zophunzitsa pa ma dataset osanthulidwa",
  "training.configTitle": "Kukonzekera Kuphunzitsa",
  "training.modelName": "Dzina la Modeli",
  "training.modelNameHelp": "Dzina la chinthu cha modeli yophunzitsidwa",
  "training.modelNamePlaceholder": "mwachitsanzo road-seg-v3",
  "training.modelType": "Mtundu wa Modeli",
  "training.dataset": "Dataset",
  "training.noneSelected": "(palibe yomwe yasankhidwa)",
  "training.datasetHelp": "Zosanthulidwa kuchokera ku dataset iyi zidzagwiritsidwa ntchito pophunzitsa",
  "training.epochs": "Ma Epoch",
  "training.epochsHelp": "Chiwerengero cha ma epoch (50–300 zimakhalitsidwa)",
  "training.batchSize": "Kukula kwa Batch",
  "training.batchSizeHelp": "Zitsanzo pa batch (zambiri = mwachangu koma memory yambiri)",
  "training.learningRate": "Mlingo Wophunzira",
  "training.learningRateHelp": "Mlingo woyambira wophunzira (0.001 ndi woyenera)",
  "training.starting": "Ikuyamba...",
  "training.startTraining": "Yambitsani Kuphunzitsa",
  "training.historyTitle": "Mbiri ya Kuphunzitsa",
  "training.liveBadge": "MOYO",
  "training.loading": "Ikutsegula...",
  "training.noJobs": "Palibe ntchito zophunzitsa pano. Konzani imodzi pamwambapa.",
  "training.loadFailed": "Zalephera kutsegula ntchito zophunzitsa.",
  "training.modelsLoadFailed": "Zalephera kutsegula ma model omwe agwiritsidwa ntchito.",
  "training.selectDatasetFirst": "Sankhani dataset kaye",
  "training.submitSuccess": "Ntchito yophunzitsa yatumizidwa bwino",
  "training.submitFailed": "Zalephera kuyambitsa kuphunzitsa. Onani ID ya dataset.",
  "training.deploySuccess": "Modeli yagwiritsidwa ntchito ku registry",
  "training.deployFailed": "Zalephera kugwiritsa ntchito modeli",
  "training.activateSuccess": "Modeli yayambitsidwa",
  "training.activateFailed": "Zalephera kuyambitsa modeli",
  "training.statusPending": "Ikudikira",
  "training.statusRunning": "Ikuyenda",
  "training.statusCompleted": "Yatha",
  "training.statusFailed": "Yalephera",
  "training.mapScore": "mAP: {{value}}%",
  "training.errorShort": "Cholakwika",
  "training.deployed": "Yagwiritsidwa Ntchito",
  "training.deploying": "Ikugwiritsidwa ntchito...",
  "training.deploy": "Gwiritsani Ntchito",
  "training.modelsTitle": "Ma Model Omwe Agwiritsidwa Ntchito",
  "training.noModels":
    "Palibe ma model omwe agwiritsidwa ntchito pano. Gwiritsani ntchito ntchito yophunzitsa yomwe yatha pamwambapa.",
  "training.active": "Yogwira Ntchito",
  "training.inactive": "Yosagwira Ntchito",
  "training.activating": "Ikuyambitsa...",
  "training.activate": "Yambitsani",
  "training.modelTypes.road_segmentation": "Kugawa Msewu (YOLOv8-seg)",
  "training.modelTypes.agri_crop_classification": "Kudziwa Mbewu za Ulimi (YOLOv8-seg)",
  "training.modelTypes.agri_health_classification": "Kudziwa Thanzi la Mbewu (YOLOv8-seg)",
  "training.modelTypes.object_detection": "Kuzindikira Zinthu (YOLOv8)",
  "training.modelTypes.classification": "Kudziwa Mtundu wa Chithunzi",
  "sidebar.loadFailed": "Zalephera kutsegula mndandanda wa zithunzi.",
  "sidebar.empty": "Palibe zithunzi mu dataset iyi pano.",
  "upload.datasetLocked": "Dataset (kuchokera ku njira yomwe ili)",
  "upload.datasetLockedHint":
    "Zotsitsidwa zimapita ku dataset yomwe ikugwira ntchito. Sinthani ma dataset kuchokera pamwambapa kuti musinthe chomwe mukufuna.",
  "queue.subtitle": "Landirani ndi kumaliza ntchito zosanthula.",
  "admin.datasetId": "ID ya Dataset",
  "admin.annotatorPicker": "Anthu Olemba",
  "admin.annotatorPickerHelp": "Sankhani wolemba mmodzi kapena angapo pa ntchitoyi.",
  "admin.annotatorsLoading": "Ikutsitsa anthu olemba...",
  "admin.annotatorsLoadFailed": "Zalephera kutsegula mndandanda wa anthu olemba.",
  "admin.noAnnotators": "Palibe anthu olemba omwe akugwira ntchito.",
  "admin.cancel": "Letsani",
  "admin.newAssignment": "+ Ntchito Yatsopano",
  "admin.creating": "Ikupanga...",
  "admin.createButton": "Pangani Ntchito",
  "admin.assignSuccess": "Ntchito yapangidwa bwino!",
  "admin.assignFailed": "Zalephera kupanga ntchito.",
  "admin.loading": "Ikutsitsa ntchito...",
  "admin.empty": "Palibe ntchito pano. Pangani imodzi kuti muyambe.",
  "roadSegmentation.subtitle":
    "Pezani ndi kudziwa zovuta pa msewu (madzenje, ming'alu, mtundu wa msewu)",
  "roadSegmentation.active": "Yogwira Ntchito",
  "roadSegmentation.inactive": "Yosagwira Ntchito",
  "roadSegmentation.drawingMode": "Njira Yojambula",
  "roadSegmentation.selectMode": "Njira Yosankha",
  "roadSegmentation.noInstancesYet": "Palibe chomwe chinapezeka pano.",
  "roadSegmentation.noInstancesHint":
    "Dinani \"Auto-Segment\" kuti muwunike msewu.",
  "roadSegmentation.processing": "Ikukonza msewu...",
  "roadSegmentation.total": "Zonse",
  "roadSegmentation.acceptedLabel": "Zavomerezeka",
  "roadSegmentation.rejectedLabel": "Zakanidwa",
  "roadSegmentation.goodRoadLabel": "Msewu Wabwino",
  "roadSegmentation.accept": "Vomerezani",
  "roadSegmentation.reject": "Kanani",
  "agriAnalysis.title": "Kuwunika Thanzi la Mbewu",
  "agriAnalysis.loading": "Ikufufuza deta ya munda...",
  "agriAnalysis.failed": "Zalephera kutsegula kuwunika kwa ulimi",
  "agriAnalysis.healthScore": "Mlingo wa Thanzi",
  "agriAnalysis.weedPressure": "Kulemera kwa Udzu",
  "agriAnalysis.pestRisk": "Ngozi ya Tizilombo",
  "agriAnalysis.imagesAnalyzed": "Zithunzi Zowunika",
  "agriAnalysis.cropBreakdown": "Kugawika kwa Mtundu wa Mbewu",
  "agriAnalysis.healthBreakdown": "Kugawika kwa Mkhalidwe wa Thanzi",
  "agriAnalysis.recommendedAction": "Zoyenera Kuchita",
  "agriAnalysis.noData": "Lowetsani ID ya dataset kuti muwunike mkhalidwe wa munda.",
  "agriAnalysis.good": "Zabwino",
  "agriAnalysis.fair": "Zamphanvu",
  "agriAnalysis.poor": "Zovuta",
  "fleet.title": "Malo a Node",
  "fleet.total": "Zonse",
  "fleet.online": "Pa Intaneti",
  "fleet.offlineDegraded": "Popanda Intaneti/Zovuta",
  "fleet.alerts": "Machenjezo",
  "fleet.refresh": "Tsitsani",
  "fleet.nodes": "Malo",
  "fleet.loading": "Ikutsegula...",
  "fleet.loadFailed": "Zalephera kutsegula malo a node. Onani kulumikizana kwanu.",
  "fleet.emptyTitle": "Palibe ma node omwe agwiritsidwa ntchito pano.",
  "fleet.emptyBody":
    "Mukamakhazikitsa ndi kulembetsa zida, ma node adzawonekera pano.",
  "fleet.enabled": "Yayambitsidwa",
  "fleet.disabled": "Yaletsedwa",
  "fleet.selectNode": "Sankhani node kuti muone tsatanetsatane",
  "fleet.district": "Boma",
  "fleet.category": "Gulu",
  "fleet.position": "Malo",
  "fleet.positionUnknown": "—",
  "fleet.lastHeartbeat": "Kumenya Kwakutha kwa Mtima",
  "fleet.never": "Palibe",
  "fleet.activeAlerts": "Machenjezo Ogwira Ntchito",
  "fleet.telemetryTitle": "Chowonera Moyo / Telemetry",
  "fleet.noTelemetry":
    "Palibe deta ya telemetry. Tikudikira kumenya kwoyamba kwa mtima...",
  "fleet.liveFeedPlaceholder":
    "Chowonera cha kamera cha moyo chidzawonekera pano mukakhala pa intaneti.",
  "fleet.management": "Kuwongolera",
  "fleet.updateFirmware": "Sinthani Firmware",
  "fleet.emergencyUpload": "Kukweza Mofulumira",
  "fleet.reboot": "Yambitsaninso",
  "fleet.throttle": "Chepetsani",
  "fleet.cmdConfirm":
    "Tumizani \"{{label}}\" ku node {{nodeId}}? Sizithe kubwezeredwa.",
  "fleet.cmdSending": "Ikutumiza {{cmd}}...",
  "fleet.cmdQueued": "Lamulo \"{{cmd}}\" lalowa m'mndandanda",
  "fleet.cmdFailed": "Zalephera kutumiza lamulo",
  "fleet.alertsPanel": "Machenjezo",
  "fleet.noAlerts": "Palibe machenjezo ogwira ntchito",
  "liveAnnotate.offlineBlocked":
    "Simungasunge popanda intaneti — lumikizaninso ndipo yesaninso.",
  ...PHASE12_NY,
};

function flatten(obj, prefix = "") {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === "object" && !Array.isArray(v)) {
      Object.assign(out, flatten(v, key));
    } else {
      out[key] = v;
    }
  }
  return out;
}

function setNested(obj, dotPath, value) {
  const parts = dotPath.split(".");
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const p = parts[i];
    if (!(p in cur) || typeof cur[p] !== "object" || cur[p] === null) {
      cur[p] = {};
    }
    cur = cur[p];
  }
  cur[parts[parts.length - 1]] = value;
}

function loadJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function saveJson(path, data) {
  writeFileSync(path, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

function ensureKeys(locale, keyValues) {
  let added = 0;
  const flat = flatten(locale);
  for (const [key, value] of Object.entries(keyValues)) {
    if (!(key in flat)) {
      setNested(locale, key, value);
      added++;
    }
  }
  return added;
}

function main() {
  const en = loadJson(EN_PATH);
  const ny = loadJson(NY_PATH);

  const enBefore = Object.keys(flatten(en)).length;
  const nyBefore = Object.keys(flatten(ny)).length;

  const phase12AddedEn = ensureKeys(en, PHASE12_EN);
  const phase12AddedNy = ensureKeys(ny, PHASE12_NY);

  const enFlat = flatten(en);
  const nyFlat = flatten(ny);
  const missing = Object.keys(enFlat).filter((k) => !(k in nyFlat));

  let addedToNy = 0;
  const untranslated = [];

  for (const key of missing) {
    const translation = CHICHEWA[key];
    if (!translation) {
      untranslated.push(key);
      continue;
    }
    setNested(ny, key, translation);
    addedToNy++;
  }

  if (untranslated.length > 0) {
    console.error("Missing Chichewa translations for:");
    for (const k of untranslated) console.error(`  - ${k}`);
    process.exit(1);
  }

  saveJson(EN_PATH, en);
  saveJson(NY_PATH, ny);

  const enAfter = Object.keys(flatten(en)).length;
  const nyAfter = Object.keys(flatten(ny)).length;
  const stillMissing = Object.keys(flatten(en)).filter((k) => !(k in flatten(ny)));

  console.log("=== i18n sync complete ===");
  console.log(`Phase 12 keys added to en.json: ${phase12AddedEn}`);
  console.log(`Phase 12 keys added to ny.json: ${phase12AddedNy}`);
  console.log(`Keys added to ny.json (Chichewa): ${addedToNy}`);
  console.log(`en.json: ${enBefore} → ${enAfter} keys`);
  console.log(`ny.json: ${nyBefore} → ${nyAfter} keys`);
  console.log(
    stillMissing.length === 0
      ? "Parity: ✓ en and ny have identical key sets"
      : `Parity: ✗ ${stillMissing.length} keys still missing from ny.json`,
  );
}

main();
