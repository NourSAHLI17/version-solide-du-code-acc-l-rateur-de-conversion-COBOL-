#!/usr/bin/env python3
"""
ACME Bank v3 - Realistic banking data generator.
Generates fixed-width COBOL data files with:
  - 500 customers (CUSTFILE.dat)
  - 800 loans (LOANFILE.dat)
  - 400 collateral records (COLFILE.dat)
  - 200 guarantee records (GUARFILE.dat)
With consistent cross-file references (every loan has a valid cust ID).
"""
import random
import datetime
from pathlib import Path

random.seed(42)  # reproducibility

OUTPUT_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

# Tunisian first names
FIRST_NAMES_M = ["AHMED", "MOHAMED", "KARIM", "YASSINE", "FARES", "MOEZ",
                  "WALID", "SAMI", "AMINE", "MEHDI", "NIDHAL", "ANIS",
                  "MAROUEN", "TAREK", "HICHEM", "RIDHA", "SLIM", "NABIL",
                  "BILEL", "HAMDI", "OUSSAMA", "AYMEN", "ZIED", "FETHI"]
FIRST_NAMES_F = ["FATMA", "LEILA", "SONIA", "RANIA", "NESRINE", "AMIRA",
                  "SALMA", "MERIEM", "MAYSSA", "EMNA", "INES", "NOUR",
                  "DORRA", "OLFA", "AIDA", "RYM", "ISLEM", "WAFA",
                  "HAFSA", "SARRA", "WIEM", "HAJER", "MANEL", "RAOUDHA"]
LAST_NAMES = ["BENSALAH", "BELHAJ", "TRABELSI", "CHAOUACHI", "MANSOURI",
              "HAMROUNI", "KARRAY", "SELLAMI", "OUALI", "MEJRI",
              "BENALI", "SOUSSI", "FERCHICHI", "GHARBI", "KHELIFA",
              "BOUAZIZ", "TLILI", "JEBALI", "BENNANI", "AYARI",
              "DRIDI", "MAALEJ", "KHEMIRI", "JLASSI", "AMARA",
              "BENABDALLAH", "MABROUK", "ZOUARI", "BACCOUCHE", "GHRAB",
              "BENMOHAMED", "ABDELLI", "DAOUD", "KILANI", "MEDIOUNI"]

GOV_CODES = {"TUN": "Tunis", "ARI": "Ariana", "BAR": "Ben Arous",
              "MAN": "Manouba", "NAB": "Nabeul", "ZAG": "Zaghouan",
              "BIZ": "Bizerte", "BEJ": "Beja", "JEN": "Jendouba",
              "KEF": "Kef", "SIL": "Siliana", "SOU": "Sousse",
              "MON": "Monastir", "MAH": "Mahdia", "SFX": "Sfax",
              "KAI": "Kairouan", "KAS": "Kasserine", "SBZ": "Sidi Bouzid",
              "GAB": "Gabes", "MED": "Medenine", "TAT": "Tataouine",
              "GAF": "Gafsa", "TOZ": "Tozeur", "KEB": "Kebili"}

GOV_LIST = list(GOV_CODES.keys())

EMPLOYERS = ["BANQUE CENTRALE DE TUNISIE", "MINISTERE DES FINANCES",
              "TUNISIE TELECOM", "ORANGE TUNISIE", "OOREDOO TUNISIE",
              "GROUPE POULINA", "GROUPE BAYAHI", "GROUPE SELLAMI IMMOBILIER",
              "PHARMACIE CENTRALE", "STAR ASSURANCE", "ARTISAN INDEPENDANT",
              "CABINET MEDICAL", "ENSEIGNANT SECONDAIRE", "FONCTIONNAIRE",
              "CABINET D AVOCAT", "GROUPE DELICE DANONE",
              "STEG SOCIETE TUNISIENNE DE L ELECTRICITE",
              "SONEDE", "TUNISAIR", "BIAT", "STB", "BNA", "ATTIJARI BANK",
              "CIMENT DE BIZERTE", "GROUPE LOUKIL", "AGIL ENERGIE",
              "ENTREPRISE INDIVIDUELLE", "COMMERCE DETAIL"]

