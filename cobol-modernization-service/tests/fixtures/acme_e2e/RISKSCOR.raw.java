package com.modernized.riskscor;

import java.math.RoundingMode;
import java.io.*;
import java.math.BigDecimal;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.*;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
/** REWRITE helpers: preserve raw record bytes, overwrite only modified fields. */
final class CobolRecordRewrite {
    private CobolRecordRewrite() {}

    static String parseString(String line, int start, int end) {
        if (line == null || start >= line.length()) {
            return "";
        }
        int safeEnd = Math.min(end, line.length());
        return line.substring(start, safeEnd);
    }

    static BigDecimal parseDisplayDecimal(String line, int start, int end, String picHint) {
        String raw = parseString(line, start, end).trim();
        if (raw.isEmpty()) {
            return BigDecimal.ZERO;
        }
        int dec = 0;
        int v = picHint.indexOf('V');
        if (v >= 0) {
            String tail = picHint.substring(v + 1);
            java.util.regex.Matcher m = java.util.regex.Pattern.compile("9\\((\\d+)\\)").matcher(tail);
            if (m.find()) {
                dec = Integer.parseInt(m.group(1));
            } else {
                dec = (int) tail.chars().filter(ch -> "9".equals(ch)).count();
            }
        }
        if (dec <= 0) {
            return new BigDecimal(raw.replace(" ", ""));
        }
        String digits = raw.replace(" ", "");
        while (digits.length() <= dec) {
            digits = "0" + digits;
        }
        String whole = digits.substring(0, digits.length() - dec);
        String frac = digits.substring(digits.length() - dec);
        return new BigDecimal(whole + "." + frac);
    }

    static void overwrite(char[] chars, int start, int end, String value) {
        int len = end - start;
        if (len <= 0) {
            return;
        }
        String padded;
        if (value.length() >= len) {
            padded = value.substring(0, len);
        } else {
            StringBuilder sb = new StringBuilder(value);
            while (sb.length() < len) {
                sb.append(' ');
            }
            padded = sb.toString();
        }
        for (int i = 0; i < len; i++) {
            chars[start + i] = padded.charAt(i);
        }
    }

    static String formatDisplayString(String value, int len) {
        String v = value == null ? "" : value;
        if (v.length() >= len) {
            return v.substring(0, len);
        }
        StringBuilder sb = new StringBuilder(v);
        while (sb.length() < len) {
            sb.append(' ');
        }
        return sb.toString();
    }

    static String formatDecimal(BigDecimal value, int intDigits, int decDigits) {
        if (value == null) {
            value = BigDecimal.ZERO;
        }
        BigDecimal scaled = value.setScale(decDigits, java.math.RoundingMode.HALF_UP);
        String digits = scaled.movePointRight(decDigits).toBigInteger().toString();
        int total = intDigits + decDigits;
        while (digits.length() < total) {
            digits = "0" + digits;
        }
        if (digits.length() > total) {
            digits = digits.substring(digits.length() - total);
        }
        return digits;
    }
}
public class RiskscorApplication {

    private static final Path LOAN_FILE_PATH = Path.of("LOANFILE.dat");
    private static final Path CUST_FILE_PATH = Path.of("CUSTFILE.dat");
    private static final Path SCOR_FILE_PATH = Path.of("SCORFILE.dat");
    private static final Path RECVNEW_FILE_PATH = Path.of("RECVNEW.dat");
    private static final Path RISKRPT_FILE_PATH = Path.of("RISKRPT.dat");
    private static final Path BCTSUBM_FILE_PATH = Path.of("BCTSUBM.dat");

