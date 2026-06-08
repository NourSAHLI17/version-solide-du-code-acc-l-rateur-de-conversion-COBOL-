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
                dec = (int) tail.chars().filter(ch -> ch == '9').count();
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

public class Riskscor {

// File paths (hardcoded as per configuration)
    private static final String LOAN_FILE_PATH = "LOANFILE.dat";
private static final String BCT_SUBMISSION_FILE_PATH = "BCTSUBM.dat";
private static final String CUSTOMER_FILE_PATH = "CUSTFILE.dat";
private static final String PROGRAM_NAME = "RISKSCOR";
private static final String RECOVERY_NEW_FILE_PATH = "RECVNEW.dat";
private static final String RISK_REPORT_FILE_PATH = "RISKRPT.dat";
private static final String SCORE_FILE_PATH = "SCORFILE.dat";
// Report header/footer lines (from copybooks RPTCOPY2 assumed)
    // Since copybooks are unresolved, we define minimal placeholders for report lines
    private final String rptProgram = "RISKSCOR";
private final String rptFooterLine = "END OF REPORT".concat(" ".repeat(124)); // padded to 137 chars
private final String rptSeparator = "-------------------------------------------------------------------------------" +;
private final String rptTitle = "RAPPORT CLASSIFICATION CREANCES BCT";
"-------------------------------------------------"; // 137 chars approx;
//;
//;
//;
// Constants;
// Customer and Score files are opened but not used in the provided logic beyond open/close;
// Error message and return code;
// File readers/writers;
// File status flags for open/read operations;
// LoanRecord;
// Report header/;
// Report lines;
// Statistics;
// Working storage classes;
// Working storage field for recovery found flag;
// Working storage variables;
private boolean custFsOk = false;
private boolean loanFsOk = false;
private boolean outFsOk = false;
private boolean recFsOkFlag = false;
private boolean rptFsOk = false;
private boolean scrFsOk = false;
private BufferedReader customerFileReader;
private BufferedReader loanFileReader;
private BufferedReader recoveryNewReader; // optional;
private BufferedReader scoreFileReader;
private BufferedWriter bctSubmissionWriter;
private BufferedWriter riskReportWriter;
private int rptPageNo = 1;
private int rptRunDate;
private int statProcessed = 0;
private int wsReturnCode = 0;
private LoanRecord loanRecord;
private Sqlca sqlca =;
private Sqlca sqlca = new Sqlca();
private String bctLine = "";
private String riskRptLine = "";
private String wsErrorMessage = "";
private String wsRecFs = "  "; //;
private String wsRecoveryFound = "N";
private WsBctRecord wsBctRecord =;
private WsBctRecord wsBctRecord = new WsBctRecord();
private WsControl wsControl =;
private WsControl wsControl = new WsControl();
private WsProvisions wsProvisions =;
private WsProvisions wsProvisions = new WsProvisions();
private WsRecoveryTable wsRecoveryTable =;
private WsRecoveryTable wsRecoveryTable = new WsRecoveryTable();
private WsSqlHost wsSqlHost =;
private WsSqlHost wsSqlHost = new WsSqlHost();

    Main entry point;
    public void main() {
        // Initialize program name and accept today's date
        // Accept WS-TODAY-DATE from DATE YYYYMMDD
        wsControl.wsTodayDate = getCurrentDateYYYYMMDD();

        openFiles();
        if (wsReturnCode != 0) {
            System.out.println("RISKSCOR ABEND: " + wsErrorMessage);
            System.exit(12);
        }

        loadRecoveryTable();

        initReport();

        while (!"Y".equals(wsControl.wsEndLoanFile)) {
            processPortfolio();
        }

        writeSummary();

        closeFiles();

        System.out.println("RISKSCOR COMPLETED.");
        System.out.println("  CLASS 1: " + wsProvisions.wsClass1Count);
        System.out.println("  CLASS 2: " + wsProvisions.wsClass2Count);
        System.out.println("  CLASS 3: " + wsProvisions.wsClass3Count);
        System.out.println("  CLASS 4: " + wsProvisions.wsClass4Count);
        System.out.println("  TOTAL PROV: " + formatBigDecimal(wsProvisions.wsTotalProvision));

        System.exit(0);
    }

