package com.modernized.rptmonth;

import java.io.*;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.*;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
public class RptmonthApplication {

    private static final Path LOAN_FILE_PATH = Path.of("LOANFILE.dat");
    private static final Path CUST_FILE_PATH = Path.of("CUSTFILE.dat");
    private static final Path SCOR_FILE_PATH = Path.of("SCORFILE.dat");
    private static final Path MONTHRPT_FILE_PATH = Path.of("MONTHRPT.dat");

    private BufferedReader loanFileReader;

    public static class LoanRecord {
        private String loanId = "";
        private String loanCustId = "";
        private String loanAcctId = "";
        private String loanType = "";
        private String loanStatus = "";
        private String loanClass = "";
        private String loanOriginalAmt = "";
        private String loanOutstanding = "";
        private String loanMonthlyPmt = "";
        private String loanInterestRate = "";
        private String loanRateType = "";
        private String loanStartDate = "";
        private String loanMaturityDate = "";
        private String loanLastPmtDate = "";
        private String loanNextPmtDate = "";
        private String loanPaymentsMade = "";
        private String loanPaymentsTotal = "";
        private String loanDaysPastDue = "";
        private String loanMissedPmts = "";
        private String loanProvisionRate = "";
        private String loanProvisionAmt = "";
        private String loanCollateralType = "";
        private String loanCollateralVal = "";
        private String loanGuarantorId = "";
        private String loanBranchCode = "";
        private String loanOfficerId = "";
        private String loanPurpose = "";
        private String loanRestructureDt = "";
        private String loanWriteOffDt = "";
        private String loanFiller = "";
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

    public static class RptMainHeader {
        private String rptBankName = "";
        private String rptProgram = "";
        private String rptPageLbl = "";
        private String rptPageNo = "";
    }

    public static class RptSubHeader {
        private String rptTitle = "";
        private String rptDateLbl = "";
        private String rptRunDate = "";
    }

    public static class RptColHeaderLoan {
    }

    public static class RptSeparator {
    }

    public static class RptThinSep {
    }

    public static class RptBlankLine {
    }

    public static class RptFooterLine {
    }

    public static class WsControl {
        private String wsTodayDate = "";
        private String wsEndLoanFile = "";
        private String wsCurrentLoanId = "";
        private String wsCurrentCustId = "";
    }

    public static class WsPortfolio {
        private String wsTotalLoans = "";
        private String wsTotalOutstanding = "";
        private String wsTotalProvision = "";
        private String wsAvgOutstanding = "";
        private String wsAvgRateNum = "";
        private String wsAvgRate = "";
    }

    public static class WsByClass {
    }

    public static class WsBySegment {
    }

    public static class WsByType {
    }

    public static class WsTopExposures {
    }

    public static class WsPage {
        private String wsPageNo = "";
        private String wsLineCount = "";
        private String wsMaxLines = "";
    }

    public static class WsDisp {
        private String wsDispCount = "";
        private String wsDispAmount = "";
        private String wsDispPct = "";
        private String wsDispRate = "";
        private String wsDispIdx = "";
    }

