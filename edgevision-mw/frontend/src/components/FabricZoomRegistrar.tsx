import { useEffect } from "react";
import {
  useFabricCanvasZoomRegistry,
  type FabricZoomApi,
} from "../context/FabricCanvasZoomContext";

export function FabricZoomRegistrar({ api }: { api: FabricZoomApi }) {
  const { register } = useFabricCanvasZoomRegistry();

  useEffect(() => {
    register(api);
    return () => register(null);
  }, [api, register]);

  return null;
}
