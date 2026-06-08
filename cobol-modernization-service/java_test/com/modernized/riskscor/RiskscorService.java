package com.modernized.riskscor;

import java.io.*;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.file.*;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.*;


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


public class RiskscorService {

    private static final DateTimeFormatter DATE_FORMATTER = DateTimeFormatter.ofPattern("yyyyMMdd");
    private static final int BANK_CODE = 1234;
    private static final String PROGRAM_NAME = "RISKSCOR";

    // File paths
    private String loanFilePath = "LOANFILE.dat";
    private String customerFilePath = "CUSTFILE.dat";
    private String scoreFilePath = "SCORFILE.dat";
    private String recoveryFilePath = "RECVNEW.dat";
    private String riskReportPath = "RISKRPT.dat";
    private String bctSubmissionPath = "BCTSUBM.dat";

    // File status tracking
    private String wsLoanFs = "  ";
    private String wsCustFs = "  ";
    private String wsScrFs = "  ";
    private String wsRecFs = "  ";
    private String wsRptFs = "  ";
    private String wsOutFs = "  ";

    // Error handling
    private int wsReturnCode = 0;
    private String wsErrorMessage = "";
    private String wsProgramName = "";

    // Control fields
    private int wsTodayDate = 0;
    private String wsEndLoanFile = "N";
    private String wsEndRecFile = "N";
    private int wsCurrentLoanId = 0;
    private int wsCurrentCustId = 0;
    private String wsPrevClass = " ";

    // Recovery table
    private static class RecoveryEntry {
        int loanId;
        String actionCode;
    }
    private List<RecoveryEntry> wsRecoveryTable = new ArrayList<>();
    private int wsRecCount = 0;
    private String wsRecoveryFound = "N";

    // Provision accumulators
    private BigDecimal wsRequiredProvision = BigDecimal.ZERO;
    private BigDecimal wsClass1Outstanding = BigDecimal.ZERO;
    private BigDecimal wsClass2Outstanding = BigDecimal.ZERO;
    private BigDecimal wsClass3Outstanding = BigDecimal.ZERO;
    private BigDecimal wsClass4Outstanding = BigDecimal.ZERO;
    private int wsClass1Count = 0;
    private int wsClass2Count = 0;
    private int wsClass3Count = 0;
    private int wsClass4Count = 0;
    private BigDecimal wsClass1Provision = BigDecimal.ZERO;
    private BigDecimal wsClass2Provision = BigDecimal.ZERO;
    private BigDecimal wsClass3Provision = BigDecimal.ZERO;
    private BigDecimal wsClass4Provision = BigDecimal.ZERO;
    private BigDecimal wsTotalProvision = BigDecimal.ZERO;
    private BigDecimal wsTotalOutstanding = BigDecimal.ZERO;

    // Statistics
    private int statProcessed = 0;

    // Report fields
    private String rptProgram = "";
    private int rptRunDate = 0;
    private int rptPageNo = 1;
    private String rptTitle = "";

    // SQL host variables (commented EXEC SQL section)
    private int wsSqlLoanId = 0;
    private int wsSqlCustId = 0;
    private String wsSqlClass = " ";
    private String wsSqlPrevClass = " ";
    private BigDecimal wsSqlOutstanding = BigDecimal.ZERO;
    private BigDecimal wsSqlProvision = BigDecimal.ZERO;
    private int wsSqlDpd = 0;
    private int wsSqlDate = 0;

    // File handles
    private BufferedReader loanReader;
    private BufferedReader recoveryReader;
    private BufferedWriter riskReportWriter;
    private BufferedWriter bctSubmissionWriter;

    // Current loan record
    private LoanRecord currentLoan;

    public void execute() {
        mainProcess();
    }

    private void mainProcess() {
        wsProgramName = PROGRAM_NAME;
        wsTodayDate = Integer.parseInt(LocalDate.now().format(DATE_FORMATTER));
        
        openFiles();
        if (wsReturnCode != 0) {
            System.out.println("RISKSCOR ABEND: " + wsErrorMessage);
            System.exit(12);
        }

        loadRecoveryTable();
        initReport();
        
        while (!wsEndLoanFile.equals("Y")) {
            processPortfolio();
        }
        
        writeSummary();
        closeFiles();
        
        System.out.println("RISKSCOR COMPLETED.");
        System.out.println("  CLASS 1: " + wsClass1Count);
        System.out.println("  CLASS 2: " + wsClass2Count);
        System.out.println("  CLASS 3: " + wsClass3Count);
        System.out.println("  CLASS 4: " + wsClass4Count);
        System.out.println("  TOTAL PROV: " + formatAmount(wsTotalProvision));
    }

