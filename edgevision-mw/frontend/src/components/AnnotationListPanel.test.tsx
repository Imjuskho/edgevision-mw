import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BBox } from "../types";
import { IconButton } from "./ui/IconButton";
import { Trash2 } from "lucide-react";

afterEach(() => cleanup());

function AnnotationListPanel({
  boxes,
  onDelete,
}: {
  boxes: BBox[];
  onDelete: (index: number) => void;
}) {
  return (
    <div role="list" aria-label="Current annotations">
      {boxes.length === 0 && (
        <p>No annotations yet.</p>
      )}
      {boxes.map((box, i) => (
        <div
          key={i}
          role="listitem"
          className="annotate-annotation-list-item"
          tabIndex={0}
          aria-label={`${box.label}, x:${Math.round(box.x * 100)}% y:${Math.round(box.y * 100)}% w:${Math.round(box.width * 100)}% h:${Math.round(box.height * 100)}%`}
        >
          <span className="annotate-annotation-list-label">{box.label}</span>
          <span className="annotate-annotation-list-coords">
            {Math.round(box.x * 100)},{Math.round(box.y * 100)} {Math.round(box.width * 100)}×{Math.round(box.height * 100)}%
          </span>
          <IconButton
            label="Delete annotation"
            size="sm"
            onClick={() => onDelete(i)}
          >
            <Trash2 size={12} />
          </IconButton>
        </div>
      ))}
    </div>
  );
}

const makeBox = (label: string, x = 0.1, y = 0.2): BBox => ({
  x,
  y,
  width: 0.3,
  height: 0.4,
  label,
  confidence: 0.9,
});

describe("AnnotationListPanel accessibility", () => {
  it("renders with role='list' and aria-label", () => {
    render(<AnnotationListPanel boxes={[makeBox("car")]} onDelete={vi.fn()} />);
    const list = screen.getByRole("list");
    expect(list).toBeTruthy();
    expect(list.getAttribute("aria-label")).toBeTruthy();
  });

  it("renders one listitem per annotation", () => {
    render(
      <AnnotationListPanel
        boxes={[makeBox("car"), makeBox("truck", 0.5, 0.5)]}
        onDelete={vi.fn()}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
  });

  it("each listitem has an aria-label with label and coords", () => {
    render(<AnnotationListPanel boxes={[makeBox("car", 0.1, 0.2)]} onDelete={vi.fn()} />);
    const item = screen.getByRole("listitem");
    const ariaLabel = item.getAttribute("aria-label") ?? "";
    expect(ariaLabel).toContain("car");
    expect(ariaLabel).toContain("10%");
    expect(ariaLabel).toContain("20%");
  });

  it("shows label text in the list item", () => {
    render(<AnnotationListPanel boxes={[makeBox("pedestrian")]} onDelete={vi.fn()} />);
    expect(screen.getByText("pedestrian")).toBeTruthy();
  });

  it("shows empty state when no boxes", () => {
    render(<AnnotationListPanel boxes={[]} onDelete={vi.fn()} />);
    expect(screen.queryByRole("listitem")).toBeNull();
    expect(screen.getByText("No annotations yet.")).toBeTruthy();
  });

  it("delete button calls onDelete with correct index", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    render(
      <AnnotationListPanel
        boxes={[makeBox("car"), makeBox("truck"), makeBox("bus")]}
        onDelete={onDelete}
      />,
    );
    const deleteButtons = screen.getAllByRole("button", { name: "Delete annotation" });
    await user.click(deleteButtons[1]);
    expect(onDelete).toHaveBeenCalledWith(1);
  });

  it("listitem is focusable via keyboard", () => {
    render(<AnnotationListPanel boxes={[makeBox("car")]} onDelete={vi.fn()} />);
    const item = screen.getByRole("listitem");
    expect(item.getAttribute("tabindex")).toBe("0");
  });
});
