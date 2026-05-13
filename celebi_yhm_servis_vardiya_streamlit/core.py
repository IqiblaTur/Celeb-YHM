from __future__ import annotations

import io
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

POOL_AIRLINES = {"UZB", "IAW", "DAH", "FAD", "RAM", "BRU", "AWG"}
DEFAULT_ARRIVAL_TIMES = ["02:30", "04:30", "06:30", "08:00", "10:00", "11:30", "14:00", "16:30", "20:00", "23:59"]
DEFAULT_DEPARTURE_TIMES = ["00:30", "02:30", "04:30", "08:30", "14:30", "17:00", "19:30", "20:30", "23:00"]

AIRLINE_ALIASES: Dict[str, List[str]] = {
    "UZB": ["UZB", "UZBEKISTAN"],
    "AEE": ["AEE", "AEGEAN"],
    "ABY": ["ABY", "AIRARABIA", "ARABIA"],
    "IAW": ["IAW", "IRAK", "IRAQ"],
    "KAC": ["KAC", "KUVEYT", "KUWAIT"],
    "CES": ["CES", "MU", "CHINA EASTERN"],
    "CSN": ["CSN", "CZ", "CHINA SOUTHERN"],
    "CCA": ["CCA", "CA", "AIRCHINA", "AIR CHINA"],
    "CSC": ["CSC", "3U", "SICHUAN"],
    "AWG": ["AWG", "A2", "ANIMAWINGS"],
    "DLH": ["DLH", "LH", "LUFTHANSA"],
    "KZR": ["KZR", "SCAT"],
    "ETD": ["ETD", "EY", "ETIHAD"],
    "UAE": ["UAE", "EK", "EMIRATES"],
    "SVA": ["SVA", "SV", "SAUDI"],
    "AHY": ["AHY"],
    "AAR": ["AAR"],
    "KAL": ["KAL"],
    "UBD": ["UBD"],
    "VSV": ["VSV"],
    "FAD": ["FAD"],
    "DAH": ["DAH"],
    "RAM": ["RAM"],
    "BRU": ["BRU"],
}


