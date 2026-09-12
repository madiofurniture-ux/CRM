import { useEffect, useRef } from "react";

const FOCUSABLE = 'a[href],button:not([disabled]),textarea,input,select,[tabindex]:not([tabindex="-1"])';

/**
 * Traps Tab/Shift+Tab inside the returned ref while `active` is true, focuses
 * the first focusable element on open, and returns focus to whatever had it
 * before the modal opened (the trigger button) on close.
 */
export default function useFocusTrap(active) {
  const ref = useRef(null);

  useEffect(() => {
    if (!active) return;
    const trigger = document.activeElement;
    const node = ref.current;
    const focusables = () => Array.from(node?.querySelectorAll(FOCUSABLE) || []);

    // Don't steal focus from an element that already has it (e.g. an
    // `autoFocus` input) — only step in when nothing inside is focused yet.
    if (!node?.contains(document.activeElement)) {
      (focusables()[0] || node)?.focus();
    }

    const onKeyDown = (e) => {
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      trigger?.focus?.();
    };
  }, [active]);

  return ref;
}