    private void openFiles() {
        try {
            loanReader = Files.newBufferedReader(Paths.get(loanFilePath));
            wsLoanFs = "00";
            readNextLoan();
        } catch (Exception e) {
            wsReturnCode = 12;
            wsErrorMessage = "LOANFILE OPEN FAILED";
            wsLoanFs = "35";
            return;
        }

        try {
            wsCustFs = "00";
        } catch (Exception e) {
            wsReturnCode = 12;
            wsErrorMessage = "CUSTFILE OPEN FAILED";
            wsCustFs = "35";
            closeQuietly(loanReader);
            return;
        }

        try {
            wsScrFs = "00";
        } catch (Exception e) {
            wsReturnCode = 12;
            wsErrorMessage = "SCORFILE OPEN FAILED";
            wsScrFs = "35";
            closeQuietly(loanReader);
            return;
        }

        try {
            recoveryReader = Files.newBufferedReader(Paths.get(recoveryFilePath));
            wsRecFs = "00";
        } catch (Exception e) {
            wsRecFs = "35";
        }

        try {
            riskReportWriter = Files.newBufferedWriter(Paths.get(riskReportPath));
            wsRptFs = "00";
        } catch (Exception e) {
            wsReturnCode = 12;
            wsErrorMessage = "RISKRPT OPEN FAILED";
            wsRptFs = "35";
            closeQuietly(loanReader);
            return;
        }

        try {
            bctSubmissionWriter = Files.newBufferedWriter(Paths.get(bctSubmissionPath));
            wsOutFs = "00";
        } catch (Exception e) {
            wsReturnCode = 12;
            wsErrorMessage = "BCTSUBM OPEN FAILED";
            wsOutFs = "35";
            closeQuietly(loanReader);
            closeQuietly(riskReportWriter);
            return;
        }

        wsReturnCode = 0;
    }

    private void loadRecoveryTable() {
        if (!"00".equals(wsRecFs)) {
            return;
        }
        
        while (!"Y".equals(wsEndRecFile) && wsRecCount < 200) {
            readRecovery();
        }
        
        closeQuietly(recoveryReader);
    }

    private void readRecovery() {
        try {
            String line = recoveryReader.readLine();
            if (line == null) {
                wsEndRecFile = "Y";
                return;
            }
            
            RecoveryEntry entry = new RecoveryEntry();
            entry.loanId = parseInteger(line.substring(12, 22).trim());
            entry.actionCode = line.substring(50, 53).trim();
            
            wsRecoveryTable.add(entry);
            wsRecCount++;
        } catch (Exception e) {
            wsEndRecFile = "Y";
        }
    }

    private void initReport() {
        rptProgram = PROGRAM_NAME;
        rptRunDate = wsTodayDate;
        rptTitle = "RAPPORT CLASSIFICATION CREANCES BCT";
        rptPageNo = 1;
        
        try {
            writeReportLine(formatMainHeader());
            writeReportLine(formatSubHeader());
            writeReportLine(formatSeparator());
        } catch (IOException e) {
            // Report write failure
        }
    }

    private void processPortfolio() {
        if (currentLoan == null || (!currentLoan.isActive() && !currentLoan.isRestructured())) {
            readNextLoan();
            return;
        }
        
        statProcessed++;
        wsCurrentLoanId = currentLoan.loanId;
        wsCurrentCustId = currentLoan.custId;
        wsPrevClass = currentLoan.loanClass;
        
        classifyLoan();
        checkRecoveryFlag();
        computeProvision();
        updateLoanClass();
        insertRiskHistory();
        accumulatePortfolio();
        writeBctRecord();
        readNextLoan();
    }

    private void classifyLoan() {
        int dpd = currentLoan.daysPastDue;
        
        if (dpd <= 30) {
            currentLoan.loanClass = "1";
            currentLoan.provisionRate = BigDecimal.ZERO;
        } else if (dpd <= 90) {
            currentLoan.loanClass = "2";
            currentLoan.provisionRate = new BigDecimal("20.0000");
        } else if (dpd <= 180) {
            currentLoan.loanClass = "3";
            currentLoan.provisionRate = new BigDecimal("50.0000");
        } else {
            currentLoan.loanClass = "4";
            currentLoan.provisionRate = new BigDecimal("100.0000");
        }
    }

    private void checkRecoveryFlag() {
        wsRecoveryFound = "N";
        
        for (RecoveryEntry entry : wsRecoveryTable) {
            if (entry.loanId == wsCurrentLoanId) {
                wsRecoveryFound = "Y";
                break;
            }
        }
    }

    private void computeProvision() {
        BigDecimal outstandingBd = currentLoan.outstanding;
        BigDecimal rateBd = currentLoan.provisionRate;
        
        wsRequiredProvision = outstandingBd.multiply(rateBd)
            .divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
        
        // Apply PIC 9(11)V99 storage constraint
        wsRequiredProvision = applyPicConstraint(wsRequiredProvision, 11, 2);
        
        currentLoan.provisionAmt = wsRequiredProvision;
    }

