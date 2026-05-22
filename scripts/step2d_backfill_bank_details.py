"""
Phase 6 / Step 2d: Backfill Employee bank details from HR-supplied list.

Source: Sungas-supplied "Bank accounts.xlsx" (191 rows). The bank data is
baked into this script (no external file upload required at run time).

Matching strategy:
    1. Token-set match `NAMES OF STAFF` against active Employee.employee_name.
       Handles first/last-name reversal (e.g. "JOHN DOMION" -> "Dominion John").
    2. Bank name normalised against canonical Bank doctype names seeded by
       step6a (UBA -> United Bank for Africa, ZENITH BANK -> Zenith Bank Plc, etc.).
    3. Account numbers preserved as strings (leading zeros intact).

Idempotent: only writes when the new value differs.

DRY_RUN=True  -> print plan, no DB writes.
DRY_RUN=False -> persist + commit.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step2d_backfill_bank_details.py" -o /tmp/s2d.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s2d.py').read())"
"""

from __future__ import annotations
import re
from pathlib import Path
import frappe


DRY_RUN = True


# ---------- Bank-name normaliser ----------
# Maps lowercase/cleaned variants -> canonical Bank.name from step6a
BANK_ALIASES: dict[str, str] = {
    "uba":                     "United Bank for Africa",
    "united bank for africa":  "United Bank for Africa",
    "zenith":                  "Zenith Bank Plc",
    "zenith bank":             "Zenith Bank Plc",
    "zenith bank plc":         "Zenith Bank Plc",
    "gtb":                     "GTBank Plc",
    "gtbank":                  "GTBank Plc",
    "gtbank plc":              "GTBank Plc",
    "gt bank":                 "GTBank Plc",
    "first bank":              "First Bank of Nigeria",
    "firstbank":               "First Bank of Nigeria",
    "first bank of nigeria":   "First Bank of Nigeria",
    "access":                  "Access Bank",
    "access bank":             "Access Bank",
    "union bank":              "Union Bank",
    "polaris":                 "Polaris Bank",
    "polaris bank":            "Polaris Bank",
    "sterling":                "Sterling Bank",
    "sterling bank":           "Sterling Bank",
    "fcmb":                    "FCMB",
    "wema":                    "Wema Bank",
    "wema bank":               "Wema Bank",
    "fidelity bank":           "Fidelity Bank",
    "fidelity":                "Fidelity Bank",
    "ecobank":                 "Ecobank Bank",
    "eco bank":                "Ecobank Bank",
    "ecobank bank":            "Ecobank Bank",
    "stanbic ibtc":            "StanbicIBTC Bank",
    "stanbicibtc":             "StanbicIBTC Bank",
    "stanbicibtc bank":        "StanbicIBTC Bank",
    "stanbic":                 "StanbicIBTC Bank",
    "keystone":                "Keystone Bank",
    "keystone bank":           "Keystone Bank",
    "citi":                    "Citi Bank",
    "citi bank":               "Citi Bank",
    "heritage":                "Heritage Bank",
    "heritage bank":           "Heritage Bank",
    "unity":                   "Unity Bank",
    "unity bank":              "Unity Bank",
    "standard chartered":      "Standard Chartered",
    "suntrust":                "Suntrust Bank",
    "suntrust bank":           "Suntrust Bank",
    "providus":                "Providus Bank",
    "providus bank":           "Providus Bank",
    "titan trust":             "Titan Trust Bank",
    "titan trust bank":        "Titan Trust Bank",
    "taj":                     "Taj Bank",
    "taj bank":                "Taj Bank",
    "globus":                  "Globus Bank",
    "globus bank":             "Globus Bank",
    "lotus":                   "Lotus Bank",
    "lotus bank":              "Lotus Bank",
    "jaiz":                    "JAIZ Bank",
    "jaiz bank":               "JAIZ Bank",
    "opay":                    "OPAY",
    "paycom":                  "OPAY",
    "paycom (opay)":           "OPAY",
    "parallex":                "Parallex Bank",
    "parallex bank":           "Parallex Bank",
}


def normalise_bank(raw: str) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"\s+", " ", raw.strip().lower())
    return BANK_ALIASES.get(cleaned)


