import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export interface FabricZoomApi {
  zoom: number;
  zoomIn: () => void;
  zoomOut: () => void;
  resetZoom: () => void;
  fitToScreen: () => void;
  isSpacePressed: boolean;
  isPanning: boolean;
}

interface FabricCanvasZoomContextValue {
  api: FabricZoomApi | null;
  register: (api: FabricZoomApi | null) => void;
}

const FabricCanvasZoomContext = createContext<FabricCanvasZoomContextValue | null>(
  null,
);

export function FabricCanvasZoomProvider({ children }: { children: ReactNode }) {
  const [api, setApi] = useState<FabricZoomApi | null>(null);
  const register = useCallback((next: FabricZoomApi | null) => {
    setApi(next);
  }, []);

  const value = useMemo(() => ({ api, register }), [api, register]);

  return (
    <FabricCanvasZoomContext.Provider value={value}>
      {children}
    </FabricCanvasZoomContext.Provider>
  );
}

export function useFabricCanvasZoomRegistry() {
  const ctx = useContext(FabricCanvasZoomContext);
  if (!ctx) {
    throw new Error("useFabricCanvasZoomRegistry requires FabricCanvasZoomProvider");
  }
  return ctx;
}

export function useOptionalFabricCanvasZoomApi(): FabricZoomApi | null {
  return useContext(FabricCanvasZoomContext)?.api ?? null;
}