    private void updateLoanClass() {
        // REWRITE loan record - would update file in real implementation
    }

    private void insertRiskHistory() {
        wsSqlLoanId = wsCurrentLoanId;
        wsSqlCustId = wsCurrentCustId;
        wsSqlClass = currentLoan.loanClass;
        wsSqlPrevClass = wsPrevClass;
        wsSqlOutstanding = currentLoan.outstanding;
        wsSqlProvision = wsRequiredProvision;
        wsSqlDpd = currentLoan.daysPastDue;
        wsSqlDate = wsTodayDate;
        
        // EXEC SQL INSERT commented out in source - no actual DB operation
    }

    private void accumulatePortfolio() {
        wsTotalOutstanding = wsTotalOutstanding.add(currentLoan.outstanding);
        wsTotalProvision = wsTotalProvision.add(wsRequiredProvision);
        
        String loanClass = currentLoan.loanClass;
        
        if ("1".equals(loanClass)) {
            wsClass1Count++;
            wsClass1Outstanding = wsClass1Outstanding.add(currentLoan.outstanding);
            wsClass1Provision = wsClass1Provision.add(wsRequiredProvision);
        } else if ("2".equals(loanClass)) {
            wsClass2Count++;
            wsClass2Outstanding = wsClass2Outstanding.add(currentLoan.outstanding);
            wsClass2Provision = wsClass2Provision.add(wsRequiredProvision);
        } else if ("3".equals(loanClass)) {
            wsClass3Count++;
            wsClass3Outstanding = wsClass3Outstanding.add(currentLoan.outstanding);
            wsClass3Provision = wsClass3Provision.add(wsRequiredProvision);
        } else if ("4".equals(loanClass)) {
            wsClass4Count++;
            wsClass4Outstanding = wsClass4Outstanding.add(currentLoan.outstanding);
            wsClass4Provision = wsClass4Provision.add(wsRequiredProvision);
        }
    }

    private void writeBctRecord() {
        try {
            String recoveryFlag = "Y".equals(wsRecoveryFound) ? "REC" : "NRC";
            
            String bctLine = String.format("%04d  %08d  %010d  %08d  %1s  %s  %s  %04d  %3s%124s",
                BANK_CODE,
                wsTodayDate,
                wsCurrentLoanId,
                wsCurrentCustId,
                currentLoan.loanClass,
                formatBigDecimal(currentLoan.outstanding, 11, 2),
                formatBigDecimal(wsRequiredProvision, 11, 2),
                currentLoan.daysPastDue,
                recoveryFlag,
                "");
            
            bctSubmissionWriter.write(bctLine);
            bctSubmissionWriter.newLine();
        } catch (IOException e) {
            // BCT write failure
        }
    }

    private void writeSummary() {
        try {
            writeReportLine(formatSeparator());
            writeReportLine("CLASSE 1 (COURANTS) : CNT=" + wsClass1Count +
                " ENC=" + formatAmount(wsClass1Outstanding) +
                " PROV=" + formatAmount(wsClass1Provision));
            writeReportLine("CLASSE 2 (30-90J)   : CNT=" + wsClass2Count +
                " ENC=" + formatAmount(wsClass2Outstanding) +
                " PROV=" + formatAmount(wsClass2Provision));
            writeReportLine("CLASSE 3 (90-180J)  : CNT=" + wsClass3Count +
                " ENC=" + formatAmount(wsClass3Outstanding) +
                " PROV=" + formatAmount(wsClass3Provision));
            writeReportLine("CLASSE 4 (>180J)    : CNT=" + wsClass4Count +
                " ENC=" + formatAmount(wsClass4Outstanding) +
                " PROV=" + formatAmount(wsClass4Provision));
            writeReportLine("TOTAL PROVISIONS    : " + formatAmount(wsTotalProvision));
            writeReportLine(formatFooter());
        } catch (IOException e) {
            // Summary write failure
        }
    }

    private void closeFiles() {
        closeQuietly(loanReader);
        closeQuietly(riskReportWriter);
        closeQuietly(bctSubmissionWriter);
    }

    private void readNextLoan() {
        try {
            String line = loanReader.readLine();
            if (line == null) {
                wsEndLoanFile = "Y";
                currentLoan = null;
                return;
            }
            
            currentLoan = parseLoanRecord(line);
            wsLoanFs = "00";
        } catch (Exception e) {
            wsEndLoanFile = "Y";
            currentLoan = null;
        }
    }

