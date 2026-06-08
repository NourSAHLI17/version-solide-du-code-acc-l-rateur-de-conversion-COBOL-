package com.modernized.autoprem;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;

public class AutopremCalculator {

    private static final int QUOTE_CAPACITY = 10;
    private static final int MIN_DRIVER_AGE = 18;
    private static final int MAX_DRIVER_AGE = 80;
    private static final int HIGH_RISK_LIMIT = 3;
    private static final BigDecimal MIN_PREMIUM = new BigDecimal("250.00");
    private static final BigDecimal MAX_PREMIUM = new BigDecimal("25000.00");
    private static final BigDecimal TVA_RATE = new BigDecimal("19.00");
    private static final BigDecimal PARAFISCAL_RATE = new BigDecimal("5.00");
    private static final BigDecimal ACCIDENT_SURCHARGE = new BigDecimal("75.00");
    private static final BigDecimal EXPERIENCE_DISCOUNT = new BigDecimal("0.85");

    private static final BigDecimal RATE_TOURISME = new BigDecimal("480.00");
    private static final BigDecimal RATE_UTILITAIRE = new BigDecimal("620.00");
    private static final BigDecimal RATE_MOTO = new BigDecimal("320.00");
    private static final BigDecimal RATE_CAMION = new BigDecimal("950.00");
    private static final BigDecimal RATE_LUXE = new BigDecimal("1850.00");

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
        BigDecimal basePremium;
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

    private List<Quote> quotes;
    private List<Premium> premiums;
    private int acceptedCount;
    private int rejectedCount;
    private int manualCount;
    private BigDecimal totalNetPremium;
    private BigDecimal totalGrossPremium;

    public AutopremCalculator() {
        this.quotes = new ArrayList<>(QUOTE_CAPACITY);
        this.premiums = new ArrayList<>(QUOTE_CAPACITY);
        this.acceptedCount = 0;
        this.rejectedCount = 0;
        this.manualCount = 0;
        this.totalNetPremium = BigDecimal.ZERO;
        this.totalGrossPremium = BigDecimal.ZERO;
    }

    public void run() {
        displayHeader();
        loadTestCases();
        processAllQuotes();
        displaySummary();
    }

    private void displayHeader() {
        System.out.println();
        System.out.println("=======================================");
        System.out.println("STAR ASSURANCE - CALCUL PRIMES AUTO");
        System.out.println("Version 1.4 - Tarif 2024");
        System.out.println("=======================================");
        System.out.println();
    }

    private void loadTestCases() {
        // Quote 1: Young driver, basic tourism vehicle, Tunis
        addQuote(10000001, "BENSALAH AHMED", 22, 2, "TR", 6, 
                 new BigDecimal("25000.00"), "RC", new BigDecimal("1.00"), "TUN", 0);

        // Quote 2: Experienced driver, family car, Sfax
        addQuote(10000002, "TRABELSI FATMA", 45, 22, "TR", 8, 
                 new BigDecimal("48000.00"), "TC", new BigDecimal("0.50"), "SFX", 0);

        // Quote 3: Luxury vehicle full coverage
        addQuote(10000003, "CHAOUACHI MOEZ", 52, 30, "LX", 14, 
                 new BigDecimal("185000.00"), "TI", new BigDecimal("0.55"), "TUN", 0);

        // Quote 4: Motorcycle, young rider
        addQuote(10000004, "GHARBI KARIM", 25, 5, "MT", 4, 
                 new BigDecimal("9500.00"), "RC", new BigDecimal("1.00"), "SOU", 1);

        // Quote 5: Commercial truck
        addQuote(10000005, "TRANSPORT BELHAJ SARL", 38, 15, "CM", 20, 
                 new BigDecimal("145000.00"), "TC", new BigDecimal("0.85"), "BIZ", 0);

        // Quote 6: Under-age driver (REJECTED)
        addQuote(10000006, "JEBALI MEHDI", 17, 0, "TR", 5, 
                 new BigDecimal("18000.00"), "RC", new BigDecimal("1.00"), "TUN", 0);

        // Quote 7: High accident history (MANUAL REVIEW)
        addQuote(10000007, "BOUAZIZ NESRINE", 28, 8, "TR", 7, 
                 new BigDecimal("32000.00"), "TC", new BigDecimal("2.50"), "NAB", 4);

        // Quote 8: Senior driver, modest car
        addQuote(10000008, "DRIDI RIDHA", 68, 45, "TR", 5, 
                 new BigDecimal("22000.00"), "TI", new BigDecimal("0.50"), "KEF", 0);

        // Quote 9: Utility vehicle, small business
        addQuote(10000009, "KHELIFA SLIM", 35, 12, "UT", 10, 
                 new BigDecimal("65000.00"), "TC", new BigDecimal("0.75"), "SFX", 1);

        // Quote 10: Over age limit (REJECTED)
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
        q.crmCoef = crmCoef;
        q.governorate = governorate;
        q.accidents3Y = accidents3Y;
        quotes.add(q);
        
        Premium p = new Premium();
        p.quoteId = quoteId;
        p.basePremium = BigDecimal.ZERO;
        p.ageCoef = BigDecimal.ZERO;
        p.powerCoef = BigDecimal.ZERO;
        p.coverageCoef = BigDecimal.ZERO;
        p.regionCoef = BigDecimal.ZERO;
        p.accidentLoad = BigDecimal.ZERO;
        p.netPremium = BigDecimal.ZERO;
        p.tva = BigDecimal.ZERO;
        p.parafiscal = BigDecimal.ZERO;
        p.totalPremium = BigDecimal.ZERO;
        p.decision = "";
        p.rejectionReason = "";
        premiums.add(p);
    }

