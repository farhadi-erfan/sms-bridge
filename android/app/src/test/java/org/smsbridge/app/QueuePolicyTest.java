package org.smsbridge.app;
import org.junit.Test;
import static org.junit.Assert.*;

public class QueuePolicyTest {
    @Test public void individualRejectionsMayBeDeferredWithoutBlockingOtherMessages() {
        for (int code : new int[]{400,413,422}) assertTrue(QueuePolicy.isMessageRejection(code));
    }
    @Test public void authenticationRateLimitsAndServerOutagesMustNotQuarantineMessages() {
        for (int code : new int[]{401,403,404,408,429,500,502,503,504}) assertFalse(QueuePolicy.isMessageRejection(code));
    }
}