    private int loanId = 0;
    private int loanCustId = 0;
    private int loanAcctId = 0;
    private String loanType = "";
    private String loanStatus = "";
    private String loanClass = "";
    private BigDecimal loanOriginalAmt = BigDecimal.ZERO;
    private BigDecimal loanOutstanding = BigDecimal.ZERO;
    private BigDecimal loanMonthlyPmt = BigDecimal.ZERO;
    private BigDecimal loanInterestRate = BigDecimal.ZERO;
    private String loanRateType = "";
    private int loanStartDate = 0;
    private int loanMaturityDate = 0;
    private int loanLastPmtDate = 0;
    private int loanNextPmtDate = 0;
    private int loanPaymentsMade = 0;
    private int loanPaymentsTotal = 0;
    private int loanDaysPastDue = 0;
    private int loanMissedPmts = 0;
    private BigDecimal loanProvisionRate = BigDecimal.ZERO;
    private BigDecimal loanProvisionAmt = BigDecimal.ZERO;
    private String loanCollateralType = "";
    private BigDecimal loanCollateralVal = BigDecimal.ZERO;
    private int loanGuarantorId = 0;
    private int loanBranchCode = 0;
    private int loanOfficerId = 0;
    private String loanPurpose = "";
    private int loanRestructureDt = 0;
    private int loanWriteOffDt = 0;
    private String loanFiller = "";
    private int custId = 0;
    private String custCin = "";
    private String custPassport = "";
    private String custType = "";
    private String custLastName = "";
    private String custFirstName = "";
    private int custDateOfBirth = 0;
    private String custNationality = "";
    private String custGender = "";
    private String custMaritalStatus = "";
    private String custAddrLine1 = "";
    private String custAddrLine2 = "";
    private String custAddrCity = "";
    private String custAddrZip = "";
    private String custAddrGov = "";
    private String custPhoneMobile = "";
    private String custPhoneHome = "";
    private String custEmail = "";
    private String custEmployer = "";
    private String custJobTitle = "";
    private BigDecimal custMonthlyIncome = BigDecimal.ZERO;
    private String custIncomeVerified = "";
    private String custSegment = "";
    private int custRiskRating = 0;
    private String custKycStatus = "";
    private int custKycExpiry = 0;
    private String custAmlFlag = "";
    private String custPepFlag = "";
    private int custOpenDate = 0;
    private String custStatus = "";
    private int custRelationshipMgr = 0;
    private int custBranchCode = 0;
    private BigDecimal custTotalAssets = BigDecimal.ZERO;
    private BigDecimal custTotalLiab = BigDecimal.ZERO;
    private String custFiller = "";
    private String scrModelVersion = "";
    private int scrMaxScore = 0;
    private int scrMinApprove = 0;
    private int scrMinCond = 0;
    private int scrMinReview = 0;
    private BigDecimal scrWeightIncome = BigDecimal.ZERO;
    private BigDecimal scrWeightHistory = BigDecimal.ZERO;
    private BigDecimal scrWeightDscr = BigDecimal.ZERO;
    private BigDecimal scrWeightCollat = BigDecimal.ZERO;
    private BigDecimal scrWeightTenure = BigDecimal.ZERO;
    private int scrIncomeScore = 0;
    private int scrHistoryScore = 0;
    private int scrDscrScore = 0;
    private int scrCollatScore = 0;
    private int scrTenureScore = 0;
    private BigDecimal scrRawScore = BigDecimal.ZERO;
    private int scrFinalScore = 0;
    private BigDecimal scrDscrRatio = BigDecimal.ZERO;
    private BigDecimal scrLtvRatio = BigDecimal.ZERO;
    private BigDecimal scrDebtIncome = BigDecimal.ZERO;
    private int scrResultId = 0;
    private int scrLoanId = 0;
    private int scrCustId = 0;
    private int scrDate = 0;
    private int scrTotalScore = 0;
    private String scrDecision = "";
    private BigDecimal scrMaxLoanAmt = BigDecimal.ZERO;
    private BigDecimal scrMaxRate = BigDecimal.ZERO;
    private String scrReason1 = "";
    private String scrReason2 = "";
    private String scrReason3 = "";
    private int scrAnalystId = 0;
    private String scrFiller = "";
    private String monthLine = "";
    private int wsReturnCode = 0;
    private int wsErrorCode = 0;
    private String wsErrorMessage = "";
    private String wsProgramName = "";
    private String wsParagraphName = "";
    private String wsCustFs = "";
    private String wsLoanFs = "";
    private String wsColFs = "";
    private String wsGtrFs = "";
    private String wsScrFs = "";
    private String wsRptFs = "";
    private String wsLogFs = "";
    private String wsRejFs = "";
    private String wsOutFs = "";
    private int statRead = 0;
    private int statProcessed = 0;
    private int statApproved = 0;
    private int statDeclined = 0;
    private int statConditional = 0;
    private int statErrors = 0;
    private int statSkipped = 0;
    private BigDecimal statTotalAmt = BigDecimal.ZERO;
    private BigDecimal statApprovedAmt = BigDecimal.ZERO;
    private BigDecimal statDeclinedAmt = BigDecimal.ZERO;
    private String rptBankName = "";
    private String rptProgram = "";
    private String rptPageLbl = "";
    private String rptPageNo = "";
    private String rptTitle = "";
    private String rptDateLbl = "";
    private int rptRunDate = 0;
    private int wsTodayDate = 0;
    private String wsEndLoanFile = "";
    private int wsCurrentLoanId = 0;
    private int wsCurrentCustId = 0;
    private int wsTotalLoans = 0;
    private BigDecimal wsTotalOutstanding = BigDecimal.ZERO;
    private BigDecimal wsTotalProvision = BigDecimal.ZERO;
    private BigDecimal wsAvgOutstanding = BigDecimal.ZERO;
    private BigDecimal wsAvgRateNum = BigDecimal.ZERO;
    private BigDecimal wsAvgRate = BigDecimal.ZERO;
    private int wsclCount = 0;
    private BigDecimal wsclOutstanding = BigDecimal.ZERO;
    private BigDecimal wsclProvision = BigDecimal.ZERO;
    private String wsseCode = "";
    private int wsseCount = 0;
    private BigDecimal wsseOutstanding = BigDecimal.ZERO;
    private int wsseApproved = 0;
    private int wsseDeclined = 0;
    private String wstyCode = "";
    private String wstyLabel = "";
    private int wstyCount = 0;
    private BigDecimal wstyAmount = BigDecimal.ZERO;
    private int wstopLoanId = 0;
    private int wstopCustId = 0;
    private String wstopCustName = "";
    private BigDecimal wstopOutstanding = BigDecimal.ZERO;
    private String wstopClass = "";
    private String wstopType = "";
    private int wsInsertIdx = 0;
    private int wsShiftIdx = 0;
    private int wsPageNo = 0;
    private int wsLineCount = 0;
    private int wsMaxLines = 0;
    private String wsDispCount = "";
    private String wsDispAmount = "";
    private String wsDispPct = "";
    private String wsDispRate = "";
    private int wsDispIdx = 0;
    private SeekableByteChannel loanFileChannel;
    private SeekableByteChannel customerFileChannel;
    private SeekableByteChannel scoreFileChannel;
    private SeekableByteChannel monthReportFileChannel;

    // TODO: [analysis-hint] Internal SORT detected — use java.util.List + Comparator for sort operations.

    // TODO: [analysis-hint] High file I/O count — use try-with-resources for all file handles.

