package org.smsbridge.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class Config {
    static SharedPreferences prefs(Context c) { return c.getSharedPreferences("bridge", Context.MODE_PRIVATE); }
    static boolean enabled(Context c) { return prefs(c).getBoolean("enabled", false); }
    static SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if (!store.containsAlias("upload-key")) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder("upload-key", KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            generator.generateKey();
        }
        return ((KeyStore.SecretKeyEntry) store.getEntry("upload-key", null)).getSecretKey();
    }
    static void saveToken(Context c, String value) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key());
        String encrypted = Base64.encodeToString(cipher.doFinal(value.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
        prefs(c).edit().putString("token", encrypted).putString("iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP)).commit();
    }
    static String token(Context c) throws Exception {
        String value = prefs(c).getString("token", ""); if (value.isEmpty()) return "";
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(prefs(c).getString("iv", ""), Base64.NO_WRAP)));
        return new String(cipher.doFinal(Base64.decode(value, Base64.NO_WRAP)), StandardCharsets.UTF_8);
    }
    static void notifyStatus(Context c) {
        NotificationManager manager = c.getSystemService(NotificationManager.class);
        if (!enabled(c)) { manager.cancel(1); return; }
        manager.createNotificationChannel(new NotificationChannel("status", "Forwarding status", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(c, 0, new Intent(c, MainActivity.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notification = new Notification.Builder(c, "status").setSmallIcon(R.drawable.ic_bridge)
            .setContentTitle("SMS forwarding is enabled").setContentText("Incoming texts upload to your personal dashboard. Tap to pause.")
            .setContentIntent(open).setOngoing(true).build();
        manager.notify(1, notification);
    }
}
