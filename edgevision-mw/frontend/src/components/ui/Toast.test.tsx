import { describe, expect, it, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToastProvider, useToast } from "./Toast";

afterEach(() => cleanup());

function TriggerToast() {
  const { showToast } = useToast();
  return <button onClick={() => showToast("Saved successfully", "success")}>Trigger</button>;
}

function ToastA11yHarness() {
  return (
    <ToastProvider>
      <TriggerToast />
    </ToastProvider>
  );
}

describe("Toast accessibility", () => {
  it("container has aria-live='polite' and aria-relevant='additions'", () => {
    const { container } = render(<ToastA11yHarness />);
    const toastContainer = container.querySelector(".ui-toast-container");
    expect(toastContainer).toBeTruthy();
    expect(toastContainer!.getAttribute("aria-live")).toBe("polite");
    expect(toastContainer!.getAttribute("aria-relevant")).toBe("additions");
  });

  it("container is always present in the DOM (not conditional)", () => {
    const { container } = render(<ToastA11yHarness />);
    const toastContainer = container.querySelector(".ui-toast-container");
    expect(toastContainer).toBeTruthy();
    expect(toastContainer!.children.length).toBe(0);
  });

  it("toast item has role='alert' when shown", async () => {
    const user = userEvent.setup();
    const { container } = render(<ToastA11yHarness />);
    const btn = screen.getByRole("button", { name: "Trigger" });
    await user.click(btn);
    const alert = container.querySelector("[role='alert']");
    expect(alert).toBeTruthy();
  });
});