    public void run() {
                wsTodayDate = Integer.parseInt(java.time.LocalDate.now().format(java.time.format.DateTimeFormatter.BASIC_ISO_DATE));
        System.out.println("RPTMONTH V2.3 START " + String.format("%08d", wsTodayDate));
                wsProgramName = "RPTMONTH";
      /**
       * Performs file setup and initial read: opens the loan input file and, if loanFsOk is false, sets wsReturnCode to 12, builds an error message including wsLoanFs, and exits the paragraph; if successful, opens the customer input file and on failure sets wsReturnCode to 12, builds an error message including wsCustFs, closes the loan file, and exits; then opens the score input file and on failure sets wsReturnCode to 12, builds an error message including wsScrFs, closes the loan and customer files, and exits; then opens the month report output file and on failure sets wsReturnCode to 12, sets a fixed error message, closes all previously opened files, and exits; if all opens succeed, it sets wsReturnCode to 0, reads the first record from the loan file, and on end-of-file sets wsEndLoanFile to 'Y'.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File READ operation
       * </ul>
       */
        openFiles();
        if (wsReturnCode != 0) {
            System.out.println("RPTMONTH ABEND: " + wsErrorMessage);
            wsReturnCode = 12;
            return;
        }
      /**
       * Initializes in-memory classification tables by populating wsseCode entries 1–4 with segment codes ('MM','MB','PR','PB') and wstyCode/wstyLabel entries 1–6 with loan type codes and their labels (e.g., 'CON'/'CONSOMMATION', 'IMM'/'IMMOBILIER', 'AUT'/'AUTOMOBILE', 'PRO'/'PROFESSIONNEL', 'REV'/'REVOLVING', 'DEC'/'DECOUVERT') for later use in aggregation or reporting logic.
       */
        initTables();
      /**
       * Formats and writes the report cover/header lines, initializing report identity, run date, title, first page number, and initial line count for the monthly credit report.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        writeCover();
      /**
       * Skips non-active and non-restructured loans, then for eligible loans updates portfolio-level aggregates (loan count, total outstanding, total provision, and weighted-rate numerator), tracks the current loan and customer identifiers, and orchestrates further aggregation and lookup paragraphs before reading the next loan record.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] 1 COMPUTE statement(s) targeting WS-AVG-RATE-NUM
       *   A loan is excluded from portfolio aggregation when it is not loanActive and not loanRestructured; such loans trigger an immediate readNext() and exit from this paragraph without updating any portfolio totals.
       * </ul>
       */
        aggregatePortfolio();
        while (!"Y".equals(wsEndLoanFile)) {
          /**
           * Skips non-active and non-restructured loans, then for eligible loans updates portfolio-level aggregates (loan count, total outstanding, total provision, and weighted-rate numerator), tracks the current loan and customer identifiers, and orchestrates further aggregation and lookup paragraphs before reading the next loan record.
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] 1 COMPUTE statement(s) targeting WS-AVG-RATE-NUM
           *   A loan is excluded from portfolio aggregation when it is not loanActive and not loanRestructured; such loans trigger an immediate readNext() and exit from this paragraph without updating any portfolio totals.
           * </ul>
           */
            aggregatePortfolio();
        }
      /**
       * Generates the report’s Section 1 for portfolio by class: writes a section header and separator, then for each of four classes outputs the class index, wsclCount, and wsclOutstanding; afterwards prints the total outstanding amount and, when non-zero, computes and prints the overall provision percentage and weighted average rate using wsTotalProvision, wsTotalOutstanding, and wsAvgRateNum, updating wsLineCount as lines are written and calling checkPage() before blocks of output.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] Conditional: WS-TOTAL-OUTSTANDING &gt; 0
       *   [pattern] 2 COMPUTE statement(s) targeting WS-DISP-PCT, WS-AVG-RATE
       *   [pattern] File WRITE operation
       *   Section 1 always reports four class buckets, iterating CL-IDX from 1 to 4, regardless of whether individual class counts or amounts are zero.
       *   The total outstanding line always displays wsTotalOutstanding as the portfolio encours value.
       *   Provision and rate metrics are only computed and printed when wsTotalOutstanding is greater than 0, preventing division by zero in the provision percentage and average rate calculations.
       *   The provision percentage is calculated as (wsTotalProvision / wsTotalOutstanding) * 100 and displayed as a percentage value.
       *   The weighted average rate is calculated as wsAvgRateNum / wsTotalOutstanding and displayed as a percentage value.
       *   Pagination control via checkPage() is invoked before the section header, before the per-class loop output, and before the totals block to avoid overrunning the page based on wsLineCount.
       * </ul>
       */
        writeSection1();
      /**
       * Generates the report’s Section 2 for top 10 exposures: writes a section header and separator, then loops through TOP-IDX 1 to 10 and, for each non-zero wstopLoanId, calls checkPage(), formats the rank, loan ID, customer name, class, type, and outstanding amount into monthLine, writes it, and increments wsLineCount.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       *   Section 2 always iterates through 10 ranking slots (TOP-IDX 1 to 10), but only prints entries where wstopLoanId(topIdx) is not zero, effectively skipping unused positions.
       *   Each printed top exposure line includes the rank number, loan identifier, customer name, loan class, loan type, and outstanding amount as stored in the wstop* arrays.
       *   Pagination control via checkPage() is invoked before printing each individual top exposure line that passes the non-zero wstopLoanId condition to manage page breaks based on wsLineCount.
       * </ul>
       */
        writeSection2();
      /**
       * Formats and writes the report's Section 3 header and a per-segment client distribution, looping over four client segments, copying each segment's count and outstanding amount into display fields, composing a descriptive line with segment code, count, and exposure, writing it to the report, and updating the current page line counter while invoking checkPage() before the section and each detail line.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        writeSection3();
      /**
       * Formats and writes the report's Section 4 header and a per-loan-type distribution, looping over six loan types, copying each type's count and amount into display fields, composing a descriptive line with type code, label, count, and amount, writing it to the report, and updating the current page line counter while invoking checkPage() before the section and each detail line.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        writeSection4();
      /**
       * Formats and writes the report's Section 5 header for risk indicators, then, only when total outstanding exposure is greater than zero, computes three rounded percentage ratios based on outstanding and provision totals (non-performing loans across classes 2–4, loss-class 4 only, and provision coverage), writes labeled lines for each ratio to the report, increments the line counter accordingly, and uses checkPage() to manage pagination before the section.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] Conditional: WS-TOTAL-OUTSTANDING &gt; 0
       *   [pattern] 3 COMPUTE statement(s) targeting WS-DISP-PCT
       *   [pattern] File WRITE operation
       *   Risk ratio calculations and their output are performed only if wsTotalOutstanding is greater than 0, preventing division-by-zero when computing percentages.
       * </ul>
       */
        writeSection5();
      /**
       * Writes the final report footer by outputting a blank spacer line, a separator line, and a static end-of-report message indicating the report was generated by program RPTMONTH v2.3, followed by a footer line.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        writeFooter();
      /**
       * Closes all active files used by the program at end of processing, specifically the loan, customer, score, and monthly report files, ensuring resources are released before control returns to the caller.
       */
        closeFiles();
        System.out.println("RPTMONTH COMPLETED. LOANS=" + String.format("%08d", wsTotalLoans)
                + " AMT=" + String.format("%017d", wsTotalOutstanding.longValue()));
        wsReturnCode = 0;
        return;
    }

