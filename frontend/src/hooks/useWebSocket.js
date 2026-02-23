import { useState, useEffect, useRef, useCallback } from 'react';

export const useWebSocket = (onMessage) => {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const onMessageRef = useRef(onMessage);
  const reconnectTimeoutRef = useRef(null);
  const isConnectingRef = useRef(false);

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

    const baseWsUrl = process.env.REACT_APP_WS_URL ||
      (window.location.hostname === 'localhost' && window.location.port === '3000' ?
        'ws://localhost:8000/ws' :
        `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`);

    // Append auth token if available
    const apiKey = sessionStorage.getItem('kure-auth-key');
    const WS_URL = apiKey ? `${baseWsUrl}?token=${encodeURIComponent(apiKey)}` : baseWsUrl;

    const websocket = new WebSocket(WS_URL);

    websocket.onopen = () => {
      isConnectingRef.current = false;
      setConnected(true);
      wsRef.current = websocket;
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

      // Attempt to reconnect after 5 seconds
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, 5000);
    };

    websocket.onerror = (error) => {
      isConnectingRef.current = false;
      console.warn('WebSocket connection error - this is normal if backend is not running');
    };

    wsRef.current = websocket;
  }, []);

  useEffect(() => {
    connect();

    return () => {
      // Clear any pending reconnect
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      // Close the connection
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { connected, ws: wsRef.current };
};
