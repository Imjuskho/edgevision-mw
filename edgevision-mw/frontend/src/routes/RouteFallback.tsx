import { Skeleton, SkeletonCard } from "../components/Skeleton";

/** Suspense fallback matching the studio content-area layout. */
export function RouteFallback() {
  return (
    <div className="route-fallback">
      <Skeleton className="ui-skeleton--route-title" />
      <div className="route-fallback__grid">
        <SkeletonCard />
        <SkeletonCard />
      </div>
      <Skeleton className="ui-skeleton--route-body" />
    </div>
  );
}
