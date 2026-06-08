package com.modernized.rptmonth;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Arrays;

public class Rptmonth {

    // Constants for file names
    private static final String LOAN_FILE_NAME = "LOANFILE.dat";
    private static final String CUSTOMER_FILE_NAME = "CUSTFILE.dat";
    private static final String SCORE_FILE_NAME = "SCORFILE.dat";
    private static final String MONTH_REPORT_FILE_NAME = "MONTHRPT.dat";

    // File readers/writers
    private BufferedReader loanFileReader;
    private BufferedReader customerFileReader;
    private BufferedReader scoreFileReader;
    private BufferedWriter monthReportWriter;

    // Working storage variables
    private WsControl wsControl = new WsControl();
    private WsPortfolio wsPortfolio = new WsPortfolio();
    private WsByClass wsByClass = new WsByClass();
    private WsBySegment wsBySegment = new WsBySegment();
    private WsByType wsByType = new WsByType();
    private WsTopExposures wsTopExposures = new WsTopExposures();
    private WsPage wsPage = new WsPage();
    private WsDisp wsDisp = new WsDisp();

    private String monthLine = "";

    // Current loan record
    private LoanRecord currentLoanRecord;

    // Current customer record
    private CustomerRecord currentCustomerRecord;

    // Flags and status
    private boolean rcSuccess = true;
    private String wsErrorMessage = "";
    private int returnCode = 0;

    // For reading loan file line by line
    private String currentLoanLine = null;

    // For reading customer file indexed by custId (simulate with file scan)
    // In real indexed file, random access would be used.
    // Here, we simulate by scanning file for matching custId.

    public static void main(String[] args) {
        Rptmonth program = new Rptmonth();
        program.main();
    }

    private void main() {
        // MOVE 'RPTMONTH' TO WS-PROGRAM-NAME (not stored, so omitted)
        // ACCEPT WS-TODAY-DATE FROM DATE YYYYMMDD
        wsControl.wsTodayDate = getTodayDateYYYYMMDD();

        display("RPTMONTH v2.3 START " + wsControl.wsTodayDate);

        openFiles();
        if (!rcSuccess) {
            display("RPTMONTH ABEND: " + wsErrorMessage);
            returnCode = 12;
            return;
        }

        initTables();
        writeCover();

        while (!"Y".equals(wsControl.wsEndLoanFile)) {
            aggregatePortfolio();
        }

        writeSection1();
        writeSection2();
        writeSection3();
        writeSection4();
        writeSection5();
        writeFooter();

        closeFiles();

        display("RPTMONTH COMPLETED. LOANS=" + wsPortfolio.wsTotalLoans + " AMT=" + formatAmount(wsPortfolio.wsTotalOutstanding));

        returnCode = 0;
    }

    private void openFiles() {
        try {
            loanFileReader = new BufferedReader(new FileReader(LOAN_FILE_NAME));
        } catch (IOException e) {
            rcSuccess = false;
            wsErrorMessage = "LOANFILE OPEN FAILED FS=IOERROR";
            returnCode = 12;
            return;
        }

        try {
            customerFileReader = new BufferedReader(new FileReader(CUSTOMER_FILE_NAME));
        } catch (IOException e) {
            rcSuccess = false;
            wsErrorMessage = "CUSTFILE OPEN FAILED FS=IOERROR";
            returnCode = 12;
            closeQuietly(loanFileReader);
            return;
        }

        try {
            scoreFileReader = new BufferedReader(new FileReader(SCORE_FILE_NAME));
        } catch (IOException e) {
            rcSuccess = false;
            wsErrorMessage = "SCORFILE OPEN FAILED FS=IOERROR";
            returnCode = 12;
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            return;
        }

        try {
            monthReportWriter = new BufferedWriter(new FileWriter(MONTH_REPORT_FILE_NAME));
        } catch (IOException e) {
            rcSuccess = false;
            wsErrorMessage = "MONTHRPT OPEN FAILED";
            returnCode = 12;
            closeQuietly(loanFileReader);
            closeQuietly(customerFileReader);
            closeQuietly(scoreFileReader);
            return;
        }

        rcSuccess = true;
        readNext();
    }