def name_tokens(name: str) -> frozenset[str]:
    """Return a token set for fuzzy name match. Strips punctuation, uppercases."""
    if not name:
        return frozenset()
    cleaned = re.sub(r"[^A-Za-z\-]", " ", name).upper()
    return frozenset(t for t in cleaned.split() if len(t) > 1)


# Explicit name aliases for HR-file rows whose spelling diverges from ERP records.
NAME_ALIASES: dict[str, str] = {
    "IGBINOVA VICTOR": "Victor Igbinoba",   # HR-EMP-00146
}


# ---------- HR-supplied bank list ----------
BANK_ROWS = [
    ("AHMED YAKUBU",                    "Union Bank",      "0057240551"),
    ("EKI ATAIGIE",                     "POLARIS",         "3027711071"),
    ("ONUWABHAGBE JOHN",                "Fidelity Bank",   "6016642851"),
    ("MICHAEL VICTORIA",                "FIRST BANK",      "3152710537"),
    ("HAWA YAKUBU",                     "ACCESS BANK",     "0060547248"),
    ("AYEGHER TERHEMBA",                "ACCESS BANK",     "1538107874"),
    ("IGBUDU MSUGHTER BARTHOLOMEW",     "UBA",             "2135379303"),
    ("PIUS SARAH ANGEL",                "WEMA",            "0426384517"),
    ("OLADIMEJI BUKOLA MARY",           "FCMB",            "1003479289"),
    ("EZE IGNATIUS",                    "FIRST BANK",      "3199673194"),
    ("OSAGIE VICTOR IMONITIE",          "zenith bank",     "2416687198"),
    ("OGBEVOEN WISDOM",                 "UBA",             "2123044943"),
    ("IRENE EMMANUEL",                  "UBA",             "2026588904"),
    ("SULAIMAN NIMOTA AYOBAMI",         "UBA",             "2133326585"),
    ("OKPARA CHUKWUEMEKA",              "ACCESS",          "1953562180"),
    ("OKOTOGBO GIFT",                   "GTB",             "0677720947"),
    ("AYO SUNDAY ILESANMI",             "ACCESS",          "1638641531"),
    ("SAMUEL ANTHONY",                  "ACCESS BANK",     "1231018468"),
    ("IGBINOVA VICTOR",                 "FIRST BANK",      "3210238753"),
    ("JOHN DOMION",                     "Union Bank",      "0223181079"),
    ("UGWOKE OBINNA PRINCEWELL",        "ACCESS",          "0820351030"),
    ("BENJAMIN ENOBOH",                 "ACCESS",          "0813044046"),
    ("UWAGWE MACAULEY",                 "GTB",             "0109301412"),
    ("OYIZA DEBORAH",                   "ACCESS BANK",     "1455667747"),
    ("IFY CHUKS",                       "KEYSTONE",        "6037822284"),
    ("AFENGBAI TIMOTHY",                "UBA",             "2282805872"),
    ("SHITTU BABATUNDE",                "WEMA",            "0233479484"),
    ("CHINELO ANIEGBUANAM",             "FIRST BANK",      "3100711171"),
    ("ALOZIE FAITH",                    "GTBANK",          "0556702455"),
    ("DENEDO JEREMIAH",                 "ACCESS BANK",     "1811636903"),
    ("IORPUU EMMANUEL",                 "ACCESS BANK",     "1398285703"),
    ("OSADOLOR OSAMWONYI",              "union bank",      "0174767933"),
    ("SHIMA JUSTINE AONDOAKULA",        "GTBANK",          "0244634316"),
    ("ORTSERGA SAMUEL",                 "UBA",             "2145521130"),
    ("IGBINEDE EMMANUEL",               "FCMB",            "1006011390"),
    ("ODIHI GIFT",                      "ACCESS BANK",     "1781612914"),
    ("EMMANUEL ANANDE",                 "ACCESS BANK",     "1891149081"),
    ("OKUWHERE HELEN",                  "ECOBANK",         "3960073751"),
    ("USHAHEMBA AYEM VICTOR",           "UBA",             "2352717188"),
    ("MELODY UDJOR OGHENEVWEGBA",       "UBA",             "2367766023"),
    ("FAVOUR OGOCHUKWU",                "ZENITH",          "2765625429"),
    ("OBAZU JEREMIAH",                  "UBA",             "2094091713"),
    ("OBI VICTOR",                      "First bank",      "3120825719"),
    ("TAKPOR EFE",                      "First bank",      "3197457356"),
    ("EMMANUELLA BENJAMIN",             "WEMA",            "0406834025"),
    ("DOMINION ROLAND",                 "ACCESS",          "1947919792"),
    ("BULUS SATI",                      "UBA",             "2311657009"),
    ("GODWIN SAVIOUR",                  "UBA",             "2314285751"),
    ("ISAAC ONWUZULUIGBO",              "STERLING",        "0142720863"),
    ("AYOMIDE JOSHUA",                  "UBA",             "2353031375"),
    ("EKHOWMANYE RUTH",                 "UBA",             "2140957800"),
    ("ORIAKHI RACHEAL O.",              "First bank",      "3050313395"),
    ("DANIEL DAVID",                    "First bank",      "3211754720"),
    ("SATURDAY ALETOR EFFOR",           "ZENITH",          "2402486901"),
    ("BLESSING NGAWCHI",                "First bank",      "3231973246"),
    ("IYARE FAVOUR",                    "ZENITH",          "2251895266"),
    ("EMADU BLESSING",                  "zenith bank",     "2400379269"),
    ("OKON ENDURANCE",                  "UBA",             "2084098337"),
    ("MMADUABUCHI CHIKODI",             "UBA",             "2325802402"),
    ("STANLEY IDRIS",                   "GTB",             "0624837421"),
    ("ANAS SHAMSUDDEEN",                "ACCESS",          "1437985021"),
    ("ONOMEASIKELE GODWIN O.",          "STANBIC IBTC",    "0081989680"),
    ("ABIGAIL SOLOMON",                 "Access Bank",     "0017058186"),
    ("DANIEL ALABO DOKUBO",             "Access Bank",     "1493522257"),
    ("NWANKWO EMMANUEL NICHOLAS",       "GTB",             "0667013534"),
    ("GODKNOWS SOLOMON",                "UBA",             "2215377456"),
    ("HENRY JOHNSON YOWIKA",            "ACCESS",          "1854854647"),
    ("KALADA VICTOR GREEN",             "zenith",          "2193134856"),
    ("COVENANT EFFIONG",                "UBA",             "2333490835"),
    ("NNOROM EMMANUEL",                 "GTB",             "0251831142"),
    ("VINCENT JONNY UWEN",              "Access Bank",     "1880170236"),
    ("SAMUEL NANIA MICHAEL",            "UBA",             "2132873831"),
    ("AGBEGE OSEMUDIAMEN FELICITY",     "Access Bank",     "1626521423"),
    ("SARAH WEALTH",                    "Access Bank",     "1920216869"),
    ("WISDOM SUNEBARI NAADE",           "First bank",      "3209318796"),
    ("AKARI OTUOTU",                    "zenith",          "4314726814"),
    ("EBIKONBOERE FLOURISH AKUNA",      "UBA",             "2329134789"),
    ("OSINACHI NWAOBA",                 "GTB",             "0633703034"),
    ("GODSPOWER FIRST SOLOMON",         "UBA",             "2343273280"),
    ("NWOBODO IZUCHUKWU E.",            "First bank",      "3125972522"),
    ("ENUGU WISDOM",                    "ECO BANK",        "3710012201"),
    ("BARIYAA JOHN TAMBARI",            "Fidelity Bank",   "6552952814"),
    ("NNANNA HUMBLE AMARACHI",          "Fidelity Bank",   "6018505439"),
    ("FIDELIS AKPAN GODWIN",            "zenith",          "2080144216"),
    ("ECHEAZU CHIDIMMA PATIENCE",       "Access Bank",     "0034468297"),
    ("ELTON GABRIEL",                   "Fidelity Bank",   "6978880469"),
    ("AKARI ILAMI THANKGOD",            "polaris",         "3020251738"),
    ("ABIGAIL NANEE",                   "UBA",             "2219769161"),
    ("ABANIKANDA FEMI",                 "First Bank",      "3064729229"),
    ("AYO AKINBOBOLA",                  "Access Bank",     "0804576606"),
    ("JIMOH IBRAHIM",                   "First Bank",      "3100955984"),
    ("OGUNSHOLA NURUDEEN",              "Access Bank",     "0801805471"),
    ("ISEME GLORY",                     "First Bank",      "3010883016"),
    ("HANNAH DAVID EFFIONG",            "STANBIC IBTC",    "0033726738"),
    ("EWONA CHARITY",                   "ZENITH BANK",     "2114189156"),
    ("OBI RASHEED",                     "Fidelity Bank",   "6323654864"),
    ("OJERUSE ROLAND",                  "GTBANK",          "0199740504"),
    ("KILANKO ASHIMIYU",                "Gtbank",          "0567520185"),
    ("ADEBISI ADETUNJI",                "Gtbank",          "0019670709"),
    ("ISMAIL ABOLORE DAVIES",           "ZENITH BANK",     "2009817599"),
    ("RAZAQ ADIGUN",                    "Gtbank",          "0035175358"),
    ("OLUWAROTIMI BUKOLA",              "ZENITH BANK",     "2175290327"),
    ("ALAO ESTHER TITILAYO",            "Gtbank",          "0220927939"),
    ("VICTORIA ESENAM ATIYOE",          "UBA",             "2184297023"),
    ("ADEWUSI JIMOH ADIO",              "First Bank",      "3192868591"),
    ("JAMES AREMU OLADEJO",             "UBA",             "2094725854"),
    ("OYEDELE ALIU BABATUNDE",          "UBA",             "2316436650"),
    ("FALANA OLUWATOYIN",               "GTBANK",          "0235322196"),
    ("BANJO ADEDAYO",                   "ZENITH BANK",     "2531511952"),
    ("ORIOYE TITUS SUNDAY",             "Access Bank",     "0055205207"),
    ("OSHOALA KOREDE HAZEEM",           "FCMB",            "6204790012"),
    ("PROSPER OGALA",                   "OPAY",            "9021437045"),
    ("OCHONOGOR OLISE",                 "STERLING",        "0086619405"),
    ("AYODELE SHERIFDEEN",              "UBA",             "2357072866"),
    ("CHRISTIAN-DAN SUSAN",             "Access Bank",     "1624616406"),
    ("AZEEZ SULAIMON ADEKUNLE",         "First Bank",      "3121557602"),
    ("ADEBAKIN SULAIMON",               "FCMB",            "6983651018"),
    ("SALAU MUTIU",                     "First Bank",      "3055061282"),
    ("ADEWOYE ADESANYA",                "FCMB",            "2415260018"),
    ("UBOJU PRINCE EMMANUEL",           "First Bank",      "3082490350"),
    ("ADEBAYO DOLAPO DEBORAH",          "GTBANK",          "0376324679"),
    ("OLUFUWAPE REUBEN",                "STERLING",        "0504262600"),
    ("OGUNTUASE MOSES TAYO",            "WEMA",            "0233747189"),
    ("AYINLA SIKIRU OLALEKAN",          "UBA",             "2137802414"),
    ("OGBOJI SUNNY",                    "UBA",             "2093623135"),
    ("AMEH MONDAY",                     "UBA",             "2101546793"),
    ("ABIODUN JACKSON",                 "ZENITH BANK",     "2212334247"),
    ("ADETANSOLA GABRIEL",              "GTBANK",          "0142233059"),
    ("OKPAKO STELLA",                   "Access Bank",     "1450318178"),
    ("NNAMANI JAMES AMAECHI",           "Fidelity Bank",   "6551637510"),
    ("AUDU ABU",                        "UBA",             "2310821476"),
    ("ANYEBE OCHANYA ELIZABETH",        "UBA",             "2173218697"),
    ("OGUMAR SONIA",                    "UBA",             "2231129527"),
    ("LAWAL MOHAMMED",                  "UBA",             "2123726906"),
    ("SAMUEL DAVID AKPA",               "First Bank",      "3222557358"),
    ("SULEIMAN ISMAIL",                 "GTBANK",          "0523745122"),
    ("EFFIONG UKEME PEACE",             "GTBANK",          "0619328132"),
    ("AGADA EMMANUEL ELEOJO",           "First Bank",      "3228451276"),
    ("VIHIMGA COURAGE T",               "GTBANK",          "0689426800"),
    ("EDORUME JONATHAN OBOAPOROHO",     "UBA",             "2125629881"),
    ("AGADA QUEEN ESTHER",              "GTBANK",          "0561332281"),
    ("GABRIEL EMMANUEL ADAH",           "UBA",             "2398591801"),
    ("OKEWU QUEEN OJONUMA",             "UBA",             "2362844281"),
    ("SAHEED EGAJI USMAN",              "GTBANK",          "0235152012"),
    ("AUDU MONDAY",                     "First Bank",      "3115840606"),
    ("DURU JEREMIAH",                   "ZENITH BANK",     "4319456048"),
    ("STEPHEN DENNIS OSEWE",            "First Bank",      "3155602628"),
    ("ADEYEMI TAIWO NAFIU",             "UBA",             "2361107365"),
    ("MATHEW CECILIA OLUWAKEMI",        "POLARIS",         "1130239925"),
    ("DUFF EFFIONG",                    "UBA",             "2133049433"),
    ("AYODELE BOLANLE ROFIAT",          "First Bank",      "3145075764"),
    ("ABILAWON BOLAJOKO",               "Access Bank",     "0810745366"),
    ("SALAU ADEDOLAPO IBRAHIM",         "UBA",             "2388833311"),
    ("ASEESE ADEWALE ADENIYI",          "UBA",             "2074459018"),
    ("MORGAN FRIDAY",                   "UBA",             "2166245251"),
    ("BAKARE OLUWAFUNKE MORENIKE",      "Access Bank",     "0033728129"),
    ("AMOS BLESSING CHIAMAKA",          "WEMA",            "0422014425"),
    ("LAWAL TOYIN",                     "ZENITH BANK",     "2997420429"),
    ("TOSIN KAYODE EMMANUEL",           "UBA",             "2144534904"),
    ("HAMMED TAOHEED",                  "WEMA",            "0422009007"),
    ("KUFORIJI BAZEET OLAMILEKAN",      "Access Bank",     "1950878228"),
    ("HASSAN TAIWO LATEEFAT",           "ACCESS BANK",     "0030226670"),
    ("IBIWOYE OMOWUNMI ADURAGBEMI",     "UBA",             "2183661355"),
    ("AGBEDEYI ABIGEAL",                "UBA",             "2067228812"),
    ("SHODEINDE LUKMON ORIYOMI",        "UBA",             "2236058774"),
    ("OSHO MAYOKUN JOHN",               "UBA",             "2353016338"),
    ("ADEOYE ADEKUNLE",                 "UBA",             "2233201603"),
    ("KAREEM KAOSARA ENIOLA",           "FIRST BANK",      "3214607652"),
    ("ABIONA ROTIMI DANIEL",            "WEMA",            "0236777806"),
    ("PATRICK SUCCESS",                 "GTB",             "0211462078"),
    ("AKINWALERE FUNMILAYO",            "FIRST BANK",      "3079458518"),
    ("OGUGUOM EUNICE",                  "zenith",          "2219027997"),
    ("KOREDE AYOMIDE",                  "Access Bank",     "1658489526"),
    ("ARIYO OLAOLUWA OLANREWAJU",       "zenith",          "2270196276"),
    ("EDE SAMUEL",                      "UBA",             "2359441163"),
    ("ADEOYE ADEWALE",                  "GTB",             "0228034972"),
    ("ADEDEJI WURAOLA GRACE",           "FIRSTBANK",       "3094074195"),
    ("ADEWALE ESTHER",                  "POLARIS",         "3031991157"),
    ("ADARALEGBE BUKOLA",               "UBA",             "2356255037"),
    ("CHIGOZIE EBONUGWO STEPHEN",       "ZENITH",          "2278415539"),
    ("AMAEFULE VALENTINE",              "UBA",             "2086993058"),
    ("OLAIYA KAFAYAT",                  "FCMB",            "5829538010"),
    ("AKOMOLAFE AYODEJI FEMI",          "FIRSTBANK",       "3147888038"),
    ("KADEJO MARY",                     "GTB",             "0212482770"),
    ("ADESINA OLUWASETEMI D.",          "Access Bank",     "1830849801"),
    ("HAMMED WALIU ALADE",              "PARALLEX BANK",   "2002835618"),
    ("AMBALI OLAWALE",                  "FIRSTBANK",       "3077887091"),
    ("TEMILOLA OLUGBENGA O.",           "ZENITH",          "2121919360"),
    ("OLAWOLE OLUWASEYI",               "UBA",             "2325971706"),
    ("AKINLADE AYOMIDE MICHAEL",        "UBA",             "2399568026"),
    ("KILASHO FATAI",                   "FIRST BANK",      "3101460562"),
    ("ADEWUNMI AKINYEMI",               "UBA",             "2337323090"),
    ("OLAWOYIN OLADAYO",                "ZENITH",          "2766485862"),
    ("ADEKOYA TOSIN SEYIFUNMI",         "FIRST BANK",      "3132078231"),
    ("SHONUBI OLUWUNMI AFOLAKE",        "UNITY BANK",      "0061431379"),
    ("KAREEM EMMANUEL",                 "POLARIS",         "3054851113"),
    ("AYINLA SUNDAY BOLUWATIFE",        "FIRST BANK",      "3232185666"),
    ("KUDIRAT TITILAYO MURITADOR",      "FIRST BANK",      "3137522193"),
    ("UDOH JOHN",                       "Gtbank",          "0162612205"),
    ("BISHOP AMOS",                     "access",          "1766688428"),
    ("HASSAN ADESEYE OMOJOLA",          "Gtbank",          "0113316835"),
    ("JOSEPH ADAMA",                    "First bank",      "3040814572"),
    ("NEGEDU CALEB ENYO-OJO",           "access",          "1444552353"),
    ("AKOGWU BLESSING",                 "UBA",             "2112434463"),
    ("MOSES RACHEAL REMILEKUN",         "Gtbank",          "0468110362"),
    ("AGABIELESIN EMMANUEL OPEYEMI",    "FCMB",            "1046582090"),
    ("VICTOR ENEOJO JOHN",              "FCMB",            "1047585380"),
]


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 2d -- Bank Details Backfill (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    # 1. Build {token-set: employee} index for active payroll-eligible employees.
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "bank_name", "bank_ac_no"],
    )
    by_token: dict[frozenset[str], list[dict]] = {}
    for e in employees:
        toks = name_tokens(e["employee_name"])
        if toks:
            by_token.setdefault(toks, []).append(e)

    # 2. Walk the HR list and resolve each row.
    matched: list[tuple[dict, str, str]] = []     # (emp, canonical_bank, acct_no)
    bank_unmapped: dict[str, list[str]] = {}       # bank_raw -> [staff names]
    name_unmatched: list[tuple[str, str, str]] = []
    name_ambiguous: list[tuple[str, list[str]]] = []
    canonical_bank_misses: list[tuple[str, str]] = []  # (raw_bank, alias_lookup)

    for staff_name, bank_raw, acct_no in BANK_ROWS:
        # Apply explicit alias if present (handles spelling drift like Igbinova vs Igbinoba)
        alias_target = NAME_ALIASES.get(staff_name)
        candidates: list[dict] = []
        if alias_target:
            emp_row = frappe.db.get_value(
                "Employee",
                {"employee_name": alias_target, "status": "Active"},
                ["name", "employee_name", "bank_name", "bank_ac_no"],
                as_dict=True,
            )
            if emp_row:
                candidates = [emp_row]

        # Token-set match on employee name. Try exact, then strict subset, then loose intersection.
        toks = name_tokens(staff_name)
        if not candidates:
            # Exact token match
            if toks in by_token:
                candidates = by_token[toks]
            else:
                # Strict: every token in HR set is present in employee tokens
                for emp_toks, emps in by_token.items():
                    if toks <= emp_toks:
                        candidates.extend(emps)
                if not candidates:
                    # Loose: at least 2-token intersection (handles middle-name drops)
                    for emp_toks, emps in by_token.items():
                        if len(toks & emp_toks) >= 2 and len(toks) >= 2 and len(emp_toks) >= 2:
                            # Bonus: require either first or last token to match for safety
                            if (next(iter(sorted(toks))) in emp_toks
                                    or next(iter(sorted(toks, reverse=True))) in emp_toks):
                                candidates.extend(emps)

        # Dedupe by Employee.name
        seen = set()
        candidates = [c for c in candidates if c["name"] not in seen and not seen.add(c["name"])]

        if not candidates:
            name_unmatched.append((staff_name, bank_raw, acct_no))
            continue
        if len(candidates) > 1:
            name_ambiguous.append((staff_name, [c["name"] for c in candidates]))
            continue
        emp = candidates[0]

        canonical_bank = normalise_bank(bank_raw)
        if not canonical_bank:
            bank_unmapped.setdefault(bank_raw, []).append(staff_name)
            canonical_bank_misses.append((bank_raw, bank_raw.lower()))
            continue
        if not frappe.db.exists("Bank", canonical_bank):
            bank_unmapped.setdefault(canonical_bank, []).append(f"{staff_name} (alias OK but Bank doctype missing)")
            continue

        matched.append((emp, canonical_bank, str(acct_no)))

    # 3. Apply
    written = 0
    unchanged = 0
    for emp, bank, acct in matched:
        if emp.get("bank_name") == bank and (emp.get("bank_ac_no") or "") == acct:
            unchanged += 1
            continue
        if DRY_RUN:
            written += 1
            continue
        frappe.db.set_value("Employee", emp["name"], "bank_name", bank, update_modified=False)
        frappe.db.set_value("Employee", emp["name"], "bank_ac_no", acct, update_modified=False)
        written += 1
    if not DRY_RUN:
        frappe.db.commit()

    # 4. Summary
    print()
    print(f"  HR rows                : {len(BANK_ROWS)}")
    print(f"  Matched (resolved)     : {len(matched)}")
    print(f"  Already correct        : {unchanged}")
    print(f"  {'Will write' if DRY_RUN else 'Wrote'}                : {written}")
    print(f"  Name unmatched          : {len(name_unmatched)}")
    print(f"  Name ambiguous (>1 hit) : {len(name_ambiguous)}")
    print(f"  Bank-name unmapped      : {len(bank_unmapped)}")

    if name_unmatched[:20]:
        print()
        print("  Sample unmatched names (first 20):")
        for n, b, a in name_unmatched[:20]:
            print(f"    - {n:<35} -> bank={b}, acct={a}")

    if name_ambiguous:
        print()
        print("  Ambiguous matches (rejected -- need manual edit):")
        for n, options in name_ambiguous[:20]:
            print(f"    - {n:<35} -> {', '.join(options[:5])}")

    if bank_unmapped:
        print()
        print("  Unmapped bank names (need to add to BANK_ALIASES or seed Bank doctype):")
        for b, staff in bank_unmapped.items():
            print(f"    - {b!r}: {len(staff)} staff -- e.g. {staff[0]}")

    # Write detailed report + skip CSV
    md = [
        f"# Step 2d -- Bank Details Backfill (DRY_RUN={DRY_RUN})",
        "",
        f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site}_",
        "",
        "## Summary",
        "",
        f"- HR rows                : {len(BANK_ROWS)}",
        f"- Matched (resolved)     : {len(matched)}",
        f"- Already correct        : {unchanged}",
        f"- {'Will write' if DRY_RUN else 'Wrote'}                : {written}",
        f"- Name unmatched          : {len(name_unmatched)}",
        f"- Name ambiguous          : {len(name_ambiguous)}",
        f"- Bank-name unmapped      : {len(bank_unmapped)}",
        "",
    ]
    if name_unmatched:
        md.append("## Unmatched names")
        md.append("")
        md.append("| HR Name | Bank | Account |")
        md.append("|---------|------|---------|")
        for n, b, a in name_unmatched:
            md.append(f"| {n} | {b} | {a} |")
        md.append("")
    if name_ambiguous:
        md.append("## Ambiguous matches")
        md.append("")
        for n, options in name_ambiguous:
            md.append(f"- {n} -> {', '.join(options)}")
        md.append("")
    if bank_unmapped:
        md.append("## Unmapped banks")
        md.append("")
        for b, staff in bank_unmapped.items():
            md.append(f"- `{b}` ({len(staff)} staff)")
            for s in staff[:5]:
                md.append(f"    - {s}")
        md.append("")

    p = Path("/tmp/step2d_bank_backfill.md")
    p.write_text("\n".join(md), encoding="utf-8")
    print()
    print(f"[OK] {p}")
    if DRY_RUN:
        print()
        print("[DRY_RUN] No DB writes. Set DRY_RUN=False and re-run to apply.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
