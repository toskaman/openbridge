package fr.openbridge.companion;

import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

/** Quick settings tile "Glasses: next": one tap = next item on the glasses (the ENGO 3's double tap, from the
 *  notification shade). Greyed out while the glasses are not connected. */
public class GlassesTile extends TileService {
    @Override public void onStartListening() { refresh(); }

    @Override public void onClick() {
        GlassesLink g = RelayServer.get(this, null).glasses();
        if ("READY".equals(g.state())) g.button("next");
        refresh();
    }

    private void refresh() {
        Tile t = getQsTile();
        if (t == null) return;
        L.init(this);
        boolean ready = "READY".equals(RelayServer.get(this, null).glasses().state());
        t.setLabel(L.t("Glasses: next"));
        t.setState(ready ? Tile.STATE_ACTIVE : Tile.STATE_UNAVAILABLE);
        t.updateTile();
    }
}