    private void initTables() {
        // Initialize WSSE-CODE array
        wsBySegment.wsseCode[0] = "MM";
        wsBySegment.wsseCode[1] = "MB";
        wsBySegment.wsseCode[2] = "PR";
        wsBySegment.wsseCode[3] = "PB";

        // Initialize WSTY-CODE and WSTY-LABEL arrays
        wsByType.wstyCode[0] = "CON";
        wsByType.wstyLabel[0] = "CONSOMMATION";
        wsByType.wstyCode[1] = "IMM";
        wsByType.wstyLabel[1] = "IMMOBILIER";
        wsByType.wstyCode[2] = "AUT";
        wsByType.wstyLabel[2] = "AUTOMOBILE";
        wsByType.wstyCode[3] = "PRO";
        wsByType.wstyLabel[3] = "PROFESSIONNEL";
        wsByType.wstyCode[4] = "REV";
        wsByType.wstyLabel[4] = "REVOLVING";
        wsByType.wstyCode[5] = "DEC";
        wsByType.wstyLabel[5] = "DECOUVERT";
    }

    private void writeCover() {
        RptCopy rpt = new RptCopy();
        rpt.rptProgram = "RPTMONTH";
        rpt.rptRunDate = wsControl.wsTodayDate;
        rpt.rptPageNo = 1;

        wsPage.wsPageNo = 1;
        wsPage.wsLineCount = 5;

        try {
            writeLine(rpt.rptMainHeader);
            writeLine(rpt.rptSubHeader);
            writeLine(rpt.rptSeparator);
            writeLine("");
            writeLine("   ACME BANK TUNISIE - DIRECTION DU CREDIT");
            writeLine("   PERIODE: " + wsControl.wsTodayDate);
            writeLine("   CONFIDENTIEL - USAGE INTERNE");
            writeLine(rpt.rptSeparator);
        } catch (IOException e) {
            rcSuccess = false;
            wsErrorMessage = "Error writing cover page";
        }
    }

    private void closeFiles() {
        closeQuietly(loanFileReader);
        closeQuietly(customerFileReader);
        closeQuietly(scoreFileReader);
        closeQuietly(monthReportWriter);
    }

    private void aggregatePortfolio() {
        if (currentLoanRecord == null) {
            wsControl.wsEndLoanFile = "Y";
            return;
        }

        if (!currentLoanRecord.isActive() && !currentLoanRecord.isRestructured()) {
            readNext();
            return;
        }

        wsPortfolio.wsTotalLoans += 1;
        wsPortfolio.wsTotalOutstanding = wsPortfolio.wsTotalOutstanding.add(currentLoanRecord.getOutstanding());
        wsPortfolio.wsTotalProvision = wsPortfolio.wsTotalProvision.add(currentLoanRecord.getProvisionAmount());

        // WS-AVG-RATE-NUM = WS-AVG-RATE-NUM + (LOAN-INTEREST-RATE * LOAN-OUTSTANDING)
        BigDecimal interestRateTimesOutstanding = currentLoanRecord.getInterestRate().multiply(currentLoanRecord.getOutstanding());
        wsPortfolio.wsAvgRateNum = wsPortfolio.wsAvgRateNum.add(interestRateTimesOutstanding);
        wsPortfolio.wsAvgRateNum = store(wsPortfolio.wsAvgRateNum, 13, 2, RoundingMode.DOWN);

        wsControl.wsCurrentLoanId = currentLoanRecord.getLoanId();
        wsControl.wsCurrentCustId = currentLoanRecord.getCustId();

        aggregateByClass();
        aggregateByType();
        lookupCustomer();
        aggregateBySegment();
        maintainTop10();

        readNext();
    }