    /**
     * Performs file setup and initial read: opens the loan input file and, if loanFsOk is false, sets wsReturnCode to 12, builds an error message including wsLoanFs, and exits the paragraph; if successful, opens the customer input file and on failure sets wsReturnCode to 12, builds an error message including wsCustFs, closes the loan file, and exits; then opens the score input file and on failure sets wsReturnCode to 12, builds an error message including wsScrFs, closes the loan and customer files, and exits; then opens the month report output file and on failure sets wsReturnCode to 12, sets a fixed error message, closes all previously opened files, and exits; if all opens succeed, it sets wsReturnCode to 0, reads the first record from the loan file, and on end-of-file sets wsEndLoanFile to 'Y'.
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

    private BigDecimal parseDisplayDecimal(String line, int start, int end, int decDigits) {
        if (line == null || start >= line.length()) {
            return BigDecimal.ZERO;
        }
        int safeEnd = Math.min(end, line.length());
        String raw = line.substring(start, safeEnd).trim();
        if (raw.isEmpty()) {
            return BigDecimal.ZERO;
        }
        String digits = raw.replace(" ", "");
        while (digits.length() <= decDigits) {
            digits = "0" + digits;
        }
        if (decDigits <= 0) {
            return new BigDecimal(digits);
        }
        String whole = digits.substring(0, digits.length() - decDigits);
        String frac = digits.substring(digits.length() - decDigits);
        return new BigDecimal(whole + "." + frac);
    }

    private void applyLoanLine(String line) {
        if (line == null || line.length() < 120) {
            return;
        }
        try {
            loanId = Integer.parseInt(line.substring(0, 10).trim());
        } catch (Exception e) {
            loanId = 0;
        }
        try {
            loanCustId = Integer.parseInt(line.substring(10, 18).trim());
        } catch (Exception e) {
            loanCustId = 0;
        }
        loanType = line.substring(28, 31).trim();
        loanStatus = line.substring(31, 33).trim();
        loanClass = line.length() > 33 ? line.substring(33, 34).trim() : "";
        loanOriginalAmt = parseDisplayDecimal(line, 34, 47, 2);
        loanOutstanding = parseDisplayDecimal(line, 47, 60, 2);
        loanMonthlyPmt = parseDisplayDecimal(line, 60, 69, 2);
        loanInterestRate = parseDisplayDecimal(line, 69, 75, 4);
        loanProvisionRate = parseDisplayDecimal(line, 123, 129, 4);
        loanProvisionAmt = parseDisplayDecimal(line, 129, 140, 2);
        try {
            loanDaysPastDue = Integer.parseInt(line.substring(116, 120).trim());
        } catch (Exception e) {
            loanDaysPastDue = 0;
        }
        try {
            loanRestructureDt = line.length() >= 222
                ? Integer.parseInt(line.substring(214, 222).trim())
                : 0;
        } catch (Exception e) {
            loanRestructureDt = 0;
        }
    }

    private void openFiles() {
        try {
            loanFileReader = Files.newBufferedReader(LOAN_FILE_PATH);
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "LOANFILE OPEN FAILED FS=" + wsLoanFs;
            return;
        }
        try {
            Files.newBufferedReader(CUST_FILE_PATH).close();
            Files.newBufferedReader(SCOR_FILE_PATH).close();
            Files.newBufferedWriter(MONTHRPT_FILE_PATH, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING).close();
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "LOANFILE OPEN FAILED FS=" + wsLoanFs;
            closeQuietly(loanFileReader);
            loanFileReader = null;
            return;
        }
        wsReturnCode = 0;
        wsErrorMessage = "";
        readNext();
    }

    /**
     * Initializes in-memory classification tables by populating wsseCode entries 1–4 with segment codes ('MM','MB','PR','PB') and wstyCode/wstyLabel entries 1–6 with loan type codes and their labels (e.g., 'CON'/'CONSOMMATION', 'IMM'/'IMMOBILIER', 'AUT'/'AUTOMOBILE', 'PRO'/'PROFESSIONNEL', 'REV'/'REVOLVING', 'DEC'/'DECOUVERT') for later use in aggregation or reporting logic.
     */
    private void initTables() {
                wstyCode = "CON";
        wstyLabel = "CONSOMMATION";
    }

    /**
     * Formats and writes the report cover/header lines, initializing report identity, run date, title, first page number, and initial line count for the monthly credit report.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void writeCover() {
                rptProgram = "RPTMONTH";
        rptRunDate = wsTodayDate;
        rptTitle = "RAPPORT MENSUEL CREDIT - DIRECTION GENERALE";
        rptPageNo = "1";
        monthLine = "";
        monthLine = "";
        monthLine = "";
        monthLine = "";
        monthLine = " ACME BANK TUNISIE - DIRECTION DU CREDIT";
        monthLine = " PERIODE: " + String.valueOf(wsTodayDate);
        monthLine = " CONFIDENTIEL - USAGE INTERNE";
        monthLine = "";
        wsLineCount = 5;
    }

    /**
     * Closes all active files used by the program at end of processing, specifically the loan, customer, score, and monthly report files, ensuring resources are released before control returns to the caller.
     */
    private void closeFiles() {
                loanFileChannel = null;
        customerFileChannel = null;
        scoreFileChannel = null;
        monthReportFileChannel = null;
    }

