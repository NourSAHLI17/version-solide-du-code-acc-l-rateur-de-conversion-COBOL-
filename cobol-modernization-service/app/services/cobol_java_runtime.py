"""Embedded Java helpers for COBOL-edited display and PIC storage (injected into converted sources)."""

from __future__ import annotations

COBOL_NUMERIC_STORAGE_JAVA = r"""
/** COBOL PIC storage simulation (truncation / ROUNDED) for converted programs. */
final class CobolNumericStorage {
    private CobolNumericStorage() {}

    /** PIC 9(7)V999 — PR-NET-PREMIUM, PR-TVA, PR-BASE-PREMIUM, etc. */
    static BigDecimal pic9_7v999(BigDecimal value, boolean rounded) {
        return store(value, 7, 3, rounded);
    }

    /** PIC 9(7)V99 — WS-MIN/MAX premium limits, WS-TOTAL-NET/GROSS. */
    static BigDecimal pic9_7v99(BigDecimal value, boolean rounded) {
        return store(value, 7, 2, rounded);
    }

    /** PIC 9(1)V99 — PR-*-COEF, PR-ACCIDENT-LOAD, QT-CRM-COEF storage. */
    static BigDecimal pic9_1v99(BigDecimal value, boolean rounded) {
        return store(value, 1, 2, rounded);
    }

    /** PIC 9(5)V99 — base rate table entries. */
    static BigDecimal pic9_5v99(BigDecimal value, boolean rounded) {
        return store(value, 5, 2, rounded);
    }

    /** PIC 9(9)V99 — WS-TOTAL-NET / WS-TOTAL-GROSS. */
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
"""

COBOL_PIC_FORMAT_JAVA = r"""
/** Locale-independent COBOL edited-picture formatting (Z/9 editing). */
final class CobolPicFormat {
    private CobolPicFormat() {}

    /** PIC ZZ,ZZZ.999 — WS-DISP-AMOUNT / premium amounts. */
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
        String grouped = groupThousands(whole);
        return padField(sign + grouped + "." + frac, 10);
    }

    /** PIC Z.99 — WS-DISP-COEF (suppress leading zero before decimal). */
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

    /** PIC ZZ9 — WS-DISP-AGE (leading space suppression, width 3). */
    static String picZz9(int value) {
        return padEdited(String.valueOf(Math.max(0, value)), 3);
    }

    /** PIC Z9 — WS-DISP-POWER (width 2). */
    static String picZ9(int value) {
        return padEdited(String.valueOf(Math.max(0, value)), 2);
    }

    /** PIC 9(3) — accepted/rejected/manual counts with leading zeros. */
    static String pic9_3(int value) {
        int v = Math.max(0, value);
        return String.format("%03d", v);
    }

    private static String groupThousands(String whole) {
        if (whole.isEmpty()) {
            return "0";
        }
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
        int spaces = width - digits.length();
        return " ".repeat(spaces) + digits;
    }

    private static String padField(String text, int width) {
        if (text.length() >= width) {
            return text.substring(text.length() - width);
        }
        return " ".repeat(width - text.length()) + text;
    }
}
"""

COBOL_RECORD_REWRITE_JAVA = r"""
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
"""
