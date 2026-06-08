package com.modernized.chkaml;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class Chkaml {
    // TODO: auto-declared missing variable 'lkReqCin'
    private String lkReqCin = "";


    private static final Path SANCTIONS_FILE_PATH = Path.of("SANCFILE.dat");

    // WS-AML-THRESHOLDS constants
    private static final BigDecimal WS_LARGE_TXN_AMT = new BigDecimal("10000.00");
    private static final BigDecimal WS_VERY_LARGE_AMT = new BigDecimal("50000.00");
    private static final String WS_HIGH_RISK_COUNTRIES = "IRN PRK SYR YEM IRQ AFG SOM SDN LBY VEN MMR CUB";

    // Working storage variables
    private String wsNameNormalized = " ".repeat(55);
    private int wsRiskScore = 0;
    private String wsSanctionsHit = "N";
    private String wsPepHit = "N";
    private String wsLargeTxnFlag = "N";
    private String wsHighRiskCountry = "N";
    private String wsListDesc = " ".repeat(20);
    private String wsFileOpened = "N";

    // File status simulation
    private String wsSancFs = "  "; // 2 chars, file status

    // Sanctions file reader and writer
    private BufferedReader sanctionsFileReader;

    // Current sanctions record read from file
    private SanctionsRecord sanctionsRecord = new SanctionsRecord();

    public void main(LkAmlRequest lkAmlRequest, LkAmlResponse lkAmlResponse) {
        // Initialize response and working storage
        lkRespClearSet(lkAmlResponse, "Y");
        lkRespScoreSet(lkAmlResponse, 0);
        lkRespReasonSet(lkAmlResponse, " ".repeat(60));
        wsSanctionsHit = "N";
        wsPepHit = "N";
        wsLargeTxnFlag = "N";
        wsHighRiskCountry = "N";
        wsRiskScore = 0;

        normalizeName(lkAmlRequest);
        openSanctions();
        if ("Y".equals(wsFileOpened)) {
            checkSanctionsName();
            checkSanctionsCin();
            closeSanctions();
        }
        checkAmount(lkAmlRequest);
        checkNationality(lkAmlRequest);
        computeFinalDecision(lkAmlResponse);
    }

    private void normalizeName(LkAmlRequest lkAmlRequest) {
        String name = lkReqNameGet(lkAmlRequest);
        if (name == null) {
            wsNameNormalized = " ".repeat(55);
            return;
        }
        // Move LK-REQ-NAME to WS-NAME-NORMALIZED
        String normalized = name;

        // Convert to uppercase
        normalized = normalized.toUpperCase();

        // Replace '.', ',', '-' with space
        normalized = normalized.replace('.', ' ')
                               .replace(',', ' ')
                               .replace('-', ' ');

        // Trim trailing spaces and pad to 55 chars (right padded with spaces)
        normalized = rtrim(normalized);
        if (normalized.length() > 55) {
            normalized = normalized.substring(0, 55);
        } else {
            normalized = String.format("%-" + 55 + "s", normalized);
        }
        wsNameNormalized = normalized;
    }

    private void openSanctions() {
        try {
            sanctionsFileReader = Files.newBufferedReader(SANCTIONS_FILE_PATH, StandardCharsets.US_ASCII);
            wsSancFs = "00"; // SANC-FS-OK
            wsFileOpened = "Y";
        } catch (IOException e) {
            wsSancFs = "23"; // SANC-FS-NOTFOUND
            wsFileOpened = "N";
        }
    }

    private void checkSanctionsName() {
        // Move WS-NAME-NORMALIZED to SANC-NAME-KEY
        sanctionsRecord.sancNameKey = wsNameNormalized;

        // Read SANCTIONS-FILE keyed by SANC-NAME-KEY
        // Since file is indexed by name key, simulate by scanning file for matching name key
        try {
            sanctionsFileReader.close();
            sanctionsFileReader = Files.newBufferedReader(SANCTIONS_FILE_PATH, StandardCharsets.US_ASCII);
            String line;
            boolean found = false;
            while ((line = sanctionsFileReader.readLine()) != null) {
                SanctionsRecord record = SanctionsRecord.fromFixedWidth(line);
                if (record.sancNameKey.equals(sanctionsRecord.sancNameKey)) {
                    sanctionsRecord = record;
                    found = true;
                    break;
                }
            }
            if (found) {
                wsSanctionsHit = "Y";
                if (sanctionsRecord.sancPepList()) {
                    wsPepHit = "Y";
                    wsListDesc = "PEP LIST" + " ".repeat(20 - "PEP LIST".length());
                    wsRiskScore += 50;
                } else if (sanctionsRecord.sancUnList()) {
                    wsListDesc = "UN SANCTIONS" + " ".repeat(20 - "UN SANCTIONS".length());
                    wsRiskScore += 200;
                } else if (sanctionsRecord.sancEuList()) {
                    wsListDesc = "EU SANCTIONS" + " ".repeat(20 - "EU SANCTIONS".length());
                    wsRiskScore += 200;
                } else if (sanctionsRecord.sancOfacList()) {
                    wsListDesc = "OFAC SANCTIONS" + " ".repeat(20 - "OFAC SANCTIONS".length());
                    wsRiskScore += 200;
                } else if (sanctionsRecord.sancTnList()) {
                    wsListDesc = "BCT WATCHLIST" + " ".repeat(20 - "BCT WATCHLIST".length());
                    wsRiskScore += 200;
                }
                // Compose LK-RESP-REASON = "HIT " + WS-LIST-DESC + " SEVERITY " + SANC-SEVERITY
                String reason = "HIT " + wsListDesc.trim() + " SEVERITY " + sanctionsRecord.sancSeverity;
                reason = padRight(reason, 60);
                lkRespReasonSet(reason);
            }
        } catch (IOException e) {
            // On error, do nothing, no hit
        }
    }

    private void checkSanctionsCin() {
        if ("Y".equals(wsSanctionsHit)) {
            return; // EXIT PARAGRAPH
        }
        sanctionsRecord.sancCin = lkReqCin;
        // Read SANCTIONS-FILE keyed by SANC-CIN (alternate key with duplicates)
        // Simulate by scanning file for matching CIN
        try {
            sanctionsFileReader.close();
            sanctionsFileReader = Files.newBufferedReader(SANCTIONS_FILE_PATH, StandardCharsets.US_ASCII);
            String line;
            boolean found = false;
            while ((line = sanctionsFileReader.readLine()) != null) {
                SanctionsRecord record = SanctionsRecord.fromFixedWidth(line);
                if (record.sancCin.equals(sanctionsRecord.sancCin)) {
                    sanctionsRecord = record;
                    found = true;
                    break;
                }
            }
            if (found) {
                wsSanctionsHit = "Y";
                wsRiskScore += 150;
                String reason = "CIN MATCH ON SANCTIONS LIST";
                reason = padRight(reason, 60);
                lkRespReasonSet(reason);
            }
        } catch (IOException e) {
            // On error, do nothing
        }
    }

    private void closeSanctions() {
        if (sanctionsFileReader != null) {
            try {
                sanctionsFileReader.close();
            } catch (IOException e) {
                // ignore
            }
        }
    }

    private void checkAmount(LkAmlRequest lkAmlRequest) {
        BigDecimal amount = lkReqAmountGet(lkAmlRequest);
        if (amount == null) {
            return;
        }
        if (amount.compareTo(WS_VERY_LARGE_AMT) > 0) {
            wsLargeTxnFlag = "Y";
            wsRiskScore += 80;
        } else if (amount.compareTo(WS_LARGE_TXN_AMT) > 0) {
            wsLargeTxnFlag = "Y";
            wsRiskScore += 30;
        }
    }

    private void checkNationality(LkAmlRequest lkAmlRequest) {
        if (wsRiskScore <= 0) {
            return;
        }
        String nationality = lkReqNationalityGet(lkAmlRequest);
        if (nationality == null) {
            return;
        }
        // Check if nationality is in high risk countries list
        // The COBOL INSPECT tallying is approximated by contains check for exact match
        // The COBOL condition checks if nationality equals one of the listed codes
        if (isHighRiskCountry(nationality)) {
            wsHighRiskCountry = "Y";
            wsRiskScore += 100;
        }
    }

    private void computeFinalDecision(LkAmlResponse lkAmlResponse) {
        if (wsRiskScore > 999) {
            wsRiskScore = 999;
        }
        lkRespScoreSet(lkAmlResponse, wsRiskScore);

        if ("Y".equals(wsSanctionsHit) && wsRiskScore > 150) {
            lkRespClearSet(lkAmlResponse, "N");
        } else if (wsRiskScore >= 300) {
            lkRespClearSet(lkAmlResponse, "N");
            if (isSpaces(lkRespReasonGet(lkAmlResponse))) {
                lkRespReasonSet(lkAmlResponse, padRight("HIGH AML RISK SCORE", 60));
            }
        } else if (wsRiskScore >= 150) {
            lkRespClearSet(lkAmlResponse, "C");
            if (isSpaces(lkRespReasonGet(lkAmlResponse))) {
                lkRespReasonSet(lkAmlResponse, padRight("MANUAL REVIEW REQUIRED", 60));
            }
        } else {
            lkRespClearSet(lkAmlResponse, "Y");
            lkRespReasonSet(lkAmlResponse, padRight("AML CLEAR", 60));
        }
    }

    // Helper methods and classes

    private static String rtrim(String s) {
        int len = s.length();
        int idx = len;
        while (idx > 0 && s.charAt(idx - 1) == ' ') {
            idx--;
        }
        return s.substring(0, idx);
    }

    private static String padRight(String s, int n) {
        if (s.length() >= n) {
            return s.substring(0, n);
        }
        return String.format("%-" + n + "s", s);
    }

    private static boolean isSpaces(String s) {
        if (s == null) return true;
        for (int i = 0; i < s.length(); i++) {
            if (s.charAt(i) != ' ') {
                return false;
            }
        }
        return true;
    }

    private boolean isHighRiskCountry(String nationality) {
        // The COBOL list: IRN PRK SYR YEM IRQ AFG SOM SDN LBY VEN MMR CUB
        // Check exact match ignoring case
        String[] countries = WS_HIGH_RISK_COUNTRIES.split(" ");
        for (String c : countries) {
            if (c.equalsIgnoreCase(nationality)) {
                return true;
            }
        }
        return false;
    }

    // Accessors for linkage fields (simulate linkage section fields)

    private String lkReqNameGet(LkAmlRequest req) {
        return req.lkReqName;
    }

    private String lkReqCinGet(LkAmlRequest req) {
        return req.lkReqCin;
    }

    private BigDecimal lkReqAmountGet(LkAmlRequest req) {
        return req.lkReqAmount;
    }

    private String lkReqNationalityGet(LkAmlRequest req) {
        return req.lkReqNationality;
    }

    private void lkRespClearSet(LkAmlResponse resp, String value) {
        resp.lkRespClear = value;
    }

    private void lkRespReasonSet(LkAmlResponse resp, String value) {
        resp.lkRespReason = value;
    }

    private void lkRespReasonSet(String value) {
        // Set LK-RESP-REASON in working storage context (simulate linkage)
        // This method is used only internally to set the response reason string
        // We keep a temporary field for this purpose
        lkRespReasonTemp = value;
    }

    private String lkRespReasonGet(LkAmlResponse resp) {
        return resp.lkRespReason;
    }

    private void lkRespScoreSet(LkAmlResponse resp, int value) {
        resp.lkRespScore = value;
    }

    // Temporary storage for LK-RESP-REASON during processing
    private String lkRespReasonTemp = " ".repeat(60);

    // Linkage classes

    public static class LkAmlRequest {
        public int lkReqCustId;
        public String lkReqCin; // X(8)
        public String lkReqName; // X(55)
        public int lkReqDob;
        public String lkReqNationality; // X(3)
        public BigDecimal lkReqAmount; // 9(11)V99
    }

    public static class LkAmlResponse {
        public String lkRespClear; // X(1)
        public int lkRespScore; // 9(3)
        public String lkRespReason; // X(60)
    }

    // Sanctions record class representing a fixed-width record of 200 chars
    public static class SanctionsRecord {
        public String sancNameKey; // X(55)
        public String sancCin; // X(8)
        public int sancDob; // 9(8)
        public String sancNationality; // X(3)
        public String sancListCode; // X(3)
        public int sancSeverity; // 9(1)
        public String sancReason; // X(60)
        public int sancListDate; // 9(8)
        public String sancFiller; // X(54)

        public static SanctionsRecord fromFixedWidth(String line) {
            SanctionsRecord rec = new SanctionsRecord();
            if (line.length() < 200) {
                line = padRight(line, 200);
            }
            rec.sancNameKey = line.substring(0, 55);
            rec.sancCin = line.substring(55, 63);
            rec.sancDob = parseIntSafe(line.substring(63, 71));
            rec.sancNationality = line.substring(71, 74);
            rec.sancListCode = line.substring(74, 77);
            rec.sancSeverity = parseIntSafe(line.substring(77, 78));
            rec.sancReason = line.substring(78, 138);
            rec.sancListDate = parseIntSafe(line.substring(138, 146));
            rec.sancFiller = line.substring(146, 200);
            return rec;
        }

        private static int parseIntSafe(String s) {
            try {
                return Integer.parseInt(s.trim());
            } catch (NumberFormatException e) {
                return 0;
            }
        }

        // Condition 88 equivalents
        public boolean sancUnList() {
            return "UNL".equals(sancListCode);
        }

        public boolean sancEuList() {
            return "EUL".equals(sancListCode);
        }

        public boolean sancOfacList() {
            return "OFC".equals(sancListCode);
        }

        public boolean sancTnList() {
            return "TUN".equals(sancListCode);
        }

        public boolean sancPepList() {
            return "PEP".equals(sancListCode);
        }
    }
}
