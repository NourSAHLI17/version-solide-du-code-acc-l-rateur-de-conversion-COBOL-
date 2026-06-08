package com.modernized.autoprem;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;

/**
 * AUTOPREM — auto insurance premium rating (STAR Assurance).
 * Paragraph-aligned Java for behavioral parity with GnuCOBOL AUTOPREM.cbl.
 */
public class Autoprem {

    private static final int QUOTE_CAPACITY = 10;
    private static final int MIN_DRIVER_AGE = 18;
    private static final int MAX_DRIVER_AGE = 80;
    private static final int HIGH_RISK_LIMIT = 3;
    // PIC 9(7)V99 — WS-MIN-PREMIUM-MILL / WS-MAX-PREMIUM-MILL
    private static final BigDecimal MIN_PREMIUM = CobolNumericStorage.pic9_7v99(new BigDecimal("250.00"), false);
    private static final BigDecimal MAX_PREMIUM = CobolNumericStorage.pic9_7v99(new BigDecimal("25000.00"), false);
    // PIC 9(2)V99
    private static final BigDecimal TVA_RATE = new BigDecimal("19.00");
    private static final BigDecimal PARAFISCAL_RATE = new BigDecimal("5.00");
    private static final BigDecimal ACCIDENT_UNIT = new BigDecimal("75.00");
    private static final BigDecimal EXPERIENCE_DISCOUNT = new BigDecimal("0.85");

    // PIC 9(5)V99 — WS-RATE-*
    private static final BigDecimal RATE_TOURISME = CobolNumericStorage.pic9_5v99(new BigDecimal("480.00"), false);
    private static final BigDecimal RATE_UTILITAIRE = CobolNumericStorage.pic9_5v99(new BigDecimal("620.00"), false);
    private static final BigDecimal RATE_MOTO = CobolNumericStorage.pic9_5v99(new BigDecimal("320.00"), false);
    private static final BigDecimal RATE_CAMION = CobolNumericStorage.pic9_5v99(new BigDecimal("950.00"), false);
    private static final BigDecimal RATE_LUXE = CobolNumericStorage.pic9_5v99(new BigDecimal("1850.00"), false);

    private static class Quote {
        int quoteId;
        String clientName;
        int driverAge;
        int licenseYears;
        String vehicleCategory;
        int vehiclePower;
        BigDecimal vehicleValue;
        String coverage;
        BigDecimal crmCoef;
        String governorate;
        int accidents3Y;
    }

    private static class Premium {
        int quoteId;
        // PIC 9(7)V999
        BigDecimal basePremium;
        // PIC 9(1)V99
        BigDecimal ageCoef;
        BigDecimal powerCoef;
        BigDecimal coverageCoef;
        BigDecimal regionCoef;
        BigDecimal accidentLoad;
        BigDecimal netPremium;
        BigDecimal tva;
        BigDecimal parafiscal;
        BigDecimal totalPremium;
        String decision;
        String rejectionReason;
    }

    private final List<Quote> quotes = new ArrayList<>(QUOTE_CAPACITY);
    private final List<Premium> premiums = new ArrayList<>(QUOTE_CAPACITY);
    private int acceptedCount;
    private int rejectedCount;
    private int manualCount;
    // PIC 9(9)V99
    private BigDecimal totalNetPremium;
    private BigDecimal totalGrossPremium;

    public Autoprem() {
        this.totalNetPremium = BigDecimal.ZERO.setScale(2, RoundingMode.DOWN);
        this.totalGrossPremium = BigDecimal.ZERO.setScale(2, RoundingMode.DOWN);
    }

    public void run() {
        displayHeader();
        loadTestCases();
        processAllQuotes();
        displaySummary();
    }

    /** 1000-INITIALIZE / header DISPLAY */
    private void displayHeader() {
        System.out.println();
        System.out.println("=======================================");
        System.out.println("STAR ASSURANCE - CALCUL PRIMES AUTO");
        System.out.println("Version 1.4 - Tarif 2024");
        System.out.println("=======================================");
        System.out.println();
    }

