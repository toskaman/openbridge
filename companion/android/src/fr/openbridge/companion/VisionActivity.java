package fr.openbridge.companion;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.os.Bundle;
import android.provider.MediaStore;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.File;

/** Visual Oracle: the owner takes a photo with the phone's camera app and asks a question; the PC answers it with a
 *  local vision model and the answer shows on the glasses. The photo is shrunk on the phone (1024 px at most), goes
 *  only to the paired PC through the signed relay, and is deleted from the phone once sent. */
public class VisionActivity extends Activity {
    private ImageView preview;
    private EditText question;
    private TextView status;
    private byte[] jpeg;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        L.init(this);
        LinearLayout col = Look.page(this, L.t("Visual Oracle"), L.t("Photo + question → the answer on your glasses."));
        LinearLayout c = Look.card(this);
        preview = new ImageView(this);
        preview.setAdjustViewBounds(true);
        preview.setBackground(Look.round(this, Color.BLACK, Look.GLASS_LINE, 14));
        c.addView(preview, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, Look.dp(this, 220)));
        Button take = Look.add(c, Look.button(this, L.t("Take a photo"), Look.CYAN, false), 10);
        take.setOnClickListener(v -> capture());
        question = new EditText(this);
        question.setHint(L.t("What is this?"));
        question.setTextColor(Look.TEXT);
        question.setHintTextColor(Look.FAINT);
        Look.add(c, question, 10);
        Button send = Look.add(c, Look.button(this, L.t("Ask the Oracle"), Look.MAGENTA, true), 10);
        send.setOnClickListener(v -> send());
        status = Look.add(c, Look.text(this, "", 13, false, Look.MUTED), 10);
        Look.add(col, c, 0);
        if (!RelayServer.get(this, null).paired()) status.setText(L.t("Pair with your PC first."));
        else capture();
    }

    private void capture() {
        Intent i = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
        i.putExtra(MediaStore.EXTRA_OUTPUT, PhotoProvider.uri());
        i.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try { startActivityForResult(i, 5); }
        catch (Exception e) { status.setText(L.t("No camera app on this phone.")); }
    }

    @Override protected void onActivityResult(int code, int result, Intent data) {
        if (code != 5 || result != RESULT_OK) return;
        File f = PhotoProvider.file(this);
        BitmapFactory.Options o = new BitmapFactory.Options();
        o.inJustDecodeBounds = true;
        BitmapFactory.decodeFile(f.getPath(), o);
        int s = 1;
        while (Math.max(o.outWidth, o.outHeight) / (s * 2) >= 1024) s *= 2;
        o = new BitmapFactory.Options();
        o.inSampleSize = s;
        Bitmap bm = BitmapFactory.decodeFile(f.getPath(), o);
        if (bm == null) { status.setText(L.t("The photo could not be read.")); return; }
        float k = 1024f / Math.max(bm.getWidth(), bm.getHeight());
        if (k < 1) bm = Bitmap.createScaledBitmap(bm, Math.round(bm.getWidth() * k), Math.round(bm.getHeight() * k), true);
        int q = 82;
        ByteArrayOutputStream out;
        do { out = new ByteArrayOutputStream(); bm.compress(Bitmap.CompressFormat.JPEG, q, out); q -= 10; }
        while (out.size() > RelayServer.VOICE_MAX_BYTES - 1024 && q > 30);
        jpeg = out.toByteArray();
        preview.setImageBitmap(bm);
        f.delete();
        status.setText(String.format(java.util.Locale.ROOT, "%d × %d · %d Ko", bm.getWidth(), bm.getHeight(), jpeg.length / 1024));
    }

    private void send() {
        if (jpeg == null) { capture(); return; }
        String q = question.getText().toString().trim();
        if (q.isEmpty()) q = L.t("What is this?");
        String r = RelayServer.get(this, null).submitPhoto(jpeg, q);
        status.setText(L.t(r));
        if (r.startsWith("Sent")) jpeg = null;
    }
}
