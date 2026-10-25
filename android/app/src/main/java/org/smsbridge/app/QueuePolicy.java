package org.smsbridge.app;

final class QueuePolicy {
    static boolean isMessageRejection(int code) {
        return code == 400 || code == 413 || code == 422;
    }
}
