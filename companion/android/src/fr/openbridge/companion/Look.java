package fr.openbridge.companion;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** The Companion's look for the secondary pages (Glasses, Settings, Devices, Sensors, AI): same palette and shapes
 *  as the main screen, in one place so each page stays short. */
final class Look {
    static final int BG_TOP = Color.rgb(3, 5, 14), BG_BOTTOM = Color.rgb(12, 10, 30),
            GLASS = Color.argb(20, 255, 255, 255), GLASS_LINE = Color.argb(36, 255, 255, 255),
            TEXT = Color.rgb(236, 240, 255), MUTED = Color.rgb(138, 148, 182), FAINT = Color.rgb(92, 100, 132),
            CYAN = Color.rgb(0, 229, 255), VIOLET = Color.rgb(140, 100, 255), MAGENTA = Color.rgb(255, 79, 216),
            OK = Color.rgb(105, 240, 174), WARN = Color.rgb(255, 183, 77), INK = Color.rgb(6, 8, 18),
            ERR = Color.rgb(255, 82, 82);

    private Look() { }

    static int dp(Context c, float v) { return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, c.getResources().getDisplayMetrics())); }

    /** Full-screen page: dark gradient, scrolling column, title row. Returns the column to fill. */
    static LinearLayout page(android.app.Activity a, String title, String subtitle) {
        if (a.getActionBar() != null) a.getActionBar().hide();     // the page draws its own title
        a.getWindow().setStatusBarColor(BG_TOP);
        ScrollView sv = new ScrollView(a);
        sv.setFillViewport(true);
        sv.setBackground(new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{BG_TOP, Color.rgb(8, 8, 24), BG_BOTTOM}));
        LinearLayout col = new LinearLayout(a);
        col.setOrientation(LinearLayout.VERTICAL);
        int p = dp(a, 18);
        col.setPadding(p, dp(a, 22), p, dp(a, 28));
        sv.addView(col);
        a.setContentView(sv);
        TextView t = text(a, title, 26, true, TEXT);
        t.setTypeface(Typeface.create("sans-serif-light", Typeface.NORMAL));
        col.addView(t);
        if (subtitle != null) {
            TextView s = text(a, subtitle, 13, false, MUTED);
            s.setPadding(0, dp(a, 4), 0, dp(a, 14));
            col.addView(s);
        }
        return col;
    }

    static LinearLayout card(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(dp(c, 18), dp(c, 16), dp(c, 18), dp(c, 16));
        l.setBackground(round(c, GLASS, GLASS_LINE, 22));
        return l;
    }

    /** Adds `v` to `parent` with a gap above it. */
    static <V extends View> V add(LinearLayout parent, V v, int gapDp) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(parent.getContext(), gapDp);
        parent.addView(v, lp);
        return v;
    }

    static TextView section(Context c, String s) {
        TextView t = text(c, s.toUpperCase(java.util.Locale.ROOT), 11, true, MUTED);
        t.setLetterSpacing(0.2f);
        t.setPadding(0, 0, 0, dp(c, 8));
        return t;
    }

    static TextView text(Context c, String s, int sp, boolean bold, int color) {
        TextView t = new TextView(c);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(color);
        t.setLineSpacing(0, 1.15f);
        if (bold) t.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        return t;
    }

    /** Pill button. primary = cyan-violet gradient; otherwise glass with an accent edge. */
    static Button button(Context c, String s, int accent, boolean primary) {
        Button b = new Button(c);
        b.setText(s);
        b.setAllCaps(false);
        b.setTextSize(15);
        b.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        b.setMinHeight(dp(c, 52));
        b.setStateListAnimator(null);
        b.setTextColor(primary ? INK : TEXT);
        int a = accent & 0x00FFFFFF;
        GradientDrawable idle = primary ? gradient(c, CYAN, VIOLET) : round(c, Color.argb(16, 255, 255, 255), 0x99000000 | a, 26);
        GradientDrawable pressed = primary ? gradient(c, Color.rgb(120, 245, 255), VIOLET) : round(c, 0x4D000000 | a, 0xFF000000 | a, 26);
        GradientDrawable focused = round(c, 0x33000000 | a, Color.WHITE, 26);
        focused.setStroke(dp(c, 2), Color.WHITE);
        StateListDrawable st = new StateListDrawable();
        st.addState(new int[]{android.R.attr.state_pressed}, pressed);
        st.addState(new int[]{android.R.attr.state_focused}, focused);
        st.addState(new int[]{-android.R.attr.state_enabled}, round(c, Color.argb(8, 255, 255, 255), GLASS_LINE, 26));
        st.addState(new int[]{}, idle);
        b.setBackground(st);
        return b;
    }

    /** On / off row: label on the left, state on the right; the whole row toggles. */
    static Button toggle(Context c, String label, boolean on) {
        Button b = button(c, "", on ? OK : MUTED, false);
        b.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        b.setPadding(dp(c, 18), 0, dp(c, 18), 0);
        setToggle(b, label, on);
        return b;
    }

    static void setToggle(Button b, String label, boolean on) {
        b.setText(label + "   " + (on ? "● " + L.t("On") : "○ " + L.t("Off")));
        b.setTextColor(on ? TEXT : MUTED);
        b.setTag(on);
    }

    /** Row of equal-width buttons. */
    static LinearLayout row(Context c, Button... bs) {
        LinearLayout r = new LinearLayout(c);
        r.setOrientation(LinearLayout.HORIZONTAL);
        for (int i = 0; i < bs.length; i++) {
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
            if (i > 0) lp.leftMargin = dp(c, 8);
            r.addView(bs[i], lp);
        }
        return r;
    }

    static GradientDrawable round(Context c, int fill, int stroke, int radiusDp) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(fill);
        d.setCornerRadius(dp(c, radiusDp));
        d.setStroke(dp(c, 1), stroke);
        return d;
    }

    static GradientDrawable gradient(Context c, int a, int b) {
        GradientDrawable d = new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, new int[]{a, b});
        d.setCornerRadius(dp(c, 26));
        return d;
    }
}