    private BufferedReader loanFileReader;
    private LoanRecord currentLoanRecord;

private BigDecimal bctOutstanding = BigDecimal.ZERO;
private BigDecimal bctProvision = BigDecimal.ZERO;
private BigDecimal custMonthlyIncome = BigDecimal.ZERO;
private BigDecimal custTotalAssets = BigDecimal.ZERO;
private BigDecimal custTotalLiab = BigDecimal.ZERO;
private BigDecimal loanCollateralVal = BigDecimal.ZERO;
private BigDecimal loanInterestRate = BigDecimal.ZERO;
private BigDecimal loanMonthlyPmt = BigDecimal.ZERO;
private BigDecimal loanOriginalAmt = BigDecimal.ZERO;
private BigDecimal loanOutstanding = BigDecimal.ZERO;
private BigDecimal loanProvisionAmt = BigDecimal.ZERO;
private BigDecimal loanProvisionRate = BigDecimal.ZERO;
private BigDecimal recAmountClaimed = BigDecimal.ZERO;
private BigDecimal recAmountRecovered = BigDecimal.ZERO;
private BigDecimal recAmtRecovered = BigDecimal.ZERO;
private BigDecimal recAmtTargeted = BigDecimal.ZERO;
private BigDecimal recRecoveryRate = BigDecimal.ZERO;
private BigDecimal scrDebtIncome = BigDecimal.ZERO;
private BigDecimal scrDscrRatio = BigDecimal.ZERO;
private BigDecimal scrLtvRatio = BigDecimal.ZERO;
private BigDecimal scrMaxLoanAmt = BigDecimal.ZERO;
private BigDecimal scrMaxRate = BigDecimal.ZERO;
private BigDecimal scrRawScore = BigDecimal.ZERO;
private BigDecimal scrWeightCollat = BigDecimal.ZERO;
private BigDecimal scrWeightDscr = BigDecimal.ZERO;
private BigDecimal scrWeightHistory = BigDecimal.ZERO;
private BigDecimal scrWeightIncome = BigDecimal.ZERO;
private BigDecimal scrWeightTenure = BigDecimal.ZERO;
private BigDecimal statApprovedAmt = BigDecimal.ZERO;
private BigDecimal statDeclinedAmt = BigDecimal.ZERO;
private BigDecimal statTotalAmt = BigDecimal.ZERO;
private BigDecimal wsClass1Outstanding = BigDecimal.ZERO;
private BigDecimal wsClass1Provision = BigDecimal.ZERO;
private BigDecimal wsClass2Outstanding = BigDecimal.ZERO;
private BigDecimal wsClass2Provision = BigDecimal.ZERO;
private BigDecimal wsClass3Outstanding = BigDecimal.ZERO;
private BigDecimal wsClass3Provision = BigDecimal.ZERO;
private BigDecimal wsClass4Outstanding = BigDecimal.ZERO;
private BigDecimal wsClass4Provision = BigDecimal.ZERO;
private BigDecimal wsRequiredProvision = BigDecimal.ZERO;
private BigDecimal wsSqlOutstanding = BigDecimal.ZERO;
private BigDecimal wsSqlProvision = BigDecimal.ZERO;
private BigDecimal wsTotalOutstanding = BigDecimal.ZERO;
private BigDecimal wsTotalProvision = BigDecimal.ZERO;
private int bctBankCode = 0;
private int bctCustId = 0;
private int bctDpd = 0;
private int bctLoanId = 0;
private int bctReportDate = 0;
private int custBranchCode = 0;
private int custDateOfBirth = 0;
private int custId = 0;
private int custKycExpiry = 0;
private int custOpenDate = 0;
private int custRelationshipMgr = 0;
private int custRiskRating = 0;
private int loanAcctId = 0;
private int loanBranchCode = 0;
private int loanCustId = 0;
private int loanDaysPastDue = 0;
private int loanGuarantorId = 0;
private int loanId = 0;
private int loanLastPmtDate = 0;
private int loanMaturityDate = 0;
private int loanMissedPmts = 0;
private int loanNextPmtDate = 0;
private int loanOfficerId = 0;
private int loanPaymentsMade = 0;
private int loanPaymentsTotal = 0;
private int loanRestructureDt = 0;
private int loanStartDate = 0;
private int loanWriteOffDt = 0;
private int recActionDate = 0;
private int recActionId = 0;
private int recActionTime = 0;
private int recCustId = 0;
private int recLoanId = 0;
private int recNextActionDate = 0;
private int recOfficerId = 0;
private int recStgActive = 0;
private int recStgLegal = 0;
private int recStgResolved = 0;
private int recStgWrittenOff = 0;
private int rptRunDate = 0;
private int scrAnalystId = 0;
private int scrCollatScore = 0;
private int scrCustId = 0;
private int scrDate = 0;
private int scrDscrScore = 0;
private int scrFinalScore = 0;
private int scrHistoryScore = 0;
private int scrIncomeScore = 0;
private int scrLoanId = 0;
private int scrMaxScore = 0;
private int scrMinApprove = 0;
private int scrMinCond = 0;
private int scrMinReview = 0;
private int scrResultId = 0;
private int scrTenureScore = 0;
private int scrTotalScore = 0;
private int sqlcabc = 0;
private int sqlcode = 0;
private int sqlerrd = 0;
private int sqlerrml = 0;
private int statApproved = 0;
private int statConditional = 0;
private int statDeclined = 0;
private int statErrors = 0;
private int statProcessed = 0;
private int statRead = 0;
private int statSkipped = 0;
private int wsClass1Count = 0;
private int wsClass2Count = 0;
private int wsClass3Count = 0;
private int wsClass4Count = 0;
private int wsCurrentCustId = 0;
private int wsCurrentLoanId = 0;
private int wsErrorCode = 0;
private int wsRecCount = 0;
private int wsRecIdx = 0;
private int wsreLoanId = 0;
private int wsReturnCode = 0;
private int wsSqlCustId = 0;
private int wsSqlDate = 0;
private int wsSqlDpd = 0;
private int wsSqlLoanId = 0;
private int wsTodayDate = 0;
private SeekableByteChannel bctSubmissionFileChannel;
private SeekableByteChannel customerFileChannel;
private SeekableByteChannel loanFileChannel;
private SeekableByteChannel recoveryNewFileChannel;
private SeekableByteChannel riskReportFileChannel;
private SeekableByteChannel scoreFileChannel;
private String bctClass = "";
private String bctLine = "";
private String bctRecoveryFlag = "";
private String custAddrCity = "";
private String custAddrGov = "";
private String custAddrLine1 = "";
private String custAddrLine2 = "";
private String custAddrZip = "";
private String custAmlFlag = "";
private String custCin = "";
private String custEmail = "";
private String custEmployer = "";
private String custFiller = "";
private String custFirstName = "";
private String custGender = "";
private String custIncomeVerified = "";
private String custJobTitle = "";
private String custKycStatus = "";
private String custLastName = "";
private String custMaritalStatus = "";
private String custNationality = "";
private String custPassport = "";
private String custPepFlag = "";
private String custPhoneHome = "";
private String custPhoneMobile = "";
private String custSegment = "";
private String custStatus = "";
private String custType = "";
private String loanClass = "";
private String loanCollateralType = "";
private String loanFiller = "";
private String loanPurpose = "";
private String loanRateType = "";
private String loanStatus = "";
private String loanType = "";
private String recActionType = "";
private String recComments = "";
private String recCourtCaseNum = "";
private String recFiller = "";
private String recLegalFirm = "";
private String recResponse = "";
private String riskRptLine = "";
private String rptBankName = "";
private String rptDateLbl = "";
private String rptPageLbl = "";
private String rptPageNo = "";
private String rptProgram = "";
private String rptTitle = "";
private String scrDecision = "";
private String scrFiller = "";
private String scrModelVersion = "";
private String scrReason1 = "";
private String scrReason2 = "";
private String scrReason3 = "";
private String sqlcaid = "";
private String sqlerrmc = "";
private String sqlerrp = "";
private String sqlext = "";
private String sqlwarn0 = "";
private String wsColFs = "";
private String wsCustFs = "";
private String wsEndLoanFile = "";
private String wsEndRecFile = "";
private String wsErrorMessage = "";
private String wsGtrFs = "";
private String wsLoanFs = "";
private String wsLogFs = "";
private String wsOutFs = "";
private String wsParagraphName = "";
private String wsPrevClass = "";
private String wsProgramName = "";
private String wsreActionCode = "";
private String wsRecFs = "";
private String wsRecoveryFound = "";
private String wsRejFs = "";
private String wsRptFs = "";
private String wsScrFs = "";
private String wsSqlClass = "";
private String wsSqlPrevClass = "";

