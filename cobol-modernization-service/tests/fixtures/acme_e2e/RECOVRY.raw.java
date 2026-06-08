package com.modernized.recovry;

import java.util.ArrayList;
import java.util.List;
import java.util.Comparator;
import java.io.*;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.*;
public class RecovryApplication {

    private static final Path LOAN_FILE_PATH = Path.of("LOANFILE.dat");
    private static final Path CUST_FILE_PATH = Path.of("CUSTFILE.dat");
    private static final Path COL_FILE_PATH = Path.of("COLFILE.dat");
    private static final Path RECVNEW_FILE_PATH = Path.of("RECVNEW.dat");
    private static final Path LETTERS_FILE_PATH = Path.of("LETTERS.dat");
    private static final Path ESCARPT_FILE_PATH = Path.of("ESCARPT.dat");
    private static final Path SORTWK2_FILE_PATH = Path.of("SORTWK2.dat");

    private BufferedReader loanFileReader;

private BigDecimal colAppraisalValue = BigDecimal.ZERO;
private BigDecimal colCoverageRatio = BigDecimal.ZERO;
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
private BigDecimal statApprovedAmt = BigDecimal.ZERO;
private BigDecimal statDeclinedAmt = BigDecimal.ZERO;
private BigDecimal statTotalAmt = BigDecimal.ZERO;
private BigDecimal wsCl2Amount = BigDecimal.ZERO;
private BigDecimal wsCl3Amount = BigDecimal.ZERO;
private BigDecimal wsCl4Amount = BigDecimal.ZERO;
private int colAppraisalDate = 0;
private int colCustId = 0;
private int colId = 0;
private int colInsuranceExpiry = 0;
private int colLoanId = 0;
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
private int sortAmount = 0;
private int sortCustId = 0;
private int sortDpd = 0;
private int sortLoanId = 0;
private int sortPriority = 0;
private int statApproved = 0;
private int statConditional = 0;
private int statDeclined = 0;
private int statErrors = 0;
private int statProcessed = 0;
private int statRead = 0;
private int statSkipped = 0;
private int wsActCrt = 0;
private int wsActCsz = 0;
private int wsActDul = 0;
private int wsActEmail = 0;
private int wsActGtr = 0;
private int wsActLeg = 0;
private int wsActPhone = 0;
private int wsActRst = 0;
private int wsActSms = 0;
private int wsActWof = 0;
private int wsCl2Count = 0;
private int wsCl3Count = 0;
private int wsCl4Count = 0;
private int wsCurrentCustId = 0;
private int wsCurrentLoanId = 0;
private int wsDaysFromLastAct = 0;
private int wsErrorCode = 0;
private int wsLastActionDate = 0;
private int wsLetterLineIdx = 0;
private int wsRecovSeq = 0;
private int wsReturnCode = 0;
private int wsTodayDate = 0;
private SeekableByteChannel collateralFileChannel;
private SeekableByteChannel customerFileChannel;
private SeekableByteChannel escalationRptFileChannel;
private SeekableByteChannel letterFileChannel;
private SeekableByteChannel loanFileChannel;
private SeekableByteChannel recoveryNewFileChannel;
private SeekableByteChannel sortWorkFileChannel;
private String colAppraisalFirm = "";
private String colDescription = "";
private String colFiller = "";
private String colInsuranceNum = "";
private String colLocation = "";
private String colRegistration = "";
private String colStatus = "";
private String colType = "";
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
private String escaRptLine = "";
private String lbText = "";
private String letterLine = "";
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
private String rptBankName = "";
private String rptDateLbl = "";
private String rptPageLbl = "";
private String rptPageNo = "";
private String rptProgram = "";
private String rptTitle = "";
private String sortClass = "";
private String sortFiller = "";
private String wsColFs = "";
private String wsCustFs = "";
private String wsEndLoanFile = "";
private String wsErrorMessage = "";
private String wsGtrFs = "";
private String wsLastActionCode = "";
private String wsLoanFs = "";
private String wsLogFs = "";
private String wsLtrFs = "";
private String wsNextActionCode = "";
private String wsOutFs = "";
private String wsParagraphName = "";
private String wsProgramName = "";
private String wsRecFs = "";
private String wsRejFs = "";
private String wsRptFs = "";
private String wsScrFs = "";

    /**
     * Top-level orchestration for the recovery batch: it initializes program identity and run date, invokes file opening and report initialization, runs a keyed SORT over the work file with dedicated input and output procedures, then writes a summary, closes resources, and displays run statistics and final status while setting the process return code.
     */

