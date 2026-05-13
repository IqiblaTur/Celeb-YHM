from __future__ import annotations

import base64
import io
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

try:
    import plotly.express as px
except Exception:  # pragma: no cover
    px = None

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
except Exception:  # pragma: no cover
    AgGrid = None
    GridOptionsBuilder = None
    GridUpdateMode = None

APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR / "assets"
DATA_DIR = APP_DIR / "data"

POOL_FLIGHTS = {"UZB", "IAW", "DAH", "FAD", "RAM", "BRU", "AWG"}
SPECIAL_AIRLINES = {"ETD": "Etihad", "ETIHAD": "Etihad"}
MAJOR_AIRLINES_TEAM_6 = {"SVA", "UAE", "ETD", "DLH", "KAL", "CSN", "CES"}
GATE_REPORT_MIN_BEFORE_STD = 95
GATE_RELEASE_MIN_AFTER_STD = 25
MIN_REST_HOURS = 11
FULL_TIME_MAX_HOURS = 50
FULL_TIME_MIN_HOURS = 40
PART_TIME_MAX_HOURS = 25

COUNTER_PERIODS = [
    ("08:35", "10:30", 12),
    ("10:30", "12:00", 9),
    ("12:00", "14:30", 17),
    ("14:30", "17:25", 10),
]

WEEKDAY_FIX = {
    "PAZARTES?": "PAZARTESİ",
    "PAZARTESI": "PAZARTESİ",
    "ÇAR?AMBA": "ÇARŞAMBA",
    "CARSAMBA": "ÇARŞAMBA",
    "PER?EMBE": "PERŞEMBE",
    "PERSEMBE": "PERŞEMBE",
    "CUMARTES?": "CUMARTESİ",
    "CUMARTESI": "CUMARTESİ",
}


def asset_path(name: str) -> Path:
    return ASSETS_DIR / name


