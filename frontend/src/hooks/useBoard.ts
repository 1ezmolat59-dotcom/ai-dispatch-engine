import { useEffect, useRef, useState, useCallback } from "react";
import type { BoardSnapshot } from "../api/client";

type Status = "connecting" | "open" | "closed" | "error";

export function useBoard() {
  const [board, setBoard] = useState<BoardSnapshot | null>(null);
  const [status, setStatus] = useState<Status>("connecting");
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const connect = useCallback(() => {  // eslint-disable-line react-hooks/exhaustive-deps
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`ws://${window.location.hostname}:8000/ws/board`);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("open");
      // keepalive ping every 30s
      const ping = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send("ping"), 30_000);
      ws.addEventListener("close", () => clearInterval(ping));
    };

    ws.onmessage = (e) => {
      try {
        const snap: BoardSnapshot = JSON.parse(e.data);
        if (snap.snapshot_id) {          // ignore "pong" strings
          setBoard(snap);
          setLastUpdate(new Date());
        }
      } catch {/* ignore malformed frames */}
    };

    ws.onerror = () => setStatus("error");

    ws.onclose = () => {
      setStatus("closed");
      // Auto-reconnect after 3 s
      reconnectTimer.current = setTimeout(connect, 3_000);
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { board, status, lastUpdate };
}