    /** 1000-LOAD-TEST-CASES */
    private void loadTestCases() {
        addQuote(10000001, "BENSALAH AHMED", 22, 2, "TR", 6,
                new BigDecimal("25000.00"), "RC", new BigDecimal("1.00"), "TUN", 0);
        addQuote(10000002, "TRABELSI FATMA", 45, 22, "TR", 8,
                new BigDecimal("48000.00"), "TC", new BigDecimal("0.50"), "SFX", 0);
        addQuote(10000003, "CHAOUACHI MOEZ", 52, 30, "LX", 14,
                new BigDecimal("185000.00"), "TI", new BigDecimal("0.55"), "TUN", 0);
        addQuote(10000004, "GHARBI KARIM", 25, 5, "MT", 4,
                new BigDecimal("9500.00"), "RC", new BigDecimal("1.00"), "SOU", 1);
        addQuote(10000005, "TRANSPORT BELHAJ SARL", 38, 15, "CM", 20,
                new BigDecimal("145000.00"), "TC", new BigDecimal("0.85"), "BIZ", 0);
        addQuote(10000006, "JEBALI MEHDI", 17, 0, "TR", 5,
                new BigDecimal("18000.00"), "RC", new BigDecimal("1.00"), "TUN", 0);
        addQuote(10000007, "BOUAZIZ NESRINE", 28, 8, "TR", 7,
                new BigDecimal("32000.00"), "TC", new BigDecimal("2.50"), "NAB", 4);
        addQuote(10000008, "DRIDI RIDHA", 68, 45, "TR", 5,
                new BigDecimal("22000.00"), "TI", new BigDecimal("0.50"), "KEF", 0);
        addQuote(10000009, "KHELIFA SLIM", 35, 12, "UT", 10,
                new BigDecimal("65000.00"), "TC", new BigDecimal("0.75"), "SFX", 1);
        addQuote(10000010, "HAMROUNI LEILA", 82, 50, "TR", 6,
                new BigDecimal("28000.00"), "TC", new BigDecimal("0.50"), "TUN", 0);
    }

    private void addQuote(int quoteId, String clientName, int driverAge, int licenseYears,
                        String vehicleCategory, int vehiclePower, BigDecimal vehicleValue,
                        String coverage, BigDecimal crmCoef, String governorate, int accidents3Y) {
        Quote q = new Quote();
        q.quoteId = quoteId;
        q.clientName = clientName;
        q.driverAge = driverAge;
        q.licenseYears = licenseYears;
        q.vehicleCategory = vehicleCategory;
        q.vehiclePower = vehiclePower;
        q.vehicleValue = vehicleValue;
        q.coverage = coverage;
        q.crmCoef = CobolNumericStorage.pic9_1v99(crmCoef, false);
        q.governorate = governorate;
        q.accidents3Y = accidents3Y;
        quotes.add(q);

        Premium p = new Premium();
        p.quoteId = quoteId;
        p.decision = "";
        p.rejectionReason = "";
        premiums.add(p);
    }

    /** 2000-PROCESS-ALL-QUOTES */
    private void processAllQuotes() {
        for (int i = 0; i < quotes.size(); i++) {
            Quote q = quotes.get(i);
            Premium p = premiums.get(i);
            validateQuote(q, p);
            if ("REFUSE".equals(p.decision)) {
                displayRejected(q, p);
            } else {
                computePremium(q, p);
                applyLimits(p);
                computeTaxes(p);
                finalDecision(q, p);
                displayQuote(q, p);
            }
        }
    }

    /** 2100-VALIDATE-QUOTE */
    private void validateQuote(Quote q, Premium p) {
        p.quoteId = q.quoteId;
        p.rejectionReason = "";
        if (q.driverAge < MIN_DRIVER_AGE) {
            p.decision = "REFUSE";
            p.rejectionReason = "AGE CONDUCTEUR INFERIEUR A 18 ANS";
            rejectedCount++;
        } else if (q.driverAge > MAX_DRIVER_AGE) {
            p.decision = "REFUSE";
            p.rejectionReason = "AGE CONDUCTEUR DEPASSE 80 ANS";
            rejectedCount++;
        } else if (q.licenseYears == 0) {
            p.decision = "REFUSE";
            p.rejectionReason = "PERMIS DE CONDUIRE REQUIS";
            rejectedCount++;
        } else if (q.crmCoef.compareTo(CobolNumericStorage.pic9_1v99(new BigDecimal("3.50"), false)) > 0) {
            p.decision = "REFUSE";
            p.rejectionReason = "COEFFICIENT CRM TROP ELEVE";
            rejectedCount++;
        }
    }

    /** 2200-COMPUTE-PREMIUM */
    private void computePremium(Quote q, Premium p) {
        setBaseRate(q, p);
        computeAgeCoef(q, p);
        computePowerCoef(q, p);
        computeCoverageCoef(q, p);
        computeRegionCoef(q, p);
        computeAccidentLoad(q, p);

        BigDecimal product = p.basePremium
                .multiply(p.ageCoef)
                .multiply(p.powerCoef)
                .multiply(p.coverageCoef)
                .multiply(p.regionCoef)
                .multiply(q.crmCoef);
        p.netPremium = CobolNumericStorage.pic9_7v999(product.add(p.accidentLoad), true);
    }