    private void accumulatePortfolio() {
        wsProvisions.wsTotalOutstanding = wsProvisions.wsTotalOutstanding.add(loanRecord.getOutstanding());
        wsProvisions.wsTotalProvision = wsProvisions.wsTotalProvision.add(wsProvisions.wsRequiredProvision);

        switch (loanRecord.getLoanClass()) {
            case "1" -> {
                wsProvisions.wsClass1Count++;
                wsProvisions.wsClass1Outstanding = wsProvisions.wsClass1Outstanding.add(loanRecord.getOutstanding());
                wsProvisions.wsClass1Provision = wsProvisions.wsClass1Provision.add(wsProvisions.wsRequiredProvision);
            }
            case "2" -> {
                wsProvisions.wsClass2Count++;
                wsProvisions.wsClass2Outstanding = wsProvisions.wsClass2Outstanding.add(loanRecord.getOutstanding());
                wsProvisions.wsClass2Provision = wsProvisions.wsClass2Provision.add(wsProvisions.wsRequiredProvision);
            }
            case "3" -> {
                wsProvisions.wsClass3Count++;
                wsProvisions.wsClass3Outstanding = wsProvisions.wsClass3Outstanding.add(loanRecord.getOutstanding());
                wsProvisions.wsClass3Provision = wsProvisions.wsClass3Provision.add(wsProvisions.wsRequiredProvision);
            }
            case "4" -> {
                wsProvisions.wsClass4Count++;
                wsProvisions.wsClass4Outstanding = wsProvisions.wsClass4Outstanding.add(loanRecord.getOutstanding());
                wsProvisions.wsClass4Provision = wsProvisions.wsClass4Provision.add(wsProvisions.wsRequiredProvision);
            }
        }
    }

    private void checkRecoveryFlag() {
        wsRecoveryFound = "N";
        for (int i = 0; i < wsRecoveryTable.getCount(); i++) {
            if (wsRecoveryTable.getLoanId(i) == wsControl.wsCurrentLoanId) {
                wsRecoveryFound = "Y";
                break;
            }
        }
    }

    private void classifyLoan() {
        int daysPastDue = loanRecord.getDaysPastDue();
        if (daysPastDue <= 30) {
            loanRecord.setLoanClass("1");
            loanRecord.setLoanProvisionRate(BigDecimal.ZERO);
        } else if (daysPastDue <= 90) {
            loanRecord.setLoanClass("2");
            loanRecord.setLoanProvisionRate(new BigDecimal("20.0000"));
        } else if (daysPastDue <= 180) {
            loanRecord.setLoanClass("3");
            loanRecord.setLoanProvisionRate(new BigDecimal("50.0000"));
        } else {
            loanRecord.setLoanClass("4");
            loanRecord.setLoanProvisionRate(new BigDecimal("100.0000"));
        }
    }

    private void closeFiles() {
        closeQuietly(loanFileReader);
        closeQuietly(customerFileReader);
        closeQuietly(scoreFileReader);
        closeQuietly(riskReportWriter);
        closeQuietly(bctSubmissionWriter);
    }

    Utility methods;

    private static void closeQuietly(AutoCloseable c) {
        if (c != null) {
            try {
                c.close();
            } catch (Exception ignored) {
            }
        }
    }

    private void computeProvision() {
        BigDecimal outstanding = loanRecord.getOutstanding();
        BigDecimal rate = loanRecord.getLoanProvisionRate();
        // WS-REQUIRED-PROVISION = LOAN-OUTSTANDING * LOAN-PROVISION-RATE / 100 rounded half up
        BigDecimal provision = outstanding.multiply(rate).divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
        wsProvisions.wsRequiredProvision = provision;
        loanRecord.setLoanProvisionAmt(provision);
    }

