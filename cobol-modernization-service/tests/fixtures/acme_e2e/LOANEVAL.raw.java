package com.modernized.loaneval;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;


public class LoanevalApplication {

    // File paths (hardcoded as per config)
    private static final Path LOAN_FILE_PATH = Path.of("LOANFILE.dat");
    private static final Path CUSTOMER_FILE_PATH = Path.of("CUSTFILE.dat");
    private static final Path COLLATERAL_FILE_PATH = Path.of("COLFILE.dat");
    private static final Path GUARANTEE_FILE_PATH = Path.of("GUARFILE.dat");
    private static final Path SCORE_FILE_PATH = Path.of("SCORFILE.dat");
    private static final Path DECISION_REPORT_PATH = Path.of("DECIRPT.dat");
    private static final Path REJECT_LOG_PATH = Path.of("EVALREJ.dat");

    // File readers/writers
    private BufferedReader loanFileReader;
    private BufferedReader customerFileReader;
    private BufferedReader collateralFileReader;
    private BufferedReader guaranteeFileReader;
    private BufferedWriter scoreFileWriter;
    private BufferedWriter decisionReportWriter;
    private BufferedWriter rejectLogWriter;

    // Working storage and state variables
    private int wsReturnCode;
    private String wsErrorMessage = "";
    private String wsProgramName = "";
    private int wsTodayDate;
    private int wsTodayTime;
    private String wsEndLoanFile = "N";
    private String wsCollateralFound = "N";
    private String wsGuaranteeFound = "N";
    private int wsCurrentLoanId;
    private int wsCurrentCustId;
    private String wsAmlClear = "N";
    private String wsAmlReason = "";

    private long wsScoreSeq;

    private BigDecimal wsTotalCollatValue = BigDecimal.ZERO;
    private BigDecimal wsTotalGuarValue = BigDecimal.ZERO;
    private BigDecimal wsTotalExistingDebt = BigDecimal.ZERO;
    private BigDecimal wsMonthlyDebtServ = BigDecimal.ZERO;
    private int wsBankTenureYears;
    private BigDecimal wsIncomeToPmt = BigDecimal.ZERO;
    private BigDecimal wsNormalizedIncome = BigDecimal.ZERO;
    private int wsBureauAdjustment;
    private int wsSectorAdjustment;

    private int statRead;
    private int statApproved;
    private int statConditional;
    private int statDeclined;
    private int statErrors;
    private BigDecimal statTotalAmt = BigDecimal.ZERO;
    private BigDecimal statApprovedAmt = BigDecimal.ZERO;
    private BigDecimal statDeclinedAmt = BigDecimal.ZERO;

    private int wsPageNo;
    private int wsLineCount;
    private final int wsMaxLines = 55;

    // Score parameters
    private String scrModelVersion = "2023.1";
    private int scrMaxScore = 1000;
    private int scrMinApprove = 600;
    private int scrMinCond = 450;
    private int scrMinReview = 350;
    private BigDecimal scrWeightIncome = new BigDecimal("25.00");
    private BigDecimal scrWeightHistory = new BigDecimal("30.00");
    private BigDecimal scrWeightDscr = new BigDecimal("20.00");
    private BigDecimal scrWeightCollat = new BigDecimal("15.00");
    private BigDecimal scrWeightTenure = new BigDecimal("10.00");

    // Sector matrix entries (12 entries)
    private static class SectorEntry {
        String code = "";
        String label = "";
        BigDecimal adjustment = BigDecimal.ZERO;
    }
    private final SectorEntry[] wsSectorEntry = new SectorEntry[12];

    // Scoring components table (5 components)
    private static class ComponentEntry {
        String name = "";
        BigDecimal weight = BigDecimal.ZERO;
        int score;
        int rank;
    }
    private final ComponentEntry[] wsCompEntry = new ComponentEntry[5];

    // Current loan record
    private LoanRecord currentLoan;
    // Current customer record
    private CustomerRecord currentCustomer;
    // Collateral and guarantee records buffers for current loan
    private final List<CollateralRecord> collateralRecords = new ArrayList<>();
    private final List<GuarantorRecord> guarantorRecords = new ArrayList<>();

    // Score result record to write
    private final ScoreResult scoreResult = new ScoreResult();

    // Decision line fields (working storage)
    private int decLoanId;
    private int decCustId;
    private String decLoanType = "";
    private String decDecision = "";
    private String decReason = "";
    private String decAmount = "";
    private String decRate = "";
    private String decScore = "";

    // External services
    private final ChkAmlService chkAmlService;
    private final Calcfee calcFeeService;

    public LoanevalApplication() {
        this.chkAmlService = new ChkAmlService();
        this.calcFeeService = new Calcfee();

        // Initialize sector entries array
        for (int i = 0; i < wsSectorEntry.length; i++) {
            wsSectorEntry[i] = new SectorEntry();
        }
        // Initialize component entries array
        for (int i = 0; i < wsCompEntry.length; i++) {
            wsCompEntry[i] = new ComponentEntry();
        }
    }