    private void aggregateByClass() {
        int clIdx;
        switch (currentLoanRecord.getLoanClass()) {
            case "1":
                clIdx = 0;
                break;
            case "2":
                clIdx = 1;
                break;
            case "3":
                clIdx = 2;
                break;
            case "4":
                clIdx = 3;
                break;
            default:
                clIdx = 0;
                break;
        }

        wsByClass.wsclCount[clIdx] += 1;
        wsByClass.wsclOutstanding[clIdx] = wsByClass.wsclOutstanding[clIdx].add(currentLoanRecord.getOutstanding());
        wsByClass.wsclProvision[clIdx] = wsByClass.wsclProvision[clIdx].add(currentLoanRecord.getProvisionAmount());

        wsByClass.wsclOutstanding[clIdx] = store(wsByClass.wsclOutstanding[clIdx], 13, 2, RoundingMode.DOWN);
        wsByClass.wsclProvision[clIdx] = store(wsByClass.wsclProvision[clIdx], 13, 2, RoundingMode.DOWN);
    }

    private void aggregateByType() {
        for (int tyIdx = 0; tyIdx < 6; tyIdx++) {
            if (wstyCodeEquals(tyIdx, currentLoanRecord.getLoanType())) {
                wsByType.wstyCount[tyIdx] += 1;
                wsByType.wstyAmount[tyIdx] = wsByType.wstyAmount[tyIdx].add(currentLoanRecord.getOutstanding());
                wsByType.wstyAmount[tyIdx] = store(wsByType.wstyAmount[tyIdx], 13, 2, RoundingMode.DOWN);
                break;
            }
        }
    }

    private boolean wstyCodeEquals(int index, String code) {
        if (wsByType.wstyCode[index] == null) return false;
        return wsByType.wstyCode[index].equals(code);
    }

    private void lookupCustomer() {
        int custId = wsControl.wsCurrentCustId;
        currentCustomerRecord = readCustomerById(custId);
        if (currentCustomerRecord == null) {
            currentCustomerRecord = new CustomerRecord();
            currentCustomerRecord.setFirstName("");
            currentCustomerRecord.setLastName("");
            currentCustomerRecord.setSegment("");
        }
    }

    private void aggregateBySegment() {
        for (int segIdx = 0; segIdx < 4; segIdx++) {
            if (wsBySegment.wsseCode[segIdx].equals(currentCustomerRecord.getSegment())) {
                wsBySegment.wsseCount[segIdx] += 1;
                wsBySegment.wsseOutstanding[segIdx] = wsBySegment.wsseOutstanding[segIdx].add(currentLoanRecord.getOutstanding());
                wsBySegment.wsseOutstanding[segIdx] = store(wsBySegment.wsseOutstanding[segIdx], 13, 2, RoundingMode.DOWN);
                if (currentLoanRecord.isActive()) {
                    wsBySegment.wsseApproved[segIdx] += 1;
                } else {
                    wsBySegment.wsseDeclined[segIdx] += 1;
                }
                break;
            }
        }
    }

    private void maintainTop10() {
        BigDecimal loanOutstanding = currentLoanRecord.getOutstanding();
        if (loanOutstanding.compareTo(wsTopExposures.wstopOutstanding[9]) > 0) {
            wsInsertIdx = 9;
            while (wsInsertIdx >= 0 && loanOutstanding.compareTo(wsTopExposures.wstopOutstanding[wsInsertIdx]) > 0) {
                wsInsertIdx--;
            }
            wsInsertIdx++;
            if (wsInsertIdx <= 9) {
                // Shift entries down to make room
                for (int wsShiftIdx = 9; wsShiftIdx > wsInsertIdx; wsShiftIdx--) {
                    wsTopExposures.wstopLoanId[wsShiftIdx] = wsTopExposures.wstopLoanId[wsShiftIdx - 1];
                    wsTopExposures.wstopCustId[wsShiftIdx] = wsTopExposures.wstopCustId[wsShiftIdx - 1];
                    wsTopExposures.wstopCustName[wsShiftIdx] = wsTopExposures.wstopCustName[wsShiftIdx - 1];
                    wsTopExposures.wstopOutstanding[wsShiftIdx] = wsTopExposures.wstopOutstanding[wsShiftIdx - 1];
                    wsTopExposures.wstopClass[wsShiftIdx] = wsTopExposures.wstopClass[wsShiftIdx - 1];
                    wsTopExposures.wstopType[wsShiftIdx] = wsTopExposures.wstopType[wsShiftIdx - 1];
                }
                // Insert new entry
                wsTopExposures.wstopLoanId[wsInsertIdx] = currentLoanRecord.getLoanId();
                wsTopExposures.wstopCustId[wsInsertIdx] = currentLoanRecord.getCustId();
                wsTopExposures.wstopCustName[wsInsertIdx] = (currentCustomerRecord.getLastName() + " " + currentCustomerRecord.getFirstName()).trim();
                wsTopExposures.wstopOutstanding[wsInsertIdx] = loanOutstanding;
                wsTopExposures.wstopClass[wsInsertIdx] = currentLoanRecord.getLoanClass();
                wsTopExposures.wstopType[wsInsertIdx] = currentLoanRecord.getLoanType();
            }
        }
    }

