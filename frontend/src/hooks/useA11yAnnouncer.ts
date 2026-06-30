import { useEffect, useRef, useCallback } from 'react';

/**
 * Returns an announce() function that pushes messages into a visually-hidden
 * aria-live="polite" region so screen readers announce new content without
 * requiring the user to navigate to the updated element.
 */
export function useA11yAnnouncer() {
  const regionRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = document.createElement('div');
    el.setAttribute('aria-live', 'polite');
    el.setAttribute('aria-atomic', 'true');
    el.setAttribute('aria-relevant', 'additions text');
    // Visually hidden but accessible to screen readers
    el.style.cssText =
      'position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0';
    document.body.appendChild(el);
    regionRef.current = el;
    return () => {
      document.body.removeChild(el);
    };
  }, []);

  const announce = useCallback((message: string) => {
    if (!regionRef.current) return;
    // Clear then set triggers re-announcement even for identical messages
    regionRef.current.textContent = '';
    requestAnimationFrame(() => {
      if (regionRef.current) regionRef.current.textContent = message;
    });
  }, []);

  return { announce };
}
