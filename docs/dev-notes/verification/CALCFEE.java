package com.modernized.calcfee;

import java.math.BigDecimal;
import java.math.RoundingMode;

public class Calcfee {

    private final WsFeeParams wsFeeParams = new WsFeeParams();
    private final WsWork wsWork = new WsWork();

    public Calcfee() {
        // Initialize constants from COBOL WORKING-STORAGE values
        wsFeeParams.wsFileFeeRateCon = new BigDecimal("1.5000");
        wsFeeParams.wsFileFeeRateImm = new BigDecimal("1.0000");
        wsFeeParams.wsFileFeeRateAut = new BigDecimal("2.0000");
        wsFeeParams.wsFileFeeRatePro = new BigDecimal("0.7500");
        wsFeeParams.wsFileFeeRateRev = new BigDecimal("2.5000");
        wsFeeParams.wsFileFeeMin = new BigDecimal("50.00");    // 50,000 millimes = 50.000 TND
        wsFeeParams.wsFileFeeMax = new BigDecimal("5000.00");  // 5000,000 millimes = 5000.000 TND
        wsFeeParams.wsInsuranceRate = new BigDecimal("0.4500");
        wsFeeParams.wsTvaRate = new BigDecimal("19.00");
        wsFeeParams.wsTimbreFixed = new BigDecimal("5.00");
    }

    public void main(LkFeeRequest lkFeeRequest, LkFeeResponse lkFeeResponse) {
        // Initialize response fields to zero
        lkFeeResponse.lkRespFileFee = BigDecimal.ZERO.setScale(2);
        lkFeeResponse.lkRespTax = BigDecimal.ZERO.setScale(2);
        lkFeeResponse.lkRespInsurance = BigDecimal.ZERO.setScale(2);
        lkFeeResponse.lkRespTotal = BigDecimal.ZERO.setScale(2);

        selectFeeRate(lkFeeRequest);
        computeFileFee(lkFeeRequest, lkFeeResponse);
        computeInsurance(lkFeeRequest, lkFeeResponse);
        computeTax(lkFeeResponse);
        computeTotal(lkFeeResponse);
    }

    private void selectFeeRate(LkFeeRequest lkFeeRequest) {
        String loanType = lkFeeRequest.lkReqLoanType;
        if ("CON".equals(loanType)) {
            wsWork.wsFeeRate = wsFeeParams.wsFileFeeRateCon;
        } else if ("IMM".equals(loanType)) {
            wsWork.wsFeeRate = wsFeeParams.wsFileFeeRateImm;
        } else if ("AUT".equals(loanType)) {
            wsWork.wsFeeRate = wsFeeParams.wsFileFeeRateAut;
        } else if ("PRO".equals(loanType)) {
            wsWork.wsFeeRate = wsFeeParams.wsFileFeeRatePro;
        } else if ("REV".equals(loanType)) {
            wsWork.wsFeeRate = wsFeeParams.wsFileFeeRateRev;
        } else {
            wsWork.wsFeeRate = wsFeeParams.wsFileFeeRateCon;
        }
    }

    private void computeFileFee(LkFeeRequest lkFeeRequest, LkFeeResponse lkFeeResponse) {
        // WS-FEE-GROSS = (LK-REQ-AMOUNT * WS-FEE-RATE) / 100 rounded half up
        wsWork.wsFeeGross = lkFeeRequest.lkReqAmount
                .multiply(wsWork.wsFeeRate)
                .divide(new BigDecimal("100"), 6, RoundingMode.HALF_UP);

        // Clamp WS-FEE-GROSS between WS-FILE-FEE-MIN and WS-FILE-FEE-MAX
        if (wsWork.wsFeeGross.compareTo(wsFeeParams.wsFileFeeMin) < 0) {
            wsWork.wsFeeGross = wsFeeParams.wsFileFeeMin;
        }
        if (wsWork.wsFeeGross.compareTo(wsFeeParams.wsFileFeeMax) > 0) {
            wsWork.wsFeeGross = wsFeeParams.wsFileFeeMax;
        }

        // Store with scale 2 (PIC 9(7)V99)
        wsWork.wsFeeGross = wsWork.wsFeeGross.setScale(2, RoundingMode.HALF_UP);

        lkFeeResponse.lkRespFileFee = wsWork.wsFeeGross;
    }

