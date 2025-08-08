import { useState, useEffect } from 'react';

export const useWebSocket = (onMessage) => {
  const [connected, setConnected] = useState(false);
  const [ws, setWs] = useState(null);

  useEffect(() => {
    const WS_URL = process.env.REACT_APP_WS_URL || 
      (window.location.hostname === 'localhost' && window.location.port === '3000' ? 
        'ws://localhost:8000/ws' : 
        `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`);
    const websocket = new WebSocket(WS_URL);

    websocket.onopen = () => {
      setConnected(true);
      setWs(websocket);
    };

    websocket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      onMessage(message);
    };

    websocket.onclose = () => {
      setConnected(false);
      setWs(null);
    };

    websocket.onerror = (error) => {
      console.warn('WebSocket connection error - this is normal if backend is not running');
    };

    return () => {
      websocket.close();
    };
  }, []);

  return { connected, ws };
};
