import java.math.BigDecimal;

/** Minimal compile stub for LOANEVAL cross-program javac (FX4). */
public class ChkAmlService {

    public AmlResponse checkAml(AmlRequest request) {
        return new AmlResponse("Y", 0, "");
    }

    public static class AmlRequest {
        public final int custId;
        public final String cin;
        public final String name;
        public final int dob;
        public final String nationality;
        public final BigDecimal amount;

        public AmlRequest(
                int custId,
                String cin,
                String name,
                int dob,
                String nationality,
                BigDecimal amount) {
            this.custId = custId;
            this.cin = cin;
            this.name = name;
            this.dob = dob;
            this.nationality = nationality;
            this.amount = amount;
        }
    }

    public static class AmlResponse {
        private final String clear;
        private final int score;
        private final String reason;

        public AmlResponse(String clear, int score, String reason) {
            this.clear = clear;
            this.score = score;
            this.reason = reason;
        }

        public String getClear() {
            return clear;
        }

        public int getScore() {
            return score;
        }

        public String getReason() {
            return reason;
        }

        public String getDecReason() {
            return reason;
        }
    }
}
