import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.aidispatch.engine',
  appName: 'AI Dispatch',
  webDir: 'dist',
  server: {
    // For local dev: point to your backend. Change to your deployed URL for production.
    // androidScheme: 'https',
    // url: 'http://YOUR_SERVER_IP:8000',  // uncomment for live-reload dev on device
  },
  plugins: {
    StatusBar: {
      style: 'dark',
      backgroundColor: '#111827',
    },
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
    Geolocation: {
      // iOS requires description strings in Info.plist (added automatically by cap add ios)
    },
  },
  ios: {
    contentInset: 'automatic',
  },
  android: {
    allowMixedContent: true,
  },
};

export default config;
