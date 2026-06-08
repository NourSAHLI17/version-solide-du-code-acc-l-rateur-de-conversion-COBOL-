package com.modernized.loaneval;

import com.modernized.calcfee.CalcFee;
import com.modernized.calcfee.FeeRequest;
import com.modernized.calcfee.FeeResponse;
import com.modernized.chkaml.AmlRequest;
import com.modernized.chkaml.AmlResponse;
import com.modernized.chkaml.ChkAmlService;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import java.util.ArrayList;
import java.util.List;
import java.util.Comparator;

public class Loaneval {

// File paths (hardcoded as per config)
    private static final Path LOAN_FILE_PATH = Path.of("LOANFILE.dat");
// Sector matrix (12 entries)
    private static final int SECTOR_MATRIX_SIZE = 12;
private static final Path COLLATERAL_FILE_PATH = Path.of("COLFILE.dat");
private static final Path CUSTOMER_FILE_PATH = Path.of("CUSTFILE.dat");
private static final Path DECISION_REPORT_PATH = Path.of("DECIRPT.dat");
private static final Path GUARANTEE_FILE_PATH = Path.of("GUARFILE.dat");
private static final Path REJECT_LOG_PATH = Path.of("EVALREJ.dat");
private static final Path SCORE_FILE_PATH = Path.of("SCORFILE.dat");
private final BigDecimal[] sctAdjustment = new BigDecimal[SECTOR_MATRIX_SIZE];
private final BigDecimal[] wscWeight = new BigDecimal[5];
private final CalcFee calcFee =;
private final CalcFee calcFee = new CalcFee();
private final CalcFee calcFeeService;
private final ChkAmlService chkAmlService =;
private final ChkAmlService chkAmlService = new ChkAmlService();
private final ChkAmlService chkAmlService;
private final int[] wscRank = new int[5];
private final int[] wscScore = new int[5];
private final String[] sctCode = new String[SECTOR_MATRIX_SIZE];
private final String[] sctLabel = new String[SECTOR_MATRIX_SIZE];
private final String[] wscName = new String[5];
//;
//;
//;
// Collateral and Guarantee records buffers (simulate indexed file access)
    private List<CollateralRecord> collateralRecords = new ArrayList<>();
// Computed values;
// Decision line fields;
// External services;
// File readers/writers;
// Placeholder classes for file records and external DTOs;
// Reject detail fields;
// Score parameters;
// Scoring components;
// Working storage variables;
//;
//;
//;
//;
private BigDecimal scrMaxLoanAmt = BigDecimal.ZERO;
private BigDecimal scrMaxRate = BigDecimal.ZERO;
private BigDecimal scrWeightCollat;
private BigDecimal scrWeightDscr;
private BigDecimal scrWeightHistory;
private BigDecimal scrWeightIncome;
private BigDecimal scrWeightTenure;
private BigDecimal statApprovedAmt = BigDecimal.ZERO;
private BigDecimal statDeclinedAmt = BigDecimal.ZERO;
private BigDecimal statTotalAmt = BigDecimal.ZERO;
private BigDecimal wsIncomeToPmt = BigDecimal.ZERO;
private BigDecimal wsMonthlyDebtServ = BigDecimal.ZERO;
private BigDecimal wsNormalizedIncome = BigDecimal.ZERO;
private BigDecimal wsTotalCollatValue = BigDecimal.ZERO;
private BigDecimal wsTotalExistingDebt = BigDecimal.ZERO;
private BigDecimal wsTotalGuarValue = BigDecimal.ZERO;
private BufferedReader collateralFileReader;
private BufferedReader customerFileReader;
private BufferedReader guaranteeFileReader;
private BufferedReader loanFileReader;
private BufferedWriter decisionReportWriter;
private BufferedWriter rejectLogWriter;
private BufferedWriter scoreFileWriter;
private CustomerRecord currentCustomerRecord;
private int decCustId;
private int decLoanId;
private int rejCustId;
private int rejLoanId;
private int scrAnalystId;
private int scrCustId;
private int scrDate;
private int scrLoanId;
private int scrMaxScore;
private int scrMinApprove;
private int scrMinCond;
private int scrMinReview;
private int scrResultId;
private int scrTotalScore;
private int statApproved;
private int statConditional;
private int statDeclined;
private int statErrors;
private int statRead;
private int wsBankTenureYears;
private int wsBureauAdjustment;
private int wsCurrentCustId;
private int wsCurrentLoanId;
private int wsReturnCode;
private int wsScoreSeq;
private int wsSectorAdjustment;
private int wsTodayDate;
private int wsTodayTime;
private List<GuaranteeRecord> guaranteeRecords = new ArrayList<>();
private LoanRecord currentLoanRecord;
private String decAmount = "";
private String decDecision = "";
private String decLoanType = "";
private String decRate = "";
private String decReason = "";
private String decScore = "";
private String rejReason = "";
private String scrDecision = "  ";
private String scrModelVersion;
private String scrReason1 = "";
private String scrReason2 = "";
private String scrReason3 = "";
private String wsAmlClear = "N";
private String wsAmlReason = "";
private String wsCollateralFound = "N";
private String wsEndLoanFile = "N";
private String wsGuaranteeFound = "N";
private String wsProgramName;

    public Loaneval() {
        this.chkAmlService = new ChkAmlService();
        this.calcFeeService = new CalcFee();
    }