    private void writeSection1() {
        try {
            checkPage();
            writeLine("");
            writeLine("SECTION 1 - REPARTITION DU PORTEFEUILLE PAR CLASSE");
            writeLine(RptCopy.rptSeparator);
            wsPage.wsLineCount += 3;

            for (int clIdx = 0; clIdx < 4; clIdx++) {
                checkPage();
                wsDisp.wsDispCount = Integer.toString(wsByClass.wsclCount[clIdx]);
                wsDisp.wsDispAmount = formatAmount(wsByClass.wsclOutstanding[clIdx]);
                wsDisp.wsDispIdx = clIdx + 1;
                String line = "  CLASSE " + wsDisp.wsDispIdx
                        + "   COUNT=" + wsDisp.wsDispCount
                        + "   ENC=" + wsDisp.wsDispAmount;
                writeLine(line);
                wsPage.wsLineCount++;
            }

            checkPage();
            wsDisp.wsDispAmount = formatAmount(wsPortfolio.wsTotalOutstanding);
            writeLine("  TOTAL ENCOURS         : " + wsDisp.wsDispAmount);
            wsPage.wsLineCount++;

            if (wsPortfolio.wsTotalOutstanding.compareTo(BigDecimal.ZERO) > 0) {
                // WS-DISP-PCT = (WS-TOTAL-PROVISION / WS-TOTAL-OUTSTANDING) * 100 (RoundingMode.DOWN)
                BigDecimal pct = wsPortfolio.wsTotalProvision.multiply(BigDecimal.valueOf(100))
                        .divide(wsPortfolio.wsTotalOutstanding, 6, RoundingMode.DOWN);
                pct = pct.setScale(0, RoundingMode.DOWN);
                wsDisp.wsDispPct = pct.toPlainString();

                // WS-AVG-RATE = WS-AVG-RATE-NUM / WS-TOTAL-OUTSTANDING (RoundingMode.DOWN)
                BigDecimal avgRate = wsPortfolio.wsAvgRateNum.divide(wsPortfolio.wsTotalOutstanding, 6, RoundingMode.DOWN);
                avgRate = store(avgRate, 2, 4, RoundingMode.DOWN);
                wsPortfolio.wsAvgRate = avgRate;

                wsDisp.wsDispAmount = formatAmount(wsPortfolio.wsTotalProvision);
                String line = "  TOTAL PROVISIONS     : " + wsDisp.wsDispAmount
                        + "   TAUX PROV: " + wsDisp.wsDispPct + "%";
                writeLine(line);

                wsDisp.wsDispRate = formatRate(wsPortfolio.wsAvgRate);
                writeLine("  TAUX MOYEN PONDERE   : " + wsDisp.wsDispRate + "%");
                wsPage.wsLineCount += 2;
            }
        } catch (IOException e) {
            rcSuccess = false;
            wsErrorMessage = "Error writing section 1";
        }
    }

    private void writeSection2() {
        try {
            checkPage();
            writeLine("");
            writeLine("SECTION 2 - TOP 10 EXPOSITIONS");
            writeLine(RptCopy.rptSeparator);
            wsPage.wsLineCount += 3;

            for (int topIdx = 0; topIdx < 10; topIdx++) {
                if (wsTopExposures.wstopLoanId[topIdx] != 0) {
                    checkPage();
                    wsDisp.wsDispAmount = formatAmount(wsTopExposures.wstopOutstanding[topIdx]);
                    wsDisp.wsDispIdx = topIdx + 1;
                    String line = "  #" + wsDisp.wsDispIdx
                            + "  " + wsTopExposures.wstopLoanId[topIdx]
                            + "  " + wsTopExposures.wstopCustName[topIdx]
                            + "  CL:" + wsTopExposures.wstopClass[topIdx]
                            + "  " + wsTopExposures.wstopType[topIdx]
                            + "  ENC:" + wsDisp.wsDispAmount;
                    writeLine(line);
                    wsPage.wsLineCount++;
                }
            }
        } catch (IOException e) {
            rcSuccess = false;
            wsErrorMessage = "Error writing section 2";
        }
    }

