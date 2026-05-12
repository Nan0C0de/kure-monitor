import { useEffect } from 'react';

/**
 * Selector matching focusable elements inside a dialog. Mirrors the WAI-ARIA
 * authoring practices guidance for modal dialogs.
 */
const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  '[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const getFocusable = (container) => {
  if (!container) return [];
  return Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR)).filter(
    (el) => !el.hasAttribute('disabled') && el.tabIndex !== -1
  );
};

/**
 * useModalA11y — minimal a11y plumbing for modal dialogs.
 *
 * When `isOpen` is truthy:
 *  - Escape key calls `onClose()`.
 *  - On open, focus moves to the first focusable element inside `dialogRef.current`.
 *  - Tab / Shift+Tab cycles focus within the dialog (focus trap).
 *
 * The dialog wrapper itself (the centered card) should carry `ref={dialogRef}`,
 * `role="dialog"`, and `aria-modal="true"`. The backdrop should NOT be the
 * trap container.
 */
export default function useModalA11y({ isOpen, onClose, dialogRef }) {
  // Escape to close.
  useEffect(() => {
    if (!isOpen) return undefined;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        if (typeof onClose === 'function') onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Initial focus.
  useEffect(() => {
    if (!isOpen) return;
    // Defer a tick so the dialog DOM is mounted.
    const id = setTimeout(() => {
      const focusable = getFocusable(dialogRef && dialogRef.current);
      if (focusable.length > 0) {
        try {
          focusable[0].focus();
        } catch {
          /* ignore */
        }
      } else if (dialogRef && dialogRef.current) {
        // Fall back: focus the dialog wrapper itself so SR users hear it.
        try {
          dialogRef.current.setAttribute('tabindex', '-1');
          dialogRef.current.focus();
        } catch {
          /* ignore */
        }
      }
    }, 0);
    return () => clearTimeout(id);
  }, [isOpen, dialogRef]);

  // Focus trap.
  useEffect(() => {
    if (!isOpen) return undefined;
    const handleKeyDown = (e) => {
      if (e.key !== 'Tab') return;
      const container = dialogRef && dialogRef.current;
      if (!container) return;
      const focusable = getFocusable(container);
      if (focusable.length === 0) {
        e.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !container.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, dialogRef]);
}
