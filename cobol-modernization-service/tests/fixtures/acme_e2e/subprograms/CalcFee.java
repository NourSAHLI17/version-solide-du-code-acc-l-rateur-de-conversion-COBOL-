import java.math.BigDecimal;

/** Minimal compile stub for LOANEVAL cross-program javac (Calcfee spelling). */
public class Calcfee {

    public void execute(LkFeeRequest request, LkFeeResponse response) {
        response.lkRespFileFee = BigDecimal.ZERO;
        response.lkRespTax = BigDecimal.ZERO;
        response.lkRespInsurance = BigDecimal.ZERO;
        response.lkRespTotal = BigDecimal.ZERO;
    }

    public static class LkFeeRequest {
        public String lkReqLoanType = "";
        public BigDecimal lkReqAmount = BigDecimal.ZERO;
        public BigDecimal lkReqRate = BigDecimal.ZERO;
    }

    public static class LkFeeResponse {
        public BigDecimal lkRespFileFee = BigDecimal.ZERO;
        public BigDecimal lkRespTax = BigDecimal.ZERO;
        public BigDecimal lkRespInsurance = BigDecimal.ZERO;
        public BigDecimal lkRespTotal = BigDecimal.ZERO;
    }
}