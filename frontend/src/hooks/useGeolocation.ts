import { useEffect, useRef, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { Geolocation } from "@capacitor/geolocation";

export interface GeoPosition {
  latitude: number;
  longitude: number;
  accuracy: number;
}

/**
 * Provides live GPS coordinates.
 * On native (iOS/Android): uses Capacitor Geolocation plugin for high-accuracy GPS.
 * On web: falls back to browser navigator.geolocation.
 */
export function useGeolocation() {
  const [position, setPosition] = useState<GeoPosition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const watchId = useRef<string | number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function startWatch() {
      if (Capacitor.isNativePlatform()) {
        try {
          await Geolocation.requestPermissions();
          watchId.current = await Geolocation.watchPosition(
            { enableHighAccuracy: true, timeout: 10_000 },
            (pos, err) => {
              if (cancelled) return;
              if (err) { setError(err.message); return; }
              if (pos) {
                setPosition({
                  latitude: pos.coords.latitude,
                  longitude: pos.coords.longitude,
                  accuracy: pos.coords.accuracy,
                });
              }
            }
          );
        } catch (e) {
          setError(String(e));
        }
      } else {
        // Web fallback
        if (!navigator.geolocation) { setError("Geolocation not supported"); return; }
        watchId.current = navigator.geolocation.watchPosition(
          (pos) => {
            if (cancelled) return;
            setPosition({
              latitude: pos.coords.latitude,
              longitude: pos.coords.longitude,
              accuracy: pos.coords.accuracy,
            });
          },
          (err) => setError(err.message),
          { enableHighAccuracy: true }
        );
      }
    }

    startWatch();

    return () => {
      cancelled = true;
      if (Capacitor.isNativePlatform() && watchId.current != null) {
        Geolocation.clearWatch({ id: watchId.current as string });
      } else if (watchId.current != null) {
        navigator.geolocation.clearWatch(watchId.current as number);
      }
    };
  }, []);

  return { position, error };
}
