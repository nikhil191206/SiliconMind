/**
 * Adds `.is-visible` to every `.reveal` element inside the returned ref once
 * it scrolls into view (the fade/slide-up entrance used across the landing
 * page). Runs once per element; respects reduced motion via CSS.
 */
import { useEffect, useRef } from "react";

export function useReveal<T extends HTMLElement = HTMLElement>() {
  const ref = useRef<T | null>(null);
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const targets = root.querySelectorAll<HTMLElement>(".reveal");
    if (!("IntersectionObserver" in window)) {
      targets.forEach((t) => t.classList.add("is-visible"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add("is-visible");
            io.unobserve(e.target);
          }
        }
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.1 },
    );
    targets.forEach((t) => io.observe(t));
    return () => io.disconnect();
  }, []);
  return ref;
}
