import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ToastProvider } from "./components/ui/Toast";
import "./styles/studio.css";

function resolveThemePref(raw: string | undefined): string {
  if (raw === "system" || raw === "dark" || raw === "light" || raw === "high-contrast") return raw;
  return "dark";
}

function applyThemeFromStorage() {
  try {
    const raw = localStorage.getItem("studio_settings_v2");
    if (raw) {
      const parsed = JSON.parse(raw) as { personal?: { theme?: string } };
      const pref = resolveThemePref(parsed.personal?.theme);
      const resolved =
        pref === "system"
          ? window.matchMedia("(prefers-color-scheme: light)").matches
            ? "light"
            : "dark"
          : pref;
      document.documentElement.setAttribute("data-theme", resolved);
      return;
    }
  } catch {
    // fall through
  }
  document.documentElement.setAttribute("data-theme", "dark");
}

applyThemeFromStorage();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ToastProvider>
      <App />
    </ToastProvider>
  </React.StrictMode>,
);
