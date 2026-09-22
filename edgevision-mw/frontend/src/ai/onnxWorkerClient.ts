import * as ort from "onnxruntime-web";
import { MODEL_REGISTRY, type ModelConfig } from "./onnxManager";

/* ── Re-export shared types for consumer convenience ─────────────── */
export type { ModelConfig };
export { MODEL_REGISTRY };

/* ── Message protocol types (mirrored from worker) ───────────────── */

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

/* ── Public types ────────────────────────────────────────────────── */

interface LoadProgress {
  modelName: string;
  loaded: number;
  total: number;
  percent: number;
}

type ProgressCallback = (p: LoadProgress) => void;

interface PendingCall {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
  onProgress?: ProgressCallback;
}

/* ── ONNXWorkerManager ───────────────────────────────────────────── */

class ONNXWorkerManager {
  private worker: Worker | null = null;
  private pending = new Map<string, PendingCall>();
  private loadedModels = new Set<string>();
  private counter = 0;
  private initialized = false;

  constructor() {
    this.spawnWorker();
  }

  /* ── Worker lifecycle ────────────────────────────────────────── */

  private spawnWorker(): void {
    this.worker = new Worker(
      new URL("./onnxWorker.ts", import.meta.url),
      { type: "module" },
    );
    this.worker.onmessage = this.handleMessage.bind(this);
    this.worker.onerror = (e) => {
      console.error("[ONNXWorker] Worker error:", e.message);
      for (const [id, entry] of this.pending) {
        entry.reject(new Error(`Worker error: ${e.message}`));
        this.pending.delete(id);
      }
    };
  }

  terminate(): void {
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
    }
    for (const [, entry] of this.pending) {
      entry.reject(new Error("Worker terminated"));
    }
    this.pending.clear();
    this.loadedModels.clear();
    this.initialized = false;
  }

  async restart(): Promise<void> {
    this.terminate();
    this.spawnWorker();
    await this.init();
  }

  /* ── Message helpers ─────────────────────────────────────────── */

  private nextId(): string {
    this.counter += 1;
    return `msg_${this.counter}`;
  }

  private post<T>(msg: Record<string, unknown>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      if (!this.worker) {
        reject(new Error("Worker is terminated"));
        return;
      }
      this.pending.set(msg.id as string, {
        resolve: resolve as (v: unknown) => void,
        reject,
      });
      this.worker.postMessage(msg);
    });
  }

  private handleMessage(e: MessageEvent<FromWorkerMessage>): void {
    const msg = e.data;
    const entry = this.pending.get(msg.id);

    switch (msg.type) {
      case "progress":
        if (entry?.onProgress) {
          entry.onProgress({
            modelName: msg.modelKey,
            loaded: msg.loaded,
            total: msg.total,
            percent: msg.percent,
          });
        }
        break;

      case "result":
        if (entry) {
          this.pending.delete(msg.id);
          entry.resolve(msg.result);
        }
        break;

      case "error":
        if (entry) {
          this.pending.delete(msg.id);
          entry.reject(new Error(msg.error));
        }
        break;
    }
  }

  /* ── Public API (matches ONNXManager signature) ──────────────── */

  async init(): Promise<void> {
    if (this.initialized) return;
    await this.post({ id: this.nextId(), type: "init" });
    this.initialized = true;
  }

  async loadModel(
    modelKey: string,
    onProgress?: ProgressCallback,
  ): Promise<ort.InferenceSession> {
    if (this.loadedModels.has(modelKey)) {
      return undefined as unknown as ort.InferenceSession;
    }

    const id = this.nextId();

    return new Promise<ort.InferenceSession>((resolve, reject) => {
      if (!this.worker) {
        reject(new Error("Worker is terminated"));
        return;
      }

      this.pending.set(id, {
        resolve: () => {
          this.loadedModels.add(modelKey);
          resolve(undefined as unknown as ort.InferenceSession);
        },
        reject,
        onProgress,
      });

      this.worker.postMessage({ id, type: "loadModel", modelKey });
    });
  }

  async runInference(
    modelKey: string,
    inputs: Record<string, ort.Tensor>,
  ): Promise<ort.InferenceSession.OnnxValueMapType> {
    if (!this.loadedModels.has(modelKey)) {
      await this.loadModel(modelKey);
    }

    const serialized: Record<string, SerializedTensor> = {};
    for (const [key, tensor] of Object.entries(inputs)) {
      serialized[key] = {
        type: tensor.type,
        data: tensor.data as SerializedTensor["data"],
        dims: [...tensor.dims],
      };
    }

    const result = await this.post<Record<string, SerializedTensor>>({
      id: this.nextId(),
      type: "runInference",
      modelKey,
      inputs: serialized,
    });

    const outputs: Record<string, ort.Tensor> = {};
    for (const [key, tensor] of Object.entries(result)) {
      outputs[key] = new ort.Tensor(tensor.type as "float32" | "float64" | "int32" | "int8" | "uint8" | "int16" | "uint16" | "string" | "bool" | "float16" | "uint32" | "uint64" | "int64", tensor.data as ort.Tensor["data"], tensor.dims);
    }

    return outputs as ort.InferenceSession.OnnxValueMapType;
  }

  async unload(modelKey: string): Promise<void> {
    await this.post({ id: this.nextId(), type: "unload", modelKey });
    this.loadedModels.delete(modelKey);
  }

  isLoaded(modelKey: string): boolean {
    return this.loadedModels.has(modelKey);
  }
}

export const onnxWorkerManager = new ONNXWorkerManager();