    private static int getCurrentDateYYYYMMDD() {
        // Return current date as int YYYYMMDD
        java.time.LocalDate now = java.time.LocalDate.now();
        return now.getYear() * 10000 + now.getMonthValue() * 100 + now.getDayOfMonth();
    }

    private void initReport() {
        rptRunDate = wsControl.wsTodayDate;
        rptPageNo = 1;

        try {
            // Write main header line
            riskRptLine = formatReportHeader();
            riskReportWriter.write(riskRptLine);
            riskReportWriter.newLine();

            // Write sub header line
            riskRptLine = formatReportSubHeader();
            riskReportWriter.write(riskRptLine);
            riskReportWriter.newLine();

            // Write separator line
            riskRptLine = rptSeparator;
            riskReportWriter.write(riskRptLine);
            riskReportWriter.newLine();

            riskReportWriter.flush();
        } catch (IOException e) {
            // Ignore for now
        }
    }

    private void insertRiskHist() {
        // Move fields to SQL host variables
        wsSqlHost.wsSqlLoanId = wsControl.wsCurrentLoanId;
        wsSqlHost.wsSqlCustId = wsControl.wsCurrentCustId;
        wsSqlHost.wsSqlClass = loanRecord.getLoanClass();
        wsSqlHost.wsSqlPrevClass = wsControl.wsPrevClass;
        wsSqlHost.wsSqlOutstanding = loanRecord.getOutstanding();
        wsSqlHost.wsSqlProvision = wsProvisions.wsRequiredProvision;
        wsSqlHost.wsSqlDpd = loanRecord.getDaysPastDue();
        wsSqlHost.wsSqlDate = wsControl.wsTodayDate;

        // Embedded SQL insert is replaced by a comment and no actual DB call
        // If SQLCODE != 0, display error
        // Here, simulate success
    }

    private void loadRecoveryTable() {
        if (recFsOk()) {
            wsRecoveryTable.clear();
            wsControl.wsEndRecFile = "N";
            while (!"Y".equals(wsControl.wsEndRecFile) && wsRecoveryTable.getCount() < 200) {
                readRec();
            }
            closeQuietly(recoveryNewReader);
        }
    }

    private void openFiles() {
        try {
            // Open LOAN-FILE in I-O mode (read/write)
            loanFileReader = new BufferedReader(new FileReader(LOAN_FILE_PATH));
            loanFsOk = true;
        } catch (IOException e) {
            loanFsOk = false;
        }
        if (!loanFsOk) {
            wsReturnCode = 12;
            wsErrorMessage = "LOANFILE OPEN FAILED";
            return;
        }

        try {
            customerFileReader = new BufferedReader(new FileReader(CUSTOMER_FILE_PATH));
            custFsOk = true;
        } catch (IOException e) {
            custFsOk = false;
        }
        if (!custFsOk) {
            wsReturnCode = 12;
            wsErrorMessage = "CUSTFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            return;
        }

        try {
            scoreFileReader = new BufferedReader(new FileReader(SCORE_FILE_PATH));
            scrFsOk = true;
        } catch (IOException e) {
            scrFsOk = false;
        }
        if (!scrFsOk) {
            wsReturnCode = 12;
            wsErrorMessage = "SCORFILE OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            return;
        }

        try {
            recoveryNewReader = new BufferedReader(new FileReader(RECOVERY_NEW_FILE_PATH));
            wsRecFs = "00"; // simulate REC-FS-OK
            recFsOkFlag = true;
        } catch (IOException e) {
            // Recovery file is optional - tolerate missing
            wsRecFs = "  ";
            recFsOkFlag = false;
        }

        try {
            riskReportWriter = new BufferedWriter(new FileWriter(RISK_REPORT_FILE_PATH));
            rptFsOk = true;
        } catch (IOException e) {
            rptFsOk = false;
        }
        if (!rptFsOk) {
            wsReturnCode = 12;
            wsErrorMessage = "RISKRPT OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            closeQuietly(scoreFileReader);
            return;
        }

        try {
            bctSubmissionWriter = new BufferedWriter(new FileWriter(BCT_SUBMISSION_FILE_PATH));
            outFsOk = true;
        } catch (IOException e) {
            outFsOk = false;
        }
        if (!outFsOk) {
            wsReturnCode = 12;
            wsErrorMessage = "BCTSUBM OPEN FAILED";
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            closeQuietly(scoreFileReader);
            closeQuietly(riskReportWriter);
            return;
        }

        wsReturnCode = 0;

        // Read first loan record
        readNextLoan();
    }

