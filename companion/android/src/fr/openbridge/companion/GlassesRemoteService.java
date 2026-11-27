package fr.openbridge.companion;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.graphics.drawable.Icon;
import android.media.VolumeProvider;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.IBinder;

/** Glasses remote that stays on: Next / Open / Back / Home in the notification and on the lock screen, and the
 *  phone's volume keys as next / back even with the screen off (a media session with remote volume, which Android
 *  routes the volume keys to). Started and stopped by the owner from the Glasses page. */
public class GlassesRemoteService extends Service {
    static final String CHANNEL = "glasses_remote", PREFIX = "fr.openbridge.companion.GLASSES_";
    static final int NOTIF_ID = 42;
    private static volatile boolean running;
    private MediaSession session;

    static boolean running(Context c) { return running; }

    static void start(Context c) { c.startForegroundService(new Intent(c, GlassesRemoteService.class)); }
    static void stop(Context c) { c.stopService(new Intent(c, GlassesRemoteService.class)); }

    @Override public void onCreate() {
        super.onCreate();
        L.init(this);
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) nm.createNotificationChannel(new NotificationChannel(CHANNEL, L.t("Glasses remote"), NotificationManager.IMPORTANCE_LOW));
        session = new MediaSession(this, "openbridge-glasses");
        session.setPlaybackToRemote(new VolumeProvider(VolumeProvider.VOLUME_CONTROL_RELATIVE, 100, 50) {
            @Override public void onAdjustVolume(int direction) {
                if (direction > 0) press("next");
                else if (direction < 0) press("back");
            }
        });
        session.setPlaybackState(new PlaybackState.Builder().setState(PlaybackState.STATE_PLAYING, 0, 1f)
                .setActions(PlaybackState.ACTION_PLAY_PAUSE | PlaybackState.ACTION_SKIP_TO_NEXT | PlaybackState.ACTION_SKIP_TO_PREVIOUS).build());
        session.setCallback(new MediaSession.Callback() {
            @Override public void onSkipToNext() { press("next"); }
            @Override public void onSkipToPrevious() { press("back"); }
            @Override public void onPlay() { press("ok"); }
            @Override public void onPause() { press("ok"); }
        });
        session.setActive(true);
        running = true;
    }

    private void press(String ev) { RelayServer.get(this, null).glasses().button(ev); }

    private Notification.Action action(String ev, String label, int icon) {
        Intent i = new Intent(this, GlassesRemoteService.class).setAction(PREFIX + ev);
        PendingIntent pi = PendingIntent.getService(this, ev.hashCode(), i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Action.Builder(Icon.createWithResource(this, icon), label, pi).build();
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        String a = intent == null ? null : intent.getAction();
        if (a != null && a.startsWith(PREFIX)) {
            press(a.substring(PREFIX.length()).toLowerCase(java.util.Locale.ROOT));
            return START_STICKY;
        }
        PendingIntent open = PendingIntent.getActivity(this, 1, new Intent(this, GlassesActivity.class), PendingIntent.FLAG_IMMUTABLE);
        int small = getResources().getIdentifier("ic_glasses", "drawable", getPackageName());
        Notification n = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(small != 0 ? small : android.R.drawable.ic_menu_view)
                .setContentTitle(L.t("Glasses remote"))
                .setContentText(L.t("Volume up = next, volume down = back"))
                .setContentIntent(open)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setOngoing(true)
                .addAction(action("back", L.t("Back"), android.R.drawable.ic_media_previous))
                .addAction(action("ok", L.t("Open"), android.R.drawable.ic_media_play))
                .addAction(action("next", L.t("Next"), android.R.drawable.ic_media_next))
                .addAction(action("home", L.t("Home"), android.R.drawable.ic_menu_revert))
                .setStyle(new Notification.MediaStyle().setMediaSession(session.getSessionToken()).setShowActionsInCompactView(0, 1, 2))
                .build();
        if (Build.VERSION.SDK_INT >= 29) startForeground(NOTIF_ID, n, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
        else startForeground(NOTIF_ID, n);
        return START_STICKY;
    }

    @Override public IBinder onBind(Intent i) { return null; }

    @Override public void onDestroy() {
        running = false;
        if (session != null) { session.setActive(false); session.release(); }
        super.onDestroy();
    }
}