    private void computeInsurance(LkFeeRequest lkFeeRequest, LkFeeResponse lkFeeResponse) {
        String loanType = lkFeeRequest.lkReqLoanType;
        if ("IMM".equals(loanType) || "AUT".equals(loanType) || "CON".equals(loanType)) {
            // LK-RESP-INSURANCE = (LK-REQ-AMOUNT * WS-INSURANCE-RATE) / 100 rounded half up
            BigDecimal insurance = lkFeeRequest.lkReqAmount
                    .multiply(wsFeeParams.wsInsuranceRate)
                    .divide(new BigDecimal("100"), 6, RoundingMode.HALF_UP);
            lkFeeResponse.lkRespInsurance = insurance.setScale(2, RoundingMode.HALF_UP);
        } else {
            lkFeeResponse.lkRespInsurance = BigDecimal.ZERO.setScale(2);
        }
    }

    private void computeTax(LkFeeResponse lkFeeResponse) {
        // WS-FEE-TVA = (LK-RESP-FILE-FEE * WS-TVA-RATE) / 100 rounded half up
        wsWork.wsFeeTva = lkFeeResponse.lkRespFileFee
                .multiply(wsFeeParams.wsTvaRate)
                .divide(new BigDecimal("100"), 6, RoundingMode.HALF_UP)
                .setScale(2, RoundingMode.HALF_UP);

        // LK-RESP-TAX = WS-FEE-TVA + WS-TIMBRE-FIXED rounded down
        BigDecimal tax = wsWork.wsFeeTva.add(wsFeeParams.wsTimbreFixed);
        lkFeeResponse.lkRespTax = tax.setScale(2, RoundingMode.DOWN);
    }

    private void computeTotal(LkFeeResponse lkFeeResponse) {
        // LK-RESP-TOTAL = LK-RESP-FILE-FEE + LK-RESP-INSURANCE + LK-RESP-TAX rounded down
        BigDecimal total = lkFeeResponse.lkRespFileFee
                .add(lkFeeResponse.lkRespInsurance)
                .add(lkFeeResponse.lkRespTax);
        lkFeeResponse.lkRespTotal = total.setScale(2, RoundingMode.DOWN);
    }

    // Supporting classes for data records

    public static class WsFeeParams {
        public BigDecimal wsFileFeeRateCon;
        public BigDecimal wsFileFeeRateImm;
        public BigDecimal wsFileFeeRateAut;
        public BigDecimal wsFileFeeRatePro;
        public BigDecimal wsFileFeeRateRev;
        public BigDecimal wsFileFeeMin;
        public BigDecimal wsFileFeeMax;
        public BigDecimal wsInsuranceRate;
        public BigDecimal wsTvaRate;
        public BigDecimal wsTimbreFixed;
    }

    public static class WsWork {
        public BigDecimal wsFeeRate = BigDecimal.ZERO.setScale(4);
        public BigDecimal wsFeeGross = BigDecimal.ZERO.setScale(2);
        public BigDecimal wsFeeTva = BigDecimal.ZERO.setScale(2);
    }

    public static class LkFeeRequest {
        public String lkReqLoanType; // PIC X(3)
        public BigDecimal lkReqAmount; // PIC 9(11)V99 scale 2
        public BigDecimal lkReqRate;   // PIC 9(2)V9(4) scale 4

        public LkFeeRequest() {
            lkReqLoanType = "";
            lkReqAmount = BigDecimal.ZERO.setScale(2);
            lkReqRate = BigDecimal.ZERO.setScale(4);
        }
    }

    public static class LkFeeResponse {
        public BigDecimal lkRespFileFee;   // PIC 9(7)V99 scale 2
        public BigDecimal lkRespTax;       // PIC 9(7)V99 scale 2
        public BigDecimal lkRespInsurance; // PIC 9(7)V99 scale 2
        public BigDecimal lkRespTotal;     // PIC 9(9)V99 scale 2

        public LkFeeResponse() {
            lkRespFileFee = BigDecimal.ZERO.setScale(2);
            lkRespTax = BigDecimal.ZERO.setScale(2);
            lkRespInsurance = BigDecimal.ZERO.setScale(2);
            lkRespTotal = BigDecimal.ZERO.setScale(2);
        }
    }
}
