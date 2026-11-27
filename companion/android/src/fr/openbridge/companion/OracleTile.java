package fr.openbridge.companion;

import android.app.PendingIntent;
import android.content.Intent;
import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

/** Quick settings tile "Oracle": opens the Oracle voice screen straight from the notification shade. Hidden in
 *  effect (unavailable) when the owner switched the Oracle module off. */
public class OracleTile extends TileService {
    @Override public void onStartListening() {
        Tile t = getQsTile();
        if (t == null) return;
        L.init(this);
        t.setLabel(L.t("Oracle"));
        t.setState(RelayServer.get(this, null).moduleOracle() ? Tile.STATE_INACTIVE : Tile.STATE_UNAVAILABLE);
        t.updateTile();
    }

    @Override public void onClick() {
        if (!RelayServer.get(this, null).moduleOracle()) return;
        Intent i = new Intent(this, OracleVoiceActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        if (Build.VERSION.SDK_INT >= 34) startActivityAndCollapse(PendingIntent.getActivity(this, 7, i, PendingIntent.FLAG_IMMUTABLE));
        else startActivityAndCollapseCompat(i);
    }

    @SuppressWarnings("deprecation")
    private void startActivityAndCollapseCompat(Intent i) { startActivityAndCollapse(i); }
}