    public void main() throws IOException {
        wsProgramName = "LOANEVAL";
        wsTodayDate = getCurrentDateYYYYMMDD();
        wsTodayTime = getCurrentTimeHHMMSS();

        System.out.println("LOANEVAL v6.0 - START " + wsTodayDate + "-" + wsTodayTime);

        openFiles();
        if (wsReturnCode != 0) {
            System.out.println("LOANEVAL ABEND: " + wsAmlReason);
            System.exit(12);
        }

        loadScoreParams();
        loadSectorMatrix();
        initReport();

        while (!"Y".equals(wsEndLoanFile)) {
            processLoans();
        }

        writeSummary();
        closeFiles();

        System.out.println("LOANEVAL COMPLETED.");
        System.out.println("  READ        : " + statRead);
        System.out.println("  APPROVED    : " + statApproved);
        System.out.println("  CONDITIONAL : " + statConditional);
        System.out.println("  DECLINED    : " + statDeclined);
        System.out.println("  ERRORS      : " + statErrors);

        if (statErrors > 0) {
            System.exit(4);
        } else {
            System.exit(0);
        }
    }

    private static String addThousandsSeparator(String number) {
        StringBuilder sb = new StringBuilder();
        int len = number.length();
        int count = 0;
        for (int i = len - 1; i >= 0; i--) {
            sb.append(number.charAt(i));
            count++;
            if (count == 3 && i > 0) {
                sb.append(',');
                count = 0;
            }
        }
        return sb.reverse().toString();
    }

    private void applyDecision() {
        if (scrTotalScore >= scrMinApprove) {
            scrDecision = "AP";
            statApproved++;
            computeMaxLoan();
            computePricing();
            statApprovedAmt = statApprovedAmt.add(currentLoanRecord.getOriginalAmount());
        } else if (scrTotalScore >= scrMinCond) {
            scrDecision = "CO";
            statConditional++;
            computeMaxLoan();
            computePricing();
        } else if (scrTotalScore >= scrMinReview) {
            scrDecision = "RV";
            statConditional++;
        } else {
            scrDecision = "DC";
            statDeclined++;
            statDeclinedAmt = statDeclinedAmt.add(currentLoanRecord.getOriginalAmount());
            scrMaxLoanAmt = BigDecimal.ZERO;
        }
    }

    private void callFeeCalculation() {        FeeRequest feeRequest = new FeeRequest();
        feeRequest.setLoanType(currentLoanRecord.getLoanType());
        feeRequest.setAmount(currentLoanRecord.getOriginalAmount());
        feeRequest.setRate(scrMaxRate);

        FeeResponse feeResponse = calcFeeService.calculate(feeRequest);

        // Fee response fields can be stored or used as needed
        // CALL 'CALCFEE' USING WS-FEE-REQUEST WS-FEE-RESPONSE
        // Build request from working storage
        CalcFee.FeeRequest feeRequest = new CalcFee.FeeRequest(
            wsFeeRequest.getLoanType(),
            wsFeeRequest.getAmount(),
            wsFeeRequest.getRate()
        );
        // Call sub-program
        CalcFee.FeeResponse feeResponse = calcFee.calculate(feeRequest);
        // Copy response back to working storage
        wsFeeResponse.setFileFee(feeResponse.getFileFee());
        wsFeeResponse.setTax(feeResponse.getTax());
        wsFeeResponse.setInsurance(feeResponse.getInsurance());
        wsFeeResponse.setTotal(feeResponse.getTotal());
    }

    private void closeFiles() {
        closeQuietly(loanFileReader);
        closeQuietly(customerFileReader);
        closeQuietly(collateralFileReader);
        closeQuietly(guaranteeFileReader);
        closeQuietly(scoreFileWriter);
        closeQuietly(decisionReportWriter);
        closeQuietly(rejectLogWriter);
    }

    private static void closeQuietly(AutoCloseable c) {
        if (c != null) {
            try {
                c.close();
            } catch (Exception ignored) {
            }
        }
    }

    private void computeMaxLoan() {
        scrMaxLoanAmt = wsNormalizedIncome.multiply(BigDecimal.valueOf(12)).multiply(new BigDecimal("0.40"))
                .setScale(2, RoundingMode.DOWN);

        if (wsTotalCollatValue.compareTo(BigDecimal.ZERO) > 0) {
            wsTotalCollatValue = wsTotalCollatValue.multiply(new BigDecimal("0.80")).setScale(2, RoundingMode.DOWN);
            if (wsTotalCollatValue.compareTo(scrMaxLoanAmt) < 0) {
                scrMaxLoanAmt = wsTotalCollatValue;
            }
        }
        if (currentLoanRecord.getOriginalAmount().compareTo(scrMaxLoanAmt) < 0) {
            scrMaxLoanAmt = currentLoanRecord.getOriginalAmount();
        }
    }

    private void computePricing() {
        BigDecimal baseRate = new BigDecimal("7.25");
        if (scrTotalScore >= 850) {
            scrMaxRate = baseRate.add(new BigDecimal("1.50")).setScale(4, RoundingMode.DOWN);
        } else if (scrTotalScore >= 700) {
            scrMaxRate = baseRate.add(new BigDecimal("2.50")).setScale(4, RoundingMode.DOWN);
        } else if (scrTotalScore >= 600) {
            scrMaxRate = baseRate.add(new BigDecimal("3.50")).setScale(4, RoundingMode.DOWN);
        } else {
            scrMaxRate = baseRate.add(new BigDecimal("4.50")).setScale(4, RoundingMode.DOWN);
        }
    }