    // TODO: [analysis-hint] Internal SORT detected — use java.util.List + Comparator for sort operations.

    // TODO: [analysis-hint] High file I/O count — use try-with-resources for all file handles.
    public static void main(String[] args) {
        new RecovryApplication().run();
    }

    public void run() {
        wsTodayDate = Integer.parseInt(java.time.LocalDate.now().format(java.time.format.DateTimeFormatter.BASIC_ISO_DATE));
        System.out.println("RECOVRY V2.5 START " + String.format("%08d", wsTodayDate));

                wsProgramName = "RECOVRY ";
      /**
       * File initialization and error-guard paragraph that opens all required input and output files for the recovery process, checks each file status condition, and on any failure sets wsReturnCode and wsErrorMessage, closes any previously opened files, and exits early to signal the caller that startup failed.
       */
        openFiles();
        if (wsReturnCode != 0) {
            wsReturnCode = 12;
                    System.out.println("RECOVRY ABEND: " + wsErrorMessage);
return;
        }
      /**
       * Initial report header setup paragraph that populates the main report control fields with the program name, run date, and initial page number, and writes the initial header and separator lines to the escalation report output.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        initReport();
        sortRecoveryWork();
      /**
       * Summary-report paragraph that writes a series of lines to the escalation report capturing class-level loan counts and amounts and action-type counts, using string concatenation into escaRptLine followed by WRITE operations and surrounding separators and footer.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        writeSummary();
      /**
       * Closes all processing-related files at the end of the program run, ensuring that the loan, customer, collateral, recovery, letter, and escalation report resources are properly terminated before control returns to the caller.
       */
        closeFiles();
        System.out.println("RECOVRY COMPLETED.");
        System.out.println(" CLASS 2 LOANS: " + String.format("%06d", wsCl2Count));
        System.out.println(" CLASS 3 LOANS: " + String.format("%06d", wsCl3Count));
        System.out.println(" CLASS 4 LOANS: " + String.format("%06d", wsCl4Count));
        System.out.println(" ACTIONS GENERATED:");
        System.out.println(" SMS : " + String.format("%06d", wsActSms));
        System.out.println(" EMAIL : " + String.format("%06d", wsActEmail));
        System.out.println(" PHONE : " + String.format("%06d", wsActPhone));
        System.out.println(" DUL : " + String.format("%06d", wsActDul));
        System.out.println(" LEG : " + String.format("%06d", wsActLeg));
        System.out.println(" GTR : " + String.format("%06d", wsActGtr));
        System.out.println(" RST : " + String.format("%06d", wsActRst));
        System.out.println(" CRT : " + String.format("%06d", wsActCrt));
        System.out.println(" CSZ : " + String.format("%06d", wsActCsz));
        System.out.println(" WOF : " + String.format("%06d", wsActWof));
        wsReturnCode = 0;
        return;
    }

    /**
     * Referenced as a performed paragraph from 2000-PROCESS-RECOVERY to obtain up-to-date loan data for the current wsCurrentLoanId; its internal logic is not present in this excerpt, but it conceptually refreshes loan-related fields before recovery decisions are made.
     */
    private void readLoanFresh() {
                // 2100-READ-LOAN-FRESH has only a CONTINUE statement in COBOL, so no action is required.
    }

    /**
     * Calculates a follow-up date by adding 15 days to the current processing date and stores it as the next action date for the recoveryAction.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
     *   recNextActionDate is computed as wsTodayDate + 15.
     * </ul>
     */
    private void add15Days() {
                recNextActionDate = wsTodayDate + 15;
    }

    /**
     * Calculates a follow-up recovery action date by setting recNextActionDate to wsTodayDate plus 30 days, providing a fixed 30-day offset from the current processing date for certain recovery actions invoked from generateAction().
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
     * </ul>
     */
    private void add30Days() {
                recNextActionDate = wsTodayDate + 30;
    }

    /**
     * Calculates a follow-up recovery action date by adding 60 days to the current processing date and storing the result in recNextActionDate, typically when invoked for specific recovery action types from generateAction().
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
     * </ul>
     */
    private void add60Days() {
                recNextActionDate = wsTodayDate + 60;
    }

    /**
     * Calculates a follow-up recovery action date by setting recNextActionDate to seven days after wsTodayDate when invoked for specific action types from generateAction().
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
     * </ul>
     */
    private void add7Days() {
                recNextActionDate = wsTodayDate + 7;
    }