    private static String padRight(String s, int n) {
        if (s.length() >= n) {
            return s.substring(0, n);
        }
        return s + " ".repeat(n - s.length());
    }

    private void processPortfolio() {
        if (!loanRecord.isActive() && !loanRecord.isRestructured()) {
            readNextLoan();
            return;
        }

        statProcessed++;

        wsControl.wsCurrentLoanId = loanRecord.getLoanId();
        wsControl.wsCurrentCustId = loanRecord.getCustId();
        wsControl.wsPrevClass = loanRecord.getLoanClass();

        classifyLoan();

        checkRecoveryFlag();

        computeProvision();

        updateLoanClass();

        insertRiskHist();

        accumulatePortfolio();

        writeBctRecord();

        readNextLoan();
    }

    private void readNextLoan() {
        try {
            String line = loanFileReader.readLine();
            if (line == null) {
                wsControl.wsEndLoanFile = "Y";
                loanRecord = null;
            } else {
                wsControl.wsEndLoanFile = "N";
                loanRecord = LoanRecord.fromFixedWidth(line);
            }
        } catch (IOException e) {
            wsControl.wsEndLoanFile = "Y";
            loanRecord = null;
        }
    }

    private void readRec() {
        try {
            String line = recoveryNewReader.readLine();
            if (line == null) {
                wsControl.wsEndRecFile = "Y";
            } else {
                wsRecoveryTable.addEntry(line);
            }
        } catch (IOException e) {
            wsControl.wsEndRecFile = "Y";
        }
    }

    2 chars, default spaces
    private boolean recFsOk() {
        return "00".equals(wsRecFs);
    }

    private void updateLoanClass() {
        // Rewrite loan record - in file-based system, this would update the record
        // Here, simulate by writing back to file or updating in-memory structure
        // Since we only have sequential read, we cannot rewrite in place easily
        // So this is a placeholder for actual file update logic
        // If rewrite fails, display error
        // For simulation, assume success
        // If failure:
        // System.err.println("LOAN REWRITE FAILED: " + wsControl.wsCurrentLoanId);
    }

    private void writeBctRecord() {
        wsBctRecord.bctReportDate = wsControl.wsTodayDate;
        wsBctRecord.bctLoanId = wsControl.wsCurrentLoanId;
        wsBctRecord.bctCustId = wsControl.wsCurrentCustId;
        wsBctRecord.bctClass = loanRecord.getLoanClass();
        wsBctRecord.bctOutstanding = loanRecord.getOutstanding();
        wsBctRecord.bctProvision = wsProvisions.wsRequiredProvision;
        wsBctRecord.bctDpd = loanRecord.getDaysPastDue();
        if ("Y".equals(wsRecoveryFound)) {
            wsBctRecord.bctRecoveryFlag = "REC";
        } else {
            wsBctRecord.bctRecoveryFlag = "NRC";
        }

        // Write BCT-LINE from WS-BCT-RECORD
        bctLine = wsBctRecord.formatRecord();
        try {
            bctSubmissionWriter.write(bctLine);
            bctSubmissionWriter.newLine();
            bctSubmissionWriter.flush();
        } catch (IOException e) {
            // Ignore for now
        }
    }