    private void computeScore() {
        // Reset scores and reasons
        int scrIncomeScore = 0;
        int scrHistoryScore = 0;
        int scrDscrScore = 0;
        int scrCollatScore = 0;
        int scrTenureScore = 0;
        scrReason1 = "";
        scrReason2 = "";
        scrReason3 = "";

        scoreIncome(scrIncomeScore);
        scoreHistory(scrHistoryScore);
        scoreDscr(scrDscrScore);
        scoreCollateral(scrCollatScore);
        scoreTenure(scrTenureScore);

        // Compute raw score
        BigDecimal rawScore = BigDecimal.valueOf(scrIncomeScore).multiply(scrWeightIncome)
                .add(BigDecimal.valueOf(scrHistoryScore).multiply(scrWeightHistory))
                .add(BigDecimal.valueOf(scrDscrScore).multiply(scrWeightDscr))
                .add(BigDecimal.valueOf(scrCollatScore).multiply(scrWeightCollat))
                .add(BigDecimal.valueOf(scrTenureScore).multiply(scrWeightTenure))
                .divide(BigDecimal.valueOf(100), 0, RoundingMode.HALF_UP);

        scrTotalScore = rawScore.intValue();

        // Final score with adjustments
        int finalScore = scrTotalScore + wsBureauAdjustment + wsSectorAdjustment;
        if (finalScore > scrMaxScore) {
            finalScore = scrMaxScore;
        }
        if (finalScore < 0) {
            finalScore = 0;
        }
        scrTotalScore = finalScore;

        // Store component scores for ranking
        wscName[0] = "INCOME  ";
        wscWeight[0] = scrWeightIncome;
        wscScore[0] = scrIncomeScore;

        wscName[1] = "HISTORY ";
        wscWeight[1] = scrWeightHistory;
        wscScore[1] = scrHistoryScore;

        wscName[2] = "DSCR    ";
        wscWeight[2] = scrWeightDscr;
        wscScore[2] = scrDscrScore;

        wscName[3] = "COLLAT  ";
        wscWeight[3] = scrWeightCollat;
        wscScore[3] = scrCollatScore;

        wscName[4] = "TENURE  ";
        wscWeight[4] = scrWeightTenure;
        wscScore[4] = scrTenureScore;
    }

    private void externalAmlCheck() {        AmlRequest amlRequest = new AmlRequest();
        amlRequest.setCustId(currentCustomerRecord.getCustId());
        amlRequest.setCin(currentCustomerRecord.getCin());
        amlRequest.setName(currentCustomerRecord.getFirstName() + " " + currentCustomerRecord.getLastName());
        amlRequest.setDob(currentCustomerRecord.getDateOfBirth());
        amlRequest.setNationality(currentCustomerRecord.getNationality());
        amlRequest.setAmount(currentLoanRecord.getOriginalAmount());

        AmlResponse amlResponse = chkAmlService.checkAml(amlRequest);

        wsAmlClear = amlResponse.getClear();
        wsAmlReason = amlResponse.getReason();
        // CALL 'CHKAML' USING WS-AML-REQUEST WS-AML-RESPONSE
        // Build request from working storage
        ChkAmlService.AmlRequest amlRequest = new ChkAmlService.AmlRequest(
            wsAmlRequest.getCustId(),
            wsAmlRequest.getCin(),
            wsAmlRequest.getName(),
            wsAmlRequest.getDob(),
            wsAmlRequest.getNationality(),
            wsAmlRequest.getAmount()
        );
        // Call sub-program
        ChkAmlService.AmlResponse amlResponse = chkAmlService.checkAml(amlRequest);
        // Copy response back to working storage
        wsAmlResponse.setClear(amlResponse.getClear());
        wsAmlResponse.setScore(amlResponse.getScore());
        wsAmlResponse.setReason(amlResponse.getReason());
    }

    private void fetchBureauScore() {
        wsBureauAdjustment = 0;
        // Fallback synthetic bureau score from custId hash mod 200 - 100
        wsBureauAdjustment = (wsCurrentCustId % 200) - 100;
    }

    private void fetchSectorAdjustment() {
        wsSectorAdjustment = 0;
        String employer = currentCustomerRecord.getEmployer();
        String sectorCode;

        if (employer.length() >= 6 && employer.substring(0, 6).equals("BANQUE")) {
            sectorCode = "BANK";
        } else if (employer.length() >= 10 && employer.substring(0, 10).equals("MINISTERE ")) {
            sectorCode = "ADMI";
        } else if (employer.length() >= 8 && employer.substring(0, 8).equals("TUNISIE ")) {
            sectorCode = "TELE";
        } else if ((employer.length() >= 6 && employer.substring(0, 6).equals("ORANGE")) ||
                (employer.length() >= 7 && employer.substring(0, 7).equals("OOREDOO"))) {
            sectorCode = "TELE";
        } else if (employer.length() >= 8 && employer.substring(0, 8).equals("PHARMACI")) {
            sectorCode = "PHAR";
        } else if ((employer.length() >= 8 && employer.substring(0, 8).equals("HOTEL  ")) ||
                (employer.length() >= 6 && employer.substring(0, 6).equals("TUNISA"))) {
            sectorCode = "TOUR";
        } else if (employer.length() >= 7 && employer.substring(0, 7).equals("GROUPE ")) {
            sectorCode = "INDS";
        } else if (employer.length() >= 8 && employer.substring(0, 8).equals("COMMERCE")) {
            sectorCode = "COMM";
        } else if (employer.length() >= 7 && employer.substring(0, 7).equals("ARTISAN")) {
            sectorCode = "COMM";
        } else {
            sectorCode = "AUTR";
        }

        for (int i = 0; i < SECTOR_MATRIX_SIZE; i++) {
            if (sctCode[i].equals(sectorCode)) {
                wsSectorAdjustment = sctAdjustment[i].intValue();
                break;
            }
        }
    }

    Utility methods;

    private static int getCurrentDateYYYYMMDD() {
        java.time.LocalDate now = java.time.LocalDate.now();
        return now.getYear() * 10000 + now.getMonthValue() * 100 + now.getDayOfMonth();
    }