    /**
     * Skips non-active and non-restructured loans, then for eligible loans updates portfolio-level aggregates (loan count, total outstanding, total provision, and weighted-rate numerator), tracks the current loan and customer identifiers, and orchestrates further aggregation and lookup paragraphs before reading the next loan record.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] 1 COMPUTE statement(s) targeting WS-AVG-RATE-NUM
     *   A loan is excluded from portfolio aggregation when it is not loanActive and not loanRestructured; such loans trigger an immediate readNext() and exit from this paragraph without updating any portfolio totals.
     * </ul>
     */
    private void aggregatePortfolio() {
                if (!"AC".equals(loanStatus) && !"RS".equals(loanStatus)) {
          /**
           * Sequentially reads the next record from the loan input stream and flags when no more loan records are available, without performing any additional processing on successful reads.
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] File READ operation
           * </ul>
           */
            readNext();
            return;
        }
        wsTotalLoans = wsTotalLoans + 1;
        wsTotalOutstanding = wsTotalOutstanding.add(loanOutstanding);
        wsTotalProvision = wsTotalProvision.add(loanProvisionAmt);
        wsAvgRateNum = wsAvgRateNum.add(loanInterestRate.multiply(loanOutstanding));
        wsCurrentLoanId = loanId;
        wsCurrentCustId = loanCustId;
      /**
       * Maps the loanClass code to a class index and increments class-level counters and monetary totals for outstanding balance and provision amount for the selected class bucket.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] EVALUATE on LOAN-CLASS: 5 branch(es) including WHEN OTHER default
       *   Loan class codes '1', '2', '3', and '4' are mapped directly to class indices 1 through 4 respectively; any other loanClass value is treated as class index 1 for aggregation purposes.
       * </ul>
       */
        aggregateByClass();
      /**
       * Iterates through predefined loan type buckets and, when a bucket code matches the current loanType, increments that bucket’s loan count and total outstanding amount, then exits the loop.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   Loan type aggregation only occurs for the first index where wstyCode at tyIdx equals loanType; once matched, the loop terminates and no further type buckets are updated.
       * </ul>
       */
        aggregateByType();
      /**
       * Looks up a customer record for the current customer id and clears key customer identity fields when the lookup fails, leaving any successful read data unchanged.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File READ operation
       * </ul>
       */
        lookupCustomer();
      /**
       * Loops over up to four customer segments and, for the first segment whose wsseCode matches custSegment, increments that segment’s loan counter, adds loanOutstanding into that segment’s outstanding total, and increments either the approved or declined counter based on the LOAN-ACTIVE status condition, then exits the loop early.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   For each loan, only the first matching customer segment (where wsseCode(segIdx) = custSegment) is updated; once matched, no further segments are considered for that loan.
       *   Loans contribute their loanOutstanding amount to the outstanding total of exactly one segment bucket, determined by the custSegment code.
       *   Loan status condition LOAN-ACTIVE controls classification: active loans increment wsseApproved for the matched segment, while non-active loans increment wsseDeclined for that segment.
       * </ul>
       */
        aggregateBySegment();
      /**
       * Maintains a descending top-10 list of exposures by loanOutstanding: if the current loanOutstanding exceeds the 10th-ranked wstopOutstanding, it searches for the correct insertion position, shifts lower-ranked entries down, and inserts the current loan’s identifiers, borrower name, outstanding amount, loanClass, and loanType into the top-10 arrays.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] Conditional: LOAN-OUTSTANDING &gt; WSTOP-OUTSTANDING
       *   [pattern] Conditional: WS-INSERT-IDX &lt;= 10
       *   A loan is only considered for the top-10 list if loanOutstanding is greater than the current 10th-ranked wstopOutstanding(10); loans at or below that threshold are ignored for ranking.
       *   Within the top-10 list, entries are ordered by descending loanOutstanding; the insertion scan finds the first position where loanOutstanding is greater than wstopOutstanding(wsInsertIdx).
       *   When inserting a new exposure into the top-10 list, existing entries at or below the insertion position are shifted down by one slot to preserve ordering and prevent overwriting.
       *   The stored customer display name for a top-10 entry is constructed as "custLastName space custFirstName" at the time of insertion.
       * </ul>
       */
        maintainTop10();
      /**
       * Sequentially reads the next record from the loan input stream and flags when no more loan records are available, without performing any additional processing on successful reads.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File READ operation
       * </ul>
       */
        readNext();
    }

    /**
     * Maps the loanClass code to a class index and increments class-level counters and monetary totals for outstanding balance and provision amount for the selected class bucket.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] EVALUATE on LOAN-CLASS: 5 branch(es) including WHEN OTHER default
     *   Loan class codes '1', '2', '3', and '4' are mapped directly to class indices 1 through 4 respectively; any other loanClass value is treated as class index 1 for aggregation purposes.
     * </ul>
     */
    private void aggregateByClass() {
                // TODO: original statement referenced undeclared: clIdx
        // Original: int clIdx;
        // TODO: original statement referenced undeclared: clIdx, equals
        // Original: if ("1".equals(loanClass)) {
        // Original: clIdx = 1;
        // Original: } else if ("2".equals(loanClass)) {
            // TODO: original statement referenced undeclared: clIdx, equals
            // Original: clIdx = 2;
            // Original: } else if ("3".equals(loanClass)) {
            // TODO: original statement referenced undeclared: clIdx, equals
            // Original: clIdx = 3;
            // Original: } else if ("4".equals(loanClass)) {
            // TODO: original statement referenced undeclared: clIdx
            // Original: clIdx = 4;
            // Original: } else {
            // TODO: original statement referenced undeclared: clIdx
            // Original: clIdx = 1;
            // Original: }
        wsclCount = wsclCount + 1;
        wsclOutstanding = wsclOutstanding.add(loanOutstanding);
        wsclProvision = wsclProvision.add(loanProvisionAmt);
    }

    /**
     * Iterates through predefined loan type buckets and, when a bucket code matches the current loanType, increments that bucket’s loan count and total outstanding amount, then exits the loop.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   Loan type aggregation only occurs for the first index where wstyCode at tyIdx equals loanType; once matched, the loop terminates and no further type buckets are updated.
     * </ul>
     */
    private void aggregateByType() {
                for (wsInsertIdx = 1; wsInsertIdx <= 6; wsInsertIdx++) {
            if (wstyCode != null && loanType != null && wstyCode.equals(loanType)) {
                wstyCount = wstyCount + 1;
                if (loanOutstanding != null) {
                    if (wstyAmount == null) {
                        wstyAmount = loanOutstanding;
                    } else {
                        wstyAmount = wstyAmount.add(loanOutstanding);
                    }
                }
                break;
            }
        }
    }

    /**
     * Looks up a customer record for the current customer id and clears key customer identity fields when the lookup fails, leaving any successful read data unchanged.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File READ operation
     * </ul>
     */
    private void lookupCustomer() {
                custId = wsCurrentCustId;
    }