    /** 2210-SET-BASE-RATE */
    private void setBaseRate(Quote q, Premium p) {
        BigDecimal rate;
        switch (q.vehicleCategory) {
            case "UT":
                rate = RATE_UTILITAIRE;
                break;
            case "MT":
                rate = RATE_MOTO;
                break;
            case "CM":
                rate = RATE_CAMION;
                break;
            case "LX":
                rate = RATE_LUXE;
                break;
            case "TR":
            default:
                rate = RATE_TOURISME;
                break;
        }
        p.basePremium = CobolNumericStorage.pic9_7v999(rate, false);
    }

    /** 2220-COMPUTE-AGE-COEF */
    private void computeAgeCoef(Quote q, Premium p) {
        BigDecimal coef;
        if (q.driverAge < 25) {
            coef = new BigDecimal("1.60");
        } else if (q.driverAge < 30) {
            coef = new BigDecimal("1.25");
        } else if (q.driverAge < 65) {
            coef = new BigDecimal("1.00");
        } else {
            coef = new BigDecimal("1.30");
        }
        p.ageCoef = CobolNumericStorage.pic9_1v99(coef, false);
        if (q.licenseYears >= 10 && q.driverAge < 65) {
            p.ageCoef = CobolNumericStorage.pic9_1v99(p.ageCoef.multiply(EXPERIENCE_DISCOUNT), false);
        }
    }

    /** 2230-COMPUTE-POWER-COEF */
    private void computePowerCoef(Quote q, Premium p) {
        BigDecimal coef;
        if (q.vehiclePower <= 4) {
            coef = new BigDecimal("0.85");
        } else if (q.vehiclePower <= 7) {
            coef = new BigDecimal("1.00");
        } else if (q.vehiclePower <= 10) {
            coef = new BigDecimal("1.20");
        } else if (q.vehiclePower <= 14) {
            coef = new BigDecimal("1.50");
        } else {
            coef = new BigDecimal("2.00");
        }
        p.powerCoef = CobolNumericStorage.pic9_1v99(coef, false);
    }

    /** 2240-COMPUTE-COVERAGE-COEF */
    private void computeCoverageCoef(Quote q, Premium p) {
        BigDecimal coef;
        switch (q.coverage) {
            case "TC":
                coef = new BigDecimal("1.80");
                break;
            case "TI":
                coef = new BigDecimal("3.20");
                break;
            case "RC":
            default:
                coef = new BigDecimal("1.00");
                break;
        }
        p.coverageCoef = CobolNumericStorage.pic9_1v99(coef, false);
    }

    /** 2250-COMPUTE-REGION-COEF */
    private void computeRegionCoef(Quote q, Premium p) {
        BigDecimal coef;
        switch (q.governorate) {
            case "TUN":
                coef = new BigDecimal("1.20");
                break;
            case "ARI":
                coef = new BigDecimal("1.15");
                break;
            case "BAR":
                coef = new BigDecimal("1.10");
                break;
            case "SFX":
            case "SOU":
                coef = new BigDecimal("1.05");
                break;
            case "NAB":
                coef = new BigDecimal("1.00");
                break;
            case "BIZ":
                coef = new BigDecimal("0.95");
                break;
            default:
                coef = new BigDecimal("0.90");
                break;
        }
        p.regionCoef = CobolNumericStorage.pic9_1v99(coef, false);
    }

    /** 2260-COMPUTE-ACCIDENT-LOAD — PIC 9(1)V99, COMPUTE ROUNDED = accidents * 75 */
    private void computeAccidentLoad(Quote q, Premium p) {
        if (q.accidents3Y == 0) {
            p.accidentLoad = CobolNumericStorage.pic9_1v99(BigDecimal.ZERO, false);
        } else {
            BigDecimal raw = new BigDecimal(q.accidents3Y).multiply(ACCIDENT_UNIT);
            p.accidentLoad = CobolNumericStorage.pic9_1v99(raw, true);
        }
    }

    /** 2300-APPLY-LIMITS */
    private void applyLimits(Premium p) {
        if (p.netPremium.compareTo(MIN_PREMIUM) < 0) {
            p.netPremium = CobolNumericStorage.pic9_7v999(MIN_PREMIUM, false);
        }
        if (p.netPremium.compareTo(MAX_PREMIUM) > 0) {
            p.netPremium = CobolNumericStorage.pic9_7v999(MAX_PREMIUM, false);
        }
    }

