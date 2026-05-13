# -*- coding: utf-8 -*-
"""
Çelebi YHM - Yeni Hafta Servis Uyumlu Vardiya ve Uçuş Planlama Sistemi
Tek dosya Streamlit uygulaması.

Çalıştırma:
    streamlit run app.py

Gerekli paketler:
    streamlit pandas numpy openpyxl xlsxwriter
"""

from __future__ import annotations

import base64
import re
import unicodedata
from datetime import datetime, date, time, timedelta
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import streamlit as st

# =========================================================
# 1) SABİTLER
# =========================================================
APP_TITLE = "Çelebi YHM Yeni Hafta Planlama"
APP_VERSION = "v5.1 Direkt Kod - Yeni Hafta + Servis Min 4 + Lacivert Tema"

ADMIN_USERS = {
    "YHMADMIN": "1234",
}

ARRIVAL_SERVICES = ["02:30", "04:30", "06:30", "08:00", "10:00", "11:30", "14:00", "16:30", "20:00", "23:59"]
DEPARTURE_SERVICES = ["00:30", "02:30", "04:30", "08:30", "14:30", "17:00", "19:30", "20:30", "23:00"]
BASE_ROUTES = ["ARN", "ATS", "AVC", "BAG", "BAH", "BHC", "BAY", "BEY", "BOL", "ESY", "HAL", "MAG", "SEF", "SUL", "AKZ"]
POOL_AIRCRAFT_CODES = ["UZB", "IAW", "DAH", "FAD", "RAM", "BRU", "AWG"]
ROLE_OPTIONS = ["Agent", "LA", "Supervisor"]
MIN_ROUTE_SERVICE_COUNT = 4
READY_BEFORE_STD_MIN = 190     # STD'den 3 saat 10 dk önce hazır
AVAILABLE_AFTER_STD_MIN = 20   # STD + 20 dk sonra başka göreve başlayabilir
FULL_TIME_MIN_HOURS = 40
FULL_TIME_MAX_HOURS = 50
PART_TIME_MAX_HOURS = 25
MIN_REST_HOURS = 11
BREAK_THRESHOLD_HOURS = 6
BREAK_HOURS = 1

LOCAL_ASSET_DIR = Path(__file__).parent / "assets"
PLANE_ASSET_FILES = [
    "luftansha_transparent.png",
    "uzb_transparent.png",
    "sv_transparent.png",
    "etihad_transparent.png",
    "emirates_transparent.png",
]

AIRLINE_ALIASES: Dict[str, List[str]] = {
    "AEE": ["AEE", "AEGEAN"],
    "AHY": ["AHY"],
    "AAR": ["AAR"],
    "ABY": ["ABY", "AIR ARABIA", "ARABIA"],
    "AWG": ["AWG", "ANIMAWINGS"],
    "BRU": ["BRU"],
    "CES": ["CES", "CHINA EASTERN", "MU"],
    "CSN": ["CSN", "CHINA SOUTHERN", "CZ"],
    "CCA": ["CCA", "AIR CHINA", "AIRCHINA", "CA"],
    "CSC": ["CSC", "SICHUAN", "3U"],
    "DAH": ["DAH", "AIR ALGERIE"],
    "DLH": ["DLH", "LH", "LUFTHANSA"],
    "ETD": ["ETD", "EY", "ETIHAD", "UAE"],
    "FAD": ["FAD"],
    "IAW": ["IAW", "IRAQ", "IRAK"],
    "KAC": ["KAC", "KUWAIT", "KUVEYT"],
    "KAL": ["KAL"],
    "KZR": ["KZR"],
    "RAM": ["RAM", "ROYAL AIR MAROC"],
    "SVA": ["SVA", "SAUDI", "SAUDIA"],
    "TRF": ["TRF"],
    "UBD": ["UBD"],
    "UZB": ["UZB", "UZBEKISTAN"],
    "VSV": ["VSV", "SCAT"],
}

ALIAS_TO_CODE: Dict[str, str] = {}
for code, aliases in AIRLINE_ALIASES.items():
    for a in aliases:
        ALIAS_TO_CODE[a] = code

