import React from "react";
import { render, act } from "@testing-library/react";
import { useWebSocket } from "../useWebSocket";

// Minimal fake WebSocket that records instances and lets tests fire lifecycle
// events imperatively.
class FakeWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static instances = [];

  constructor(url) {
    this.url = url;
    this.readyState = 0; // CONNECTING
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    this.closeCalls = 0;
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.closeCalls += 1;
    this.readyState = FakeWebSocket.CLOSED;
    // Mirror real browser behaviour: closing a socket fires onclose.
    if (this.onclose) this.onclose({});
  }

  // Helpers for tests to drive the socket from "outside".
  _open() {
    this.readyState = FakeWebSocket.OPEN;
    if (this.onopen) this.onopen({});
  }

  _serverClose() {
    this.readyState = FakeWebSocket.CLOSED;
    if (this.onclose) this.onclose({});
  }
}

const Harness = () => {
  useWebSocket(() => {});
  return null;
};

describe("useWebSocket", () => {
  let originalWS;

  beforeEach(() => {
    originalWS = global.WebSocket;
    global.WebSocket = FakeWebSocket;
    FakeWebSocket.instances = [];
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
    global.WebSocket = originalWS;
  });

  test("opens a socket on mount", () => {
    render(<Harness />);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  test("cleanup-triggered close does NOT schedule a reconnect", () => {
    const { unmount } = render(<Harness />);
    expect(FakeWebSocket.instances).toHaveLength(1);
    const first = FakeWebSocket.instances[0];
    act(() => {
      first._open();
    });

    act(() => {
      unmount();
    });

    // Effect cleanup should have called close() once, and the close handler
    // must NOT schedule a reconnect. Advancing past the reconnect delay
    // should therefore not create any new sockets.
    expect(first.closeCalls).toBe(1);
    act(() => {
      jest.advanceTimersByTime(10000);
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  test("server-side close schedules a reconnect", () => {
    render(<Harness />);
    expect(FakeWebSocket.instances).toHaveLength(1);
    const first = FakeWebSocket.instances[0];
    act(() => {
      first._open();
    });

    // Server drops the connection.
    act(() => {
      first._serverClose();
    });

    // Reconnect is scheduled 5s later.
    act(() => {
      jest.advanceTimersByTime(5000);
    });
    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2);
  });
});