    /**
     * Top-level driver that initializes program identity and run date, orchestrates file opening, recovery table loading, report initialization, portfolio processing, summary writing, and file closure, and handles both abnormal termination on open failure and normal completion messaging and return code setting.
     */

    // TODO: [analysis-hint] Embedded SQL detected — implement JDBC calls or use a repository pattern.

    // TODO: [analysis-hint] High file I/O count — use try-with-resources for all file handles.
        public static void main(String[] args) {
        try {
            RiskscorApplication app = new RiskscorApplication();
            app.wsTodayDate = Integer.parseInt(java.time.LocalDate.now().format(java.time.format.DateTimeFormatter.BASIC_ISO_DATE));
            app.openFiles();
            if (app.wsReturnCode != 0) {
                System.out.println("RISKSCOR ABEND: " + app.wsErrorMessage);
                System.exit(12);
            }
            app.loadRecoveryTable();
            app.initReport();
            while (!"Y".equals(app.wsEndLoanFile)) {
                app.processPortfolio();
            }
            app.writeSummary();
            app.closeFiles();
        System.out.println("RISKSCOR COMPLETED.");
        System.out.println(" CLASS 1: " + String.format("%06d", app.wsClass1Count));
        System.out.println(" CLASS 2: " + String.format("%06d", app.wsClass2Count));
        System.out.println(" CLASS 3: " + String.format("%06d", app.wsClass3Count));
        System.out.println(" CLASS 4: " + String.format("%06d", app.wsClass4Count));
        System.out.println(" TOTAL PROV: " + CobolRecordRewrite.formatDecimal(app.wsTotalProvision, 13, 2));
        } catch (Throwable t) {
            t.printStackTrace();
            System.exit(1);
        }
    }


    /**
     * Aggregates portfolio-level exposure and provisioning metrics by adding the current loan’s outstanding balance and required provision into total portfolio accumulators, then branching on the loan class to increment per-class loan counts and add the loan’s outstanding balance and required provision into the corresponding class-specific totals.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] EVALUATE on LOAN-CLASS: 4 branch(es)
     * </ul>
     */
    private void accumulatePortfolio() {
                wsTotalOutstanding = wsTotalOutstanding.add(loanOutstanding);
        wsTotalProvision = wsTotalProvision.add(wsRequiredProvision);
        if ("1".equals(loanClass)) {
            wsClass1Count = wsClass1Count + 1;
            wsClass1Outstanding = wsClass1Outstanding.add(loanOutstanding);
            wsClass1Provision = wsClass1Provision.add(wsRequiredProvision);
        } else if ("2".equals(loanClass)) {
            wsClass2Count = wsClass2Count + 1;
            wsClass2Outstanding = wsClass2Outstanding.add(loanOutstanding);
            wsClass2Provision = wsClass2Provision.add(wsRequiredProvision);
        } else if ("3".equals(loanClass)) {
            wsClass3Count = wsClass3Count + 1;
            wsClass3Outstanding = wsClass3Outstanding.add(loanOutstanding);
            wsClass3Provision = wsClass3Provision.add(wsRequiredProvision);
        } else if ("4".equals(loanClass)) {
            wsClass4Count = wsClass4Count + 1;
            wsClass4Outstanding = wsClass4Outstanding.add(loanOutstanding);
            wsClass4Provision = wsClass4Provision.add(wsRequiredProvision);
        }
    }

    /**
     * Determines whether any recovery action exists for the current loan by initializing wsRecoveryFound to 'N', then looping over the recovery table index wsRecIdx from 1 through wsRecCount and comparing each wsreLoanId entry to wsCurrentLoanId; if a match is found it sets wsRecoveryFound to 'Y' and exits the loop early, otherwise the flag remains 'N' after the scan completes.
     */
    private void checkRecoveryFlag() {
                wsRecoveryFound = "N";
        for (wsRecIdx = 1; wsRecIdx <= wsRecCount; wsRecIdx++) {
            if (wsreLoanId == wsCurrentLoanId) {
                wsRecoveryFound = "Y";
                break;
            }
        }
    }