    private static int getCurrentTimeHHMMSS() {
        java.time.LocalTime now = java.time.LocalTime.now();
        return now.getHour() * 10000 + now.getMinute() * 100 + now.getSecond();
    }

    private void initReport() throws IOException {
        // Write report headers (hardcoded lines as per copybook RPTCOPY2)
        decisionReportWriter.write("LOANEVAL\n");
        decisionReportWriter.write("RAPPORT EVALUATION CREDITS - PRODUCTION\n");
        decisionReportWriter.write("-------------------------------------------------------------\n");
        decisionReportWriter.write("LOAN ID  CUST ID  TYPE  AMOUNT     RATE   SCORE  DECISION\n");
        decisionReportWriter.write("-------------------------------------------------------------\n");
        decisionReportWriter.flush();
    }

    private void loadCollateral() throws IOException {
        wsTotalCollatValue = BigDecimal.ZERO;
        wsCollateralFound = "N";

        // Load all collateral records for current loan id
        collateralRecords.clear();
        collateralFileReader.close();
        collateralFileReader = Files.newBufferedReader(COLLATERAL_FILE_PATH, StandardCharsets.UTF_8);
        String line;
        while ((line = collateralFileReader.readLine()) != null) {
            CollateralRecord collat = CollateralRecord.fromFixedWidth(line);
            if (collat.getLoanId() == wsCurrentLoanId) {
                wsCollateralFound = "Y";
                collateralRecords.add(collat);
            }
        }

        // Sum active collateral appraisal values
        for (CollateralRecord collat : collateralRecords) {
            if (collat.isActive()) {
                wsTotalCollatValue = wsTotalCollatValue.add(collat.getAppraisalValue());
            }
        }
    }

    private void loadCustomer() throws IOException {
        // Simulate random access by scanning customer file for matching custId
        wsReturnCode = 12; // default not found
        customerFileReader.close();
        customerFileReader = Files.newBufferedReader(CUSTOMER_FILE_PATH, StandardCharsets.UTF_8);
        String line;
        while ((line = customerFileReader.readLine()) != null) {
            CustomerRecord cust = CustomerRecord.fromFixedWidth(line);
            if (cust.getCustId() == wsCurrentCustId) {
                currentCustomerRecord = cust;
                wsReturnCode = 0;
                return;
            }
        }
        currentCustomerRecord = null;
    }

    private void loadGuarantees() throws IOException {
        wsTotalGuarValue = BigDecimal.ZERO;
        wsGuaranteeFound = "N";

        guaranteeRecords.clear();
        guaranteeFileReader.close();
        guaranteeFileReader = Files.newBufferedReader(GUARANTEE_FILE_PATH, StandardCharsets.UTF_8);
        String line;
        while ((line = guaranteeFileReader.readLine()) != null) {
            GuaranteeRecord guar = GuaranteeRecord.fromFixedWidth(line);
            if (guar.getLoanId() == wsCurrentLoanId) {
                wsGuaranteeFound = "Y";
                guaranteeRecords.add(guar);
            }
        }

        for (GuaranteeRecord guar : guaranteeRecords) {
            if (guar.isActive()) {
                wsTotalGuarValue = wsTotalGuarValue.add(guar.getAmount());
            }
        }
    }

    private void loadScoreParams() {
        scrModelVersion = "2024.1";
        scrMaxScore = 1000;
        scrMinApprove = 600;
        scrMinCond = 450;
        scrMinReview = 350;
        scrWeightIncome = new BigDecimal("25.00");
        scrWeightHistory = new BigDecimal("30.00");
        scrWeightDscr = new BigDecimal("20.00");
        scrWeightCollat = new BigDecimal("15.00");
        scrWeightTenure = new BigDecimal("10.00");
    }

    private void loadSectorMatrix() {
        // Hardcoded fallback sector matrix
        sctCode[0] = "BANK";
        sctLabel[0] = "SECTEUR BANCAIRE";
        sctAdjustment[0] = new BigDecimal("25.00");

        sctCode[1] = "ADMI";
        sctLabel[1] = "ADMINISTRATION PUBLIQUE";
        sctAdjustment[1] = new BigDecimal("30.00");

        sctCode[2] = "INDS";
        sctLabel[2] = "INDUSTRIE MANUFACTURIERE";
        sctAdjustment[2] = new BigDecimal("15.00");

        sctCode[3] = "COMM";
        sctLabel[3] = "COMMERCE GROS DETAIL";
        sctAdjustment[3] = new BigDecimal("5.00");

        sctCode[4] = "AGRI";
        sctLabel[4] = "AGRICULTURE PECHE";
        sctAdjustment[4] = new BigDecimal("-10.00");

        sctCode[5] = "TOUR";
        sctLabel[5] = "TOURISME HOTELLERIE";
        sctAdjustment[5] = new BigDecimal("-15.00");

        sctCode[6] = "CONS";
        sctLabel[6] = "CONSTRUCTION BTP";
        sctAdjustment[6] = new BigDecimal("-5.00");

        sctCode[7] = "TRSP";
        sctLabel[7] = "TRANSPORT LOGISTIQUE";
        sctAdjustment[7] = new BigDecimal("10.00");

        sctCode[8] = "PROF";
        sctLabel[8] = "PROFESSIONS LIBERALES";
        sctAdjustment[8] = new BigDecimal("20.00");

        sctCode[9] = "PHAR";
        sctLabel[9] = "PHARMACIE SANTE";
        sctAdjustment[9] = new BigDecimal("25.00");

        sctCode[10] = "TELE";
        sctLabel[10] = "TELECOMMUNICATIONS";
        sctAdjustment[10] = new BigDecimal("20.00");

        sctCode[11] = "AUTR";
        sctLabel[11] = "AUTRES SECTEURS";
        sctAdjustment[11] = new BigDecimal("0.00");
    }