    private void writeSummary() {
        try {
            riskRptLine = rptSeparator;
            riskReportWriter.write(riskRptLine);
            riskReportWriter.newLine();

            riskRptLine = "CLASSE 1 (COURANTS) : CNT=" + wsProvisions.wsClass1Count
                    + " ENC=" + formatBigDecimal(wsProvisions.wsClass1Outstanding)
                    + " PROV=" + formatBigDecimal(wsProvisions.wsClass1Provision);
            riskReportWriter.write(padRight(riskRptLine, 137));
            riskReportWriter.newLine();

            riskRptLine = "CLASSE 2 (30-90J)   : CNT=" + wsProvisions.wsClass2Count
                    + " ENC=" + formatBigDecimal(wsProvisions.wsClass2Outstanding)
                    + " PROV=" + formatBigDecimal(wsProvisions.wsClass2Provision);
            riskReportWriter.write(padRight(riskRptLine, 137));
            riskReportWriter.newLine();

            riskRptLine = "CLASSE 3 (90-180J)  : CNT=" + wsProvisions.wsClass3Count
                    + " ENC=" + formatBigDecimal(wsProvisions.wsClass3Outstanding)
                    + " PROV=" + formatBigDecimal(wsProvisions.wsClass3Provision);
            riskReportWriter.write(padRight(riskRptLine, 137));
            riskReportWriter.newLine();

            riskRptLine = "CLASSE 4 (>180J)    : CNT=" + wsProvisions.wsClass4Count
                    + " ENC=" + formatBigDecimal(wsProvisions.wsClass4Outstanding)
                    + " PROV=" + formatBigDecimal(wsProvisions.wsClass4Provision);
            riskReportWriter.write(padRight(riskRptLine, 137));
            riskReportWriter.newLine();

            riskRptLine = "TOTAL PROVISIONS    : " + formatBigDecimal(wsProvisions.wsTotalProvision);
            riskReportWriter.write(padRight(riskRptLine, 137));
            riskReportWriter.newLine();

            riskRptLine = padRight(rptFooterLine, 137);
            riskReportWriter.write(riskRptLine);
            riskReportWriter.newLine();

            riskReportWriter.flush();
        } catch (IOException e) {
            // Ignore for now
        }
    }

    private static String formatBigDecimal(BigDecimal bd) {
        // Format BigDecimal as US style with dot decimal, no thousands separator, no leading zeros
        // Show 2 decimals fixed
        if (bd == null) {
            return "0.00";
        }
        return bd.setScale(2, RoundingMode.HALF_UP).toPlainString();
    }

    private String formatLoanRecord(LoanRecord rec) {
        char[] chars = rec.rawLine.toCharArray();
        CobolRecordRewrite.overwrite(chars, 33, 34, CobolRecordRewrite.formatDisplayString(rec.loanClass, 1));
        CobolRecordRewrite.overwrite(chars, 129, 140, CobolRecordRewrite.formatDecimal(rec.loanProvisionAmt, 9, 2));
        CobolRecordRewrite.overwrite(chars, 123, 129, CobolRecordRewrite.formatDecimal(rec.loanProvisionRate, 2, 4));
        return new String(chars);
    }

    private String formatReportHeader() {
        // Compose a header line of length 137 chars
        // Minimal implementation: program name + date + title truncated/padded
        StringBuilder sb = new StringBuilder(137);
        sb.append(rptProgram);
        sb.append(" ");
        sb.append(rptRunDate);
        sb.append(" ");
        sb.append(rptTitle);
        if (sb.length() > 137) {
            return sb.substring(0, 137);
        }
        return padRight(sb.toString(), 137);
    }

    private String formatReportSubHeader() {
        // Placeholder for sub header line, can be empty or fixed text
        String subHeader = "Portfolio Risk Classification Report";
        return padRight(subHeader, 137);
    }

