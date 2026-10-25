package org.smsbridge.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.provider.Telephony;
import android.telephony.SmsMessage;

public class SmsReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (!Telephony.Sms.Intents.SMS_RECEIVED_ACTION.equals(intent.getAction()) || !Config.enabled(context)) return;
        SmsMessage[] parts = Telephony.Sms.Intents.getMessagesFromIntent(intent);
        if (parts == null || parts.length == 0) return;
        PendingResult result = goAsync();
        new Thread(() -> {
            try (Queue queue = new Queue(context)) {
                StringBuilder body = new StringBuilder(); for (SmsMessage part : parts) body.append(part.getMessageBody());
                String sender = parts[0].getOriginatingAddress();
                queue.add(sender == null ? "Unknown" : sender, body.toString(), parts[0].getTimestampMillis());
                Config.prefs(context).edit().putLong("last_capture", System.currentTimeMillis()).putString("capture_error", "").commit();
                UploadService.schedule(context);
            } catch (Exception e) { Config.prefs(context).edit().putString("status", "Could not save incoming SMS. Check device storage.").putString("capture_error", "Could not persist incoming SMS; check storage.").apply(); }
            finally { result.finish(); }
        }).start();
    }
}
