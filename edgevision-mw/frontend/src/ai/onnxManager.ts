import * as ort from "onnxruntime-web";

export interface ModelConfig {
  name: string;
  url: string;
  sizeBytes: number;
  preferredBackend: "wasm" | "webgpu";
  warmupRuns: number;
}

export const MODEL_REGISTRY: Record<string, ModelConfig> = {
  yolov8n_cls: {
    name: "yolov8n-cls",
    url: "/models/yolov8n_cls_int8.onnx",
    sizeBytes: 5_200_000,
    preferredBackend: "wasm",
    warmupRuns: 2,
  },
  mobile_sam: {
    name: "mobile-sam-encoder",
    url: "/models/mobile_sam_encoder.onnx",
    sizeBytes: 27_000_000,
    preferredBackend: "wasm",
    warmupRuns: 1,
  },
  mobile_sam_decoder: {
    name: "mobile-sam-decoder",
    url: "/models/mobile_sam_decoder.onnx",
    sizeBytes: 20_000_000,
    preferredBackend: "wasm",
    warmupRuns: 1,
  },
  clip_vit_b32: {
    name: "clip-vit-b32",
    url: "/models/clip_vit_b32.onnx",
    sizeBytes: 335_000_000,
    preferredBackend: "wasm",
    warmupRuns: 1,
  },
  yolov8n_seg: {
    name: "yolov8n-seg",
    url: "/models/yolov8n-seg-fp32.onnx",
    sizeBytes: 22_000_000,
    preferredBackend: "wasm",
    warmupRuns: 1,
  },
};

interface LoadProgress {
  modelName: string;
  loaded: number;
  total: number;
  percent: number;
}

type ProgressCallback = (p: LoadProgress) => void;

class ONNXManager {
  private sessions: Map<string, ort.InferenceSession> = new Map();
  private cache: Cache | null = null;
  private memoryLimitMB = 1536;
  private currentMemoryMB = 0;

  async init(): Promise<void> {
    ort.env.wasm.numThreads = navigator.hardwareConcurrency > 2 ? 2 : 1;
    ort.env.wasm.simd = true;
    ort.env.wasm.proxy = false;
    ort.env.wasm.wasmPaths = {
      mjs: new URL("/ort-wasm-simd-threaded.jsep.mjs", import.meta.url).href,
      wasm: new URL("/ort-wasm-simd-threaded.jsep.wasm", import.meta.url).href,
    };
    this.cache = await caches.open("edgevision-models-v1").catch(() => null);
  }

  async loadModel(
    modelKey: string,
    onProgress?: ProgressCallback,
  ): Promise<ort.InferenceSession> {
    if (this.sessions.has(modelKey)) {
      return this.sessions.get(modelKey)!;
    }

    const config = MODEL_REGISTRY[modelKey];
    if (!config) throw new Error(`Unknown model: ${modelKey}`);

    let modelBuffer: ArrayBuffer;
    const cached = await this.cache?.match(config.url);

    if (cached) {
      modelBuffer = await cached.arrayBuffer();
    } else {
      modelBuffer = await this.downloadWithProgress(config, onProgress);
      await this.cache?.put(config.url, new Response(modelBuffer));
    }

    const modelSizeMB = modelBuffer.byteLength / (1024 * 1024);
    if (this.currentMemoryMB + modelSizeMB > this.memoryLimitMB) {
      await this.evictLRU(modelSizeMB);
    }

    const session = await ort.InferenceSession.create(modelBuffer, {
      executionProviders: [config.preferredBackend],
      graphOptimizationLevel: "all",
    });

    this.sessions.set(modelKey, session);
    this.currentMemoryMB += modelSizeMB;

    await this.warmup(config, session);

    return session;
  }

  private async downloadWithProgress(
    config: ModelConfig,
    onProgress?: ProgressCallback,
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
      onProgress?.({
        modelName: config.name,
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

  private async warmup(
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

  private async evictLRU(requiredMB: number): Promise<void> {
    const entries = Array.from(this.sessions.entries());
    entries.sort(
      (a, b) => MODEL_REGISTRY[b[0]].sizeBytes - MODEL_REGISTRY[a[0]].sizeBytes,
    );

    for (const [key, session] of entries) {
      if (this.currentMemoryMB + requiredMB <= this.memoryLimitMB) break;
      await session.release();
      this.sessions.delete(key);
      this.currentMemoryMB -= MODEL_REGISTRY[key].sizeBytes / (1024 * 1024);
    }
  }

  async runInference(
    modelKey: string,
    inputs: Record<string, ort.Tensor>,
  ): Promise<ort.InferenceSession.OnnxValueMapType> {
    const session = await this.loadModel(modelKey);
    return session.run(inputs);
  }

  async unload(modelKey: string): Promise<void> {
    const session = this.sessions.get(modelKey);
    if (session) {
      await session.release();
      this.sessions.delete(modelKey);
      this.currentMemoryMB -=
        MODEL_REGISTRY[modelKey].sizeBytes / (1024 * 1024);
    }
  }

  isLoaded(modelKey: string): boolean {
    return this.sessions.has(modelKey);
  }
}

export const onnxManager = new ONNXManager();