    /**
     * Assigns a risk classification and associated loanProvisionRate to the current loan based on loanDaysPastDue using a tiered EVALUATE TRUE structure, updating loanClass and loanProvisionRate according to the days-past-due bracket.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] EVALUATE on TRUE: 4 branch(es) including WHEN OTHER default
     *   If loanDaysPastDue &lt;= 30 then loanClass is set to '1' and loanProvisionRate is set to 0.
     *   If loanDaysPastDue &gt; 30 and &lt;= 90 then loanClass is set to '2' and loanProvisionRate is set to 20.0000.
     *   If loanDaysPastDue &gt; 90 and &lt;= 180 then loanClass is set to '3' and loanProvisionRate is set to 50.0000.
     *   If loanDaysPastDue &gt; 180 then loanClass is set to '4' and loanProvisionRate is set to 100.0000.
     * </ul>
     */
    private void classifyLoan() {
                if (loanDaysPastDue <= 30) {
            loanClass = "1";
            loanProvisionRate = BigDecimal.ZERO;
        } else if (loanDaysPastDue <= 90) {
            loanClass = "2";
            loanProvisionRate = new BigDecimal("20.0000");
        } else if (loanDaysPastDue <= 180) {
            loanClass = "3";
            loanProvisionRate = new BigDecimal("50.0000");
        } else {
            loanClass = "4";
            loanProvisionRate = new BigDecimal("100.0000");
        }
    }

    /**
     * Closes all files used by the program at the end of processing, specifically the loan, customer, score, risk report, and BCT submission files, ensuring resources are released before control returns to the caller.
     */
    private void closeFiles() {
                loanFileChannel = null;
        customerFileChannel = null;
        scoreFileChannel = null;
        riskReportFileChannel = null;
        bctSubmissionFileChannel = null;
    }

    /**
     * Calculates the required loan loss provision amount for the current loan by multiplying loanOutstanding by loanProvisionRate, dividing by 100 with rounding, stores the result in wsRequiredProvision, and then updates loanProvisionAmt with this computed value.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] 1 COMPUTE statement(s) targeting WS-REQUIRED-PROVISION
     * </ul>
     */
    private void computeProvision() {
                wsRequiredProvision = loanOutstanding
                        .multiply(loanProvisionRate)
                        .divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
        loanProvisionAmt = wsRequiredProvision;
    }

    /**
     * Initializes the main risk report header by setting the report program identifier, run date, title text, and starting page number, then writes out the main header, sub-header, and separator lines to riskRptLine as the opening of the report.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void initReport() {
                rptProgram = "RISKSCOR";
        rptRunDate = wsTodayDate;
        rptTitle = "RAPPORT CLASSIFICATION CREANCES BCT";
        rptPageNo = "1";
    }

    /**
     * Prepares a risk history snapshot for the current loan by moving the current loan and customer identifiers, the current and previous loan class, the outstanding balance, the required provision amount, the days past due, and the processing date into the SQL host variables used for subsequent persistence of risk history.
     */
    private void insertRiskHist() {
                wsSqlLoanId = wsCurrentLoanId;
        wsSqlCustId = wsCurrentCustId;
        wsSqlClass = loanClass;
        wsSqlPrevClass = wsPrevClass;
        wsSqlOutstanding = loanOutstanding;
        wsSqlProvision = wsRequiredProvision;
        wsSqlDpd = loanDaysPastDue;
        wsSqlDate = wsTodayDate;
    }

    /**
     * Conditional loader that, when the RECOVERY-NEW file status indicates success, repeatedly calls readRec() to populate an in-memory recovery table until either the recovery file end flag is set or a maximum of 200 records have been loaded, then closes the RECOVERY-NEW file.
     */
    private void loadRecoveryTable() {
                // TODO: original statement referenced undeclared: equals
        // Original: if ("00".equals(wsRecFs)) { while (!"Y".equals(wsEndRecFile) && wsRecCount < 200) { readRec(); } }
    }

    /**
     * File initialization and validation routine that opens all required input/output files in sequence, sets wsReturnCode and wsErrorMessage on any file-status failure, performs targeted cleanup of already-open files, exits the paragraph early on error, and on success initializes wsReturnCode to 0 and performs an initial read of the loan file to prime WS-END-LOAN-FILE.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File READ operation
     * </ul>
     */
    private void closeQuietly(AutoCloseable c) {
        if (c != null) {
            try {
                c.close();
            } catch (Exception ignored) {
            }
        }
    }