    /**
     * Loops over up to four customer segments and, for the first segment whose wsseCode matches custSegment, increments that segment’s loan counter, adds loanOutstanding into that segment’s outstanding total, and increments either the approved or declined counter based on the LOAN-ACTIVE status condition, then exits the loop early.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   For each loan, only the first matching customer segment (where wsseCode(segIdx) = custSegment) is updated; once matched, no further segments are considered for that loan.
     *   Loans contribute their loanOutstanding amount to the outstanding total of exactly one segment bucket, determined by the custSegment code.
     *   Loan status condition LOAN-ACTIVE controls classification: active loans increment wsseApproved for the matched segment, while non-active loans increment wsseDeclined for that segment.
     * </ul>
     */
    private void aggregateBySegment() {
        final String[] segCodes = {"MM", "MB", "PR", "PB"};
        String segment = custSegment != null ? custSegment.trim() : "";
        for (String code : segCodes) {
            if (code.equals(segment)) {
                wsseCode = code;
                wsseCount = wsseCount + 1;
                if (loanOutstanding != null) {
                    wsseOutstanding = wsseOutstanding.add(loanOutstanding);
                }
                if ("AC".equals(loanStatus)) {
                    wsseApproved = wsseApproved + 1;
                } else {
                    wsseDeclined = wsseDeclined + 1;
                }
                return;
            }
        }
    }

    /**
     * Maintains a descending top-10 list of exposures by loanOutstanding: if the current loanOutstanding exceeds the 10th-ranked wstopOutstanding, it searches for the correct insertion position, shifts lower-ranked entries down, and inserts the current loan’s identifiers, borrower name, outstanding amount, loanClass, and loanType into the top-10 arrays.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] Conditional: LOAN-OUTSTANDING &gt; WSTOP-OUTSTANDING
     *   [pattern] Conditional: WS-INSERT-IDX &lt;= 10
     *   A loan is only considered for the top-10 list if loanOutstanding is greater than the current 10th-ranked wstopOutstanding(10); loans at or below that threshold are ignored for ranking.
     *   Within the top-10 list, entries are ordered by descending loanOutstanding; the insertion scan finds the first position where loanOutstanding is greater than wstopOutstanding(wsInsertIdx).
     *   When inserting a new exposure into the top-10 list, existing entries at or below the insertion position are shifted down by one slot to preserve ordering and prevent overwriting.
     *   The stored customer display name for a top-10 entry is constructed as "custLastName space custFirstName" at the time of insertion.
     * </ul>
     */
    private void maintainTop10() {
                if (loanOutstanding != null && loanOutstanding.compareTo(wstopOutstanding) > 0) {
            wsInsertIdx = 10;
            for (wsInsertIdx = 1; wsInsertIdx <= 10; wsInsertIdx++) {
                if (loanOutstanding.compareTo(wstopOutstanding) > 0) {
                    break;
                }
            }
            if (wsInsertIdx <= 10) {
                for (wsShiftIdx = 10; wsShiftIdx > wsInsertIdx; wsShiftIdx--) {
                    wstopLoanId = wstopLoanId;
                    wstopCustId = wstopCustId;
                    wstopCustName = wstopCustName;
                    wstopOutstanding = wstopOutstanding;
                    wstopClass = wstopClass;
                    wstopType = wstopType;
                }
                wstopLoanId = wsCurrentLoanId;
                wstopCustId = wsCurrentCustId;
                wstopCustName = (custLastName == null ? "" : custLastName) + " " + (custFirstName == null ? "" : custFirstName);
                wstopOutstanding = loanOutstanding;
                wstopClass = loanClass;
                wstopType = loanType;
            }
        }
    }

    /**
     * Generates the report’s Section 1 for portfolio by class: writes a section header and separator, then for each of four classes outputs the class index, wsclCount, and wsclOutstanding; afterwards prints the total outstanding amount and, when non-zero, computes and prints the overall provision percentage and weighted average rate using wsTotalProvision, wsTotalOutstanding, and wsAvgRateNum, updating wsLineCount as lines are written and calling checkPage() before blocks of output.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] Conditional: WS-TOTAL-OUTSTANDING &gt; 0
     *   [pattern] 2 COMPUTE statement(s) targeting WS-DISP-PCT, WS-AVG-RATE
     *   [pattern] File WRITE operation
     *   Section 1 always reports four class buckets, iterating CL-IDX from 1 to 4, regardless of whether individual class counts or amounts are zero.
     *   The total outstanding line always displays wsTotalOutstanding as the portfolio encours value.
     *   Provision and rate metrics are only computed and printed when wsTotalOutstanding is greater than 0, preventing division by zero in the provision percentage and average rate calculations.
     *   The provision percentage is calculated as (wsTotalProvision / wsTotalOutstanding) * 100 and displayed as a percentage value.
     *   The weighted average rate is calculated as wsAvgRateNum / wsTotalOutstanding and displayed as a percentage value.
     *   Pagination control via checkPage() is invoked before the section header, before the per-class loop output, and before the totals block to avoid overrunning the page based on wsLineCount.
     * </ul>
     */
    private void writeSection1() {
              /**
               * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
               * <p><b>Business rules (analysis-extracted):</b></p>
               * <ul>
               *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
               *   [pattern] File WRITE operation
               * </ul>
               */
                checkPage();
        monthLine = "";
      /**
       * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
       *   [pattern] File WRITE operation
       * </ul>
       */
        checkPage();
        monthLine = "SECTION 1 - REPARTITION DU PORTEFEUILLE PAR CLASSE";
        new RptSeparator();
        wsLineCount = wsLineCount + 3;
        for (wsDispIdx = 1; wsDispIdx <= 4; wsDispIdx++) {
          /**
           * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
           *   [pattern] File WRITE operation
           * </ul>
           */
            checkPage();
            wsDispCount = "";
            wsDispAmount = "";
            monthLine = " CLASSE " + wsDispIdx + " COUNT=" + wsDispCount + " ENC=" + wsDispAmount;
            wsLineCount = wsLineCount + 1;
        }
      /**
       * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
       *   [pattern] File WRITE operation
       * </ul>
       */
        checkPage();
        wsDispAmount = "";
        monthLine = " TOTAL ENCOURS : " + wsDispAmount;
        wsLineCount = wsLineCount + 1;
        if (wsTotalOutstanding.compareTo(BigDecimal.ZERO) > 0) {
            wsDispPct = "";
            wsAvgRate = wsAvgRateNum.divide(wsTotalOutstanding, 10, RoundingMode.HALF_UP);
            wsDispAmount = "";
            monthLine = " TOTAL PROVISIONS : " + wsDispAmount + " TAUX PROV: " + wsDispPct + "%";
            wsDispRate = "";
            monthLine = " TAUX MOYEN PONDERE : " + wsDispRate + "%";
            wsLineCount = wsLineCount + 2;
        }
    }