    /**
     * Closes all processing-related files at the end of the program run, ensuring that the loan, customer, collateral, recovery, letter, and escalation report resources are properly terminated before control returns to the caller.
     */
    private void closeFiles() {
                if (loanFileChannel != null) {
            loanFileChannel = null;
        }
        if (customerFileChannel != null) {
            customerFileChannel = null;
        }
        if (collateralFileChannel != null) {
            collateralFileChannel = null;
        }
        if (recoveryNewFileChannel != null) {
            recoveryNewFileChannel = null;
        }
        if (letterFileChannel != null) {
            letterFileChannel = null;
        }
        if (escalationRptFileChannel != null) {
            escalationRptFileChannel = null;
        }
    }

    /**
     * Initializes the letter buffer and sequentially builds a French dunning-style letter in wsLetterBuffer lines, including bank header, date, customer name and address, loan reference, action-specific body text based on wsNextActionCode, overdue amount and days past due, and closing salutation.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] EVALUATE on WS-NEXT-ACTION-CODE: 3 branch(es)
     * </ul>
     */
    private void composeLetter() {
                wsLetterLineIdx = 0;
        wsLetterLineIdx = 1;
        lbText = "ACME BANK TUNISIE";
        wsLetterLineIdx = wsLetterLineIdx + 1;
        lbText = "15 Avenue Habib Bourguiba, 1001 Tunis";
        wsLetterLineIdx = wsLetterLineIdx + 1;
        lbText = "Tel: +216 71 123 456";
        wsLetterLineIdx = wsLetterLineIdx + 2;
        lbText = "Tunis, le " + wsTodayDate;
        wsLetterLineIdx = wsLetterLineIdx + 2;
        lbText = "Madame, Monsieur " + (custFirstName == null ? "" : custFirstName) + " " + (custLastName == null ? "" : custLastName);
        wsLetterLineIdx = wsLetterLineIdx + 1;
        lbText = custAddrLine1;
        wsLetterLineIdx = wsLetterLineIdx + 1;
        lbText = (custAddrZip == null ? "" : custAddrZip) + " " + (custAddrCity == null ? "" : custAddrCity);
        wsLetterLineIdx = wsLetterLineIdx + 3;
        lbText = "Objet: Mise en demeure - Dossier " + wsCurrentLoanId;
        wsLetterLineIdx = wsLetterLineIdx + 3;
        if ("DUL".equals(wsNextActionCode)) {
            lbText = "Nous constatons un retard de paiement sur votre dossier de credit.";
        } else if ("LEG".equals(wsNextActionCode)) {
            lbText = "Suite a nos rappels precedents restes sans suite, nous vous mettons formellement en demeure.";
        } else if ("GTR".equals(wsNextActionCode)) {
            lbText = "Nous nous reservons le droit de faire appel au garant en cas de non regularisation.";
        }
        wsLetterLineIdx = wsLetterLineIdx + 2;
        lbText = "Montant du sont: " + sortAmount + " TND";
        wsLetterLineIdx = wsLetterLineIdx + 1;
        lbText = "Jours de retard: " + sortDpd;
        wsLetterLineIdx = wsLetterLineIdx + 3;
        lbText = "Veuillez regulariser votre situation dans un delai de 15 jours.";
        wsLetterLineIdx = wsLetterLineIdx + 3;
        lbText = "Veuillez agreer, Madame, Monsieur, l expression de nos salutations distinguees.";
        wsLetterLineIdx = wsLetterLineIdx + 4;
        lbText = "Le Directeur du Recouvrement";
    }

