package org.smsbridge.app;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import org.json.JSONObject;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.net.ssl.HttpsURLConnection;

public class UploadService extends JobService {
    static final int IMMEDIATE = 100, PERIODIC = 101;
    static final AtomicBoolean running = new AtomicBoolean(false);
    private volatile boolean stopped;
    static void schedule(Context c) {
        if (!Config.enabled(c)) return;
        JobScheduler scheduler = c.getSystemService(JobScheduler.class);
        ComponentName name = new ComponentName(c, UploadService.class);
        if (scheduler.getPendingJob(IMMEDIATE) == null) scheduler.schedule(new JobInfo.Builder(IMMEDIATE, name)
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPersisted(true).setBackoffCriteria(30000, JobInfo.BACKOFF_POLICY_EXPONENTIAL).build());
        if (scheduler.getPendingJob(PERIODIC) == null) scheduler.schedule(new JobInfo.Builder(PERIODIC, name)
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPersisted(true).setPeriodic(15 * 60 * 1000L).build());
    }
    static void pause(Context c) {
        JobScheduler scheduler = c.getSystemService(JobScheduler.class); scheduler.cancel(IMMEDIATE); scheduler.cancel(PERIODIC);
        Config.notifyStatus(c);
    }
    static class UploadError extends Exception {
        final int code;
        UploadError(int code) { super("Server returned " + code); this.code = code; }
    }
    static JSONObject diagnostics(Context c, Queue queue) throws Exception {
        android.content.SharedPreferences p = Config.prefs(c);
        return new JSONObject().put("device", Config.prefs(c).getString("device", "Android phone")).put("diagnostics", new JSONObject()
            .put("app_version", BuildConfig.VERSION_NAME).put("queue_count", queue.count())
            .put("blocked_count", queue.blockedCount()).put("sms_permission", c.checkSelfPermission(android.Manifest.permission.RECEIVE_SMS) == android.content.pm.PackageManager.PERMISSION_GRANTED)
            .put("forwarding_enabled", Config.enabled(c)).put("last_capture", p.getLong("last_capture", 0))
            .put("last_upload", p.getLong("last_upload", 0)).put("upload_error", p.getString("upload_error", ""))
            .put("capture_error", p.getString("capture_error", "")));
    }
    static void report(Context c, Queue queue) {
        try { post(c, "heartbeat", diagnostics(c, queue)); Config.prefs(c).edit().putLong("last_sync", System.currentTimeMillis()).apply(); } catch (Exception ignored) { }
    }
    static JSONObject post(Context c, String route, JSONObject payload) throws Exception {
        URL url = new URL(Config.prefs(c).getString("server", "") + "/dashboard/api/" + route);
        HttpsURLConnection connection = (HttpsURLConnection) url.openConnection();
        try {
            connection.setInstanceFollowRedirects(false); connection.setConnectTimeout(15000); connection.setReadTimeout(20000);
            connection.setRequestMethod("POST"); connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setRequestProperty("Authorization", "Bearer " + Config.token(c));
            byte[] bytes = payload.toString().getBytes(StandardCharsets.UTF_8); connection.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream out = connection.getOutputStream()) { out.write(bytes); }
            int code = connection.getResponseCode();
            if (code != 200) throw new UploadError(code);
            // An HTML fallback must never cause a queued SMS to be deleted.
            try (java.io.InputStream input = connection.getInputStream()) {
                java.io.ByteArrayOutputStream buffer = new java.io.ByteArrayOutputStream();
                byte[] block = new byte[1024]; int read;
                while ((read = input.read(block)) != -1) { if (buffer.size() + read > 16384) throw new Exception("Unexpected server response"); buffer.write(block, 0, read); }
                JSONObject result = new JSONObject(buffer.toString("UTF-8"));
                if (!result.optBoolean("ok", false)) throw new Exception("Upload not acknowledged");
                return result;
            }
        } finally { connection.disconnect(); }
    }
    @Override public boolean onStartJob(JobParameters params) {
        if (!Config.enabled(this)) return false;
        if (!running.compareAndSet(false, true)) return false;
        stopped = false;
        new Thread(() -> {
            boolean retry = false;
            try (Queue queue = new Queue(this)) {
                report(this, queue);
                long deadline = android.os.SystemClock.elapsedRealtime() + 120000L;
                boolean failed = false;
                for (int n = 0; n < 100 && !stopped && Config.enabled(this) && android.os.SystemClock.elapsedRealtime() < deadline; n++) {
                    JSONObject message = queue.next(); if (message == null) break;
                    String id = message.getString("event_id");
                    try {
                        message.put("device", Config.prefs(this).getString("device", "Android phone"));
                        message.put("contact_name", Contacts.name(this, message.getString("sender")));
                        JSONObject result = post(this, "ingest", message);
                        queue.remove(id);
                        if (!result.optBoolean("discarded", false)) Config.prefs(this).edit().putLong("last_upload", System.currentTimeMillis()).apply();
                    } catch (UploadError e) {
                        failed = true;
                        if (QueuePolicy.isMessageRejection(e.code)) {
                            queue.defer(id, true);
                            Config.prefs(this).edit().putString("upload_error", "A message was rejected (HTTP " + e.code + "); retained for retry. Other messages continue.").apply();
                            continue;
                        }
                        queue.defer(id, false);
                        Config.prefs(this).edit().putString("upload_error", "Upload failed (HTTP " + e.code + "); queued messages retained.").apply();
                        break;
                    } catch (Exception e) {
                        failed = true; queue.defer(id, false);
                        Config.prefs(this).edit().putString("upload_error", "Network or acknowledgement failure; queued messages retained.").apply();
                        break;
                    }
                }
                if (!failed && queue.blockedCount() == 0) Config.prefs(this).edit().putString("upload_error", "").apply();
                retry = queue.count() > queue.blockedCount() && Config.enabled(this);
                Config.prefs(this).edit().putString("status", queue.count() == 0 ? "Upload queue empty. Server check-in attempted." : queue.count() + " queued; " + queue.blockedCount() + " rejected messages retained.").apply();
                report(this, queue);
            } catch (Exception e) {
                retry = true; Config.prefs(this).edit().putString("status", "Queue processing failed; pending messages retained.")
                    .putString("upload_error", "Queue processing failed; pending messages retained.").apply();
            } finally { running.set(false); if (!stopped) jobFinished(params, retry); }
        }).start();
        return true;
    }
    @Override public boolean onStopJob(JobParameters params) { stopped = true; return Config.enabled(this); }
}