def normalize_text(value: object) -> str:
    """Uppercase, de-accent and remove noisy whitespace for matching."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip().upper()
    text = text.replace("İ", "I").replace("ı", "I")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text


def compact_token(value: object) -> str:
    return re.sub(r"[^A-Z0-9_]", "", normalize_text(value))


def read_csv_smart(source, *, sep: Optional[str] = None) -> pd.DataFrame:
    """Read CSV/Excel uploads robustly. Handles semicolon Turkish exports and comma CSVs."""
    if source is None:
        return pd.DataFrame()

    if isinstance(source, (str, Path)):
        path = Path(source)
        suffix = path.suffix.lower()
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(path)
        # Read bytes once so we can retry separators.
        raw = path.read_bytes()
    else:
        raw = source.getvalue()

    encodings = ["utf-8-sig", "utf-8", "cp1254", "latin1"]
    separators = [sep] if sep else [None, ";", ",", "\t"]
    last_error = None
    best_df = pd.DataFrame()
    best_score = -1
    for enc in encodings:
        for s in separators:
            try:
                text = raw.decode(enc, errors="replace")
                if s is None:
                    df = pd.read_csv(io.StringIO(text), sep=None, engine="python")
                else:
                    df = pd.read_csv(io.StringIO(text), sep=s, engine="python")
                # score by number of real columns and non-empty cells
                real_cols = [c for c in df.columns if not str(c).startswith("Unnamed")]
                score = len(real_cols) * 10 + min(len(df), 10)
                if score > best_score:
                    best_df, best_score = df, score
            except Exception as exc:  # pragma: no cover - defensive retry
                last_error = exc
    if best_df.empty and last_error:
        raise last_error
    return clean_columns(best_df)


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    # Keep unnamed columns only when they contain data; otherwise remove.
    drop_cols = []
    for c in df.columns:
        if str(c).lower().startswith("unnamed") and df[c].isna().all():
            drop_cols.append(c)
    if drop_cols:
        df = df.drop(columns=drop_cols)
    return df


def parse_departures(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = clean_columns(df)
    # If the CSV was read as one column, retry with semicolon when possible.
    if len(df.columns) == 1 and ";" in str(df.columns[0]):
        return pd.DataFrame()

    rename_map = {}
    for c in df.columns:
        n = normalize_text(c)
        if n in {"A/L", "AL", "AIRLINE"}:
            rename_map[c] = "airline"
        elif n == "IN":
            rename_map[c] = "in_flight"
        elif n == "OUT":
            rename_map[c] = "out_flight"
        elif n == "STA":
            rename_map[c] = "sta"
        elif n == "STD":
            rename_map[c] = "std"
        elif "A/C" in n or "TYPE" in n or "UCAK" in n:
            rename_map[c] = "aircraft_type"
    df = df.rename(columns=rename_map)

    # Passenger/config column is usually the first non-named column after aircraft type.
    if "pax_raw" not in df.columns:
        candidates = [c for c in df.columns if c not in {"airline", "in_flight", "out_flight", "sta", "std", "aircraft_type"}]
        if candidates:
            df = df.rename(columns={candidates[0]: "pax_raw"})
        else:
            df["pax_raw"] = ""

    required = ["airline", "in_flight", "out_flight", "sta", "std", "aircraft_type", "pax_raw"]
    for col in required:
        if col not in df.columns:
            df[col] = ""

    out = df[required].copy()
    out["airline"] = out["airline"].map(compact_token)
    out["std_dt"] = pd.to_datetime(out["std"], dayfirst=True, errors="coerce")
    out["sta_dt"] = pd.to_datetime(out["sta"], dayfirst=True, errors="coerce")
    out["pax_count"] = out["pax_raw"].map(parse_pax_count)
    out["flight_key"] = out["airline"].fillna("") + "-" + out["out_flight"].astype(str).fillna("")
    out = out.dropna(subset=["std_dt"])
    out = out[out["airline"].astype(str).str.len() > 0]
    out = out.sort_values("std_dt").reset_index(drop=True)
    return out


def parse_pax_count(value: object) -> int:
    text = str(value or "")
    # In cells like 10+197 (22+222), the first part is planned pax; parentheses are config/alternative.
    text = text.split("(")[0]
    nums = [int(x) for x in re.findall(r"\d+", text)]
    return int(sum(nums)) if nums else 0


def parse_staff(qual_df: pd.DataFrame, route_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    if qual_df is None or qual_df.empty:
        return pd.DataFrame(columns=["name", "qualifications", "route", "employment_type", "max_weekly_hours", "is_active"])
    q = clean_columns(qual_df)
    name_col = next((c for c in q.columns if "PERSONEL" in normalize_text(c) or "ISIM" in normalize_text(c) or "AD" in normalize_text(c)), q.columns[0])
    qual_col = next((c for c in q.columns if "YETKIN" in normalize_text(c) or "QUAL" in normalize_text(c)), q.columns[-1])
    staff = q[[name_col, qual_col]].rename(columns={name_col: "name", qual_col: "qualifications"}).copy()
    staff["name"] = staff["name"].astype(str).str.strip()
    staff["name_key"] = staff["name"].map(normalize_text)
    staff["qualifications"] = staff["qualifications"].fillna("").astype(str)
    staff["employment_type"] = "Full-time"
    staff["max_weekly_hours"] = 50
    staff["is_active"] = True

    if route_df is not None and not route_df.empty:
        r = clean_columns(route_df)
        route_name_col = next((c for c in r.columns if "ISIM" in normalize_text(c) or "SOYISIM" in normalize_text(c) or "PERSONEL" in normalize_text(c)), r.columns[0])
        route_col = next((c for c in r.columns if "GUZERGAH" in normalize_text(c) or "ROUTE" in normalize_text(c)), r.columns[-1])
        routes = r[[route_name_col, route_col]].rename(columns={route_name_col: "name", route_col: "route"}).copy()
        routes["name_key"] = routes["name"].map(normalize_text)
        routes["route"] = routes["route"].map(compact_token)
        staff = staff.merge(routes[["name_key", "route"]], on="name_key", how="left")
        # Some route files include an extra/missing middle name. Fill blank routes with a safe substring match.
        route_lookup = routes[["name_key", "route"]].dropna().drop_duplicates().to_dict("records")
        def fuzzy_route(row):
            current = row.get("route", "")
            if isinstance(current, str) and current.strip():
                return current
            key = row.get("name_key", "")
            for item in route_lookup:
                rk = item["name_key"]
                if key and rk and (key in rk or rk in key):
                    return item["route"]
            return ""
        staff["route"] = staff.apply(fuzzy_route, axis=1)
    else:
        staff["route"] = ""

    staff["route"] = staff["route"].fillna("").map(compact_token)
    return staff.reset_index(drop=True)


def parse_hakedis(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    h = clean_columns(df).copy()
    if len(h.columns) >= 4:
        h = h.rename(columns={
            h.columns[0]: "airline_name",
            h.columns[1]: "criteria_type",
            h.columns[2]: "criteria_detail",
            h.columns[3]: "counter_text",
        })
        if len(h.columns) >= 5:
            h = h.rename(columns={h.columns[4]: "notes"})
    for col in ["airline_name", "criteria_type", "criteria_detail", "counter_text", "notes"]:
        if col not in h.columns:
            h[col] = ""
    h["airline_name"] = h["airline_name"].ffill().fillna("")
    h["counter_count"] = h["counter_text"].map(extract_first_int)
    h["la_required"] = h["counter_text"].astype(str).str.contains("LA", case=False, na=False)
    return h


def extract_first_int(value: object) -> int:
    nums = re.findall(r"\d+", str(value or ""))
    return int(nums[0]) if nums else 0


def calculate_requirement(row: pd.Series) -> Dict[str, object]:
    airline = compact_token(row.get("airline", ""))
    pax = int(row.get("pax_count", 0) or 0)
    ac = compact_token(row.get("aircraft_type", ""))
    std_dt = row.get("std_dt")
    hour = std_dt.hour if hasattr(std_dt, "hour") else 12
    counters = 0
    la_required = False
    rule = "Genel kural: her 50 yolcuya 1 kontuar, minimum 2 kontuar."

    if airline == "UZB":
        if pax <= 150:
            counters = 4
            rule = "Uzbekistan 0-150 yolcu: 4 kontuar."
        elif pax <= 200:
            counters = 5
            rule = "Uzbekistan 150-200 yolcu: 5 kontuar."
        else:
            counters = 7
            rule = "Uzbekistan 200+ yolcu: 7 kontuar."
    elif airline == "AEE":
        if pax <= 60:
            counters = 2
            rule = "Aegean 0-60 yolcu: 2 kontuar."
        elif pax <= 119:
            counters = 3
            rule = "Aegean 61-119 yolcu: 3 kontuar."
        else:
            counters = 4
            rule = "Aegean 120+ yolcu: 4 kontuar."
    elif airline == "ABY":
        if pax <= 56:
            counters = 1
            rule = "Arabia 0-56 yolcu: 1 kontuar."
        elif pax <= 111:
            counters = 2
            rule = "Arabia 56-111 yolcu: 2 kontuar."
        elif pax <= 167:
            counters = 3
            rule = "Arabia 112-167 yolcu: 3 kontuar."
        else:
            counters = 4
            rule = "Arabia 168+ yolcu: 4 kontuar."
    elif airline == "IAW":
        counters = 1 if pax <= 60 else max(2, math.ceil(pax / 60))
        rule = "Irak 0-60 yolcu: 1 kontuar; üstü için her 60 yolcuya yaklaşık 1 kontuar."
    elif airline == "KAC":
        la_required = True
        if ac.startswith("77"):
            counters = 8
            rule = "Kuveyt 777 tipi: 8 kontuar + 1 LA."
        elif ac in {"332", "338"} or ac.startswith("33"):
            counters = 6
            rule = "Kuveyt 332/338 tipi: 6 kontuar + 1 LA."
        elif ac.startswith("32"):
            counters = 4
            rule = "Kuveyt 320 tipi: 4 kontuar + 1 LA."
        else:
            counters = 6
            rule = "Kuveyt varsayılan: 6 kontuar + 1 LA."
    elif airline == "CES":
        counters = 7 if pax >= 240 else 6
        rule = "China Eastern: 240+ konfigürasyon 7+1; <240 6 kontuar."
    elif airline == "CSN":
        counters = 8 if pax >= 240 else max(6, math.ceil(max(pax, 1) / 40) + 1)
        rule = "China Southern: 240+ 8 kontuar; <240 değişken hesap."
    elif airline == "CCA":
        counters = 6
        rule = "Air China: sabit 6 kontuar."
    elif airline == "CSC":
        counters = 7 if hour >= 8 else max(4, math.ceil(max(pax, 1) / 50))
        rule = "Sichuan gündüz TFU: 7 kontuar; gece/Atina: talebe göre."
    elif airline == "AWG":
        counters = max(1, math.ceil(max(pax, 1) / 60))
        if pax > 0:
            counters += 1  # business possibility buffer
        rule = "Animawings: her 60 yolcuya 1 kontuar; Bzn ihtimali için +1 buffer."
    elif airline == "DLH":
        counters = 7 if (hour < 8 or hour >= 21) else 6
        rule = "Lufthansa: gece 6+1, gündüz 5+1 kontuar."
    elif airline == "KZR":
        counters = max(1, math.ceil(max(pax, 1) / 50))
        rule = "Scat Airways: her 50 yolcuya 1 kontuar."
    else:
        counters = max(2, math.ceil(max(pax, 1) / 50))
        rule = "Varsayılan: her 50 yolcuya 1 kontuar, minimum 2."

    total = counters + (1 if la_required else 0)
    return {
        "counter_count": int(counters),
        "la_required": bool(la_required),
        "required_staff": int(max(1, total)),
        "rule_applied": rule,
        "requires_supervisor": airline in POOL_AIRLINES,
    }


def enrich_departures_with_requirements(departures: pd.DataFrame) -> pd.DataFrame:
    if departures.empty:
        return departures
    enriched = departures.copy()
    reqs = enriched.apply(calculate_requirement, axis=1, result_type="expand")
    for c in reqs.columns:
        enriched[c] = reqs[c]
    return enriched


def qualification_tokens(qual_string: object) -> List[str]:
    text = normalize_text(qual_string).replace(" ", "-")
    raw_tokens = re.split(r"[-/;,]+", text)
    tokens = []
    for tok in raw_tokens:
        t = compact_token(tok)
        if t:
            tokens.append(t)
    # Also preserve combined patterns separated by underscores, e.g. IAW_S.
    return tokens


def person_can_work(qual_string: object, airline: str) -> bool:
    airline = compact_token(airline)
    aliases = AIRLINE_ALIASES.get(airline, [airline])
    tokens = qualification_tokens(qual_string)
    token_set = set(tokens)
    if airline in POOL_AIRLINES:
        return True
    for alias in aliases:
        a = compact_token(alias)
        if a in token_set or f"{a}_S" in token_set or f"{a}_L" in token_set or f"{a}_T" in token_set:
            return True
    return False


def person_is_supervisor(qual_string: object, airline: Optional[str] = None) -> bool:
    tokens = qualification_tokens(qual_string)
    if airline:
        aliases = AIRLINE_ALIASES.get(compact_token(airline), [compact_token(airline)])
        for alias in aliases:
            a = compact_token(alias)
            if f"{a}_S" in tokens or f"{a}S" in tokens:
                return True
    return any(tok.endswith("_S") or tok.endswith("S") and len(tok) <= 6 for tok in tokens) or "S" in tokens


def person_is_la(qual_string: object, airline: Optional[str] = None) -> bool:
    tokens = qualification_tokens(qual_string)
    if airline:
        aliases = AIRLINE_ALIASES.get(compact_token(airline), [compact_token(airline)])
        for alias in aliases:
            a = compact_token(alias)
            if f"{a}_L" in tokens or f"{a}L" in tokens:
                return True
    return any(tok.endswith("_L") or tok.endswith("L") and len(tok) <= 6 for tok in tokens)


def overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime, buffer_minutes: int = 15) -> bool:
    return a_start < b_end + timedelta(minutes=buffer_minutes) and b_start < a_end + timedelta(minutes=buffer_minutes)


def build_shift_plan(
    departures: pd.DataFrame,
    staff: pd.DataFrame,
    requests: Optional[pd.DataFrame] = None,
    report_minutes: int = 150,
    debrief_minutes: int = 45,
    min_rest_hours: int = 11,
    service_min_people: int = 4,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Greedy planning prototype.

    Returns: assignment rows, flight summary rows, warnings.
    The algorithm is deterministic and explainable: it sorts flights chronologically,
    picks required supervisor/LA first, then fills remaining slots by lowest workload.
    """
    if departures is None or departures.empty or staff is None or staff.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    flights = enrich_departures_with_requirements(departures).sort_values("std_dt").reset_index(drop=True)
    staff = staff.copy().reset_index(drop=True)
    if "is_active" in staff.columns:
        staff = staff[staff["is_active"].astype(bool)]
    else:
        staff["is_active"] = True
    staff["route"] = staff.get("route", "").fillna("").map(compact_token)
    staff["name_key"] = staff["name"].map(normalize_text)
    # Orijinal personel sırası korunur; seçimlerde alfabetik sıralama yerine iş yükü + dosya sırası kullanılır.
    staff["_staff_order"] = range(len(staff))
    staff["max_weekly_hours"] = pd.to_numeric(staff.get("max_weekly_hours", 50), errors="coerce").fillna(50)

    unavailable = set()
    if requests is not None and not requests.empty:
        req = requests.copy()
        if "name" in req.columns and "date" in req.columns:
            req["name_key"] = req["name"].map(normalize_text)
            req["date"] = pd.to_datetime(req["date"], errors="coerce").dt.date
            status_col = "status" if "status" in req.columns else None
            for _, r in req.iterrows():
                status = normalize_text(r.get(status_col, "DO")) if status_col else "DO"
                if status in {"DO", "IZIN", "TATIL", "OFF", "ANNUAL LEAVE", "RAPOR"}:
                    unavailable.add((r["name_key"], r["date"]))

    assignments: List[Dict[str, object]] = []
    warnings: List[Dict[str, object]] = []
    workload_minutes: Dict[str, int] = {row["name_key"]: 0 for _, row in staff.iterrows()}
    daily_task_count: Dict[Tuple[str, object], int] = {}

    def candidate_score(person_row: pd.Series, flight_start: datetime) -> Tuple[int, int, int]:
        key = person_row["name_key"]
        day = flight_start.date()
        return (
            workload_minutes.get(key, 0),
            daily_task_count.get((key, day), 0),
            int(person_row.get("_staff_order", 0)),
        )

    for _, f in flights.iterrows():
        std_dt: datetime = f["std_dt"].to_pydatetime() if hasattr(f["std_dt"], "to_pydatetime") else f["std_dt"]
        start = std_dt - timedelta(minutes=report_minutes)
        end = std_dt + timedelta(minutes=debrief_minutes)
        duration = int((end - start).total_seconds() // 60) - 60  # meal break deduction
        duration = max(duration, 60)
        airline = compact_token(f["airline"])
        required = int(f["required_staff"])
        selected_keys: List[str] = []
        selected_roles: Dict[str, str] = {}

        base_candidates = []
        for _, p in staff.iterrows():
            key = p["name_key"]
            if (key, start.date()) in unavailable:
                continue
            if not person_can_work(p["qualifications"], airline):
                continue
            max_weekly = float(p.get("max_weekly_hours", 50)) * 60
            if workload_minutes.get(key, 0) + duration > max_weekly:
                continue
            conflict = False
            for a in assignments:
                if a["name_key"] == key and overlap(start, end, a["work_start_dt"], a["work_end_dt"]):
                    conflict = True
                    break
            if conflict:
                continue
            base_candidates.append(p)

        if bool(f.get("requires_supervisor", False)):
            supervisors = [p for p in base_candidates if person_is_supervisor(p["qualifications"], airline)]
            if supervisors:
                chosen = sorted(supervisors, key=lambda p: candidate_score(p, start))[0]
                selected_keys.append(chosen["name_key"])
                selected_roles[chosen["name_key"]] = "Supervisor"
            else:
                warnings.append({
                    "flight": f.get("out_flight", ""),
                    "airline": airline,
                    "warning": "Havuz uçuşu için uygun Supervisor bulunamadı.",
                    "severity": "High",
                })

        if bool(f.get("la_required", False)) and len(selected_keys) < required:
            la_candidates = [p for p in base_candidates if p["name_key"] not in selected_keys and person_is_la(p["qualifications"], airline)]
            if la_candidates:
                chosen = sorted(la_candidates, key=lambda p: candidate_score(p, start))[0]
                selected_keys.append(chosen["name_key"])
                selected_roles[chosen["name_key"]] = "LA"
            else:
                warnings.append({
                    "flight": f.get("out_flight", ""),
                    "airline": airline,
                    "warning": "LA gerektiren uçuş için LA yetkinlikli personel bulunamadı; kontuar personeliyle doldurulacak.",
                    "severity": "Medium",
                })

        remaining_candidates = [p for p in base_candidates if p["name_key"] not in selected_keys]
        for p in sorted(remaining_candidates, key=lambda p: candidate_score(p, start)):
            if len(selected_keys) >= required:
                break
            selected_keys.append(p["name_key"])
            selected_roles[p["name_key"]] = "Kontuar/Gate"

        if len(selected_keys) < required:
            warnings.append({
                "flight": f.get("out_flight", ""),
                "airline": airline,
                "warning": f"Eksik atama: gerekli {required}, atanabilen {len(selected_keys)}.",
                "severity": "High",
            })

        for slot_no, key in enumerate(selected_keys, start=1):
            p = staff[staff["name_key"] == key].iloc[0]
            workload_minutes[key] = workload_minutes.get(key, 0) + duration
            daily_task_count[(key, start.date())] = daily_task_count.get((key, start.date()), 0) + 1
            assignments.append({
                "date": start.date(),
                "airline": airline,
                "in_flight": f.get("in_flight", ""),
                "out_flight": f.get("out_flight", ""),
                "aircraft_type": f.get("aircraft_type", ""),
                "pax_count": f.get("pax_count", 0),
                "rule_applied": f.get("rule_applied", ""),
                "required_staff": required,
                "slot_no": slot_no,
                "name": p["name"],
                "name_key": key,
                "role": selected_roles.get(key, "Kontuar/Gate"),
                "route": p.get("route", ""),
                "work_start_dt": start,
                "work_end_dt": end,
                "duty_start_dt": start,
                "duty_end_dt": end,
                "work_start": start.strftime("%d.%m.%Y %H:%M"),
                "work_end": end.strftime("%d.%m.%Y %H:%M"),
                "duty_start": start.strftime("%d.%m.%Y %H:%M"),
                "duty_end": end.strftime("%d.%m.%Y %H:%M"),
                "net_work_minutes": duration,
                "std": std_dt.strftime("%d.%m.%Y %H:%M"),
            })

    assignment_df = pd.DataFrame(assignments)
    warnings_df = pd.DataFrame(warnings)
    flight_summary = build_flight_summary(flights, assignment_df)
    return assignment_df, flight_summary, warnings_df


def build_flight_summary(flights: pd.DataFrame, assignments: pd.DataFrame) -> pd.DataFrame:
    if flights.empty:
        return pd.DataFrame()
    rows = []
    for _, f in flights.iterrows():
        out_flight = f.get("out_flight", "")
        std = f.get("std_dt")
        assigned = assignments[assignments["out_flight"] == out_flight] if not assignments.empty else pd.DataFrame()
        rows.append({
            "date": std.date() if hasattr(std, "date") else "",
            "airline": f.get("airline", ""),
            "out_flight": out_flight,
            "std": std.strftime("%d.%m.%Y %H:%M") if hasattr(std, "strftime") else str(std),
            "aircraft_type": f.get("aircraft_type", ""),
            "pax_count": f.get("pax_count", 0),
            "counter_count": f.get("counter_count", 0),
            "la_required": f.get("la_required", False),
            "required_staff": f.get("required_staff", 0),
            "assigned_staff": len(assigned),
            "status": "Tamam" if len(assigned) >= int(f.get("required_staff", 0)) else "Eksik",
            "rule_applied": f.get("rule_applied", ""),
        })
    return pd.DataFrame(rows)


def parse_time_list(values: Iterable[object], fallback: List[str]) -> List[str]:
    times = []
    for v in values:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        m = re.search(r"\d{1,2}:\d{2}", str(v))
        if m:
            hh, mm = m.group(0).split(":")
            times.append(f"{int(hh):02d}:{int(mm):02d}")
    return sorted(set(times)) if times else fallback


def service_datetime(base_date, t: str, *, direction: str, target_dt: datetime) -> datetime:
    hh, mm = map(int, t.split(":"))
    dt = datetime.combine(base_date, time(hh, mm))
    if direction == "arrival":
        if dt > target_dt:
            dt -= timedelta(days=1)
    else:
        if dt < target_dt:
            dt += timedelta(days=1)
    return dt


def _service_options_for_target(
    target_dt: datetime,
    service_times: List[str],
    *,
    direction: str,
    latest_allowed: Optional[datetime] = None,
    earliest_allowed: Optional[datetime] = None,
    max_wait_hours: int = 6,
) -> List[Tuple[str, datetime]]:
    """Return valid service options around a duty target.

    Arrival services must be before the duty/report target. Departure services
    must be after the duty end target. A generous wait window is used so the
    planner can align shifts to existing services instead of marking people as
    public transport too quickly.
    """
    options = []
    base_dates = [target_dt.date(), (target_dt - timedelta(days=1)).date(), (target_dt + timedelta(days=1)).date()]
    for base_date in base_dates:
        for t in service_times:
            hh, mm = map(int, t.split(":"))
            dt = datetime.combine(base_date, time(hh, mm))
            if direction == "arrival":
                upper = latest_allowed or target_dt
                lower = earliest_allowed or (target_dt - timedelta(hours=max_wait_hours))
                if lower <= dt <= upper:
                    options.append((t, dt))
            else:
                lower = earliest_allowed or target_dt
                upper = latest_allowed or (target_dt + timedelta(hours=max_wait_hours))
                if lower <= dt <= upper:
                    options.append((t, dt))
    # remove duplicates and sort chronologically
    dedup = {(t, dt): (t, dt) for t, dt in options}
    return sorted(dedup.values(), key=lambda x: x[1])


def choose_service(work_start: datetime, work_end: datetime, route: str, arrival_times: List[str], departure_times: List[str]) -> Tuple[str, datetime, str, datetime]:
    # Kept for compatibility: choose the nearest service around a duty window.
    arrival_target = work_start - timedelta(minutes=30)
    arr_options = _service_options_for_target(arrival_target, arrival_times, direction="arrival", latest_allowed=arrival_target)
    arr_time, arr_dt = max(arr_options, key=lambda x: x[1]) if arr_options else ("Toplu Taşıma", work_start)

    dep_target = work_end + timedelta(minutes=15)
    dep_options = _service_options_for_target(dep_target, departure_times, direction="departure", earliest_allowed=dep_target)
    dep_time, dep_dt = min(dep_options, key=lambda x: x[1]) if dep_options else ("Toplu Taşıma", work_end)
    return arr_time, arr_dt, dep_time, dep_dt


def _pick_service_by_route_density(
    row_index: int,
    option_map: Dict[int, List[Tuple[str, datetime]]],
    density: Dict[Tuple[str, datetime], int],
    route: str,
    target_dt: datetime,
    *,
    direction: str,
    min_people: int,
) -> Tuple[str, datetime]:
    options = option_map.get(row_index, [])
    if not options:
        return "Toplu Taşıma", target_dt

    def score(item: Tuple[str, datetime]) -> Tuple[int, int, int]:
        _time, service_dt = item
        people = density.get((route, service_dt), 0)
        wait_minutes = abs(int((target_dt - service_dt).total_seconds() // 60))
        # Önce 4+ kişilik servisleri, sonra aynı servise toplanan kişi sayısını, sonra bekleme süresini optimize et.
        return (1 if people >= min_people else 0, people, -wait_minutes)

    return max(options, key=score)


def add_service_plan(
    assignments: pd.DataFrame,
    service_df: Optional[pd.DataFrame] = None,
    min_people: int = 4,
    align_shift_to_service: bool = True,
    max_wait_hours: int = 6,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Attach service plan and service-aligned shift times.

    Older version marked many people as ``Toplu Taşıma`` when the exact duty
    start/end did not create a 4-person service group. This version first looks
    at all valid services on the same route and aligns the displayed shift start
    and end to those service times. Public transport is only used when route or
    service data is missing.
    """
    if assignments is None or assignments.empty:
        return pd.DataFrame(), pd.DataFrame()
    service_df = clean_columns(service_df) if service_df is not None and not service_df.empty else pd.DataFrame()
    arrival_times = DEFAULT_ARRIVAL_TIMES
    departure_times = DEFAULT_DEPARTURE_TIMES
    if not service_df.empty:
        if "Geliş" in service_df.columns:
            arrival_times = parse_time_list(service_df["Geliş"].dropna(), DEFAULT_ARRIVAL_TIMES)
        elif "Gelis" in service_df.columns:
            arrival_times = parse_time_list(service_df["Gelis"].dropna(), DEFAULT_ARRIVAL_TIMES)
        if "Gidiş" in service_df.columns:
            departure_times = parse_time_list(service_df["Gidiş"].dropna(), DEFAULT_DEPARTURE_TIMES)
        elif "Gidis" in service_df.columns:
            departure_times = parse_time_list(service_df["Gidis"].dropna(), DEFAULT_DEPARTURE_TIMES)

    df = assignments.copy().reset_index(drop=True)
    df["route"] = df.get("route", "").fillna("").map(compact_token)
    if "duty_start_dt" not in df.columns:
        df["duty_start_dt"] = df["work_start_dt"]
    if "duty_end_dt" not in df.columns:
        df["duty_end_dt"] = df["work_end_dt"]
    df["duty_start"] = df["duty_start_dt"].apply(lambda x: pd.to_datetime(x).strftime("%d.%m.%Y %H:%M"))
    df["duty_end"] = df["duty_end_dt"].apply(lambda x: pd.to_datetime(x).strftime("%d.%m.%Y %H:%M"))

    arrival_option_map: Dict[int, List[Tuple[str, datetime]]] = {}
    departure_option_map: Dict[int, List[Tuple[str, datetime]]] = {}
    arrival_density: Dict[Tuple[str, datetime], int] = {}
    departure_density: Dict[Tuple[str, datetime], int] = {}

    for idx, r in df.iterrows():
        route = compact_token(r.get("route", ""))
        start = r["duty_start_dt"] if isinstance(r["duty_start_dt"], datetime) else pd.to_datetime(r["duty_start_dt"]).to_pydatetime()
        end = r["duty_end_dt"] if isinstance(r["duty_end_dt"], datetime) else pd.to_datetime(r["duty_end_dt"]).to_pydatetime()
        if not route:
            arrival_option_map[idx] = []
            departure_option_map[idx] = []
            continue
        arrival_target = start - timedelta(minutes=30)
        departure_target = end + timedelta(minutes=15)
        arr_opts = _service_options_for_target(
            arrival_target,
            arrival_times,
            direction="arrival",
            latest_allowed=arrival_target,
            earliest_allowed=arrival_target - timedelta(hours=max_wait_hours),
            max_wait_hours=max_wait_hours,
        )
        dep_opts = _service_options_for_target(
            departure_target,
            departure_times,
            direction="departure",
            earliest_allowed=departure_target,
            latest_allowed=departure_target + timedelta(hours=max_wait_hours),
            max_wait_hours=max_wait_hours,
        )
        # Eğer geniş pencere içinde yoksa en yakın önceki/sonraki servisi kullan.
        if not arr_opts:
            arr_opts = _service_options_for_target(arrival_target, arrival_times, direction="arrival", latest_allowed=arrival_target, max_wait_hours=12)
        if not dep_opts:
            dep_opts = _service_options_for_target(departure_target, departure_times, direction="departure", earliest_allowed=departure_target, max_wait_hours=12)
        arrival_option_map[idx] = arr_opts
        departure_option_map[idx] = dep_opts
        for _t, dt in arr_opts:
            arrival_density[(route, dt)] = arrival_density.get((route, dt), 0) + 1
        for _t, dt in dep_opts:
            departure_density[(route, dt)] = departure_density.get((route, dt), 0) + 1

    rows = []
    for idx, r in df.iterrows():
        route = compact_token(r.get("route", ""))
        start = r["duty_start_dt"] if isinstance(r["duty_start_dt"], datetime) else pd.to_datetime(r["duty_start_dt"]).to_pydatetime()
        end = r["duty_end_dt"] if isinstance(r["duty_end_dt"], datetime) else pd.to_datetime(r["duty_end_dt"]).to_pydatetime()
        arrival_target = start - timedelta(minutes=30)
        departure_target = end + timedelta(minutes=15)
        if not route:
            arr_t, arr_dt = "Toplu Taşıma", start
            dep_t, dep_dt = "Toplu Taşıma", end
        else:
            arr_t, arr_dt = _pick_service_by_route_density(
                idx, arrival_option_map, arrival_density, route, arrival_target, direction="arrival", min_people=min_people
            )
            dep_t, dep_dt = _pick_service_by_route_density(
                idx, departure_option_map, departure_density, route, departure_target, direction="departure", min_people=min_people
            )
        rows.append({
            "arrival_service_time": arr_t,
            "arrival_service_dt": arr_dt,
            "departure_service_time": dep_t,
            "departure_service_dt": dep_dt,
        })

    service_cols = pd.DataFrame(rows)
    df = pd.concat([df.reset_index(drop=True), service_cols], axis=1)

    arr_counts = df.groupby(["route", "arrival_service_dt"], dropna=False).size().rename("arrival_service_count").reset_index()
    dep_counts = df.groupby(["route", "departure_service_dt"], dropna=False).size().rename("departure_service_count").reset_index()
    df = df.merge(arr_counts, on=["route", "arrival_service_dt"], how="left")
    df = df.merge(dep_counts, on=["route", "departure_service_dt"], how="left")

    if align_shift_to_service:
        df["shift_start_dt"] = df["arrival_service_dt"]
        df["shift_end_dt"] = df["departure_service_dt"]
    else:
        df["shift_start_dt"] = df["duty_start_dt"]
        df["shift_end_dt"] = df["duty_end_dt"]
    df["shift_start"] = df["shift_start_dt"].apply(lambda x: pd.to_datetime(x).strftime("%d.%m.%Y %H:%M"))
    df["shift_end"] = df["shift_end_dt"].apply(lambda x: pd.to_datetime(x).strftime("%d.%m.%Y %H:%M"))
    df["shift_hours_gross"] = (pd.to_datetime(df["shift_end_dt"]) - pd.to_datetime(df["shift_start_dt"])).dt.total_seconds().div(3600).round(2)

    def note(kind: str, r: pd.Series) -> str:
        time_col = f"{kind}_service_time"
        count_col = f"{kind}_service_count"
        if not compact_token(r.get("route", "")) or r.get(time_col) == "Toplu Taşıma":
            return "Toplu Taşıma - güzergah/servis verisi yok"
        count = int(r.get(count_col, 0) or 0)
        if count >= min_people:
            return "Servis OK"
        return "Servis önerisi - 4 kişi altı; vardiya servis saatine hizalandı"

    df["arrival_note"] = df.apply(lambda r: note("arrival", r), axis=1)
    df["departure_note"] = df.apply(lambda r: note("departure", r), axis=1)

    service_rows = []
    for (route, arr_dt), group in df.groupby(["route", "arrival_service_dt"], dropna=False):
        if pd.isna(arr_dt):
            continue
        status = "Kalkar" if len(group) >= min_people and str(group.iloc[0].get("arrival_service_time")) != "Toplu Taşıma" else "4 kişi altı / yönetici onayı"
        if not compact_token(route):
            status = "Toplu Taşıma"
        service_rows.append({
            "type": "Geliş",
            "date": arr_dt.date(),
            "route": route,
            "service_time": arr_dt.strftime("%d.%m.%Y %H:%M"),
            "people_count": len(group),
            "status": status,
            "people": ", ".join(group["name"].astype(str).tolist()[:12]),
        })
    for (route, dep_dt), group in df.groupby(["route", "departure_service_dt"], dropna=False):
        if pd.isna(dep_dt):
            continue
        status = "Kalkar" if len(group) >= min_people and str(group.iloc[0].get("departure_service_time")) != "Toplu Taşıma" else "4 kişi altı / yönetici onayı"
        if not compact_token(route):
            status = "Toplu Taşıma"
        service_rows.append({
            "type": "Gidiş",
            "date": dep_dt.date(),
            "route": route,
            "service_time": dep_dt.strftime("%d.%m.%Y %H:%M"),
            "people_count": len(group),
            "status": status,
            "people": ", ".join(group["name"].astype(str).tolist()[:12]),
        })
    service_summary = pd.DataFrame(service_rows)
    if not service_summary.empty:
        service_summary = service_summary.sort_values(["date", "service_time", "route", "type"]).reset_index(drop=True)
    return df, service_summary


def build_daily_staff_schedule(assignments: pd.DataFrame) -> pd.DataFrame:
    """One row per person/day showing service-aligned arrival and exit."""
    if assignments is None or assignments.empty:
        return pd.DataFrame()
    df = assignments.copy()
    for col in ["shift_start_dt", "shift_end_dt", "duty_start_dt", "duty_end_dt"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    if "shift_start_dt" not in df.columns:
        df["shift_start_dt"] = pd.to_datetime(df["work_start_dt"])
    if "shift_end_dt" not in df.columns:
        df["shift_end_dt"] = pd.to_datetime(df["work_end_dt"])
    if "duty_start_dt" not in df.columns:
        df["duty_start_dt"] = pd.to_datetime(df["work_start_dt"])
    if "duty_end_dt" not in df.columns:
        df["duty_end_dt"] = pd.to_datetime(df["work_end_dt"])

    rows = []
    sort_cols = ["date", "shift_start_dt", "route", "out_flight"]
    df = df.sort_values([c for c in sort_cols if c in df.columns])
    for (day, name), group in df.groupby(["date", "name"], sort=False):
        g = group.sort_values("shift_start_dt")
        first = g.iloc[0]
        last = g.sort_values("shift_end_dt").iloc[-1]
        rows.append({
            "date": day,
            "name": name,
            "route": first.get("route", ""),
            "arrival_service_time": first.get("arrival_service_time", ""),
            "shift_start": pd.to_datetime(g["shift_start_dt"].min()).strftime("%d.%m.%Y %H:%M"),
            "first_duty_start": pd.to_datetime(g["duty_start_dt"].min()).strftime("%d.%m.%Y %H:%M"),
            "last_duty_end": pd.to_datetime(g["duty_end_dt"].max()).strftime("%d.%m.%Y %H:%M"),
            "shift_end": pd.to_datetime(g["shift_end_dt"].max()).strftime("%d.%m.%Y %H:%M"),
            "departure_service_time": last.get("departure_service_time", ""),
            "arrival_note": first.get("arrival_note", ""),
            "departure_note": last.get("departure_note", ""),
            "total_net_hours": round(float(g.get("net_work_minutes", pd.Series([0])).sum()) / 60, 2),
            "tasks": " | ".join((g["airline"].astype(str) + " " + g["out_flight"].astype(str) + " (" + g["role"].astype(str) + ")").tolist()),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["date", "shift_start", "route"]).reset_index(drop=True)
    return out

def recommend_delay_actions(assignments: pd.DataFrame, delayed_flight: str, delay_minutes: int = 60) -> pd.DataFrame:
    if assignments is None or assignments.empty:
        return pd.DataFrame()
    delayed_flight_norm = compact_token(delayed_flight)
    same = assignments[assignments["out_flight"].map(compact_token) == delayed_flight_norm].copy()
    if same.empty:
        return pd.DataFrame()
    flight = same.iloc[0]
    new_end = flight["work_end_dt"] + timedelta(minutes=delay_minutes)
    airline = flight["airline"]
    date = flight["date"]

    # People already working the delayed flight are default continuation candidates.
    recs = []
    for _, p in same.iterrows():
        recs.append({
            "recommendation_type": "Devir almadan devam",
            "name": p["name"],
            "route": p.get("route", ""),
            "reason": f"Zaten {delayed_flight} üzerinde atanmış; delay sonrası bitiş {new_end.strftime('%H:%M')}.",
            "priority": 1,
        })

    # Other on-duty people around the new time can take over.
    window = assignments[(assignments["date"] == date) & (assignments["out_flight"].map(compact_token) != delayed_flight_norm)].copy()
    if not window.empty:
        window["distance_minutes"] = window.apply(lambda r: abs((r["work_end_dt"] - flight["work_end_dt"]).total_seconds()) / 60, axis=1)
        for _, p in window.sort_values(["distance_minutes", "route"]).head(10).iterrows():
            recs.append({
                "recommendation_type": "Devir / destek adayı",
                "name": p["name"],
                "route": p.get("route", ""),
                "reason": f"Aynı gün vardiyada; mevcut görevi {p['out_flight']} {p['work_end_dt'].strftime('%H:%M')} civarı bitiyor.",
                "priority": 2,
            })
    return pd.DataFrame(recs).sort_values(["priority", "name"]).reset_index(drop=True)


def to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for name, df in sheets.items():
            safe_name = re.sub(r"[^A-Za-z0-9 _-]", "", name)[:31] or "Sheet"
            export_df = df.copy()
            for c in export_df.columns:
                if pd.api.types.is_datetime64_any_dtype(export_df[c]):
                    export_df[c] = export_df[c].dt.strftime("%d.%m.%Y %H:%M")
            export_df.to_excel(writer, index=False, sheet_name=safe_name)
            worksheet = writer.sheets[safe_name]
            for idx, col in enumerate(export_df.columns):
                max_len = max([len(str(col))] + [len(str(x)) for x in export_df[col].head(200).tolist()])
                worksheet.set_column(idx, idx, min(max(max_len + 2, 12), 45))
    return output.getvalue()
