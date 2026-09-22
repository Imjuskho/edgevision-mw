import { describe, expect, it } from "vitest";
import { getHomePersonaConfig, resolveHomePersona } from "./homePersona";

describe("homePersona", () => {
  it("maps annotator role to annotator persona", () => {
    expect(resolveHomePersona("ANNOTATOR")).toBe("ANNOTATOR");
    const config = getHomePersonaConfig("ANNOTATOR");
    expect(config.showQueue).toBe(true);
    expect(config.primaryAction).toBe("label");
  });

  it("maps QA role to QA persona with review ops", () => {
    expect(resolveHomePersona("QA")).toBe("QA");
    const config = getHomePersonaConfig("QA");
    expect(config.showReviewOps).toBe(true);
    expect(config.primaryAction).toBe("review");
  });

  it("maps operator to fleet-first persona", () => {
    const config = getHomePersonaConfig("OPERATOR");
    expect(config.showFleet).toBe(true);
    expect(config.showIngestion).toBe(true);
    expect(config.primaryAction).toBe("fleet");
  });

  it("maps field tech to fleet-only surface", () => {
    const config = getHomePersonaConfig("FIELD_TECH");
    expect(config.showFleet).toBe(true);
    expect(config.showQueue).toBe(false);
  });

  it("maps buyer to marketplace browse persona", () => {
    const config = getHomePersonaConfig("BUYER");
    expect(config.showMarketplacePlaceholder).toBe(false);
    expect(config.primaryAction).toBe("browse");
  });
});
