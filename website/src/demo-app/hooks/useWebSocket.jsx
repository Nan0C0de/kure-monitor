import { useState, useEffect, useRef, useCallback } from 'react';

export const useWebSocket = (onMessage) => {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const onMessageRef = useRef(onMessage);
  const reconnectTimeoutRef = useRef(null);
  const isConnectingRef = useRef(false);
  // Set to true by the effect cleanup before calling close(); read by the
  // socket's onclose handler so an intentional unmount/HMR/StrictMode
  // double-invoke does not schedule a reconnect against a torn-down hook.
  const intentionalCloseRef = useRef(false);

  // Keep the callback ref updated
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current || (wsRef.current && wsRef.current.readyState === WebSocket.OPEN)) {
      return;
    }

    isConnectingRef.current = true;

    // Cookie auth: the browser attaches the `kure_session` cookie automatically
    // for same-origin connections. In dev the frontend talks cross-origin to
    // localhost:8000, so we rely on CORS (handled by the backend).
    const WS_URL = undefined ||
      (window.location.hostname === 'localhost' && window.location.port === '3000' ?
        'ws://localhost:8000/ws' :
        `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`);

    const websocket = new WebSocket(WS_URL);
    // Track the socket immediately so the cleanup function can close it even
    // if the connection is still pending when the component unmounts.
    wsRef.current = websocket;

    websocket.onopen = () => {
      isConnectingRef.current = false;
      setConnected(true);
    };

    websocket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        // Use the ref to always get the current callback
        if (onMessageRef.current) {
          onMessageRef.current(message);
        }
      } catch (e) {
        console.error('Error parsing WebSocket message:', e);
      }
    };

    websocket.onclose = () => {
      isConnectingRef.current = false;
      setConnected(false);
      wsRef.current = null;

      // If the close was triggered by effect cleanup (unmount/HMR/StrictMode),
      // do NOT schedule a reconnect — the hook is going away.
      if (intentionalCloseRef.current) {
        return;
      }

      // Attempt to reconnect after 5 seconds
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, 5000);
    };

    websocket.onerror = () => {
      isConnectingRef.current = false;
      console.warn('WebSocket connection error - this is normal if backend is not running');
    };
  }, []);

  useEffect(() => {
    // Fresh mount (or remount after StrictMode double-invoke): allow
    // server-side closes to drive reconnects again.
    intentionalCloseRef.current = false;
    connect();

    return () => {
      // Clear any pending reconnect
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      // Flag must be set BEFORE close() so the synchronous (or async) onclose
      // handler sees the intentional-close signal.
      intentionalCloseRef.current = true;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { connected, ws: wsRef.current };
};
