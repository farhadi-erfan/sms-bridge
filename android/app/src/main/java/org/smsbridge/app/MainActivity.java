package org.smsbridge.app;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.provider.Telephony;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONObject;
import java.net.URI;
import java.text.DateFormat;
import java.util.Date;

public class MainActivity extends Activity {
    EditText server, token, device;
    TextView status;
    Button enable;
    android.os.Handler handler = new android.os.Handler(android.os.Looper.getMainLooper());
    Runnable update = new Runnable() { public void run() { refresh(); handler.postDelayed(this, 3000); } };
    LinearLayout page;
    TextView text(String value, int size, String color) {
        TextView v = new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(Color.parseColor(color)); v.setPadding(0, 15, 0, 10); page.addView(v); return v;
    }
    Button button(String label, View.OnClickListener click) { Button b = new Button(this); b.setText(label); b.setAllCaps(false); b.setOnClickListener(click); page.addView(b); return b; }
    void error(String value) { new AlertDialog.Builder(this).setMessage(value).setPositiveButton("OK", null).show(); }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE, android.view.WindowManager.LayoutParams.FLAG_SECURE);
        ScrollView scroll = new ScrollView(this); page = new LinearLayout(this); page.setOrientation(LinearLayout.VERTICAL); page.setPadding(32, 38, 32, 38); page.setBackgroundColor(Color.rgb(246,247,244)); scroll.addView(page); setContentView(scroll);
        text(getString(R.string.app_name), 30, "#326c51");
        text("Your messages, your server.", 22, "#252b29");
        text("This app sends incoming SMS, including sender and full message text, to your private dashboard. It can include verification codes. Forwarding starts only when you enable it below.", 15, "#66745d");
        text("این برنامه با اجازه شما پیامک‌ها را به داشبورد شخصی شما ارسال می‌کند. برای توقف، دکمه Pause را بزنید.", 15, "#66745d");
        server = new EditText(this); server.setSingleLine(true);
        server.setText(Config.prefs(this).getString("server", ""));
        token = new EditText(this); token.setSingleLine(true);
        token.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        try { token.setText(Config.token(this)); } catch (Exception e) { error("Could not read upload configuration."); }
        text("Server URL", 13, "#66745d"); page.addView(server);
        server.setHint("https://sms.example.com");
        text("Private upload key", 13, "#66745d"); page.addView(token);
        text("Device label", 13, "#66745d");
        device = new EditText(this); device.setSingleLine(true);
        device.setText(Config.prefs(this).getString("device", "Android phone")); page.addView(device);
        enable = button("Enable forwarding", v -> {
            if (Config.enabled(this)) { Config.prefs(this).edit().putBoolean("enabled", false).commit(); UploadService.pause(this); refresh(); return; }
            if (!save()) return;
            if (checkSelfPermission(Manifest.permission.RECEIVE_SMS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.RECEIVE_SMS}, 10); return;
            }
            activate();
        });
        button("Test connection / Sync now", v -> {
            if (!save()) return;
            status.setText("Testing connection…");
            new Thread(() -> {
                try { try (Queue queue = new Queue(this)) { UploadService.post(this, "heartbeat", UploadService.diagnostics(this, queue)); } runOnUiThread(() -> { Config.prefs(this).edit().putString("status", "Connection successful.").putLong("last_sync", System.currentTimeMillis()).apply(); refresh(); }); UploadService.schedule(this); }
                catch (Exception e) { runOnUiThread(() -> error("Connection failed. " + e.getMessage())); }
            }).start();
        });
        button("Allow contact names", v -> {
            if (checkSelfPermission(Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED)
                requestPermissions(new String[]{Manifest.permission.READ_CONTACTS}, 11);
            else error("Contact names are enabled for new messages.");
        });
        button("Open battery / background settings", v -> startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:" + getPackageName()))));
        status = text("", 15, "#326c51");
        text("Setup: Allow SMS access. In Samsung Settings → Apps → SMS Bridge → Battery, allow background activity and remove the app from sleeping apps. Keep Wi-Fi/mobile data enabled. Do not force stop the app. After restarting, unlock the phone once. Pending messages stay on this phone until acknowledged by the server.", 14, "#7a846f");
        text("Only SMS is supported, not WhatsApp, MMS or RCS. Android may delay some verification texts. Only new incoming texts are collected. Existing inbox messages are never imported. Contact access is optional.", 13, "#7a846f");
    }
    boolean save() {
        try {
            String origin = server.getText().toString().trim().replaceAll("/+$", ""); URI uri = new URI(origin);
            if (!"https".equals(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null || (uri.getPath() != null && !uri.getPath().isEmpty()) || uri.getQuery() != null || uri.getFragment() != null) throw new Exception("Enter an HTTPS origin only, e.g. https://sms.example.com");
            String secret = token.getText().toString().trim(); if (secret.length() < 32) throw new Exception("Please enter the private upload key.");
            if (Config.enabled(this) && (!origin.equals(Config.prefs(this).getString("server", "")) || !secret.equals(Config.token(this)))) throw new Exception("Pause forwarding before changing the server or upload key.");
            String label = device.getText().toString().trim();
            if (label.isEmpty() || label.length() > 100) throw new Exception("Enter a device label (1–100 characters).");
            Config.prefs(this).edit().putString("device", label).commit();
            Config.saveToken(this, secret); Config.prefs(this).edit().putString("server", origin).commit(); return true;
        } catch (Exception e) { error(e.getMessage()); return false; }
    }
    void activate() {
        Config.prefs(this).edit().putBoolean("enabled", true).commit();
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 12);
        Config.notifyStatus(this); UploadService.schedule(this); refresh();
        if (Build.VERSION.SDK_INT < 33 && checkSelfPermission(Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) requestPermissions(new String[]{Manifest.permission.READ_CONTACTS}, 11);
    }
    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) { if (request == 10) activate(); if (request == 11) error("Contact names enabled for new messages."); if (request == 12) { Config.notifyStatus(this); if (checkSelfPermission(Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) requestPermissions(new String[]{Manifest.permission.READ_CONTACTS}, 11); } }
        else if (request != 12) error("SMS permission is required for this action. You can enable it in app settings.");
    }
    void refresh() {
        if (status == null) return;
        enable.setText(Config.enabled(this) ? "Pause forwarding" : "Enable forwarding");
        try (Queue queue = new Queue(this)) {
            long sync = Config.prefs(this).getLong("last_sync", 0);
            status.setText((Config.enabled(this) ? "Forwarding enabled" : "Forwarding paused") + "\n" + queue.count() + " messages waiting\n" + Config.prefs(this).getString("status", "Not connected yet.") + (sync == 0 ? "" : "\nLast connected: " + DateFormat.getDateTimeInstance().format(new Date(sync))));
        }
    }
    @Override protected void onResume() { super.onResume(); handler.post(update); if (Config.enabled(this)) UploadService.schedule(this); }
    @Override protected void onPause() { super.onPause(); handler.removeCallbacks(update); }
}