    private LoanRecord parseLoanRecord(String line) {
        LoanRecord rec = new LoanRecord();
        rec.rawLine = line.length() >= 238
            ? line.substring(0, 238)
            : String.format("%-238s", line);
        rec.wsreLoanId = CobolRecordRewrite.parseDisplayDecimal(line, 0, 10, "9(10)");
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

    class representing LOAN-RECORD from LOANCOPY
    public static class LoanRecord {
        // Fields inferred from usage:
        // LOAN-ID: int (9(10))
        // LOAN-CUST-ID: int (9(8))
        // LOAN-CLASS: String (X(1))
        // LOAN-PROVISION-RATE: BigDecimal (9(5)V4 assumed from 20.0000 etc)
        // LOAN-PROVISION-AMT: BigDecimal (9(11)V99)
        // LOAN-OUTSTANDING: BigDecimal (9(11)V99)
        // LOAN-DAYS-PAST-DUE: int (9(4))
        // LOAN-ACTIVE: boolean (not explicit, assume from method)
        // LOAN-RESTRUCTURED: boolean (not explicit, assume from method)

        private int loanId;
        private int custId;
        private String loanClass;
        private BigDecimal loanProvisionRate = BigDecimal.ZERO;
        private BigDecimal loanProvisionAmt = BigDecimal.ZERO;
        private BigDecimal outstanding = BigDecimal.ZERO;
        private int daysPastDue;
        private boolean active;
        private boolean restructured;

        public static LoanRecord fromFixedWidth(String line) {
            LoanRecord lr = new LoanRecord();
            // Parse fixed width fields from line
            // Positions and lengths are assumed from PICs and usage:
            // LOAN-ID: pos 0-9 (10 chars)
            // LOAN-CUST-ID: pos 10-17 (8 chars)
            // LOAN-CLASS: pos 18 (1 char)
            // LOAN-PROVISION-RATE: not in file, set later
            // LOAN-PROVISION-AMT: not in file, set later
            // LOAN-OUTSTANDING: pos 19-31 (13 chars, 9(11)V99)
            // LOAN-DAYS-PAST-DUE: pos 32-35 (4 chars)
            // LOAN-ACTIVE: pos 36 (1 char) 'Y'/'N'
            // LOAN-RESTRUCTURED: pos 37 (1 char) 'Y'/'N'
            // These positions are assumed for demonstration; adjust as per actual copybook

            try {
                String loanIdStr = safeSubstring(line, 0, 10).trim();
                lr.loanId = Integer.parseInt(loanIdStr);
            } catch (Exception e) {
                lr.loanId = 0;
            }
            try {
                String custIdStr = safeSubstring(line, 10, 18).trim();
                lr.custId = Integer.parseInt(custIdStr);
            } catch (Exception e) {
                lr.custId = 0;
            }
            lr.loanClass = safeSubstring(line, 18, 19);
            try {
                String outstandingStr = safeSubstring(line, 19, 32).trim();
                // 9(11)V99 means 13 chars with implied decimal 2 places
                // Convert string to BigDecimal with 2 decimals implied
                lr.outstanding = parseBigDecimalImpliedDecimal(outstandingStr, 2);
            } catch (Exception e) {
                lr.outstanding = BigDecimal.ZERO;
            }
            try {
                String dpdStr = safeSubstring(line, 32, 36).trim();
                lr.daysPastDue = Integer.parseInt(dpdStr);
            } catch (Exception e) {
                lr.daysPastDue = 0;
            }
            String activeFlag = safeSubstring(line, 36, 37);
            lr.active = "Y".equalsIgnoreCase(activeFlag);
            String restructFlag = safeSubstring(line, 37, 38);
            lr.restructured = "Y".equalsIgnoreCase(restructFlag);

            return lr;
        }

        public int getLoanId() {
            return loanId;
        }

        public int getCustId() {
            return custId;
        }

        public String getLoanClass() {
            return loanClass;
        }

        public void setLoanClass(String loanClass) {
            this.loanClass = loanClass;
        }

        public BigDecimal getLoanProvisionRate() {
            return loanProvisionRate;
        }

        public void setLoanProvisionRate(BigDecimal loanProvisionRate) {
            this.loanProvisionRate = loanProvisionRate;
        }

        public BigDecimal getLoanProvisionAmt() {
            return loanProvisionAmt;
        }

        public void setLoanProvisionAmt(BigDecimal loanProvisionAmt) {
            this.loanProvisionAmt = loanProvisionAmt;
        }

        public BigDecimal getOutstanding() {
            return outstanding;
        }

        public int getDaysPastDue() {
            return daysPastDue;
        }

        public boolean isActive() {
            return active;
        }

        public boolean isRestructured() {
            return restructured;
        }

        private static String safeSubstring(String s, int start, int end) {
            if (s == null) return "";
            if (start >= s.length()) return "";
            if (end > s.length()) end = s.length();
            return s.substring(start, end);
        }

        private static BigDecimal parseBigDecimalImpliedDecimal(String s, int decimals) {
            if (s == null || s.isEmpty()) {
                return BigDecimal.ZERO;
            }
            // Remove leading zeros
            s = s.replaceFirst("^0+(?!$)", "");
            if (s.isEmpty()) {
                return BigDecimal.ZERO;
            }
            BigDecimal bd = new BigDecimal(s);
            return bd.movePointLeft(decimals);
        }
    }

    private static class Sqlca {
        String sqlcaid;
        int sqlcabc;
        int sqlcode;
        Sqlerrm sqlerrm = new Sqlerrm();
        String sqlerrp;
        int[] sqlerrd = new int[6];
        String sqlwarn0;
        String sqlext;

        static class Sqlerrm {
            int sqlerrml;
            String sqlerrmc;
        }
    }

    private static class WsBctRecord {
        int bctBankCode = 1234;
        // filler 2 spaces
        int bctReportDate;
        // filler 2 spaces
        int bctLoanId;
        // filler 2 spaces
        int bctCustId;
        // filler 2 spaces
        String bctClass;
        // filler 2 spaces
        BigDecimal bctOutstanding;
        // filler 2 spaces
        BigDecimal bctProvision;
        // filler 2 spaces
        int bctDpd;
        // filler 2 spaces
        String bctRecoveryFlag;
        // filler 124 spaces

        String formatRecord() {
            // Fixed width 200 chars
            // Format each field with padding as per PIC
            // BCT-BANK-CODE: 9(4)
            // filler: X(2)
            // BCT-REPORT-DATE: 9(8)
            // filler: X(2)
            // BCT-LOAN-ID: 9(10)
            // filler: X(2)
            // BCT-CUST-ID: 9(8)
            // filler: X(2)
            // BCT-CLASS: X(1)
            // filler: X(2)
            // BCT-OUTSTANDING: 9(11)V99 (13 chars)
            // filler: X(2)
            // BCT-PROVISION: 9(11)V99 (13 chars)
            // filler: X(2)
            // BCT-DPD: 9(4)
            // filler: X(2)
            // BCT-RECOVERY-FLAG: X(3)
            // filler: X(124)

            StringBuilder sb = new StringBuilder(200);
            sb.append(padLeftZeros(Integer.toString(bctBankCode), 4));
            sb.append("  ");
            sb.append(padLeftZeros(Integer.toString(bctReportDate), 8));
            sb.append("  ");
            sb.append(padLeftZeros(Integer.toString(bctLoanId), 10));
            sb.append("  ");
            sb.append(padLeftZeros(Integer.toString(bctCustId), 8));
            sb.append("  ");
            sb.append(padRight(bctClass != null ? bctClass : " ", 1));
            sb.append("  ");
            sb.append(padLeftZeros(formatBigDecimalNoDecimalPoint(bctOutstanding, 13), 13));
            sb.append("  ");
            sb.append(padLeftZeros(formatBigDecimalNoDecimalPoint(bctProvision, 13), 13));
            sb.append("  ");
            sb.append(padLeftZeros(Integer.toString(bctDpd), 4));
            sb.append("  ");
            sb.append(padRight(bctRecoveryFlag != null ? bctRecoveryFlag : "   ", 3));
            sb.append(" ".repeat(124));
            return sb.toString();
        }

        private static String padLeftZeros(String s, int n) {
            if (s == null) s = "";
            if (s.length() >= n) {
                return s.substring(0, n);
            }
            return "0".repeat(n - s.length()) + s;
        }

        private static String formatBigDecimalNoDecimalPoint(BigDecimal bd, int totalLength) {
            // Convert BigDecimal with 2 decimals implied to string without decimal point
            // e.g. 1234.56 -> "000000123456"
            if (bd == null) {
                return "0".repeat(totalLength);
            }
            BigDecimal scaled = bd.setScale(2, RoundingMode.HALF_UP);
            String plain = scaled.movePointRight(2).toPlainString();
            if (plain.length() > totalLength) {
                return plain.substring(plain.length() - totalLength);
            }
            return "0".repeat(totalLength - plain.length()) + plain;
        }
    }

    private static class WsControl {
        int wsTodayDate = 0;
        String wsEndLoanFile = "N";
        String wsEndRecFile = "N";
        int wsCurrentLoanId = 0;
        int wsCurrentCustId = 0;
        String wsPrevClass = " ";
    }

    private static class WsProvisions {
        BigDecimal wsRequiredProvision = BigDecimal.ZERO;
        BigDecimal wsClass1Outstanding = BigDecimal.ZERO;
        BigDecimal wsClass2Outstanding = BigDecimal.ZERO;
        BigDecimal wsClass3Outstanding = BigDecimal.ZERO;
        BigDecimal wsClass4Outstanding = BigDecimal.ZERO;
        int wsClass1Count = 0;
        int wsClass2Count = 0;
        int wsClass3Count = 0;
        int wsClass4Count = 0;
        BigDecimal wsClass1Provision = BigDecimal.ZERO;
        BigDecimal wsClass2Provision = BigDecimal.ZERO;
        BigDecimal wsClass3Provision = BigDecimal.ZERO;
        BigDecimal wsClass4Provision = BigDecimal.ZERO;
        BigDecimal wsTotalProvision = BigDecimal.ZERO;
        BigDecimal wsTotalOutstanding = BigDecimal.ZERO;
    }

    private static class WsRecoveryTable {
        private static final int MAX_ENTRIES = 200;
        private final int[] wsreLoanId = new int[MAX_ENTRIES];
        private final String[] wsreActionCode = new String[MAX_ENTRIES];
        private int wsRecCount = 0;

        void clear() {
            wsRecCount = 0;
            Arrays.fill(wsreLoanId, 0);
            Arrays.fill(wsreActionCode, null);
        }

        void addEntry(String line) {
            if (wsRecCount >= MAX_ENTRIES) {
                return;
            }
            // Parse fixed width line for REC-LOAN-ID (9(10)) and REC-ACTION-TYPE (X(3))
            // Assuming REC-LOAN-ID at positions 0-9 (10 chars), REC-ACTION-TYPE at 10-12 (3 chars)
            String loanIdStr = safeSubstring(line, 0, 10).trim();
            String actionCode = safeSubstring(line, 10, 13).trim();
            int loanId = 0;
            try {
                loanId = Integer.parseInt(loanIdStr);
            } catch (NumberFormatException ignored) {
            }
            wsreLoanId[wsRecCount] = loanId;
            wsreActionCode[wsRecCount] = actionCode;
            wsRecCount++;
        }

        int getCount() {
            return wsRecCount;
        }

        int getLoanId(int index) {
            if (index < 0 || index >= wsRecCount) {
                return 0;
            }
            return wsreLoanId[index];
        }

        private static String safeSubstring(String s, int start, int end) {
            if (s == null) return "";
            if (start >= s.length()) return "";
            if (end > s.length()) end = s.length();
            return s.substring(start, end);
        }
    }

    private static class WsSqlHost {
        int wsSqlLoanId;
        int wsSqlCustId;
        String wsSqlClass;
        String wsSqlPrevClass;
        BigDecimal wsSqlOutstanding;
        BigDecimal wsSqlProvision;
        int wsSqlDpd;
        int wsSqlDate;
    }

}
