import { useEffect, useRef, useState } from 'react';

/**
 * Counts a figure up to its target once, on mount.
 *
 * Used only on the stat rail. A dashboard whose headline numbers snap into
 * existence reads as a screenshot; a short count tells the analyst the figures
 * were just computed. It runs once — subsequent live updates jump straight to
 * the new value, because a number that re-animates every poll is noise.
 *
 * Respects `prefers-reduced-motion`, in which case the final value renders
 * immediately with no intermediate frames.
 *
 * :param target: the value to settle on.
 * :param durationMs: total run time; capped short so the rail settles fast.
 * :returns: the current value to render.
 */
export function useCountUp(target: number, durationMs = 450): number {
  const [value, setValue] = useState(target);
  const hasRun = useRef(false);

  useEffect(() => {
    if (hasRun.current) {
      setValue(target);
      return;
    }
    hasRun.current = true;

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || target === 0) {
      setValue(target);
      return;
    }

    let frame = 0;
    const start = performance.now();

    const step = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      // Matches --ease-out: decelerate into place.
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(target * eased);
      if (t < 1) frame = requestAnimationFrame(step);
    };

    setValue(0);
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs]);

  return value;
}