JOB_TITLES = ["DIRECTEUR ADJOINT", "INGENIEUR SYSTEMES", "PHARMACIEN",
              "ENSEIGNANT", "MEDECIN GENERALISTE", "AVOCAT",
              "EXPERT COMPTABLE", "CHEF DE PROJET", "DIRECTEUR COMMERCIAL",
              "AGENT COMMERCIAL", "TECHNICIEN MAINTENANCE", "ARTISAN",
              "COMMERCANT", "CADRE BANCAIRE", "INFIRMIER",
              "ASSISTANT ADMINISTRATIF", "CHAUFFEUR", "GERANT BOUTIQUE",
              "PDG", "DIRECTRICE GENERALE", "DENTISTE", "INGENIEUR CIVIL",
              "ARCHITECTE", "JOURNALISTE", "PROFESSEUR UNIVERSITE",
              "DEVELOPPEUR INFORMATIQUE", "COMPTABLE", "GERANT SOCIETE"]

ADDRESSES = ["15 Avenue Habib Bourguiba", "22 Rue de Marseille",
              "7 Impasse des Oliviers", "44 Avenue de la Liberte",
              "8 Rue Ibn Khaldoun", "31 Boulevard du Lac",
              "15 Route de Megrine", "6 Rue de Carthage",
              "78 Avenue Jugurtha", "23 Avenue des Jasmins",
              "12 Rue du 7 Novembre", "55 Avenue Mongi Slim",
              "9 Rue de Tunis", "27 Avenue de la Republique",
              "104 Rue de Sfax", "3 Impasse El Manar",
              "67 Avenue Taieb Mhiri", "42 Rue d Espagne",
              "18 Avenue de France", "89 Boulevard 9 Avril",
              "5 Rue Pierre Curie", "33 Avenue Hedi Chaker",
              "21 Rue Charles de Gaulle", "56 Avenue Bourguiba"]

LOAN_PURPOSES = {
    "CON": ["Credit consommation divers", "Financement etudes enfants",
            "Achat electromenager", "Mariage", "Voyage",
            "Soins medicaux", "Amenagement logement",
            "Achat materiel informatique", "Frais divers"],
    "IMM": ["Acquisition appartement", "Construction villa",
            "Achat terrain", "Renovation logement",
            "Acquisition logement principal",
            "Achat residence secondaire"],
    "AUT": ["Achat voiture neuve", "Achat voiture occasion",
            "Achat utilitaire", "Achat moto"],
    "PRO": ["Acquisition local commercial", "Equipement professionnel",
            "Tresorerie entreprise", "Investissement extension",
            "Acquisition fonds de commerce", "Achat materiel industriel"],
    "REV": ["Ligne de credit revolving", "Decouvert autorise",
            "Carte de credit business"],
    "DEC": ["Decouvert temporaire", "Facilite de caisse"]
}


def pad(value, length, side='left', fill=' '):
    """Pad value to fixed width."""
    s = str(value)
    if len(s) > length:
        return s[:length]
    if side == 'left':
        return s.ljust(length, fill)
    return s.rjust(length, fill)


def numpad(value, length):
    """Pad numeric value with leading zeros."""
    return str(int(value)).zfill(length)


def date_in_range(start_year, end_year):
    """Generate YYYYMMDD date in range."""
    start = datetime.date(start_year, 1, 1)
    end = datetime.date(end_year, 12, 28)
    delta = (end - start).days
    d = start + datetime.timedelta(days=random.randint(0, delta))
    return f"{d.year:04d}{d.month:02d}{d.day:02d}"