    /**
     * Determines the next recovery action code based on loan classification and days past due, then updates per-action statistics counters for the selected action.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] EVALUATE on TRUE: 9 branch(es)
     *   [pattern] EVALUATE on WS-NEXT-ACTION-CODE: 10 branch(es)
     *   [pattern] Conditional: SORT-AMOUNT &gt; 50000
     *   For loans with sortClass = '2' and sortDpd &lt;= 45, set wsNextActionCode to 'SMS'.
     *   For loans with sortClass = '2' and sortDpd &gt; 45 and &lt;= 60, set wsNextActionCode to 'PHN'.
     *   For loans with sortClass = '2' and sortDpd &gt; 60, set wsNextActionCode to 'DUL'.
     *   For loans with sortClass = '3' and sortDpd &lt;= 120, set wsNextActionCode to 'LEG'.
     *   For loans with sortClass = '3' and sortDpd &gt; 120 and &lt;= 150, set wsNextActionCode to 'GTR'.
     *   For loans with sortClass = '3' and sortDpd &gt; 150, set wsNextActionCode to 'RST'.
     *   For loans with sortClass = '4' and sortDpd &lt;= 365, set wsNextActionCode to 'CRT'.
     *   For loans with sortClass = '4' and sortDpd &gt; 365 and &lt;= 540 and sortAmount &gt; 50000, set wsNextActionCode to 'CSZ'.
     *   For loans with sortClass = '4' and sortDpd &gt; 365 and &lt;= 540 and sortAmount &lt;= 50000, set wsNextActionCode to 'WOF'.
     *   For loans with sortClass = '4' and sortDpd &gt; 540, set wsNextActionCode to 'WOF'.
     *   After determining wsNextActionCode, increment the corresponding wsAct* counter (wsActSms, wsActEmail, wsActPhone, wsActDul, wsActLeg, wsActGtr, wsActRst, wsActCrt, wsActCsz, or wsActWof) by 1 based on the chosen action code.
     * </ul>
     */
    private void determineNextAction() {
                wsNextActionCode = "";
        if ("2".equals(sortClass) && sortDpd <= 45) {
            wsNextActionCode = "SMS";
        } else if ("2".equals(sortClass) && sortDpd <= 60) {
            wsNextActionCode = "PHN";
        } else if ("2".equals(sortClass)) {
            wsNextActionCode = "DUL";
        } else if ("3".equals(sortClass) && sortDpd <= 120) {
            wsNextActionCode = "LEG";
        } else if ("3".equals(sortClass) && sortDpd <= 150) {
            wsNextActionCode = "GTR";
        } else if ("3".equals(sortClass)) {
            wsNextActionCode = "RST";
        } else if ("4".equals(sortClass) && sortDpd <= 365) {
            wsNextActionCode = "CRT";
        } else if ("4".equals(sortClass) && sortDpd <= 540) {
            if (sortAmount > 50000) {
                wsNextActionCode = "CSZ";
            } else {
                wsNextActionCode = "WOF";
            }
        } else if ("4".equals(sortClass)) {
            wsNextActionCode = "WOF";
        }
        if ("SMS".equals(wsNextActionCode)) {
            wsActSms = wsActSms + 1;
        } else if ("EML".equals(wsNextActionCode)) {
            wsActEmail = wsActEmail + 1;
        } else if ("PHN".equals(wsNextActionCode)) {
            wsActPhone = wsActPhone + 1;
        } else if ("DUL".equals(wsNextActionCode)) {
            wsActDul = wsActDul + 1;
        } else if ("LEG".equals(wsNextActionCode)) {
            wsActLeg = wsActLeg + 1;
        } else if ("GTR".equals(wsNextActionCode)) {
            wsActGtr = wsActGtr + 1;
        } else if ("RST".equals(wsNextActionCode)) {
            wsActRst = wsActRst + 1;
        } else if ("CRT".equals(wsNextActionCode)) {
            wsActCrt = wsActCrt + 1;
        } else if ("CSZ".equals(wsNextActionCode)) {
            wsActCsz = wsActCsz + 1;
        } else if ("WOF".equals(wsNextActionCode)) {
            wsActWof = wsActWof + 1;
        }
    }