    private void writeSection3() {
        try {
            checkPage();
            writeLine("");
            writeLine("SECTION 3 - REPARTITION PAR SEGMENT CLIENT");
            writeLine(RptCopy.rptSeparator);
            wsPage.wsLineCount += 3;

            for (int segIdx = 0; segIdx < 4; segIdx++) {
                checkPage();
                wsDisp.wsDispCount = Integer.toString(wsBySegment.wsseCount[segIdx]);
                wsDisp.wsDispAmount = formatAmount(wsBySegment.wsseOutstanding[segIdx]);
                String line = "  SEGMENT " + wsBySegment.wsseCode[segIdx]
                        + "   CNT=" + wsDisp.wsDispCount
                        + "   ENC=" + wsDisp.wsDispAmount;
                writeLine(line);
                wsPage.wsLineCount++;
            }
        } catch (IOException e) {
            rcSuccess = false;
            wsErrorMessage = "Error writing section 3";
        }
    }

    private void writeSection4() {
        try {
            checkPage();
            writeLine("");
            writeLine("SECTION 4 - VENTILATION PAR TYPE DE CREDIT");
            writeLine(RptCopy.rptSeparator);
            wsPage.wsLineCount += 3;

            for (int tyIdx = 0; tyIdx < 6; tyIdx++) {
                checkPage();
                wsDisp.wsDispCount = Integer.toString(wsByType.wstyCount[tyIdx]);
                wsDisp.wsDispAmount = formatAmount(wsByType.wstyAmount[tyIdx]);
                String line = "  " + wsByType.wstyCode[tyIdx]
                        + " " + wsByType.wstyLabel[tyIdx]
                        + "  CNT=" + wsDisp.wsDispCount
                        + "  AMT=" + wsDisp.wsDispAmount;
                writeLine(line);
                wsPage.wsLineCount++;
            }
        } catch (IOException e) {
            rcSuccess = false;
            wsErrorMessage = "Error writing section 4";
        }
    }

    private void writeSection5() {
        try {
            checkPage();
            writeLine("");
            writeLine("SECTION 5 - INDICATEURS DE RISQUE");
            writeLine(RptCopy.rptSeparator);
            wsPage.wsLineCount += 3;

            if (wsPortfolio.wsTotalOutstanding.compareTo(BigDecimal.ZERO) > 0) {
                // RATIO NPL (CL 2-3-4) = ((WSCL-OUTSTANDING(2) + WSCL-OUTSTANDING(3) + WSCL-OUTSTANDING(4)) / WS-TOTAL-OUTSTANDING) * 100
                BigDecimal sum234 = wsByClass.wsclOutstanding[1].add(wsByClass.wsclOutstanding[2]).add(wsByClass.wsclOutstanding[3]);
                BigDecimal ratioNpl = sum234.multiply(BigDecimal.valueOf(100))
                        .divide(wsPortfolio.wsTotalOutstanding, 0, RoundingMode.HALF_UP);
                wsDisp.wsDispPct = ratioNpl.toPlainString();
                writeLine("  RATIO NPL (CL 2-3-4) : " + wsDisp.wsDispPct + "%");

                // RATIO PERTES (CL 4) = (WSCL-OUTSTANDING(4) / WS-TOTAL-OUTSTANDING) * 100
                BigDecimal ratioLoss = wsByClass.wsclOutstanding[3].multiply(BigDecimal.valueOf(100))
                        .divide(wsPortfolio.wsTotalOutstanding, 0, RoundingMode.HALF_UP);
                wsDisp.wsDispPct = ratioLoss.toPlainString();
                writeLine("  RATIO PERTES (CL 4)  : " + wsDisp.wsDispPct + "%");

                // TAUX COUVERTURE PROV = (WS-TOTAL-PROVISION / WS-TOTAL-OUTSTANDING) * 100
                BigDecimal coverageRate = wsPortfolio.wsTotalProvision.multiply(BigDecimal.valueOf(100))
                        .divide(wsPortfolio.wsTotalOutstanding, 0, RoundingMode.HALF_UP);
                wsDisp.wsDispPct = coverageRate.toPlainString();
                writeLine("  TAUX COUVERTURE PROV : " + wsDisp.wsDispPct + "%");

                wsPage.wsLineCount += 3;
            }
        } catch (IOException e) {
            rcSuccess = false;
            wsErrorMessage = "Error writing section 5";
        }
    }