def generate_customers(count=500):
    """Generate CUSTFILE.dat with realistic Tunisian customer data."""
    records = []
    cust_ids = []

    for i in range(count):
        cust_id = numpad(10000000 + i + 1, 8)
        cust_ids.append(int(cust_id))

        cust_type = random.choices(["PP", "PM", "NR"], weights=[88, 10, 2])[0]
        gender = random.choice(["M", "F"])

        if gender == "M":
            first = random.choice(FIRST_NAMES_M)
        else:
            first = random.choice(FIRST_NAMES_F)
        last = random.choice(LAST_NAMES)

        # CIN: 8 digits
        cin = numpad(random.randint(1000000, 99999999), 8)
        passport = pad("", 12)

        dob = date_in_range(1955, 2003)
        nationality = "TUN"
        marital = random.choices(["S", "M", "D", "W"], weights=[30, 60, 7, 3])[0]

        addr1 = random.choice(ADDRESSES)
        addr2 = random.choice(["", "Appartement 3B", "Etage 2",
                                "Bloc A", "Villa", "Lot 5"])
        gov_code = random.choice(GOV_LIST)
        city = GOV_CODES[gov_code]
        zip_code = numpad(random.randint(1000, 99999), 5)

        phone_mobile = "00216" + numpad(random.randint(20000000, 99999999), 7)
        phone_home = "00216" + numpad(random.randint(70000000, 79999999), 7)

        email = f"{first.lower()}.{last.lower()}@email.tn"
        employer = random.choice(EMPLOYERS)
        job = random.choice(JOB_TITLES)

        # Income distribution: log-normal-ish for realism
        # Most clients: 1500-5000 TND, premium: 8000-25000, private: 50000+
        segment_roll = random.random()
        if segment_roll < 0.70:
            income = random.randint(150000, 500000)  # mass market 1500-5000
            segment = "MM"
        elif segment_roll < 0.92:
            income = random.randint(500000, 1500000)  # middle 5000-15000
            segment = "MB"
        elif segment_roll < 0.99:
            income = random.randint(1500000, 4000000)  # premium 15000-40000
            segment = "PR"
        else:
            income = random.randint(4000000, 12000000)  # private 40000-120000
            segment = "PB"

        income_verified = "Y" if random.random() > 0.05 else "N"

        # Risk rating 1-99 (lower better)
        risk_rating = numpad(random.randint(1, 99), 2)

        # KYC: 92% valid, 5% pending, 3% expired
        kyc_status = random.choices(["V", "P", "E"], weights=[92, 5, 3])[0]
        kyc_expiry = date_in_range(2025, 2028)

        # AML alerts: rare
        aml_flag = "Y" if random.random() < 0.02 else "N"

        # PEP: very rare
        pep_flag = "Y" if random.random() < 0.015 else "N"

        open_date = date_in_range(2005, 2024)

        # Status: 92% active, 6% inactive, 2% blacklisted
        status = random.choices(["A", "I", "B"], weights=[92, 6, 2])[0]

        rm_id = numpad(random.randint(100000, 999999), 6)
        branch = numpad(random.randint(1, 50), 4)

        total_assets = numpad(income * random.randint(8, 24), 15)
        total_liab = numpad(income * random.randint(2, 8), 15)

        # Build fixed-width 380-char record
        record = (
            cust_id +                              # 8
            pad(cin, 8) +                          # 8
            pad(passport, 12) +                    # 12
            cust_type +                            # 2
            pad(last, 30) +                        # 30
            pad(first, 25) +                       # 25
            dob +                                  # 8
            nationality +                          # 3
            gender +                               # 1
            marital +                              # 1
            pad(addr1, 40) +                       # 40
            pad(addr2, 40) +                       # 40
            pad(city, 20) +                        # 20
            zip_code +                             # 5
            gov_code +                             # 3
            pad(phone_mobile, 12) +                # 12
            pad(phone_home, 12) +                  # 12
            pad(email, 50) +                       # 50
            pad(employer, 40) +                    # 40
            pad(job, 30) +                         # 30
            numpad(income, 9) +                    # 9 (PIC 9(7)V99)
            income_verified +                      # 1
            segment +                              # 2
            risk_rating +                          # 2
            kyc_status +                           # 1
            kyc_expiry +                           # 8
            aml_flag +                             # 1
            pep_flag +                             # 1
            open_date +                            # 8
            status +                               # 1
            rm_id +                                # 6
            branch +                               # 4
            total_assets +                         # 15
            total_liab +                           # 15
            pad("", 10)                            # 10 filler
        )
        records.append(record)

    return records, cust_ids