    private void normalizeIncome() {
        String incomeRaw = currentCustomerRecord.getMonthlyIncome();
        // Replace spaces and '-' with '0'
        incomeRaw = incomeRaw.replace(' ', '0').replace('-', '0');
        // Parse whole and cents parts
        if (incomeRaw.length() < 9) {
            incomeRaw = String.format("%-9s", incomeRaw).substring(0, 9);
        }
        String wholePartStr = incomeRaw.substring(0, 7);
        String centsPartStr = incomeRaw.substring(7, 9);
        int wholePart = parseIntSafe(wholePartStr);
        int centsPart = parseIntSafe(centsPartStr);
        if (wholePart == 0 && centsPart == 0) {
            wsNormalizedIncome = BigDecimal.ZERO;
        } else {
            wsNormalizedIncome = BigDecimal.valueOf(wholePart).add(BigDecimal.valueOf(centsPart).movePointLeft(2));
        }
        wsNormalizedIncome = wsNormalizedIncome.setScale(2, RoundingMode.DOWN);
    }

    private void openFiles() {
        try {
            loanFileReader = Files.newBufferedReader(LOAN_FILE_PATH, StandardCharsets.UTF_8);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsAmlReason = "LOANFILE OPEN FAILED";
            return;
        }

        try {
            customerFileReader = Files.newBufferedReader(CUSTOMER_FILE_PATH, StandardCharsets.UTF_8);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsAmlReason = "CUSTFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            return;
        }

        try {
            collateralFileReader = Files.newBufferedReader(COLLATERAL_FILE_PATH, StandardCharsets.UTF_8);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsAmlReason = "COLFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            return;
        }

        try {
            guaranteeFileReader = Files.newBufferedReader(GUARANTEE_FILE_PATH, StandardCharsets.UTF_8);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsAmlReason = "GUARFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            closeQuietly(collateralFileReader);
            return;
        }

        try {
            scoreFileWriter = Files.newBufferedWriter(SCORE_FILE_PATH, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.WRITE);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsAmlReason = "SCORFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            closeQuietly(collateralFileReader);
            closeQuietly(guaranteeFileReader);
            return;
        }

        try {
            decisionReportWriter = Files.newBufferedWriter(DECISION_REPORT_PATH, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.WRITE);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsAmlReason = "DECIRPT OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            closeQuietly(collateralFileReader);
            closeQuietly(guaranteeFileReader);
            closeQuietly(scoreFileWriter);
            return;
        }

        try {
            rejectLogWriter = Files.newBufferedWriter(REJECT_LOG_PATH, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.WRITE);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsAmlReason = "EVALREJ OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            closeQuietly(collateralFileReader);
            closeQuietly(guaranteeFileReader);
            closeQuietly(scoreFileWriter);
            closeQuietly(decisionReportWriter);
            return;
        }

        wsReturnCode = 0;
        readNextLoan();
    }

    private static String padRight(String s, int n) {
        if (s == null) s = "";
        if (s.length() > n) return s.substring(0, n);
        return String.format("%-" + n + "s", s);
    }

    private void processLoans() throws IOException {
        statRead++;
        if (currentLoanRecord == null) {
            wsEndLoanFile = "Y";
            return;
        }
        wsCurrentLoanId = currentLoanRecord.getLoanId();
        wsCurrentCustId = currentLoanRecord.getCustId();
        statTotalAmt = statTotalAmt.add(currentLoanRecord.getOriginalAmount());

        validatePreconditions();
        if (wsReturnCode == 12) {
            statErrors++;
            writeReject();
            readNextLoan();
            return;
        }

        loadCustomer();
        if (wsReturnCode != 0) {
            statErrors++;
            wsAmlReason = "CUSTOMER NOT FOUND: " + wsCurrentCustId;
            writeReject();
            readNextLoan();
            return;
        }

        normalizeIncome();
        validateCustomer();
        if (wsReturnCode == 8) {
            statDeclined++;
            writeReject();
            readNextLoan();
            return;
        }

        externalAmlCheck();
        if (!"Y".equals(wsAmlClear)) {
            statDeclined++;
            wsAmlReason = wsAmlReason.trim();
            writeReject();
            readNextLoan();
            return;
        }

        fetchBureauScore();
        fetchSectorAdjustment();
        loadCollateral();
        loadGuarantees();
        computeScore();
        rankComponents();
        applyDecision();
        callFeeCalculation();
        writeScoreRecord();
        writeDecisionLine();
        readNextLoan();
    }

    private void rankComponents() {
        // Create list of components for sorting
        List<SortComponentRec> components = new ArrayList<>();
        for (int i = 0; i < 5; i++) {
            SortComponentRec rec = new SortComponentRec();
            rec.setSortComponentName(wscName[i]);
            rec.setSortComponentWeight(wscWeight[i]);
            rec.setSortComponentScore(wscScore[i]);
            rec.setSortComponentRank(0);
            components.add(rec);
        }

        // Sort descending by score
        components.sort(Comparator.comparingInt(SortComponentRec::getSortComponentScore).reversed());

        // Assign ranks and update arrays
        for (int i = 0; i < components.size(); i++) {
            SortComponentRec rec = components.get(i);
            rec.setSortComponentRank(i + 1);
            wscName[i] = rec.getSortComponentName();
            wscRank[i] = i + 1;
        }
        sortComponents();
    }

    private void readNextLoan() throws IOException {
        String line = loanFileReader.readLine();
        if (line == null) {
            wsEndLoanFile = "Y";
            currentLoanRecord = null;
        } else {
            currentLoanRecord = LoanRecord.fromFixedWidth(line);
        }
    }

