import { useState, useRef, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  TAXONOMY_CATEGORIES,
  getCategoryColor,
} from "../constants/taxonomy";
import { AGRI_CROP_DISPLAY_NAMES, AGRI_HEALTH_DISPLAY_NAMES } from "../constants/agriTaxonomy";
import { toStyle } from "../utils/toStyle";

interface Props {
  value: string;
  onChange: (label: string) => void;
  taxonomyContext?: "road" | "agri";
}

interface FlatItem {
  type: "category" | "label";
  label?: string;
  name?: string;
  categoryId?: string;
  categoryName?: string;
  color?: string;
  edgeCases?: string;
}

const AGRI_CROP_TYPES = Object.keys(AGRI_CROP_DISPLAY_NAMES);
const AGRI_HEALTH_TYPES = Object.keys(AGRI_HEALTH_DISPLAY_NAMES);

export default function LabelSelector({ value, onChange, taxonomyContext = "road" }: Props) {
  const { i18n, t } = useTranslation();
  const agriLang = i18n.language.startsWith("ny") ? "ny" : "en";
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [focusedIdx, setFocusedIdx] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const currentColor = taxonomyContext === "agri" ? "#4CAF50" : getCategoryColor(value);

  const flatItems = useMemo(() => {
    if (taxonomyContext === "agri") {
      const items: FlatItem[] = [];
      const crops = AGRI_CROP_TYPES.filter((c) => c.includes(search.toLowerCase()));
      if (crops.length > 0) {
        items.push({ type: "category", categoryId: "agri_crops", categoryName: "🌾 Crop Types", color: "#4CAF50" });
        for (const c of crops) {
          items.push({ type: "label", label: c, name: AGRI_CROP_DISPLAY_NAMES[c]?.[agriLang] || c, color: "#4CAF50" });
        }
      }
      const health = AGRI_HEALTH_TYPES.filter((h) => h.includes(search.toLowerCase()));
      if (health.length > 0) {
        items.push({ type: "category", categoryId: "agri_health", categoryName: "🧬 Health Conditions", color: "#FF9800" });
        for (const h of health) {
          items.push({ type: "label", label: h, name: AGRI_HEALTH_DISPLAY_NAMES[h]?.[agriLang] || h, color: "#FF9800" });
        }
      }
      return items;
    }
    const items: FlatItem[] = [];
    for (const cat of TAXONOMY_CATEGORIES) {
      const filtered = cat.classes.filter(
        (c) =>
          c.label.includes(search.toLowerCase()) ||
          c.name.toLowerCase().includes(search.toLowerCase())
      );
      if (filtered.length === 0) continue;
      items.push({
        type: "category",
        categoryId: cat.id,
        categoryName: `${cat.icon} ${cat.name}`,
        color: cat.color,
      });
      for (const cls of filtered) {
        items.push({
          type: "label",
          label: cls.label,
          name: cls.name,
          categoryId: cat.id,
          categoryName: cat.name,
          color: cat.color,
          edgeCases: cls.edgeCases,
        });
      }
    }
    return items;
  }, [search, taxonomyContext, agriLang]);

  const labelItems = flatItems.filter((i) => i.type === "label");

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "l" && !e.ctrlKey && !e.metaKey && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  useEffect(() => {
    if (open && searchRef.current) searchRef.current.focus();
    setFocusedIdx(-1);
  }, [open, search]);

  useEffect(() => {
    if (focusedIdx < 0 || !listRef.current) return;
    const el = listRef.current.querySelector(`[data-idx="${focusedIdx}"]`);
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [focusedIdx]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setOpen(false);
      setSearch("");
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setFocusedIdx((prev) => {
        let next = prev + 1;
        while (next < labelItems.length && !labelItems[next]) next++;
        return next < labelItems.length ? next : prev;
      });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setFocusedIdx((prev) => {
        let next = prev - 1;
        while (next >= 0 && !labelItems[next]) next--;
        return next >= 0 ? next : prev;
      });
    } else if (e.key === "Enter" && focusedIdx >= 0 && focusedIdx < labelItems.length) {
      const item = labelItems[focusedIdx];
      if (item?.label) {
        onChange(item.label);
        setOpen(false);
        setSearch("");
      }
    }
  };

  const currentName = taxonomyContext === "agri"
    ? (AGRI_CROP_DISPLAY_NAMES[value]?.[agriLang] || AGRI_HEALTH_DISPLAY_NAMES[value]?.[agriLang] || value)
    : TAXONOMY_CATEGORIES.flatMap((c) => c.classes).find((c) => c.label === value)?.name || value;

  return (
    <div ref={containerRef} className="label-selector">
      <button
        className="label-selector-trigger"
        style={toStyle({ "--label-color": currentColor })}
        onClick={() => setOpen(!open)}
        onKeyDown={(e) => {
          if (e.key === "l" && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            setOpen((o) => !o);
          }
        }}
        title={t("annotation.labelPickerShortcut")}
        aria-label={t("annotation.labelPickerShortcut")}
      >
        <span className="label-selector-dot" />
        <span className="label-selector-label">{currentName}</span>
        <span className="label-selector-shortcut">L</span>
      </button>

      {open && (
        <div className="label-selector-dropdown" onKeyDown={handleKeyDown}>
          <div className="label-selector-search-wrap">
            <input
              ref={searchRef}
              type="text"
              className="label-selector-search"
              placeholder="Search labels..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setFocusedIdx(-1);
              }}
            />
          </div>

          <div ref={listRef} className="label-selector-list">
            {flatItems.length === 0 && (
              <div className="label-selector-empty">
                No labels found for "{search}"
              </div>
            )}

            {flatItems.map((item, idx) => {
              if (item.type === "category") {
                return (
                  <div
                    key={`cat-${item.categoryId}`}
                    className={`label-selector-category${idx > 0 ? " label-selector-category--bordered" : ""}`}
                    style={toStyle({ "--category-color": item.color })}
                  >
                    {item.categoryName}
                  </div>
                );
              }

              const isSelected = item.label === value;
              const isFocused = idx === focusedIdx;

              return (
                <button
                  key={item.label}
                  data-idx={idx}
                  className={`label-selector-item${isSelected ? " label-selector-item--selected" : ""}${isFocused ? " label-selector-item--focused" : ""}`}
                  style={toStyle({ "--item-color": item.color })}
                  onClick={() => {
                    onChange(item.label!);
                    setOpen(false);
                    setSearch("");
                  }}
                >
                  <span className="label-selector-item-dot" />
                  <span className="label-selector-item-name">{item.name}</span>
                  <span className="label-selector-item-code">{item.label}</span>
                </button>
              );
            })}
          </div>

          <div className="label-selector-footer">
            <span>{labelItems.length} labels</span>
            <span>↑↓ navigate · Enter select · Esc close</span>
          </div>
        </div>
      )}
    </div>
  );
}
