import { studioApi } from "../services/api";
import { toStyle } from "../utils/toStyle";

interface BBox {
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  confidence: number;
}

interface Props {
  annotationId: string;
  annotations: BBox[];
}

/** Renders review image with normalized bbox overlays for visual QA. */
export function ReviewImagePreview({ annotationId, annotations }: Props) {
  const imageUrl = studioApi.serveImage(annotationId);

  return (
    <div className="review-image-preview">
      <img src={imageUrl} alt="Review target" className="review-image-preview__img" />
      <div className="review-image-preview__overlay">
        {annotations.map((ann, idx) => (
          <div
            key={idx}
            className="review-bbox"
            title={`${ann.label} (${ann.confidence.toFixed(2)})`}
            style={toStyle({
              left: `${ann.x * 100}%`,
              top: `${ann.y * 100}%`,
              width: `${ann.width * 100}%`,
              height: `${ann.height * 100}%`,
            })}
          >
            <span className="review-bbox__label">{ann.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