    /**
     * Outputs each composed letter line from wsLetterBuffer to letterLine in a fixed loop, then writes spacing and a separator line of '=' characters to visually delimit the letter.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void emitLetter() {
                for (wsLetterLineIdx = 1; wsLetterLineIdx <= 30; wsLetterLineIdx++) {
            letterLine = lbText;
        }
        letterLine = "";
        letterLine = "";
        letterLine = "";
    }

    /**
     * Creates and writes a recoveryAction record for the selected next action, populating identifiers, dates, amounts, default response, scheduling the next action date based on the action type, and setting officer and legal fields.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] EVALUATE on WS-NEXT-ACTION-CODE: 10 branch(es)
     *   [pattern] File WRITE operation
     *   Each generated recoveryAction increments wsRecovSeq by 1 and uses the new value as recActionId.
     *   The recoveryAction is tied to the current loan and customer by copying wsCurrentLoanId to recLoanId and wsCurrentCustId to recCustId.
     *   The action date recActionDate is set to wsTodayDate and recActionTime is fixed at 120000.
     *   The action type recActionType is set from wsNextActionCode.
     *   The claimed amount recAmountClaimed is set from sortAmount and recAmountRecovered is initialized to 0.
     *   The initial response flag recResponse is set to 'N'.
     *   If wsNextActionCode is 'SMS' or 'EML', schedule the next action date via add7Days().
     *   If wsNextActionCode is 'PHN', schedule the next action date via add7Days().
     *   If wsNextActionCode is 'DUL', schedule the next action date via add15Days().
     *   If wsNextActionCode is 'LEG', 'GTR', or 'RST', schedule the next action date via add30Days().
     *   If wsNextActionCode is 'CRT' or 'CSZ', schedule the next action date via add60Days().
     *   If wsNextActionCode is 'WOF', set recNextActionDate equal to wsTodayDate.
     *   The officer responsible for the action is hard-coded as recOfficerId = 100000.
     *   Legal-related fields recLegalFirm and recCourtCaseNum are cleared to spaces for each new action.
     *   A descriptive comment is built into recComments combining the literal 'ACTION ', wsNextActionCode, ' AMT ', sortAmount, and ' DPD ', sortDpd before writing the recoveryAction record.
     * </ul>
     */
    private void generateAction() {
                wsRecovSeq = wsRecovSeq + 1;
        recActionId = wsRecovSeq;
        recLoanId = wsCurrentLoanId;
        recCustId = wsCurrentCustId;
        recActionDate = wsTodayDate;
        recActionTime = 120000;
        recActionType = wsNextActionCode;
        recAmountClaimed = new BigDecimal(sortAmount);
        recAmountRecovered = new BigDecimal("0");
        recResponse = "N";
        if (wsNextActionCode == "SMS" || wsNextActionCode == "EML") {
          /**
           * Calculates a follow-up recovery action date by setting recNextActionDate to seven days after wsTodayDate when invoked for specific action types from generateAction().
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
           * </ul>
           */
            add7Days();
        } else if (wsNextActionCode == "PHN") {
          /**
           * Calculates a follow-up recovery action date by setting recNextActionDate to seven days after wsTodayDate when invoked for specific action types from generateAction().
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
           * </ul>
           */
            add7Days();
        } else if (wsNextActionCode == "DUL") {
          /**
           * Calculates a follow-up date by adding 15 days to the current processing date and stores it as the next action date for the recoveryAction.
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
           *   recNextActionDate is computed as wsTodayDate + 15.
           * </ul>
           */
            add15Days();
        } else if (wsNextActionCode == "LEG") {
          /**
           * Calculates a follow-up recovery action date by setting recNextActionDate to wsTodayDate plus 30 days, providing a fixed 30-day offset from the current processing date for certain recovery actions invoked from generateAction().
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
           * </ul>
           */
            add30Days();
        } else if (wsNextActionCode == "GTR") {
          /**
           * Calculates a follow-up recovery action date by setting recNextActionDate to wsTodayDate plus 30 days, providing a fixed 30-day offset from the current processing date for certain recovery actions invoked from generateAction().
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
           * </ul>
           */
            add30Days();
        } else if (wsNextActionCode == "RST") {
          /**
           * Calculates a follow-up recovery action date by setting recNextActionDate to wsTodayDate plus 30 days, providing a fixed 30-day offset from the current processing date for certain recovery actions invoked from generateAction().
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
           * </ul>
           */
            add30Days();
        } else if (wsNextActionCode == "CRT") {
          /**
           * Calculates a follow-up recovery action date by adding 60 days to the current processing date and storing the result in recNextActionDate, typically when invoked for specific recovery action types from generateAction().
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
           * </ul>
           */
            add60Days();
        } else if (wsNextActionCode == "CSZ") {
          /**
           * Calculates a follow-up recovery action date by adding 60 days to the current processing date and storing the result in recNextActionDate, typically when invoked for specific recovery action types from generateAction().
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] 1 COMPUTE statement(s) targeting REC-NEXT-ACTION-DATE
           * </ul>
           */
            add60Days();
        } else if (wsNextActionCode == "WOF") {
            recNextActionDate = wsTodayDate;
        }
        recOfficerId = 100000;
        recLegalFirm = "";
        recCourtCaseNum = "";
        recComments = "ACTION " + wsNextActionCode + " AMT " + sortAmount + " DPD " + sortDpd;
    }

