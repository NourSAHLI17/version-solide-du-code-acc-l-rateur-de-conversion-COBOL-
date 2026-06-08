"""Hand-curated behavioral metrics and sub-program test cases (F62).

Computed fields (stdout MD5, file checksums) come from ``capture_baseline``;
``KEY_METRICS`` and ``SUB_PROGRAM_BASELINES`` are the exact targets Java output
must match during behavioral diff (F63).
"""

from __future__ import annotations

from typing import Any, Dict

# Record lengths for generated .dat files (GnuCOBOL SEQUENTIAL, no line endings).
GENERATED_FILE_RECORD_LEN: Dict[str, int] = {
    "BCTSUBM.dat": 200,
    "RISKRPT.dat": 137,
    "MONTHRPT.dat": 137,
    "DECIRPT.dat": 137,
    "ESCARPT.dat": 137,
    "EVALREJ.dat": 160,
    "SCORFILE.dat": 229,
    "RECVNEW.dat": 238,
    "LETTERS.dat": 200,
}

# Exact metrics Java must reproduce (full LOANFILE semantics, 800 records / 726 active).
KEY_METRICS: Dict[str, Dict[str, Any]] = {
    "LOANEVAL": {
        "read_count": 800,
        "approved_count": 454,
        "conditional_count": 102,
        "declined_count": 170,
        "errors_count": 74,
    },
    "RECOVRY": {
        "class_2_count": 0,
        "class_3_count": 0,
        "class_4_count": 0,
        "total_actions": 0,
    },
    "RISKSCOR": {
        "CLASS_1_count": 726,
        "CLASS_2_count": 0,
        "CLASS_3_count": 0,
        "CLASS_4_count": 0,
        "TOTAL_PROVISION": "0.00",
    },
    "RPTMONTH": {
        "total_loans": 726,
        "total_outstanding_millimes": "7261328662",
    },
}

SUB_PROGRAM_BASELINES: Dict[str, Dict[str, Any]] = {
    "CHKAML": {
        "program": "CHKAML",
        "test_cases": [
            {
                "name": "clean_client",
                "input": {
                    "cust_id": 10000001,
                    "cin": "88776655",
                    "name": "BENSALAH AHMED",
                    "dob": 19850515,
                    "nationality": "TUN",
                    "amount": "5000.00",
                },
                "expected_output": {
                    "clear": "Y",
                    "score": 0,
                    "reason": "AML CLEAR",
                },
            },
            {
                "name": "pep_hit",
                "input": {
                    "cust_id": 10000002,
                    "name": "MOHAMED TRABELSI",
                    "dob": 19700101,
                    "nationality": "TUN",
                    "cin": "00000000",
                    "amount": "5000.00",
                },
                "expected_output": {
                    "clear": "Y",
                    "score": 50,
                    "reason": "AML CLEAR",
                },
            },
        ],
    },
    "CALCFEE": {
        "program": "CALCFEE",
        "test_cases": [
            {
                "name": "consumer_standard",
                "input": {
                    "loan_type": "CON",
                    "amount": "100000.00",
                    "rate": "12.5000",
                },
                "expected_output": {
                    "file_fee": "1500.00",
                    "tax": "290.00",
                    "insurance": "450.00",
                    "total": "2240.00",
                },
            },
            {
                "name": "mortgage_at_cap",
                "input": {
                    "loan_type": "IMM",
                    "amount": "500000.00",
                    "rate": "9.2500",
                },
                "expected_output": {
                    "file_fee": "5000.00",
                    "tax": "955.00",
                    "insurance": "2250.00",
                    "total": "8205.00",
                },
            },
            {
                "name": "business_min_fee",
                "input": {
                    "loan_type": "PRO",
                    "amount": "1000.00",
                    "rate": "8.0000",
                },
                "expected_output": {
                    "file_fee": "50.00",
                    "tax": "14.50",
                    "insurance": "0.00",
                    "total": "64.50",
                },
            },
        ],
    },
}