    /** 2400-COMPUTE-TAXES */
    private void computeTaxes(Premium p) {
        p.tva = CobolNumericStorage.pic9_7v999(
                p.netPremium.multiply(TVA_RATE).divide(new BigDecimal("100"), 10, RoundingMode.HALF_UP),
                true);
        p.parafiscal = CobolNumericStorage.pic9_7v999(
                p.netPremium.multiply(PARAFISCAL_RATE).divide(new BigDecimal("100"), 10, RoundingMode.HALF_UP),
                true);
        p.totalPremium = CobolNumericStorage.pic9_7v999(
                p.netPremium.add(p.tva).add(p.parafiscal),
                false);
    }

    /** 2500-FINAL-DECISION */
    private void finalDecision(Quote q, Premium p) {
        if (q.accidents3Y >= HIGH_RISK_LIMIT) {
            p.decision = "MANUEL";
            p.rejectionReason = "SINISTRES > 3 - REVUE MANUELLE REQUISE";
            manualCount++;
        } else if (q.crmCoef.compareTo(CobolNumericStorage.pic9_1v99(new BigDecimal("2.00"), false)) > 0) {
            p.decision = "MANUEL";
            p.rejectionReason = "CRM ELEVE - REVUE MANUELLE";
            manualCount++;
        } else {
            p.decision = "ACCEPTE";
            acceptedCount++;
            totalNetPremium = CobolNumericStorage.pic9_9v99(totalNetPremium.add(p.netPremium), false);
            totalGrossPremium = CobolNumericStorage.pic9_9v99(totalGrossPremium.add(p.totalPremium), false);
        }
    }

    /** 4000-DISPLAY-REJECTED */
    private void displayRejected(Quote q, Premium p) {
        System.out.println();
        System.out.println("DEVIS " + q.quoteId + " --- REFUSE");
        System.out.println("  Client: " + q.clientName);
        System.out.println("  Motif : " + p.rejectionReason);
    }

    /** 4100-DISPLAY-QUOTE */
    private void displayQuote(Quote q, Premium p) {
        System.out.println();
        System.out.println("DEVIS " + q.quoteId + " --- " + p.decision);
        System.out.println("  Client    : " + q.clientName);
        System.out.println("  Age conducteur: " + CobolPicFormat.picZz9(q.driverAge)
                + " ans   Puissance: " + CobolPicFormat.picZ9(q.vehiclePower) + " CV");
        System.out.println("  Categorie : " + q.vehicleCategory
                + "    Couverture: " + q.coverage
                + "    Gouvernorat: " + q.governorate);
        System.out.println("  Prime base : " + CobolPicFormat.picZzZzz999(p.basePremium) + " TND");
        System.out.println("    Coef age      : " + CobolPicFormat.picZ99(p.ageCoef));
        System.out.println("    Coef puissance: " + CobolPicFormat.picZ99(p.powerCoef));
        System.out.println("    Coef garantie : " + CobolPicFormat.picZ99(p.coverageCoef));
        System.out.println("    Coef region   : " + CobolPicFormat.picZ99(p.regionCoef));
        System.out.println("    CRM           : " + CobolPicFormat.picZ99(q.crmCoef));
        System.out.println("  Prime nette: " + CobolPicFormat.picZzZzz999(p.netPremium) + " TND");
        System.out.println("    TVA 19 pct   : " + CobolPicFormat.picZzZzz999(p.tva) + " TND");
        System.out.println("    Parafiscal 5 : " + CobolPicFormat.picZzZzz999(p.parafiscal) + " TND");
        System.out.println("  PRIME TTC  : " + CobolPicFormat.picZzZzz999(p.totalPremium) + " TND");
        if ("MANUEL".equals(p.decision)) {
            System.out.println("  Note: " + p.rejectionReason);
        }
    }

    /** 3000-DISPLAY-SUMMARY */
    private void displaySummary() {
        System.out.println();
        System.out.println("=======================================");
        System.out.println("RECAPITULATIF DU LOT");
        System.out.println("=======================================");
        System.out.println("  DEVIS ACCEPTES   : " + CobolPicFormat.pic9_3(acceptedCount));
        System.out.println("  DEVIS REFUSES    : " + CobolPicFormat.pic9_3(rejectedCount));
        System.out.println("  REVUE MANUELLE   : " + CobolPicFormat.pic9_3(manualCount));
        System.out.println("  PRIME NETTE TOT  : " + CobolPicFormat.picZzZzz999(totalNetPremium) + " TND");
        System.out.println("  PRIME TTC TOTALE : " + CobolPicFormat.picZzZzz999(totalGrossPremium) + " TND");
        System.out.println("=======================================");
    }