    private void scoreCollateral(int scrCollatScore) {
        wsTotalCollatValue = wsTotalCollatValue.add(wsTotalGuarValue);
        if (wsTotalCollatValue.compareTo(BigDecimal.ZERO) == 0) {
            scrCollatScore = 0;
            return;
        }
        BigDecimal ltvRatio = currentLoanRecord.getOutstandingAmount()
                .divide(wsTotalCollatValue, 4, RoundingMode.HALF_UP)
                .multiply(new BigDecimal("100"));

        if (ltvRatio.compareTo(new BigDecimal("60")) <= 0) {
            scrCollatScore = 1000;
        } else if (ltvRatio.compareTo(new BigDecimal("70")) <= 0) {
            scrCollatScore = 800;
        } else if (ltvRatio.compareTo(new BigDecimal("80")) <= 0) {
            scrCollatScore = 600;
        } else if (ltvRatio.compareTo(new BigDecimal("90")) <= 0) {
            scrCollatScore = 400;
        } else if (ltvRatio.compareTo(new BigDecimal("100")) <= 0) {
            scrCollatScore = 200;
        } else {
            scrCollatScore = 0;
        }
    }

    private void scoreDscr(int scrDscrScore) {
        wsMonthlyDebtServ = currentLoanRecord.getMonthlyPayment().add(wsTotalExistingDebt);
        if (wsMonthlyDebtServ.compareTo(BigDecimal.ZERO) == 0) {
            scrDscrScore = 1000;
            return;
        }
        BigDecimal dscrRatio = wsNormalizedIncome.divide(wsMonthlyDebtServ, 4, RoundingMode.HALF_UP);

        BigDecimal onePointFive = new BigDecimal("1.5");
        BigDecimal onePointTwo = new BigDecimal("1.2");
        BigDecimal one = new BigDecimal("1.0");
        BigDecimal zeroPointEight = new BigDecimal("0.8");

        if (dscrRatio.compareTo(onePointFive) >= 0) {
            scrDscrScore = 1000;
        } else if (dscrRatio.compareTo(onePointTwo) >= 0) {
            scrDscrScore = 750;
        } else if (dscrRatio.compareTo(one) >= 0) {
            scrDscrScore = 500;
        } else if (dscrRatio.compareTo(zeroPointEight) >= 0) {
            scrDscrScore = 250;
            scrReason3 = "TAUX DE COUVERTURE FAIBLE";
        } else {
            scrDscrScore = 0;
            scrReason3 = "CAPACITE REMBOURSEMENT INSUFFISANTE";
        }
    }

    private void scoreHistory(int scrHistoryScore) {
        int daysPastDue = currentLoanRecord.getDaysPastDue();
        int missedPmts = currentLoanRecord.getMissedPayments();

        if (daysPastDue == 0 && missedPmts == 0) {
            scrHistoryScore = 1000;
        } else if (daysPastDue <= 30) {
            scrHistoryScore = 700;
        } else if (daysPastDue <= 90) {
            scrHistoryScore = 400;
            scrReason1 = "RETARDS DE PAIEMENT DETECTES";
        } else if (daysPastDue <= 180) {
            scrHistoryScore = 150;
            scrReason1 = "CREANCE CLASSEE - SUIVI REQUIS";
        } else {
            scrHistoryScore = 0;
            scrReason1 = "CREANCE EN SOUFFRANCE > 180 JOURS";
        }
    }

    private void scoreIncome(int scrIncomeScore) {
        if (wsNormalizedIncome.compareTo(BigDecimal.ZERO) == 0 || currentLoanRecord.getMonthlyPayment().compareTo(BigDecimal.ZERO) == 0) {
            scrIncomeScore = 0;
            scrReason2 = "REVENU OU MENSUALITE NULS";
            return;
        }
        wsIncomeToPmt = wsNormalizedIncome.divide(currentLoanRecord.getMonthlyPayment(), 4, RoundingMode.HALF_UP);

        BigDecimal three = new BigDecimal("3.0");
        BigDecimal twoPointFive = new BigDecimal("2.5");
        BigDecimal two = new BigDecimal("2.0");
        BigDecimal onePointFive = new BigDecimal("1.5");
        BigDecimal onePointTwo = new BigDecimal("1.2");

        if (wsIncomeToPmt.compareTo(three) >= 0) {
            scrIncomeScore = 1000;
        } else if (wsIncomeToPmt.compareTo(twoPointFive) >= 0) {
            scrIncomeScore = 850;
        } else if (wsIncomeToPmt.compareTo(two) >= 0) {
            scrIncomeScore = 700;
        } else if (wsIncomeToPmt.compareTo(onePointFive) >= 0) {
            scrIncomeScore = 500;
        } else if (wsIncomeToPmt.compareTo(onePointTwo) >= 0) {
            scrIncomeScore = 300;
        } else {
            scrIncomeScore = 0;
            scrReason2 = "RATIO REVENU/MENSUALITE INSUFFISANT";
        }
    }

    private void scoreTenure(int scrTenureScore) {
        wsBankTenureYears = (wsTodayDate - currentCustomerRecord.getOpenDate()) / 10000;

        if (wsBankTenureYears >= 10) {
            scrTenureScore = 1000;
        } else if (wsBankTenureYears >= 7) {
            scrTenureScore = 800;
        } else if (wsBankTenureYears >= 5) {
            scrTenureScore = 600;
        } else if (wsBankTenureYears >= 3) {
            scrTenureScore = 400;
        } else if (wsBankTenureYears >= 1) {
            scrTenureScore = 200;
        } else {
            scrTenureScore = 0;
        }
    }

