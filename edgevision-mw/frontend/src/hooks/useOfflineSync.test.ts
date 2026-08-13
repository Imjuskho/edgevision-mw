import { describe, it, expect } from "vitest";
import { computeBackoffMs, isReadyForRetry, MAX_RETRIES } from "../hooks/useOfflineSync";

describe("computeBackoffMs", () => {
  it("respects retry-after header seconds", () => {
    const delay = computeBackoffMs(0, 5);
    expect(delay).toBeGreaterThanOrEqual(5000);
    expect(delay).toBeLessThan(5600);
  });

  it("grows exponentially with retry count", () => {
    const d0 = computeBackoffMs(0);
    const d3 = computeBackoffMs(3);
    expect(d3).toBeGreaterThan(d0);
  });

  it("caps at 60 seconds", () => {
    const delay = computeBackoffMs(20);
    expect(delay).toBeLessThanOrEqual(75_000);
  });
});

describe("isReadyForRetry", () => {
  it("blocks when max retries exceeded", () => {
    expect(isReadyForRetry({ retryCount: MAX_RETRIES })).toBe(false);
  });

  it("blocks until nextRetryAt", () => {
    const future = new Date(Date.now() + 60_000);
    expect(isReadyForRetry({ retryCount: 1, nextRetryAt: future })).toBe(false);
  });

  it("allows when nextRetryAt elapsed", () => {
    const past = new Date(Date.now() - 1000);
    expect(isReadyForRetry({ retryCount: 1, nextRetryAt: past })).toBe(true);
  });
});
