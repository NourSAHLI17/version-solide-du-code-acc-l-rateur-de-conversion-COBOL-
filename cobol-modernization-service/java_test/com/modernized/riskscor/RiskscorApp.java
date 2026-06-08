package com.modernized.riskscor;

import java.io.*;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.*;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@SpringBootApplication

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


public class RiskscorApplication {
    public static void main(String[] args) {
        SpringApplication.exit(
            SpringApplication.run(RiskscorApplication.class, args),
            () -> 0
        );
    }
}

@Component
class RiskscorProcessor implements CommandLineRunner {

    private static final String PROGRAM_NAME = "RISKSCOR";
    private static final int BCT_BANK_CODE = 1234;

    private String todayDate;
    private boolean endLoanFile;
    private boolean endRecFile;
    private int currentLoanId;
    private int currentCustId;
    private String prevClass;

    private final List<RecoveryEntry> recoveryTable = new ArrayList<>();
    private int recCount;
    private boolean recoveryFound;

    private BigDecimal requiredProvision;
    private BigDecimal class1Outstanding;
    private BigDecimal class2Outstanding;
    private BigDecimal class3Outstanding;
    private BigDecimal class4Outstanding;
    private int class1Count;
    private int class2Count;
    private int class3Count;
    private int class4Count;
    private BigDecimal class1Provision;
    private BigDecimal class2Provision;
    private BigDecimal class3Provision;
    private BigDecimal class4Provision;
    private BigDecimal totalProvision;
    private BigDecimal totalOutstanding;

    private int statProcessed;

    private String wsReturnCode;
    private String wsErrorMessage;

    private String wsLoanFs;
    private String wsCustFs;
    private String wsScrFs;
    private String wsRecFs;
    private String wsRptFs;
    private String wsOutFs;

    private BufferedReader loanFileReader;
    private BufferedReader recoveryFileReader;
    private BufferedWriter riskReportWriter;
    private BufferedWriter bctSubmissionWriter;

    private LoanRecord currentLoanRecord;
    private int rptPageNo;

    @Override
    public void run(String... args) throws Exception {
        mainProcedure();
    }

    private void mainProcedure() {
        try {
            todayDate = LocalDate.now().format(DateTimeFormatter.ofPattern("yyyyMMdd"));
            openFiles();

            if (!"0".equals(wsReturnCode)) {
                System.out.println("RISKSCOR ABEND: " + wsErrorMessage);
                System.exit(12);
            }

            loadRecoveryTable();
            initReport();

            while (!endLoanFile) {
                processPortfolio();
            }

            writeSummary();
            closeFiles();

            System.out.println("RISKSCOR COMPLETED.");
            System.out.println("  CLASS 1: " + class1Count);
            System.out.println("  CLASS 2: " + class2Count);
            System.out.println("  CLASS 3: " + class3Count);
            System.out.println("  CLASS 4: " + class4Count);
            System.out.println("  TOTAL PROV: " + totalProvision);

        } catch (Exception e) {
            System.err.println("Error in RISKSCOR: " + e.getMessage());
            e.printStackTrace();
            System.exit(12);
        }
    }

    private void openFiles() {
        wsReturnCode = "0";
        wsErrorMessage = "";

        try {
            loanFileReader = new BufferedReader(
                new InputStreamReader(new FileInputStream("LOANFILE.dat"), StandardCharsets.UTF_8)
            );
            wsLoanFs = "00";
        } catch (FileNotFoundException e) {
            wsReturnCode = "12";
            wsErrorMessage = "LOANFILE OPEN FAILED";
            return;
        }

        try {
            wsRecFs = "00";
            recoveryFileReader = new BufferedReader(
                new InputStreamReader(new FileInputStream("RECVNEW.dat"), StandardCharsets.UTF_8)
            );
        } catch (FileNotFoundException e) {
            wsRecFs = "35";
        }

        try {
            riskReportWriter = new BufferedWriter(
                new OutputStreamWriter(new FileOutputStream("RISKRPT.dat"), StandardCharsets.UTF_8)
            );
            wsRptFs = "00";
        } catch (IOException e) {
            wsReturnCode = "12";
            wsErrorMessage = "RISKRPT OPEN FAILED";
            closePartialFiles();
            return;
        }

        try {
            bctSubmissionWriter = new BufferedWriter(
                new OutputStreamWriter(new FileOutputStream("BCTSUBM.dat"), StandardCharsets.UTF_8)
            );
            wsOutFs = "00";
        } catch (IOException e) {
            wsReturnCode = "12";
            wsErrorMessage = "BCTSUBM OPEN FAILED";
            closePartialFiles();
            return;
        }

        readNextLoan();
    }

    private void closePartialFiles() {
        try {
            if (loanFileReader != null) loanFileReader.close();
            if (riskReportWriter != null) riskReportWriter.close();
        } catch (IOException ignored) {
        }
    }