    private void sortComponents() {
        List<SortComponentRec> sortBuffer = new ArrayList<>();
        // INPUT PROCEDURE
        loadSort(sortBuffer);
        // SORT — descending SORT-COMPONENT-SCORE
        sortBuffer.sort((a, b) -> Integer.compare(b.sortComponentScore, a.sortComponentScore));
        // OUTPUT PROCEDURE
        rankOutput(sortBuffer);
    }

    private void validateCustomer() {
        wsReturnCode = 0;
        if (currentCustomerRecord.isBlacklisted()) {
            wsReturnCode = 8;
            wsAmlReason = "CLIENT BLACKLISTE - DEMANDE REFUSEE";
            return;
        }
        if (currentCustomerRecord.isAmlAlert()) {
            wsReturnCode = 8;
            wsAmlReason = "ALERTE AML EN COURS";
            return;
        }
        if (!currentCustomerRecord.isKycOk()) {
            wsReturnCode = 8;
            wsAmlReason = "KYC NON VALIDE - STATUT: " + currentCustomerRecord.getKycStatus();
            return;
        }
        if (currentCustomerRecord.isPep()) {
            scrReason1 = "DOSSIER PEP - VALIDATION MANUELLE";
        }
        if (!currentCustomerRecord.isActive()) {
            wsReturnCode = 8;
            wsAmlReason = "CLIENT INACTIF";
        }
    }

    private void validatePreconditions() {
        wsReturnCode = 0;
        if (wsCurrentLoanId == 0) {
            wsReturnCode = 12;
            wsAmlReason = "LOAN-ID IS ZERO - INVALID RECORD";
            return;
        }
        if (currentLoanRecord.getOriginalAmount().compareTo(BigDecimal.ZERO) == 0) {
            wsReturnCode = 12;
            wsAmlReason = "LOAN AMOUNT IS ZERO";
            return;
        }
        if (!currentLoanRecord.isActive() && !currentLoanRecord.isRestructured()) {
            wsReturnCode = 12;
            wsAmlReason = "LOAN STATUS NOT ELIGIBLE FOR EVALUATION";
        }
    }

    private void writeDecisionLine() throws IOException {
        if (wsLineCount >= wsMaxLines) {
            wsPageNo++;
            wsLineCount = 2;
            // Write headers for new page
            decisionReportWriter.write("LOANEVAL\n");
            decisionReportWriter.write("-------------------------------------------------------------\n");
        }

        decLoanId = wsCurrentLoanId;
        decCustId = wsCurrentCustId;
        decLoanType = currentLoanRecord.getLoanType();
        decAmount = formatAmount(currentLoanRecord.getOriginalAmount());
        decRate = formatRate(currentLoanRecord.getInterestRate());
        decScore = String.format("%4d", scrTotalScore).trim();

        switch (scrDecision) {
            case "AP" -> decDecision = "APPROUVE   ";
            case "CO" -> decDecision = "CONDITIONNEL";
            case "RV" -> decDecision = "A ETUDIER  ";
            case "DC" -> decDecision = "REFUSE     ";
            default -> decDecision = "UNKNOWN    ";
        }
        decReason = scrReason1;

        String line = String.format("%010d  %08d  %-3s  %11s  %6s  %4s  %-11s  %-50s",
                decLoanId, decCustId, decLoanType, decAmount, decRate, decScore, decDecision, decReason);
        decisionReportWriter.write(line);
        decisionReportWriter.newLine();
        decisionReportWriter.flush();

        wsLineCount++;
    }

    private void writeReject() throws IOException {
        rejLoanId = wsCurrentLoanId;
        rejCustId = wsCurrentCustId;
        rejReason = wsAmlReason;
        String line = String.format("%010d  %08d  %-80s", rejLoanId, rejCustId, rejReason);
        rejectLogWriter.write(line);
        rejectLogWriter.newLine();
        rejectLogWriter.flush();
    }

    private void writeScoreRecord() throws IOException {
        wsScoreSeq++;
        scrResultId = wsScoreSeq;
        scrLoanId = wsCurrentLoanId;
        scrCustId = wsCurrentCustId;
        scrDate = wsTodayDate;

        // Compose fixed-width record line for score file
        StringBuilder sb = new StringBuilder(229);
        sb.append(String.format("%012d", scrResultId));
        sb.append(String.format("%010d", scrLoanId));
        sb.append(String.format("%08d", scrCustId));
        sb.append(String.format("%08d", scrDate));
        sb.append(String.format("%04d", scrTotalScore));
        sb.append(scrDecision);
        sb.append(String.format("%013.2f", scrMaxLoanAmt));
        sb.append(String.format("%06.4f", scrMaxRate));
        sb.append(padRight(scrReason1, 50));
        sb.append(padRight(scrReason2, 50));
        sb.append(padRight(scrReason3, 50));
        sb.append(String.format("%06d", scrAnalystId));
        sb.append("          "); // filler 10 spaces

        scoreFileWriter.write(sb.toString());
        scoreFileWriter.newLine();
        scoreFileWriter.flush();
    }

    private void writeSummary() throws IOException {
        decisionReportWriter.write("-------------------------------------------------------------\n");
        String totalsLine = String.format("TOTAUX: TRAITES=%d APPROUVES=%d CONDITIONNEL=%d REFUSES=%d",
                statRead, statApproved, statConditional, statDeclined);
        decisionReportWriter.write(totalsLine + "\n");
        String amountLine = String.format("MONTANT TOTAL: %s  APPROUVE: %s",
                statTotalAmt.toPlainString(), statApprovedAmt.toPlainString());
        decisionReportWriter.write(amountLine + "\n");
        decisionReportWriter.write("-------------------------------------------------------------\n");
        decisionReportWriter.flush();
    }

