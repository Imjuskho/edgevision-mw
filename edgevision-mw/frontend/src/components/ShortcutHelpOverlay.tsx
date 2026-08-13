import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { ShortcutHint } from "./KeyboardShortcuts";

interface Props {
  open: boolean;
  onClose: () => void;
  isAdmin: boolean;
}

interface ShortcutRow {
  keys: string[];
  labelKey: string;
  adminOnly?: boolean;
}

const SHORTCUT_ROWS: ShortcutRow[] = [
  { keys: ["1"], labelKey: "shortcuts.annotate" },
  { keys: ["2"], labelKey: "shortcuts.upload" },
  { keys: ["3"], labelKey: "shortcuts.queue" },
  { keys: ["4"], labelKey: "shortcuts.assign", adminOnly: true },
  { keys: ["5"], labelKey: "shortcuts.review", adminOnly: true },
  { keys: ["6"], labelKey: "shortcuts.agriAnnotate" },
  { keys: ["7"], labelKey: "shortcuts.segment" },
  { keys: ["8"], labelKey: "shortcuts.roadAnalysis" },
  { keys: ["9"], labelKey: "shortcuts.fleet" },
  { keys: ["0"], labelKey: "shortcuts.training" },
  { keys: ["H"], labelKey: "shortcuts.health" },
  { keys: ["D"], labelKey: "shortcuts.dedup" },
  { keys: ["E"], labelKey: "shortcuts.export" },
  { keys: ["C"], labelKey: "shortcuts.liveAnnotate" },
  { keys: ["Esc"], labelKey: "shortcuts.escape" },
  { keys: ["L"], labelKey: "shortcuts.labelPicker" },
  { keys: ["?"], labelKey: "shortcuts.toggleHelp" },
];

export function ShortcutHelpOverlay({ open, onClose, isAdmin }: Props) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const rows = SHORTCUT_ROWS.filter((row) => !row.adminOnly || isAdmin);

  return (
    <div className="shortcut-overlay-backdrop" onClick={onClose} role="presentation">
      <div
        className="shortcut-overlay-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcut-help-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="shortcut-overlay-header">
          <h2 id="shortcut-help-title">{t("shortcuts.title")}</h2>
          <button type="button" className="shortcut-overlay-close" onClick={onClose} aria-label={t("shortcuts.close")}>
            ×
          </button>
        </div>
        <p className="shortcut-overlay-hint">{t("shortcuts.hint")}</p>
        <ul className="shortcut-overlay-list">
          {rows.map((row) => (
            <li key={row.labelKey}>
              <ShortcutHint keys={row.keys} />
              <span>{t(row.labelKey)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