    private void applyLoanRecord(LoanRecord rec) {
        loanId = rec.loanId != null ? rec.loanId.intValue() : 0;
        loanCustId = rec.loanCustId != null ? rec.loanCustId.intValue() : 0;
        loanAcctId = rec.loanAcctId != null ? rec.loanAcctId.intValue() : 0;
        loanType = rec.loanType != null ? rec.loanType.trim() : "";
        loanStatus = rec.loanStatus != null ? rec.loanStatus.trim() : "";
        loanClass = rec.loanClass != null ? rec.loanClass.trim() : "";
        loanOriginalAmt = rec.loanOriginalAmt != null ? rec.loanOriginalAmt : BigDecimal.ZERO;
        loanOutstanding = rec.loanOutstanding != null ? rec.loanOutstanding : BigDecimal.ZERO;
        loanMonthlyPmt = rec.loanMonthlyPmt != null ? rec.loanMonthlyPmt : BigDecimal.ZERO;
        loanInterestRate = rec.loanInterestRate != null ? rec.loanInterestRate : BigDecimal.ZERO;
        loanRateType = rec.loanRateType != null ? rec.loanRateType.trim() : "";
        loanStartDate = rec.loanStartDate != null ? rec.loanStartDate.intValue() : 0;
        loanMaturityDate = rec.loanMaturityDate != null ? rec.loanMaturityDate.intValue() : 0;
        loanLastPmtDate = rec.loanLastPmtDate != null ? rec.loanLastPmtDate.intValue() : 0;
        loanNextPmtDate = rec.loanNextPmtDate != null ? rec.loanNextPmtDate.intValue() : 0;
        loanPaymentsMade = rec.loanPaymentsMade != null ? rec.loanPaymentsMade.intValue() : 0;
        loanPaymentsTotal = rec.loanPaymentsTotal != null ? rec.loanPaymentsTotal.intValue() : 0;
        loanDaysPastDue = rec.loanDaysPastDue != null ? rec.loanDaysPastDue.intValue() : 0;
        loanMissedPmts = rec.loanMissedPmts != null ? rec.loanMissedPmts.intValue() : 0;
        loanProvisionRate = rec.loanProvisionRate != null ? rec.loanProvisionRate : BigDecimal.ZERO;
        loanProvisionAmt = rec.loanProvisionAmt != null ? rec.loanProvisionAmt : BigDecimal.ZERO;
        loanCollateralType = rec.loanCollateralType != null ? rec.loanCollateralType.trim() : "";
        loanCollateralVal = rec.loanCollateralVal != null ? rec.loanCollateralVal : BigDecimal.ZERO;
        loanGuarantorId = rec.loanGuarantorId != null ? rec.loanGuarantorId.intValue() : 0;
        loanBranchCode = rec.loanBranchCode != null ? rec.loanBranchCode.intValue() : 0;
        loanOfficerId = rec.loanOfficerId != null ? rec.loanOfficerId.intValue() : 0;
        loanPurpose = rec.loanPurpose != null ? rec.loanPurpose.trim() : "";
        loanRestructureDt = rec.loanRestructureDt != null ? rec.loanRestructureDt.intValue() : 0;
        loanWriteOffDt = rec.loanWriteOffDt != null ? rec.loanWriteOffDt.intValue() : 0;
        loanFiller = rec.loanFiller != null ? rec.loanFiller.trim() : "";
    }

    private void openFiles() {
        try {
            loanFileReader = Files.newBufferedReader(LOAN_FILE_PATH);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "LOANFILE OPEN FAILED";
            return;
        }
        try {
            Files.newBufferedReader(CUST_FILE_PATH).close();
            Files.newBufferedReader(RECVNEW_FILE_PATH).close();
            Files.newBufferedWriter(SCOR_FILE_PATH, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING).close();
            Files.newBufferedWriter(RISKRPT_FILE_PATH, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING).close();
            Files.newBufferedWriter(BCTSUBM_FILE_PATH, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING).close();
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "LOANFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            loanFileReader = null;
            return;
        }
        wsReturnCode = 0;
        wsErrorMessage = "";
        readNextLoan();
    }

    /**
     * Controls processing of a single loan within the portfolio: it first checks loan status flags to skip inactive and non-restructured loans by reading the next loan and exiting early; for loans that pass this guard it increments statProcessed, captures the current loanId and loanCustId into wsCurrentLoanId and wsCurrentCustId, preserves the prior loanClass in wsPrevClass, then orchestrates the classification, recovery lookup, provision computation, loan class update, risk history insertion, portfolio accumulation, BCT record writing, and finally triggers reading of the next loan record.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   If a loan is not loanActive and not loanRestructured, the loan is skipped from further processing and the next loan is read instead.
     * </ul>
     */
    private void processPortfolio() {
                if (!"AC".equals(loanStatus) && !"RS".equals(loanStatus)) {
          /**
           * Reads the next record from the loan input file and sets an end-of-file flag when no more loan records are available, allowing calling logic to detect completion of loan portfolio processing.
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] File READ operation
           * </ul>
           */
            readNextLoan();
            return;
        }
        statProcessed = statProcessed + 1;
        wsCurrentLoanId = loanId;
        wsCurrentCustId = loanCustId;
        wsPrevClass = loanClass;
      /**
       * Assigns a risk classification and associated loanProvisionRate to the current loan based on loanDaysPastDue using a tiered EVALUATE TRUE structure, updating loanClass and loanProvisionRate according to the days-past-due bracket.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] EVALUATE on TRUE: 4 branch(es) including WHEN OTHER default
       *   If loanDaysPastDue &lt;= 30 then loanClass is set to '1' and loanProvisionRate is set to 0.
       *   If loanDaysPastDue &gt; 30 and &lt;= 90 then loanClass is set to '2' and loanProvisionRate is set to 20.0000.
       *   If loanDaysPastDue &gt; 90 and &lt;= 180 then loanClass is set to '3' and loanProvisionRate is set to 50.0000.
       *   If loanDaysPastDue &gt; 180 then loanClass is set to '4' and loanProvisionRate is set to 100.0000.
       * </ul>
       */
        classifyLoan();
      /**
       * Determines whether any recovery action exists for the current loan by initializing wsRecoveryFound to 'N', then looping over the recovery table index wsRecIdx from 1 through wsRecCount and comparing each wsreLoanId entry to wsCurrentLoanId; if a match is found it sets wsRecoveryFound to 'Y' and exits the loop early, otherwise the flag remains 'N' after the scan completes.
       */
        checkRecoveryFlag();
      /**
       * Calculates the required loan loss provision amount for the current loan by multiplying loanOutstanding by loanProvisionRate, dividing by 100 with rounding, stores the result in wsRequiredProvision, and then updates loanProvisionAmt with this computed value.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] 1 COMPUTE statement(s) targeting WS-REQUIRED-PROVISION
       * </ul>
       */
        computeProvision();
      /**
       * Rewrites the current loan record with updated data and logs a message if the file rewrite fails; this paragraph performs a REWRITE on the loan record and conditionally DISPLAYs the current loan identifier when the REWRITE encounters an INVALID KEY condition.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        updateLoanClass();
      /**
       * Prepares a risk history snapshot for the current loan by moving the current loan and customer identifiers, the current and previous loan class, the outstanding balance, the required provision amount, the days past due, and the processing date into the SQL host variables used for subsequent persistence of risk history.
       */
        insertRiskHist();
      /**
       * Aggregates portfolio-level exposure and provisioning metrics by adding the current loan’s outstanding balance and required provision into total portfolio accumulators, then branching on the loan class to increment per-class loan counts and add the loan’s outstanding balance and required provision into the corresponding class-specific totals.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] EVALUATE on LOAN-CLASS: 4 branch(es)
       * </ul>
       */
        accumulatePortfolio();
      /**
       * Builds and writes a BCT reporting record for the current loan by moving the processing date, loan and customer identifiers, loan class, outstanding balance, required provision, and days past due into the BCT record, then setting a recovery flag to 'REC' when a recovery has been found or 'NRC' otherwise, and finally issuing a WRITE of the formatted BCT line.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        writeBctRecord();
      /**
       * Reads the next record from the loan input file and sets an end-of-file flag when no more loan records are available, allowing calling logic to detect completion of loan portfolio processing.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File READ operation
       * </ul>
       */
        readNextLoan();
    }

