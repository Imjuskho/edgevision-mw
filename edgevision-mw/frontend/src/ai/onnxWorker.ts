import * as ort from "onnxruntime-web";
import { MODEL_REGISTRY, type ModelConfig } from "./onnxManager";

/* ── Message protocol types ──────────────────────────────────────── */

interface SerializedTensor {
  type: string;
  data:
    | Float32Array
    | Uint8Array
    | Int8Array
    | Uint16Array
    | Int16Array
    | Uint32Array
    | Int32Array
    | Float64Array
    | string[];
  dims: number[];
}

type ToWorkerMessage =
  | { id: string; type: "init" }
  | { id: string; type: "loadModel"; modelKey: string }
  | {
      id: string;
      type: "runInference";
      modelKey: string;
      inputs: Record<string, SerializedTensor>;
    }
  | { id: string; type: "unload"; modelKey: string }
  | { id: string; type: "isLoaded"; modelKey: string };

type FromWorkerMessage =
  | {
      id: string;
      type: "progress";
      modelKey: string;
      loaded: number;
      total: number;
      percent: number;
    }
  | { id: string; type: "result"; result: unknown }
  | { id: string; type: "error"; error: string };

/* ── Worker state ────────────────────────────────────────────────── */

const sessions = new Map<string, ort.InferenceSession>();
let cache: Cache | null = null;
const MEMORY_LIMIT_MB = 1536;
let currentMemoryMB = 0;

/* ── Helpers ─────────────────────────────────────────────────────── */

function post(msg: FromWorkerMessage): void {
  self.postMessage(msg);
}

function configureWasm(): void {
  ort.env.wasm.numThreads = navigator.hardwareConcurrency > 2 ? 2 : 1;
  ort.env.wasm.simd = true;
  ort.env.wasm.proxy = false;
  ort.env.wasm.wasmPaths = {
    mjs: new URL("/ort-wasm-simd-threaded.jsep.mjs", import.meta.url).href,
    wasm: new URL("/ort-wasm-simd-threaded.jsep.wasm", import.meta.url).href,
  };
}

async function downloadWithProgress(
  config: ModelConfig,
  id: string,
): Promise<ArrayBuffer> {
  const response = await fetch(config.url);
  const reader = response.body?.getReader();
  if (!reader) throw new Error("ReadableStream not supported");

  const chunks: Uint8Array[] = [];
  let received = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    post({
      id,
      type: "progress",
      modelKey: config.name,
      loaded: received,
      total: config.sizeBytes,
      percent: Math.round((received / config.sizeBytes) * 100),
    });
  }

  const all = new Uint8Array(received);
  let pos = 0;
  for (const chunk of chunks) {
    all.set(chunk, pos);
    pos += chunk.length;
  }
  return all.buffer;
}

async function warmup(
  config: ModelConfig,
  session: ort.InferenceSession,
): Promise<void> {
  const firstInput = session.inputNames[0];
  let dummy: ort.Tensor;

  if (config.name.includes("encoder") && config.name.includes("sam")) {
    dummy = new ort.Tensor(
      "float32",
      new Float32Array(3 * 1024 * 1024),
      [1, 3, 1024, 1024],
    );
  } else if (config.name.includes("decoder") && config.name.includes("sam")) {
    return;
  } else if (config.name.includes("clip")) {
    dummy = new ort.Tensor(
      "float32",
      new Float32Array(3 * 224 * 224),
      [1, 3, 224, 224],
    );
  } else if (config.name.includes("yolov8n-seg")) {
    dummy = new ort.Tensor(
      "float32",
      new Float32Array(3 * 640 * 640),
      [1, 3, 640, 640],
    );
  } else {
    dummy = new ort.Tensor(
      "float32",
      new Float32Array(3 * 224 * 224),
      [1, 3, 224, 224],
    );
  }

  for (let i = 0; i < config.warmupRuns; i++) {
    await session.run({ [firstInput]: dummy });
  }
}

async function evictLRU(requiredMB: number): Promise<void> {
  const entries = Array.from(sessions.entries());
  entries.sort(
    (a, b) => MODEL_REGISTRY[b[0]].sizeBytes - MODEL_REGISTRY[a[0]].sizeBytes,
  );

  for (const [key, session] of entries) {
    if (currentMemoryMB + requiredMB <= MEMORY_LIMIT_MB) break;
    await session.release();
    sessions.delete(key);
    currentMemoryMB -= MODEL_REGISTRY[key].sizeBytes / (1024 * 1024);
  }
}