def generate_loans(cust_ids, count=800):
    """Generate LOANFILE.dat - one or more loans per customer."""
    records = []
    loan_ids = []

    for i in range(count):
        loan_id_num = 1000000001 + i
        loan_id = numpad(loan_id_num, 10)
        loan_ids.append(loan_id_num)

        # Pick a random customer (some have multiple loans)
        cust_id = numpad(random.choice(cust_ids), 8)
        acct_id = numpad(int(cust_id) * 100 + random.randint(1, 9), 10)

        # Loan type distribution (realistic for Tunisian retail bank)
        loan_type = random.choices(
            ["CON", "IMM", "AUT", "PRO", "REV", "DEC"],
            weights=[40, 25, 15, 12, 5, 3]
        )[0]

        # Status: most active, some restructured/litigious
        status_roll = random.random()
        if status_roll < 0.85:
            loan_status = "AC"
        elif status_roll < 0.92:
            loan_status = "RS"
        elif status_roll < 0.97:
            loan_status = "LT"
        elif status_roll < 0.99:
            loan_status = "SD"
        else:
            loan_status = "WO"

        # Days past due (correlated with status)
        if loan_status == "AC":
            days_past = random.choices(
                [0, random.randint(1, 30)],
                weights=[85, 15]
            )[0]
        elif loan_status == "RS":
            days_past = random.randint(0, 30)
        elif loan_status == "LT":
            days_past = random.randint(91, 365)
        else:
            days_past = random.randint(180, 720)

        # Classification (driven by days_past)
        if days_past <= 30:
            loan_class = "1"
            prov_rate = 0
        elif days_past <= 90:
            loan_class = "2"
            prov_rate = 200000  # 20.0000%
        elif days_past <= 180:
            loan_class = "3"
            prov_rate = 500000  # 50.0000%
        else:
            loan_class = "4"
            prov_rate = 999999   # 99.9999% (caps at PIC 9(2)V9(4))

        # Original amount depends on type
        if loan_type == "IMM":
            original_amt = random.randint(8000000, 80000000)  # 80k-800k TND
        elif loan_type == "PRO":
            original_amt = random.randint(2000000, 40000000)  # 20k-400k
        elif loan_type == "AUT":
            original_amt = random.randint(1500000, 12000000)  # 15k-120k
        elif loan_type == "REV":
            original_amt = random.randint(500000, 5000000)
        elif loan_type == "DEC":
            original_amt = random.randint(100000, 2000000)
        else:  # CON
            original_amt = random.randint(200000, 3000000)

        # Outstanding (less than or equal to original)
        if loan_status == "WO":
            outstanding = 0
        else:
            payment_progress = random.random()
            outstanding = int(original_amt * (1 - payment_progress * 0.7))

        # Monthly payment (rough)
        rate = random.uniform(7.5, 14.0)
        if loan_type == "IMM":
            months = random.randint(120, 300)
        elif loan_type == "AUT":
            months = random.randint(36, 84)
        else:
            months = random.randint(12, 72)

        monthly_pmt = int(original_amt * (rate / 100 / 12) /
                          (1 - (1 + rate / 100 / 12) ** -months))

        rate_int = int(rate * 10000)  # PIC 9(2)V9(4)
        rate_type = "F" if random.random() > 0.3 else "V"

        start_date = date_in_range(2018, 2024)
        # Maturity = start + months
        start_dt = datetime.date(int(start_date[:4]),
                                  int(start_date[4:6]),
                                  int(start_date[6:8]))
        maturity = start_dt + datetime.timedelta(days=months * 30)
        maturity_date = f"{maturity.year:04d}{maturity.month:02d}{maturity.day:02d}"

        last_pmt = date_in_range(2024, 2024)
        next_pmt = date_in_range(2024, 2025)

        pmts_made = numpad(random.randint(1, months), 4)
        pmts_total = numpad(months, 4)

        missed = numpad(min(days_past // 30, 999), 3)
        provision_amt = int(outstanding * prov_rate / 10000 / 100)

        # Collateral
        if loan_type in ["IMM"]:
            col_type = "IMM"
            col_value = int(outstanding * random.uniform(1.2, 2.0))
        elif loan_type == "AUT":
            col_type = "VEH"
            col_value = int(outstanding * random.uniform(0.8, 1.3))
        elif loan_type == "PRO":
            col_type = random.choice(["IMM", "DEP", "NON"])
            col_value = int(outstanding * random.uniform(0.5, 1.5)) if col_type != "NON" else 0
        else:
            col_type = "NON"
            col_value = 0

        guarantor_id = numpad(random.choice(cust_ids), 8) if random.random() < 0.3 else numpad(0, 8)

        branch = numpad(random.randint(1, 50), 4)
        officer_id = numpad(random.randint(100000, 999999), 6)

        purpose = random.choice(LOAN_PURPOSES.get(loan_type, ["Divers"]))

        restructure_dt = date_in_range(2022, 2024) if loan_status == "RS" else numpad(0, 8)
        write_off_dt = date_in_range(2022, 2024) if loan_status == "WO" else numpad(0, 8)

        # Build 240-char record
        record = (
            loan_id +                              # 10
            cust_id +                              # 8
            acct_id +                              # 10
            loan_type +                            # 3
            loan_status +                          # 2
            loan_class +                           # 1
            numpad(original_amt, 13) +             # 13 (PIC 9(11)V99)
            numpad(outstanding, 13) +              # 13
            numpad(monthly_pmt, 9) +               # 9 (PIC 9(7)V99)
            numpad(rate_int, 6) +                  # 6 (PIC 9(2)V9(4))
            rate_type +                            # 1
            start_date +                           # 8
            maturity_date +                        # 8
            last_pmt +                             # 8
            next_pmt +                             # 8
            pmts_made +                            # 4
            pmts_total +                           # 4
            numpad(days_past, 4) +                 # 4
            missed +                               # 3
            numpad(prov_rate, 6) +                 # 6 (PIC 9(2)V9(4))
            numpad(provision_amt, 11) +            # 11 (PIC 9(9)V99)
            col_type +                             # 3
            numpad(col_value, 13) +                # 13
            guarantor_id +                         # 8
            branch +                               # 4
            officer_id +                           # 6
            pad(purpose, 40) +                     # 40
            restructure_dt +                       # 8
            write_off_dt +                         # 8
            pad("", 8)                             # 8 filler
        )
        records.append(record)

    return records, loan_ids


def generate_collateral(loan_ids, count=400):
    """Generate COLFILE.dat - 253-char records matching COLLATCOPY."""
    records = []
    secured_loans = random.sample(loan_ids, min(count, len(loan_ids)))

    for i, loan_id_num in enumerate(secured_loans):
        col_id = numpad(2000000001 + i, 10)
        loan_id = numpad(loan_id_num, 10)
        cust_id = numpad(10000000 + random.randint(1, 500), 8)

        col_type = random.choices(
            ["IMM", "VEH", "FIN", "GAR"],
            weights=[55, 25, 10, 10]
        )[0]

        if col_type == "IMM":
            desc = random.choice([
                "Appartement 3 pieces 105m2",
                "Villa 6 pieces 280m2 jardin",
                "Local commercial Centre Ville",
                "Terrain agricole 2 hectares",
                "Bureau professionnel 80m2",
                "Maison familiale 220m2"
            ])
            location = f"{random.choice(['Tunis', 'Sfax', 'Sousse', 'Bizerte', 'Nabeul'])} - {random.choice(['Centre', 'Nord', 'Sud', 'Est'])}"
            appraisal_value = random.randint(15000000, 100000000)
        elif col_type == "VEH":
            desc = random.choice([
                "Voiture Toyota Corolla 2022",
                "Voiture Peugeot 208 2023",
                "Voiture Renault Clio 2021",
                "Utilitaire Iveco Daily 2020",
                "Voiture Volkswagen Golf 2022"
            ])
            location = "Lot stationnement client"
            appraisal_value = random.randint(2500000, 15000000)
        elif col_type == "FIN":
            desc = "Depot a terme nanti"
            location = "ACME Bank"
            appraisal_value = random.randint(5000000, 30000000)
        else:
            desc = "Garantie hypothecaire"
            location = "Divers"
            appraisal_value = random.randint(3000000, 25000000)

        appraisal_date = date_in_range(2022, 2024)
        appraisal_firm = random.choice([
            "CABINET EXPERTISE FONCIERE TUNIS",
            "EXPERT IMMOBILIER SFAX SUD",
            "CABINET EXPERTISE NORD TUNIS",
            "AGENCE AUTOMOBILE AGREEE TUNIS",
            "EXPERT COMPTABLE SOUSSE"
        ])

        coverage_ratio = random.randint(10000, 16000)
        insurance_num = f"POL-{random.randint(100000, 999999)}"
        insurance_expiry = date_in_range(2025, 2027)
        registration = f"REG-{random.randint(1000, 9999)}"
        status = random.choices(["A", "R", "S"], weights=[90, 7, 3])[0]

        # 253-char record matching COLLATCOPY exactly
        record = (
            col_id +                               # 10
            loan_id +                              # 10
            cust_id +                              # 8
            col_type +                             # 3
            pad(desc, 60) +                        # 60
            pad(location, 40) +                    # 40
            numpad(appraisal_value, 13) +          # 13 (PIC 9(11)V99)
            appraisal_date +                       # 8
            pad(appraisal_firm, 30) +              # 30
            numpad(coverage_ratio, 5) +            # 5 (PIC 9(3)V99)
            pad(insurance_num, 20) +               # 20
            insurance_expiry +                     # 8
            pad(registration, 20) +                # 20
            status +                               # 1
            pad("", 17)                            # 17 filler
        )
        # Final pad/truncate to exactly 253
        record = record[:253].ljust(253)
        records.append(record)

    return records


def generate_guarantees(cust_ids, loan_ids, count=200):
    """Generate GUARFILE.dat - guarantor records."""
    records = []
    for i in range(count):
        gtr_id = numpad(3000000001 + i, 10)
        loan_id = numpad(random.choice(loan_ids), 10)
        guarantor_id = numpad(random.choice(cust_ids), 8)

        first = random.choice(FIRST_NAMES_M + FIRST_NAMES_F)
        last = random.choice(LAST_NAMES)
        guarantor_name = f"{last} {first}"

        amount = random.randint(2000000, 50000000)
        income = random.randint(150000, 3000000)
        sign_date = date_in_range(2020, 2024)
        expiry = date_in_range(2025, 2030)
        status = random.choices(["A", "C", "E"], weights=[88, 7, 5])[0]

        record = (
            gtr_id +                               # 10
            loan_id +                              # 10
            guarantor_id +                         # 8
            pad(guarantor_name, 50) +              # 50
            numpad(amount, 13) +                   # 13
            numpad(income, 9) +                    # 9
            sign_date +                            # 8
            expiry +                               # 8
            status +                               # 1
            pad("", 13)                            # 13 filler -> total 130
        )
        record = record[:130].ljust(130)
        records.append(record)
    return records


def main():
    print("Generating ACME Bank v3 data files...")

    # 500 customers
    print("  - Customers...", end=" ", flush=True)
    cust_records, cust_ids = generate_customers(500)
    (OUTPUT_DIR / "CUSTFILE.dat").write_text("\n".join(cust_records) + "\n",
                                              encoding="utf-8")
    print(f"{len(cust_records)} records written")

    # 800 loans
    print("  - Loans...", end=" ", flush=True)
    loan_records, loan_ids = generate_loans(cust_ids, 800)
    (OUTPUT_DIR / "LOANFILE.dat").write_text("\n".join(loan_records) + "\n",
                                              encoding="utf-8")
    print(f"{len(loan_records)} records written")

    # 400 collateral
    print("  - Collateral...", end=" ", flush=True)
    col_records = generate_collateral(loan_ids, 400)
    (OUTPUT_DIR / "COLFILE.dat").write_text("\n".join(col_records) + "\n",
                                             encoding="utf-8")
    print(f"{len(col_records)} records written")

    # 200 guarantees
    print("  - Guarantees...", end=" ", flush=True)
    gtr_records = generate_guarantees(cust_ids, loan_ids, 200)
    (OUTPUT_DIR / "GUARFILE.dat").write_text("\n".join(gtr_records) + "\n",
                                              encoding="utf-8")
    print(f"{len(gtr_records)} records written")

    print(f"\nAll files written to {OUTPUT_DIR}")
    print("File sizes:")
    for f in sorted(OUTPUT_DIR.glob("*.dat")):
        size_kb = f.stat().st_size / 1024
        line_count = sum(1 for _ in f.open(encoding="utf-8"))
        print(f"  {f.name}: {line_count:,} records, {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