def file_to_base64(path: Path) -> str:
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def inject_css() -> None:
    logo_b64 = file_to_base64(asset_path("celebi_logo.png"))
    plane_b64 = file_to_base64(asset_path("plane_emirates.jpg"))
    st.markdown(
        f"""
        <style>
            :root {{
                --navy: #071E3D;
                --navy-2: #0B2D5B;
                --blue-soft: #EAF2FF;
                --white: #FFFFFF;
                --ink: #122033;
                --muted: #607089;
                --line: rgba(7, 30, 61, 0.12);
            }}
            .stApp {{
                background: radial-gradient(circle at top right, rgba(11,45,91,.10), transparent 32%),
                            linear-gradient(180deg, #ffffff 0%, #f7faff 45%, #ffffff 100%);
                color: var(--ink);
            }}
            section[data-testid="stSidebar"] {{
                background: linear-gradient(180deg, #071E3D 0%, #0B2D5B 100%);
                color: #fff;
            }}
            section[data-testid="stSidebar"] * {{ color: #fff !important; }}
            .block-container {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1450px; }}
            .yhm-topbar {{
                display:flex; align-items:center; gap:18px; margin-bottom: 18px;
                border:1px solid var(--line); border-radius:24px; padding:14px 18px;
                background:rgba(255,255,255,.86); box-shadow:0 18px 45px rgba(7,30,61,.08);
            }}
            .yhm-logo-box {{
                width:80px; height:58px; border-radius:18px; background:white;
                display:flex; align-items:center; justify-content:center; overflow:hidden;
                border:1px solid var(--line);
            }}
            .yhm-logo-box img {{ max-width:76px; max-height:54px; object-fit:contain; }}
            .yhm-title {{ font-weight:800; font-size:28px; color:var(--navy); line-height:1.1; margin:0; }}
            .yhm-subtitle {{ color:var(--muted); font-size:14px; margin-top:5px; }}
            .hero-card {{
                position:relative; min-height:290px; overflow:hidden; border-radius:32px;
                background: linear-gradient(135deg, #071E3D 0%, #0B2D5B 65%, #ffffff 210%);
                box-shadow: 0 28px 80px rgba(7,30,61,.22);
                padding:34px; color:white; margin-bottom:22px;
            }}
            .hero-card:before {{
                content:""; position:absolute; inset:0; opacity:.10;
                background-image:url('data:image/png;base64,{logo_b64}'); background-size:340px; background-repeat:no-repeat;
                background-position: 92% 16%;
            }}
            .hero-plane {{
                position:absolute; right:3%; top:16%; width:42%; max-width:610px; opacity:.32;
                filter: drop-shadow(0 28px 25px rgba(0,0,0,.25));
                animation: planeFloat 7s ease-in-out infinite;
            }}
            @keyframes planeFloat {{
                0%,100% {{ transform: translateY(0px) translateX(0px) rotate(-1deg); }}
                50% {{ transform: translateY(-12px) translateX(-8px) rotate(1deg); }}
            }}
            .hero-content {{ position:relative; z-index:2; max-width:740px; }}
            .hero-kicker {{ letter-spacing:.10em; font-size:13px; color:#BFD8FF; font-weight:700; }}
            .hero-title {{ font-size:44px; line-height:1.06; margin:12px 0 14px 0; font-weight:900; }}
            .hero-text {{ font-size:16px; line-height:1.7; color:#EAF2FF; max-width:640px; }}
            .stat-card {{
                border:1px solid var(--line); border-radius:22px; background:rgba(255,255,255,.90);
                padding:18px; box-shadow:0 16px 40px rgba(7,30,61,.08); min-height:112px;
            }}
            .stat-number {{ color:var(--navy); font-size:32px; font-weight:900; line-height:1; }}
            .stat-label {{ color:var(--muted); font-size:13px; margin-top:8px; }}
            .blue-card {{
                border:1px solid var(--line); border-radius:24px; background:white;
                padding:20px; box-shadow:0 16px 40px rgba(7,30,61,.06); margin-bottom:15px;
            }}
            .section-title {{ font-size:22px; font-weight:850; color:var(--navy); margin: 0 0 8px; }}
            .tiny-muted {{ color:var(--muted); font-size:13px; }}
            .pill {{ display:inline-block; padding:5px 10px; border-radius:999px; background:#EAF2FF; color:#071E3D; font-weight:700; font-size:12px; margin-right:6px; }}
            div.stButton > button, div.stDownloadButton > button {{
                border-radius:14px; border:1px solid #0B2D5B; background:#071E3D; color:white;
                font-weight:750; padding:.58rem 1rem;
            }}
            div.stButton > button:hover, div.stDownloadButton > button:hover {{
                border-color:#071E3D; background:#0B2D5B; color:white;
            }}
            [data-testid="stMetricValue"] {{ color: #071E3D; font-weight:900; }}
            .ag-theme-streamlit {{ border-radius:18px; overflow:hidden; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def topbar() -> None:
    logo_b64 = file_to_base64(asset_path("celebi_logo.png"))
    st.markdown(
        f"""
        <div class="yhm-topbar">
            <div class="yhm-logo-box"><img src="data:image/png;base64,{logo_b64}" /></div>
            <div>
                <p class="yhm-title">YHM-Shift Akıllı Vardiya ve Servis Planlama Sistemi</p>
                <div class="yhm-subtitle">Çelebi YHM operasyonu için departure bazlı ekip, vardiya, servis ve disruption yönetimi</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def hero() -> None:
    plane_b64 = file_to_base64(asset_path("plane_emirates.jpg"))
    st.markdown(
        f"""
        <div class="hero-card">
            <img class="hero-plane" src="data:image/jpeg;base64,{plane_b64}" />
            <div class="hero-content">
                <div class="hero-kicker">YHM OPERASYON KONTROL</div>
                <div class="hero-title">Vardiya, uçak ekibi ve servis planını tek ekranda yönet.</div>
                <div class="hero-text">
                    Departure dosyasındaki STD saatlerine göre gate hazır bulunma zamanı hesaplanır,
                    personel yetkinlikleri kontrol edilir, servis saatleriyle uyumlu vardiya önerilir ve gecikme durumunda uygun devir personeli bulunur.
                </div>
                <div style="margin-top:20px;">
                    <span class="pill">11 saat dinlenme</span>
                    <span class="pill">Servis kotası ≥ 4</span>
                    <span class="pill">Pool flight Supervisor</span>
                    <span class="pill">Etihad özel yetkinlik</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def parse_clock(value: str) -> time:
    value = str(value).strip()
    return datetime.strptime(value, "%H:%M").time()


def combine_date_time(d: date, hhmm: str) -> datetime:
    return datetime.combine(d, parse_clock(hhmm))


def norm_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if pd.isna(v):
        return False
    s = str(v).strip().lower()
    return s in {"1", "true", "evet", "yes", "y", "aktif", "var"}


def split_tokens(v) -> List[str]:
    if pd.isna(v):
        return []
    return [x.strip().upper() for x in re.split(r"[,;/|]+", str(v)) if x.strip()]


@st.cache_data(show_spinner=False)
def read_default_departures() -> pd.DataFrame:
    return read_departure_file(DATA_DIR / "departure_sample.csv")


@st.cache_data(show_spinner=False)
def read_default_staff() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "staff_sample.csv")


@st.cache_data(show_spinner=False)
def read_default_services() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "services_sample.csv")


def read_departure_file(file_or_path) -> pd.DataFrame:
    """Read YHM departure CSV/Excel and normalize to operational fields."""
    if file_or_path is None:
        return pd.DataFrame()

    if isinstance(file_or_path, (str, Path)):
        suffix = Path(file_or_path).suffix.lower()
        source = file_or_path
    else:
        suffix = Path(getattr(file_or_path, "name", "upload.csv")).suffix.lower()
        source = file_or_path

    if suffix in {".xlsx", ".xls"}:
        raw = pd.read_excel(source)
    else:
        raw = None
        for enc in ["utf-8-sig", "cp1254", "latin1"]:
            for sep in [";", ",", "\t"]:
                try:
                    if hasattr(source, "seek"):
                        source.seek(0)
                    candidate = pd.read_csv(source, sep=sep, encoding=enc)
                    if candidate.shape[1] > 1:
                        raw = candidate
                        raise StopIteration
                except StopIteration:
                    break
                except Exception:
                    continue
            if raw is not None:
                break
        if raw is None:
            if hasattr(source, "seek"):
                source.seek(0)
            raw = pd.read_csv(source, encoding="latin1")

    raw = raw.copy()
    raw.columns = [str(c).strip() for c in raw.columns]

    day_col = raw.columns[0] if raw.shape[1] else "day_marker"
    rename_map = {}
    for c in raw.columns:
        c_clean = str(c).strip().upper()
        if c_clean in {"A/L", "AL", "AIRLINE", "A I R L I N E"}:
            rename_map[c] = "airline"
        elif c_clean == "IN":
            rename_map[c] = "flight_in"
        elif c_clean == "OUT":
            rename_map[c] = "flight_out"
        elif c_clean == "STA":
            rename_map[c] = "sta"
        elif c_clean == "STD":
            rename_map[c] = "std"
    raw = raw.rename(columns=rename_map)
    if day_col in raw.columns and day_col not in rename_map.values():
        raw = raw.rename(columns={day_col: "day_marker"})
    elif "day_marker" not in raw.columns:
        raw["day_marker"] = np.nan

    required = ["airline", "flight_in", "flight_out", "sta", "std"]
    for col in required:
        if col not in raw.columns:
            raw[col] = np.nan

    df = raw[["day_marker", "airline", "flight_in", "flight_out", "sta", "std"]].copy()
    df = df.dropna(subset=["airline", "flight_out", "std"], how="any")
    df["weekday"] = df["day_marker"].ffill().astype(str).str.strip().str.upper()
    df["weekday"] = df["weekday"].replace(WEEKDAY_FIX)
    df["airline"] = df["airline"].astype(str).str.strip().str.upper()
    df["flight_in"] = df["flight_in"].astype(str).str.strip().replace({"nan": ""})
    df["flight_out"] = df["flight_out"].astype(str).str.strip().replace({"nan": ""})
    df["sta"] = pd.to_datetime(df["sta"], dayfirst=True, errors="coerce")
    df["std"] = pd.to_datetime(df["std"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["std"])
    df["op_date"] = df["std"].dt.date
    df["std_time"] = df["std"].dt.strftime("%H:%M")
    df["gate_start"] = df["std"] - pd.to_timedelta(GATE_REPORT_MIN_BEFORE_STD, unit="m")
    df["gate_end"] = df["std"] + pd.to_timedelta(GATE_RELEASE_MIN_AFTER_STD, unit="m")
    df["team_size"] = df["airline"].apply(lambda x: 6 if x in MAJOR_AIRLINES_TEAM_6 else 5)
    df["pool_flight"] = df["airline"].isin(POOL_FLIGHTS)
    df["special_required"] = df["airline"].isin(SPECIAL_AIRLINES.keys())
    df["flight_key"] = df["airline"] + "-" + df["flight_out"].astype(str) + "-" + df["std"].dt.strftime("%Y%m%d%H%M")
    return df.sort_values("std").reset_index(drop=True)


def normalize_staff(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    defaults = {
        "employee_id": "",
        "name": "",
        "route": "ARN",
        "employment_type": "FT",
        "qualifications": "Check-in",
        "is_supervisor": False,
        "is_lead": False,
        "can_checkin": True,
        "special_airlines": "",
        "success_pct": 75,
        "active": True,
        "notes": "",
    }
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
    df["employee_id"] = df["employee_id"].astype(str).replace({"nan": ""})
    missing_id = df["employee_id"].str.strip().eq("")
    df.loc[missing_id, "employee_id"] = [f"YHM-AUTO-{i+1:03d}" for i in range(missing_id.sum())]
    df["name"] = df["name"].astype(str).str.strip()
    df["route"] = df["route"].astype(str).str.strip().str.upper()
    df["employment_type"] = df["employment_type"].astype(str).str.strip().str.upper().replace({"PARTTIME": "PT", "FULLTIME": "FT"})
    for col in ["is_supervisor", "is_lead", "can_checkin", "active"]:
        df[col] = df[col].apply(norm_bool)
    df["success_pct"] = pd.to_numeric(df["success_pct"], errors="coerce").fillna(75).clip(0, 100)
    return df


def normalize_services(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["route", "direction", "time", "min_count", "capacity", "active"]:
        if col not in df.columns:
            if col == "active":
                df[col] = True
            elif col in {"min_count", "capacity"}:
                df[col] = 4 if col == "min_count" else 20
            else:
                df[col] = ""
    df["route"] = df["route"].astype(str).str.strip().str.upper()
    df["direction"] = df["direction"].astype(str).str.strip().str.upper()
    df["time"] = df["time"].astype(str).str.strip().str[:5]
    df["min_count"] = pd.to_numeric(df["min_count"], errors="coerce").fillna(4).astype(int)
    df["capacity"] = pd.to_numeric(df["capacity"], errors="coerce").fillna(20).astype(int)
    df["active"] = df["active"].apply(norm_bool)
    return df


def display_table(df: pd.DataFrame, key: str, height: int = 420, editable: bool = False) -> pd.DataFrame:
    if df is None or df.empty:
        st.info("Gösterilecek veri yok.")
        return df
    if AgGrid is not None and not editable:
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=25)
        gb.configure_side_bar()
        gb.configure_default_column(filter=True, sortable=True, resizable=True)
        grid = AgGrid(
            df,
            gridOptions=gb.build(),
            height=height,
            theme="streamlit",
            update_mode=GridUpdateMode.NO_UPDATE,
            allow_unsafe_jscode=False,
            key=key,
        )
        return pd.DataFrame(grid["data"])
    if editable:
        return st.data_editor(df, height=height, use_container_width=True, num_rows="dynamic", key=key)
    st.dataframe(df, height=height, use_container_width=True)
    return df


def has_special(staff_row: pd.Series, airline: str) -> bool:
    special = set(split_tokens(staff_row.get("special_airlines", "")))
    return airline in special or (airline == "ETD" and "ETIHAD" in special)


def is_qualified_for_flight(staff_row: pd.Series, flight: pd.Series) -> bool:
    if not bool(staff_row.get("active", True)):
        return False
    airline = str(flight["airline"]).upper()
    if bool(flight.get("special_required", False)) and not has_special(staff_row, airline):
        return False
    return True


def intervals_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def find_service_for_interval(route: str, start_dt: datetime, end_dt: datetime, services: pd.DataFrame) -> Dict[str, object]:
    route = str(route).upper()
    svc = services[(services["route"] == route) & (services["active"] == True)].copy()
    result = {
        "arrival_service": None,
        "departure_service": None,
        "arrival_wait_min": None,
        "departure_wait_min": None,
        "service_score": 9999,
    }
    if svc.empty:
        return result

    def candidates(direction: str, anchor: datetime) -> List[datetime]:
        rows = svc[svc["direction"] == direction]
        out = []
        for day_delta in [-1, 0, 1]:
            d = (anchor + timedelta(days=day_delta)).date()
            for t in rows["time"].dropna().unique():
                try:
                    out.append(combine_date_time(d, t))
                except Exception:
                    continue
        return sorted(out)

    arrivals = [c for c in candidates("ARRIVAL", start_dt) if c <= start_dt]
    departures = [c for c in candidates("DEPARTURE", end_dt) if c >= end_dt]
    if arrivals:
        arr = max(arrivals)
        result["arrival_service"] = arr
        result["arrival_wait_min"] = int((start_dt - arr).total_seconds() // 60)
    if departures:
        dep = min(departures)
        result["departure_service"] = dep
        result["departure_wait_min"] = int((dep - end_dt).total_seconds() // 60)
    if result["arrival_wait_min"] is not None and result["departure_wait_min"] is not None:
        result["service_score"] = result["arrival_wait_min"] + result["departure_wait_min"]
    return result


def in_leave(staff_id: str, task_date: date, leave_df: pd.DataFrame) -> bool:
    if leave_df is None or leave_df.empty:
        return False
    needed = {"employee_id", "start_date", "end_date"}
    if not needed.issubset(set(leave_df.columns)):
        return False
    for _, row in leave_df.iterrows():
        if str(row.get("employee_id")) != str(staff_id):
            continue
        try:
            s = pd.to_datetime(row.get("start_date")).date()
            e = pd.to_datetime(row.get("end_date")).date()
        except Exception:
            continue
        if s <= task_date <= e:
            return True
    return False


def check_rest_and_overlap(
    staff_id: str,
    start_dt: datetime,
    end_dt: datetime,
    assignments_by_staff: Dict[str, List[Tuple[datetime, datetime]]],
) -> bool:
    existing = assignments_by_staff.get(staff_id, [])
    for s, e in existing:
        if intervals_overlap(s, e, start_dt, end_dt):
            return False
        if e <= start_dt and (start_dt - e).total_seconds() < MIN_REST_HOURS * 3600:
            if s.date() != start_dt.date():
                return False
        if end_dt <= s and (s - end_dt).total_seconds() < MIN_REST_HOURS * 3600:
            if s.date() != end_dt.date():
                return False
    return True


def weekly_limit_ok(staff_row: pd.Series, current_hours: float, add_hours: float) -> bool:
    emp_type = str(staff_row.get("employment_type", "FT")).upper()
    max_h = PART_TIME_MAX_HOURS if emp_type == "PT" else FULL_TIME_MAX_HOURS
    return current_hours + add_hours <= max_h + 0.01


def choose_staff_for_task(
    task: Dict[str, object],
    staff: pd.DataFrame,
    services: pd.DataFrame,
    leave_df: pd.DataFrame,
    assignments_by_staff: Dict[str, List[Tuple[datetime, datetime]]],
    weekly_hours: Dict[str, float],
    already_in_task: set,
    require_supervisor: bool = False,
    require_checkin: bool = False,
) -> Tuple[Optional[pd.Series], str]:
    candidates = []
    start_dt = task["start"]
    end_dt = task["end"]
    task_date = start_dt.date()
    duration_hours = max((end_dt - start_dt).total_seconds() / 3600.0, 0.25)

    for _, row in staff.iterrows():
        staff_id = str(row["employee_id"])
        if staff_id in already_in_task:
            continue
        if not bool(row.get("active", True)):
            continue
        if in_leave(staff_id, task_date, leave_df):
            continue
        if require_supervisor and not bool(row.get("is_supervisor", False)):
            continue
        if require_checkin and not bool(row.get("can_checkin", True)):
            continue
        flight = task.get("flight")
        if flight is not None and not is_qualified_for_flight(row, flight):
            continue
        if not check_rest_and_overlap(staff_id, start_dt, end_dt, assignments_by_staff):
            continue
        if not weekly_limit_ok(row, weekly_hours.get(staff_id, 0.0), duration_hours):
            continue
        svc = find_service_for_interval(str(row["route"]), start_dt, end_dt, services)
        service_score = svc["service_score"]
        route_bonus = 0 if service_score < 9999 else 500
        supervisor_penalty = -8 if bool(row.get("is_supervisor", False)) else 0
        lead_penalty = -3 if bool(row.get("is_lead", False)) else 0
        score = (
            weekly_hours.get(staff_id, 0.0) * 8
            + service_score * 0.08
            - float(row.get("success_pct", 75)) * 0.25
            + route_bonus
            + supervisor_penalty
            + lead_penalty
        )
        candidates.append((score, row))

    if not candidates:
        return None, "Uygun personel bulunamadı"
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], "OK"


def build_plan(
    departures: pd.DataFrame,
    staff_df: pd.DataFrame,
    services_df: pd.DataFrame,
    leave_df: pd.DataFrame,
    include_counter: bool = True,
) -> Dict[str, pd.DataFrame]:
    staff = normalize_staff(staff_df)
    services = normalize_services(services_df)
    warnings = []
    flight_rows = []
    counter_rows = []
    assignments_by_staff: Dict[str, List[Tuple[datetime, datetime]]] = {str(s): [] for s in staff["employee_id"]}
    weekly_hours: Dict[str, float] = {str(s): 0.0 for s in staff["employee_id"]}

    deps = departures.sort_values("std").reset_index(drop=True)

    for _, flight in deps.iterrows():
        task = {
            "type": "flight",
            "start": flight["gate_start"].to_pydatetime() if hasattr(flight["gate_start"], "to_pydatetime") else flight["gate_start"],
            "end": flight["gate_end"].to_pydatetime() if hasattr(flight["gate_end"], "to_pydatetime") else flight["gate_end"],
            "flight": flight,
        }
        team_size = int(flight.get("team_size", 5))
        already = set()
        assigned = []

        if bool(flight.get("pool_flight", False)):
            chosen, reason = choose_staff_for_task(task, staff, services, leave_df, assignments_by_staff, weekly_hours, already, require_supervisor=True)
            if chosen is None:
                warnings.append({
                    "severity": "Kritik",
                    "context": str(flight["flight_out"]),
                    "message": f"{flight['airline']} pool uçuşu için Supervisor bulunamadı.",
                    "recommendation": "S yetkin personel ekleyin veya manuel devir yapın.",
                })
            else:
                assigned.append((chosen, "Supervisor"))
                already.add(str(chosen["employee_id"]))

        for slot in range(team_size - len(assigned)):
            chosen, reason = choose_staff_for_task(task, staff, services, leave_df, assignments_by_staff, weekly_hours, already)
            if chosen is None:
                warnings.append({
                    "severity": "Uyarı",
                    "context": str(flight["flight_out"]),
                    "message": f"{flight['airline']} {flight['flight_out']} için {team_size} kişilik ekip tamamlanamadı. Eksik slot: {team_size - len(assigned)}",
                    "recommendation": "Vardiya sayısını artırın, izin/DO listesini kontrol edin veya servis saatini manuel düzenleyin.",
                })
                break
            role = "Lead Agent" if bool(chosen.get("is_lead", False)) and not any(r == "Lead Agent" for _, r in assigned) else "Agent"
            if bool(chosen.get("is_supervisor", False)) and not any(r == "Supervisor" for _, r in assigned):
                role = "Supervisor"
            assigned.append((chosen, role))
            already.add(str(chosen["employee_id"]))

        for chosen, role in assigned:
            staff_id = str(chosen["employee_id"])
            start_dt, end_dt = task["start"], task["end"]
            duration_hours = max((end_dt - start_dt).total_seconds() / 3600.0, 0.25)
            assignments_by_staff.setdefault(staff_id, []).append((start_dt, end_dt))
            assignments_by_staff[staff_id].sort()
            weekly_hours[staff_id] = weekly_hours.get(staff_id, 0.0) + duration_hours
            flight_rows.append({
                "date": start_dt.date().isoformat(),
                "weekday": flight.get("weekday", ""),
                "airline": flight["airline"],
                "flight_in": flight.get("flight_in", ""),
                "flight_out": flight["flight_out"],
                "std": flight["std"].strftime("%d.%m.%Y %H:%M") if hasattr(flight["std"], "strftime") else str(flight["std"]),
                "gate_start": start_dt.strftime("%d.%m.%Y %H:%M"),
                "gate_end": end_dt.strftime("%d.%m.%Y %H:%M"),
                "employee_id": staff_id,
                "employee": chosen["name"],
                "route": chosen["route"],
                "role": role,
                "special_check": "ETD yetkili" if str(flight["airline"]).upper() == "ETD" else ("Pool" if bool(flight.get("pool_flight", False)) else "Standart"),
                "success_pct": float(chosen.get("success_pct", 0)),
            })

    if include_counter:
        dates = sorted(pd.to_datetime(deps["op_date"].astype(str)).dt.date.unique()) if not deps.empty else []
        for d in dates:
            for start_s, end_s, demand in COUNTER_PERIODS:
                start_dt = combine_date_time(d, start_s)
                end_dt = combine_date_time(d, end_s)
                task = {"type": "counter", "start": start_dt, "end": end_dt, "flight": None}
                already = set()
                for slot in range(demand):
                    chosen, reason = choose_staff_for_task(task, staff, services, leave_df, assignments_by_staff, weekly_hours, already, require_checkin=True)
                    if chosen is None:
                        warnings.append({
                            "severity": "Uyarı",
                            "context": f"Counter {d} {start_s}-{end_s}",
                            "message": f"Counter ihtiyacı {demand}, karşılanan {slot}.",
                            "recommendation": "Check-in yetkili personel, izin/DO veya servis uyumluluğunu kontrol edin.",
                        })
                        break
                    staff_id = str(chosen["employee_id"])
                    duration_hours = max((end_dt - start_dt).total_seconds() / 3600.0, 0.25)
                    assignments_by_staff.setdefault(staff_id, []).append((start_dt, end_dt))
                    assignments_by_staff[staff_id].sort()
                    weekly_hours[staff_id] = weekly_hours.get(staff_id, 0.0) + duration_hours
                    already.add(staff_id)
                    counter_rows.append({
                        "date": d.isoformat(),
                        "weekday": pd.Timestamp(d).day_name(),
                        "area": "Check-in / Counter",
                        "period": f"{start_s}-{end_s}",
                        "need": demand,
                        "employee_id": staff_id,
                        "employee": chosen["name"],
                        "route": chosen["route"],
                        "role": "Counter Agent",
                    })

    shift_rows = build_shift_rows(staff, services, assignments_by_staff, flight_rows, counter_rows, warnings)
    service_rows = build_service_rows(pd.DataFrame(shift_rows), services, warnings)
    workload = build_workload_rows(staff, weekly_hours, warnings)
    return {
        "flight_assignments": pd.DataFrame(flight_rows),
        "counter_assignments": pd.DataFrame(counter_rows),
        "shift_plan": pd.DataFrame(shift_rows),
        "service_plan": pd.DataFrame(service_rows),
        "workload": pd.DataFrame(workload),
        "warnings": pd.DataFrame(warnings),
    }


def build_shift_rows(
    staff: pd.DataFrame,
    services: pd.DataFrame,
    assignments_by_staff: Dict[str, List[Tuple[datetime, datetime]]],
    flight_rows: List[Dict[str, object]],
    counter_rows: List[Dict[str, object]],
    warnings: List[Dict[str, str]],
) -> List[Dict[str, object]]:
    detail_by_staff_date: Dict[Tuple[str, date], List[str]] = {}
    for row in flight_rows:
        try:
            d = pd.to_datetime(row["gate_start"], dayfirst=True).date()
        except Exception:
            d = pd.to_datetime(row["date"]).date()
        key = (str(row["employee_id"]), d)
        detail_by_staff_date.setdefault(key, []).append(f"{row['airline']} {row['flight_out']} ({row['role']})")
    for row in counter_rows:
        d = pd.to_datetime(row["date"]).date()
        key = (str(row["employee_id"]), d)
        detail_by_staff_date.setdefault(key, []).append(f"Counter {row['period']}")

    shift_rows = []
    staff_lookup = staff.set_index("employee_id").to_dict("index")
    for staff_id, intervals in assignments_by_staff.items():
        if not intervals:
            continue
        by_date: Dict[date, List[Tuple[datetime, datetime]]] = {}
        for s, e in intervals:
            by_date.setdefault(s.date(), []).append((s, e))
        for d, items in sorted(by_date.items()):
            start_dt = min(x[0] for x in items)
            end_dt = max(x[1] for x in items)
            raw_hours = (end_dt - start_dt).total_seconds() / 3600.0
            paid_hours = max(raw_hours - 1.0, 0.0) if raw_hours >= 6.0 else raw_hours
            staff_info = staff_lookup.get(staff_id, {})
            route = staff_info.get("route", "")
            svc = find_service_for_interval(route, start_dt, end_dt, services)
            if svc["arrival_service"] is None or svc["departure_service"] is None:
                warnings.append({
                    "severity": "Servis",
                    "context": f"{staff_info.get('name', staff_id)} {d}",
                    "message": "Vardiya için uygun geliş/gidiş servisi bulunamadı.",
                    "recommendation": "Servis saat tablosuna bu güzergah için uygun saat ekleyin veya vardiyayı kaydırın.",
                })
            if raw_hours > 10.5:
                warnings.append({
                    "severity": "Mesai",
                    "context": f"{staff_info.get('name', staff_id)} {d}",
                    "message": f"Vardiya aralığı uzun görünüyor: {raw_hours:.1f} saat.",
                    "recommendation": "Görevleri iki personele bölün veya manuel düzenleyin.",
                })
            shift_rows.append({
                "date": d.isoformat(),
                "weekday": pd.Timestamp(d).day_name(),
                "employee_id": staff_id,
                "employee": staff_info.get("name", staff_id),
                "route": route,
                "employment_type": staff_info.get("employment_type", "FT"),
                "shift_start": start_dt.strftime("%H:%M"),
                "shift_end": end_dt.strftime("%H:%M"),
                "gross_hours": round(raw_hours, 2),
                "paid_hours_after_meal": round(paid_hours, 2),
                "arrival_service": svc["arrival_service"].strftime("%d.%m %H:%M") if svc["arrival_service"] else "YOK",
                "departure_service": svc["departure_service"].strftime("%d.%m %H:%M") if svc["departure_service"] else "YOK",
                "arrival_wait_min": svc["arrival_wait_min"],
                "departure_wait_min": svc["departure_wait_min"],
                "tasks": " | ".join(detail_by_staff_date.get((staff_id, d), [])),
            })
    return shift_rows


def build_service_rows(shift_plan: pd.DataFrame, services: pd.DataFrame, warnings: List[Dict[str, str]]) -> List[Dict[str, object]]:
    service_rows = []
    if shift_plan.empty:
        return service_rows
    for direction_col, direction_label in [("arrival_service", "Geliş"), ("departure_service", "Gidiş")]:
        tmp = shift_plan[shift_plan[direction_col].notna() & (shift_plan[direction_col] != "YOK")].copy()
        if tmp.empty:
            continue
        grouped = tmp.groupby(["date", "route", direction_col])
        for (d, route, service_time), g in grouped:
            svc_route = services[(services["route"] == route) & (services["direction"] == ("ARRIVAL" if direction_label == "Geliş" else "DEPARTURE"))]
            min_count = int(svc_route["min_count"].iloc[0]) if not svc_route.empty else 4
            capacity = int(svc_route["capacity"].iloc[0]) if not svc_route.empty else 20
            status = "Kalkar" if len(g) >= min_count else "Kota altı"
            if len(g) < min_count:
                warnings.append({
                    "severity": "Servis Kotası",
                    "context": f"{route} {service_time}",
                    "message": f"{direction_label} servisi için {len(g)} kişi var; minimum {min_count} kişi gerekli.",
                    "recommendation": "Aynı güzergah/saatte vardiya kaydırma, yakın personel değişimi veya manuel servis onayı önerilir.",
                })
            service_rows.append({
                "date": d,
                "route": route,
                "direction": direction_label,
                "service_time": service_time,
                "person_count": len(g),
                "min_count": min_count,
                "capacity": capacity,
                "status": status,
                "employees": ", ".join(g["employee"].astype(str).tolist()),
            })
    return service_rows


def build_workload_rows(staff: pd.DataFrame, weekly_hours: Dict[str, float], warnings: List[Dict[str, str]]) -> List[Dict[str, object]]:
    rows = []
    for _, row in staff.iterrows():
        staff_id = str(row["employee_id"])
        hours = weekly_hours.get(staff_id, 0.0)
        emp_type = str(row.get("employment_type", "FT")).upper()
        max_h = PART_TIME_MAX_HOURS if emp_type == "PT" else FULL_TIME_MAX_HOURS
        min_h = 0 if emp_type == "PT" else FULL_TIME_MIN_HOURS
        status = "OK"
        if hours > max_h:
            status = "Maksimum üstü"
        elif emp_type == "FT" and hours < min_h:
            status = "Minimum altı"
        if status != "OK" and hours > 0:
            warnings.append({
                "severity": "Haftalık Saat",
                "context": str(row.get("name", staff_id)),
                "message": f"{emp_type} personel haftalık görev saati {hours:.1f}; hedef aralık {min_h}-{max_h}.",
                "recommendation": "Görev dağılımını dengeleyin veya haftalık plan aralığını genişletin.",
            })
        rows.append({
            "employee_id": staff_id,
            "employee": row.get("name", staff_id),
            "route": row.get("route", ""),
            "employment_type": emp_type,
            "assigned_task_hours": round(hours, 2),
            "target_min": min_h,
            "target_max": max_h,
            "status": status,
        })
    return rows


def init_state() -> None:
    if "departures" not in st.session_state:
        st.session_state.departures = read_default_departures()
    if "staff" not in st.session_state:
        st.session_state.staff = normalize_staff(read_default_staff())
    if "services" not in st.session_state:
        st.session_state.services = normalize_services(read_default_services())
    if "leave_df" not in st.session_state:
        st.session_state.leave_df = pd.DataFrame(columns=["employee_id", "name", "type", "start_date", "end_date", "note"])
    if "plan" not in st.session_state:
        st.session_state.plan = {}


def upload_data_panel() -> None:
    st.markdown('<div class="blue-card"><div class="section-title">Veri Yükleme</div><div class="tiny-muted">Departure, personel ve servis tablolarını buradan değiştirebilirsin. Varsayılan örnek dosyalar ZIP içinde hazır gelir.</div></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        dep_file = st.file_uploader("Departure CSV / Excel", type=["csv", "xlsx", "xls"], key="dep_upload")
        if dep_file is not None:
            try:
                st.session_state.departures = read_departure_file(dep_file)
                st.success("Departure dosyası okundu.")
            except Exception as exc:
                st.error(f"Departure okunamadı: {exc}")
    with c2:
        staff_file = st.file_uploader("Personel CSV / Excel", type=["csv", "xlsx", "xls"], key="staff_upload")
        if staff_file is not None:
            try:
                if staff_file.name.lower().endswith((".xlsx", ".xls")):
                    staff_new = pd.read_excel(staff_file)
                else:
                    staff_new = pd.read_csv(staff_file)
                st.session_state.staff = normalize_staff(staff_new)
                st.success("Personel dosyası okundu.")
            except Exception as exc:
                st.error(f"Personel okunamadı: {exc}")
    with c3:
        svc_file = st.file_uploader("Servis CSV / Excel", type=["csv", "xlsx", "xls"], key="svc_upload")
        if svc_file is not None:
            try:
                if svc_file.name.lower().endswith((".xlsx", ".xls")):
                    svc_new = pd.read_excel(svc_file)
                else:
                    svc_new = pd.read_csv(svc_file)
                st.session_state.services = normalize_services(svc_new)
                st.success("Servis dosyası okundu.")
            except Exception as exc:
                st.error(f"Servis okunamadı: {exc}")


def home_page() -> None:
    topbar()
    hero()
    deps = st.session_state.departures
    staff = st.session_state.staff
    plan = st.session_state.plan
    shift_count = len(plan.get("shift_plan", pd.DataFrame())) if plan else 0
    flight_count = len(plan.get("flight_assignments", pd.DataFrame())) if plan else 0
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{len(deps):,}</div><div class="stat-label">Departure satırı</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{deps["airline"].nunique() if not deps.empty else 0}</div><div class="stat-label">Farklı airline</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{int(staff["active"].sum()) if not staff.empty else 0}</div><div class="stat-label">Aktif personel</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{shift_count}</div><div class="stat-label">Oluşturulan vardiya</div></div>', unsafe_allow_html=True)

    st.markdown("### Haftalık Departure Özeti")
    if not deps.empty:
        daily = deps.groupby("op_date").agg(departure=("flight_out", "count"), airline=("airline", "nunique")).reset_index()
        daily["op_date"] = daily["op_date"].astype(str)
        if px is not None:
            fig = px.bar(daily, x="op_date", y="departure", text="departure", title="Gün Bazında Departure Sayısı")
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=55, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            display_table(daily, "daily_home", 250)
    else:
        st.warning("Departure verisi yok.")

    st.markdown("### Sistem Modülleri")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="blue-card"><b>Planlama</b><br><span class="tiny-muted">STD saatlerinden gate başlangıcı, ekip ve vardiya planı oluşturur.</span></div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="blue-card"><b>Yönetim Paneli</b><br><span class="tiny-muted">Personel, yetkinlik, izin/DO ve servis saatlerini düzenler.</span></div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="blue-card"><b>Disruption</b><br><span class="tiny-muted">Delay sonrası çakışma ve uygun devir personeli önerir.</span></div>', unsafe_allow_html=True)


def planning_page() -> None:
    topbar()
    upload_data_panel()
    deps = st.session_state.departures.copy()
    if deps.empty:
        st.error("Departure verisi yok. Önce Departure CSV yükle.")
        return

    st.markdown("### Planlama Filtreleri")
    min_d, max_d = min(deps["op_date"]), max(deps["op_date"])
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        selected_range = st.date_input("Planlanacak tarih aralığı", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    with c2:
        airline_filter = st.multiselect("Airline filtre", sorted(deps["airline"].unique().tolist()), default=[])
    with c3:
        include_counter = st.toggle("Counter ihtiyacını da plana dahil et", value=True)

    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    else:
        start_date = end_date = selected_range if isinstance(selected_range, date) else min_d
    filtered = deps[(deps["op_date"] >= start_date) & (deps["op_date"] <= end_date)].copy()
    if airline_filter:
        filtered = filtered[filtered["airline"].isin(airline_filter)]

    st.markdown("#### Departure Ön İzleme")
    preview_cols = ["weekday", "airline", "flight_in", "flight_out", "sta", "std", "gate_start", "gate_end", "team_size", "pool_flight", "special_required"]
    preview = filtered[preview_cols].copy()
    for col in ["sta", "std", "gate_start", "gate_end"]:
        preview[col] = pd.to_datetime(preview[col]).dt.strftime("%d.%m.%Y %H:%M")
    display_table(preview, "dep_preview", 360)

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("Planı Oluştur / Yenile", type="primary", use_container_width=True):
            with st.spinner("YHM-Shift planı oluşturuluyor..."):
                st.session_state.plan = build_plan(
                    departures=filtered,
                    staff_df=st.session_state.staff,
                    services_df=st.session_state.services,
                    leave_df=st.session_state.leave_df,
                    include_counter=include_counter,
                )
            st.success("Plan oluşturuldu.")
    with c2:
        st.info("Algoritma: departure STD → gate başlangıcı, yetkinlik kontrolü, 11 saat dinlenme, haftalık saat limiti, servis uyum skoru ve servis kotası uyarıları.")

    plan = st.session_state.plan
    if not plan:
        st.warning("Henüz plan oluşturulmadı.")
        return

    tabs = st.tabs(["Vardiya Planı", "Uçak Atamaları", "Counter", "Servis Listesi", "İş Yükü", "Uyarılar", "Manuel Müdahale"])
    with tabs[0]:
        st.markdown("#### İsim isim: hangi gün hangi vardiya ve hangi servis?")
        display_table(plan.get("shift_plan", pd.DataFrame()), "shift_plan", 520)
    with tabs[1]:
        st.markdown("#### Departure bazlı uçak ekipleri")
        display_table(plan.get("flight_assignments", pd.DataFrame()), "flight_assignments", 520)
    with tabs[2]:
        display_table(plan.get("counter_assignments", pd.DataFrame()), "counter_assignments", 440)
    with tabs[3]:
        display_table(plan.get("service_plan", pd.DataFrame()), "service_plan", 520)
    with tabs[4]:
        display_table(plan.get("workload", pd.DataFrame()), "workload", 520)
    with tabs[5]:
        warnings_df = plan.get("warnings", pd.DataFrame())
        if warnings_df.empty:
            st.success("Kritik uyarı yok.")
        else:
            display_table(warnings_df, "warnings", 520)
    with tabs[6]:
        manual_override_panel()


def manual_override_panel() -> None:
    plan = st.session_state.plan
    flights = plan.get("flight_assignments", pd.DataFrame()).copy()
    if flights.empty:
        st.info("Manuel düzenleme için önce uçak planı oluştur.")
        return
    st.markdown("#### Manuel Uçak Ekibi Değişimi")
    st.caption("Bu bölüm mevcut plan tablosundaki personeli değiştirir. Değişiklik rapor çıktısına yansır; yeniden optimizasyon yaparsan otomatik plan tekrar oluşur.")
    row_options = [f"{i} | {r['date']} | {r['airline']} {r['flight_out']} | {r['employee']} | {r['role']}" for i, r in flights.iterrows()]
    c1, c2 = st.columns(2)
    with c1:
        selected = st.selectbox("Değiştirilecek görev", row_options)
    with c2:
        new_emp = st.selectbox("Yeni personel", st.session_state.staff["name"].tolist())
    if st.button("Seçili görevi yeni personele ver", use_container_width=True):
        idx = int(selected.split(" | ")[0])
        staff_row = st.session_state.staff[st.session_state.staff["name"] == new_emp].iloc[0]
        for col, val in {
            "employee_id": staff_row["employee_id"],
            "employee": staff_row["name"],
            "route": staff_row["route"],
            "success_pct": staff_row["success_pct"],
        }.items():
            flights.loc[idx, col] = val
        plan["flight_assignments"] = flights
        st.session_state.plan = plan
        st.success("Manuel değişiklik uygulandı.")

    st.markdown("#### Hak ediş / ekip sayısı manuel notu")
    st.text_area("Operasyon notu", placeholder="Örn: UZB0272 hak ediş +1; Supervisor devir notu...", key="manual_note")


def management_page() -> None:
    topbar()
    st.markdown("### Yönetim Paneli")
    tabs = st.tabs(["Personel ve Yetkinlik", "İzin / DO", "Servis Güzergahları", "Veri Dışa Aktarım"])
    with tabs[0]:
        st.markdown("#### Personel Matrisi")
        edited = display_table(st.session_state.staff, "staff_editor", 520, editable=True)
        if st.button("Personel matrisini kaydet", use_container_width=True):
            st.session_state.staff = normalize_staff(edited)
            st.success("Personel matrisi güncellendi.")
        st.caption("Etihad için special_airlines alanına ETD veya ETIHAD yaz. Supervisor için is_supervisor=True olmalı.")
    with tabs[1]:
        st.markdown("#### İzin / DO Kayıtları")
        staff_names = st.session_state.staff[["employee_id", "name"]].copy()
        with st.form("leave_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                emp_label = st.selectbox("Personel", [f"{r.employee_id} | {r.name}" for r in staff_names.itertuples()])
                leave_type = st.selectbox("Tip", ["DO", "Yıllık İzin", "Rapor", "Diğer"])
            with c2:
                s_date = st.date_input("Başlangıç", value=date.today())
                e_date = st.date_input("Bitiş", value=date.today())
            with c3:
                note = st.text_area("Not", height=92)
            submitted = st.form_submit_button("İzin / DO ekle")
            if submitted:
                emp_id, emp_name = emp_label.split(" | ", 1)
                new_row = pd.DataFrame([{
                    "employee_id": emp_id,
                    "name": emp_name,
                    "type": leave_type,
                    "start_date": s_date.isoformat(),
                    "end_date": e_date.isoformat(),
                    "note": note,
                }])
                st.session_state.leave_df = pd.concat([st.session_state.leave_df, new_row], ignore_index=True)
                st.success("Kayıt eklendi.")
        edited_leave = display_table(st.session_state.leave_df, "leave_editor", 320, editable=True)
        if st.button("İzin / DO tablosunu kaydet", use_container_width=True):
            st.session_state.leave_df = edited_leave
            st.success("İzin/DO tablosu kaydedildi.")
    with tabs[2]:
        st.markdown("#### Servis Güzergah ve Saatleri")
        edited_services = display_table(st.session_state.services, "services_editor", 520, editable=True)
        if st.button("Servis tablosunu kaydet", use_container_width=True):
            st.session_state.services = normalize_services(edited_services)
            st.success("Servis tablosu güncellendi.")
        st.caption("Servis kotası için min_count en az 4 olmalı. Kapasite, ileride koltuk sınırı için kullanılabilir.")
    with tabs[3]:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button("Personel CSV indir", st.session_state.staff.to_csv(index=False).encode("utf-8-sig"), "staff_yhm.csv", "text/csv")
        with c2:
            st.download_button("Servis CSV indir", st.session_state.services.to_csv(index=False).encode("utf-8-sig"), "services_yhm.csv", "text/csv")
        with c3:
            st.download_button("İzin/DO CSV indir", st.session_state.leave_df.to_csv(index=False).encode("utf-8-sig"), "leave_do_yhm.csv", "text/csv")


def disruption_page() -> None:
    topbar()
    st.markdown("### AI Destekli Operasyonel Müdahale / Delay Yönetimi")
    plan = st.session_state.plan
    flights = plan.get("flight_assignments", pd.DataFrame()) if plan else pd.DataFrame()
    if flights.empty:
        st.warning("Delay analizi için önce Planlama sayfasında plan oluştur.")
        return
    unique_flights = flights[["date", "airline", "flight_out", "std", "gate_start", "gate_end"]].drop_duplicates().reset_index(drop=True)
    labels = [f"{i} | {r.date} | {r.airline} {r.flight_out} | STD {r.std}" for i, r in unique_flights.iterrows()]
    c1, c2 = st.columns([2, 1])
    with c1:
        chosen = st.selectbox("Geciken uçuş", labels)
    with c2:
        delay_min = st.number_input("Delay dakika", min_value=5, max_value=720, value=60, step=5)
    idx = int(chosen.split(" | ")[0])
    flight = unique_flights.iloc[idx]
    old_end = pd.to_datetime(flight["gate_end"], dayfirst=True)
    new_end = old_end + timedelta(minutes=int(delay_min))
    st.info(f"Yeni tahmini gate bitiş: {new_end.strftime('%d.%m.%Y %H:%M')}")

    impacted = flights[(flights["date"] == flight["date"]) & (flights["airline"] == flight["airline"]) & (flights["flight_out"] == flight["flight_out"])].copy()
    st.markdown("#### Mevcut ekip")
    display_table(impacted, "delay_impacted", 280)

    suggestions = build_delay_suggestions(flight, impacted, new_end, plan, st.session_state.staff, st.session_state.services)
    st.markdown("#### Sistem Önerileri")
    if suggestions.empty:
        st.success("Bu delay için ekipte net çakışma tespit edilmedi veya uygun alternatif bulunamadı.")
    else:
        display_table(suggestions, "delay_suggestions", 440)


def build_delay_suggestions(
    flight: pd.Series,
    impacted: pd.DataFrame,
    new_end: datetime,
    plan: Dict[str, pd.DataFrame],
    staff: pd.DataFrame,
    services: pd.DataFrame,
) -> pd.DataFrame:
    all_flights = plan.get("flight_assignments", pd.DataFrame()).copy()
    shift_plan = plan.get("shift_plan", pd.DataFrame()).copy()
    rows = []
    if all_flights.empty or impacted.empty:
        return pd.DataFrame()
    this_key = (flight["date"], flight["airline"], flight["flight_out"])
    for _, person in impacted.iterrows():
        emp_id = str(person["employee_id"])
        next_tasks = all_flights[
            (all_flights["employee_id"].astype(str) == emp_id)
            & ~((all_flights["date"] == this_key[0]) & (all_flights["airline"] == this_key[1]) & (all_flights["flight_out"] == this_key[2]))
        ].copy()
        for _, nt in next_tasks.iterrows():
            try:
                nt_start = pd.to_datetime(nt["gate_start"], dayfirst=True)
            except Exception:
                continue
            if nt_start < new_end:
                replacement = find_replacement_for_delay(nt, new_end, staff, all_flights, shift_plan, services)
                rows.append({
                    "impacted_employee": person["employee"],
                    "conflicting_next_task": f"{nt['airline']} {nt['flight_out']} {nt['gate_start']}",
                    "problem": f"Delay sonrası {person['employee']} bir sonraki göreve yetişemiyor.",
                    "suggested_replacement": replacement.get("name", "Bulunamadı"),
                    "replacement_route": replacement.get("route", ""),
                    "reason": replacement.get("reason", "Uygun ve yetkin personel bulunamadı."),
                })
    return pd.DataFrame(rows)


def find_replacement_for_delay(
    next_task: pd.Series,
    delay_end: datetime,
    staff: pd.DataFrame,
    all_flights: pd.DataFrame,
    shift_plan: pd.DataFrame,
    services: pd.DataFrame,
) -> Dict[str, str]:
    nt_start = pd.to_datetime(next_task["gate_start"], dayfirst=True)
    nt_end = pd.to_datetime(next_task["gate_end"], dayfirst=True)
    airline = str(next_task["airline"]).upper()
    task_date = nt_start.date().isoformat()
    busy_ids = set(
        all_flights[
            all_flights.apply(
                lambda r: intervals_overlap(
                    pd.to_datetime(r["gate_start"], dayfirst=True),
                    pd.to_datetime(r["gate_end"], dayfirst=True),
                    nt_start,
                    nt_end,
                ), axis=1
            )
        ]["employee_id"].astype(str)
    )
    # First prefer people already on shift that day but not on an overlapping aircraft.
    candidates = []
    for _, row in staff.iterrows():
        staff_id = str(row["employee_id"])
        if staff_id in busy_ids:
            continue
        if not bool(row.get("active", True)):
            continue
        if airline == "ETD" and not has_special(row, "ETD"):
            continue
        same_day_shift = shift_plan[(shift_plan["employee_id"].astype(str) == staff_id) & (shift_plan["date"].astype(str) == task_date)]
        on_shift_bonus = 0 if not same_day_shift.empty else 50
        svc = find_service_for_interval(str(row["route"]), nt_start, nt_end, services)
        score = on_shift_bonus + svc["service_score"] * 0.05 - float(row.get("success_pct", 70)) * 0.2
        candidates.append((score, row, same_day_shift.empty, svc))
    if not candidates:
        return {"reason": "Aynı anda boşta, yetkin ve servis uyumlu personel bulunamadı."}
    candidates.sort(key=lambda x: x[0])
    _, row, not_on_shift, svc = candidates[0]
    reason = "O an vardiyada ve görevi çakışmıyor." if not not_on_shift else "Vardiyada değil; servis uyumu kontrol edilerek çağrılabilir."
    if svc["service_score"] >= 9999:
        reason += " Servis uyumu zayıf, manuel onay gerekir."
    return {"name": row["name"], "route": row["route"], "reason": reason}


def reports_page() -> None:
    topbar()
    st.markdown("### 20. Hafta YHM Formatına Uygun Raporlama")
    plan = st.session_state.plan
    if not plan:
        st.warning("Rapor için önce plan oluştur.")
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Vardiya satırı", len(plan.get("shift_plan", pd.DataFrame())))
    with c2:
        st.metric("Uçak ataması", len(plan.get("flight_assignments", pd.DataFrame())))
    with c3:
        st.metric("Servis satırı", len(plan.get("service_plan", pd.DataFrame())))

    excel_bytes = build_excel_report(plan, st.session_state.departures, st.session_state.staff, st.session_state.services, st.session_state.leave_df)
    st.download_button(
        "Excel Raporu İndir",
        data=excel_bytes,
        file_name="YHM_Shift_20_Hafta_Raporu.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.markdown("#### Rapor Ön İzleme")
    tabs = st.tabs(["Vardiya", "Servis", "Uçak", "Uyarılar"])
    with tabs[0]: display_table(plan.get("shift_plan", pd.DataFrame()), "r_shift", 440)
    with tabs[1]: display_table(plan.get("service_plan", pd.DataFrame()), "r_service", 440)
    with tabs[2]: display_table(plan.get("flight_assignments", pd.DataFrame()), "r_flight", 440)
    with tabs[3]: display_table(plan.get("warnings", pd.DataFrame()), "r_warn", 440)


def build_excel_report(plan: Dict[str, pd.DataFrame], departures: pd.DataFrame, staff: pd.DataFrame, services: pd.DataFrame, leave_df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        sheets = {
            "Vardiya Planı": plan.get("shift_plan", pd.DataFrame()),
            "Uçak Atamaları": plan.get("flight_assignments", pd.DataFrame()),
            "Counter": plan.get("counter_assignments", pd.DataFrame()),
            "Servis Listesi": plan.get("service_plan", pd.DataFrame()),
            "İş Yükü": plan.get("workload", pd.DataFrame()),
            "Uyarılar": plan.get("warnings", pd.DataFrame()),
            "Departure": departures.copy(),
            "Personel": staff.copy(),
            "Servis Tanım": services.copy(),
            "İzin_DO": leave_df.copy(),
        }
        for name, df in sheets.items():
            safe = df.copy()
            for col in safe.columns:
                if pd.api.types.is_datetime64_any_dtype(safe[col]):
                    safe[col] = safe[col].dt.strftime("%d.%m.%Y %H:%M")
            safe.to_excel(writer, sheet_name=name[:31], index=False)
            ws = writer.book[name[:31]]
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            for column_cells in ws.columns:
                max_length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
                ws.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 48)
    return output.getvalue()


def data_quality_page() -> None:
    topbar()
    st.markdown("### Veri Kontrol Merkezi")
    deps = st.session_state.departures
    staff = st.session_state.staff
    services = st.session_state.services
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Departure", len(deps))
        if not deps.empty:
            st.write("Tarih aralığı:", f"{min(deps['op_date'])} → {max(deps['op_date'])}")
    with c2:
        st.metric("Personel", len(staff))
        st.write("Supervisor:", int(staff["is_supervisor"].sum()) if "is_supervisor" in staff else 0)
    with c3:
        st.metric("Servis tanımı", len(services))
        st.write("Güzergah:", services["route"].nunique() if not services.empty else 0)

    st.markdown("#### Hızlı Kontroller")
    checks = []
    if not deps.empty:
        checks.append({"check": "STD boş satır", "result": int(deps["std"].isna().sum())})
        checks.append({"check": "Pool uçuş sayısı", "result": int(deps["pool_flight"].sum())})
        checks.append({"check": "Etihad/özel yetkinlik uçuşu", "result": int(deps["special_required"].sum())})
    checks.append({"check": "ETD yetkili personel", "result": int(staff["special_airlines"].astype(str).str.upper().str.contains("ETD|ETIHAD", regex=True).sum())})
    checks.append({"check": "Aktif olmayan personel", "result": int((~staff["active"]).sum())})
    display_table(pd.DataFrame(checks), "checks", 260)


def main() -> None:
    st.set_page_config(page_title="YHM-Shift", page_icon="✈️", layout="wide")
    inject_css()
    init_state()

    with st.sidebar:
        st.image(str(asset_path("celebi_logo.png")), use_container_width=True)
        st.markdown("## YHM-Shift")
        page = st.radio(
            "Modül",
            ["Ana Sayfa", "Planlama", "Yönetim Paneli", "Disruption", "Raporlama", "Veri Kontrol"],
            label_visibility="collapsed",
        )
        st.markdown("---")
        st.caption("v1.0 • Streamlit + Pandas + optimizasyon skoru")

    if page == "Ana Sayfa":
        home_page()
    elif page == "Planlama":
        planning_page()
    elif page == "Yönetim Paneli":
        management_page()
    elif page == "Disruption":
        disruption_page()
    elif page == "Raporlama":
        reports_page()
    elif page == "Veri Kontrol":
        data_quality_page()


if __name__ == "__main__":
    main()