    private static String formatAmount(BigDecimal amount) {
        // Format with comma thousands separator and no decimals
        String plain = amount.setScale(0, RoundingMode.DOWN).toPlainString();
        return addThousandsSeparator(plain);
    }

    private static String formatRate(BigDecimal rate) {
        // Format with 4 decimals, no thousands separator
        return rate.setScale(4, RoundingMode.DOWN).toPlainString();
    }

    private static int parseIntSafe(String s) {
        try {
            return Integer.parseInt(s.trim());
        } catch (NumberFormatException e) {
            return 0;
        }
    }


    public static class CollateralRecord {
        private int loanId;
        private boolean active;
        private BigDecimal appraisalValue;

        public static CollateralRecord fromFixedWidth(String line) {
            // Parse fixed-width line into CollateralRecord fields
            // Placeholder: implement parsing logic according to COLLATCOPY layout
            return new CollateralRecord();
        }

        public int getLoanId() {
            return loanId;
        }

        public boolean isActive() {
            return active;
        }

        public BigDecimal getAppraisalValue() {
            return appraisalValue == null ? BigDecimal.ZERO : appraisalValue;
        }
    }

    public static class CustomerRecord {
        private int custId;
        private String monthlyIncome;
        private boolean blacklisted;
        private boolean amlAlert;
        private boolean kycOk;
        private String kycStatus;
        private boolean pep;
        private boolean active;
        private String employer;
        private int openDate;
        private String cin;
        private String firstName;
        private String lastName;
        private int dateOfBirth;
        private String nationality;

        public static CustomerRecord fromFixedWidth(String line) {
            // Parse fixed-width line into CustomerRecord fields
            // Placeholder: implement parsing logic according to CUSTCOPY layout
            return new CustomerRecord();
        }

        public int getCustId() {
            return custId;
        }

        public String getMonthlyIncome() {
            return monthlyIncome == null ? "" : monthlyIncome;
        }

        public boolean isBlacklisted() {
            return blacklisted;
        }

        public boolean isAmlAlert() {
            return amlAlert;
        }

        public boolean isKycOk() {
            return kycOk;
        }

        public String getKycStatus() {
            return kycStatus == null ? "" : kycStatus;
        }

        public boolean isPep() {
            return pep;
        }

        public boolean isActive() {
            return active;
        }

        public String getEmployer() {
            return employer == null ? "" : employer;
        }

        public int getOpenDate() {
            return openDate;
        }

        public String getCin() {
            return cin == null ? "" : cin;
        }

        public String getFirstName() {
            return firstName == null ? "" : firstName;
        }

        public String getLastName() {
            return lastName == null ? "" : lastName;
        }

        public int getDateOfBirth() {
            return dateOfBirth;
        }

        public String getNationality() {
            return nationality == null ? "" : nationality;
        }
    }

    public static class GuaranteeRecord {
        private int loanId;
        private boolean active;
        private BigDecimal amount;

        public static GuaranteeRecord fromFixedWidth(String line) {
            // Parse fixed-width line into GuaranteeRecord fields
            // Placeholder: implement parsing logic according to GUARCOPY layout
            return new GuaranteeRecord();
        }

        public int getLoanId() {
            return loanId;
        }

        public boolean isActive() {
            return active;
        }

        public BigDecimal getAmount() {
            return amount == null ? BigDecimal.ZERO : amount;
        }
    }

    public static class LoanRecord {
        private int loanId;
        private int custId;
        private BigDecimal originalAmount;
        private boolean active;
        private boolean restructured;
        private BigDecimal monthlyPayment;
        private int daysPastDue;
        private int missedPayments;
        private BigDecimal outstandingAmount;
        private String loanType;
        private BigDecimal interestRate;

        public static LoanRecord fromFixedWidth(String line) {
            // Parse fixed-width line into LoanRecord fields
            // Placeholder: implement parsing logic according to LOANCOPY layout
            return new LoanRecord();
        }

        public int getLoanId() {
            return loanId;
        }

        public int getCustId() {
            return custId;
        }

        public BigDecimal getOriginalAmount() {
            return originalAmount == null ? BigDecimal.ZERO : originalAmount;
        }

        public boolean isActive() {
            return active;
        }

        public boolean isRestructured() {
            return restructured;
        }

        public BigDecimal getMonthlyPayment() {
            return monthlyPayment == null ? BigDecimal.ZERO : monthlyPayment;
        }

        public int getDaysPastDue() {
            return daysPastDue;
        }

        public int getMissedPayments() {
            return missedPayments;
        }

        public BigDecimal getOutstandingAmount() {
            return outstandingAmount == null ? BigDecimal.ZERO : outstandingAmount;
        }

        public String getLoanType() {
            return loanType == null ? "" : loanType;
        }

        public BigDecimal getInterestRate() {
            return interestRate == null ? BigDecimal.ZERO : interestRate;
        }
    }

    public static class SortComponentRec {
        private String sortComponentName;
        private BigDecimal sortComponentWeight;
        private int sortComponentScore;
        private int sortComponentRank;

        public String getSortComponentName() {
            return sortComponentName;
        }

        public void setSortComponentName(String sortComponentName) {
            this.sortComponentName = sortComponentName;
        }

        public BigDecimal getSortComponentWeight() {
            return sortComponentWeight;
        }

        public void setSortComponentWeight(BigDecimal sortComponentWeight) {
            this.sortComponentWeight = sortComponentWeight;
        }

        public int getSortComponentScore() {
            return sortComponentScore;
        }

        public void setSortComponentScore(int sortComponentScore) {
            this.sortComponentScore = sortComponentScore;
        }

        public int getSortComponentRank() {
            return sortComponentRank;
        }

        public void setSortComponentRank(int sortComponentRank) {
            this.sortComponentRank = sortComponentRank;
        }
    }

}