/* ── Message handlers ────────────────────────────────────────────── */

async function handleInit(id: string): Promise<void> {
  configureWasm();
  cache = await caches.open("edgevision-models-v1").catch(() => null);
  post({ id, type: "result", result: undefined });
}

async function handleLoadModel(id: string, modelKey: string): Promise<void> {
  if (sessions.has(modelKey)) {
    post({ id, type: "result", result: { loaded: true } });
    return;
  }

  const config = MODEL_REGISTRY[modelKey];
  if (!config) throw new Error(`Unknown model: ${modelKey}`);

  let modelBuffer: ArrayBuffer;
  const cached = await cache?.match(config.url);

  if (cached) {
    modelBuffer = await cached.arrayBuffer();
    post({
      id,
      type: "progress",
      modelKey: config.name,
      loaded: config.sizeBytes,
      total: config.sizeBytes,
      percent: 100,
    });
  } else {
    modelBuffer = await downloadWithProgress(config, id);
    await cache?.put(config.url, new Response(modelBuffer));
  }

  const modelSizeMB = modelBuffer.byteLength / (1024 * 1024);
  if (currentMemoryMB + modelSizeMB > MEMORY_LIMIT_MB) {
    await evictLRU(modelSizeMB);
  }

  const session = await ort.InferenceSession.create(modelBuffer, {
    executionProviders: [config.preferredBackend],
    graphOptimizationLevel: "all",
  });

  sessions.set(modelKey, session);
  currentMemoryMB += modelSizeMB;

  await warmup(config, session);

  post({ id, type: "result", result: { loaded: true } });
}

async function handleRunInference(
  id: string,
  modelKey: string,
  inputs: Record<string, SerializedTensor>,
): Promise<void> {
  const session = sessions.get(modelKey);
  if (!session) {
    throw new Error(
      `Model "${modelKey}" is not loaded. Call loadModel first.`,
    );
  }

  const ortInputs: Record<string, ort.Tensor> = {};
  for (const [key, tensor] of Object.entries(inputs)) {
    ortInputs[key] = new ort.Tensor(tensor.type as "float32" | "float64" | "int32" | "int8" | "uint8" | "int16" | "uint16" | "string" | "bool" | "float16" | "uint32" | "uint64" | "int64", tensor.data as ort.Tensor["data"], tensor.dims);
  }

  const outputMap = await session.run(ortInputs);

  const serialized: Record<string, SerializedTensor> = {};
  for (const [key, tensor] of Object.entries(outputMap)) {
    serialized[key] = {
      type: tensor.type,
      data: tensor.data as SerializedTensor["data"],
      dims: [...tensor.dims],
    };
  }

  post({ id, type: "result", result: serialized });
}

async function handleUnload(id: string, modelKey: string): Promise<void> {
  const session = sessions.get(modelKey);
  if (session) {
    await session.release();
    sessions.delete(modelKey);
    currentMemoryMB -= MODEL_REGISTRY[modelKey].sizeBytes / (1024 * 1024);
  }
  post({ id, type: "result", result: undefined });
}

function handleIsLoaded(id: string, modelKey: string): void {
  post({ id, type: "result", result: sessions.has(modelKey) });
}

/* ── Main message handler ────────────────────────────────────────── */

self.onmessage = async (e: MessageEvent<ToWorkerMessage>): Promise<void> => {
  const msg = e.data;

  try {
    switch (msg.type) {
      case "init":
        await handleInit(msg.id);
        break;
      case "loadModel":
        await handleLoadModel(msg.id, msg.modelKey);
        break;
      case "runInference":
        await handleRunInference(msg.id, msg.modelKey, msg.inputs);
        break;
      case "unload":
        await handleUnload(msg.id, msg.modelKey);
        break;
      case "isLoaded":
        handleIsLoaded(msg.id, msg.modelKey);
        break;
      default: {
        const unknown = msg as { id: string; type: string };
        post({
          id: unknown.id,
          type: "error",
          error: `Unknown message type: ${unknown.type}`,
        });
      }
    }
  } catch (err) {
    post({
      id: msg.id,
      type: "error",
      error: err instanceof Error ? err.message : String(err),
    });
  }
};
