# -*- coding: utf-8 -*-
"""
Çelebi YHM - Servise Uyumlu Haftalık Vardiya ve Uçuş Planlama Sistemi
Streamlit uygulaması

Bu uygulama haftalık DEPARTURE, QUALIFICATIONLAR-YHM, 20. HAFTA YHM ve Hakediş dosyalarını okuyarak:
- servis saatlerine uyumlu vardiya kontrolü,
- haftalık saat limiti kontrolü,
- 11 saat dinlenme kuralı kontrolü,
- uçuş hakediş/personel ihtiyacı hesaplama,
- Supervisor / LA / Agent rolüne göre uçuş ekibi önerme,
- uçak gecikmelerinde devir alma / personel değişikliği önerisi,
- manuel hakediş ve görev düzenleme,
- Excel rapor çıktısı
sağlar.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from io import BytesIO
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import streamlit as st

# =============================================================================
# SABİT KURALLAR
# =============================================================================

APP_TITLE = "Çelebi YHM Servise Uyumlu Vardiya Planlama"
APP_VERSION = "v1.1"

ARRIVAL_SERVICES = ["02:30", "04:30", "06:30", "08:00", "10:00", "11:30", "14:00", "16:30", "20:00", "23:59"]
DEPARTURE_SERVICES = ["00:30", "02:30", "04:30", "08:30", "14:30", "17:00", "19:30", "20:30", "23:00"]
ROUTES = ["ARN", "ATS", "AVC", "BAG", "BAH", "BHC", "BAY", "BEY", "BOL", "ESY", "HAL", "MAG", "SEF", "SUL", "AKZ"]

# A/L kodu ile qualification dosyasındaki muhtemel isim/kod eşleşmeleri.
# Bu tablo uygulama içinden değiştirilebilir.
DEFAULT_AIRLINE_ALIASES: Dict[str, List[str]] = {
    "AEE": ["AEE", "AEGEAN"],
    "AHY": ["AHY"],
    "AWG": ["AWG", "A2", "ANIMAWINGS"],
    "CSC": ["CSC", "3U", "SICHUAN"],
    "CES": ["CES", "MU", "CHINA EASTERN"],
    "CSN": ["CSN", "CZ", "CHINA SOUTHERN"],
    "CCA": ["CCA", "CA", "AIR CHINA", "AIRCHINA"],
    "DLH": ["DLH", "LH", "LUFTHANSA"],
    "ETD": ["ETD", "EY", "ETIHAD"],
    "IAW": ["IAW", "IRAQ", "IRAK"],
    "KAC": ["KAC", "KUWAIT", "KUVEYT"],
    "SVA": ["SVA", "SAUDI", "SAUDIA"],
    "UZB": ["UZB", "UZBEKISTAN"],
    "VSV": ["VSV", "SCAT"],
    "TRF": ["TRF"],
    "FAD": ["FAD"],
    "ABY": ["ABY", "AIR ARABIA", "ARABIA"],
    "AAR": ["AAR", "ARABIA"],
}

AIRLINE_RULE_NAME_TO_CODES: Dict[str, List[str]] = {
    "UZBEKISTAN": ["UZB"],
    "AEGEAN": ["AEE"],
    "ARABIA": ["ABY", "AAR", "AWG"],
    "IRAK": ["IAW"],
    "IRAQ": ["IAW"],
    "KUVEYT": ["KAC"],
    "KUWAIT": ["KAC"],
    "CHINA EASTERN": ["CES"],
    "CHINA SOUTHERN": ["CSN"],
    "AIRCHINA": ["CCA"],
    "AIR CHINA": ["CCA"],
    "SICHUAN": ["CSC"],
    "ANIMAWINGS": ["AWG"],
    "LUFTHANSA": ["DLH"],
    "SCAT": ["VSV"],
}

ROLE_OPTIONS = ["Agent", "LA", "Supervisor"]
STATUS_WORK = "Çalışıyor"
STATUS_DO = "DO"
STATUS_LEAVE = "İzin/VA"
STATUS_EMPTY = "Boş/Okunamadı"


# =============================================================================
# GENEL YARDIMCI FONKSİYONLAR
# =============================================================================


def normalize_text(value: object) -> str:
    """Türkçe karakter ve boşluk farklılıklarını azaltarak karşılaştırma metni üretir."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    s = str(value).replace("\xa0", " ").strip()
    tr_map = str.maketrans({
        "ı": "i", "İ": "I", "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U",
        "ş": "s", "Ş": "S", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
    })
    s = s.translate(tr_map)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s.upper().strip()