    /**
     * Generates the report’s Section 2 for top 10 exposures: writes a section header and separator, then loops through TOP-IDX 1 to 10 and, for each non-zero wstopLoanId, calls checkPage(), formats the rank, loan ID, customer name, class, type, and outstanding amount into monthLine, writes it, and increments wsLineCount.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     *   Section 2 always iterates through 10 ranking slots (TOP-IDX 1 to 10), but only prints entries where wstopLoanId(topIdx) is not zero, effectively skipping unused positions.
     *   Each printed top exposure line includes the rank number, loan identifier, customer name, loan class, loan type, and outstanding amount as stored in the wstop* arrays.
     *   Pagination control via checkPage() is invoked before printing each individual top exposure line that passes the non-zero wstopLoanId condition to manage page breaks based on wsLineCount.
     * </ul>
     */
    private void writeSection2() {
              /**
               * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
               * <p><b>Business rules (analysis-extracted):</b></p>
               * <ul>
               *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
               *   [pattern] File WRITE operation
               * </ul>
               */
                checkPage();
        monthLine = "";
        monthLine = "";
        monthLine = "SECTION 2 - TOP 10 EXPOSITIONS";
        monthLine = "";
        wsLineCount = wsLineCount + 3;
        for (wsDispIdx = 1; wsDispIdx <= 10; wsDispIdx++) {
            if (wstopLoanId != 0) {
              /**
               * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
               * <p><b>Business rules (analysis-extracted):</b></p>
               * <ul>
               *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
               *   [pattern] File WRITE operation
               * </ul>
               */
                checkPage();
                wsDispAmount = "";
                wsDispIdx = wsDispIdx;
                monthLine = " #" + wsDispIdx + " " + wstopLoanId + " " + wstopCustName + " CL:" + wstopClass + " " + wstopType + " ENC:" + wsDispAmount;
                wsLineCount = wsLineCount + 1;
            }
        }
    }