    private void writeFooter() {
        try {
            writeLine("");
            writeLine(RptCopy.rptSeparator);
            writeLine("  FIN DU RAPPORT - GENERE PAR RPTMONTH v2.3");
            writeLine(RptCopy.rptFooterLine);
        } catch (IOException e) {
            rcSuccess = false;
            wsErrorMessage = "Error writing footer";
        }
    }

    private void checkPage() throws IOException {
        if (wsPage.wsLineCount >= wsPage.wsMaxLines) {
            wsPage.wsPageNo++;
            RptCopy rpt = new RptCopy();
            rpt.rptPageNo = wsPage.wsPageNo;
            writeLine(rpt.rptMainHeader);
            writeLine(rpt.rptSeparator);
            wsPage.wsLineCount = 2;
        }
    }

    private void readNext() {
        try {
            currentLoanLine = loanFileReader.readLine();
            if (currentLoanLine == null) {
                wsControl.wsEndLoanFile = "Y";
                currentLoanRecord = null;
            } else {
                currentLoanRecord = LoanRecord.parse(currentLoanLine);
                wsControl.wsEndLoanFile = "N";
            }
        } catch (IOException e) {
            wsControl.wsEndLoanFile = "Y";
            currentLoanRecord = null;
        }
    }

    private CustomerRecord readCustomerById(int custId) {
        // Simulate indexed read by scanning file for matching custId
        try {
            customerFileReader.close();
            customerFileReader = new BufferedReader(new FileReader(CUSTOMER_FILE_NAME));
            String line;
            while ((line = customerFileReader.readLine()) != null) {
                CustomerRecord cr = CustomerRecord.parse(line);
                if (cr.getCustId() == custId) {
                    return cr;
                }
            }
        } catch (IOException e) {
            // ignore, return null
        }
        return null;
    }

    private void writeLine(String line) throws IOException {
        if (line == null) line = "";
        if (line.length() > 137) {
            line = line.substring(0, 137);
        } else if (line.length() < 137) {
            line = String.format("%-" + 137 + "s", line);
        }
        monthReportWriter.write(line);
        monthReportWriter.newLine();
        monthReportWriter.flush();
        monthLine = line;
    }

    private void display(String message) {
        System.out.println(message);
    }

    private int getTodayDateYYYYMMDD() {
        java.time.LocalDate now = java.time.LocalDate.now();
        return now.getYear() * 10000 + now.getMonthValue() * 100 + now.getDayOfMonth();
    }

    private void closeQuietly(AutoCloseable c) {
        if (c != null) {
            try {
                c.close();
            } catch (Exception ignored) {
            }
        }
    }

