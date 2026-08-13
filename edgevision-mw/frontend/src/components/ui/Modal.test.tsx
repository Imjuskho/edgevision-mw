import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Modal } from "./Modal";

describe("Modal", () => {
  it("keeps input focus while parent re-renders with new onClose", async () => {
    const user = userEvent.setup();
    let renderCount = 0;

    function Wrapper() {
      const [name, setName] = useState("");
      renderCount += 1;
      return (
        <Modal open onClose={() => undefined} title="Create dataset">
          <input
            aria-label="Dataset name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Modal>
      );
    }

    render(<Wrapper />);
    const input = screen.getByLabelText("Dataset name");
    await user.click(input);
    expect(input).toHaveFocus();

    await user.type(input, "abc");
    expect(input).toHaveFocus();
    expect(renderCount).toBeGreaterThan(1);
    expect(input).toHaveValue("abc");
  });
});
