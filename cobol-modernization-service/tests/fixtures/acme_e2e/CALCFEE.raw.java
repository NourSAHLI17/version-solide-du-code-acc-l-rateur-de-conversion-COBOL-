package com.modernized.calcfee;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 // CALCFEE - Fee and tax calculation sub-program.
 // Called by LOANEVAL and TXNHIGH.
 // Computes:
 // - File opening fee (frais de dossier)
 // - Insurance premium (ADI - assurance deces invalidite)
 // - Stamp tax (timbre fiscal)
 // - Total upfront cost
 // All amounts in millimes (TND has 3 decimal places).
 */
public class CalcFee {

    // Working-storage: fee parameters
    private BigDecimal wsFileFeeRateCon;
    private BigDecimal wsFileFeeRateImm;
    private BigDecimal wsFileFeeRateAut;
    private BigDecimal wsFileFeeRatePro;
    private BigDecimal wsFileFeeRateRev;
    private BigDecimal wsFileFeeMin;
    private BigDecimal wsFileFeeMax;
    private BigDecimal wsInsuranceRate;
    private BigDecimal wsTvaRate;
    private BigDecimal wsTimbreFixed;

    // Working-storage: work variables
    private BigDecimal wsFeeRate;
    private BigDecimal wsFeeGross;
    private BigDecimal wsFeeTva;

    public CalcFee() {
        initializeWorkingStorage();
    }

    private void initializeWorkingStorage() {
        // WS-FEE-PARAMS initialization with DECIMAL-POINT IS COMMA values
        wsFileFeeRateCon = new BigDecimal("1.5000");
        wsFileFeeRateImm = new BigDecimal("1.0000");
        wsFileFeeRateAut = new BigDecimal("2.0000");
        wsFileFeeRatePro = new BigDecimal("0.7500");
        wsFileFeeRateRev = new BigDecimal("2.5000");
        wsFileFeeMin = new BigDecimal("50.00");
        wsFileFeeMax = new BigDecimal("5000.00");
        wsInsuranceRate = new BigDecimal("0.4500");
        wsTvaRate = new BigDecimal("19.00");
        wsTimbreFixed = new BigDecimal("5.00");

        // WS-WORK initialization
        wsFeeRate = BigDecimal.ZERO;
        wsFeeGross = BigDecimal.ZERO;
        wsFeeTva = BigDecimal.ZERO;
    }

    /**
     // Main entry point - PROCEDURE DIVISION USING
     */
    public void execute(LkFeeRequest request, LkFeeResponse response) {
        response.lkRespFileFee = BigDecimal.ZERO;
        response.lkRespTax = BigDecimal.ZERO;
        response.lkRespInsurance = BigDecimal.ZERO;
        response.lkRespTotal = BigDecimal.ZERO;

        selectFeeRate(request);
        computeFileFee(request, response);
        computeInsurance(request, response);
        computeTax(response);
        computeTotal(response);
    }

    /**
     // 1000-SELECT-FEE-RATE
     */
    private void selectFeeRate(LkFeeRequest request) {
        String loanType = request.lkReqLoanType;
        
        switch (loanType) {
            case "CON":
                wsFeeRate = wsFileFeeRateCon;
                break;
            case "IMM":
                wsFeeRate = wsFileFeeRateImm;
                break;
            case "AUT":
                wsFeeRate = wsFileFeeRateAut;
                break;
            case "PRO":
                wsFeeRate = wsFileFeeRatePro;
                break;
            case "REV":
                wsFeeRate = wsFileFeeRateRev;
                break;
            default:
                wsFeeRate = wsFileFeeRateCon;
                break;
        }
    }

    /**
     // 2000-COMPUTE-FILE-FEE
     */
    private void computeFileFee(LkFeeRequest request, LkFeeResponse response) {
        // COMPUTE WS-FEE-GROSS ROUNDED = LK-REQ-AMOUNT * WS-FEE-RATE / 100
        wsFeeGross = request.lkReqAmount
                .multiply(wsFeeRate)
                .divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
        
        // Apply min/max boundaries
        if (wsFeeGross.compareTo(wsFileFeeMin) < 0) {
            wsFeeGross = wsFileFeeMin;
        }
        if (wsFeeGross.compareTo(wsFileFeeMax) > 0) {
            wsFeeGross = wsFileFeeMax;
        }
        
        response.lkRespFileFee = wsFeeGross;
    }

    /**
     // 3000-COMPUTE-INSURANCE
     */
    private void computeInsurance(LkFeeRequest request, LkFeeResponse response) {
        String loanType = request.lkReqLoanType;
        
        if ("IMM".equals(loanType) || "AUT".equals(loanType) || "CON".equals(loanType)) {
            // COMPUTE LK-RESP-INSURANCE ROUNDED = LK-REQ-AMOUNT * WS-INSURANCE-RATE / 100
            response.lkRespInsurance = request.lkReqAmount
                    .multiply(wsInsuranceRate)
                    .divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
        } else {
            response.lkRespInsurance = BigDecimal.ZERO;
        }
    }

    /**
     // 4000-COMPUTE-TAX
     */
    private void computeTax(LkFeeResponse response) {
        // COMPUTE WS-FEE-TVA ROUNDED = LK-RESP-FILE-FEE * WS-TVA-RATE / 100
        wsFeeTva = response.lkRespFileFee
                .multiply(wsTvaRate)
                .divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
        
        // COMPUTE LK-RESP-TAX = WS-FEE-TVA + WS-TIMBRE-FIXED
        response.lkRespTax = wsFeeTva.add(wsTimbreFixed);
    }

    /**
     // 5000-COMPUTE-TOTAL
     */
    private void computeTotal(LkFeeResponse response) {
        response.lkRespTotal = response.lkRespFileFee
                .add(response.lkRespInsurance)
                .add(response.lkRespTax);
    }

    /**
     // Request DTO - maps to LK-FEE-REQUEST
     */
    public static class LkFeeRequest {
        public String lkReqLoanType;
        public BigDecimal lkReqAmount;
        public BigDecimal lkReqRate;

        public LkFeeRequest() {
            this.lkReqLoanType = "";
            this.lkReqAmount = BigDecimal.ZERO;
            this.lkReqRate = BigDecimal.ZERO;
        }
    }

    /**
     // Response DTO - maps to LK-FEE-RESPONSE
     */
    public static class LkFeeResponse {
        public BigDecimal lkRespFileFee;
        public BigDecimal lkRespTax;
        public BigDecimal lkRespInsurance;
        public BigDecimal lkRespTotal;

        public LkFeeResponse() {
            this.lkRespFileFee = BigDecimal.ZERO;
            this.lkRespTax = BigDecimal.ZERO;
            this.lkRespInsurance = BigDecimal.ZERO;
            this.lkRespTotal = BigDecimal.ZERO;
        }
    }
}
