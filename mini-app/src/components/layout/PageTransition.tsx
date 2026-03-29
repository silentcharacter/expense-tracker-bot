import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

interface PageTransitionProps {
  children: ReactNode;
  pageKey: string;
}

/** Wraps page content and triggers a slide-in animation on route change. */
export function PageTransition({ children, pageKey }: PageTransitionProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.classList.remove("page-enter");
    // Force reflow to restart animation
    void el.offsetWidth;
    el.classList.add("page-enter");
  }, [pageKey]);

  return (
    <div ref={ref} className="page-content page-enter">
      {children}
    </div>
  );
}