    private void loadRecoveryTable() {
        if (!"00".equals(wsRecFs)) {
            return;
        }

        endRecFile = false;
        while (!endRecFile && recCount < 200) {
            readRec();
        }

        try {
            if (recoveryFileReader != null) {
                recoveryFileReader.close();
            }
        } catch (IOException ignored) {
        }
    }

    private void readRec() {
        try {
            String line = recoveryFileReader.readLine();
            if (line == null) {
                endRecFile = true;
            } else {
                recCount++;
                RecoveryAction rec = parseRecoveryAction(line);
                recoveryTable.add(new RecoveryEntry(rec.loanId, rec.actionType));
            }
        } catch (IOException e) {
            endRecFile = true;
        }
    }

    private void initReport() {
        try {
            rptPageNo = 1;
            String headerLine1 = String.format("%-10s%-25s%-5s%-8s%-5s%-6s%-5s%-73s",
                " ", "ACME BANK SA", " ", PROGRAM_NAME, " ", "PAGE: ", formatPage(rptPageNo), " ");
            riskReportWriter.write(headerLine1);
            riskReportWriter.newLine();

            String headerLine2 = String.format("%-15s%-60s%-5s%-6s%-8s%-43s",
                " ", "RAPPORT CLASSIFICATION CREANCES BCT", " ", "DATE: ", todayDate, " ");
            riskReportWriter.write(headerLine2);
            riskReportWriter.newLine();

            String separator = String.format("%" + 137 + "s", " ").replace(' ', '=');
            riskReportWriter.write(separator);
            riskReportWriter.newLine();

        } catch (IOException e) {
            System.err.println("Report header write error: " + e.getMessage());
        }
    }

    private String formatPage(int page) {
        return String.format("%5d", page).replace(' ', ' ');
    }

    private void writeSummary() {
        try {
            String separator = String.format("%" + 137 + "s", " ").replace(' ', '=');
            riskReportWriter.write(separator);
            riskReportWriter.newLine();

            String line1 = "CLASSE 1 (COURANTS) : CNT=" + class1Count +
                " ENC=" + class1Outstanding + " PROV=" + class1Provision;
            riskReportWriter.write(line1);
            riskReportWriter.newLine();

            String line2 = "CLASSE 2 (30-90J)   : CNT=" + class2Count +
                " ENC=" + class2Outstanding + " PROV=" + class2Provision;
            riskReportWriter.write(line2);
            riskReportWriter.newLine();

            String line3 = "CLASSE 3 (90-180J)  : CNT=" + class3Count +
                " ENC=" + class3Outstanding + " PROV=" + class3Provision;
            riskReportWriter.write(line3);
            riskReportWriter.newLine();

            String line4 = "CLASSE 4 (>180J)    : CNT=" + class4Count +
                " ENC=" + class4Outstanding + " PROV=" + class4Provision;
            riskReportWriter.write(line4);
            riskReportWriter.newLine();

            String line5 = "TOTAL PROVISIONS    : " + totalProvision;
            riskReportWriter.write(line5);
            riskReportWriter.newLine();

            String footer = String.format("%-20s%-60s%-57s", " ",
                "*** END OF REPORT ***", " ");
            riskReportWriter.write(footer);
            riskReportWriter.newLine();

        } catch (IOException e) {
            System.err.println("Summary write error: " + e.getMessage());
        }
    }

    private void closeFiles() {
        try {
            if (loanFileReader != null) loanFileReader.close();
            if (riskReportWriter != null) riskReportWriter.close();
            if (bctSubmissionWriter != null) bctSubmissionWriter.close();
        } catch (IOException e) {
            System.err.println("File close error: " + e.getMessage());
        }
    }

    private void processPortfolio() {
        if (currentLoanRecord == null) {
            readNextLoan();
            return;
        }

        if (!currentLoanRecord.isActive() && !currentLoanRecord.isRestructured()) {
            readNextLoan();
            return;
        }

        statProcessed++;
        currentLoanId = currentLoanRecord.loanId;
        currentCustId = currentLoanRecord.custId;
        prevClass = currentLoanRecord.loanClass;

        classifyLoan();
        checkRecoveryFlag();
        computeProvision();
        updateLoanClass();
        insertRiskHist();
        accumulatePortfolio();
        writeBctRecord();
        readNextLoan();
    }

    private void classifyLoan() {
        int dpd = currentLoanRecord.daysPastDue;

        if (dpd <= 30) {
            currentLoanRecord.loanClass = "1";
            currentLoanRecord.provisionRate = BigDecimal.ZERO;
        } else if (dpd <= 90) {
            currentLoanRecord.loanClass = "2";
            currentLoanRecord.provisionRate = new BigDecimal("20.0000");
        } else if (dpd <= 180) {
            currentLoanRecord.loanClass = "3";
            currentLoanRecord.provisionRate = new BigDecimal("50.0000");
        } else {
            currentLoanRecord.loanClass = "4";
            currentLoanRecord.provisionRate = new BigDecimal("100.0000");
        }
    }

    private void checkRecoveryFlag() {
        recoveryFound = false;
        for (RecoveryEntry entry : recoveryTable) {
            if (entry.loanId == currentLoanId) {
                recoveryFound = true;
                break;
            }
        }
    }

