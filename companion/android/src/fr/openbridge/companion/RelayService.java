package fr.openbridge.companion;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;

/** Keeps the OpenBridge relay socket alive while the app is not on screen.
 *  Headless by design: the relay serves the paired PC (pairing, controls, polls,
 *  owner-queued commands) with a NOOP screen sink; opening the app re-attaches
 *  the live UI to the same relay instance. Started/stopped only by explicit
 *  owner action in MainActivity; START_STICKY so a killed process resumes serving
 *  without silently dropping the pairing. Voice capture and TTS stay foreground-only. */
public class RelayService extends Service {
    static final String ACTION_START = "fr.openbridge.companion.RELAY_START";
    static final String ACTION_STOP = "fr.openbridge.companion.RELAY_STOP";
    static final String CHANNEL = "openbridge-relay";
    static final int NOTIF_ID = 41;

    static void start(Context ctx) {
        Intent i = new Intent(ctx, RelayService.class).setAction(ACTION_START);
        ctx.startForegroundService(i);
    }

    static void stop(Context ctx) {
        ctx.startService(new Intent(ctx, RelayService.class).setAction(ACTION_STOP));
    }

    static boolean running(Context ctx) {
        android.app.ActivityManager am = (android.app.ActivityManager) ctx.getSystemService(Context.ACTIVITY_SERVICE);
        if (am == null) return false;
        for (android.app.ActivityManager.RunningServiceInfo s : am.getRunningServices(64)) {
            if (RelayService.class.getName().equals(s.service.getClassName())) return true;
        }
        return false;
    }

    @Override public void onCreate() {
        super.onCreate();
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) nm.createNotificationChannel(
                new NotificationChannel(CHANNEL, "OpenBridge relay", NotificationManager.IMPORTANCE_MIN));
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            RelayServer.get(this, null).stop();
            stopForeground(STOP_FOREGROUND_REMOVE);
            stopSelf();
            return START_NOT_STICKY;
        }
        Notification note = new Notification.Builder(this, CHANNEL)
                .setContentTitle("OpenBridge relay running")
                .setContentText("Your paired PC can reach this device while the app is closed.")
                .setSmallIcon(android.R.drawable.sym_def_app_icon)
                .setOngoing(true)
                .build();
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIF_ID, note, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
        } else {
            startForeground(NOTIF_ID, note);
        }
        RelayServer.get(this, null).start();   // idempotent: same socket the UI uses
        return START_STICKY;
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public void onDestroy() {
        try { RelayServer.get(this, null).stop(); } catch (Exception ignored) { }
        super.onDestroy();
    }
}
