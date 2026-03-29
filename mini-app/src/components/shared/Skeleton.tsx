/** Skeleton loading placeholders using the shimmer animation from globals.css. */

interface SkeletonLineProps {
  height?: number;
  width?: string;
  className?: string;
}

export function SkeletonLine({ height = 16, width = "100%", className = "" }: SkeletonLineProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ height, width }}
    />
  );
}

interface SkeletonBlockProps {
  height: number;
  className?: string;
}

export function SkeletonBlock({ height, className = "" }: SkeletonBlockProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ height, width: "100%", borderRadius: 12 }}
    />
  );
}
