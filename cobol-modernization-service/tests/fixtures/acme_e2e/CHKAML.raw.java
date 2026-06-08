package com.modernized.chkaml;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashMap;
import java.util.Map;

/**
 // CHKAML - AML (Anti-Money Laundering) screening sub-program.
 // Performs sanctions list lookup, PEP screening, adverse media screening,
 // transaction amount threshold check, and high-risk nationality check.
 // Returns clearance flag, risk score, and reason.
 //
 // BCT REF: Loi 2015-26 (LBA/FT), Decret 2018-1129
 // Version: 3.1
 */
public class ChkAmlService {

    // Working Storage
    private String wsSancFs;
    private final WsAmlThresholds wsAmlThresholds;
    private final WsWork wsWork;
    
    // File data
    private Map<String, SanctionsRecord> sanctionsNameIndex;
    private Map<String, SanctionsRecord> sanctionsCinIndex;
    private boolean sanctionsFileLoaded;

    public ChkAmlService() {
        this.wsSancFs = "  ";
        this.wsAmlThresholds = new WsAmlThresholds();
        this.wsWork = new WsWork();
        this.sanctionsNameIndex = new HashMap<>();
        this.sanctionsCinIndex = new HashMap<>();
        this.sanctionsFileLoaded = false;
    }

    /**
     // Main entry point - processes AML request and populates response.
     */
    public void execute(LkAmlRequest request, LkAmlResponse response) {
        // Initialize response
        response.lkRespClear = "Y";
        response.lkRespScore = 0;
        response.lkRespReason = padRight("", 60);
        
        // Initialize work flags
        wsWork.wsSanctionsHit = "N";
        wsWork.wsPepHit = "N";
        wsWork.wsLargeTxnFlag = "N";
        wsWork.wsHighRiskCountry = "N";
        wsWork.wsRiskScore = 0;

        normalizeName(request);
        openSanctions();
        
        if (wsWork.wsFileOpened.equals("Y")) {
            checkSanctionsName(request, response);
            checkSanctionsCin(request, response);
            closeSanctions();
        }
        
        checkAmount(request);
        checkNationality(request);
        computeFinalDecision(response);
    }

    /**
     // 1000-NORMALIZE-NAME
     // INSPECT and TRANSFORM the name for comparison: uppercase,
     // trim trailing spaces, remove special chars.
     */
    private void normalizeName(LkAmlRequest request) {
        wsWork.wsNameNormalized = request.lkReqName;
        wsWork.wsNameNormalized = wsWork.wsNameNormalized.toUpperCase();
        wsWork.wsNameNormalized = wsWork.wsNameNormalized.replace('.', ' ');
        wsWork.wsNameNormalized = wsWork.wsNameNormalized.replace(',', ' ');
        wsWork.wsNameNormalized = wsWork.wsNameNormalized.replace('-', ' ');
        wsWork.wsNameNormalized = padRight(wsWork.wsNameNormalized, 55);
    }

    /**
     // 2000-OPEN-SANCTIONS
     */
    private void openSanctions() {
        String fileName = System.getProperty("SANCFILE", "SANCFILE.dat");
        
        try {
            loadSanctionsFile(fileName);
            wsSancFs = "00";
            wsWork.wsFileOpened = "Y";
        } catch (IOException e) {
            wsSancFs = "35";
            wsWork.wsFileOpened = "N";
        }
    }

