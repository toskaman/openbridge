package fr.openbridge.companion;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

/** Keeps the phone's sensors (GPS, compass, sport sensors) running for the glasses while the app is in the
 *  background, with a visible notification. Started and stopped only by the owner (Sensors page). */
public class SensorService extends Service {
    static final String CHANNEL = "phone_sensors";
    static final int NOTIF_ID = 43;
    private static volatile boolean running;

    static boolean running() { return running; }
    static void start(Context c) { c.startForegroundService(new Intent(c, SensorService.class)); }
    static void stop(Context c) { c.stopService(new Intent(c, SensorService.class)); }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        L.init(this);
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) nm.createNotificationChannel(new NotificationChannel(CHANNEL, L.t("Phone sensors"), NotificationManager.IMPORTANCE_LOW));
        int small = getResources().getIdentifier("ic_glasses", "drawable", getPackageName());
        Notification n = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(small != 0 ? small : android.R.drawable.ic_menu_mylocation)
                .setContentTitle(L.t("Phone sensors on"))
                .setContentText(L.t("GPS, compass and sport sensors for your glasses"))
                .setContentIntent(PendingIntent.getActivity(this, 2, new Intent(this, SensorsActivity.class), PendingIntent.FLAG_IMMUTABLE))
                .setOngoing(true).build();
        int type = ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE;
        if (PhoneSensors.get(this).locationPermission()) type |= ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION;
        if (Build.VERSION.SDK_INT >= 29) startForeground(NOTIF_ID, n, type); else startForeground(NOTIF_ID, n);
        PhoneSensors.get(this).start();
        running = true;
        return START_STICKY;
    }

    @Override public IBinder onBind(Intent i) { return null; }

    @Override public void onDestroy() {
        running = false;
        PhoneSensors.get(this).stop();
        super.onDestroy();
    }
}
