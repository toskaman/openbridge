package fr.openbridge.companion;

import android.app.Notification;
import android.content.ComponentName;
import android.content.Context;
import android.os.Bundle;
import android.os.Parcelable;
import android.provider.Settings;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/**
 * Messages for the ENGO glasses: reads the notifications of the messaging apps the owner allowed (Discord, Telegram,
 * SMS / Messages) once the owner has granted notification access in Android settings.
 *
 * Only sender, text, app and time are kept, in memory, at most MAX items; they leave the phone only to the paired
 * PC, over the signed and encrypted relay, when it asks with the get_notifications op. Nothing is stored on disk,
 * nothing is answered or dismissed on the owner's behalf.
 */
public class NotifListener extends NotificationListenerService {
    static final Set<String> APPS = new HashSet<>(Arrays.asList(
            "com.discord", "org.telegram.messenger", "org.telegram.messenger.web", "org.thunderdog.challegram",
            "com.google.android.apps.messaging", "com.samsung.android.messaging", "com.android.mms",
            "com.android.messaging", "com.whatsapp", "org.thoughtcrime.securesms"));
    private static final int MAX = 50, MAX_SENDER = 40, MAX_TEXT = 400;
    private static final ArrayDeque<JSONObject> queue = new ArrayDeque<>();

    static android.content.SharedPreferences filter(Context c) { return c.getSharedPreferences("notif_filter", Context.MODE_PRIVATE); }

    /** Apps whose messages reach the glasses: the owner's choice (Settings), or the messaging apps above by default. */
    static Set<String> chosen(Context c) {
        Set<String> s = filter(c).getStringSet("apps", null);
        return s == null ? APPS : s;
    }
    static boolean allowed(Context c, String pkg) { return pkg != null && chosen(c).contains(pkg); }

    /** Quiet hours: nothing reaches the glasses between "from" and "to" (minutes of the day), when switched on. */
    static boolean quiet(Context c) {
        android.content.SharedPreferences f = filter(c);
        if (!f.getBoolean("quiet", false)) return false;
        java.util.Calendar k = java.util.Calendar.getInstance();
        int now = k.get(java.util.Calendar.HOUR_OF_DAY) * 60 + k.get(java.util.Calendar.MINUTE);
        int from = f.getInt("quiet_from", 22 * 60), to = f.getInt("quiet_to", 7 * 60);
        return from <= to ? now >= from && now < to : now >= from || now < to;
    }

    /** True once the owner has allowed notification access for this app in Android settings. */
    static boolean accessGranted(Context ctx) {
        String flat = Settings.Secure.getString(ctx.getContentResolver(), "enabled_notification_listeners");
        return flat != null && flat.contains(new ComponentName(ctx, NotifListener.class).flattenToString());
    }

    /** Hands the queued messages to the paired PC and forgets them. */
    static synchronized JSONArray drain() {
        JSONArray out = new JSONArray();
        while (!queue.isEmpty()) out.put(queue.poll());
        return out;
    }

    private static synchronized void offer(JSONObject o) {
        queue.add(o);
        while (queue.size() > MAX) queue.poll();
    }

    private static String clip(CharSequence s, int max) {
        if (s == null) return "";
        String t = s.toString().replaceAll("\\p{Cntrl}", " ").replaceAll("\\s+", " ").trim();
        return t.length() > max ? t.substring(0, max) : t;
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        try {
            if (sbn == null || !allowed(this, sbn.getPackageName())) return;
            RelayServer relay = RelayServer.get(this, null);
            if (!relay.module("messages") || "off".equals(Profiles.notifMode(this)) || quiet(this)) return;
            Notification n = sbn.getNotification();
            if (n == null || (n.flags & Notification.FLAG_GROUP_SUMMARY) != 0 || sbn.isOngoing()) return;
            Bundle x = n.extras;
            if (x == null) return;
            CharSequence sender = x.getCharSequence(Notification.EXTRA_TITLE);
            CharSequence text = x.getCharSequence(Notification.EXTRA_BIG_TEXT);
            if (text == null) text = x.getCharSequence(Notification.EXTRA_TEXT);
            Parcelable[] msgs = x.getParcelableArray(Notification.EXTRA_MESSAGES);   // MessagingStyle: newest last
            if (msgs != null && msgs.length > 0 && msgs[msgs.length - 1] instanceof Bundle) {
                Bundle last = (Bundle) msgs[msgs.length - 1];
                CharSequence t = last.getCharSequence("text"), who = last.getCharSequence("sender");
                if (t != null) text = t;
                if (who != null) {
                    CharSequence conv = x.getCharSequence(Notification.EXTRA_CONVERSATION_TITLE);
                    sender = conv != null ? who + " · " + conv : who;
                }
            }
            String s = clip(sender, MAX_SENDER), body = clip(text, MAX_TEXT);
            if (s.isEmpty() && body.isEmpty()) return;
            if ("private".equals(Profiles.notifMode(this)) || filter(this).getBoolean("private", false)) body = "New message";   // the PC shows it as hidden
            JSONObject o = new JSONObject().put("package", sbn.getPackageName()).put("sender", s).put("text", body)
                    .put("time", sbn.getPostTime() / 1000.0);
            if (getSharedPreferences("ai", MODE_PRIVATE).getBoolean("summaries", false) && body.length() > 140 && LocalAi.llmReady(this)) {
                final String full = body;              // a long message: two short lines for the glasses, made on the phone
                new Thread(() -> {
                    try { String sum = LocalAi.summarise(this, full); if (sum != null && !sum.trim().isEmpty()) o.put("text", sum.trim()).put("summary", true); }
                    catch (Exception ignored) { }
                    offer(o);
                    if (StandaloneHub.enabled(this)) StandaloneHub.get(this).message(o);
                }, "notif-summary").start();
                return;
            }
            offer(o);
            if (StandaloneHub.enabled(this)) StandaloneHub.get(this).message(o);
        } catch (Exception ignored) {
            // A malformed notification is skipped; it never stops the listener.
        }
    }
}