def clean_name(*parts: object) -> str:
    raw = " ".join(str(p) for p in parts if p is not None and not pd.isna(p))
    raw = raw.replace("\xa0", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None or pd.isna(value):
            return default
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def parse_any_date(value: object) -> Optional[pd.Timestamp]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        ts = pd.to_datetime(value, dayfirst=True, errors="coerce")
        if pd.isna(ts):
            return None
        return pd.Timestamp(ts)
    except Exception:
        return None




def parse_header_date(value: object) -> Optional[pd.Timestamp]:
    """Vardiya tablosundaki gerçek tarih başlıklarını yakalar; 1, 2, 19 gibi sayısal rapor kolonlarını tarih sanmaz."""
    if isinstance(value, pd.Timestamp):
        return value.normalize() if value.year >= 2000 else None
    if isinstance(value, datetime):
        return pd.Timestamp(value).normalize() if value.year >= 2000 else None
    if isinstance(value, date):
        return pd.Timestamp(value).normalize() if value.year >= 2000 else None
    if isinstance(value, (int, float, np.integer, np.floating)):
        return None
    text = str(value).strip()
    if not re.search(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", text):
        return None
    ts = parse_any_date(text)
    if ts is None or ts.year < 2000:
        return None
    return ts.normalize()

def format_hhmm(t: time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def parse_time_token(token: str) -> Optional[time]:
    token = str(token).strip().replace(".", ":")
    token = re.sub(r"[^0-9:]", "", token)
    if not token:
        return None
    if ":" in token:
        h, m = token.split(":", 1)
        if not h:
            return None
        hour, minute = int(h), int(m[:2] or 0)
    else:
        token = token.zfill(4)
        hour, minute = int(token[:-2]), int(token[-2:])
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour, minute)
    return None


def parse_shift_interval(shift_text: object, day_value: object) -> Tuple[Optional[datetime], Optional[datetime]]:
    """0800-1700, 14:00-00:30 gibi vardiya metinlerini başlangıç/bitiş datetime'a çevirir."""
    txt = normalize_text(shift_text)
    if not txt or txt in {"DO", "OFF", "VA", "IZIN", "R", "REST"}:
        return None, None
    # İlk gördüğümüz saat-saat aralığını yakala.
    m = re.search(r"(\d{1,2}[:.]?\d{2}|\d{3,4})\s*[-–—]\s*(\d{1,2}[:.]?\d{2}|\d{3,4})", str(shift_text))
    if not m:
        return None, None
    start_t = parse_time_token(m.group(1))
    end_t = parse_time_token(m.group(2))
    day_ts = parse_any_date(day_value)
    if start_t is None or end_t is None or day_ts is None:
        return None, None
    start_dt = datetime.combine(day_ts.date(), start_t)
    end_dt = datetime.combine(day_ts.date(), end_t)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def hours_between(start_dt: Optional[datetime], end_dt: Optional[datetime], break_threshold: float = 6.0, break_hours: float = 1.0) -> float:
    if not start_dt or not end_dt:
        return 0.0
    raw = max(0.0, (end_dt - start_dt).total_seconds() / 3600)
    if raw >= break_threshold:
        return max(0.0, raw - break_hours)
    return raw


def shift_status(shift_text: object) -> str:
    txt = normalize_text(shift_text)
    if not txt:
        return STATUS_EMPTY
    if txt in {"DO", "OFF", "REST"} or " DO" in f" {txt} ":
        return STATUS_DO
    if txt in {"VA", "IZIN", "ANNUAL LEAVE"} or "VA" == txt or "IZIN" in txt:
        return STATUS_LEAVE
    if re.search(r"\d{3,4}\s*[-–—]\s*\d{3,4}|\d{1,2}:\d{2}\s*[-–—]\s*\d{1,2}:\d{2}", str(shift_text)):
        return STATUS_WORK
    return STATUS_EMPTY


def is_service_aligned(start_dt: Optional[datetime], end_dt: Optional[datetime]) -> bool:
    if not start_dt or not end_dt:
        return False
    return format_hhmm(start_dt.time()) in ARRIVAL_SERVICES and format_hhmm(end_dt.time()) in DEPARTURE_SERVICES


def extract_pax_count(value: object) -> int:
    """10+197 (22+222) gibi alanlardan ilk parantez öncesi toplam yolcu sayısını yaklaşık çıkarır."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return 0
    s = str(value)
    s = s.split("(")[0]
    nums = [int(x) for x in re.findall(r"\d+", s)]
    if not nums:
        return 0
    return int(sum(nums))


def extract_first_number(value: object, default: int = 0) -> int:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else default


def overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def normalize_code_list(raw: object) -> List[str]:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    parts = re.split(r"[,;/|]+", str(raw))
    out = []
    for p in parts:
        p = normalize_text(p)
        if p:
            out.append(p)
    return out



def rewind_file(file_obj):
    """Streamlit UploadedFile aynı akışta birden fazla kez okunacaksa başa sarar."""
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
    except Exception:
        pass
    return file_obj


# =============================================================================
# DOSYA OKUMA
# =============================================================================


def read_csv_smart(file_obj) -> pd.DataFrame:
    """Türkçe CSV dosyalarını noktalı virgül ve farklı encodinglerle okumayı dener."""
    file_obj = rewind_file(file_obj)
    if file_obj is None:
        raise ValueError("CSV dosyası bulunamadı.")
    raw = file_obj.read() if hasattr(file_obj, "read") else open(file_obj, "rb").read()
    for enc in ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "latin1"]:
        for sep in [";", ",", "\t"]:
            try:
                df = pd.read_csv(BytesIO(raw), encoding=enc, sep=sep)
                if df.shape[1] > 1:
                    return df
            except Exception:
                continue
    # Son çare: pandas ayırsın.
    return pd.read_csv(BytesIO(raw), engine="python", sep=None)


def read_excel_sheet(file_obj, preferred_names: Sequence[str] | None = None, required_cols: Sequence[str] | None = None) -> pd.DataFrame:
    file_obj = rewind_file(file_obj)
    if file_obj is None:
        raise ValueError("Excel dosyası bulunamadı.")
    xls = pd.ExcelFile(file_obj)
    sheet_name = None
    preferred_names = preferred_names or []
    for pref in preferred_names:
        for sh in xls.sheet_names:
            if normalize_text(pref) == normalize_text(sh):
                sheet_name = sh
                break
        if sheet_name:
            break
    if not sheet_name and required_cols:
        for sh in xls.sheet_names:
            test = pd.read_excel(xls, sheet_name=sh, nrows=3)
            cols = {normalize_text(c) for c in test.columns}
            if all(normalize_text(c) in cols for c in required_cols):
                sheet_name = sh
                break
    if not sheet_name:
        sheet_name = xls.sheet_names[0]
    return pd.read_excel(xls, sheet_name=sheet_name)


def load_default_or_upload(uploaded, default_path: str):
    if uploaded is not None:
        return uploaded
    try:
        return default_path
    except Exception:
        return None


def standardize_departure(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Fazla tamamen boş sütunları temizle.
    df = df.dropna(axis=1, how="all")
    col_map = {}
    for col in df.columns:
        n = normalize_text(col)
        if n in {"A/L", "AL", "AIRLINE"}:
            col_map[col] = "airline"
        elif n == "IN":
            col_map[col] = "in_flight"
        elif n == "OUT":
            col_map[col] = "out_flight"
        elif n == "STA":
            col_map[col] = "sta"
        elif n == "STD":
            col_map[col] = "std"
        elif n == "FROM":
            col_map[col] = "from"
        elif n == "TO":
            col_map[col] = "to"
        elif "A/C" in n or "TYPE" in n or "AC" == n:
            col_map[col] = "ac_type"
        elif "EKIP" in n:
            col_map[col] = "existing_team"
        elif "NOT" in n:
            col_map[col] = "notes"
        elif "TRN" in n:
            col_map[col] = "trn"
        elif "UNNAMED" in n or n in {"", "NAN"}:
            # İlk isimsiz sütun genelde gün bilgisidir.
            if "day" not in col_map.values():
                col_map[col] = "day"
            else:
                # Yolcu bilgisi genelde 9. sütundaki isimsiz alan.
                col_map[col] = f"extra_{len(col_map)}"
        else:
            if "day" not in col_map.values() and df[col].astype(str).str.contains("PAZ|SALI|CARS|ÇAR|PER|CUMA|CUMART|PAZAR", case=False, na=False).any():
                col_map[col] = "day"
            else:
                col_map[col] = normalize_text(col).lower().replace(" ", "_")
    df = df.rename(columns=col_map)

    # Yolcu/raw kapasite alanını bul.
    pax_col = None
    for c in df.columns:
        if c in {"airline", "in_flight", "out_flight", "sta", "std", "from", "to", "ac_type", "existing_team", "notes", "trn", "day"}:
            continue
        series = df[c].dropna().astype(str)
        if not series.empty and series.str.contains(r"\d", regex=True).mean() > 0.5:
            pax_col = c
            break
    if pax_col is None:
        df["pax_raw"] = ""
    else:
        df["pax_raw"] = df[pax_col]

    for required in ["airline", "in_flight", "out_flight", "sta", "std"]:
        if required not in df.columns:
            df[required] = np.nan
    if "day" not in df.columns:
        df["day"] = ""
    if "from" not in df.columns:
        df["from"] = ""
    if "to" not in df.columns:
        df["to"] = ""
    if "ac_type" not in df.columns:
        df["ac_type"] = ""
    if "existing_team" not in df.columns:
        df["existing_team"] = ""
    if "notes" not in df.columns:
        df["notes"] = ""

    df["day"] = df["day"].ffill()
    df["airline"] = df["airline"].apply(lambda x: normalize_text(x).replace(" ", ""))
    df["std"] = pd.to_datetime(df["std"], dayfirst=True, errors="coerce")
    df["sta"] = pd.to_datetime(df["sta"], dayfirst=True, errors="coerce")
    df["pax_count"] = df["pax_raw"].apply(extract_pax_count)
    df["ac_type"] = df["ac_type"].astype(str).replace("nan", "")
    df["flight_id"] = (
        df["airline"].astype(str) + " | " +
        df["out_flight"].astype(str) + " | " +
        df["std"].dt.strftime("%d.%m %H:%M").fillna("")
    )
    df = df[df["airline"].notna() & (df["airline"] != "") & df["std"].notna()].copy()
    keep = ["flight_id", "day", "airline", "in_flight", "out_flight", "sta", "std", "from", "to", "ac_type", "pax_raw", "pax_count", "existing_team", "notes"]
    return df[keep].reset_index(drop=True)


def standardize_qualifications(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().dropna(axis=1, how="all")
    cols = {normalize_text(c): c for c in df.columns}
    ad_col = cols.get("AD") or cols.get("NAME")
    soyad_col = cols.get("SOYAD") or cols.get("SURNAME")
    q_col = cols.get("QUALIFICATIONS") or cols.get("QUALIFICATION")
    if ad_col is None or soyad_col is None or q_col is None:
        # Esnek fallback: ilk 3 sütun
        ad_col, soyad_col, q_col = df.columns[:3]
    out = pd.DataFrame({
        "first_name": df[ad_col],
        "last_name": df[soyad_col],
        "name": [clean_name(a, b) for a, b in zip(df[ad_col], df[soyad_col])],
        "name_key": [normalize_text(clean_name(a, b)) for a, b in zip(df[ad_col], df[soyad_col])],
        "flight_qualifications": df[q_col].fillna(""),
    })
    out = out[out["name_key"] != ""].drop_duplicates("name_key", keep="last")
    return out.reset_index(drop=True)


def detect_week_sheet(file_obj) -> str:
    file_obj = rewind_file(file_obj)
    xls = pd.ExcelFile(file_obj)
    candidates = []
    for sh in xls.sheet_names:
        ns = normalize_text(sh)
        if "DEPARTURE" in ns:
            continue
        try:
            test = pd.read_excel(xls, sheet_name=sh, nrows=2)
            cols = {normalize_text(c) for c in test.columns}
            if {"MAIL", "AD", "SOYAD", "GUZERGAH"}.issubset(cols):
                candidates.append(sh)
        except Exception:
            pass
    return candidates[0] if candidates else xls.sheet_names[0]


def standardize_staff_and_shifts(week_df: pd.DataFrame, break_threshold: float, break_hours: float) -> Tuple[pd.DataFrame, pd.DataFrame, List[pd.Timestamp]]:
    df = week_df.copy().dropna(how="all")
    df = df.dropna(axis=1, how="all")

    col_lookup = {normalize_text(c): c for c in df.columns}
    required_cols = ["MAIL", "FULL/PART", "CINSIYET", "AD", "SOYAD", "GUZERGAH", "QUALIFICATIONS"]
    for c in required_cols:
        if c not in col_lookup:
            # Eksik olabilir, yine de boş oluştur.
            df[c] = ""
            col_lookup[c] = c

    date_cols: List[Tuple[object, object, pd.Timestamp]] = []
    columns = list(df.columns)
    for idx, col in enumerate(columns):
        parsed = parse_header_date(col)
        if parsed is not None:
            hour_col = columns[idx + 1] if idx + 1 < len(columns) else None
            date_cols.append((col, hour_col, parsed.normalize()))

    def classify_type(x: object) -> str:
        raw = normalize_text(x)
        num = safe_float(x, default=np.nan)
        if "PART" in raw or "PT" == raw or (not np.isnan(num) and num <= 25):
            return "PART"
        return "FULL"

    def base_role(x: object) -> str:
        raw = normalize_text(x)
        if "LA" in raw or "LIDER" in raw:
            return "LA"
        if "SEF" in raw or "SUP" in raw or "SPV" in raw:
            return "Supervisor"
        return "Agent"

    staff = pd.DataFrame({
        "email": df[col_lookup["MAIL"]].fillna(""),
        "work_type_raw": df[col_lookup["FULL/PART"]],
        "work_type": df[col_lookup["FULL/PART"]].apply(classify_type),
        "gender": df[col_lookup["CINSIYET"]].fillna(""),
        "first_name": df[col_lookup["AD"]].fillna(""),
        "last_name": df[col_lookup["SOYAD"]].fillna(""),
        "route": df[col_lookup["GUZERGAH"]].fillna(""),
        "base_qualification": df[col_lookup["QUALIFICATIONS"]].fillna(""),
    })
    staff["name"] = [clean_name(a, b) for a, b in zip(staff["first_name"], staff["last_name"])]
    staff["name_key"] = staff["name"].apply(normalize_text)
    staff["base_role"] = staff["base_qualification"].apply(base_role)
    staff["role_override"] = staff["base_role"]
    staff["active"] = True
    staff["route"] = staff["route"].apply(lambda x: normalize_text(x).replace(" ", ""))
    staff["route_valid"] = staff["route"].isin(ROUTES)
    staff = staff[staff["name_key"] != ""].drop_duplicates("name_key", keep="first").reset_index(drop=True)
    staff["staff_id"] = staff.index.astype(str)

    # ID'leri ana tabloya geri eşlemek için key kullan.
    id_by_key = dict(zip(staff["name_key"], staff["staff_id"]))

    shifts = []
    for _, row in df.iterrows():
        name = clean_name(row.get(col_lookup["AD"], ""), row.get(col_lookup["SOYAD"], ""))
        key = normalize_text(name)
        if key not in id_by_key:
            continue
        for shift_col, hour_col, day_ts in date_cols:
            shift_txt = row.get(shift_col, "")
            raw_hours = row.get(hour_col, np.nan) if hour_col is not None else np.nan
            status = shift_status(shift_txt)
            start_dt, end_dt = parse_shift_interval(shift_txt, day_ts)
            planned = hours_between(start_dt, end_dt, break_threshold, break_hours) if status == STATUS_WORK else 0.0
            shifts.append({
                "staff_id": id_by_key[key],
                "name": name,
                "name_key": key,
                "date": day_ts.date(),
                "shift_text": "" if pd.isna(shift_txt) else str(shift_txt),
                "status": status,
                "start_dt": start_dt,
                "end_dt": end_dt,
                "start_service": format_hhmm(start_dt.time()) if start_dt else "",
                "end_service": format_hhmm(end_dt.time()) if end_dt else "",
                "service_ok": is_service_aligned(start_dt, end_dt) if status == STATUS_WORK else True,
                "raw_hours_from_file": safe_float(raw_hours, 0.0),
                "planned_work_hours": round(planned, 2),
            })
    shifts_df = pd.DataFrame(shifts)
    week_dates = [d for _, _, d in date_cols]
    return staff, shifts_df, week_dates


def standardize_hakedis(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().dropna(axis=1, how="all")
    if df.empty:
        return pd.DataFrame(columns=["airline_rule", "criterion", "detail", "staff_text"])
    # İlk 4 sütunu kullan.
    base = df.iloc[:, :4].copy()
    base.columns = ["airline_rule", "criterion", "detail", "staff_text"]
    base["airline_rule"] = base["airline_rule"].ffill()
    base["criterion"] = base["criterion"].ffill()
    base = base.dropna(how="all")
    base["airline_rule_norm"] = base["airline_rule"].apply(normalize_text)
    return base.reset_index(drop=True)


# =============================================================================
# HAKEDİŞ / İHTİYAÇ HESABI
# =============================================================================


def codes_for_rule_name(rule_name_norm: str) -> List[str]:
    codes: List[str] = []
    for key, vals in AIRLINE_RULE_NAME_TO_CODES.items():
        if key in rule_name_norm:
            codes.extend(vals)
    return list(dict.fromkeys(codes))


def parse_staff_text(staff_text: object, pax_count: int = 0) -> Tuple[int, int, str]:
    """Hakediş personel alanından (agent/toplam, LA) tahmini sayı döndürür."""
    s = normalize_text(staff_text)
    if not s:
        return 3, 0, "Varsayılan 3 staff"
    # Her 60/50 yolcu için 1 staff
    m = re.search(r"HER\s+(\d+)\s+YOLCU", s)
    if m:
        divisor = int(m.group(1))
        total = max(1, math.ceil(max(pax_count, 1) / divisor))
        return total, 0, f"Her {divisor} yolcu için 1 staff"

    # 8 Staff + 1 LA
    la = 0
    m_la = re.search(r"(\d+)\s*LA", s)
    if m_la:
        la = int(m_la.group(1))

    # 7+1 Staff veya 6+1 gibi ifadeler
    plus_match = re.search(r"(\d+)\s*\+\s*(\d+)", s)
    if plus_match:
        total = int(plus_match.group(1)) + int(plus_match.group(2))
        # +1 LA açık yazmadıysa bunu toplam staff sayısı sayıyoruz.
        return total, la, str(staff_text)

    nums = [int(x) for x in re.findall(r"\d+", s)]
    if nums:
        total = nums[0]
        return total, la, str(staff_text)
    return 3, 0, str(staff_text)


def detail_matches(detail: object, criterion: object, pax_count: int, ac_type: object, std: pd.Timestamp) -> bool:
    d = normalize_text(detail)
    c = normalize_text(criterion)
    ac = normalize_text(ac_type)
    if not d:
        return True

    # Uçak tipi: 777 Tipi, 320 Tipi vb.
    if "TIP" in c or "TIP" in d:
        nums = re.findall(r"\d+", d)
        if nums:
            return any(n in ac for n in nums)

    # Yolcu aralıkları: 0-150, 61-119, 200+
    range_match = re.search(r"(\d+)\s*[-–]\s*(\d+)", d)
    if range_match:
        lo, hi = int(range_match.group(1)), int(range_match.group(2))
        return lo <= pax_count <= hi
    plus_match = re.search(r"(\d+)\s*\+", d)
    if plus_match:
        return pax_count >= int(plus_match.group(1))
    alt_match = re.search(r"(\d+)\s*ALTI", d)
    if alt_match:
        return pax_count < int(alt_match.group(1))

    if "GECE" in d:
        hour = pd.Timestamp(std).hour
        return hour >= 20 or hour < 7
    if "GUNDUZ" in d:
        hour = pd.Timestamp(std).hour
        return 7 <= hour < 20

    if "GENEL" in d or "SABIT" in c or "TALEP" in c:
        return True
    if "HER" in d and "YOLCU" in d:
        return True
    return False


def estimate_required_staff_for_flight(flight_row: pd.Series, hakedis_rules: pd.DataFrame) -> Tuple[int, int, str]:
    airline = normalize_text(flight_row.get("airline", "")).replace(" ", "")
    pax = safe_int(flight_row.get("pax_count", 0), 0)
    ac = flight_row.get("ac_type", "")
    std = flight_row.get("std")

    if hakedis_rules is not None and not hakedis_rules.empty:
        rules = hakedis_rules.copy()
        rules["codes"] = rules["airline_rule_norm"].apply(codes_for_rule_name)
        matched = rules[rules["codes"].apply(lambda xs: airline in xs)]
        for _, r in matched.iterrows():
            if detail_matches(r.get("detail"), r.get("criterion"), pax, ac, std):
                total, la, reason = parse_staff_text(r.get("staff_text"), pax)
                return max(total, la), la, f"{r.get('airline_rule')} / {r.get('detail')} → {reason}"

    # Fallback: yolcu varsa yaklaşık her 60 yolcu 1 staff, alt-üst sınırla.
    if pax > 0:
        total = min(10, max(2, math.ceil(pax / 60)))
        return total, 0, "Fallback: her ~60 yolcu için 1 staff"
    return 3, 0, "Fallback: yolcu bilgisi yok, 3 staff"


def enrich_flights_with_requirements(flights: pd.DataFrame, hakedis_rules: pd.DataFrame) -> pd.DataFrame:
    if flights.empty:
        return flights
    rows = []
    for _, row in flights.iterrows():
        total, la, reason = estimate_required_staff_for_flight(row, hakedis_rules)
        rows.append({"required_total": int(total), "required_la": int(la), "required_reason": reason})
    req = pd.DataFrame(rows)
    out = pd.concat([flights.reset_index(drop=True), req], axis=1)
    out["manual_required_total"] = out["required_total"]
    out["manual_required_la"] = out["required_la"]
    out["require_supervisor"] = True
    return out


# =============================================================================
# QUALIFICATION / ROL UYGUNLUĞU
# =============================================================================


def build_alias_dict(alias_editor_df: pd.DataFrame | None = None) -> Dict[str, List[str]]:
    aliases = {k: list(v) for k, v in DEFAULT_AIRLINE_ALIASES.items()}
    if alias_editor_df is not None and not alias_editor_df.empty:
        for _, row in alias_editor_df.iterrows():
            code = normalize_text(row.get("A/L Kodu", "")).replace(" ", "")
            raw = row.get("Qualification Aliasları", "")
            if code:
                parsed = normalize_code_list(raw)
                if code not in parsed:
                    parsed.insert(0, code)
                aliases[code] = parsed
    return aliases


def contains_alias(raw_qualification: object, alias: str) -> bool:
    q = normalize_text(raw_qualification)
    a = re.escape(normalize_text(alias))
    if not q or not a:
        return False
    return re.search(rf"(?<![A-Z0-9]){a}(?![A-Z0-9])", q) is not None


def contains_role_marker(raw_qualification: object, alias: str, marker: str) -> bool:
    """UZB_S, S-UZB, UZB-S, L-UZB, UZB_L gibi işaretleri yakalar."""
    q = normalize_text(raw_qualification)
    a = re.escape(normalize_text(alias))
    m = re.escape(normalize_text(marker))
    if not q or not a:
        return False
    patterns = [
        rf"(?<![A-Z0-9]){m}\s*[-_/ ]\s*{a}(?![A-Z0-9])",
        rf"(?<![A-Z0-9]){a}\s*[-_/ ]\s*{m}(?![A-Z0-9])",
        rf"(?<![A-Z0-9]){a}_{m}(?![A-Z0-9])",
        rf"(?<![A-Z0-9]){m}_{a}(?![A-Z0-9])",
    ]
    return any(re.search(p, q) is not None for p in patterns)


def flight_roles_for_staff(staff_row: pd.Series, airline_code: str, alias_dict: Dict[str, List[str]]) -> List[str]:
    airline_code = normalize_text(airline_code).replace(" ", "")
    aliases = alias_dict.get(airline_code, [airline_code])
    qual = staff_row.get("flight_qualifications", "")
    base_role = staff_row.get("role_override", staff_row.get("base_role", "Agent"))

    has_plain = any(contains_alias(qual, alias) for alias in aliases)
    has_sup = any(contains_role_marker(qual, alias, "S") for alias in aliases)
    has_la = any(contains_role_marker(qual, alias, "L") or contains_role_marker(qual, alias, "LA") for alias in aliases)

    roles: List[str] = []
    if has_plain or has_sup or has_la:
        roles.append("Agent")
        if has_la or base_role == "LA":
            roles.append("LA")
        if has_sup or base_role == "Supervisor":
            roles.append("Supervisor")
    # Şef/LA genel rolü varsa, uçuş kodu plain eşleştiğinde görev rolü de açılır.
    return list(dict.fromkeys(roles))


def merge_staff_qualifications(staff: pd.DataFrame, quals: pd.DataFrame) -> pd.DataFrame:
    staff = staff.copy()
    if quals is None or quals.empty:
        staff["flight_qualifications"] = ""
        return staff
    merged = staff.merge(quals[["name_key", "flight_qualifications"]], on="name_key", how="left")
    merged["flight_qualifications"] = merged["flight_qualifications"].fillna("")
    return merged


# =============================================================================
# DO / İZİN / PERSONEL SAAT KONTROLLERİ
# =============================================================================


def make_empty_request_table(week_dates: List[pd.Timestamp], staff: pd.DataFrame) -> pd.DataFrame:
    default_date = week_dates[0].date() if week_dates else date.today()
    first_person = staff["name"].iloc[0] if not staff.empty else ""
    return pd.DataFrame([{"Personel": first_person, "Tarih": default_date, "Tip": "DO Talebi", "Not": ""}])


def normalize_request_table(req: pd.DataFrame) -> pd.DataFrame:
    if req is None or req.empty:
        return pd.DataFrame(columns=["name_key", "date", "type", "note"])
    out = req.copy()
    if "Personel" not in out.columns:
        out["Personel"] = ""
    if "Tarih" not in out.columns:
        out["Tarih"] = date.today()
    if "Tip" not in out.columns:
        out["Tip"] = "DO Talebi"
    if "Not" not in out.columns:
        out["Not"] = ""
    out["name_key"] = out["Personel"].apply(normalize_text)
    out["date"] = pd.to_datetime(out["Tarih"], errors="coerce").dt.date
    out["type"] = out["Tip"].astype(str)
    out["note"] = out["Not"].astype(str)
    out = out[out["name_key"] != ""]
    return out[["name_key", "date", "type", "note"]]


def has_request_block(name_key: str, target_date: date, req_norm: pd.DataFrame) -> Tuple[bool, str]:
    if req_norm is None or req_norm.empty:
        return False, ""
    hit = req_norm[(req_norm["name_key"] == normalize_text(name_key)) & (req_norm["date"] == target_date)]
    if hit.empty:
        return False, ""
    labels = ", ".join(hit["type"].astype(str).unique())
    return True, labels


def staff_hour_summary(staff: pd.DataFrame, shifts: pd.DataFrame) -> pd.DataFrame:
    if staff.empty:
        return pd.DataFrame()
    if shifts.empty:
        out = staff[["staff_id", "name", "work_type", "route", "role_override", "active"]].copy()
        out["planned_work_hours"] = 0.0
        out["limit_status"] = "Vardiya yok"
        return out
    agg = shifts.groupby("staff_id", as_index=False).agg(
        planned_work_hours=("planned_work_hours", "sum"),
        file_hours=("raw_hours_from_file", "sum"),
        work_days=("status", lambda x: int((x == STATUS_WORK).sum())),
    )
    out = staff.merge(agg, on="staff_id", how="left")
    out[["planned_work_hours", "file_hours", "work_days"]] = out[["planned_work_hours", "file_hours", "work_days"]].fillna(0)

    def status(row):
        if not row.get("active", True):
            return "Pasif"
        h = float(row["planned_work_hours"])
        if row["work_type"] == "PART":
            return "OK" if h <= 25 else "Part max 25 aşıldı"
        if h < 40:
            return "Full min 40 altında"
        if h > 50:
            return "Full max 50 aşıldı"
        return "OK"

    out["limit_status"] = out.apply(status, axis=1)
    return out[["staff_id", "name", "work_type", "route", "role_override", "active", "planned_work_hours", "file_hours", "work_days", "limit_status"]]


def rest_rule_violations(staff: pd.DataFrame, shifts: pd.DataFrame, min_rest_hours: float = 11.0) -> pd.DataFrame:
    rows = []
    if shifts.empty:
        return pd.DataFrame(rows)
    work = shifts[(shifts["status"] == STATUS_WORK) & shifts["start_dt"].notna() & shifts["end_dt"].notna()].copy()
    for staff_id, grp in work.groupby("staff_id"):
        grp = grp.sort_values("start_dt")
        prev = None
        for _, row in grp.iterrows():
            if prev is not None:
                rest = (row["start_dt"] - prev["end_dt"]).total_seconds() / 3600
                if rest < min_rest_hours:
                    rows.append({
                        "Personel": row["name"],
                        "Önceki Vardiya": f"{prev['start_dt']:%d.%m %H:%M} - {prev['end_dt']:%d.%m %H:%M}",
                        "Sonraki Vardiya": f"{row['start_dt']:%d.%m %H:%M} - {row['end_dt']:%d.%m %H:%M}",
                        "Dinlenme Saati": round(rest, 2),
                        "Uyarı": f"{min_rest_hours} saat kuralı ihlal"
                    })
            prev = row
    return pd.DataFrame(rows)


def service_warnings(staff: pd.DataFrame, shifts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if shifts.empty:
        return pd.DataFrame(rows)
    route_map = staff.set_index("staff_id")["route"].to_dict()
    for _, row in shifts.iterrows():
        if row["status"] != STATUS_WORK:
            continue
        route = route_map.get(row["staff_id"], "")
        reasons = []
        if not row["service_ok"]:
            reasons.append(f"Vardiya {row['start_service']}-{row['end_service']} servis saatleriyle tam eşleşmiyor")
        if route not in ROUTES:
            reasons.append(f"Güzergah tanımsız/geçersiz: {route}")
        if reasons:
            rows.append({
                "Personel": row["name"],
                "Tarih": row["date"],
                "Vardiya": row["shift_text"],
                "Güzergah": route,
                "Geliş Servisi": row["start_service"],
                "Gidiş Servisi": row["end_service"],
                "Uyarı": " | ".join(reasons),
            })
    return pd.DataFrame(rows)


# =============================================================================
# PLANLAMA MOTORU
# =============================================================================


def find_covering_shift(staff_id: str, duty_start: datetime, duty_end: datetime, shifts: pd.DataFrame) -> Optional[pd.Series]:
    if shifts.empty:
        return None
    grp = shifts[(shifts["staff_id"].astype(str) == str(staff_id)) & (shifts["status"] == STATUS_WORK)].copy()
    grp = grp[grp["start_dt"].notna() & grp["end_dt"].notna()]
    for _, row in grp.iterrows():
        if row["start_dt"] <= duty_start and row["end_dt"] >= duty_end:
            return row
    return None


def assignment_conflicts(staff_id: str, duty_start: datetime, duty_end: datetime, assigned_slots: List[dict]) -> bool:
    for slot in assigned_slots:
        if str(slot["staff_id"]) == str(staff_id) and overlap(duty_start, duty_end, slot["duty_start"], slot["duty_end"]):
            return True
    return False


def candidate_pool_for_flight(
    flight: pd.Series,
    staff: pd.DataFrame,
    shifts: pd.DataFrame,
    req_norm: pd.DataFrame,
    alias_dict: Dict[str, List[str]],
    duty_start: datetime,
    duty_end: datetime,
    assigned_slots: List[dict],
    hour_summary: pd.DataFrame,
    allow_non_service_shift: bool = False,
) -> pd.DataFrame:
    rows = []
    hour_map = hour_summary.set_index("staff_id").to_dict("index") if not hour_summary.empty else {}
    target_date = pd.Timestamp(flight["std"]).date()
    for _, person in staff.iterrows():
        if not bool(person.get("active", True)):
            continue
        blocked, block_reason = has_request_block(person["name_key"], target_date, req_norm)
        if blocked:
            continue
        roles = flight_roles_for_staff(person, flight["airline"], alias_dict)
        if not roles:
            continue
        shift = find_covering_shift(person["staff_id"], duty_start, duty_end, shifts)
        if shift is None:
            continue
        if not allow_non_service_shift and not bool(shift.get("service_ok", False)):
            continue
        if assignment_conflicts(person["staff_id"], duty_start, duty_end, assigned_slots):
            continue
        hrow = hour_map.get(person["staff_id"], {})
        if hrow.get("limit_status") in {"Part max 25 aşıldı", "Full max 50 aşıldı", "Pasif"}:
            continue
        rows.append({
            "staff_id": person["staff_id"],
            "Personel": person["name"],
            "Rol Yetkileri": ", ".join(roles),
            "Ana Rol": person.get("role_override", person.get("base_role", "Agent")),
            "Güzergah": person.get("route", ""),
            "Vardiya": shift.get("shift_text", ""),
            "Vardiya Başlangıç": shift.get("start_dt"),
            "Vardiya Bitiş": shift.get("end_dt"),
            "Haftalık Saat": hrow.get("planned_work_hours", 0.0),
            "Limit Durumu": hrow.get("limit_status", ""),
            "_roles": roles,
        })
    return pd.DataFrame(rows)


def choose_candidates(pool: pd.DataFrame, needed: int, role: str, already_selected: set, assignment_counts: Dict[str, int]) -> List[pd.Series]:
    if needed <= 0 or pool.empty:
        return []
    p = pool[~pool["staff_id"].astype(str).isin(already_selected)].copy()
    if role != "Any":
        p = p[p["_roles"].apply(lambda xs: role in xs)]
    if p.empty:
        return []
    p["_assign_count"] = p["staff_id"].astype(str).map(lambda x: assignment_counts.get(x, 0))
    p["_role_bonus"] = p["Ana Rol"].apply(lambda r: 0 if (role == "Any" or r == role) else 1)
    p = p.sort_values(["_assign_count", "Haftalık Saat", "_role_bonus", "Personel"])
    return [row for _, row in p.head(needed).iterrows()]


def generate_flight_plan(
    flights: pd.DataFrame,
    staff: pd.DataFrame,
    shifts: pd.DataFrame,
    req_norm: pd.DataFrame,
    alias_dict: Dict[str, List[str]],
    duty_lead_minutes: int = 95,
    duty_after_minutes: int = 30,
    allow_non_service_shift: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    assignments: List[dict] = []
    warnings: List[dict] = []
    assigned_slots: List[dict] = []
    assignment_counts: Dict[str, int] = {}
    hsum = staff_hour_summary(staff, shifts)

    if flights.empty or staff.empty:
        return pd.DataFrame(assignments), pd.DataFrame(warnings)

    flights_sorted = flights.sort_values("std").reset_index(drop=True)
    for _, flight in flights_sorted.iterrows():
        std = pd.Timestamp(flight["std"]).to_pydatetime()
        duty_start = std - timedelta(minutes=duty_lead_minutes)
        duty_end = std + timedelta(minutes=duty_after_minutes)
        required_total = safe_int(flight.get("manual_required_total", flight.get("required_total", 3)), 3)
        required_la = safe_int(flight.get("manual_required_la", flight.get("required_la", 0)), 0)
        require_supervisor = bool(flight.get("require_supervisor", True))

        pool = candidate_pool_for_flight(
            flight, staff, shifts, req_norm, alias_dict, duty_start, duty_end,
            assigned_slots, hsum, allow_non_service_shift=allow_non_service_shift,
        )
        selected: List[Tuple[pd.Series, str]] = []
        selected_ids: set = set()

        # Önce supervisor.
        if require_supervisor:
            sup = choose_candidates(pool, 1, "Supervisor", selected_ids, assignment_counts)
            for c in sup:
                selected.append((c, "Supervisor"))
                selected_ids.add(str(c["staff_id"]))

        # Sonra LA.
        la_needed = max(0, required_la)
        la_chosen = choose_candidates(pool, la_needed, "LA", selected_ids, assignment_counts)
        for c in la_chosen:
            selected.append((c, "LA"))
            selected_ids.add(str(c["staff_id"]))

        # Kalan toplam sayıyı agent/uygun herkesle doldur.
        remaining = max(0, required_total - len(selected))
        any_chosen = choose_candidates(pool, remaining, "Any", selected_ids, assignment_counts)
        for c in any_chosen:
            # Yetkisi varsa ana rolünü koru, yoksa Agent yaz.
            duty_role = c["Ana Rol"] if c["Ana Rol"] in c["_roles"] else "Agent"
            selected.append((c, duty_role))
            selected_ids.add(str(c["staff_id"]))

        if len(selected) < required_total:
            warnings.append({
                "Uçuş": flight["flight_id"],
                "STD": std,
                "Gereken": required_total,
                "Bulunan": len(selected),
                "Uyarı": "Yeterli uygun personel bulunamadı. Qualification, servis saati, vardiya kapsaması veya DO/izin engeli olabilir.",
            })
        if require_supervisor and not any(role == "Supervisor" for _, role in selected):
            warnings.append({
                "Uçuş": flight["flight_id"],
                "STD": std,
                "Gereken": "1 Supervisor",
                "Bulunan": 0,
                "Uyarı": "Supervisor uygunluğu bulunamadı.",
            })
        if required_la > 0 and sum(1 for _, role in selected if role == "LA") < required_la:
            warnings.append({
                "Uçuş": flight["flight_id"],
                "STD": std,
                "Gereken": f"{required_la} LA",
                "Bulunan": sum(1 for _, role in selected if role == "LA"),
                "Uyarı": "LA uygunluğu eksik kaldı.",
            })

        for idx, (cand, duty_role) in enumerate(selected, start=1):
            assignments.append({
                "Uçuş ID": flight["flight_id"],
                "Gün": flight.get("day", ""),
                "A/L": flight["airline"],
                "IN": flight.get("in_flight", ""),
                "OUT": flight.get("out_flight", ""),
                "STD": std,
                "Görev Başlangıç": duty_start,
                "Görev Bitiş": duty_end,
                "Sıra": idx,
                "Personel": cand["Personel"],
                "staff_id": cand["staff_id"],
                "Görev Rolü": duty_role,
                "Güzergah": cand["Güzergah"],
                "Vardiya": cand["Vardiya"],
                "Haftalık Saat": cand["Haftalık Saat"],
                "Hakediş": required_total,
                "Hakediş LA": required_la,
                "Hakediş Nedeni": flight.get("required_reason", ""),
                "Not": "Otomatik öneri",
            })
            assigned_slots.append({
                "staff_id": cand["staff_id"],
                "flight_id": flight["flight_id"],
                "duty_start": duty_start,
                "duty_end": duty_end,
            })
            assignment_counts[str(cand["staff_id"])] = assignment_counts.get(str(cand["staff_id"]), 0) + 1

    return pd.DataFrame(assignments), pd.DataFrame(warnings)


def validate_edited_plan(plan: pd.DataFrame, flights: pd.DataFrame, staff: pd.DataFrame, shifts: pd.DataFrame, req_norm: pd.DataFrame, alias_dict: Dict[str, List[str]]) -> pd.DataFrame:
    rows = []
    if plan is None or plan.empty:
        return pd.DataFrame(rows)
    staff_by_name = {normalize_text(r["name"]): r for _, r in staff.iterrows()}
    flight_by_id = {str(r["flight_id"]): r for _, r in flights.iterrows()}
    slots = []
    for idx, row in plan.iterrows():
        person_name = row.get("Personel", "")
        person = staff_by_name.get(normalize_text(person_name))
        flight = flight_by_id.get(str(row.get("Uçuş ID", "")))
        errors = []
        if person is None:
            errors.append("Personel master listede yok")
        if flight is None:
            errors.append("Uçuş bulunamadı")
        if person is not None and flight is not None:
            duty_start = pd.to_datetime(row.get("Görev Başlangıç"), errors="coerce")
            duty_end = pd.to_datetime(row.get("Görev Bitiş"), errors="coerce")
            if pd.isna(duty_start) or pd.isna(duty_end):
                std = pd.Timestamp(flight["std"]).to_pydatetime()
                duty_start = std - timedelta(minutes=95)
                duty_end = std + timedelta(minutes=30)
            else:
                duty_start = duty_start.to_pydatetime()
                duty_end = duty_end.to_pydatetime()
            roles = flight_roles_for_staff(person, flight["airline"], alias_dict)
            duty_role = row.get("Görev Rolü", "Agent")
            if duty_role not in roles and not (duty_role == "Agent" and roles):
                errors.append(f"{flight['airline']} için {duty_role} yetkisi görünmüyor")
            shift = find_covering_shift(person["staff_id"], duty_start, duty_end, shifts)
            if shift is None:
                errors.append("Vardiya görev saatini kapsamıyor")
            else:
                if not shift.get("service_ok", False):
                    errors.append("Vardiya servis saatlerine uymuyor")
            blocked, reason = has_request_block(person["name_key"], pd.Timestamp(flight["std"]).date(), req_norm)
            if blocked:
                errors.append(f"DO/izin/talep engeli: {reason}")
            for slot in slots:
                if slot["staff_id"] == person["staff_id"] and overlap(duty_start, duty_end, slot["start"], slot["end"]):
                    errors.append(f"Başka görevle çakışıyor: {slot['flight']}")
            slots.append({"staff_id": person["staff_id"], "start": duty_start, "end": duty_end, "flight": row.get("Uçuş ID", "")})
        rows.append({
            "Satır": idx + 1,
            "Uçuş": row.get("Uçuş ID", ""),
            "Personel": person_name,
            "Durum": "OK" if not errors else "Uyarı",
            "Açıklama": " | ".join(errors) if errors else "Manuel plan uygun görünüyor",
        })
    return pd.DataFrame(rows)


# =============================================================================
# GECİKME / DEVİR ÖNERİ MOTORU
# =============================================================================


def delay_recommendations(
    selected_flight_id: str,
    delay_minutes: int,
    plan: pd.DataFrame,
    flights: pd.DataFrame,
    staff: pd.DataFrame,
    shifts: pd.DataFrame,
    req_norm: pd.DataFrame,
    alias_dict: Dict[str, List[str]],
) -> Tuple[pd.DataFrame, str]:
    if plan is None or plan.empty or flights.empty:
        return pd.DataFrame(), "Önce otomatik plan oluşturulmalı veya manuel plan girilmeli."
    flight_row = flights[flights["flight_id"].astype(str) == str(selected_flight_id)]
    if flight_row.empty:
        return pd.DataFrame(), "Seçilen uçuş bulunamadı."
    flight = flight_row.iloc[0]
    old_std = pd.Timestamp(flight["std"]).to_pydatetime()
    new_std = old_std + timedelta(minutes=int(delay_minutes))
    old_duty_end = old_std + timedelta(minutes=30)
    new_duty_end = new_std + timedelta(minutes=30)
    old_duty_start = old_std - timedelta(minutes=95)

    current_team = plan[plan["Uçuş ID"].astype(str) == str(selected_flight_id)].copy()
    if current_team.empty:
        return pd.DataFrame(), "Bu uçuş için mevcut planda ekip yok."

    staff_by_name = {normalize_text(r["name"]): r for _, r in staff.iterrows()}
    existing_slots = []
    for _, r in plan.iterrows():
        if str(r.get("Uçuş ID", "")) == str(selected_flight_id):
            continue
        person = staff_by_name.get(normalize_text(r.get("Personel", "")))
        if person is None:
            continue
        start = pd.to_datetime(r.get("Görev Başlangıç"), errors="coerce")
        end = pd.to_datetime(r.get("Görev Bitiş"), errors="coerce")
        if not pd.isna(start) and not pd.isna(end):
            existing_slots.append({"staff_id": person["staff_id"], "duty_start": start.to_pydatetime(), "duty_end": end.to_pydatetime(), "flight_id": r.get("Uçuş ID", "")})

    rows = []
    hsum = staff_hour_summary(staff, shifts)

    for _, member in current_team.iterrows():
        person = staff_by_name.get(normalize_text(member.get("Personel", "")))
        if person is None:
            continue
        shift = find_covering_shift(person["staff_id"], old_duty_start, new_duty_end, shifts)
        has_other_conflict = assignment_conflicts(person["staff_id"], old_duty_start, new_duty_end, existing_slots)
        needs_change = shift is None or has_other_conflict
        reason_parts = []
        if shift is None:
            reason_parts.append("Yeni gecikmeli bitiş personelin vardiyasını aşıyor")
        if has_other_conflict:
            reason_parts.append("Yeni süre başka görevle çakışıyor")
        if not needs_change:
            rows.append({
                "Etkilenen Personel": member.get("Personel"),
                "Mevcut Rol": member.get("Görev Rolü"),
                "Sorun": "Sorun görünmüyor",
                "Önerilen Devir": "Gerek yok",
                "Önerilen Güzergah": person.get("route", ""),
                "Önerilen Vardiya": shift.get("shift_text", "") if shift is not None else "",
                "Öneri Notu": "Personel gecikmeli bitişi karşılayabiliyor.",
            })
            continue

        # Devir aralığı: eski görev bitişinden yeni görev bitişine kadar.
        takeover_start = min(old_duty_end, new_duty_end)
        takeover_end = new_duty_end
        pool = candidate_pool_for_flight(
            flight, staff, shifts, req_norm, alias_dict,
            takeover_start, takeover_end, existing_slots, hsum,
            allow_non_service_shift=False,
        )
        if not pool.empty:
            # Aynı kişi yerine başkasını öner.
            pool = pool[pool["staff_id"].astype(str) != str(person["staff_id"])]
            duty_role = member.get("Görev Rolü", "Agent")
            if duty_role in {"Supervisor", "LA"}:
                role_pool = pool[pool["_roles"].apply(lambda xs: duty_role in xs)]
                if not role_pool.empty:
                    pool = role_pool
            pool["_same_route"] = pool["Güzergah"].apply(lambda r: 0 if r == person.get("route", "") else 1)
            pool = pool.sort_values(["_same_route", "Haftalık Saat", "Personel"])
        if pool.empty:
            rows.append({
                "Etkilenen Personel": member.get("Personel"),
                "Mevcut Rol": member.get("Görev Rolü"),
                "Sorun": " | ".join(reason_parts),
                "Önerilen Devir": "Uygun aday bulunamadı",
                "Önerilen Güzergah": "",
                "Önerilen Vardiya": "",
                "Öneri Notu": "Manuel kontrol gerekir: servis, qualification veya vardiya kapsaması engeli var.",
            })
        else:
            best = pool.iloc[0]
            rows.append({
                "Etkilenen Personel": member.get("Personel"),
                "Mevcut Rol": member.get("Görev Rolü"),
                "Sorun": " | ".join(reason_parts),
                "Önerilen Devir": best["Personel"],
                "Önerilen Güzergah": best["Güzergah"],
                "Önerilen Vardiya": best["Vardiya"],
                "Öneri Notu": f"{takeover_start:%H:%M}-{takeover_end:%H:%M} aralığını devralabilir. Rol yetkileri: {best['Rol Yetkileri']}",
            })

    summary = (
        f"{flight['out_flight']} uçuşu {old_std:%d.%m.%Y %H:%M} STD'den "
        f"{new_std:%d.%m.%Y %H:%M} STD'ye gecikmiş kabul edildi. "
        f"Devir önerileri yeni görev bitişi {new_duty_end:%H:%M} dikkate alınarak üretildi."
    )
    return pd.DataFrame(rows), summary


# =============================================================================
# RAPOR EXPORT
# =============================================================================


def make_excel_report(sheets: Dict[str, pd.DataFrame]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="dd.mm.yyyy hh:mm", date_format="dd.mm.yyyy") as writer:
        for sheet_name, df in sheets.items():
            if df is None:
                continue
            safe_sheet = sheet_name[:31]
            data = df.copy()
            # Streamlit internal kolonlarını raporda gizle.
            for col in list(data.columns):
                if str(col).startswith("_") or col == "staff_id":
                    data = data.drop(columns=[col])
            data.to_excel(writer, sheet_name=safe_sheet, index=False)
            worksheet = writer.sheets[safe_sheet]
            workbook = writer.book
            header_fmt = workbook.add_format({"bold": True, "bg_color": "#D71920", "font_color": "white", "border": 1})
            for col_num, value in enumerate(data.columns.values):
                worksheet.write(0, col_num, value, header_fmt)
                width = min(max(len(str(value)) + 2, 12), 36)
                worksheet.set_column(col_num, col_num, width)
            worksheet.freeze_panes(1, 0)
    return output.getvalue()


# =============================================================================
# STREAMLIT UI
# =============================================================================


def inject_css():
    st.markdown(
        """
        <style>
        :root {
            --celebi-red: #D71920;
            --celebi-blue: #003D7C;
            --celebi-yellow: #FFC20E;
            --soft-bg: #F7F9FC;
        }
        .main .block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1450px;}
        .celebi-hero {
            background: linear-gradient(135deg, #D71920 0%, #9E1016 45%, #003D7C 100%);
            padding: 22px 26px; border-radius: 18px; color: white; margin-bottom: 16px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.13);
        }
        .celebi-hero h1 {margin: 0; font-size: 30px; letter-spacing: .2px;}
        .celebi-hero p {margin: 8px 0 0 0; opacity: .95;}
        .metric-card {
            background: white; border: 1px solid #E8EDF3; border-radius: 16px; padding: 16px;
            box-shadow: 0 4px 18px rgba(0,0,0,0.05);
        }
        .small-note {font-size: 13px; color: #667085;}
        div[data-testid="stMetric"] {background: white; border: 1px solid #EEF2F6; padding: 14px; border-radius: 14px;}
        .stTabs [data-baseweb="tab-list"] {gap: 6px;}
        .stTabs [data-baseweb="tab"] {border-radius: 12px 12px 0 0; padding: 10px 14px;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(logo_file=None):
    cols = st.columns([0.14, 0.86])
    with cols[0]:
        if logo_file is not None:
            st.image(logo_file, use_container_width=True)
        else:
            st.markdown(
                """
                <div style="height:78px;border-radius:16px;background:white;display:flex;align-items:center;justify-content:center;border:2px solid #D71920;color:#D71920;font-weight:900;font-size:22px;">Çelebi</div>
                """,
                unsafe_allow_html=True,
            )
    with cols[1]:
        st.markdown(
            f"""
            <div class="celebi-hero">
              <h1>{APP_TITLE}</h1>
              <p>Haftalık uçuş planı, qualification, servis saatleri, DO/izin talepleri, 11 saat dinlenme ve gecikme devir önerilerini tek panelde yönetir. <b>{APP_VERSION}</b></p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def load_all_data(upload_departure, upload_qual, upload_week, upload_hakedis, break_threshold, break_hours):
    default_departure = "/mnt/data/Departure(Sayfa1).csv"
    default_qual = "/mnt/data/QUALIFICATIONLAR-YHM(Sheet1).csv"
    default_week = "/mnt/data/20 HAFTA YHM.xlsx"
    default_hakedis = "/mnt/data/Hakediş.xlsx"

    # Departure
    dep_source = upload_departure if upload_departure is not None else default_departure
    if str(dep_source).lower().endswith(".csv") or (upload_departure is not None and upload_departure.name.lower().endswith(".csv")):
        dep_raw = read_csv_smart(dep_source)
    else:
        dep_raw = read_excel_sheet(dep_source, preferred_names=["20.HAFTA DEPARTURE", "DEPARTURE"])
    flights = standardize_departure(dep_raw)

    # Qualifications
    qual_source = upload_qual if upload_qual is not None else default_qual
    if str(qual_source).lower().endswith(".csv") or (upload_qual is not None and upload_qual.name.lower().endswith(".csv")):
        qual_raw = read_csv_smart(qual_source)
    else:
        qual_raw = read_excel_sheet(qual_source, required_cols=["AD", "SOYAD", "QUALIFICATIONS"])
    quals = standardize_qualifications(qual_raw)

    # Week staff/shifts
    week_source = upload_week if upload_week is not None else default_week
    week_sheet = detect_week_sheet(week_source)
    week_source = rewind_file(week_source)
    week_df = pd.read_excel(week_source, sheet_name=week_sheet)
    staff, shifts, week_dates = standardize_staff_and_shifts(week_df, break_threshold, break_hours)
    staff = merge_staff_qualifications(staff, quals)

    # Hakediş
    hakedis_source = upload_hakedis if upload_hakedis is not None else default_hakedis
    hak_raw = read_excel_sheet(hakedis_source)
    hakedis = standardize_hakedis(hak_raw)
    flights = enrich_flights_with_requirements(flights, hakedis)
    return flights, quals, staff, shifts, hakedis, week_dates, week_sheet


def init_session_tables(staff: pd.DataFrame, week_dates: List[pd.Timestamp]):
    if "staff_editor" not in st.session_state:
        st.session_state.staff_editor = staff[["name", "email", "work_type", "gender", "route", "base_role", "role_override", "active", "flight_qualifications"]].copy()
    if "request_editor" not in st.session_state:
        st.session_state.request_editor = make_empty_request_table(week_dates, staff)
    if "manual_plan" not in st.session_state:
        st.session_state.manual_plan = pd.DataFrame()


def apply_staff_editor(base_staff: pd.DataFrame, edited: pd.DataFrame) -> pd.DataFrame:
    if edited is None or edited.empty:
        return base_staff
    out_rows = []
    base_by_key = {normalize_text(r["name"]): r for _, r in base_staff.iterrows()}
    for idx, row in edited.iterrows():
        name = clean_name(row.get("name", ""))
        if not name:
            continue
        key = normalize_text(name)
        if key in base_by_key:
            base = base_by_key[key].copy()
        else:
            base = pd.Series({
                "staff_id": f"new_{idx}", "name": name, "name_key": key,
                "first_name": name.split(" ")[0], "last_name": " ".join(name.split(" ")[1:]),
                "email": "", "work_type_raw": row.get("work_type", "FULL"),
                "gender": row.get("gender", ""), "base_qualification": "",
                "base_role": row.get("base_role", "Agent"), "route_valid": True,
            })
        base["name"] = name
        base["name_key"] = key
        base["email"] = row.get("email", base.get("email", ""))
        base["work_type"] = row.get("work_type", base.get("work_type", "FULL"))
        base["gender"] = row.get("gender", base.get("gender", ""))
        base["route"] = normalize_text(row.get("route", base.get("route", ""))).replace(" ", "")
        base["base_role"] = row.get("base_role", base.get("base_role", "Agent"))
        base["role_override"] = row.get("role_override", base.get("role_override", base.get("base_role", "Agent")))
        base["active"] = bool(row.get("active", True))
        base["flight_qualifications"] = row.get("flight_qualifications", base.get("flight_qualifications", ""))
        base["route_valid"] = base["route"] in ROUTES
        out_rows.append(dict(base))
    out = pd.DataFrame(out_rows)
    if "staff_id" not in out.columns:
        out["staff_id"] = out.index.astype(str)
    return out.reset_index(drop=True)


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="✈️", layout="wide")
    inject_css()

    with st.sidebar:
        st.subheader("Logo ve Dosyalar")
        logo = st.file_uploader("Çelebi logosu yükle (PNG/JPG)", type=["png", "jpg", "jpeg"])
        st.caption("Logo yüklemezsen sistem Çelebi renklerine uygun yazı logosu gösterir.")
        st.divider()
        upload_departure = st.file_uploader("DEPARTURE dosyası", type=["csv", "xlsx"])
        upload_qual = st.file_uploader("QUALIFICATIONLAR-YHM dosyası", type=["csv", "xlsx"])
        upload_week = st.file_uploader("20. HAFTA YHM / vardiya dosyası", type=["xlsx"])
        upload_hakedis = st.file_uploader("Hakediş dosyası", type=["xlsx"])
        st.caption("Dosya yüklemezsen uygulama klasördeki örnek dosyalarla açılır.")

    hero(logo)

    with st.sidebar:
        st.subheader("Planlama Kuralları")
        duty_lead = st.number_input("Uçuş görev başlangıcı: STD'den kaç dk önce?", 30, 240, 95, 5)
        duty_after = st.number_input("Uçuş görev bitişi: STD'den kaç dk sonra?", 0, 180, 30, 5)
        min_rest = st.number_input("İki vardiya arası minimum dinlenme saati", 6.0, 24.0, 11.0, 0.5)
        break_threshold = st.number_input("Mola düşme eşiği (saat)", 0.0, 12.0, 6.0, 0.5)
        break_hours = st.number_input("Mola süresi (saat)", 0.0, 3.0, 1.0, 0.25)
        allow_non_service = st.checkbox("Servis uyumsuz vardiyayı yine de aday göster", value=False)

    try:
        flights, quals, staff_base, shifts, hakedis, week_dates, week_sheet = load_all_data(
            upload_departure, upload_qual, upload_week, upload_hakedis, break_threshold, break_hours
        )
    except Exception as e:
        st.error(f"Dosyalar okunurken hata oluştu: {e}")
        st.stop()

    init_session_tables(staff_base, week_dates)

    # Aliases editor init
    if "alias_editor" not in st.session_state:
        st.session_state.alias_editor = pd.DataFrame([
            {"A/L Kodu": k, "Qualification Aliasları": ", ".join(v)}
            for k, v in DEFAULT_AIRLINE_ALIASES.items()
        ])

    tab_data, tab_rules, tab_staff, tab_shift, tab_flights, tab_plan, tab_delay, tab_report = st.tabs([
        "1 Veri", "2 Kurallar", "3 Personel", "4 Vardiya & Servis", "5 Uçuş Hakediş", "6 Planlama", "7 Gecikme AI", "8 Rapor"
    ])

    with tab_data:
        st.subheader("Okunan Dosya Özeti")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Uçuş", len(flights))
        c2.metric("Personel", len(staff_base))
        c3.metric("Qualification Kaydı", len(quals))
        c4.metric("Vardiya Sheet", week_sheet)
        st.info("Her hafta yeni DEPARTURE ve 20. HAFTA YHM dosyasını soldan yükleyerek sistemi güncelleyebilirsin.")
        with st.expander("DEPARTURE önizleme", expanded=False):
            st.dataframe(flights.head(50), use_container_width=True)
        with st.expander("Qualification önizleme", expanded=False):
            st.dataframe(quals.head(50), use_container_width=True)
        with st.expander("Hakediş kural önizleme", expanded=False):
            st.dataframe(hakedis, use_container_width=True)

    with tab_rules:
        st.subheader("Servis ve Qualification Kuralları")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Geliş servisleri**")
            st.write(", ".join(ARRIVAL_SERVICES))
            st.markdown("**Gidiş servisleri**")
            st.write(", ".join(DEPARTURE_SERVICES))
        with c2:
            st.markdown("**Servis güzergahları**")
            st.write(", ".join(ROUTES))
            st.markdown("**Saat limitleri**")
            st.write("Full-time: minimum 40, maksimum 50 saat. Part-time: maksimum 25 saat. Mola hariç çalışma saati hesaplanır.")
        st.markdown("### A/L ↔ Qualification Alias Tablosu")
        st.caption("Qualification dosyasında kodlar farklı yazılıyorsa buradan düzenle. Örneğin ETD için EY/ETIHAD eşleşmesi gibi.")
        st.session_state.alias_editor = st.data_editor(
            st.session_state.alias_editor,
            num_rows="dynamic",
            use_container_width=True,
            key="alias_data_editor",
        )

    alias_dict = build_alias_dict(st.session_state.alias_editor)

    with tab_staff:
        st.subheader("Personel Yönetimi")
        st.caption("Buradan rol terfisi, güzergah değişimi, yeni personel ekleme veya istifa/pasif işlemini yapabilirsin. Pasif personel planlamaya girmez.")
        st.session_state.staff_editor = st.data_editor(
            st.session_state.staff_editor,
            column_config={
                "work_type": st.column_config.SelectboxColumn("work_type", options=["FULL", "PART"]),
                "base_role": st.column_config.SelectboxColumn("base_role", options=ROLE_OPTIONS),
                "role_override": st.column_config.SelectboxColumn("role_override", options=ROLE_OPTIONS),
                "route": st.column_config.SelectboxColumn("route", options=ROUTES + ["KGT", ""]),
                "active": st.column_config.CheckboxColumn("active"),
                "flight_qualifications": st.column_config.TextColumn("flight_qualifications", width="large"),
            },
            num_rows="dynamic",
            use_container_width=True,
            key="staff_data_editor",
        )
        staff = apply_staff_editor(staff_base, st.session_state.staff_editor)

        st.markdown("### DO / İzin / VA Talepleri")
        st.caption("Uçuş planlama motoru bu tabloda seçilen personeli ilgili tarihte aday göstermeyecek.")
        person_options = staff["name"].sort_values().tolist()
        min_date = min([d.date() for d in week_dates], default=date.today())
        max_date = max([d.date() for d in week_dates], default=date.today() + timedelta(days=6))
        st.session_state.request_editor = st.data_editor(
            st.session_state.request_editor,
            column_config={
                "Personel": st.column_config.SelectboxColumn("Personel", options=person_options),
                "Tarih": st.column_config.DateColumn("Tarih", min_value=min_date, max_value=max_date),
                "Tip": st.column_config.SelectboxColumn("Tip", options=["DO Talebi", "İzin", "VA", "Rapor", "Diğer"]),
                "Not": st.column_config.TextColumn("Not"),
            },
            num_rows="dynamic",
            use_container_width=True,
            key="request_data_editor",
        )
        req_norm = normalize_request_table(st.session_state.request_editor)

        c1, c2, c3 = st.columns(3)
        c1.metric("Aktif Personel", int(staff["active"].sum()))
        c2.metric("Pasif/İstifa", int((~staff["active"].astype(bool)).sum()))
        c3.metric("DO/İzin Talebi", len(req_norm))

    # staff and req norm may not exist if tab not opened due Streamlit execution? Ensure now.
    staff = apply_staff_editor(staff_base, st.session_state.staff_editor)
    req_norm = normalize_request_table(st.session_state.request_editor)

    with tab_shift:
        st.subheader("Vardiya, Servis ve 11 Saat Dinlenme Kontrolü")
        hour_sum = staff_hour_summary(staff, shifts)
        svc_warn = service_warnings(staff, shifts)
        rest_warn = rest_rule_violations(staff, shifts, min_rest)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Servis Uyarısı", len(svc_warn))
        c2.metric("11 Saat İhlali", len(rest_warn))
        c3.metric("Saat Limiti Uyarısı", int((hour_sum["limit_status"] != "OK").sum()) if not hour_sum.empty else 0)
        c4.metric("Toplam Planlanan Saat", round(float(hour_sum["planned_work_hours"].sum()), 1) if not hour_sum.empty else 0)

        st.markdown("### Personel Saat Özeti")
        st.dataframe(hour_sum.sort_values(["limit_status", "planned_work_hours"], ascending=[True, False]), use_container_width=True)

        st.markdown("### Servis Uyumsuzlukları")
        if svc_warn.empty:
            st.success("Servis saatleriyle ilgili uyarı yok.")
        else:
            st.dataframe(svc_warn, use_container_width=True)

        st.markdown("### 11 Saat Dinlenme Uyarıları")
        if rest_warn.empty:
            st.success("11 saat dinlenme kuralı ihlali görünmüyor.")
        else:
            st.dataframe(rest_warn, use_container_width=True)

    with tab_flights:
        st.subheader("Uçuş Hakediş ve Manuel Sayı Düzenleme")
        st.caption("Sistem hakediş dosyasından ihtiyacı tahmin eder. Buradan manuel artırıp azaltabilirsin.")
        flight_edit_cols = [
            "flight_id", "day", "airline", "out_flight", "std", "to", "ac_type", "pax_raw", "pax_count",
            "required_total", "required_la", "manual_required_total", "manual_required_la", "require_supervisor", "required_reason"
        ]
        edited_flights = st.data_editor(
            flights[flight_edit_cols],
            column_config={
                "manual_required_total": st.column_config.NumberColumn("Manuel Hakediş", min_value=1, max_value=30, step=1),
                "manual_required_la": st.column_config.NumberColumn("Manuel LA", min_value=0, max_value=10, step=1),
                "require_supervisor": st.column_config.CheckboxColumn("Supervisor Gerekli"),
                "required_reason": st.column_config.TextColumn("Hakediş Nedeni", width="large"),
            },
            disabled=["flight_id", "day", "airline", "out_flight", "std", "to", "ac_type", "pax_raw", "pax_count", "required_total", "required_la"],
            use_container_width=True,
            key="flight_requirement_editor",
        )
        # Düzenlenen kolonları ana flights tablosuna geri yaz.
        flights = flights.drop(columns=["manual_required_total", "manual_required_la", "require_supervisor"], errors="ignore").merge(
            edited_flights[["flight_id", "manual_required_total", "manual_required_la", "require_supervisor"]],
            on="flight_id", how="left"
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam Hakediş", int(flights["manual_required_total"].sum()))
        c2.metric("LA İhtiyacı", int(flights["manual_required_la"].sum()))
        c3.metric("Supervisor İstenen Uçuş", int(flights["require_supervisor"].sum()))

    with tab_plan:
        st.subheader("Otomatik Uçuş Ekibi Planlama")
        st.caption("Planlama; qualification, rol, vardiya kapsaması, servis uyumu, DO/izin, çakışma ve saat limitlerini birlikte kontrol eder.")
        col_a, col_b = st.columns([0.25, 0.75])
        with col_a:
            run_plan = st.button("Planı Oluştur / Yenile", type="primary", use_container_width=True)
            st.write("Planlama penceresi:")
            st.write(f"STD - {duty_lead} dk → STD + {duty_after} dk")
        if run_plan or st.session_state.manual_plan.empty:
            plan_df, plan_warn = generate_flight_plan(
                flights, staff, shifts, req_norm, alias_dict,
                duty_lead_minutes=int(duty_lead), duty_after_minutes=int(duty_after),
                allow_non_service_shift=allow_non_service,
            )
            st.session_state.manual_plan = plan_df
            st.session_state.plan_warnings = plan_warn

        plan_df = st.session_state.manual_plan.copy()
        plan_warn = st.session_state.get("plan_warnings", pd.DataFrame())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Atanan Görev", len(plan_df))
        c2.metric("Plan Uyarısı", len(plan_warn) if plan_warn is not None else 0)
        c3.metric("Uçuş Kapsanan", plan_df["Uçuş ID"].nunique() if not plan_df.empty else 0)
        c4.metric("Toplam Uçuş", len(flights))

        if plan_warn is not None and not plan_warn.empty:
            with st.expander("Planlama Uyarıları", expanded=True):
                st.dataframe(plan_warn, use_container_width=True)

        st.markdown("### Manuel Görev Düzenleme")
        st.caption("Bazı uçak ekiplerindeki personelin görevini buradan manuel değiştirebilirsin. Değişiklik sonrası alttaki kontrol tablosu uyarı verir.")
        if plan_df.empty:
            st.warning("Plan oluşturulamadı. Kuralları veya dosyaları kontrol et.")
        else:
            editable_plan = plan_df.drop(columns=["staff_id"], errors="ignore")
            st.session_state.manual_plan = st.data_editor(
                editable_plan,
                column_config={
                    "Personel": st.column_config.SelectboxColumn("Personel", options=staff[staff["active"]]["name"].sort_values().tolist()),
                    "Görev Rolü": st.column_config.SelectboxColumn("Görev Rolü", options=ROLE_OPTIONS),
                    "Not": st.column_config.TextColumn("Not", width="medium"),
                },
                num_rows="dynamic",
                use_container_width=True,
                key="manual_plan_editor",
            )
            validation = validate_edited_plan(st.session_state.manual_plan, flights, staff, shifts, req_norm, alias_dict)
            st.markdown("### Manuel Plan Kontrolü")
            if validation.empty or (validation["Durum"] == "OK").all():
                st.success("Manuel plan kontrollerinde kritik uyarı görünmüyor.")
            else:
                st.dataframe(validation, use_container_width=True)

    with tab_delay:
        st.subheader("Gecikme Durumunda AI Devir / Değişiklik Önerisi")
        st.caption("Bu motor, gecikme sonrası görevi uzayan personelin çıkışı veya başka uçuş görevi varsa vardiyada olan uygun personelden devir önerir.")
        if flights.empty:
            st.warning("Uçuş verisi yok.")
        else:
            selected_flight = st.selectbox("Geciken uçuş", flights["flight_id"].tolist())
            delay_min = st.number_input("Gecikme dakikası", min_value=0, max_value=720, value=60, step=5)
            if st.button("AI Devir Önerisi Oluştur", type="primary"):
                rec_df, summary = delay_recommendations(
                    selected_flight, int(delay_min), st.session_state.manual_plan,
                    flights, staff, shifts, req_norm, alias_dict,
                )
                st.session_state.delay_recommendations = rec_df
                st.session_state.delay_summary = summary
            if "delay_summary" in st.session_state:
                st.info(st.session_state.delay_summary)
            if "delay_recommendations" in st.session_state:
                rec = st.session_state.delay_recommendations
                if rec.empty:
                    st.warning("Öneri üretilemedi.")
                else:
                    st.dataframe(rec, use_container_width=True)
                    st.markdown("#### Okuma Mantığı")
                    st.write(
                        "Öneri; aynı uçuş qualification yetkisi, görev rolü, vardiya kapsaması, servis saatine uyum, DO/izin engeli ve mevcut görev çakışmasına göre sıralanır. "
                        "Aynı güzergah varsa öncelik verilir; yoksa servis saatine uyan başka güzergah personeli önerilir."
                    )

    with tab_report:
        st.subheader("Rapor İndir")
        hour_sum = staff_hour_summary(staff, shifts)
        svc_warn = service_warnings(staff, shifts)
        rest_warn = rest_rule_violations(staff, shifts, min_rest)
        validation = validate_edited_plan(st.session_state.manual_plan, flights, staff, shifts, req_norm, alias_dict) if not st.session_state.manual_plan.empty else pd.DataFrame()
        delay_rec = st.session_state.get("delay_recommendations", pd.DataFrame())
        report_sheets = {
            "Ucus Plani": st.session_state.manual_plan,
            "Plan Kontrol": validation,
            "Personel Saat": hour_sum,
            "Servis Uyarilari": svc_warn,
            "Dinlenme Uyarilari": rest_warn,
            "DO Izin Talepleri": st.session_state.request_editor,
            "Ucus Hakedis": flights,
            "Gecikme Onerileri": delay_rec,
        }
        excel_bytes = make_excel_report(report_sheets)
        st.download_button(
            "Excel Raporu İndir",
            data=excel_bytes,
            file_name=f"celebi_yhm_planlama_raporu_{datetime.now():%Y%m%d_%H%M}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        st.markdown("### Rapora girecek tablolar")
        st.write(", ".join(report_sheets.keys()))

    st.caption("Not: Bu uygulama karar destek sistemidir. Operasyonel son kontrol yetkili planlama/supervisor tarafından yapılmalıdır.")


if __name__ == "__main__":
    main()