    /**
     * Initial report header setup paragraph that populates the main report control fields with the program name, run date, and initial page number, and writes the initial header and separator lines to the escalation report output.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void initReport() {
                rptProgram = "RECOVRY ";
        rptRunDate = wsTodayDate;
        rptTitle = "RAPPORT ESCALADE RECOUVREMENT";
        rptPageNo = "1";
      /**
       * Formats and writes a single escalation report line by concatenating the current loan and customer identifiers, loan classification, days past due, amount, and the next action code into escaRptLine, then outputs that line to the report file or stream.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        writeEscalationLine();
      /**
       * Formats and writes a single escalation report line by concatenating the current loan and customer identifiers, loan classification, days past due, amount, and the next action code into escaRptLine, then outputs that line to the report file or stream.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        writeEscalationLine();
      /**
       * Formats and writes a single escalation report line by concatenating the current loan and customer identifiers, loan classification, days past due, amount, and the next action code into escaRptLine, then outputs that line to the report file or stream.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] File WRITE operation
       * </ul>
       */
        writeEscalationLine();
    }

    /**
     * Scans all loan records from the loan file, and for each loan that is either active or restructured, assigns a numeric sortPriority based on loanClass (100 for class '2', 200 for class '3', 300 for class '4') and conditionally calls releaseToSort() to pass the loan into the sort stream; iteration continues until wsEndLoanFile is flagged as 'Y' by an end-of-file condition on the loan file reads.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] EVALUATE on LOAN-CLASS: 4 branch(es) including WHEN OTHER default
     *   [pattern] File READ operation
     *   Only loans that satisfy the LOAN-ACTIVE or LOAN-RESTRUCTURED status conditions are eligible to be included in the sort output.
     *   Loan records with loanClass = '2' are assigned sortPriority = 100 before being released to sort.
     *   Loan records with loanClass = '3' are assigned sortPriority = 200 before being released to sort.
     *   Loan records with loanClass = '4' are assigned sortPriority = 300 before being released to sort.
     *   Loan records whose loanClass is not '2', '3', or '4' are not released to sort and are effectively excluded from the sorted population.
     * </ul>
     */
    private void loadSort(List<SortLoanRec> buffer) {
        while (!"Y".equals(wsEndLoanFile)) {
            if (!"AC".equals(loanStatus) && !"RS".equals(loanStatus)) {
                readNextLoan();
                continue;
            }
            if ("2".equals(loanClass)) {
                sortPriority = 100;
                releaseToSort(buffer);
            } else if ("3".equals(loanClass)) {
                sortPriority = 200;
                releaseToSort(buffer);
            } else if ("4".equals(loanClass)) {
                sortPriority = 300;
                releaseToSort(buffer);
            }
            readNextLoan();
        }
    }

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
        loanOutstanding = parseDisplayDecimal(line, 47, 60, 2);
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

    private void readNextLoan() {
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
            Files.newBufferedReader(COL_FILE_PATH).close();
            Files.newBufferedWriter(RECVNEW_FILE_PATH, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING).close();
            Files.newBufferedWriter(LETTERS_FILE_PATH, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING).close();
            Files.newBufferedWriter(ESCARPT_FILE_PATH, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING).close();
            Files.newBufferedWriter(SORTWK2_FILE_PATH, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING).close();
        } catch (IOException e) {
            wsReturnCode = 12;
            wsErrorMessage = "CUSTFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            loanFileReader = null;
            return;
        }
        wsReturnCode = 0;
        wsErrorMessage = "";
        readNextLoan();
    }

    /**
     * Iterates through all records from the SORT-WORK stream, maps each sorted entry’s loan and customer identifiers into wsCurrentLoanId and wsCurrentCustId, then for each entry orchestrates downstream processing by calling readLoanFresh(), readCustomer(), and determineNextAction(); if wsNextActionCode is not blank it conditionally triggers generation of a recovery action, optional letter output, and an escalation report line, repeating this sequence in a perform-until loop that terminates only when the RETURN from SORT-WORK signals end-of-data via AT END.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] Conditional: WS-NEXT-ACTION-CODE NOT = SPACES
     * </ul>
     */
    private void processRecovery(List<SortLoanRec> buffer) {
        for (SortLoanRec item : buffer) {
            sortPriority = item.sortPriority;
            sortAmount = item.sortAmount;
            sortLoanId = item.sortLoanId;
            sortCustId = item.sortCustId;
            sortDpd = item.sortDpd;
            sortClass = item.sortClass;
            wsCurrentLoanId = sortLoanId;
            wsCurrentCustId = sortCustId;
            readLoanFresh();
            readCustomer();
            determineNextAction();
            if (wsNextActionCode != null && !wsNextActionCode.trim().isEmpty()) {
                generateAction();
                writeLetterIfNeeded();
                writeEscalationLine();
            }
        }
    }

    /**
     * Loads the customer master record corresponding to the current recovery context by moving wsCurrentCustId into custId and issuing a keyed READ on CUSTOMER-FILE, with both INVALID KEY and NOT INVALID KEY branches falling through to CONTINUE, effectively ignoring read success or failure at this level.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File READ operation
     * </ul>
     */
    private void readCustomer() {
                custId = wsCurrentCustId;
    }

    /**
     * Prepares a SortLoanRec from the current loan fields, releases it to the COBOL sort, and updates per-class aggregation counters and amounts for delinquent loans based on loanClass
     */
    private void releaseToSort(List<SortLoanRec> buffer) {
        SortLoanRec rec = new SortLoanRec();
        rec.sortPriority = sortPriority;
        rec.sortAmount = loanOutstanding == null ? 0 : loanOutstanding.intValue();
        rec.sortLoanId = loanId;
        rec.sortCustId = loanCustId;
        rec.sortDpd = loanDaysPastDue;
        rec.sortClass = loanClass;
        rec.sortFiller = "";
        buffer.add(rec);
        if ("2".equals(loanClass)) {
            wsCl2Count = wsCl2Count + 1;
        } else if ("3".equals(loanClass)) {
            wsCl3Count = wsCl3Count + 1;
        } else if ("4".equals(loanClass)) {
            wsCl4Count = wsCl4Count + 1;
        }
    }

    private void sortRecoveryWork() {
        List<SortLoanRec> sortBuffer = new ArrayList<>();
        // INPUT PROCEDURE
      /**
       * Scans all loan records from the loan file, and for each loan that is either active or restructured, assigns a numeric sortPriority based on loanClass (100 for class '2', 200 for class '3', 300 for class '4') and conditionally calls releaseToSort() to pass the loan into the sort stream; iteration continues until wsEndLoanFile is flagged as 'Y' by an end-of-file condition on the loan file reads.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] EVALUATE on LOAN-CLASS: 4 branch(es) including WHEN OTHER default
       *   [pattern] File READ operation
       *   Only loans that satisfy the LOAN-ACTIVE or LOAN-RESTRUCTURED status conditions are eligible to be included in the sort output.
       *   Loan records with loanClass = '2' are assigned sortPriority = 100 before being released to sort.
       *   Loan records with loanClass = '3' are assigned sortPriority = 200 before being released to sort.
       *   Loan records with loanClass = '4' are assigned sortPriority = 300 before being released to sort.
       *   Loan records whose loanClass is not '2', '3', or '4' are not released to sort and are effectively excluded from the sorted population.
       * </ul>
       */
        loadSort(sortBuffer);
        // SORT — descending SORT-PRIORITY, descending SORT-AMOUNT
        sortBuffer.sort(Comparator.comparingInt((SortLoanRec a) -> a.sortPriority).reversed().thenComparingInt((SortLoanRec a) -> a.sortAmount).reversed());
        // OUTPUT PROCEDURE
      /**
       * Iterates through all records from the SORT-WORK stream, maps each sorted entry’s loan and customer identifiers into wsCurrentLoanId and wsCurrentCustId, then for each entry orchestrates downstream processing by calling readLoanFresh(), readCustomer(), and determineNextAction(); if wsNextActionCode is not blank it conditionally triggers generation of a recovery action, optional letter output, and an escalation report line, repeating this sequence in a perform-until loop that terminates only when the RETURN from SORT-WORK signals end-of-data via AT END.
       * <p><b>Business rules (analysis-extracted):</b></p>
       * <ul>
       *   [pattern] Conditional: WS-NEXT-ACTION-CODE NOT = SPACES
       * </ul>
       */
        processRecovery(sortBuffer);
    }

    /**
     * Formats and writes a single escalation report line by concatenating the current loan and customer identifiers, loan classification, days past due, amount, and the next action code into escaRptLine, then outputs that line to the report file or stream.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void writeEscalationLine() {
                // escaRptLine = String.valueOf(wsCurrentLoanId)
        // + " " + wsCurrentCustId
        // + " CL:" + sortClass
        // + " DPD:" + sortDpd
        // + " AMT:" + sortAmount
        // + " ACT:" + wsNextActionCode;
    }

    /**
     * Conditionally triggers letter composition and emission when a recovery next-action code indicates a dunning, legal, or guarantor-related step.
     */
    private void writeLetterIfNeeded() {
                if (wsNextActionCode == "DUL" || wsNextActionCode == "LEG" || wsNextActionCode == "GTR") {
          /**
           * Initializes the letter buffer and sequentially builds a French dunning-style letter in wsLetterBuffer lines, including bank header, date, customer name and address, loan reference, action-specific body text based on wsNextActionCode, overdue amount and days past due, and closing salutation.
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] EVALUATE on WS-NEXT-ACTION-CODE: 3 branch(es)
           * </ul>
           */
            composeLetter();
          /**
           * Outputs each composed letter line from wsLetterBuffer to letterLine in a fixed loop, then writes spacing and a separator line of '=' characters to visually delimit the letter.
           * <p><b>Business rules (analysis-extracted):</b></p>
           * <ul>
           *   [pattern] File WRITE operation
           * </ul>
           */
            emitLetter();
        }
    }

    /**
     * Summary-report paragraph that writes a series of lines to the escalation report capturing class-level loan counts and amounts and action-type counts, using string concatenation into escaRptLine followed by WRITE operations and surrounding separators and footer.
     * <p><b>Business rules (analysis-extracted):</b></p>
     * <ul>
     *   [pattern] File WRITE operation
     * </ul>
     */
    private void writeSummary() {
                escaRptLine = "";
        escaRptLine = "";
        escaRptLine = "RESUME PAR CLASSE";
        escaRptLine = " CLASSE 2 (30-90J) : " + wsCl2Count + " LOANS ENC: " + wsCl2Amount;
        escaRptLine = " CLASSE 3 (90-180J) : " + wsCl3Count + " LOANS ENC: " + wsCl3Amount;
        escaRptLine = " CLASSE 4 (>180J) : " + wsCl4Count + " LOANS ENC: " + wsCl4Amount;
        escaRptLine = "";
        escaRptLine = "ACTIONS GENEREES";
        escaRptLine = " SMS : " + wsActSms + " EMAIL: " + wsActEmail + " TEL : " + wsActPhone + " DUL : " + wsActDul;
        escaRptLine = " LEG : " + wsActLeg + " GTR : " + wsActGtr + " RST : " + wsActRst + " CRT : " + wsActCrt;
        escaRptLine = " CSZ : " + wsActCsz + " WOF : " + wsActWof;
        escaRptLine = "";
    }

    public static class CollateralRecord {
        private String colId = "";
        private String colLoanId = "";
        private String colCustId = "";
        private String colType = "";
        private String colDescription = "";
        private String colLocation = "";
        private String colAppraisalValue = "";
        private String colAppraisalDate = "";
        private String colAppraisalFirm = "";
        private String colCoverageRatio = "";
        private String colInsuranceNum = "";
        private String colInsuranceExpiry = "";
        private String colRegistration = "";
        private String colStatus = "";
        private String colFiller = "";
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

    public static class SortLoanRec {
        private int sortPriority = 0;
        private int sortAmount = 0;
        private int sortLoanId = 0;
        private int sortCustId = 0;
        private int sortDpd = 0;
        private String sortClass = "";
        private String sortFiller = "";
    }

    public static class WsActionStats {
        private String wsActSms = "";
        private String wsActEmail = "";
        private String wsActPhone = "";
        private String wsActDul = "";
        private String wsActLeg = "";
        private String wsActGtr = "";
        private String wsActRst = "";
        private String wsActCrt = "";
        private String wsActCsz = "";
        private String wsActWof = "";
    }

    public static class WsClassStats {
        private String wsCl2Count = "";
        private String wsCl3Count = "";
        private String wsCl4Count = "";
        private String wsCl2Amount = "";
        private String wsCl3Amount = "";
        private String wsCl4Amount = "";
    }

    public static class WsControl {
        private String wsTodayDate = "";
        private String wsEndLoanFile = "";
        private String wsCurrentLoanId = "";
        private String wsCurrentCustId = "";
    }

    public static class WsLetterBuffer {
    }

    public static class WsRecovWork {
        private String wsNextActionCode = "";
        private String wsRecovSeq = "";
        private String wsDaysFromLastAct = "";
        private String wsLastActionDate = "";
        private String wsLastActionCode = "";
    }

}
