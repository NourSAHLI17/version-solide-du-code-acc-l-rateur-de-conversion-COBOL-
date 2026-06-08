#!/usr/bin/env python3
"""
Generates SANCFILE.dat - sanctions and PEP list for AML screening.
Contains ~50 fake sanctions entries spanning UN, EU, OFAC, BCT, PEP lists.
Some entries match customer names from CUSTFILE to demonstrate hits.
"""
import random
from pathlib import Path

random.seed(123)

OUTPUT_DIR = Path(__file__).parent.parent / "data"

# Some names that will match CUSTFILE entries (to trigger AML hits)
# and some that won't (to fill the list)
SANCTIONED_ENTRIES = [
    # name(55), cin(8), dob(8), nat(3), list(3), sev(1), reason(60)
    ("MOHAMED TRABELSI                                       ",
     "12345678", "19700101", "TUN", "PEP", "3",
     "Former government official - enhanced due diligence"),
    ("AHMED BENALI                                           ",
     "23456789", "19650512", "TUN", "PEP", "2",
     "Member of parliament family"),
    ("VICTOR YANUKOVYCH                                      ",
     "00000001", "19500709", "UKR", "EUL", "4",
     "EU asset freeze list - sanctioned 2014"),
    ("SAIF AL-ISLAM GADDAFI                                  ",
     "00000002", "19720625", "LBY", "UNL", "5",
     "UN Security Council resolution 1970"),
    ("ALEKSANDR LUKASHENKO                                   ",
     "00000003", "19540830", "BLR", "EUL", "4",
     "EU sanctions list - human rights"),
    ("BASHAR AL-ASSAD                                        ",
     "00000004", "19650911", "SYR", "OFC", "5",
     "OFAC SDN list - Syria sanctions"),
    ("RAMI MAKHLOUF                                          ",
     "00000005", "19690710", "SYR", "OFC", "5",
     "OFAC SDN list - Syria businessman"),
    ("KIM JONG UN                                            ",
     "00000006", "19840108", "PRK", "UNL", "5",
     "UN sanctions DPRK leadership"),
    ("VIKTOR BOUT                                            ",
     "00000007", "19670113", "RUS", "OFC", "5",
     "OFAC arms trafficking"),
    ("SEMION MOGILEVICH                                      ",
     "00000008", "19460630", "UKR", "OFC", "5",
     "OFAC FBI Top Ten Most Wanted"),
    ("ABU BAKR AL-BAGHDADI                                   ",
     "00000009", "19710728", "IRQ", "UNL", "5",
     "UN ISIL Al-Qaida sanctions list"),
    ("MARIA GABRIELA CHAVEZ                                  ",
     "00000010", "19800312", "VEN", "OFC", "4",
     "OFAC Venezuela sanctions"),
    ("AHMED EL ARABI                                         ",
     "34567890", "19751220", "TUN", "PEP", "2",
     "Former minister - enhanced monitoring"),
    ("LEILA KHELIFA                                          ",
     "45678901", "19680403", "TUN", "PEP", "2",
     "Spouse of senior judge"),
    ("KARIM CHAOUACHI                                        ",
     "56789012", "19720915", "TUN", "PEP", "1",
     "Cousin of regional governor"),
    ("YAHYA SINWAR                                           ",
     "00000011", "19621029", "PSE", "OFC", "4",
     "OFAC SDN list"),
    ("HASSAN NASRALLAH                                       ",
     "00000012", "19600831", "LBN", "OFC", "5",
     "OFAC SDGT designation"),
    ("ALI KHAMENEI                                           ",
     "00000013", "19390419", "IRN", "OFC", "5",
     "OFAC Iran sanctions"),
    ("EBRAHIM RAISI                                          ",
     "00000014", "19601214", "IRN", "OFC", "5",
     "OFAC Iran human rights sanctions"),
    ("QASEM SOLEIMANI                                        ",
     "00000015", "19570311", "IRN", "OFC", "5",
     "OFAC Iran IRGC commander - deceased"),
    ("MOHAMED MORSI                                          ",
     "00000016", "19510820", "EGY", "PEP", "3",
     "Former president - deceased"),
    ("HOSNI MUBARAK                                          ",
     "00000017", "19280504", "EGY", "PEP", "3",
     "Former president - deceased"),
    ("ZINE EL ABIDINE BEN ALI                                ",
     "00000018", "19360903", "TUN", "TUN", "5",
     "BCT freeze - former regime - deceased"),
    ("LEILA TRABELSI                                         ",
     "00000019", "19561024", "TUN", "TUN", "5",
     "BCT freeze - former regime"),
    ("BELHASSEN TRABELSI                                     ",
     "00000020", "19620114", "TUN", "TUN", "5",
     "BCT freeze - former regime"),
    ("SAKHER EL MATERI                                       ",
     "00000021", "19810118", "TUN", "TUN", "5",
     "BCT freeze - former regime"),
    ("MOHAMED SAKHER EL MATERI                               ",
     "00000022", "19531213", "TUN", "TUN", "4",
     "BCT freeze - former regime relative"),
    ("CECILIA ATTIAS                                         ",
     "00000023", "19571112", "FRA", "PEP", "2",
     "Former French first lady"),
    ("MARINE LE PEN                                          ",
     "00000024", "19680805", "FRA", "PEP", "2",
     "French politician - enhanced monitoring"),
    ("ELON MUSK                                              ",
     "00000025", "19710628", "USA", "PEP", "1",
     "Foreign senior executive"),
    ("VLADIMIR PUTIN                                         ",
     "00000026", "19521007", "RUS", "EUL", "5",
     "EU sanctions - Russia"),
    ("SERGEI LAVROV                                          ",
     "00000027", "19500321", "RUS", "EUL", "4",
     "EU sanctions - Russia"),
    ("MIKHAIL FRIDMAN                                        ",
     "00000028", "19640421", "RUS", "EUL", "3",
     "EU asset freeze - oligarch"),
    ("ROMAN ABRAMOVICH                                       ",
     "00000029", "19661024", "RUS", "EUL", "3",
     "EU asset freeze - oligarch"),
    ("ALISHER USMANOV                                        ",
     "00000030", "19530909", "RUS", "EUL", "3",
     "EU asset freeze - oligarch"),
    ("KARIM BENALI                                           ",
     "67890123", "19880204", "TUN", "PEP", "1",
     "Nephew of senior bank official"),
    ("FATMA HAMROUNI                                         ",
     "78901234", "19770806", "TUN", "PEP", "1",
     "Daughter of former minister"),
    ("RIDHA OUALI                                            ",
     "89012345", "19660629", "TUN", "PEP", "2",
     "Senior judiciary official"),
    ("SAMIR LOUKIL                                           ",
     "00000031", "19550617", "TUN", "PEP", "1",
     "Former state company CEO"),
    ("MEHDI JOMAA                                            ",
     "00000032", "19620420", "TUN", "PEP", "2",
     "Former prime minister"),
    ("MUSTAPHA KAMEL NABLI                                   ",
     "00000033", "19481215", "TUN", "PEP", "2",
     "Former central bank governor"),
    ("CHEDLY AYARI                                           ",
     "00000034", "19330216", "TUN", "PEP", "2",
     "Former central bank governor"),
    ("MARZOUKI MONCEF                                        ",
     "00000035", "19450707", "TUN", "PEP", "2",
     "Former president"),
    ("BEJI CAID ESSEBSI                                      ",
     "00000036", "19261129", "TUN", "PEP", "3",
     "Former president - deceased"),
    ("KAIS SAIED                                             ",
     "00000037", "19580222", "TUN", "PEP", "3",
     "Current president"),
    ("YOUSSEF CHAHED                                         ",
     "00000038", "19750918", "TUN", "PEP", "2",
     "Former prime minister"),
    ("HICHEM MECHICHI                                        ",
     "00000039", "19740411", "TUN", "PEP", "2",
     "Former prime minister"),
    ("ELYES FAKHFAKH                                         ",
     "00000040", "19720519", "TUN", "PEP", "2",
     "Former prime minister"),
    ("ABDELHAMID DBEIBEH                                     ",
     "00000041", "19590221", "LBY", "PEP", "3",
     "Foreign head of government"),
    ("AHMED ABOUL GHEIT                                      ",
     "00000042", "19420607", "EGY", "PEP", "2",
     "Arab League official"),
    ("OMAR AL-BASHIR                                         ",
     "00000043", "19440101", "SDN", "UNL", "5",
     "UN ICC indicted - Sudan"),
]


def pad(value, length):
    s = str(value)
    if len(s) > length:
        return s[:length]
    return s.ljust(length)


def main():
    print("Generating SANCFILE.dat...")
    records = []
    for entry in SANCTIONED_ENTRIES:
        name, cin, dob, nat, list_code, sev, reason = entry
        record = (
            pad(name, 55) +
            pad(cin, 8) +
            pad(dob, 8) +
            pad(nat, 3) +
            pad(list_code, 3) +
            pad(sev, 1) +
            pad(reason, 60) +
            pad("20240101", 8) +
            pad("", 54)
        )
        record = record[:200].ljust(200)
        records.append(record)

    output = OUTPUT_DIR / "SANCFILE.dat"
    output.write_text("\n".join(records) + "\n", encoding="utf-8")
    print(f"  {output.name}: {len(records)} records written ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