    /**
     // Load sanctions file and build in-memory indexes
     */
    private void loadSanctionsFile(String fileName) throws IOException {
        sanctionsNameIndex.clear();
        sanctionsCinIndex.clear();
        
        try (BufferedReader reader = new BufferedReader(new FileReader(fileName))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.length() >= 200) {
                    SanctionsRecord record = parseSanctionsRecord(line);
                    sanctionsNameIndex.put(record.sancNameKey, record);
                    if (!sanctionsCinIndex.containsKey(record.sancCin)) {
                        sanctionsCinIndex.put(record.sancCin, record);
                    }
                }
            }
        }
        sanctionsFileLoaded = true;
    }

    /**
     // Parse fixed-width sanctions record (200 characters)
     */
    private SanctionsRecord parseSanctionsRecord(String line) {
        SanctionsRecord record = new SanctionsRecord();
        
        record.sancNameKey = line.substring(0, 55);
        record.sancCin = line.substring(55, 63);
        record.sancDob = Integer.parseInt(line.substring(63, 71).trim());
        record.sancNationality = line.substring(71, 74);
        record.sancListCode = line.substring(74, 77);
        record.sancSeverity = Integer.parseInt(line.substring(77, 78).trim());
        record.sancReason = line.substring(78, 138);
        record.sancListDate = Integer.parseInt(line.substring(138, 146).trim());
        record.sancFiller = line.substring(146, 200);
        
        return record;
    }

    /**
     // 3000-CHECK-SANCTIONS-NAME
     */
    private void checkSanctionsName(LkAmlRequest request, LkAmlResponse response) {
        String key = wsWork.wsNameNormalized;
        SanctionsRecord record = sanctionsNameIndex.get(key);
        
        if (record != null) {
            wsWork.wsSanctionsHit = "Y";
            
            if (record.sancListCode.equals("PEP")) {
                wsWork.wsPepHit = "Y";
                wsWork.wsListDesc = padRight("PEP LIST", 20);
                wsWork.wsRiskScore += 50;
            } else if (record.sancListCode.equals("UNL")) {
                wsWork.wsListDesc = padRight("UN SANCTIONS", 20);
                wsWork.wsRiskScore += 200;
            } else if (record.sancListCode.equals("EUL")) {
                wsWork.wsListDesc = padRight("EU SANCTIONS", 20);
                wsWork.wsRiskScore += 200;
            } else if (record.sancListCode.equals("OFC")) {
                wsWork.wsListDesc = padRight("OFAC SANCTIONS", 20);
                wsWork.wsRiskScore += 200;
            } else if (record.sancListCode.equals("TUN")) {
                wsWork.wsListDesc = padRight("BCT WATCHLIST", 20);
                wsWork.wsRiskScore += 200;
            }
            
            StringBuilder reason = new StringBuilder();
            reason.append("HIT ").append(wsWork.wsListDesc.trim())
                  .append(" SEVERITY ").append(record.sancSeverity);
            response.lkRespReason = padRight(reason.toString(), 60);
        }
    }

    /**
     // 3100-CHECK-SANCTIONS-CIN
     */
    private void checkSanctionsCin(LkAmlRequest request, LkAmlResponse response) {
        if (wsWork.wsSanctionsHit.equals("Y")) {
            return;
        }
        
        SanctionsRecord record = sanctionsCinIndex.get(request.lkReqCin);
        
        if (record != null) {
            wsWork.wsSanctionsHit = "Y";
            wsWork.wsRiskScore += 150;
            response.lkRespReason = padRight("CIN MATCH ON SANCTIONS LIST", 60);
        }
    }

    /**
     // 4000-CLOSE-SANCTIONS
     */
    private void closeSanctions() {
        // No action needed for in-memory index approach
        wsSancFs = "00";
    }

    /**
     // 5000-CHECK-AMOUNT
     */
    private void checkAmount(LkAmlRequest request) {
        if (request.lkReqAmount.compareTo(wsAmlThresholds.wsVeryLargeAmt) > 0) {
            wsWork.wsLargeTxnFlag = "Y";
            wsWork.wsRiskScore += 80;
        } else if (request.lkReqAmount.compareTo(wsAmlThresholds.wsLargeTxnAmt) > 0) {
            wsWork.wsLargeTxnFlag = "Y";
            wsWork.wsRiskScore += 30;
        }
    }

    /**
     // 6000-CHECK-NATIONALITY
     */
    private void checkNationality(LkAmlRequest request) {
        String nationality = request.lkReqNationality;
        int countBefore = wsWork.wsRiskScore;
        
        // INSPECT TALLYING - count occurrences of nationality in high-risk list
        String[] highRiskList = {"IRN", "PRK", "SYR", "YEM", "IRQ", "AFG", 
                                  "SOM", "SDN", "LBY", "VEN", "MMR", "CUB"};
        
        for (String country : highRiskList) {
            if (nationality.equals(country)) {
                wsWork.wsHighRiskCountry = "Y";
                wsWork.wsRiskScore += 100;
                break;
            }
        }
    }

    /**
     // 7000-COMPUTE-FINAL-DECISION
     */
    private void computeFinalDecision(LkAmlResponse response) {
        if (wsWork.wsRiskScore > 999) {
            wsWork.wsRiskScore = 999;
        }
        
        response.lkRespScore = wsWork.wsRiskScore;
        
        if (wsWork.wsSanctionsHit.equals("Y") && wsWork.wsRiskScore > 150) {
            response.lkRespClear = "N";
        } else if (wsWork.wsRiskScore >= 300) {
            response.lkRespClear = "N";
            if (response.lkRespReason.trim().isEmpty()) {
                response.lkRespReason = padRight("HIGH AML RISK SCORE", 60);
            }
        } else if (wsWork.wsRiskScore >= 150) {
            response.lkRespClear = "C";
            if (response.lkRespReason.trim().isEmpty()) {
                response.lkRespReason = padRight("MANUAL REVIEW REQUIRED", 60);
            }
        } else {
            response.lkRespClear = "Y";
            response.lkRespReason = padRight("AML CLEAR", 60);
        }
    }

    private String padRight(String str, int length) {
        if (str == null) str = "";
        if (str.length() >= length) {
            return str.substring(0, length);
        }
        StringBuilder sb = new StringBuilder(str);
        while (sb.length() < length) {
            sb.append(' ');
        }
        return sb.toString();
    }

    // Data Transfer Objects

    public static class LkAmlRequest {
        public int lkReqCustId;
        public String lkReqCin;
        public String lkReqName;
        public int lkReqDob;
        public String lkReqNationality;
        public BigDecimal lkReqAmount;

        public LkAmlRequest() {
            this.lkReqCustId = 0;
            this.lkReqCin = padRight("", 8);
            this.lkReqName = padRight("", 55);
            this.lkReqDob = 0;
            this.lkReqNationality = padRight("", 3);
            this.lkReqAmount = BigDecimal.ZERO;
        }

        private static String padRight(String str, int length) {
            if (str == null) str = "";
            if (str.length() >= length) return str.substring(0, length);
            StringBuilder sb = new StringBuilder(str);
            while (sb.length() < length) sb.append(' ');
            return sb.toString();
        }
    }

    public static class LkAmlResponse {
        public String lkRespClear;
        public int lkRespScore;
        public String lkRespReason;

        public LkAmlResponse() {
            this.lkRespClear = " ";
            this.lkRespScore = 0;
            this.lkRespReason = padRight("", 60);
        }

        private static String padRight(String str, int length) {
            if (str == null) str = "";
            if (str.length() >= length) return str.substring(0, length);
            StringBuilder sb = new StringBuilder(str);
            while (sb.length() < length) sb.append(' ');
            return sb.toString();
        }
    }

    public static class SanctionsRecord {
        public String sancNameKey;
        public String sancCin;
        public int sancDob;
        public String sancNationality;
        public String sancListCode;
        public int sancSeverity;
        public String sancReason;
        public int sancListDate;
        public String sancFiller;

        public SanctionsRecord() {
            this.sancNameKey = "";
            this.sancCin = "";
            this.sancDob = 0;
            this.sancNationality = "";
            this.sancListCode = "";
            this.sancSeverity = 0;
            this.sancReason = "";
            this.sancListDate = 0;
            this.sancFiller = "";
        }
    }

    public static class WsAmlThresholds {
        public BigDecimal wsLargeTxnAmt;
        public BigDecimal wsVeryLargeAmt;
        public String wsHighRiskCountries;

        public WsAmlThresholds() {
            this.wsLargeTxnAmt = new BigDecimal("10000.00");
            this.wsVeryLargeAmt = new BigDecimal("50000.00");
            this.wsHighRiskCountries = "IRN PRK SYR YEM IRQ AFG SOM SDN LBY VEN MMR CUB".concat("                            ");
        }
    }

    public static class WsWork {
        public String wsNameNormalized;
        public int wsRiskScore;
        public String wsSanctionsHit;
        public String wsPepHit;
        public String wsLargeTxnFlag;
        public String wsHighRiskCountry;
        public String wsListDesc;
        public String wsFileOpened;

        public WsWork() {
            this.wsNameNormalized = padRight("", 55);
            this.wsRiskScore = 0;
            this.wsSanctionsHit = "N";
            this.wsPepHit = "N";
            this.wsLargeTxnFlag = "N";
            this.wsHighRiskCountry = "N";
            this.wsListDesc = padRight("", 20);
            this.wsFileOpened = "N";
        }

        private static String padRight(String str, int length) {
            if (str == null) str = "";
            if (str.length() >= length) return str.substring(0, length);
            StringBuilder sb = new StringBuilder(str);
            while (sb.length() < length) sb.append(' ');
            return sb.toString();
        }
    }
}
