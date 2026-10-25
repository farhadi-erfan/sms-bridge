package org.smsbridge.app;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

final class Queue extends SQLiteOpenHelper {
    Queue(Context c) { super(c, "outbox.db", null, 3); }
    public void onCreate(SQLiteDatabase db) { db.execSQL("CREATE TABLE outbox (event_id TEXT PRIMARY KEY, sender TEXT, body TEXT, received_at INTEGER, retry_after INTEGER NOT NULL DEFAULT 0, blocked INTEGER NOT NULL DEFAULT 0)"); }
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        if (oldVersion < 3) {
            db.execSQL("ALTER TABLE outbox ADD COLUMN retry_after INTEGER NOT NULL DEFAULT 0");
            db.execSQL("ALTER TABLE outbox ADD COLUMN blocked INTEGER NOT NULL DEFAULT 0");
        }
    }
    static String eventId(String sender, String body, long received) throws Exception {
        String raw = new JSONObject().put("sender", sender).put("body", body).put("time", received).toString();
        byte[] bytes = MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8));
        StringBuilder result = new StringBuilder(); for (byte b : bytes) result.append(String.format("%02x", b & 0xff));
        return result.toString();
    }
    void add(String sender, String body, long received) throws Exception {
        ContentValues values = new ContentValues(); values.put("event_id", eventId(sender, body, received));
        values.put("sender", sender); values.put("body", body); values.put("received_at", received);
        getWritableDatabase().insertWithOnConflict("outbox", null, values, SQLiteDatabase.CONFLICT_IGNORE);
    }
    JSONObject next() throws Exception {
        try (Cursor cursor = getReadableDatabase().rawQuery("SELECT event_id,sender,body,received_at FROM outbox WHERE retry_after<=? ORDER BY received_at LIMIT 1", new String[]{Long.toString(System.currentTimeMillis())})) {
            if (!cursor.moveToFirst()) return null;
            return new JSONObject().put("event_id", cursor.getString(0)).put("sender", cursor.getString(1))
                .put("body", cursor.getString(2)).put("received_at", cursor.getLong(3));
        }
    }
    void defer(String id, boolean rejected) {
        ContentValues values = new ContentValues();
        values.put("retry_after", System.currentTimeMillis() + (rejected ? 6 * 60 * 60 * 1000L : 60000L));
        values.put("blocked", rejected ? 1 : 0);
        getWritableDatabase().update("outbox", values, "event_id=?", new String[]{id});
    }
    long blockedCount() {
        try (Cursor cursor = getReadableDatabase().rawQuery("SELECT COUNT(*) FROM outbox WHERE blocked=1", null)) { cursor.moveToFirst(); return cursor.getLong(0); }
    }
    void remove(String id) { getWritableDatabase().delete("outbox", "event_id=?", new String[]{id}); }
    long count() {
        try (Cursor cursor = getReadableDatabase().rawQuery("SELECT COUNT(*) FROM outbox", null)) { cursor.moveToFirst(); return cursor.getLong(0); }
    }
}