    private LoanRecord parseLoanRecord(String line) {
        LoanRecord rec = new LoanRecord();
        rec.rawLine = line.length() >= 238
            ? line.substring(0, 238)
            : String.format("%-238s", line);
        rec.loanId = CobolRecordRewrite.parseDisplayDecimal(line, 0, 10, "9(10)").intValue();
        rec.custId = CobolRecordRewrite.parseDisplayDecimal(line, 10, 18, "9(8)").intValue();
        rec.loanStatus = CobolRecordRewrite.parseString(line, 31, 33);
        rec.loanClass = CobolRecordRewrite.parseString(line, 33, 34);
        rec.outstanding = CobolRecordRewrite.parseDisplayDecimal(line, 47, 60, "9(11)V99");
        rec.daysPastDue = CobolRecordRewrite.parseDisplayDecimal(line, 116, 120, "9(4)").intValue();
        rec.provisionRate = CobolRecordRewrite.parseDisplayDecimal(line, 123, 129, "9(2)V9(4)");
        rec.provisionAmt = CobolRecordRewrite.parseDisplayDecimal(line, 129, 140, "9(9)V99");
        return rec;
    }

    private String formatMainHeader() {
        return String.format("          ACME BANK SA     %8s     PAGE: %5d%73s",
            rptProgram, rptPageNo, "");
    }

    private String formatSubHeader() {
        return String.format("               %60s     DATE: %08d%43s",
            rptTitle, rptRunDate, "");
    }

    private String formatSeparator() {
        return "=".repeat(137);
    }

    private String formatFooter() {
        return " ".repeat(137);
    }

    private void writeReportLine(String line) throws IOException {
        riskReportWriter.write(padRight(line, 137));
        riskReportWriter.newLine();
    }

    private String formatAmount(BigDecimal amount) {
        return formatBigDecimal(amount, 13, 2);
    }

    private String formatBigDecimal(BigDecimal value, int intDigits, int decDigits) {
        BigDecimal scaled = value.setScale(decDigits, RoundingMode.HALF_UP);
        String[] parts = scaled.toPlainString().split("\\.");
        String intPart = parts[0];
        String decPart = parts.length > 1 ? parts[1] : "00";
        
        // Pad decimal part
        while (decPart.length() < decDigits) {
            decPart += "0";
        }
        
        // Apply comma thousands separator
        StringBuilder formatted = new StringBuilder();
        int len = intPart.length();
        for (int i = 0; i < len; i++) {
            if (i > 0 && (len - i) % 3 == 0) {
                formatted.append(',');
            }
            formatted.append(intPart.charAt(i));
        }
        
        return formatted.toString() + "." + decPart;
    }

    private BigDecimal applyPicConstraint(BigDecimal value, int intDigits, int decDigits) {
        BigDecimal maxValue = new BigDecimal("9".repeat(intDigits) + "." + "9".repeat(decDigits));
        if (value.compareTo(maxValue) > 0) {
            return maxValue;
        }
        return value.setScale(decDigits, RoundingMode.HALF_UP);
    }

    private int parseInteger(String s) {
        if (s == null || s.isEmpty()) return 0;
        try {
            return Integer.parseInt(s);
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private BigDecimal parseBigDecimal(String s, int scale) {
        if (s == null || s.isEmpty()) return BigDecimal.ZERO;
        try {
            BigDecimal bd = new BigDecimal(s);
            return bd.setScale(scale, RoundingMode.HALF_UP);
        } catch (NumberFormatException e) {
            return BigDecimal.ZERO;
        }
    }

    private String padRight(String s, int length) {
        if (s.length() >= length) return s.substring(0, length);
        return s + " ".repeat(length - s.length());
    }

    private void closeQuietly(Closeable closeable) {
        if (closeable != null) {
            try {
                closeable.close();
            } catch (IOException e) {
                // Ignore
            }
        }
    }

    private String formatLoanRecord(LoanRecord rec) {
        char[] chars = rec.rawLine.toCharArray();
        CobolRecordRewrite.overwrite(chars, 33, 34, CobolRecordRewrite.formatDisplayString(rec.loanClass, 1));
        CobolRecordRewrite.overwrite(chars, 129, 140, CobolRecordRewrite.formatDecimal(rec.provisionAmt, 9, 2));
        CobolRecordRewrite.overwrite(chars, 123, 129, CobolRecordRewrite.formatDecimal(rec.provisionRate, 2, 4));
        return new String(chars);
    }

    private static class LoanRecord {
        String rawLine;
        int loanId;
        int custId;
        String loanType;
        String loanStatus;
        String loanClass;
        BigDecimal originalAmt = BigDecimal.ZERO;
        BigDecimal outstanding = BigDecimal.ZERO;
        int daysPastDue;
        BigDecimal provisionRate = BigDecimal.ZERO;
        BigDecimal provisionAmt = BigDecimal.ZERO;
        
        boolean isActive() {
            return "AC".equals(loanStatus);
        }
        
        boolean isRestructured() {
            return "RS".equals(loanStatus);
        }
    }
}