    public static void main(String[] args) {
        new Autoprem().run();
    }
}

/** COBOL PIC storage simulation (truncation / ROUNDED) for converted programs. */
final class CobolNumericStorage {
    private CobolNumericStorage() {}

    static BigDecimal pic9_7v999(BigDecimal value, boolean rounded) {
        return store(value, 7, 3, rounded);
    }

    static BigDecimal pic9_7v99(BigDecimal value, boolean rounded) {
        return store(value, 7, 2, rounded);
    }

    static BigDecimal pic9_1v99(BigDecimal value, boolean rounded) {
        return store(value, 1, 2, rounded);
    }

    static BigDecimal pic9_5v99(BigDecimal value, boolean rounded) {
        return store(value, 5, 2, rounded);
    }

    static BigDecimal pic9_9v99(BigDecimal value, boolean rounded) {
        return store(value, 9, 2, rounded);
    }

    static BigDecimal store(BigDecimal value, int integerDigits, int decimalPlaces, boolean rounded) {
        if (value == null) {
            return BigDecimal.ZERO.setScale(decimalPlaces, RoundingMode.DOWN);
        }
        RoundingMode mode = rounded ? RoundingMode.HALF_UP : RoundingMode.DOWN;
        BigDecimal scaled = value.setScale(decimalPlaces, mode);
        BigDecimal limit = BigDecimal.TEN.pow(integerDigits).subtract(BigDecimal.ONE.movePointLeft(decimalPlaces));
        while (scaled.abs().compareTo(limit) > 0) {
            scaled = scaled.remainder(BigDecimal.TEN.pow(integerDigits));
            scaled = scaled.setScale(decimalPlaces, RoundingMode.DOWN);
        }
        return scaled;
    }
}

/** Locale-independent COBOL edited-picture formatting (Z/9 editing). */
final class CobolPicFormat {
    private CobolPicFormat() {}

    static String picZzZzz999(BigDecimal value) {
        if (value == null) {
            value = BigDecimal.ZERO;
        }
        BigDecimal scaled = value.setScale(3, RoundingMode.HALF_UP);
        String sign = scaled.signum() < 0 ? "-" : "";
        BigDecimal abs = scaled.abs();
        String digits = abs.movePointRight(3).toBigInteger().toString();
        while (digits.length() <= 3) {
            digits = "0" + digits;
        }
        String frac = digits.substring(digits.length() - 3);
        String whole = digits.substring(0, digits.length() - 3);
        String core = sign + groupThousands(whole.isEmpty() ? "0" : whole) + "." + frac;
        return padField(core, 10);
    }

    static String picZ99(BigDecimal value) {
        if (value == null) {
            value = BigDecimal.ZERO;
        }
        BigDecimal scaled = value.setScale(2, RoundingMode.HALF_UP);
        String sign = scaled.signum() < 0 ? "-" : "";
        BigDecimal abs = scaled.abs();
        String digits = abs.movePointRight(2).toBigInteger().toString();
        while (digits.length() <= 2) {
            digits = "0" + digits;
        }
        String frac = digits.substring(digits.length() - 2);
        String whole = digits.substring(0, digits.length() - 2);
        String wholeOut = whole.equals("0") ? "" : whole;
        return padField(sign + wholeOut + "." + frac, 4);
    }

    static String picZz9(int value) {
        return padEdited(String.valueOf(Math.max(0, value)), 3);
    }

    static String picZ9(int value) {
        return padEdited(String.valueOf(Math.max(0, value)), 2);
    }

    static String pic9_3(int value) {
        return String.format("%03d", Math.max(0, value));
    }

    private static String groupThousands(String whole) {
        StringBuilder sb = new StringBuilder();
        int len = whole.length();
        for (int i = 0; i < len; i++) {
            if (i > 0 && (len - i) % 3 == 0) {
                sb.append(',');
            }
            sb.append(whole.charAt(i));
        }
        return sb.toString();
    }

    private static String padEdited(String digits, int width) {
        if (digits.length() >= width) {
            return digits.substring(digits.length() - width);
        }
        return " ".repeat(width - digits.length()) + digits;
    }

    private static String padField(String text, int width) {
        if (text.length() >= width) {
            return text.substring(text.length() - width);
        }
        return " ".repeat(width - text.length()) + text;
    }
}
