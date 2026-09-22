import { describe, expect, it } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useState, useCallback, useRef } from "react";
import { shallowEqualBoxes, cloneBoxes } from "../utils/shallowEqualBoxes";
import type { BBox } from "../types";

const UNDO_MAX = 50;

const box = (overrides: Partial<BBox> = {}): BBox => ({
  x: 0.1,
  y: 0.2,
  width: 0.3,
  height: 0.4,
  label: "car_private",
  confidence: 0.9,
  ...overrides,
});

function useUndoRedoHarness(initialBoxes: BBox[] = []) {
  const [boxes, setBoxes] = useState<BBox[]>(initialBoxes);
  const undoStackRef = useRef<BBox[][]>([]);
  const redoStackRef = useRef<BBox[][]>([]);

  const pushUndo = useCallback((currentBoxes: BBox[]) => {
    undoStackRef.current = [...undoStackRef.current.slice(-(UNDO_MAX - 1)), cloneBoxes(currentBoxes)];
    redoStackRef.current = [];
  }, []);

  const recordChange = useCallback((prev: BBox[], next: BBox[]) => {
    if (!shallowEqualBoxes(prev, next)) {
      pushUndo(prev);
    }
  }, [pushUndo]);

  const undo = useCallback(() => {
    const stack = undoStackRef.current;
    if (stack.length === 0) return;
    const prev = stack[stack.length - 1];
    undoStackRef.current = stack.slice(0, -1);
    redoStackRef.current = [...redoStackRef.current.slice(-(UNDO_MAX - 1)), cloneBoxes(boxes)];
    setBoxes(prev);
  }, [boxes]);

  const redo = useCallback(() => {
    const stack = redoStackRef.current;
    if (stack.length === 0) return;
    const next = stack[stack.length - 1];
    redoStackRef.current = stack.slice(0, -1);
    undoStackRef.current = [...undoStackRef.current.slice(-(UNDO_MAX - 1)), cloneBoxes(boxes)];
    setBoxes(next);
  }, [boxes]);

  const editBoxes = useCallback((updater: (prev: BBox[]) => BBox[]) => {
    setBoxes((prev) => {
      const next = updater(prev);
      recordChange(prev, next);
      return next;
    });
  }, [recordChange]);

  return {
    boxes,
    editBoxes,
    undo,
    redo,
    undoStackSize: () => undoStackRef.current.length,
    redoStackSize: () => redoStackRef.current.length,
  };
}

describe("Annotation undo/redo logic", () => {
  it("undo reverts to previous state after a change", () => {
    const { result } = renderHook(() => useUndoRedoHarness([box()]));

    act(() => {
      result.current.editBoxes((prev) => [...prev, box({ label: "truck", x: 0.5 })]);
    });
    expect(result.current.boxes).toHaveLength(2);

    act(() => {
      result.current.undo();
    });
    expect(result.current.boxes).toHaveLength(1);
    expect(result.current.boxes[0].label).toBe("car_private");
  });

  it("redo restores state after undo", () => {
    const { result } = renderHook(() => useUndoRedoHarness([box()]));

    act(() => {
      result.current.editBoxes((prev) => [...prev, box({ label: "truck" })]);
    });
    expect(result.current.boxes).toHaveLength(2);

    act(() => {
      result.current.undo();
    });
    expect(result.current.boxes).toHaveLength(1);

    act(() => {
      result.current.redo();
    });
    expect(result.current.boxes).toHaveLength(2);
    expect(result.current.boxes[1].label).toBe("truck");
  });

  it("new change clears redo stack", () => {
    const { result } = renderHook(() => useUndoRedoHarness([box()]));

    act(() => {
      result.current.editBoxes((prev) => [...prev, box({ label: "truck" })]);
    });
    act(() => {
      result.current.undo();
    });
    expect(result.current.redoStackSize()).toBe(1);

    act(() => {
      result.current.editBoxes((prev) => [...prev, box({ label: "bus" })]);
    });
    expect(result.current.redoStackSize()).toBe(0);
  });

  it("undo on empty stack is a no-op", () => {
    const { result } = renderHook(() => useUndoRedoHarness([box()]));
    act(() => {
      result.current.undo();
    });
    expect(result.current.boxes).toHaveLength(1);
    expect(result.current.boxes[0].label).toBe("car_private");
  });

  it("redo on empty stack is a no-op", () => {
    const { result } = renderHook(() => useUndoRedoHarness([box()]));
    act(() => {
      result.current.redo();
    });
    expect(result.current.boxes).toHaveLength(1);
  });

  it("undo cap: 51st push evicts oldest entry", () => {
    const { result } = renderHook(() => useUndoRedoHarness([box()]));

    for (let i = 0; i < 51; i++) {
      act(() => {
        result.current.editBoxes((prev) => [...prev, box({ label: `box_${i}`, x: i * 0.01 })]);
      });
    }
    expect(result.current.undoStackSize()).toBe(UNDO_MAX);

    for (let i = 0; i < UNDO_MAX; i++) {
      act(() => {
        result.current.undo();
      });
    }
    expect(result.current.boxes).toHaveLength(2);
    expect(result.current.boxes[1].label).toBe("box_0");

    act(() => {
      result.current.undo();
    });
    expect(result.current.boxes).toHaveLength(2);
  });

  it("multiple undo/redo cycles preserve correctness", () => {
    const { result } = renderHook(() => useUndoRedoHarness([box()]));

    act(() => {
      result.current.editBoxes((prev) => [...prev, box({ label: "second" })]);
    });
    act(() => {
      result.current.editBoxes((prev) => [...prev, box({ label: "third" })]);
    });
    expect(result.current.boxes).toHaveLength(3);

    act(() => { result.current.undo(); });
    act(() => { result.current.undo(); });
    expect(result.current.boxes).toHaveLength(1);

    act(() => { result.current.redo(); });
    expect(result.current.boxes).toHaveLength(2);
    expect(result.current.boxes[1].label).toBe("second");

    act(() => { result.current.redo(); });
    expect(result.current.boxes).toHaveLength(3);
    expect(result.current.boxes[2].label).toBe("third");
  });

  it("cloneBoxes produces deep copies in the undo stack", () => {
    const { result } = renderHook(() => useUndoRedoHarness([box({ polygon: [[0, 0], [1, 0], [0.5, 1]] })]));

    act(() => {
      result.current.editBoxes((prev) => [
        { ...prev[0], label: "mutated" },
      ]);
    });
    act(() => {
      result.current.undo();
    });
    expect(result.current.boxes[0].label).toBe("car_private");
    expect(result.current.boxes[0].polygon).toEqual([[0, 0], [1, 0], [0.5, 1]]);
  });
});