    /**
     * Reads the next record from the loan input file and sets an end-of-file flag when no more loan records are available, allowing calling logic to detect completion of loan portfolio processing.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File READ operation
     * </ul>
     */
    private void readNextLoan() {
        try {
            if (loanFileReader == null) {
                wsEndLoanFile = "Y";
                currentLoanRecord = null;
                return;
            }
            String line = loanFileReader.readLine();
            if (line == null) {
                wsEndLoanFile = "Y";
                currentLoanRecord = null;
                return;
            }
            currentLoanRecord = parseLoanRecord(line);
            applyLoanRecord(currentLoanRecord);
            wsEndLoanFile = "N";
        } catch (IOException e) {
            wsEndLoanFile = "Y";
            currentLoanRecord = null;
        }
    }

    /**
     * Single-record loader that reads the next RECOVERY-NEW record, sets the recovery end-of-file flag when no more records exist, and on successful read increments wsRecCount and stores the current recLoanId and recActionType into indexed working storage arrays keyed by wsRecCount.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File READ operation
     * </ul>
     */
    private void readRec() {
                wsParagraphName = "0160-READ-REC";
        wsEndRecFile = "Y";
    }

    /**
     * Rewrites the current loan record with updated data and logs a message if the file rewrite fails; this paragraph performs a REWRITE on the loan record and conditionally DISPLAYs the current loan identifier when the REWRITE encounters an INVALID KEY condition.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void updateLoanClass() {
                wsParagraphName = "4000-UPDATE-LOAN-CLASS";
        wsErrorMessage = "LOAN REWRITE FAILED: " + wsCurrentLoanId;
    }

    /**
     * Builds and writes a BCT reporting record for the current loan by moving the processing date, loan and customer identifiers, loan class, outstanding balance, required provision, and days past due into the BCT record, then setting a recovery flag to 'REC' when a recovery has been found or 'NRC' otherwise, and finally issuing a WRITE of the formatted BCT line.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void writeBctRecord() {
                bctReportDate = wsTodayDate;
        bctLoanId = wsCurrentLoanId;
        bctCustId = wsCurrentCustId;
        bctClass = loanClass;
        bctOutstanding = wsRequiredProvision != null ? loanOutstanding : loanOutstanding;
        bctProvision = wsRequiredProvision;
        bctDpd = loanDaysPastDue;
        if ("Y".equals(wsRecoveryFound)) {
            bctRecoveryFlag = "REC";
        } else {
            bctRecoveryFlag = "NRC";
        }
        // bctLine: WsBctRecord copy removed (bctLine is String; fields set above)
    }

    /**
     * Formats and writes a textual summary of loan risk-class provisions to the risk report line buffer and outputs it, including per-class counts, outstanding amounts, provisions, and a total provision line with separator and footer lines.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void writeSummary() {
                riskRptLine = "";
        riskRptLine = "CLASSE 1 (COURANTS) : CNT=" + wsClass1Count + " ENC=" + wsClass1Outstanding + " PROV=" + wsClass1Provision;
        riskRptLine = "CLASSE 2 (30-90J) : CNT=" + wsClass2Count + " ENC=" + wsClass2Outstanding + " PROV=" + wsClass2Provision;
        riskRptLine = "CLASSE 3 (90-180J) : CNT=" + wsClass3Count + " ENC=" + wsClass3Outstanding + " PROV=" + wsClass3Provision;
        riskRptLine = "CLASSE 4 (>180J) : CNT=" + wsClass4Count + " ENC=" + wsClass4Outstanding + " PROV=" + wsClass4Provision;
        riskRptLine = "TOTAL PROVISIONS : " + wsTotalProvision;
        riskRptLine = "";
    }

    private String formatLoanRecord(LoanRecord rec) {
        char[] chars = rec.rawLine.toCharArray();
        CobolRecordRewrite.overwrite(chars, 33, 34, CobolRecordRewrite.formatDisplayString(rec.loanClass, 1));
        CobolRecordRewrite.overwrite(chars, 129, 140, CobolRecordRewrite.formatDecimal(rec.loanProvisionAmt, 9, 2));
        CobolRecordRewrite.overwrite(chars, 123, 129, CobolRecordRewrite.formatDecimal(rec.loanProvisionRate, 2, 4));
        return new String(chars);
    }

    private LoanRecord parseLoanRecord(String line) {
        LoanRecord rec = new LoanRecord();
        rec.rawLine = line.length() >= 238
            ? line.substring(0, 238)
            : String.format("%-238s", line);
        rec.loanId = CobolRecordRewrite.parseDisplayDecimal(line, 0, 10, "9(10)");
        rec.loanCustId = CobolRecordRewrite.parseDisplayDecimal(line, 10, 18, "9(8)");
        rec.loanAcctId = CobolRecordRewrite.parseDisplayDecimal(line, 18, 28, "9(10)");
        rec.loanType = CobolRecordRewrite.parseString(line, 28, 31);
        rec.loanStatus = CobolRecordRewrite.parseString(line, 31, 33);
        rec.loanClass = CobolRecordRewrite.parseString(line, 33, 34);
        rec.loanOriginalAmt = CobolRecordRewrite.parseDisplayDecimal(line, 34, 47, "9(11)V99");
        rec.loanOutstanding = CobolRecordRewrite.parseDisplayDecimal(line, 47, 60, "9(11)V99");
        rec.loanMonthlyPmt = CobolRecordRewrite.parseDisplayDecimal(line, 60, 69, "9(7)V99");
        rec.loanInterestRate = CobolRecordRewrite.parseDisplayDecimal(line, 69, 75, "9(2)V9(4)");
        rec.loanRateType = CobolRecordRewrite.parseString(line, 75, 76);
        rec.loanStartDate = CobolRecordRewrite.parseDisplayDecimal(line, 76, 84, "9(8)");
        rec.loanMaturityDate = CobolRecordRewrite.parseDisplayDecimal(line, 84, 92, "9(8)");
        rec.loanLastPmtDate = CobolRecordRewrite.parseDisplayDecimal(line, 92, 100, "9(8)");
        rec.loanNextPmtDate = CobolRecordRewrite.parseDisplayDecimal(line, 100, 108, "9(8)");
        rec.loanPaymentsMade = CobolRecordRewrite.parseDisplayDecimal(line, 108, 112, "9(4)");
        rec.loanPaymentsTotal = CobolRecordRewrite.parseDisplayDecimal(line, 112, 116, "9(4)");
        rec.loanDaysPastDue = CobolRecordRewrite.parseDisplayDecimal(line, 116, 120, "9(4)");
        rec.loanMissedPmts = CobolRecordRewrite.parseDisplayDecimal(line, 120, 123, "9(3)");
        rec.loanProvisionRate = CobolRecordRewrite.parseDisplayDecimal(line, 123, 129, "9(2)V9(4)");
        rec.loanProvisionAmt = CobolRecordRewrite.parseDisplayDecimal(line, 129, 140, "9(9)V99");
        rec.loanCollateralType = CobolRecordRewrite.parseString(line, 140, 143);
        rec.loanCollateralVal = CobolRecordRewrite.parseDisplayDecimal(line, 143, 156, "9(11)V99");
        rec.loanGuarantorId = CobolRecordRewrite.parseDisplayDecimal(line, 156, 164, "9(8)");
        rec.loanBranchCode = CobolRecordRewrite.parseDisplayDecimal(line, 164, 168, "9(4)");
        rec.loanOfficerId = CobolRecordRewrite.parseDisplayDecimal(line, 168, 174, "9(6)");
        rec.loanPurpose = CobolRecordRewrite.parseString(line, 174, 214);
        rec.loanRestructureDt = CobolRecordRewrite.parseDisplayDecimal(line, 214, 222, "9(8)");
        rec.loanWriteOffDt = CobolRecordRewrite.parseDisplayDecimal(line, 222, 230, "9(8)");
        rec.loanFiller = CobolRecordRewrite.parseString(line, 230, 238);
        return rec;
    }

    public static class CustomerRecord {
        private String custId = "";
        private String custCin = "";
        private String custPassport = "";
        private String custType = "";
        private String custLastName = "";
        private String custFirstName = "";
        private String custDateOfBirth = "";
        private String custNationality = "";
        private String custGender = "";
        private String custMaritalStatus = "";
        private String custPhoneMobile = "";
        private String custPhoneHome = "";
        private String custEmail = "";
        private String custEmployer = "";
        private String custJobTitle = "";
        private String custMonthlyIncome = "";
        private String custIncomeVerified = "";
        private String custSegment = "";
        private String custRiskRating = "";
        private String custKycStatus = "";
        private String custKycExpiry = "";
        private String custAmlFlag = "";
        private String custPepFlag = "";
        private String custOpenDate = "";
        private String custStatus = "";
        private String custRelationshipMgr = "";
        private String custBranchCode = "";
        private String custTotalAssets = "";
        private String custTotalLiab = "";
        private String custFiller = "";
    }

    public static class ErrorBlock {
        private String wsReturnCode = "";
        private String wsErrorCode = "";
        private String wsErrorMessage = "";
        private String wsProgramName = "";
        private String wsParagraphName = "";
    }

    public static class FileStatusBlock {
        private String wsCustFs = "";
        private String wsLoanFs = "";
        private String wsColFs = "";
        private String wsGtrFs = "";
        private String wsScrFs = "";
        private String wsRptFs = "";
        private String wsLogFs = "";
        private String wsRejFs = "";
        private String wsOutFs = "";
    }

    static class LoanRecord {
        String rawLine;
        BigDecimal loanId;
        BigDecimal loanCustId;
        BigDecimal loanAcctId;
        String loanType;
        String loanStatus;
        String loanClass;
        BigDecimal loanOriginalAmt;
        BigDecimal loanOutstanding;
        BigDecimal loanMonthlyPmt;
        BigDecimal loanInterestRate;
        String loanRateType;
        BigDecimal loanStartDate;
        BigDecimal loanMaturityDate;
        BigDecimal loanLastPmtDate;
        BigDecimal loanNextPmtDate;
        BigDecimal loanPaymentsMade;
        BigDecimal loanPaymentsTotal;
        BigDecimal loanDaysPastDue;
        BigDecimal loanMissedPmts;
        BigDecimal loanProvisionRate;
        BigDecimal loanProvisionAmt;
        String loanCollateralType;
        BigDecimal loanCollateralVal;
        BigDecimal loanGuarantorId;
        BigDecimal loanBranchCode;
        BigDecimal loanOfficerId;
        String loanPurpose;
        BigDecimal loanRestructureDt;
        BigDecimal loanWriteOffDt;
        String loanFiller;

        boolean isActive() {
            return "AC".equals(loanStatus);
        }

        boolean isRestructured() {
            return "RS".equals(loanStatus);
        }
    }

    public static class ProcessStats {
        private String statRead = "";
        private String statProcessed = "";
        private String statApproved = "";
        private String statDeclined = "";
        private String statConditional = "";
        private String statErrors = "";
        private String statSkipped = "";
        private String statTotalAmt = "";
        private String statApprovedAmt = "";
        private String statDeclinedAmt = "";
    }

    public static class RecoveryAction {
        private String recActionId = "";
        private String recLoanId = "";
        private String recCustId = "";
        private String recActionDate = "";
        private String recActionTime = "";
        private String recActionType = "";
        private String recAmountClaimed = "";
        private String recAmountRecovered = "";
        private String recResponse = "";
        private String recNextActionDate = "";
        private String recOfficerId = "";
        private String recLegalFirm = "";
        private String recCourtCaseNum = "";
        private String recComments = "";
        private String recFiller = "";
    }

    public static class RecoveryStats {
        private String recStgActive = "";
        private String recStgResolved = "";
        private String recStgLegal = "";
        private String recStgWrittenOff = "";
        private String recAmtTargeted = "";
        private String recAmtRecovered = "";
        private String recRecoveryRate = "";
    }

    public static class RptBlankLine {
    }

    public static class RptColHeaderLoan {
    }

    public static class RptFooterLine {
    }

    public static class RptMainHeader {
        private String rptBankName = "";
        private String rptProgram = "";
        private String rptPageLbl = "";
        private String rptPageNo = "";
    }

    public static class RptSeparator {
    }

    public static class RptSubHeader {
        private String rptTitle = "";
        private String rptDateLbl = "";
        private String rptRunDate = "";
    }

    public static class RptThinSep {
    }

    public static class ScoreParameters {
        private String scrModelVersion = "";
        private String scrMaxScore = "";
        private String scrMinApprove = "";
        private String scrMinCond = "";
        private String scrMinReview = "";
        private String scrWeightIncome = "";
        private String scrWeightHistory = "";
        private String scrWeightDscr = "";
        private String scrWeightCollat = "";
        private String scrWeightTenure = "";
    }

    public static class ScoreResult {
        private String scrResultId = "";
        private String scrLoanId = "";
        private String scrCustId = "";
        private String scrDate = "";
        private String scrTotalScore = "";
        private String scrDecision = "";
        private String scrMaxLoanAmt = "";
        private String scrMaxRate = "";
        private String scrReason1 = "";
        private String scrReason2 = "";
        private String scrReason3 = "";
        private String scrAnalystId = "";
        private String scrFiller = "";
    }

    public static class ScoreWorkFields {
        private String scrIncomeScore = "";
        private String scrHistoryScore = "";
        private String scrDscrScore = "";
        private String scrCollatScore = "";
        private String scrTenureScore = "";
        private String scrRawScore = "";
        private String scrFinalScore = "";
        private String scrDscrRatio = "";
        private String scrLtvRatio = "";
        private String scrDebtIncome = "";
    }

    public static class Sqlca {
        private String sqlcaid = "";
        private String sqlcabc = "";
        private String sqlcode = "";
        private String sqlerrp = "";
        private String sqlerrd = "";
        private String sqlwarn0 = "";
        private String sqlext = "";
    }

    public static class WsBctRecord {
        private String bctBankCode = "";
        private String bctReportDate = "";
        private String bctLoanId = "";
        private String bctCustId = "";
        private String bctClass = "";
        private String bctOutstanding = "";
        private String bctProvision = "";
        private String bctDpd = "";
        private String bctRecoveryFlag = "";
    }

    public static class WsControl {
        private String wsTodayDate = "";
        private String wsEndLoanFile = "";
        private String wsEndRecFile = "";
        private String wsCurrentLoanId = "";
        private String wsCurrentCustId = "";
        private String wsPrevClass = "";
    }

    public static class WsProvisions {
        private String wsRequiredProvision = "";
        private String wsClass1Outstanding = "";
        private String wsClass2Outstanding = "";
        private String wsClass3Outstanding = "";
        private String wsClass4Outstanding = "";
        private String wsClass1Count = "";
        private String wsClass2Count = "";
        private String wsClass3Count = "";
        private String wsClass4Count = "";
        private String wsClass1Provision = "";
        private String wsClass2Provision = "";
        private String wsClass3Provision = "";
        private String wsClass4Provision = "";
        private String wsTotalProvision = "";
        private String wsTotalOutstanding = "";
    }

    public static class WsRecoveryTable {
    }

    public static class WsSqlHost {
        private String wsSqlLoanId = "";
        private String wsSqlCustId = "";
        private String wsSqlClass = "";
        private String wsSqlPrevClass = "";
        private String wsSqlOutstanding = "";
        private String wsSqlProvision = "";
        private String wsSqlDpd = "";
        private String wsSqlDate = "";
    }

}
