package org.smsbridge.app;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
public class BootReceiver extends BroadcastReceiver {
    public void onReceive(Context context, Intent intent) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction()) && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(intent.getAction())) return;
        if (Config.enabled(context)) { Config.notifyStatus(context); UploadService.schedule(context); }
    }
}