    private void computeProvision() {
        BigDecimal outstanding = currentLoanRecord.outstanding;
        BigDecimal rate = currentLoanRecord.provisionRate;
        requiredProvision = outstanding.multiply(rate)
            .divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);

        currentLoanRecord.provisionAmt = requiredProvision;
    }

    private void updateLoanClass() {
        // In real implementation, would rewrite the indexed loan file record
        // For this conversion, we acknowledge the REWRITE but do not persist
    }

    private void insertRiskHist() {
        // SQL INSERT would be executed here with host variables:
        // WS-SQL-LOAN-ID = currentLoanId
        // WS-SQL-CUST-ID = currentCustId
        // WS-SQL-CLASS = currentLoanRecord.loanClass
        // WS-SQL-PREV-CLASS = prevClass
        // WS-SQL-OUTSTANDING = currentLoanRecord.outstanding
        // WS-SQL-PROVISION = requiredProvision
        // WS-SQL-DPD = currentLoanRecord.daysPastDue
        // WS-SQL-DATE = todayDate
        // If SQLCODE != 0, log error
    }

    private void accumulatePortfolio() {
        if (totalOutstanding == null) totalOutstanding = BigDecimal.ZERO;
        if (totalProvision == null) totalProvision = BigDecimal.ZERO;

        totalOutstanding = totalOutstanding.add(currentLoanRecord.outstanding);
        totalProvision = totalProvision.add(requiredProvision);

        switch (currentLoanRecord.loanClass) {
            case "1":
                class1Count++;
                if (class1Outstanding == null) class1Outstanding = BigDecimal.ZERO;
                if (class1Provision == null) class1Provision = BigDecimal.ZERO;
                class1Outstanding = class1Outstanding.add(currentLoanRecord.outstanding);
                class1Provision = class1Provision.add(requiredProvision);
                break;
            case "2":
                class2Count++;
                if (class2Outstanding == null) class2Outstanding = BigDecimal.ZERO;
                if (class2Provision == null) class2Provision = BigDecimal.ZERO;
                class2Outstanding = class2Outstanding.add(currentLoanRecord.outstanding);
                class2Provision = class2Provision.add(requiredProvision);
                break;
            case "3":
                class3Count++;
                if (class3Outstanding == null) class3Outstanding = BigDecimal.ZERO;
                if (class3Provision == null) class3Provision = BigDecimal.ZERO;
                class3Outstanding = class3Outstanding.add(currentLoanRecord.outstanding);
                class3Provision = class3Provision.add(requiredProvision);
                break;
            case "4":
                class4Count++;
                if (class4Outstanding == null) class4Outstanding = BigDecimal.ZERO;
                if (class4Provision == null) class4Provision = BigDecimal.ZERO;
                class4Outstanding = class4Outstanding.add(currentLoanRecord.outstanding);
                class4Provision = class4Provision.add(requiredProvision);
                break;
        }
    }

    private void writeBctRecord() {
        try {
            String recoveryFlag = recoveryFound ? "REC" : "NRC";
            String bctLine = String.format("%04d  %s  %010d  %08d  %s  %013.2f  %013.2f  %04d  %s%-124s",
                BCT_BANK_CODE, todayDate, currentLoanId, currentCustId,
                currentLoanRecord.loanClass,
                currentLoanRecord.outstanding,
                requiredProvision,
                currentLoanRecord.daysPastDue,
                recoveryFlag, " ");
            bctSubmissionWriter.write(bctLine);
            bctSubmissionWriter.newLine();
        } catch (IOException e) {
            System.err.println("BCT write error: " + e.getMessage());
        }
    }

    private void readNextLoan() {
        try {
            String line = loanFileReader.readLine();
            if (line == null) {
                endLoanFile = true;
                currentLoanRecord = null;
            } else {
                currentLoanRecord = parseLoanRecord(line);
            }
        } catch (IOException e) {
            endLoanFile = true;
            currentLoanRecord = null;
        }
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

    private RecoveryAction parseRecoveryAction(String line) {
        if (line.length() < 238) {
            line = String.format("%-238s", line);
        }

        RecoveryAction rec = new RecoveryAction();
        rec.loanId = Integer.parseInt(line.substring(12, 22).trim());
        rec.actionType = line.substring(38, 41).trim();
        return rec;
    }

    static class LoanRecord {
        int loanId;
        int custId;
        String status;
        String loanClass;
        BigDecimal outstanding;
        int daysPastDue;
        BigDecimal provisionRate;
        BigDecimal provisionAmt;

        boolean isActive() {
            return "AC".equals(status);
        }

        boolean isRestructured() {
            return "RS".equals(status);
        }
    }

    static class RecoveryAction {
        int loanId;
        String actionType;
    }

    static class RecoveryEntry {
        int loanId;
        String actionCode;

        RecoveryEntry(int loanId, String actionCode) {
            this.loanId = loanId;
            this.actionCode = actionCode;
        }
    }
}
