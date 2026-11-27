package fr.openbridge.companion;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

/** Home screen widget: the glasses' state and Back / Open / Next / Oracle buttons, without opening the app. */
public class GlassesWidget extends AppWidgetProvider {
    static final String PREFIX = "fr.openbridge.companion.WIDGET_";

    private static int id(Context c, String name, String type) { return c.getResources().getIdentifier(name, type, c.getPackageName()); }

    @Override public void onUpdate(Context c, AppWidgetManager m, int[] ids) { update(c, m, ids); }

    static void refreshAll(Context c) {
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        int[] ids = m.getAppWidgetIds(new ComponentName(c, GlassesWidget.class));
        if (ids.length > 0) update(c, m, ids);
    }

    private static PendingIntent press(Context c, String ev) {
        Intent i = new Intent(c, GlassesWidget.class).setAction(PREFIX + ev);
        return PendingIntent.getBroadcast(c, ev.hashCode(), i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private static void update(Context c, AppWidgetManager m, int[] ids) {
        L.init(c);
        GlassesLink g = RelayServer.get(c, null).glasses();
        boolean ready = "READY".equals(g.state());
        RemoteViews v = new RemoteViews(c.getPackageName(), id(c, "widget_glasses", "layout"));
        v.setTextViewText(id(c, "w_state", "id"), (ready ? "● " : "○ ") + L.t(ready ? "Glasses connected" : "Glasses not connected"));
        v.setTextViewText(id(c, "w_back", "id"), L.t("Back"));
        v.setTextViewText(id(c, "w_ok", "id"), L.t("Open"));
        v.setTextViewText(id(c, "w_next", "id"), L.t("Next"));
        v.setTextViewText(id(c, "w_oracle", "id"), L.t("Oracle"));
        v.setOnClickPendingIntent(id(c, "w_back", "id"), press(c, "back"));
        v.setOnClickPendingIntent(id(c, "w_ok", "id"), press(c, "ok"));
        v.setOnClickPendingIntent(id(c, "w_next", "id"), press(c, "next"));
        v.setOnClickPendingIntent(id(c, "w_oracle", "id"), PendingIntent.getActivity(c, 8,
                new Intent(c, OracleVoiceActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK), PendingIntent.FLAG_IMMUTABLE));
        v.setOnClickPendingIntent(id(c, "w_state", "id"), PendingIntent.getActivity(c, 9,
                new Intent(c, GlassesActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK), PendingIntent.FLAG_IMMUTABLE));
        for (int i : ids) m.updateAppWidget(i, v);
    }

    @Override public void onReceive(Context c, Intent i) {
        String a = i.getAction();
        if (a != null && a.startsWith(PREFIX)) {
            String ev = a.substring(PREFIX.length());
            GlassesLink g = RelayServer.get(c, null).glasses();
            if ("READY".equals(g.state())) g.button(ev);
            refreshAll(c);
            return;
        }
        super.onReceive(c, i);
    }
}