# =========================================================
# 2) GENEL YARDIMCI FONKSİYONLAR
# =========================================================
def norm_text(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip().upper()
    tr_map = str.maketrans("İIĞÜŞÖÇıiğüşöç", "IIGUSOCIIGUSOC")
    s = s.translate(tr_map)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def clean_name(ad, soyad="") -> str:
    return re.sub(r"\s+", " ", f"{str(ad).strip()} {str(soyad).strip()}".strip()).upper()


def parse_time_token(x) -> Optional[time]:
    if x is None or pd.isna(x):
        return None
    if isinstance(x, time):
        return x
    if isinstance(x, datetime):
        return x.time().replace(second=0, microsecond=0)
    s = str(x).strip()
    m = re.search(r"(\d{1,2})[:.](\d{2})", s)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return time(h, mn)
    m = re.search(r"\b(\d{4})\b", s)
    if m:
        raw = m.group(1)
        h, mn = int(raw[:2]), int(raw[2:])
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return time(h, mn)
    return None


def to_datetime_safe(x) -> pd.Timestamp:
    if pd.isna(x):
        return pd.NaT
    return pd.to_datetime(x, dayfirst=True, errors="coerce")


def hours_between(start_dt, end_dt, break_threshold=BREAK_THRESHOLD_HOURS, break_hours=BREAK_HOURS) -> float:
    if pd.isna(start_dt) or pd.isna(end_dt):
        return 0.0
    h = (pd.Timestamp(end_dt) - pd.Timestamp(start_dt)).total_seconds() / 3600
    if h < 0:
        h += 24
    if h >= break_threshold:
        h -= break_hours
    return round(max(h, 0), 2)


def read_any_table(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.DataFrame()
    name = uploaded_file.name.lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            # İçinde personel sheet'i varsa onu seç; yoksa ilk sheet.
            xl = pd.ExcelFile(uploaded_file)
            preferred = None
            for s in xl.sheet_names:
                ss = norm_text(s)
                if "20" in ss and "HAFTA" in ss and "DEPARTURE" not in ss:
                    preferred = s
                    break
            if preferred is None:
                preferred = xl.sheet_names[0]
            return pd.read_excel(uploaded_file, sheet_name=preferred)
        for enc in ["utf-8-sig", "cp1254", "latin1"]:
            try:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, encoding=enc, sep=None, engine="python")
            except Exception:
                continue
    except Exception as e:
        st.error(f"Dosya okunamadı: {e}")
    return pd.DataFrame()


def read_excel_sheet_by_keyword(uploaded_file, keyword: str) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.DataFrame()
    try:
        xl = pd.ExcelFile(uploaded_file)
        selected = xl.sheet_names[0]
        for s in xl.sheet_names:
            if keyword in norm_text(s):
                selected = s
                break
        return pd.read_excel(uploaded_file, sheet_name=selected)
    except Exception:
        return read_any_table(uploaded_file)


def find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    normalized = {norm_text(c): c for c in df.columns}
    for cand in candidates:
        nc = norm_text(cand)
        if nc in normalized:
            return normalized[nc]
    for c in df.columns:
        nc = norm_text(c)
        for cand in candidates:
            if norm_text(cand) in nc:
                return c
    return None


def code_from_airline(raw) -> str:
    s = norm_text(raw)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    parts = [p for p in s.split() if p]
    for p in parts + [s]:
        if p in ALIAS_TO_CODE:
            return ALIAS_TO_CODE[p]
    if len(s) >= 3:
        return s[:3]
    return s


def parse_pax_number(x) -> int:
    if pd.isna(x):
        return 0
    nums = [int(n) for n in re.findall(r"\d+", str(x))]
    if not nums:
        return 0
    return max(nums)


def required_staff_guess(code: str, pax: int, ac_type: str = "") -> int:
    # Hakediş dosyası karışık gelirse çalışsın diye basit operasyon kuralı.
    code = code_from_airline(code)
    pax = int(pax or 0)
    if code == "SVA":
        if pax >= 300: return 18
        if pax >= 200: return 14
        if pax >= 150: return 10
        return 6
    if code in ["UZB", "CES", "CSN", "CCA", "CSC"]:
        if pax >= 200: return 7
        if pax >= 150: return 5
        return 4
    if code in ["AEE", "AAR", "ABY", "AHY", "DLH", "ETD", "KAC", "DAH", "RAM", "BRU", "AWG", "IAW", "FAD"]:
        if pax >= 160: return 5
        if pax >= 120: return 4
        if pax >= 60: return 3
        return 2
    return 4


def data_uri_from_file(path: Path) -> str:
    if not path.exists():
        return ""
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    data = path.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

# =========================================================
# 3) CSS VE GÖRSEL ARAYÜZ
# =========================================================
def inject_css():
    st.markdown(
        """
        <style>
        :root {--navy:#07182f;--navy2:#0d2b52;--blue:#163e73;--white:#fff;--soft:#f5f8fc;--text:#07182f;--muted:#526070;}
        html, body, [data-testid="stAppViewContainer"] {
            background: radial-gradient(circle at 15% 12%, rgba(13,43,82,.10) 0, rgba(13,43,82,0) 25%),
                        radial-gradient(circle at 85% 18%, rgba(22,62,115,.10) 0, rgba(22,62,115,0) 26%),
                        linear-gradient(135deg, #ffffff 0%, #f5f8fc 55%, #e8eef6 100%) !important;
            color:var(--text) !important;
        }
        .main .block-container {padding-top:1rem; max-width:1480px; position:relative; z-index:2;}
        .main .block-container, .main .block-container p, .main .block-container span, .main .block-container label,
        .main .block-container div, .main .block-container h1, .main .block-container h2, .main .block-container h3 {color:var(--text) !important;}
        [data-testid="stSidebar"] {background:linear-gradient(180deg,#07182f 0%,#0d2b52 76%,#081120 100%) !important;}
        [data-testid="stSidebar"] * {color:#fff !important;}
        [data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea {color:#07182f !important;}
        .sky-layer {position:fixed; inset:0; pointer-events:none; overflow:hidden; z-index:1;}
        .flying-plane {position:absolute; width:min(390px,35vw); opacity:.20; object-fit:contain; filter:drop-shadow(0 16px 22px rgba(7,24,47,.20)); animation-timing-function:linear; animation-iteration-count:infinite;}
        .plane-one {top:7%; animation:fly-ltr 42s linear infinite; animation-delay:-8s;}
        .plane-two {top:30%; width:min(460px,40vw); animation:fly-rtl 52s linear infinite; animation-delay:-18s;}
        .plane-three {top:54%; width:min(400px,36vw); animation:fly-ltr 46s linear infinite; animation-delay:-4s;}
        .plane-four {top:73%; width:min(470px,42vw); animation:fly-rtl 58s linear infinite; animation-delay:-30s;}
        .plane-five {top:18%; width:min(430px,38vw); animation:fly-ltr 61s linear infinite; animation-delay:-35s;}
        @keyframes fly-ltr {0%{left:-45vw;transform:translateY(0) rotate(-2deg);}50%{transform:translateY(-18px) rotate(1.5deg);}100%{left:118vw;transform:translateY(10px) rotate(-1deg);}}
        @keyframes fly-rtl {0%{right:-48vw;transform:scaleX(-1) translateY(0) rotate(-1deg);}50%{transform:scaleX(-1) translateY(18px) rotate(1.5deg);}100%{right:118vw;transform:scaleX(-1) translateY(-8px) rotate(-1deg);}}
        .glass-panel {background:rgba(255,255,255,.86); border:1px solid rgba(7,24,47,.14); box-shadow:0 18px 45px rgba(7,24,47,.10); backdrop-filter:blur(14px); border-radius:24px; padding:24px;}
        .hero {background:linear-gradient(135deg,rgba(7,24,47,.96),rgba(13,43,82,.94)); border-radius:30px; padding:34px; box-shadow:0 24px 60px rgba(7,24,47,.24);}
        .hero h1,.hero p,.hero b {color:white !important;}.hero h1{font-size:46px;line-height:1.05;margin:12px 0;letter-spacing:-.04em}.hero p{color:rgba(255,255,255,.78)!important;font-size:17px;line-height:1.65;}
        .pill {display:inline-flex; padding:8px 13px; border-radius:999px; background:#fff; color:#07182f!important; font-size:12px; font-weight:900; letter-spacing:.08em;}
        .landing-shell {display:grid; grid-template-columns:1.2fr .8fr; gap:24px; align-items:stretch; position:relative; z-index:2; padding-top:20px;}
        .landing-title {font-size:58px; line-height:1.02; letter-spacing:-.055em; margin:0 0 18px; color:#07182f!important;}.landing-title span{color:#163e73!important;}
        .landing-text {color:#526070!important; font-size:18px; line-height:1.7; max-width:820px;}
        .feature-grid {display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; margin-top:28px;}
        .feature-card {padding:18px; border-radius:20px; background:#fff; border:1px solid rgba(7,24,47,.12); box-shadow:0 12px 28px rgba(7,24,47,.06);}
        .feature-card b{display:block;margin-bottom:6px;color:#07182f!important}.feature-card span{color:#526070!important;font-size:14px;line-height:1.45;}
        .tower {padding:32px; border-radius:24px; background:linear-gradient(180deg,#07182f 0%,#0d2b52 100%); color:#fff!important;}.tower *{color:#fff!important;}
        .mini-stat {display:flex; align-items:center; justify-content:space-between; padding:15px 0; border-bottom:1px solid rgba(255,255,255,.12);}.mini-stat small{color:rgba(255,255,255,.70)!important}.mini-stat strong{font-size:22px;}
        div[data-testid="metric-container"] {background:rgba(255,255,255,.90); border:1px solid rgba(7,24,47,.12); border-radius:20px; padding:18px; box-shadow:0 12px 28px rgba(7,24,47,.07);} div[data-testid="metric-container"] *{color:#07182f!important;}
        .stButton>button {border-radius:16px!important; border:1px solid rgba(7,24,47,.22)!important; background:#fff!important; color:#07182f!important; font-weight:800!important;}
        .stButton>button[kind="primary"] {background:#07182f!important; color:#fff!important; border:1px solid #07182f!important;}
        [data-testid="stDataFrame"] {background:white!important; border-radius:18px!important; border:1px solid rgba(7,24,47,.12)!important; overflow:hidden!important;} [data-testid="stDataFrame"] *{color:#07182f!important;}
        .stTabs [data-baseweb="tab"] {background:#fff; border:1px solid rgba(7,24,47,.14); border-radius:14px; color:#07182f!important; font-weight:700;} .stTabs [aria-selected="true"]{background:#07182f!important;color:#fff!important}.stTabs [aria-selected="true"] *{color:#fff!important;}
        @media(max-width:1000px){.landing-shell{grid-template-columns:1fr}.landing-title{font-size:40px}.feature-grid{grid-template-columns:1fr}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_flying_background():
    html = '<div class="sky-layer" aria-hidden="true">'
    for i, fn in enumerate(PLANE_ASSET_FILES, start=1):
        uri = data_uri_from_file(LOCAL_ASSET_DIR / fn)
        if uri:
            html += f'<img class="flying-plane plane-{["one","two","three","four","five"][i-1]}" src="{uri}" />'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def logo_html(width=190) -> str:
    uri = data_uri_from_file(LOCAL_ASSET_DIR / "celebi_logo.png")
    if not uri:
        uri = data_uri_from_file(LOCAL_ASSET_DIR / "celebi_logo.png.png")
    if uri:
        return f'<img src="{uri}" style="max-width:{width}px;margin-bottom:22px;" />'
    return '<div style="font-weight:900;font-size:30px;letter-spacing:.08em;color:#07182f;">ÇELEBİ</div>'

# =========================================================
# 4) DOSYA PARSE FONKSİYONLARI
# =========================================================
def parse_flights(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    al_col = find_col(df, ["A/L", "AL", "AIRLINE", "HAVAYOLU"])
    in_col = find_col(df, ["IN", "ARR", "ARRIVAL"])
    out_col = find_col(df, ["OUT", "DEP", "DEPARTURE", "FLT"])
    sta_col = find_col(df, ["STA"])
    std_col = find_col(df, ["STD", "KALKIŞ", "KALKIS"])
    ac_col = find_col(df, ["A/C TYPE", "A/C\nTYPE", "TYPE", "UCAK TIPI"])
    pax_col = find_col(df, ["PAX", "YOLCU", "CAPACITY", "KAPASITE", "UNNAMED: 9"])

    rows = []
    current_day = ""
    for idx, r in df.iterrows():
        al = r.get(al_col, "") if al_col else ""
        std = to_datetime_safe(r.get(std_col, pd.NaT)) if std_col else pd.NaT
        if pd.isna(std) or not str(al).strip():
            continue
        day_raw = r.iloc[0] if len(r) else ""
        if str(day_raw).strip() and "NAN" not in norm_text(day_raw):
            current_day = str(day_raw).strip()
        code = code_from_airline(al)
        out_no = str(r.get(out_col, "")).strip() if out_col else ""
        in_no = str(r.get(in_col, "")).strip() if in_col else ""
        pax_detail = r.get(pax_col, "") if pax_col else ""
        pax = parse_pax_number(pax_detail)
        req = required_staff_guess(code, pax, str(r.get(ac_col, "")) if ac_col else "")
        rows.append({
            "flight_id": f"{idx+1:03d}-{code}-{out_no or std.strftime('%H%M')}",
            "Gün": current_day,
            "Tarih": std.date(),
            "A/L": code,
            "IN": in_no,
            "OUT": out_no,
            "STA": to_datetime_safe(r.get(sta_col, pd.NaT)) if sta_col else pd.NaT,
            "STD": std.to_pydatetime(),
            "A/C Type": str(r.get(ac_col, "")).strip() if ac_col else "",
            "Pax/Kapasite": str(pax_detail),
            "Tahmini Yolcu": pax,
            "Hakediş": req,
            "Hazır Olma": (std - pd.Timedelta(minutes=READY_BEFORE_STD_MIN)).to_pydatetime(),
            "Görev Bitiş": (std + pd.Timedelta(minutes=AVAILABLE_AFTER_STD_MIN)).to_pydatetime(),
        })
    return pd.DataFrame(rows).sort_values("STD").reset_index(drop=True)


def parse_qualification_token(token: str) -> Tuple[str, str]:
    t = norm_text(token).replace(" ", "")
    if not t:
        return "", "Agent"
    role = "Agent"
    if re.search(r"(^S[-_])|([-_]S$)|(SPV|SUP|SUPERVISOR)", t):
        role = "Supervisor"
    elif re.search(r"(^L[-_])|([-_]L$)|(LA$)|(^LA)", t):
        role = "LA"
    t = re.sub(r"(^S[-_])|([-_]S$)|(^L[-_])|([-_]L$)|SPV|SUPERVISOR|SUP", "", t)
    t = t.replace("LA", "") if len(t) > 3 else t
    code = code_from_airline(t)
    return code, role


def parse_qualifications(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Dict[str, str]]]:
    if df.empty:
        return pd.DataFrame(), {}
    ad_col = find_col(df, ["AD", "NAME", "ISIM"])
    soyad_col = find_col(df, ["SOYAD", "SURNAME"])
    q_col = find_col(df, ["QUALIFICATIONS", "YETKINLIK", "YETKİNLİK"])
    people = []
    qmap: Dict[str, Dict[str, str]] = {}
    for _, r in df.iterrows():
        name = clean_name(r.get(ad_col, ""), r.get(soyad_col, "")) if ad_col else ""
        if not name:
            continue
        raw = str(r.get(q_col, "")) if q_col else ""
        tokens = re.split(r"[-;,/]+", raw.replace("--", "-"))
        qual_dict: Dict[str, str] = {}
        for tok in tokens:
            code, role = parse_qualification_token(tok)
            if not code or code in ["GATE", "COCO", "INT", "TRN", "DEPORTE", "IME", "CIN"]:
                continue
            old = qual_dict.get(code, "Agent")
            if role == "Supervisor" or old == "Supervisor":
                qual_dict[code] = "Supervisor"
            elif role == "LA" or old == "LA":
                qual_dict[code] = "LA"
            else:
                qual_dict[code] = "Agent"
        qmap[name] = qual_dict
        base_role = "Supervisor" if any(v == "Supervisor" for v in qual_dict.values()) else ("LA" if any(v == "LA" for v in qual_dict.values()) else "Agent")
        people.append({"Personel": name, "Base Rol": base_role, "Qualification": ", ".join(sorted(qual_dict.keys()))})
    return pd.DataFrame(people), qmap


def parse_staff_master(shift_df: pd.DataFrame, qual_people: pd.DataFrame, qmap: Dict[str, Dict[str, str]]) -> pd.DataFrame:
    rows = []
    if not shift_df.empty:
        ad_col = find_col(shift_df, ["AD"])
        soyad_col = find_col(shift_df, ["SOYAD"])
        mail_col = find_col(shift_df, ["MAIL", "EMAIL"])
        type_col = find_col(shift_df, ["FULL/PART", "FULL", "PART"])
        route_col = find_col(shift_df, ["GÜZERGAH", "GUZERGAH", "SERVIS"])
        qual_col = find_col(shift_df, ["QUALIFICATIONS"])
        for _, r in shift_df.iterrows():
            name = clean_name(r.get(ad_col, ""), r.get(soyad_col, "")) if ad_col else ""
            if not name:
                continue
            fp = str(r.get(type_col, "45")).strip() if type_col else "45"
            staff_type = "Part-Time" if any(x in norm_text(fp) for x in ["PART", "PT", "25"]) else "Full-Time"
            route = norm_text(r.get(route_col, "")) if route_col else ""
            if not route:
                route = "TANIMSIZ"
            qual_text = str(r.get(qual_col, "")) if qual_col else ""
            role = "Supervisor" if "SEF" in norm_text(qual_text) or "SUP" in norm_text(qual_text) else "Agent"
            qd = qmap.get(name, {})
            if qd:
                role = "Supervisor" if any(v == "Supervisor" for v in qd.values()) else ("LA" if any(v == "LA" for v in qd.values()) else role)
            rows.append({
                "staff_id": f"S{len(rows)+1:04d}",
                "Personel": name,
                "Mail": str(r.get(mail_col, "")).strip() if mail_col else "",
                "Tip": staff_type,
                "Güzergah": route,
                "Base Rol": role,
                "Aktif": True,
                "Qualification": ", ".join(sorted(qd.keys())),
            })
    # Qualification dosyasında olup 20. hafta master'da olmayanları da ekle.
    existing = {r["Personel"] for r in rows}
    if qual_people is not None and not qual_people.empty:
        for _, r in qual_people.iterrows():
            name = r["Personel"]
            if name not in existing:
                rows.append({
                    "staff_id": f"S{len(rows)+1:04d}", "Personel": name, "Mail": "", "Tip": "Full-Time",
                    "Güzergah": "TANIMSIZ", "Base Rol": r.get("Base Rol", "Agent"), "Aktif": True,
                    "Qualification": r.get("Qualification", ""),
                })
    return pd.DataFrame(rows)

# =========================================================
# 5) SERVİS VE PLANLAMA MOTORU
# =========================================================
def service_datetime_candidates(anchor: datetime, service_list: List[str]) -> List[datetime]:
    candidates = []
    for offset in [-1, 0, 1]:
        base_date = anchor.date() + timedelta(days=offset)
        for s in service_list:
            t = parse_time_token(s)
            if t:
                candidates.append(datetime.combine(base_date, t))
    return sorted(candidates)


def snap_to_arrival_service(required_start: datetime) -> datetime:
    candidates = [x for x in service_datetime_candidates(required_start, ARRIVAL_SERVICES) if x <= required_start]
    return max(candidates) if candidates else required_start


def snap_to_departure_service(required_end: datetime) -> datetime:
    candidates = [x for x in service_datetime_candidates(required_end, DEPARTURE_SERVICES) if x >= required_end]
    return min(candidates) if candidates else required_end


def staff_can_do_flight(staff_name: str, base_role: str, flight_code: str, qmap: Dict[str, Dict[str, str]]) -> Tuple[bool, str]:
    code = code_from_airline(flight_code)
    if code in POOL_AIRCRAFT_CODES:
        return True, base_role
    qd = qmap.get(staff_name, {})
    if code in qd:
        return True, qd[code]
    return False, ""


def role_score(role: str) -> int:
    return {"Supervisor": 3, "LA": 2, "Agent": 1}.get(role, 0)


def overlaps(a_start, a_end, b_start, b_end) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def generate_new_week_plan(flights: pd.DataFrame, staff: pd.DataFrame, qmap: Dict[str, Dict[str, str]], do_requests: List[str], leave_people: List[str], manual_need: Dict[str, int]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if flights.empty or staff.empty:
        return pd.DataFrame(), pd.DataFrame()

    assigned_intervals: Dict[str, List[Tuple[datetime, datetime, str]]] = {n: [] for n in staff["Personel"]}
    total_hours: Dict[str, float] = {n: 0.0 for n in staff["Personel"]}
    plan_rows = []
    diag_rows = []
    blocked = set(do_requests or []) | set(leave_people or [])

    active_staff = staff[(staff["Aktif"] == True) & (~staff["Personel"].isin(blocked))].copy()

    for _, f in flights.sort_values("STD").iterrows():
        fid = f["flight_id"]
        code = f["A/L"]
        duty_start = pd.Timestamp(f["Hazır Olma"]).to_pydatetime()
        duty_end = pd.Timestamp(f["Görev Bitiş"]).to_pydatetime()
        need = int(manual_need.get(fid, f.get("Hakediş", 4)))
        need = max(1, need)

        candidates = []
        for _, s in active_staff.iterrows():
            name = s["Personel"]
            ok, duty_role = staff_can_do_flight(name, s["Base Rol"], code, qmap)
            if not ok:
                continue
            # Çakışma kontrolü
            conflict = any(overlaps(duty_start, duty_end, a, b) for a, b, _ in assigned_intervals.get(name, []))
            if conflict:
                continue
            # 11 saat dinlenme: bir önceki blok bitişi ile yeni blok başlangıcı arasında
            rest_ok = True
            for a, b, _ in assigned_intervals.get(name, []):
                gap = (duty_start - b).total_seconds() / 3600
                if b <= duty_start and gap < MIN_REST_HOURS:
                    # Aynı gün üst üste uçak devri olabilir; bu durumda çakışmıyorsa tek vardiya içinde kabul edilir.
                    if duty_start.date() != b.date():
                        rest_ok = False
                elif a >= duty_end:
                    gap2 = (a - duty_end).total_seconds() / 3600
                    if gap2 < MIN_REST_HOURS and a.date() != duty_end.date():
                        rest_ok = False
            if not rest_ok:
                continue
            limit = PART_TIME_MAX_HOURS if s["Tip"] == "Part-Time" else FULL_TIME_MAX_HOURS
            estimated_add = hours_between(snap_to_arrival_service(duty_start), snap_to_departure_service(duty_end))
            if total_hours[name] + estimated_add > limit + 2:
                continue
            candidates.append({
                "Personel": name,
                "Güzergah": s["Güzergah"],
                "Tip": s["Tip"],
                "Base Rol": s["Base Rol"],
                "Görev Rolü": duty_role if duty_role else s["Base Rol"],
                "score": role_score(duty_role if duty_role else s["Base Rol"]),
                "hours": total_hours[name],
            })

        cdf = pd.DataFrame(candidates)
        diag_rows.append({
            "Tarih": f["Tarih"], "STD": f["STD"], "Uçuş": f["OUT"], "A/L": code, "Hakediş": need,
            "Aday": len(cdf),
            "Supervisor Adayı": int((cdf["Görev Rolü"].eq("Supervisor")).sum()) if not cdf.empty else 0,
            "LA Adayı": int((cdf["Görev Rolü"].eq("LA")).sum()) if not cdf.empty else 0,
            "Havuz": "Evet" if code in POOL_AIRCRAFT_CODES else "Hayır",
        })
        if cdf.empty:
            continue

        selected = []
        # Her uçuşta en az 1 supervisor; havuz uçaklarında da bu şart var.
        spv = cdf[cdf["Görev Rolü"].eq("Supervisor")].sort_values(["hours", "score"], ascending=[True, False])
        if not spv.empty:
            selected.append(spv.iloc[0].to_dict())
        remaining = cdf[~cdf["Personel"].isin([x["Personel"] for x in selected])]
        # LA varsa bir tane al, ama havuz uçaklarda zorunlu değil.
        if code not in POOL_AIRCRAFT_CODES and len(selected) < need:
            la = remaining[remaining["Görev Rolü"].eq("LA")].sort_values(["hours", "score"], ascending=[True, False])
            if not la.empty:
                selected.append(la.iloc[0].to_dict())
                remaining = remaining[~remaining["Personel"].isin([x["Personel"] for x in selected])]
        remaining = remaining.sort_values(["hours", "score"], ascending=[True, False])
        for _, rr in remaining.iterrows():
            if len(selected) >= need:
                break
            selected.append(rr.to_dict())

        for person in selected:
            name = person["Personel"]
            assigned_intervals[name].append((duty_start, duty_end, fid))
            total_hours[name] += hours_between(snap_to_arrival_service(duty_start), snap_to_departure_service(duty_end))
            plan_rows.append({
                "Tarih": f["Tarih"],
                "Gün": f["Gün"],
                "A/L": code,
                "IN": f["IN"],
                "OUT": f["OUT"],
                "STD": f["STD"],
                "Hazır Olma": duty_start,
                "Görev Bitiş": duty_end,
                "flight_id": fid,
                "Personel": name,
                "Görev Rolü": person["Görev Rolü"],
                "Güzergah": person["Güzergah"],
                "Tip": person["Tip"],
                "Not": "Havuz uçak" if code in POOL_AIRCRAFT_CODES else "Qualification uygun",
            })

    return pd.DataFrame(plan_rows), pd.DataFrame(diag_rows)


def build_shift_plan_from_assignments(plan: pd.DataFrame, staff: pd.DataFrame) -> pd.DataFrame:
    if plan.empty:
        return pd.DataFrame()
    rows = []
    staff_info = staff.set_index("Personel").to_dict("index") if not staff.empty else {}
    for name, g in plan.groupby("Personel"):
        intervals = sorted([(pd.Timestamp(r["Hazır Olma"]).to_pydatetime(), pd.Timestamp(r["Görev Bitiş"]).to_pydatetime(), r["OUT"]) for _, r in g.iterrows()], key=lambda x: x[0])
        blocks = []
        for duty_start, duty_end, out_no in intervals:
            service_start = snap_to_arrival_service(duty_start)
            service_end = snap_to_departure_service(duty_end)
            if not blocks:
                blocks.append({"start": service_start, "end": service_end, "duties": [out_no]})
                continue
            last = blocks[-1]
            gap = (service_start - last["end"]).total_seconds() / 3600
            if service_start <= last["end"] or gap < MIN_REST_HOURS:
                last["end"] = max(last["end"], service_end)
                last["duties"].append(out_no)
            else:
                blocks.append({"start": service_start, "end": service_end, "duties": [out_no]})
        for b in blocks:
            info = staff_info.get(name, {})
            rows.append({
                "Personel": name,
                "Tarih": b["start"].date(),
                "Vardiya Giriş": b["start"],
                "Vardiya Çıkış": b["end"],
                "Geliş Servisi": b["start"].strftime("%H:%M"),
                "Gidiş Servisi": b["end"].strftime("%H:%M"),
                "Güzergah": info.get("Güzergah", ""),
                "Tip": info.get("Tip", ""),
                "Net Çalışma Saati": hours_between(b["start"], b["end"]),
                "Uçuşlar": ", ".join(map(str, b["duties"])),
            })
    return pd.DataFrame(rows).sort_values(["Tarih", "Vardiya Giriş", "Personel"]).reset_index(drop=True)


def build_service_plan(shift_plan: pd.DataFrame) -> pd.DataFrame:
    if shift_plan.empty:
        return pd.DataFrame()
    rows = []
    for _, r in shift_plan.iterrows():
        rows.append({"Tip": "Geliş", "Tarih": r["Vardiya Giriş"].date(), "Saat": r["Geliş Servisi"], "Güzergah": r["Güzergah"], "Personel": r["Personel"]})
        rows.append({"Tip": "Gidiş", "Tarih": r["Vardiya Çıkış"].date(), "Saat": r["Gidiş Servisi"], "Güzergah": r["Güzergah"], "Personel": r["Personel"]})
    raw = pd.DataFrame(rows)
    grouped = raw.groupby(["Tip", "Tarih", "Saat", "Güzergah"], dropna=False).agg(
        **{"Kişi Sayısı": ("Personel", "nunique"), "Personeller": ("Personel", lambda x: ", ".join(sorted(set(map(str, x)))))}
    ).reset_index()
    grouped["Min Kişi"] = MIN_ROUTE_SERVICE_COUNT
    grouped["Servis Durumu"] = np.where(grouped["Kişi Sayısı"] >= MIN_ROUTE_SERVICE_COUNT, "Servis Çıkar", "Servis Çıkmaz - 4 kişi altı")
    grouped["Öneri"] = np.where(grouped["Kişi Sayısı"] >= MIN_ROUTE_SERVICE_COUNT, "Uygun", "Aynı güzergah ve aynı servis saatinde en az 4 kişi tamamlanmalı.")
    return grouped.sort_values(["Tarih", "Tip", "Saat", "Güzergah"]).reset_index(drop=True)


def build_daily_flight_view(plan: pd.DataFrame) -> pd.DataFrame:
    if plan.empty:
        return pd.DataFrame()
    return plan.groupby(["Tarih", "Gün", "STD", "A/L", "OUT"], dropna=False).agg(
        **{
            "Ekip Sayısı": ("Personel", "nunique"),
            "Supervisor": ("Personel", lambda x: ", ".join(plan.loc[x.index][plan.loc[x.index, "Görev Rolü"].eq("Supervisor")]["Personel"].tolist())),
            "LA": ("Personel", lambda x: ", ".join(plan.loc[x.index][plan.loc[x.index, "Görev Rolü"].eq("LA")]["Personel"].tolist())),
            "Tüm Ekip": ("Personel", lambda x: ", ".join(map(str, x))),
        }
    ).reset_index().sort_values(["Tarih", "STD"])


def validate_weekly_hours(shift_plan: pd.DataFrame, staff: pd.DataFrame) -> pd.DataFrame:
    if shift_plan.empty:
        return pd.DataFrame()
    weekly = shift_plan.groupby("Personel")["Net Çalışma Saati"].sum().reset_index()
    weekly = weekly.merge(staff[["Personel", "Tip", "Güzergah"]], on="Personel", how="left")
    def status(r):
        if r["Tip"] == "Part-Time" and r["Net Çalışma Saati"] > PART_TIME_MAX_HOURS:
            return "Part-Time 25 saat üstü"
        if r["Tip"] == "Full-Time" and r["Net Çalışma Saati"] > FULL_TIME_MAX_HOURS:
            return "Full-Time 50 saat üstü"
        if r["Tip"] == "Full-Time" and r["Net Çalışma Saati"] < FULL_TIME_MIN_HOURS:
            return "Full-Time 40 saat altı"
        return "OK"
    weekly["Durum"] = weekly.apply(status, axis=1)
    return weekly.sort_values(["Durum", "Net Çalışma Saati"], ascending=[True, False])


def ai_delay_advisor(plan: pd.DataFrame, shift_plan: pd.DataFrame, staff: pd.DataFrame, qmap: Dict[str, Dict[str, str]], selected_out: str, delay_min: int) -> pd.DataFrame:
    if plan.empty or not selected_out:
        return pd.DataFrame()
    affected = plan[plan["OUT"].astype(str).eq(str(selected_out))].copy()
    if affected.empty:
        return pd.DataFrame()
    f = affected.iloc[0]
    code = f["A/L"]
    new_end = pd.Timestamp(f["Görev Bitiş"]) + pd.Timedelta(minutes=delay_min)
    current_team = set(affected["Personel"])
    suggestions = []
    for _, s in staff[staff["Aktif"] == True].iterrows():
        name = s["Personel"]
        if name in current_team:
            continue
        ok, role = staff_can_do_flight(name, s["Base Rol"], code, qmap)
        if not ok:
            continue
        person_shifts = shift_plan[shift_plan["Personel"].eq(name)] if not shift_plan.empty else pd.DataFrame()
        available = True
        reason = "Boşta görünüyor"
        for _, sh in person_shifts.iterrows():
            if overlaps(pd.Timestamp(f["Hazır Olma"]), new_end, pd.Timestamp(sh["Vardiya Giriş"]), pd.Timestamp(sh["Vardiya Çıkış"])):
                available = False
                reason = "Vardiyası/görevi çakışıyor"
                break
        if available:
            suggestions.append({
                "Önerilen Personel": name,
                "Rol": role or s["Base Rol"],
                "Güzergah": s["Güzergah"],
                "Uygunluk": reason,
                "AI Önerisi": f"{selected_out} gecikirse {name} görevi devralabilir. Rol: {role or s['Base Rol']}."
            })
    return pd.DataFrame(suggestions).sort_values("Rol", ascending=False).head(20)


def export_excel(plan, daily, shifts, services, validation, diagnostics) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        plan.to_excel(writer, index=False, sheet_name="Ucus Plani Detay")
        daily.to_excel(writer, index=False, sheet_name="Gunluk Ucus Ekipleri")
        shifts.to_excel(writer, index=False, sheet_name="Yeni Hafta Vardiya")
        services.to_excel(writer, index=False, sheet_name="Servis Plani")
        validation.to_excel(writer, index=False, sheet_name="Saat Kontrol")
        diagnostics.to_excel(writer, index=False, sheet_name="Aday Diagnostik")
    return output.getvalue()

# =========================================================
# 6) SAYFALAR
# =========================================================
def login_screen():
    render_flying_background()
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown('<div class="glass-panel" style="text-align:center;margin-top:70px;">' + logo_html(210) + '</div>', unsafe_allow_html=True)
        st.markdown("### Yetkili Giriş")
        uid = st.text_input("Kullanıcı ID")
        pwd = st.text_input("Şifre", type="password")
        if st.button("Giriş Yap", type="primary", use_container_width=True):
            if ADMIN_USERS.get(uid) == pwd:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Kullanıcı ID veya şifre hatalı.")
        st.caption("Varsayılan: YHMADMIN / 1234")


def home_page():
    render_flying_background()
    st.markdown(
        f"""
        <div class="landing-shell">
          <div class="glass-panel">
            {logo_html(220)}
            <div class="pill">{APP_VERSION}</div>
            <h1 class="landing-title">Yeni Hafta <span>Vardiya</span> ve Servis Planlama</h1>
            <p class="landing-text">Bu sistem eski haftayı raporlamak için değil; DEPARTURE dosyasındaki yeni uçuşlara göre personelin hangi gün kaçta gireceğini, kaçta çıkacağını, hangi servisle gelip gideceğini ve hangi uçağa çıkacağını planlamak için tasarlanmıştır.</p>
            <div class="feature-grid">
              <div class="feature-card"><b>Servis Min 4 Kuralı</b><span>Aynı güzergah ve aynı servis saatinde en az 4 kişi yoksa sistem servis çıkmaz uyarısı verir.</span></div>
              <div class="feature-card"><b>STD Operasyon Kuralı</b><span>Personel STD'den 3 saat 10 dakika önce hazır olur, STD + 20 dakika sonra yeni göreve geçebilir.</span></div>
              <div class="feature-card"><b>Havuz Uçakları</b><span>UZB, IAW, DAH, FAD, RAM, BRU, AWG herkes tarafından yapılabilir; en az 1 Supervisor gerekir.</span></div>
              <div class="feature-card"><b>AI Gecikme Önerisi</b><span>Delay durumunda görevi devralabilecek uygun personeli önerir.</span></div>
            </div>
          </div>
          <div class="tower">
            <h2>Kontrol Kulesi</h2>
            <p>Planlama ekranına geçip dosyaları yükle, hakedişleri düzenle ve yeni hafta planını oluştur.</p>
            <div class="mini-stat"><small>Geliş Servisleri</small><strong>{len(ARRIVAL_SERVICES)}</strong></div>
            <div class="mini-stat"><small>Gidiş Servisleri</small><strong>{len(DEPARTURE_SERVICES)}</strong></div>
            <div class="mini-stat"><small>Servis Alt Limiti</small><strong>{MIN_ROUTE_SERVICE_COUNT}</strong></div>
            <div class="mini-stat"><small>Havuz Uçak</small><strong>{len(POOL_AIRCRAFT_CODES)}</strong></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    if st.button("Planlama Sayfasına Geç", type="primary"):
        st.session_state.page = "Planlama"
        st.rerun()


def planning_page():
    render_flying_background()
    st.markdown('<div class="hero">' + logo_html(170) + '<span class="pill">PLANLAMA PANELİ</span><h1>Yeni Hafta Operasyon Planı</h1><p>Dosyaları yükle, hakedişleri kontrol et, yeni hafta vardiya ve servis planını üret.</p></div>', unsafe_allow_html=True)
    st.write("")

    with st.sidebar:
        st.markdown("### Dosyalar")
        dep_file = st.file_uploader("DEPARTURE dosyası", type=["csv", "xlsx", "xls"])
        q_file = st.file_uploader("QUALIFICATIONLAR-YHM dosyası", type=["csv", "xlsx", "xls"])
        shift_file = st.file_uploader("20. Hafta YHM dosyası", type=["xlsx", "xls", "csv"])
        hak_file = st.file_uploader("Hakediş dosyası (opsiyonel)", type=["xlsx", "xls", "csv"])
        st.caption("Hakediş dosyası okunamazsa sistem tahmini kural kullanır.")

    if dep_file is None or q_file is None or shift_file is None:
        st.info("Devam etmek için DEPARTURE, QUALIFICATIONLAR-YHM ve 20. Hafta YHM dosyalarını yükle.")
        return

    dep_raw = read_any_table(dep_file)
    q_raw = read_any_table(q_file)
    shift_raw = read_excel_sheet_by_keyword(shift_file, "HAFTA") if shift_file.name.lower().endswith((".xlsx", ".xls")) else read_any_table(shift_file)

    flights = parse_flights(dep_raw)
    qual_people, qmap = parse_qualifications(q_raw)
    staff = parse_staff_master(shift_raw, qual_people, qmap)

    if flights.empty or staff.empty:
        st.error("Uçuş veya personel verisi okunamadı. Sütun adlarını kontrol et.")
        st.write("Departure kolonları:", list(dep_raw.columns))
        st.write("Shift kolonları:", list(shift_raw.columns))
        return

    # Dashboard
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aktif Personel", int(staff["Aktif"].sum()))
    c2.metric("Haftalık Uçuş", len(flights))
    c3.metric("Toplam Hakediş", int(flights["Hakediş"].sum()))
    c4.metric("Havuz Uçuş", int(flights["A/L"].isin(POOL_AIRCRAFT_CODES).sum()))

    tab_files, tab_admin, tab_plan, tab_ai = st.tabs(["1 Dosya Kontrol", "2 Admin", "3 Yeni Hafta Planı", "4 AI Gecikme"])

    with tab_files:
        st.markdown("### Uçuş Verisi")
        st.dataframe(flights, use_container_width=True)
        st.markdown("### Personel Master")
        st.dataframe(staff, use_container_width=True)
        st.markdown("### Qualification Okuma")
        st.dataframe(qual_people, use_container_width=True)

    with tab_admin:
        st.markdown("### Personel Yönetimi")
        edited_staff = st.data_editor(
            staff,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Base Rol": st.column_config.SelectboxColumn("Base Rol", options=ROLE_OPTIONS),
                "Tip": st.column_config.SelectboxColumn("Tip", options=["Full-Time", "Part-Time"]),
                "Aktif": st.column_config.CheckboxColumn("Aktif"),
            },
            key="staff_editor",
        )
        staff = edited_staff.copy()
        st.markdown("### DO / İzin / Rapor")
        names = staff[staff["Aktif"] == True]["Personel"].sort_values().tolist()
        do_people = st.multiselect("DO talebi olanlar", names)
        leave_people = st.multiselect("İzin / VA / Raporlu olanlar", names)

        st.markdown("### Uçuş Hakediş Manuel Ayarı")
        need_df = flights[["flight_id", "Tarih", "STD", "A/L", "OUT", "Hakediş"]].copy()
        need_df = st.data_editor(need_df, use_container_width=True, key="need_editor")
        manual_need = dict(zip(need_df["flight_id"], need_df["Hakediş"].astype(int)))
        st.session_state.staff = staff
        st.session_state.do_people = do_people
        st.session_state.leave_people = leave_people
        st.session_state.manual_need = manual_need

    with tab_plan:
        staff = st.session_state.get("staff", staff)
        do_people = st.session_state.get("do_people", [])
        leave_people = st.session_state.get("leave_people", [])
        manual_need = st.session_state.get("manual_need", dict(zip(flights["flight_id"], flights["Hakediş"])))

        st.markdown("### Yeni Hafta Planını Oluştur")
        st.caption("Bu plan eski haftayı raporlamaz. 20. hafta dosyasını personel adı, rol, servis güzergahı ve master bilgi için kullanır.")
        if st.button("Yeni Hafta Planı Oluştur / Yenile", type="primary"):
            plan, diagnostics = generate_new_week_plan(flights, staff, qmap, do_people, leave_people, manual_need)
            shift_plan = build_shift_plan_from_assignments(plan, staff)
            service_plan = build_service_plan(shift_plan)
            daily_view = build_daily_flight_view(plan)
            hour_validation = validate_weekly_hours(shift_plan, staff)
            st.session_state.plan = plan
            st.session_state.diagnostics = diagnostics
            st.session_state.shift_plan = shift_plan
            st.session_state.service_plan = service_plan
            st.session_state.daily_view = daily_view
            st.session_state.hour_validation = hour_validation

        plan = st.session_state.get("plan", pd.DataFrame())
        if plan.empty:
            st.info("Henüz plan oluşturulmadı.")
        else:
            daily_view = st.session_state.get("daily_view", pd.DataFrame())
            shift_plan = st.session_state.get("shift_plan", pd.DataFrame())
            service_plan = st.session_state.get("service_plan", pd.DataFrame())
            hour_validation = st.session_state.get("hour_validation", pd.DataFrame())
            diagnostics = st.session_state.get("diagnostics", pd.DataFrame())

            st.markdown("### Gün Gün Hangi Uçağa Kimler Çıkacak")
            st.dataframe(daily_view, use_container_width=True)

            st.markdown("### Gün Gün Herkesin Vardiyası")
            st.dataframe(shift_plan, use_container_width=True)

            st.markdown("### Servis Planlaması")
            st.caption("Aynı güzergah + aynı servis saati için minimum 4 kişi kuralı uygulanır.")
            st.dataframe(service_plan, use_container_width=True)

            st.markdown("### Saat Kontrol")
            st.dataframe(hour_validation, use_container_width=True)

            st.markdown("### Aday Diagnostik")
            st.dataframe(diagnostics, use_container_width=True)

            st.markdown("### Manuel Görev Düzenleme")
            edited_plan = st.data_editor(
                plan,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Personel": st.column_config.SelectboxColumn("Personel", options=staff[staff["Aktif"] == True]["Personel"].sort_values().tolist()),
                    "Görev Rolü": st.column_config.SelectboxColumn("Görev Rolü", options=ROLE_OPTIONS),
                },
                key="manual_plan_editor",
            )
            if st.button("Manuel Değişikliklerden Vardiya/Servisi Tekrar Hesapla"):
                st.session_state.plan = edited_plan
                st.session_state.shift_plan = build_shift_plan_from_assignments(edited_plan, staff)
                st.session_state.service_plan = build_service_plan(st.session_state.shift_plan)
                st.session_state.daily_view = build_daily_flight_view(edited_plan)
                st.session_state.hour_validation = validate_weekly_hours(st.session_state.shift_plan, staff)
                st.success("Manuel değişiklikler tekrar hesaplandı.")
                st.rerun()

            excel_bytes = export_excel(plan, daily_view, shift_plan, service_plan, hour_validation, diagnostics)
            st.download_button("Excel Raporu İndir", data=excel_bytes, file_name="celebi_yhm_yeni_hafta_planlama.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tab_ai:
        plan = st.session_state.get("plan", pd.DataFrame())
        shift_plan = st.session_state.get("shift_plan", pd.DataFrame())
        if plan.empty:
            st.info("AI gecikme önerisi için önce plan oluştur.")
        else:
            outs = plan["OUT"].dropna().astype(str).sort_values().unique().tolist()
            selected_out = st.selectbox("Geciken uçuş", outs)
            delay_min = st.number_input("Gecikme dakikası", min_value=0, max_value=600, value=60, step=10)
            if st.button("AI Devir / Değişiklik Önerisi Üret", type="primary"):
                advice = ai_delay_advisor(plan, shift_plan, staff, qmap, selected_out, int(delay_min))
                if advice.empty:
                    st.warning("Uygun devralacak personel bulunamadı. Manuel müdahale gerekebilir.")
                else:
                    st.dataframe(advice, use_container_width=True)


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="✈️", layout="wide")
    inject_css()
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "page" not in st.session_state:
        st.session_state.page = "Ana Sayfa"

    if not st.session_state.logged_in:
        login_screen()
        return

    with st.sidebar:
        st.markdown("## Çelebi YHM")
        st.caption(APP_VERSION)
        page = st.radio("Menü", ["Ana Sayfa", "Planlama"], index=0 if st.session_state.page == "Ana Sayfa" else 1)
        st.session_state.page = page
        if st.button("Çıkış"):
            st.session_state.logged_in = False
            st.rerun()

    if st.session_state.page == "Ana Sayfa":
        home_page()
    else:
        planning_page()


if __name__ == "__main__":
    main()