    private String formatAmount(BigDecimal amount) {
        // Format with comma thousands separator, dot decimal, no locale
        // Z-suppressed leading zeros (no leading zeros)
        // 2 decimals fixed
        if (amount == null) return "0.00";
        amount = amount.setScale(2, RoundingMode.DOWN);
        String s = amount.toPlainString();
        // Insert commas manually
        int dotIndex = s.indexOf('.');
        String intPart = dotIndex >= 0 ? s.substring(0, dotIndex) : s;
        String decPart = dotIndex >= 0 ? s.substring(dotIndex) : ".00";

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

    private String formatRate(BigDecimal rate) {
        // Format rate with 4 decimals, no leading zeros, dot decimal
        if (rate == null) return "0.0000";
        rate = rate.setScale(4, RoundingMode.DOWN);
        return rate.toPlainString();
    }

    private BigDecimal store(BigDecimal value, int intDigits, int decDigits, RoundingMode roundingMode) {
        if (value == null) return BigDecimal.ZERO;
        int scale = decDigits;
        BigDecimal scaled = value.setScale(scale, roundingMode);
        // Truncate integer digits if needed (not typical in BigDecimal, so just return scaled)
        return scaled;
    }

    // Working storage classes and arrays

    private static class WsControl {
        int wsTodayDate;
        String wsEndLoanFile = "N";
        int wsCurrentLoanId;
        int wsCurrentCustId;
    }

    private static class WsPortfolio {
        int wsTotalLoans = 0;
        BigDecimal wsTotalOutstanding = BigDecimal.ZERO;
        BigDecimal wsTotalProvision = BigDecimal.ZERO;
        BigDecimal wsAvgOutstanding = BigDecimal.ZERO;
        BigDecimal wsAvgRateNum = BigDecimal.ZERO;
        BigDecimal wsAvgRate = BigDecimal.ZERO;
    }

    private static class WsByClass {
        int[] wsclCount = new int[4];
        BigDecimal[] wsclOutstanding = new BigDecimal[4];
        BigDecimal[] wsclProvision = new BigDecimal[4];

        WsByClass() {
            Arrays.fill(wsclOutstanding, BigDecimal.ZERO);
            Arrays.fill(wsclProvision, BigDecimal.ZERO);
        }
    }

    private static class WsBySegment {
        String[] wsseCode = new String[4];
        int[] wsseCount = new int[4];
        BigDecimal[] wsseOutstanding = new BigDecimal[4];
        int[] wsseApproved = new int[4];
        int[] wsseDeclined = new int[4];

        WsBySegment() {
            Arrays.fill(wsseOutstanding, BigDecimal.ZERO);
        }
    }

    private static class WsByType {
        String[] wstyCode = new String[6];
        String[] wstyLabel = new String[6];
        int[] wstyCount = new int[6];
        BigDecimal[] wstyAmount = new BigDecimal[6];

        WsByType() {
            Arrays.fill(wstyAmount, BigDecimal.ZERO);
        }
    }

    private static class WsTopExposures {
        int[] wstopLoanId = new int[10];
        int[] wstopCustId = new int[10];
        String[] wstopCustName = new String[10];
        BigDecimal[] wstopOutstanding = new BigDecimal[10];
        String[] wstopClass = new String[10];
        String[] wstopType = new String[10];

        WsTopExposures() {
            Arrays.fill(wstopCustName, "");
            Arrays.fill(wstopOutstanding, BigDecimal.ZERO);
            Arrays.fill(wstopClass, "");
            Arrays.fill(wstopType, "");
        }
    }

    private static class WsPage {
        int wsPageNo = 0;
        int wsLineCount = 0;
        int wsMaxLines = 55;
    }

    private static class WsDisp {
        String wsDispCount = "0";
        String wsDispAmount = "0.00";
        String wsDispPct = "0";
        String wsDispRate = "0";
        int wsDispIdx = 0;
    }

    // Temporary indices for maintainTop10
    private int wsInsertIdx = 0;
    private int wsShiftIdx = 0;

    // LoanRecord class representing LOAN-FILE record
    public static class LoanRecord {
        private int loanId;
        private int custId;
        private String loanClass;
        private String loanType;
        private BigDecimal outstanding;
        private BigDecimal provisionAmount;
        private BigDecimal interestRate;
        private boolean active;
        private boolean restructured;

        public static LoanRecord parse(String line) {
            // Fixed width parsing based on LOANCOPY (not provided, so assumptions)
            // Loan ID: positions 0-9 (10 chars), numeric
            // Cust ID: positions 10-17 (8 chars), numeric
            // Loan Class: position 18 (1 char)
            // Loan Type: positions 19-21 (3 chars)
            // Outstanding: positions 22-36 (15V99) => 17 chars, implied decimal 2
            // Provision Amount: positions 37-49 (13V99) => 15 chars, implied decimal 2
            // Interest Rate: positions 50-55 (6 chars) => 9(2)V9(4) maybe stored differently, assume 6 chars with implied decimal 4
            // Active: position 56 (1 char) 'Y' or 'N'
            // Restructured: position 57 (1 char) 'Y' or 'N'

            LoanRecord lr = new LoanRecord();
            try {
                lr.loanId = Integer.parseInt(line.substring(0, 10).trim());
            } catch (Exception e) {
                lr.loanId = 0;
            }
            try {
                lr.custId = Integer.parseInt(line.substring(10, 18).trim());
            } catch (Exception e) {
                lr.custId = 0;
            }
            lr.loanClass = line.substring(18, 19);
            lr.loanType = line.substring(19, 22).trim();

            try {
                String outStr = line.substring(22, 37).trim();
                lr.outstanding = parseImpliedDecimal(outStr, 2);
            } catch (Exception e) {
                lr.outstanding = BigDecimal.ZERO;
            }
            try {
                String provStr = line.substring(37, 52).trim();
                lr.provisionAmount = parseImpliedDecimal(provStr, 2);
            } catch (Exception e) {
                lr.provisionAmount = BigDecimal.ZERO;
            }
            try {
                String rateStr = line.substring(52, 58).trim();
                lr.interestRate = parseImpliedDecimal(rateStr, 4);
            } catch (Exception e) {
                lr.interestRate = BigDecimal.ZERO;
            }
            lr.active = "Y".equalsIgnoreCase(line.substring(58, 59));
            lr.restructured = "Y".equalsIgnoreCase(line.substring(59, 60));

            return lr;
        }

        private static BigDecimal parseImpliedDecimal(String s, int decimals) {
            if (s == null || s.isEmpty()) return BigDecimal.ZERO;
            // Remove leading zeros
            s = s.replaceFirst("^0+(?!$)", "");
            if (s.isEmpty()) s = "0";
            BigDecimal bd = new BigDecimal(s);
            bd = bd.movePointLeft(decimals);
            return bd;
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

        public String getLoanType() {
            return loanType;
        }

        public BigDecimal getOutstanding() {
            return outstanding;
        }

        public BigDecimal getProvisionAmount() {
            return provisionAmount;
        }

        public BigDecimal getInterestRate() {
            return interestRate;
        }

        public boolean isActive() {
            return active;
        }

        public boolean isRestructured() {
            return restructured;
        }
    }

    // CustomerRecord class representing CUSTOMER-FILE record
    public static class CustomerRecord {
        private int custId;
        private String firstName;
        private String lastName;
        private String segment;

        public static CustomerRecord parse(String line) {
            // Fixed width parsing based on CUSTCOPY (not provided, so assumptions)
            // Cust ID: positions 0-7 (8 chars), numeric
            // Last Name: positions 8-47 (40 chars)
            // First Name: positions 48-87 (40 chars)
            // Segment: positions 88-89 (2 chars)

            CustomerRecord cr = new CustomerRecord();
            try {
                cr.custId = Integer.parseInt(line.substring(0, 8).trim());
            } catch (Exception e) {
                cr.custId = 0;
            }
            cr.lastName = line.substring(8, 48).trim();
            cr.firstName = line.substring(48, 88).trim();
            cr.segment = line.substring(88, 90).trim();
            return cr;
        }

        public int getCustId() {
            return custId;
        }

        public String getFirstName() {
            return firstName == null ? "" : firstName;
        }

        public String getLastName() {
            return lastName == null ? "" : lastName;
        }

        public String getSegment() {
            return segment == null ? "" : segment;
        }

        public void setFirstName(String firstName) {
            this.firstName = firstName;
        }

        public void setLastName(String lastName) {
            this.lastName = lastName;
        }

        public void setSegment(String segment) {
            this.segment = segment;
        }
    }

    // RptCopy class simulating RPTCOPY2 copybook constants and lines
    private static class RptCopy {
        static final String rptMainHeader = "RPTMONTH - EXECUTIVE REPORT";
        static final String rptSubHeader = "PRODUCTION v2.3";
        static final String rptSeparator = "---------------------------------------------------------------------------------------------------------------------------------";
        static final String rptFooterLine = "---------------------------------------------------------------------------------------------------------------------------------";

        String rptProgram;
        int rptRunDate;
        int rptPageNo;
        String rptTitle;
    }
}