    /**
     * Formats and writes the report's Section 3 header and a per-segment client distribution, looping over four client segments, copying each segment's count and outstanding amount into display fields, composing a descriptive line with segment code, count, and exposure, writing it to the report, and updating the current page line counter while invoking checkPage() before the section and each detail line.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void writeSection3() {
              /**
               * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
               * <p><b>Business rules (analysis-extracted):</b></p>
               * <ul>
               *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
               *   [pattern] File WRITE operation
               * </ul>
               */
                checkPage();
        monthLine = "";
      /**
       * Formats and writes the report's Section 3 header and a per-segment client distribution, looping over four client segments, copying each segment's count and outstanding amount into display fields, composing a descriptive line with segment code, count, and exposure, writing it to the report, and updating the current page line counter while invoking checkPage() before the section and each detail line.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        // TODO: removed self-recursive writeSection3()
        monthLine = "SECTION 3 - REPARTITION PAR SEGMENT CLIENT";
      /**
       * Formats and writes the report's Section 3 header and a per-segment client distribution, looping over four client segments, copying each segment's count and outstanding amount into display fields, composing a descriptive line with segment code, count, and exposure, writing it to the report, and updating the current page line counter while invoking checkPage() before the section and each detail line.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        // TODO: removed self-recursive writeSection3()
      /**
       * Formats and writes the report's Section 3 header and a per-segment client distribution, looping over four client segments, copying each segment's count and outstanding amount into display fields, composing a descriptive line with segment code, count, and exposure, writing it to the report, and updating the current page line counter while invoking checkPage() before the section and each detail line.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        // TODO: removed self-recursive writeSection3()
        wsLineCount = wsLineCount + 3;
        for (wsDispIdx = 1; wsDispIdx <= 4; wsDispIdx++) {
          /**
           * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
           *   [pattern] File WRITE operation
           * </ul>
           */
            checkPage();
            wsDispCount = "";
            wsDispAmount = "";
            monthLine = " SEGMENT " + wsseCode + " CNT=" + wsDispCount + " ENC=" + wsDispAmount;
          /**
           * Formats and writes the report's Section 3 header and a per-segment client distribution, looping over four client segments, copying each segment's count and outstanding amount into display fields, composing a descriptive line with segment code, count, and exposure, writing it to the report, and updating the current page line counter while invoking checkPage() before the section and each detail line.
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] File WRITE operation
           * </ul>
           */
            // TODO: removed self-recursive writeSection3()
            wsLineCount = wsLineCount + 1;
        }
    }

    /**
     * Formats and writes the report's Section 4 header and a per-loan-type distribution, looping over six loan types, copying each type's count and amount into display fields, composing a descriptive line with type code, label, count, and amount, writing it to the report, and updating the current page line counter while invoking checkPage() before the section and each detail line.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void writeSection4() {
              /**
               * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
               * <p><b>Business rules (analysis-extracted):</b></p>
               * <ul>
               *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
               *   [pattern] File WRITE operation
               * </ul>
               */
                checkPage();
        monthLine = "";
        monthLine = "SECTION 4 - VENTILATION PAR TYPE DE CREDIT";
        monthLine = "";
        wsLineCount = wsLineCount + 3;
        for (wsDispIdx = 1; wsDispIdx <= 6; wsDispIdx++) {
          /**
           * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
           *   [pattern] File WRITE operation
           * </ul>
           */
            checkPage();
            wsDispCount = "";
            wsDispAmount = "";
            monthLine = " " + wstyCode + " " + wstyLabel + " CNT=" + wsDispCount + " AMT=" + wsDispAmount;
            wsLineCount = wsLineCount + 1;
        }
    }

    /**
     * Formats and writes the report's Section 5 header for risk indicators, then, only when total outstanding exposure is greater than zero, computes three rounded percentage ratios based on outstanding and provision totals (non-performing loans across classes 2–4, loss-class 4 only, and provision coverage), writes labeled lines for each ratio to the report, increments the line counter accordingly, and uses checkPage() to manage pagination before the section.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] Conditional: WS-TOTAL-OUTSTANDING &gt; 0
     *   [pattern] 3 COMPUTE statement(s) targeting WS-DISP-PCT
     *   [pattern] File WRITE operation
     *   Risk ratio calculations and their output are performed only if wsTotalOutstanding is greater than 0, preventing division-by-zero when computing percentages.
     * </ul>
     */
    private void writeSection5() {
              /**
               * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
               * <p><b>Business rules (analysis-extracted):</b></p>
               * <ul>
               *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
               *   [pattern] File WRITE operation
               * </ul>
               */
                checkPage();
        monthLine = "";
        monthLine = "SECTION 5 - INDICATEURS DE RISQUE";
        monthLine = "";
        wsLineCount = wsLineCount + 3;
        if (wsTotalOutstanding.compareTo(new BigDecimal("0")) > 0) {
            // TODO: original statement referenced undeclared: wsclOutstanding2
            // Original: BigDecimal wsclOutstanding2 = wsclOutstanding;
            // TODO: original statement referenced undeclared: wsclOutstanding3
            // Original: BigDecimal wsclOutstanding3 = wsclOutstanding;
            // TODO: original statement referenced undeclared: wsclOutstanding4
            // Original: BigDecimal wsclOutstanding4 = wsclOutstanding;
            // TODO: original statement referenced undeclared: wsDispPctNum, wsclOutstanding2, wsclOutstanding3, wsclOutstanding4
            // Original: BigDecimal wsDispPctNum = wsclOutstanding2.add(wsclOutstanding3).add(wsclOutstanding4);
            // TODO: original statement referenced undeclared: wsDispPctBd, wsDispPctNum
            // Original: BigDecimal wsDispPctBd = wsDispPctNum
            // Original: .divide(wsTotalOutstanding, 2, RoundingMode.HALF_UP)
            // Original: .multiply(new BigDecimal("100"));
            // TODO: original statement referenced undeclared: wsDispPctBd
            // Original: wsDispPct = wsDispPctBd + "";
            monthLine = " RATIO NPL (CL 2-3-4) : " + wsDispPct + "%";
            // TODO: original statement referenced undeclared: wsDispPctBd, wsclOutstanding4
            // Original: wsDispPctBd = wsclOutstanding4
            // Original: .divide(wsTotalOutstanding, 2, RoundingMode.HALF_UP)
            // Original: .multiply(new BigDecimal("100"));
            // TODO: original statement referenced undeclared: wsDispPctBd
            // Original: wsDispPct = wsDispPctBd + "";
            monthLine = " RATIO PERTES (CL 4) : " + wsDispPct + "%";
            // TODO: original statement referenced undeclared: wsDispPctBd
            // Original: wsDispPctBd = wsTotalProvision
            // Original: .divide(wsTotalOutstanding, 2, RoundingMode.HALF_UP)
            // Original: .multiply(new BigDecimal("100"));
            // TODO: original statement referenced undeclared: wsDispPctBd
            // Original: wsDispPct = wsDispPctBd + "";
            monthLine = " TAUX COUVERTURE PROV : " + wsDispPct + "%";
            wsLineCount = wsLineCount + 3;
        }
    }

    /**
     * Writes the final report footer by outputting a blank spacer line, a separator line, and a static end-of-report message indicating the report was generated by program RPTMONTH v2.3, followed by a footer line.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void writeFooter() {
                monthLine = "";
        monthLine = " FIN DU RAPPORT - GENERE PAR RPTMONTH v2.3";
    }

    /**
     * Controls report pagination by checking if the current line count has reached the maximum lines per page; when the threshold is met it increments the internal page counter, copies the new page number into the report header field, writes a main header line and a separator line to monthLine for the new page, and resets the line counter to start after the header lines.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] Conditional: WS-LINE-COUNT &gt;= WS-MAX-LINES
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void checkPage() {
                if (wsLineCount >= wsMaxLines) {
            wsPageNo = wsPageNo + 1;
            rptPageNo = String.valueOf(wsPageNo);
            wsLineCount = 2;
        }
    }

    /**
     * Sequentially reads the next record from the loan input stream and flags when no more loan records are available, without performing any additional processing on successful reads.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File READ operation
     * </ul>
     */
    private void readNext() {
        try {
            if (loanFileReader == null) {
                wsEndLoanFile = "Y";
                return;
            }
            String line = loanFileReader.readLine();
            if (line == null) {
                wsEndLoanFile = "Y";
                return;
            }
            applyLoanLine(line);
            wsEndLoanFile = "N";
        } catch (IOException e) {
            wsEndLoanFile = "Y";
        }
    }

    /**
     * Controls the overall monthly report run: sets wsProgramName, captures wsTodayDate from the system date, logs a startup message, calls openFiles(), and if rcSuccess is false it logs wsErrorMessage, sets the process return code to 12, and terminates the program; otherwise it calls initTables(), writeCover(), aggregatePortfolio(), then sequentially calls writeSection1() through writeSection5(), writeFooter(), calls closeFiles(), logs completion with wsTotalLoans and wsTotalOutstanding, sets the process return code to 0, and stops execution.
     */
    
        public static void main(String[] args) {
        new RptmonthApplication().run();
    }

}
