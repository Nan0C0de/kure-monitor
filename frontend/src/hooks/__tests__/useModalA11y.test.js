import React, { useRef } from 'react';
import { render, fireEvent, act } from '@testing-library/react';
import useModalA11y from '../useModalA11y';

const Dialog = ({ isOpen, onClose }) => {
  const ref = useRef(null);
  useModalA11y({ isOpen, onClose, dialogRef: ref });
  if (!isOpen) return null;
  return (
    <div ref={ref} role="dialog" aria-modal="true" aria-label="test">
      <button>First</button>
      <button>Second</button>
    </div>
  );
};

describe('useModalA11y', () => {
  test('Escape key calls onClose', () => {
    const onClose = jest.fn();
    render(<Dialog isOpen={true} onClose={onClose} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test('does not call onClose when closed', () => {
    const onClose = jest.fn();
    render(<Dialog isOpen={false} onClose={onClose} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });

  test('focuses first focusable element on open', () => {
    jest.useFakeTimers();
    const onClose = jest.fn();
    const { getByText } = render(<Dialog isOpen={true} onClose={onClose} />);
    act(() => {
      jest.runAllTimers();
    });
    expect(document.activeElement).toBe(getByText('First'));
    jest.useRealTimers();
  });
});