    public void main() throws IOException {
        wsProgramName = "LOANEVAL";
        wsTodayDate = acceptDate();
        wsTodayTime = acceptTime();

        display("LOANEVAL v6.0 - START " + wsTodayDate + "-" + String.format("%06d", wsTodayTime));

        openFiles();
        if (wsReturnCode != 0) {
            display("LOANEVAL ABEND: " + wsErrorMessage);
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

        display("LOANEVAL COMPLETED.");
        display("  READ        : " + String.format("%08d", statRead));
        display("  APPROVED    : " + String.format("%08d", statApproved));
        display("  CONDITIONAL : " + String.format("%08d", statConditional));
        display("  DECLINED    : " + String.format("%08d", statDeclined));
        display("  ERRORS      : " + String.format("%08d", statErrors));

        System.exit(statErrors > 0 ? 4 : 0);
    }

    private int acceptDate() {
        // Accept current date in YYYYMMDD format as int
        // For simplicity, use java.time.LocalDate
        return Integer.parseInt(java.time.LocalDate.now().toString().replace("-", ""));
    }

    private int acceptTime() {
        // Accept current time in HHMMSS format as int
        return Integer.parseInt(java.time.LocalTime.now().toString().replace(":", "").substring(0, 6));
    }

    private void display(String message) {
        System.out.println(message);
    }

    private void openFiles() throws IOException {
        try {
            loanFileReader = Files.newBufferedReader(LOAN_FILE_PATH);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "LOANFILE OPEN FAILED";
            return;
        }

        try {
            customerFileReader = Files.newBufferedReader(CUSTOMER_FILE_PATH);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "CUSTFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            return;
        }

        try {
            collateralFileReader = Files.newBufferedReader(COLLATERAL_FILE_PATH);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "COLFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            return;
        }

        try {
            guaranteeFileReader = Files.newBufferedReader(GUARANTEE_FILE_PATH);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "GUARFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            closeQuietly(collateralFileReader);
            return;
        }

        try {
            scoreFileWriter = Files.newBufferedWriter(SCORE_FILE_PATH, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "SCORFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            closeQuietly(collateralFileReader);
            closeQuietly(guaranteeFileReader);
            return;
        }

        try {
            decisionReportWriter = Files.newBufferedWriter(DECISION_REPORT_PATH, StandardOpenOption.CREATE, StandardOpenOption.WRITE);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "DECIRPT OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            closeQuietly(collateralFileReader);
            closeQuietly(guaranteeFileReader);
            closeQuietly(scoreFileWriter);
            return;
        }

        try {
            rejectLogWriter = Files.newBufferedWriter(REJECT_LOG_PATH, StandardOpenOption.CREATE, StandardOpenOption.WRITE);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "EVALREJ OPEN FAILED";
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

    private void closeQuietly(AutoCloseable c) {
        if (c != null) {
            try {
                c.close();
            } catch (Exception ignored) {
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
        wsSectorEntry[0].code = "BANK";
        wsSectorEntry[0].label = "SECTEUR BANCAIRE";
        wsSectorEntry[0].adjustment = new BigDecimal("25.00");

        wsSectorEntry[1].code = "ADMI";
        wsSectorEntry[1].label = "ADMINISTRATION PUBLIQUE";
        wsSectorEntry[1].adjustment = new BigDecimal("30.00");

        wsSectorEntry[2].code = "INDS";
        wsSectorEntry[2].label = "INDUSTRIE MANUFACTURIERE";
        wsSectorEntry[2].adjustment = new BigDecimal("15.00");

        wsSectorEntry[3].code = "COMM";
        wsSectorEntry[3].label = "COMMERCE GROS DETAIL";
        wsSectorEntry[3].adjustment = new BigDecimal("5.00");

        wsSectorEntry[4].code = "AGRI";
        wsSectorEntry[4].label = "AGRICULTURE PECHE";
        wsSectorEntry[4].adjustment = new BigDecimal("-10.00");

        wsSectorEntry[5].code = "TOUR";
        wsSectorEntry[5].label = "TOURISME HOTELLERIE";
        wsSectorEntry[5].adjustment = new BigDecimal("-15.00");

        wsSectorEntry[6].code = "CONS";
        wsSectorEntry[6].label = "CONSTRUCTION BTP";
        wsSectorEntry[6].adjustment = new BigDecimal("-5.00");

        wsSectorEntry[7].code = "TRSP";
        wsSectorEntry[7].label = "TRANSPORT LOGISTIQUE";
        wsSectorEntry[7].adjustment = new BigDecimal("10.00");

        wsSectorEntry[8].code = "PROF";
        wsSectorEntry[8].label = "PROFESSIONS LIBERALES";
        wsSectorEntry[8].adjustment = new BigDecimal("20.00");

        wsSectorEntry[9].code = "PHAR";
        wsSectorEntry[9].label = "PHARMACIE SANTE";
        wsSectorEntry[9].adjustment = new BigDecimal("25.00");

        wsSectorEntry[10].code = "TELE";
        wsSectorEntry[10].label = "TELECOMMUNICATIONS";
        wsSectorEntry[10].adjustment = new BigDecimal("20.00");

        wsSectorEntry[11].code = "AUTR";
        wsSectorEntry[11].label = "AUTRES SECTEURS";
        wsSectorEntry[11].adjustment = BigDecimal.ZERO;
    }

    private void initReport() throws IOException {
        // Write report headers to decision report file
        // Using fixed strings from copybook (hardcoded here)
        String mainHeader = "ACME BANK SA     LOANEVAL  PAGE: 1                                                                 ";
        String subHeader = "DATE: " + wsTodayDate + "                                                            ";
        String separator = "=".repeat(137);
        String colHeaderLoan = "  DOSSIER  CLIENT  TYPE  MONTANT  TAUX  SCORE  DECISION                                                        ";

        decisionReportWriter.write(mainHeader);
        decisionReportWriter.newLine();
        decisionReportWriter.write(subHeader);
        decisionReportWriter.newLine();
        decisionReportWriter.write(separator);
        decisionReportWriter.newLine();
        decisionReportWriter.write(colHeaderLoan);
        decisionReportWriter.newLine();
        decisionReportWriter.write(separator);
        decisionReportWriter.newLine();

        wsPageNo = 1;
        wsLineCount = 6; // 5 lines written + 1 for next line count
    }

    private void writeSummary() throws IOException {
        String separator = "=".repeat(137);
        decisionReportWriter.write(separator);
        decisionReportWriter.newLine();

        String totalsLine = String.format("TOTAUX: TRAITES=%d APPROUVES=%d CONDITIONNEL=%d REFUSES=%d",
                statRead, statApproved, statConditional, statDeclined);
        decisionReportWriter.write(totalsLine);
        decisionReportWriter.newLine();

        String amountLine = String.format("MONTANT TOTAL: %s  APPROUVE: %s",
                formatBigDecimal(statTotalAmt), formatBigDecimal(statApprovedAmt));
        decisionReportWriter.write(amountLine);
        decisionReportWriter.newLine();

        String footerLine = " ".repeat(137);
        decisionReportWriter.write(footerLine);
        decisionReportWriter.newLine();
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

    private void processLoans() throws IOException {
        statRead++;
        if (currentLoan == null) {
            wsEndLoanFile = "Y";
            return;
        }
        wsCurrentLoanId = currentLoan.loanId;
        wsCurrentCustId = currentLoan.loanCustId;
        statTotalAmt = statTotalAmt.add(currentLoan.loanOriginalAmt);

        validatePreconditions();
        if (wsReturnCode == 12) {
            statErrors++;
            writeReject();
            readNextLoan();
            return;
        }

        loadCustomer();
        if (!custFsOk) {
            statErrors++;
            wsErrorMessage = "CUSTOMER NOT FOUND: " + wsCurrentCustId;
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
            wsErrorMessage = wsAmlReason;
            writeReject();
            readNextLoan();
            return;
        }

           fetchBureauScore();
           fetchSectorAdjustment();
           loadCollateral();
           sumCollat();
           loadGuarantees();
           sumGuarantees();
           computeScore();
        rankComponents();
        applyDecision();
        callFeeCalculation();
        writeScoreRecord();
        writeDecisionLine();
        readNextLoan();
    }

    private void validatePreconditions() {
        wsReturnCode = 0;
        if (wsCurrentLoanId == 0) {
            wsReturnCode = 12;
            wsErrorMessage = "LOAN-ID IS ZERO - INVALID RECORD";
            return;
        }
        if (currentLoan.loanOriginalAmt.compareTo(BigDecimal.ZERO) == 0) {
            wsReturnCode = 12;
            wsErrorMessage = "LOAN AMOUNT IS ZERO";
            return;
        }
        if (!currentLoan.loanActive && !currentLoan.loanRestructured) {
            wsReturnCode = 12;
            wsErrorMessage = "LOAN STATUS NOT ELIGIBLE FOR EVALUATION";
        }
    }

    private void writeReject() throws IOException {
        StringBuilder sb = new StringBuilder();
        sb.append(String.format("%10d  %8d  ", wsCurrentLoanId, wsCurrentCustId));
        sb.append(padRight(wsErrorMessage, 80));
        sb.append(" ".repeat(18));
        rejectLogWriter.write(sb.toString());
        rejectLogWriter.newLine();
    }

    private void loadCustomer() throws IOException {
        custFsOk = false;
        customerFileReader.close();
        customerFileReader = Files.newBufferedReader(CUSTOMER_FILE_PATH);
        String line;
        while ((line = customerFileReader.readLine()) != null) {
            CustomerRecord cust = CustomerRecord.fromFixedWidth(line);
            if (cust.custId == wsCurrentCustId) {
                currentCustomer = cust;
                custFsOk = true;
                break;
            }
        }
    }

    private void normalizeIncome() {
        // Format as COBOL PIC 9(7)V99 display (9 digits, no decimal point)
        BigDecimal income = currentCustomer.custMonthlyIncome;
        if (income == null) {
            wsNormalizedIncome = BigDecimal.ZERO;
            return;
        }
        long centsTotal = income.abs()
                .movePointRight(2)
                .setScale(0, RoundingMode.DOWN)
                .longValue();
        String incomeRaw = String.format("%09d", centsTotal % 1_000_000_000L);
        // INSPECT replacing spaces and '-' by '0' in income string
        incomeRaw = incomeRaw.replace(' ', '0').replace('-', '0');

        // Parse whole and cents parts from incomeRaw string (length 9)
        // WS-INCOME-WHOLE PIC 9(7), WS-INCOME-CENTS PIC 9(2)
        String wholePartStr = incomeRaw.substring(0, 7);
        String centsPartStr = incomeRaw.substring(7, 9);

        int wholePart = 0;
        int centsPart = 0;
        try {
            wholePart = Integer.parseInt(wholePartStr);
            centsPart = Integer.parseInt(centsPartStr);
        } catch (NumberFormatException e) {
            wholePart = 0;
            centsPart = 0;
        }

        if (wholePart == 0 && centsPart == 0) {
            wsNormalizedIncome = BigDecimal.ZERO;
        } else {
            wsNormalizedIncome = BigDecimal.valueOf(wholePart).add(BigDecimal.valueOf(centsPart).movePointLeft(2));
        }
        wsNormalizedIncome = wsNormalizedIncome.setScale(2, RoundingMode.DOWN);
    }

    private void validateCustomer() {
        wsReturnCode = 0;
        if (currentCustomer.custBlacklisted) {
            wsReturnCode = 8;
            wsErrorMessage = "CLIENT BLACKLISTE - DEMANDE REFUSEE";
            return;
        }
        if (currentCustomer.custAmlAlert) {
            wsReturnCode = 8;
            wsErrorMessage = "ALERTE AML EN COURS";
            return;
        }
        if (!currentCustomer.custKycOk) {
            wsReturnCode = 8;
            wsErrorMessage = "KYC NON VALIDE - STATUT: " + currentCustomer.custKycStatus;
            return;
        }
        if (currentCustomer.custIsPep) {
            scoreResult.scrReason1 = "DOSSIER PEP - VALIDATION MANUELLE";
        }
        if (!currentCustomer.custActive) {
            wsReturnCode = 8;
            wsErrorMessage = "CLIENT INACTIF";
        }
    }

    private void externalAmlCheck() {
        ChkAmlService.AmlRequest amlRequest = new ChkAmlService.AmlRequest(
                currentCustomer.custId,
                currentCustomer.custCin,
                currentCustomer.custFirstName + " " + currentCustomer.custLastName,
                currentCustomer.custDateOfBirth,
                currentCustomer.custNationality,
                currentLoan.loanOriginalAmt);
        ChkAmlService.AmlResponse amlResponse = chkAmlService.checkAml(amlRequest);
        wsAmlClear = amlResponse.getClear();
        wsAmlReason = amlResponse.getReason();
    }

    private void fetchBureauScore() {
        wsBureauAdjustment = 0;
        // Fallback synthetic bureau score from custId hash mod 200 - 100
        wsBureauAdjustment = (wsCurrentCustId % 200) - 100;
    }

    private void fetchSectorAdjustment() {
        wsSectorAdjustment = 0;
        String sectorCode = "AUTR";

        String employer = currentCustomer.custEmployer != null ? currentCustomer.custEmployer : "";
        employer = employer.length() >= 10 ? employer : String.format("%-10s", employer);

        if (employer.startsWith("BANQUE")) {
            sectorCode = "BANK";
        } else if (employer.startsWith("MINISTERE ")) {
            sectorCode = "ADMI";
        } else if (employer.startsWith("TUNISIE ")) {
            sectorCode = "TELE";
        } else if (employer.startsWith("ORANGE") || employer.startsWith("OOREDOO")) {
            sectorCode = "TELE";
        } else if (employer.startsWith("PHARMACI")) {
            sectorCode = "PHAR";
        } else if (employer.startsWith("HOTEL  ") || employer.startsWith("TUNISA")) {
            sectorCode = "TOUR";
        } else if (employer.startsWith("GROUPE ")) {
            sectorCode = "INDS";
        } else if (employer.startsWith("COMMERCE")) {
            sectorCode = "COMM";
        } else if (employer.startsWith("ARTISAN")) {
            sectorCode = "COMM";
        }

        for (SectorEntry entry : wsSectorEntry) {
            if (entry.code.equals(sectorCode)) {
                wsSectorAdjustment = entry.adjustment.intValue();
                break;
            }
        }
    }

    private void loadCollateral() throws IOException {
        wsTotalCollatValue = BigDecimal.ZERO;
        wsCollateralFound = "N";
        collateralRecords.clear();

        // For simplicity, scan collateral file for matching loanId
        collateralFileReader.close();
        collateralFileReader = Files.newBufferedReader(COLLATERAL_FILE_PATH);
        String line;
        while ((line = collateralFileReader.readLine()) != null) {
            CollateralRecord col = CollateralRecord.fromFixedWidth(line);
            if (col.colLoanId == wsCurrentLoanId) {
                wsCollateralFound = "Y";
                collateralRecords.add(col);
            }
        }
    }

    private void sumCollat() {
        for (CollateralRecord col : collateralRecords) {
            if (col.colActive) {
                wsTotalCollatValue = wsTotalCollatValue.add(col.colAppraisalValue);
            }
        }
    }

    private void loadGuarantees() throws IOException {
        wsTotalGuarValue = BigDecimal.ZERO;
        wsGuaranteeFound = "N";
        guarantorRecords.clear();

        guaranteeFileReader.close();
        guaranteeFileReader = Files.newBufferedReader(GUARANTEE_FILE_PATH);
        String line;
        while ((line = guaranteeFileReader.readLine()) != null) {
            GuarantorRecord gtr = GuarantorRecord.fromFixedWidth(line);
            if (gtr.gtrLoanId == wsCurrentLoanId) {
                wsGuaranteeFound = "Y";
                guarantorRecords.add(gtr);
            }
        }
    }

    private void sumGuarantees() {
        for (GuarantorRecord gtr : guarantorRecords) {
            if (gtr.gtrActive) {
                wsTotalGuarValue = wsTotalGuarValue.add(gtr.gtrAmount);
            }
        }
    }

    private void computeScore() {
        scoreResult.scrIncomeScore = 0;
        scoreResult.scrHistoryScore = 0;
        scoreResult.scrDscrScore = 0;
        scoreResult.scrCollatScore = 0;
        scoreResult.scrTenureScore = 0;
        scoreResult.scrReason1 = "";
        scoreResult.scrReason2 = "";
        scoreResult.scrReason3 = "";

        scoreIncome();
        scoreHistory();
        scoreDscr();
        scoreCollateral();
        scoreTenure();

        BigDecimal incomeComponent = BigDecimal.valueOf(scoreResult.scrIncomeScore).multiply(scrWeightIncome);
        BigDecimal historyComponent = BigDecimal.valueOf(scoreResult.scrHistoryScore).multiply(scrWeightHistory);
        BigDecimal dscrComponent = BigDecimal.valueOf(scoreResult.scrDscrScore).multiply(scrWeightDscr);
        BigDecimal collatComponent = BigDecimal.valueOf(scoreResult.scrCollatScore).multiply(scrWeightCollat);
        BigDecimal tenureComponent = BigDecimal.valueOf(scoreResult.scrTenureScore).multiply(scrWeightTenure);

        BigDecimal rawScore = incomeComponent.add(historyComponent).add(dscrComponent).add(collatComponent).add(tenureComponent)
                .divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);

        scoreResult.scrRawScore = rawScore;

        int finalScore = rawScore.setScale(0, RoundingMode.DOWN).intValue() + wsBureauAdjustment + wsSectorAdjustment;

        if (finalScore > scrMaxScore) {
            finalScore = scrMaxScore;
        }
        if (finalScore < 0) {
            finalScore = 0;
        }
        scoreResult.scrFinalScore = finalScore;
    }

    private void scoreIncome() {
        if (wsNormalizedIncome.compareTo(BigDecimal.ZERO) == 0 || currentLoan.loanMonthlyPmt.compareTo(BigDecimal.ZERO) == 0) {
            scoreResult.scrIncomeScore = 0;
            scoreResult.scrReason2 = "REVENU OU MENSUALITE NULS";
            return;
        }
        wsIncomeToPmt = wsNormalizedIncome.divide(currentLoan.loanMonthlyPmt, 4, RoundingMode.HALF_UP);

        BigDecimal three = new BigDecimal("3.0");
        BigDecimal twoPointFive = new BigDecimal("2.5");
        BigDecimal two = new BigDecimal("2.0");
        BigDecimal onePointFive = new BigDecimal("1.5");
        BigDecimal onePointTwo = new BigDecimal("1.2");

        if (wsIncomeToPmt.compareTo(three) >= 0) {
            scoreResult.scrIncomeScore = 1000;
        } else if (wsIncomeToPmt.compareTo(twoPointFive) >= 0) {
            scoreResult.scrIncomeScore = 850;
        } else if (wsIncomeToPmt.compareTo(two) >= 0) {
            scoreResult.scrIncomeScore = 700;
        } else if (wsIncomeToPmt.compareTo(onePointFive) >= 0) {
            scoreResult.scrIncomeScore = 500;
        } else if (wsIncomeToPmt.compareTo(onePointTwo) >= 0) {
            scoreResult.scrIncomeScore = 300;
        } else {
            scoreResult.scrIncomeScore = 0;
            scoreResult.scrReason2 = "RATIO REVENU/MENSUALITE INSUFFISANT";
        }
    }

    private void scoreHistory() {
        int daysPastDue = currentLoan.loanDaysPastDue;
        int missedPmts = currentLoan.loanMissedPmts;

        if (daysPastDue == 0 && missedPmts == 0) {
            scoreResult.scrHistoryScore = 1000;
        } else if (daysPastDue <= 30) {
            scoreResult.scrHistoryScore = 700;
        } else if (daysPastDue <= 90) {
            scoreResult.scrHistoryScore = 400;
            scoreResult.scrReason1 = "RETARDS DE PAIEMENT DETECTES";
        } else if (daysPastDue <= 180) {
            scoreResult.scrHistoryScore = 150;
            scoreResult.scrReason1 = "CREANCE CLASSEE - SUIVI REQUIS";
        } else {
            scoreResult.scrHistoryScore = 0;
            scoreResult.scrReason1 = "CREANCE EN SOUFFRANCE > 180 JOURS";
        }
    }

    private void scoreDscr() {
        wsMonthlyDebtServ = currentLoan.loanMonthlyPmt.add(wsTotalExistingDebt);
        if (wsMonthlyDebtServ.compareTo(BigDecimal.ZERO) == 0) {
            scoreResult.scrDscrScore = 1000;
            return;
        }
        wsIncomeToPmt = wsNormalizedIncome.divide(wsMonthlyDebtServ, 4, RoundingMode.HALF_UP);

        BigDecimal onePointFive = new BigDecimal("1.5");
        BigDecimal onePointTwo = new BigDecimal("1.2");
        BigDecimal one = new BigDecimal("1.0");
        BigDecimal zeroPointEight = new BigDecimal("0.8");

        if (wsIncomeToPmt.compareTo(onePointFive) >= 0) {
            scoreResult.scrDscrScore = 1000;
        } else if (wsIncomeToPmt.compareTo(onePointTwo) >= 0) {
            scoreResult.scrDscrScore = 750;
        } else if (wsIncomeToPmt.compareTo(one) >= 0) {
            scoreResult.scrDscrScore = 500;
        } else if (wsIncomeToPmt.compareTo(zeroPointEight) >= 0) {
            scoreResult.scrDscrScore = 250;
            scoreResult.scrReason3 = "TAUX DE COUVERTURE FAIBLE";
        } else {
            scoreResult.scrDscrScore = 0;
            scoreResult.scrReason3 = "CAPACITE REMBOURSEMENT INSUFFISANTE";
        }
    }

    private void scoreCollateral() {
        wsTotalCollatValue = wsTotalCollatValue.add(wsTotalGuarValue);
        if (wsTotalCollatValue.compareTo(BigDecimal.ZERO) == 0) {
            scoreResult.scrCollatScore = 0;
            return;
        }
        BigDecimal ltvRatio = currentLoan.loanOutstanding.multiply(BigDecimal.valueOf(100))
                .divide(wsTotalCollatValue, 4, RoundingMode.HALF_UP);
        scoreResult.scrLtvRatio = ltvRatio;

        if (ltvRatio.compareTo(new BigDecimal("60")) <= 0) {
            scoreResult.scrCollatScore = 1000;
        } else if (ltvRatio.compareTo(new BigDecimal("70")) <= 0) {
            scoreResult.scrCollatScore = 800;
        } else if (ltvRatio.compareTo(new BigDecimal("80")) <= 0) {
            scoreResult.scrCollatScore = 600;
        } else if (ltvRatio.compareTo(new BigDecimal("90")) <= 0) {
            scoreResult.scrCollatScore = 400;
        } else if (ltvRatio.compareTo(new BigDecimal("100")) <= 0) {
            scoreResult.scrCollatScore = 200;
        } else {
            scoreResult.scrCollatScore = 0;
        }
    }

    private void scoreTenure() {
        wsBankTenureYears = (wsTodayDate - currentCustomer.custOpenDate) / 10000;
        if (wsBankTenureYears >= 10) {
            scoreResult.scrTenureScore = 1000;
        } else if (wsBankTenureYears >= 7) {
            scoreResult.scrTenureScore = 800;
        } else if (wsBankTenureYears >= 5) {
            scoreResult.scrTenureScore = 600;
        } else if (wsBankTenureYears >= 3) {
            scoreResult.scrTenureScore = 400;
        } else if (wsBankTenureYears >= 1) {
            scoreResult.scrTenureScore = 200;
        } else {
            scoreResult.scrTenureScore = 0;
        }
    }

    private void rankComponents() {
        // Load components into wsCompEntry array
        wsCompEntry[0].name = "INCOME  ";
        wsCompEntry[0].weight = scrWeightIncome;
        wsCompEntry[0].score = scoreResult.scrIncomeScore;
        wsCompEntry[0].rank = 0;

        wsCompEntry[1].name = "HISTORY ";
        wsCompEntry[1].weight = scrWeightHistory;
        wsCompEntry[1].score = scoreResult.scrHistoryScore;
        wsCompEntry[1].rank = 0;

        wsCompEntry[2].name = "DSCR    ";
        wsCompEntry[2].weight = scrWeightDscr;
        wsCompEntry[2].score = scoreResult.scrDscrScore;
        wsCompEntry[2].rank = 0;

        wsCompEntry[3].name = "COLLAT  ";
        wsCompEntry[3].weight = scrWeightCollat;
        wsCompEntry[3].score = scoreResult.scrCollatScore;
        wsCompEntry[3].rank = 0;

        wsCompEntry[4].name = "TENURE  ";
        wsCompEntry[4].weight = scrWeightTenure;
        wsCompEntry[4].score = scoreResult.scrTenureScore;
        wsCompEntry[4].rank = 0;

        // Sort descending by score
        List<ComponentEntry> compList = new ArrayList<>(List.of(wsCompEntry));
        compList.sort(Comparator.comparingInt((ComponentEntry c) -> c.score).reversed());

        // Assign ranks and reorder wsCompEntry by rank
        for (int i = 0; i < compList.size(); i++) {
            ComponentEntry c = compList.get(i);
            c.rank = i + 1;
        }

        // Reorder wsCompEntry by rank ascending
        compList.sort(Comparator.comparingInt(c -> c.rank));
        for (int i = 0; i < compList.size(); i++) {
            wsCompEntry[i] = compList.get(i);
        }
    }

    private void applyDecision() {
        int finalScore = scoreResult.scrFinalScore;
        if (finalScore >= scrMinApprove) {
            scoreResult.scrDecision = "AP";
            statApproved++;
            computeMaxLoan();
            computePricing();
            statApprovedAmt = statApprovedAmt.add(currentLoan.loanOriginalAmt);
        } else if (finalScore >= scrMinCond) {
            scoreResult.scrDecision = "CO";
            statConditional++;
            computeMaxLoan();
            computePricing();
        } else if (finalScore >= scrMinReview) {
            scoreResult.scrDecision = "RV";
            statConditional++;
        } else {
            scoreResult.scrDecision = "DC";
            statDeclined++;
            statDeclinedAmt = statDeclinedAmt.add(currentLoan.loanOriginalAmt);
            scoreResult.scrMaxLoanAmt = BigDecimal.ZERO;
        }
    }

    private void computeMaxLoan() {
        BigDecimal maxLoanAmt = wsNormalizedIncome.multiply(BigDecimal.valueOf(12)).multiply(new BigDecimal("0.40"));
        if (wsTotalCollatValue.compareTo(BigDecimal.ZERO) > 0) {
            BigDecimal collatAdj = wsTotalCollatValue.multiply(new BigDecimal("0.80"));
            if (collatAdj.compareTo(maxLoanAmt) < 0) {
                maxLoanAmt = collatAdj;
            }
        }
        if (currentLoan.loanOriginalAmt.compareTo(maxLoanAmt) < 0) {
            maxLoanAmt = currentLoan.loanOriginalAmt;
        }
        scoreResult.scrMaxLoanAmt = maxLoanAmt.setScale(2, RoundingMode.DOWN);
    }

    private void computePricing() {
        BigDecimal baseRate = new BigDecimal("7.25");
        BigDecimal addOn;
        int finalScore = scoreResult.scrFinalScore;

        if (finalScore >= 850) {
            addOn = new BigDecimal("1.50");
        } else if (finalScore >= 700) {
            addOn = new BigDecimal("2.50");
        } else if (finalScore >= 600) {
            addOn = new BigDecimal("3.50");
        } else {
            addOn = new BigDecimal("4.50");
        }
        scoreResult.scrMaxRate = baseRate.add(addOn).setScale(4, RoundingMode.DOWN);
    }

    private void callFeeCalculation() {
        Calcfee.LkFeeRequest feeRequest = new Calcfee.LkFeeRequest();
        feeRequest.lkReqLoanType = currentLoan.loanType;
        feeRequest.lkReqAmount = currentLoan.loanOriginalAmt;
        feeRequest.lkReqRate = scoreResult.scrMaxRate;
        Calcfee.LkFeeResponse feeResponse = new Calcfee.LkFeeResponse();
        calcFeeService.execute(feeRequest, feeResponse);
    }

    private void writeScoreRecord() throws IOException {
        wsScoreSeq++;
        scoreResult.scrResultId = (int) wsScoreSeq;
        scoreResult.scrLoanId = wsCurrentLoanId;
        scoreResult.scrCustId = wsCurrentCustId;
        scoreResult.scrDate = wsTodayDate;
        scoreResult.scrTotalScore = scoreResult.scrFinalScore;

        // Write fixed-width record to score file
        String record = scoreResult.toFixedWidth();
        scoreFileWriter.write(record);
        scoreFileWriter.newLine();
        scoreFileWriter.flush();
    }

    private void writeDecisionLine() throws IOException {
        if (wsLineCount >= wsMaxLines) {
            wsPageNo++;
            wsLineCount = 2; // reset after header lines
            initReport();
        }

        decLoanId = wsCurrentLoanId;
        decCustId = wsCurrentCustId;
        decLoanType = currentLoan.loanType;
        decAmount = formatBigDecimal(currentLoan.loanOriginalAmt);
        decRate = formatBigDecimal(scoreResult.scrMaxRate);
        decScore = String.format("%4d", scoreResult.scrFinalScore).trim();

        switch (scoreResult.scrDecision) {
            case "AP" -> decDecision = "APPROUVE   ";
            case "CO" -> decDecision = "CONDITIONNEL";
            case "RV" -> decDecision = "A ETUDIER  ";
            case "DC" -> decDecision = "REFUSE     ";
            default -> decDecision = "           ";
        }
        decReason = scoreResult.scrReason1 != null ? scoreResult.scrReason1 : "";

        StringBuilder sb = new StringBuilder();
        sb.append(String.format("%10d  %8d  %-3s  %11s  %6s  %6s  %-11s  %-50s",
                decLoanId, decCustId, decLoanType, decAmount, decRate, decScore, decDecision, decReason));

        decisionReportWriter.write(sb.toString());
        decisionReportWriter.newLine();
        wsLineCount++;
    }

    private void readNextLoan() throws IOException {
        String line = loanFileReader.readLine();
        if (line == null) {
            wsEndLoanFile = "Y";
            currentLoan = null;
        } else {
            currentLoan = LoanRecord.fromFixedWidth(line);
            wsEndLoanFile = "N";
        }
    }

    private String padRight(String s, int n) {
        if (s == null) s = "";
        if (s.length() >= n) return s.substring(0, n);
        return String.format("%-" + n + "s", s);
    }

    private String formatBigDecimal(BigDecimal bd) {
        if (bd == null) return "";
        // Format with comma thousands separator and dot decimal point, no locale
        String plain = bd.setScale(2, RoundingMode.DOWN).toPlainString();
        // Insert commas manually
        int dotIndex = plain.indexOf('.');
        String intPart = dotIndex >= 0 ? plain.substring(0, dotIndex) : plain;
        String decPart = dotIndex >= 0 ? plain.substring(dotIndex) : "";
        StringBuilder sb = new StringBuilder();
        int len = intPart.length();
        int count = 0;
        for (int i = len - 1; i >= 0; i--) {
            sb.insert(0, intPart.charAt(i));
            count++;
            if (count == 3 && i > 0) {
                sb.insert(0, ',');
                count = 0;
            }
        }
        sb.append(decPart);
        return sb.toString();
    }

    // File status flags for customer file read
    private boolean custFsOk = false;

    // Data record classes and parsing from fixed-width lines

    public static class LoanRecord {
        int loanId;
        int loanCustId;
        int loanAcctId;
        String loanType;
        boolean loanConsumer;
        boolean loanMortgage;
        boolean loanAuto;
        boolean loanBusiness;
        boolean loanRevolving;
        boolean loanOverdraft;
        String loanStatus;
        boolean loanActive;
        boolean loanRestructured;
        boolean loanLitigious;
        boolean loanSettled;
        boolean loanWrittenOff;
        String loanClass;
        boolean loanClass1;
        boolean loanClass2;
        boolean loanClass3;
        boolean loanClass4;
        BigDecimal loanOriginalAmt;
        BigDecimal loanOutstanding;
        BigDecimal loanMonthlyPmt;
        BigDecimal loanInterestRate;
        String loanRateType;
        boolean loanFixedRate;
        boolean loanVariable;
        int loanStartDate;
        int loanMaturityDate;
        int loanLastPmtDate;
        int loanNextPmtDate;
        int loanPaymentsMade;
        int loanPaymentsTotal;
        int loanDaysPastDue;
        int loanMissedPmts;
        BigDecimal loanProvisionRate;
        BigDecimal loanProvisionAmt;
        String loanCollateralType;
        boolean loanColProperty;
        boolean loanColVehicle;
        boolean loanColDeposit;
        boolean loanColNone;
        BigDecimal loanCollateralVal;
        int loanGuarantorId;
        int loanBranchCode;
        int loanOfficerId;
        String loanPurpose;
        int loanRestructureDt;
        int loanWriteOffDt;
        String loanFiller;

        public static LoanRecord fromFixedWidth(String line) {
            LoanRecord r = new LoanRecord();
            // Field positions from LOANCOPY.cpy (0-based):
            // LOAN-ID: 0-9 (10), LOAN-CUST-ID: 10-17 (8), LOAN-ACCT-ID: 18-27 (10),
            // LOAN-TYPE: 28-30 (3), LOAN-STATUS: 31-32 (2), LOAN-CLASS: 33 (1),
            // LOAN-ORIGINAL-AMT: 34-46 (13, 9(11)V99), LOAN-OUTSTANDING: 47-59 (13, 9(11)V99),
            // LOAN-MONTHLY-PMT: 60-68 (9, 9(7)V99), LOAN-INTEREST-RATE: 69-74 (6, 9(2)V9(4)),
            // LOAN-RATE-TYPE: 75 (1), LOAN-START-DATE: 76-83 (8), LOAN-MATURITY-DATE: 84-91 (8),
            // LOAN-LAST-PMT-DATE: 92-99 (8), LOAN-NEXT-PMT-DATE: 100-107 (8),
            // LOAN-PAYMENTS-MADE: 108-111 (4), LOAN-PAYMENTS-TOTAL: 112-115 (4),
            // LOAN-DAYS-PAST-DUE: 116-119 (4), LOAN-MISSED-PMTS: 120-122 (3),
            // LOAN-PROVISION-RATE: 123-128 (6), LOAN-PROVISION-AMT: 129-139 (11),
            // LOAN-COLLATERAL-TYPE: 140-142 (3), LOAN-COLLATERAL-VAL: 143-155 (13),
            // LOAN-GUARANTOR-ID: 156-163 (8), LOAN-BRANCH-CODE: 164-167 (4),
            // LOAN-OFFICER-ID: 168-173 (6), LOAN-PURPOSE: 174-213 (40),
            // LOAN-RESTRUCTURE-DT: 214-221 (8), LOAN-WRITE-OFF-DT: 222-229 (8)

            try {
                r.loanId = Integer.parseInt(line.substring(0, 10).trim());
            } catch (Exception e) {
                r.loanId = 0;
            }
            try {
                r.loanCustId = Integer.parseInt(line.substring(10, 18).trim());
            } catch (Exception e) {
                r.loanCustId = 0;
            }
            r.loanType = line.substring(28, 31).trim();
            r.loanStatus = line.substring(31, 33).trim();
            r.loanActive = "AC".equals(r.loanStatus);
            r.loanRestructured = "RS".equals(r.loanStatus);

            try {
                r.loanOriginalAmt = parseBigDecimal(line.substring(34, 47), 2);
            } catch (Exception e) {
                r.loanOriginalAmt = BigDecimal.ZERO;
            }
            try {
                r.loanOutstanding = parseBigDecimal(line.substring(47, 60), 2);
            } catch (Exception e) {
                r.loanOutstanding = BigDecimal.ZERO;
            }
            try {
                r.loanMonthlyPmt = parseBigDecimal(line.substring(60, 69), 2);
            } catch (Exception e) {
                r.loanMonthlyPmt = BigDecimal.ZERO;
            }
            try {
                r.loanInterestRate = parseBigDecimal(line.substring(69, 75), 4);
            } catch (Exception e) {
                r.loanInterestRate = BigDecimal.ZERO;
            }
            try {
                r.loanDaysPastDue = Integer.parseInt(line.substring(116, 120).trim());
            } catch (Exception e) {
                r.loanDaysPastDue = 0;
            }
            try {
                r.loanMissedPmts = Integer.parseInt(line.substring(120, 123).trim());
            } catch (Exception e) {
                r.loanMissedPmts = 0;
            }
            r.loanPurpose = safeSubstring(line, 174, 214).trim();

            return r;
        }

        private static String safeSubstring(String s, int start, int end) {
            if (s.length() < end) return s.length() > start ? s.substring(start) : "";
            return s.substring(start, end);
        }
    }

    public static class CustomerRecord {
        int custId;
        String custCin;
        String custPassport;
        String custType;
        boolean custIndividual;
        boolean custCorporate;
        boolean custNonResident;
        String custLastName;
        String custFirstName;
        int custDateOfBirth;
        String custNationality;
        String custGender;
        boolean custMale;
        boolean custFemale;
        String custMaritalStatus;
        boolean custSingle;
        boolean custMarried;
        boolean custDivorced;
        boolean custWidowed;
        String custAddrLine1;
        String custAddrLine2;
        String custAddrCity;
        String custAddrZip;
        String custAddrGov;
        String custPhoneMobile;
        String custPhoneHome;
        String custEmail;
        String custEmployer;
        String custJobTitle;
        BigDecimal custMonthlyIncome;
        String custIncomeVerified;
        boolean custIncomeOk;
        String custSegment;
        boolean custMassMarket;
        boolean custMiddle;
        boolean custPremium;
        boolean custPrivate;
        int custRiskRating;
        String custKycStatus;
        boolean custKycOk;
        boolean custKycPending;
        boolean custKycExpired;
        int custKycExpiry;
        String custAmlFlag;
        boolean custAmlAlert;
        String custPepFlag;
        boolean custIsPep;
        int custOpenDate;
        String custStatus;
        boolean custActive;
        boolean custInactive;
        boolean custBlacklisted;
        int custRelationshipMgr;
        int custBranchCode;
        BigDecimal custTotalAssets;
        BigDecimal custTotalLiab;
        String custFiller;

        public boolean custBlacklisted() {
            return custBlacklisted;
        }

        public boolean custAmlAlert() {
            return custAmlAlert;
        }

        public boolean custKycOk() {
            return custKycOk;
        }

        public boolean custIsPep() {
            return custIsPep;
        }

        public boolean custActive() {
            return custActive;
        }

        public static CustomerRecord fromFixedWidth(String line) {
            CustomerRecord c = new CustomerRecord();
            if (line.length() < 384) {
                return c;
            }
            try {
                c.custId = Integer.parseInt(line.substring(0, 8).trim());
            } catch (Exception e) {
                c.custId = 0;
            }
            c.custCin = line.substring(8, 16).trim();
            c.custLastName = line.substring(30, 60).trim();
            c.custFirstName = line.substring(60, 85).trim();
            try {
                c.custDateOfBirth = Integer.parseInt(line.substring(85, 93).trim());
            } catch (Exception e) {
                c.custDateOfBirth = 0;
            }
            c.custNationality = line.substring(93, 96).trim();
            c.custEmployer = line.substring(280, 320).trim();
            try {
                c.custMonthlyIncome = parseBigDecimal(line.substring(350, 359), 2);
            } catch (Exception e) {
                c.custMonthlyIncome = BigDecimal.ZERO;
            }
            c.custKycStatus = line.substring(364, 365);
            c.custKycOk = "V".equals(c.custKycStatus);
            c.custBlacklisted = "B".equals(line.substring(383, 384));
            c.custAmlAlert = "Y".equals(line.substring(373, 374));
            c.custIsPep = "Y".equals(line.substring(374, 375));
            c.custActive = "A".equals(line.substring(383, 384));
            c.custOpenDate = 0;
            try {
                c.custOpenDate = Integer.parseInt(line.substring(375, 383).trim());
            } catch (Exception ignored) {
            }
            return c;
        }
    }

    public static class CollateralRecord {
        int colId;
        int colLoanId;
        int colCustId;
        String colType;
        boolean colRealEstate;
        boolean colVehicle;
        boolean colFinancial;
        boolean colGuarantee;
        String colDescription;
        String colLocation;
        BigDecimal colAppraisalValue;
        int colAppraisalDate;
        String colAppraisalFirm;
        BigDecimal colCoverageRatio;
        String colInsuranceNum;
        int colInsuranceExpiry;
        String colRegistration;
        String colStatus;
        boolean colActive;
        boolean colReleased;
        boolean colSeized;
        String colFiller;

        public boolean colActive() {
            return colActive;
        }

        public static CollateralRecord fromFixedWidth(String line) {
            CollateralRecord c = new CollateralRecord();
            if (line.length() < 236) {
                return c;
            }
            try {
                c.colLoanId = Integer.parseInt(line.substring(10, 20).trim());
            } catch (Exception e) {
                c.colLoanId = 0;
            }
            try {
                c.colAppraisalValue = parseBigDecimal(line.substring(131, 144), 2);
            } catch (Exception e) {
                c.colAppraisalValue = BigDecimal.ZERO;
            }
            c.colStatus = line.substring(235, 236);
            c.colActive = "A".equals(c.colStatus);
            return c;
        }
    }

    public static class GuarantorRecord {
        int gtrId;
        int gtrLoanId;
        int gtrGuarantorId;
        String gtrName;
        BigDecimal gtrAmount;
        BigDecimal gtrIncome;
        int gtrSignDate;
        int gtrExpiryDate;
        String gtrStatus;
        boolean gtrActive;
        boolean gtrCalled;
        boolean gtrExpired;
        String gtrFiller;

        public boolean gtrActive() {
            return gtrActive;
        }

        public static GuarantorRecord fromFixedWidth(String line) {
            GuarantorRecord g = new GuarantorRecord();
            if (line.length() < 117) {
                return g;
            }
            try {
                g.gtrLoanId = Integer.parseInt(line.substring(10, 20).trim());
            } catch (Exception e) {
                g.gtrLoanId = 0;
            }
            try {
                g.gtrAmount = parseBigDecimal(line.substring(78, 91), 2);
            } catch (Exception e) {
                g.gtrAmount = BigDecimal.ZERO;
            }
            g.gtrStatus = line.substring(116, 117);
            g.gtrActive = "A".equals(g.gtrStatus);
            return g;
        }
    }

    public static class ScoreResult {
        int scrResultId;
        int scrLoanId;
        int scrCustId;
        int scrDate;
        int scrTotalScore;
        String scrDecision = "";
        int scrIncomeScore;
        int scrHistoryScore;
        int scrDscrScore;
        int scrCollatScore;
        int scrTenureScore;
        BigDecimal scrRawScore = BigDecimal.ZERO;
        int scrFinalScore;
        BigDecimal scrMaxLoanAmt = BigDecimal.ZERO;
        BigDecimal scrMaxRate = BigDecimal.ZERO;
        BigDecimal scrLtvRatio = BigDecimal.ZERO;
        String scrReason1 = "";
        String scrReason2 = "";
        String scrReason3 = "";
        int scrAnalystId;
        String scrFiller = "";

        String toFixedWidth() {
            StringBuilder sb = new StringBuilder(229);
            sb.append(String.format("%012d", scrResultId));
            sb.append(String.format("%010d", scrLoanId));
            sb.append(String.format("%08d", scrCustId));
            sb.append(String.format("%08d", scrDate));
            sb.append(String.format("%04d", scrFinalScore));
            sb.append(pad(scrDecision, 2));
            sb.append(String.format("%013.2f", scrMaxLoanAmt));
            sb.append(String.format("%06.4f", scrMaxRate));
            sb.append(pad(scrReason1, 50));
            sb.append(pad(scrReason2, 50));
            sb.append(pad(scrReason3, 50));
            sb.append(String.format("%06d", scrAnalystId));
            sb.append(pad(scrFiller, 10));
            while (sb.length() < 229) {
                sb.append(' ');
            }
            return sb.toString();
        }

        private static String pad(String s, int n) {
            if (s == null) s = "";
            if (s.length() >= n) return s.substring(0, n);
            StringBuilder sb = new StringBuilder(s);
            while (sb.length() < n) sb.append(' ');
            return sb.toString();
        }
    }

    private static BigDecimal parseBigDecimal(String s, int scale) {
        s = s.trim();
        if (s.isEmpty()) return BigDecimal.ZERO;
        BigDecimal bd = new BigDecimal(s);
        return bd.movePointLeft(scale).setScale(scale, RoundingMode.DOWN);
    }
    public static void main(String[] args) throws Exception {
        new LoanevalApplication().main();
    }

    private void closFiles() {
        // TODO: COBOL paragraph closFiles — requires implementation
    }

    private void loadSort() {
        // TODO: COBOL paragraph loadSort — requires implementation
    }

    private void rankOutput() {
        // TODO: COBOL paragraph rankOutput — requires implementation
    }
}
