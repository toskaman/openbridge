package fr.openbridge.companion;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import java.io.File;
import java.io.FileNotFoundException;

/** Hands the camera app one file to write the visual Oracle's photo into (cache/vision.jpg), and nothing else. */
public class PhotoProvider extends ContentProvider {
    static final String AUTHORITY = "fr.openbridge.companion.photo";
    static Uri uri() { return Uri.parse("content://" + AUTHORITY + "/vision.jpg"); }
    static File file(android.content.Context c) { return new File(c.getCacheDir(), "vision.jpg"); }

    @Override public boolean onCreate() { return true; }

    @Override public ParcelFileDescriptor openFile(Uri u, String mode) throws FileNotFoundException {
        if (!"/vision.jpg".equals(u.getPath())) throw new FileNotFoundException();
        File f = file(getContext());
        return ParcelFileDescriptor.open(f, ParcelFileDescriptor.MODE_READ_WRITE | ParcelFileDescriptor.MODE_CREATE | ParcelFileDescriptor.MODE_TRUNCATE);
    }

    @Override public String getType(Uri u) { return "image/jpeg"; }
    @Override public Cursor query(Uri u, String[] p, String s, String[] a, String o) { return null; }
    @Override public Uri insert(Uri u, ContentValues v) { return null; }
    @Override public int delete(Uri u, String s, String[] a) { return 0; }
    @Override public int update(Uri u, ContentValues v, String s, String[] a) { return 0; }
}
