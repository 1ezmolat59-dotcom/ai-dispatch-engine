import { useEffect } from "react";
import { Capacitor } from "@capacitor/core";
import { PushNotifications } from "@capacitor/push-notifications";

/**
 * Registers the device for push notifications on native platforms.
 * Call once at app startup. Notifications display job assignments and ETAs.
 */
export function usePushNotifications() {
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    async function register() {
      const result = await PushNotifications.requestPermissions();
      if (result.receive !== "granted") return;

      await PushNotifications.register();

      PushNotifications.addListener("registration", (token) => {
        // Send token to your backend: POST /api/v1/technicians/{id}/push-token
        console.log("Push token:", token.value);
      });

      PushNotifications.addListener("pushNotificationReceived", (notification) => {
        console.log("Push received:", notification);
      });

      PushNotifications.addListener("pushNotificationActionPerformed", (action) => {
        console.log("Push action:", action);
        // Navigate to the relevant job when user taps the notification
      });
    }

    register();
  }, []);
}