    private void processAllQuotes() {
        for (int i = 0; i < quotes.size(); i++) {
            Quote q = quotes.get(i);
            Premium p = premiums.get(i);

            validateQuote(i, q, p);

            if ("REFUSE".equals(p.decision)) {
                displayRejected(i, q, p);
            } else {
                computePremium(i, q, p);
                applyLimits(i, p);
                computeTaxes(i, p);
                finalDecision(i, q, p);
                displayQuote(i, q, p);
            }
        }
    }

    private void validateQuote(int idx, Quote q, Premium p) {
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
        } else if (q.crmCoef.compareTo(new BigDecimal("3.50")) > 0) {
            p.decision = "REFUSE";
            p.rejectionReason = "COEFFICIENT CRM TROP ELEVE";
            rejectedCount++;
        }
    }

    private void computePremium(int idx, Quote q, Premium p) {
        setBaseRate(q, p);
        computeAgeCoef(q, p);
        computePowerCoef(q, p);
        computeCoverageCoef(q, p);
        computeRegionCoef(q, p);
        computeAccidentLoad(q, p);

        // netPremium = basePremium * ageCoef * powerCoef * coverageCoef * regionCoef * crmCoef + accidentLoad
        BigDecimal computed = p.basePremium
                .multiply(p.ageCoef)
                .multiply(p.powerCoef)
                .multiply(p.coverageCoef)
                .multiply(p.regionCoef)
                .multiply(q.crmCoef)
                .add(p.accidentLoad);
        p.netPremium = computed.setScale(3, RoundingMode.HALF_UP);
    }

    private void setBaseRate(Quote q, Premium p) {
        switch (q.vehicleCategory) {
            case "TR":
                p.basePremium = RATE_TOURISME;
                break;
            case "UT":
                p.basePremium = RATE_UTILITAIRE;
                break;
            case "MT":
                p.basePremium = RATE_MOTO;
                break;
            case "CM":
                p.basePremium = RATE_CAMION;
                break;
            case "LX":
                p.basePremium = RATE_LUXE;
                break;
            default:
                p.basePremium = RATE_TOURISME;
                break;
        }
    }

    private void computeAgeCoef(Quote q, Premium p) {
        if (q.driverAge < 25) {
            p.ageCoef = new BigDecimal("1.60");
        } else if (q.driverAge < 30) {
            p.ageCoef = new BigDecimal("1.25");
        } else if (q.driverAge < 65) {
            p.ageCoef = new BigDecimal("1.00");
        } else {
            p.ageCoef = new BigDecimal("1.30");
        }

        // Experience discount: if license years >= 10 AND age < 65
        if (q.licenseYears >= 10 && q.driverAge < 65) {
            p.ageCoef = p.ageCoef.multiply(EXPERIENCE_DISCOUNT);
        }
    }

    private void computePowerCoef(Quote q, Premium p) {
        if (q.vehiclePower <= 4) {
            p.powerCoef = new BigDecimal("0.85");
        } else if (q.vehiclePower <= 7) {
            p.powerCoef = new BigDecimal("1.00");
        } else if (q.vehiclePower <= 10) {
            p.powerCoef = new BigDecimal("1.20");
        } else if (q.vehiclePower <= 14) {
            p.powerCoef = new BigDecimal("1.50");
        } else {
            p.powerCoef = new BigDecimal("2.00");
        }
    }

    private void computeCoverageCoef(Quote q, Premium p) {
        switch (q.coverage) {
            case "RC":
                p.coverageCoef = new BigDecimal("1.00");
                break;
            case "TC":
                p.coverageCoef = new BigDecimal("1.80");
                break;
            case "TI":
                p.coverageCoef = new BigDecimal("3.20");
                break;
            default:
                p.coverageCoef = new BigDecimal("1.00");
                break;
        }
    }

    private void computeRegionCoef(Quote q, Premium p) {
        switch (q.governorate) {
            case "TUN":
                p.regionCoef = new BigDecimal("1.20");
                break;
            case "ARI":
                p.regionCoef = new BigDecimal("1.15");
                break;
            case "BAR":
                p.regionCoef = new BigDecimal("1.10");
                break;
            case "SFX":
                p.regionCoef = new BigDecimal("1.05");
                break;
            case "SOU":
                p.regionCoef = new BigDecimal("1.05");
                break;
            case "NAB":
                p.regionCoef = new BigDecimal("1.00");
                break;
            case "BIZ":
                p.regionCoef = new BigDecimal("0.95");
                break;
            default:
                p.regionCoef = new BigDecimal("0.90");
                break;
        }
    }

    private void computeAccidentLoad(Quote q, Premium p) {
        if (q.accidents3Y == 0) {
            p.accidentLoad = BigDecimal.ZERO;
        } else {
            p.accidentLoad = new BigDecimal(q.accidents3Y)
                    .multiply(ACCIDENT_SURCHARGE)
                    .setScale(3, RoundingMode.HALF_UP);
        }
    }

    private void applyLimits(int idx, Premium p) {
        if (p.netPremium.compareTo(MIN_PREMIUM) < 0) {
            p.netPremium = MIN_PREMIUM;
        }
        if (p.netPremium.compareTo(MAX_PREMIUM) > 0) {
            p.netPremium = MAX_PREMIUM;
        }
    }

    private void computeTaxes(int idx, Premium p) {
        p.tva = p.netPremium.multiply(TVA_RATE).divide(new BigDecimal("100"), 3, RoundingMode.HALF_UP);
        p.parafiscal = p.netPremium.multiply(PARAFISCAL_RATE).divide(new BigDecimal("100"), 3, RoundingMode.HALF_UP);
        p.totalPremium = p.netPremium.add(p.tva).add(p.parafiscal).setScale(3, RoundingMode.DOWN);
    }

    private void finalDecision(int idx, Quote q, Premium p) {
        if (q.accidents3Y >= HIGH_RISK_LIMIT) {
            p.decision = "MANUEL";
            p.rejectionReason = "SINISTRES > 3 - REVUE MANUELLE REQUISE";
            manualCount++;
        } else if (q.crmCoef.compareTo(new BigDecimal("2.00")) > 0) {
            p.decision = "MANUEL";
            p.rejectionReason = "CRM ELEVE - REVUE MANUELLE";
            manualCount++;
        } else {
            p.decision = "ACCEPTE";
            acceptedCount++;
            totalNetPremium = totalNetPremium.add(p.netPremium);
            totalGrossPremium = totalGrossPremium.add(p.totalPremium);
        }
    }

    private void displayRejected(int idx, Quote q, Premium p) {
        System.out.println();
        System.out.println("DEVIS " + q.quoteId + " --- REFUSE");
        System.out.println("  Client: " + q.clientName);
        System.out.println("  Motif : " + p.rejectionReason);
    }

    private void displayQuote(int idx, Quote q, Premium p) {
        System.out.println();
        System.out.println("DEVIS " + q.quoteId + " --- " + p.decision);
        System.out.println("  Client    : " + q.clientName);
        System.out.println("  Age conducteur: " + q.driverAge + " ans   Puissance: " + q.vehiclePower + " CV");
        System.out.println("  Categorie : " + q.vehicleCategory + 
                          "    Couverture: " + q.coverage + 
                          "    Gouvernorat: " + q.governorate);
        System.out.println("  Prime base : " + formatAmount(p.basePremium) + " TND");
        System.out.println("    Coef age      : " + formatCoef(p.ageCoef));
        System.out.println("    Coef puissance: " + formatCoef(p.powerCoef));
        System.out.println("    Coef garantie : " + formatCoef(p.coverageCoef));
        System.out.println("    Coef region   : " + formatCoef(p.regionCoef));
        System.out.println("    CRM           : " + formatCoef(q.crmCoef));
        System.out.println("  Prime nette: " + formatAmount(p.netPremium) + " TND");
        System.out.println("    TVA 19 pct   : " + formatAmount(p.tva) + " TND");
        System.out.println("    Parafiscal 5 : " + formatAmount(p.parafiscal) + " TND");
        System.out.println("  PRIME TTC  : " + formatAmount(p.totalPremium) + " TND");
        
        if ("MANUEL".equals(p.decision)) {
            System.out.println("  Note: " + p.rejectionReason);
        }
    }

    private void displaySummary() {
        System.out.println();
        System.out.println("=======================================");
        System.out.println("RECAPITULATIF DU LOT");
        System.out.println("=======================================");
        System.out.println("  DEVIS ACCEPTES   : " + acceptedCount);
        System.out.println("  DEVIS REFUSES    : " + rejectedCount);
        System.out.println("  REVUE MANUELLE   : " + manualCount);
        System.out.println("  PRIME NETTE TOT  : " + formatAmount(totalNetPremium) + " TND");
        System.out.println("  PRIME TTC TOTALE : " + formatAmount(totalGrossPremium) + " TND");
        System.out.println("=======================================");
    }

    private String formatAmount(BigDecimal amount) {
        if (amount == null) {
            return "0.000";
        }
        return String.format("%,.3f", amount);
    }

    private String formatCoef(BigDecimal coef) {
        if (coef == null) {
            return "0.00";
        }
        return String.format("%.2f", coef);
    }

    public static void main(String[] args) {
        AutopremCalculator calculator = new AutopremCalculator();
        calculator.run();
    }
}
