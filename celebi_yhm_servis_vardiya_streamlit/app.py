import base64
import math
import re
from collections import deque
from datetime import datetime, date, time, timedelta
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
    HAS_AGGRID = True
except Exception:
    HAS_AGGRID = False

APP_TITLE = "YHM-Shift | Akıllı Vardiya ve Servis Planlama"
NAVY = "#071C35"
NAVY_2 = "#0B2E59"
LIGHT = "#F6F9FC"
BORDER = "#D9E3F0"
ASSET_DIR = Path(".")
CACHE_DIR = Path(".yhm_assets")
CACHE_DIR.mkdir(exist_ok=True)

PLANE_FILES = [
    "luftansha(1).png",
    "sv(1).jpg",
    "uzb(1).png",
    "ethiad(1).jpg",
    "emirates(1).jpg",
]
LOGO_FILE = "celebi_logo.png(1).png"

DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
ROUTES = ["ARN", "ATS", "AVC", "BAG", "BAH", "BHC", "BAY", "BEY", "BOL", "ESY", "HAL", "MAG", "SEF", "SUL", "AKZ"]
POOL_FLIGHTS = {"UZB", "IAW", "DAH", "FAD", "RAM", "BRU", "AWG"}
SPECIAL_FLIGHT_RULES = {
    "ETD": ["Meral Yunus", "Tansu Bosnak"],
    "ETIHAD": ["Meral Yunus", "Tansu Bosnak"],
    "EY": ["Meral Yunus", "Tansu Bosnak"],
}

SHIFT_TEMPLATES = [
    {"kod": "S1", "baslangic": "02:30", "bitis": "10:30"},
    {"kod": "S2", "baslangic": "04:30", "bitis": "12:30"},
    {"kod": "S3", "baslangic": "06:30", "bitis": "14:30"},
    {"kod": "S4", "baslangic": "08:30", "bitis": "16:30"},
    {"kod": "S5", "baslangic": "10:30", "bitis": "18:30"},
    {"kod": "S6", "baslangic": "12:30", "bitis": "20:30"},
    {"kod": "S7", "baslangic": "14:30", "bitis": "22:30"},
    {"kod": "S8", "baslangic": "16:30", "bitis": "00:30"},
    {"kod": "S9", "baslangic": "20:30", "bitis": "04:30"},
]

SERVICE_TIMES = ["00:30", "02:30", "04:30", "06:30", "08:30", "10:30", "12:30", "14:30", "16:30", "18:30", "20:30", "22:30"]


def to_time(value: str) -> time:
    return datetime.strptime(str(value).strip(), "%H:%M").time()


def day_start(base_date: date, day_name: str) -> datetime:
    return datetime.combine(base_date + timedelta(days=DAYS.index(day_name)), time(0, 0))


def build_dt(base_date: date, day_name: str, hhmm: str) -> datetime:
    return datetime.combine(base_date + timedelta(days=DAYS.index(day_name)), to_time(hhmm))


def shift_interval(base_date: date, day_name: str, start_hhmm: str, end_hhmm: str):
    start_dt = build_dt(base_date, day_name, start_hhmm)
    end_dt = build_dt(base_date, day_name, end_hhmm)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def fmt_dt(dt: datetime) -> str:
    day_diff = (dt.date() - st.session_state.week_start).days if "week_start" in st.session_state else 0
    suffix = "+1" if dt.time() < time(8, 0) and day_diff > 0 else ""
    return dt.strftime("%H:%M") + suffix


def hours_between(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / 3600, 2)


@st.cache_data(show_spinner=False)
def clean_background_to_png(path_str: str) -> str:
    src = Path(path_str)
    if not src.exists():
        return ""
    out = CACHE_DIR / f"clean_{src.stem}.png"
    if out.exists():
        return str(out)

    img = Image.open(src).convert("RGBA")
    arr = np.array(img)
    rgb = arr[:, :, :3].astype(np.int16)
    mean = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)

    # Sadece kenara bağlı gri/beyaz kareli arka planı siler; uçağın gövdesini korumaya çalışır.
    candidate = (mean > 205) & (chroma < 28)
    h, w = candidate.shape
    visited = np.zeros_like(candidate, dtype=bool)
    q = deque()

    for x in range(w):
        if candidate[0, x]:
            q.append((0, x))
            visited[0, x] = True
        if candidate[h - 1, x]:
            q.append((h - 1, x))
            visited[h - 1, x] = True
    for y in range(h):
        if candidate[y, 0]:
            q.append((y, 0))
            visited[y, 0] = True
        if candidate[y, w - 1]:
            q.append((y, w - 1))
            visited[y, w - 1] = True

    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and candidate[ny, nx] and not visited[ny, nx]:
                visited[ny, nx] = True
                q.append((ny, nx))

    arr[:, :, 3] = np.where(visited, 0, arr[:, :, 3])
    Image.fromarray(arr).save(out)
    return str(out)


@st.cache_data(show_spinner=False)
def image_as_base64(path_str: str, clean_plane: bool = False) -> str:
    path = Path(path_str)
    if clean_plane:
        cleaned = clean_background_to_png(str(path))
        if cleaned:
            path = Path(cleaned)
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def render_css():
    logo_path = ASSET_DIR / LOGO_FILE
    logo_b64 = image_as_base64(str(logo_path)) if logo_path.exists() else ""
    st.markdown(
        f"""
        <style>
        .stApp {{
            background: radial-gradient(circle at top left, #ffffff 0%, #f6f9fc 42%, #edf3fa 100%);
        }}
        h1, h2, h3, h4, p, label, span, div {{ color: {NAVY}; }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {NAVY} 0%, {NAVY_2} 100%);
        }}
        [data-testid="stSidebar"] * {{ color: white !important; }}
        .block-container {{ padding-top: 1.5rem; max-width: 1350px; }}
        .hero-card, .metric-card, .panel-card {{
            background: rgba(255,255,255,.92);
            border: 1px solid {BORDER};
            border-radius: 24px;
            padding: 24px;
            box-shadow: 0 18px 45px rgba(7, 28, 53, .08);
            backdrop-filter: blur(8px);
        }}
        .hero-title {{ font-size: 42px; font-weight: 850; margin-bottom: 8px; color: {NAVY}; }}
        .hero-subtitle {{ font-size: 17px; line-height: 1.6; color: #334E68; }}
        .navy-button a, .stButton > button {{
            background: {NAVY} !important;
            color: white !important;
            border: 1px solid {NAVY} !important;
            border-radius: 14px !important;
            padding: .65rem 1.1rem !important;
            font-weight: 700 !important;
        }}
        .stButton > button:hover {{
            background: white !important;
            color: {NAVY} !important;
            border: 1px solid {NAVY} !important;
        }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 8px; }}
        .stTabs [data-baseweb="tab"] {{
            background: white;
            border: 1px solid {BORDER};
            border-radius: 14px 14px 0 0;
            padding: 10px 18px;
            color: {NAVY};
        }}
        .plane-bg {{
            position: fixed;
            inset: 0;
            overflow: hidden;
            pointer-events: none;
            z-index: 0;
        }}
        .plane-bg img {{
            position: absolute;
            width: 300px;
            opacity: .105;
            filter: drop-shadow(0 8px 16px rgba(7,28,53,.15));
            animation-timing-function: linear;
            animation-iteration-count: infinite;
        }}
        .plane1 {{ top: 11%; left: -28%; animation-name: fly-right; animation-duration: 37s; }}
        .plane2 {{ top: 38%; left: -40%; animation-name: fly-right; animation-duration: 50s; animation-delay: 8s; width: 420px !important; }}
        .plane3 {{ top: 72%; left: -35%; animation-name: fly-right; animation-duration: 44s; animation-delay: 15s; }}
        @keyframes fly-right {{
            0% {{ transform: translateX(0) translateY(0) rotate(0deg); }}
            50% {{ transform: translateX(70vw) translateY(-20px) rotate(2deg); }}
            100% {{ transform: translateX(145vw) translateY(0) rotate(0deg); }}
        }}
        section.main > div {{ position: relative; z-index: 1; }}
        .small-muted {{ color: #627D98; font-size: 13px; }}
        .risk {{ background:#fff; border-left: 5px solid {NAVY}; padding: 12px; border-radius: 12px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    if logo_b64:
        st.sidebar.markdown(
            f"<div style='text-align:center;margin:8px 0 20px 0;'><img src='data:image/png;base64,{logo_b64}' style='max-width:180px;background:white;border-radius:16px;padding:10px;'></div>",
            unsafe_allow_html=True,
        )


def render_planes():
    tags = []
    for i, f in enumerate(PLANE_FILES[:3], start=1):
        p = ASSET_DIR / f
        b64 = image_as_base64(str(p), clean_plane=True) if p.exists() else ""
        if b64:
            tags.append(f"<img class='plane{i}' src='data:image/png;base64,{b64}'>")
    if tags:
        st.markdown(f"<div class='plane-bg'>{''.join(tags)}</div>", unsafe_allow_html=True)


def show_grid(df: pd.DataFrame, key: str, editable: bool = False, height: int = 390) -> pd.DataFrame:
    if df is None or df.empty:
        st.info("Gösterilecek kayıt yok.")
        return pd.DataFrame()
    if HAS_AGGRID:
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_default_column(filter=True, sortable=True, resizable=True, editable=editable, wrapText=True, autoHeight=True)
        gb.configure_grid_options(domLayout="normal")
        response = AgGrid(
            df,
            gridOptions=gb.build(),
            height=height,
            theme="balham",
            update_mode=GridUpdateMode.MODEL_CHANGED,
            allow_unsafe_jscode=True,
            key=key,
        )
        return pd.DataFrame(response["data"])
    if editable:
        return st.data_editor(df, num_rows="dynamic", use_container_width=True, height=height, key=key)
    st.dataframe(df, use_container_width=True, height=height)
    return df


def seed_employees() -> pd.DataFrame:
    names = [
        "Meral Yunus", "Tansu Bosnak", "Ahmet Yılmaz", "Mehmet Kaya", "Ayşe Demir", "Fatma Şahin", "Ali Çelik",
        "Zeynep Arslan", "Emre Koç", "Elif Aydın", "Burak Öz", "Seda Kılıç", "Can Aksoy", "Ece Yıldız",
        "Mustafa Kurt", "Derya Polat", "Onur Taş", "İrem Güneş", "Kerem Uçar", "Buse Er", "Murat Can",
        "Nazlı Bulut", "Selin Deniz", "Hakan Tekin", "Yasemin Boz", "Serkan Eren", "Cemre Aslan", "Okan Bilgin",
        "Gizem Yalçın", "Barış Çınar", "Melis Kara", "Tolga Şen", "Pelin Uslu", "Deniz Korkmaz", "Arda Turan",
        "Cansu Duman", "Umut Sarı", "Nisa Özcan", "Furkan Acar", "Esra Kaplan", "Kaan Yüce", "Gökçe Avcı",
        "Berkay Yaman", "Dilara Ateş", "Sinem Uğur", "Eren Baş", "İlayda Keskin", "Orhan Yıldırım", "Tuğçe Kalkan",
    ]
    rows = []
    for i, name in enumerate(names):
        role = "Check-in"
        quals = ["Check-in"]
        if i in [0, 1, 2, 7, 14, 21, 28, 35]:
            role = "S"
            quals = ["S", "L", "Check-in"]
        elif i in [3, 8, 15, 22, 29, 36, 43]:
            role = "L"
            quals = ["L", "Check-in"]
        if name in ["Meral Yunus", "Tansu Bosnak"]:
            quals += ["ETD", "ETIHAD", "EY"]
        rows.append(
            {
                "isim": name,
                "guzergah": ROUTES[i % len(ROUTES)],
                "sozlesme": "Part-time" if i in [10, 17, 24, 31, 38, 45] else "Full-time",
                "rol": role,
                "yetkinlikler": ",".join(sorted(set(quals))),
                "aktif": True,
            }
        )
    return pd.DataFrame(rows)


def seed_flights() -> pd.DataFrame:
    base = [
        ("UZB251", "UZB", "10:20", "A11", 155),
        ("IAW307", "IAW", "11:45", "B04", 170),
        ("EY096", "ETD", "12:55", "C02", 230),
        ("SV264", "SV", "14:10", "A15", 210),
        ("EK118", "EK", "16:30", "D08", 280),
        ("DLH1301", "DLH", "18:20", "E03", 190),
    ]
    rows = []
    for d_i, day in enumerate(DAYS):
        for j, (code, airline, dep, gate, pax) in enumerate(base):
            dep_dt = (datetime.combine(date(2026, 1, 1), to_time(dep)) + timedelta(minutes=(d_i % 3) * 10 + j * 3)).strftime("%H:%M")
            rows.append(
                {
                    "gun": day,
                    "sefer_kodu": code,
                    "havayolu": airline,
                    "kalkis": dep_dt,
                    "gate": gate,
                    "pax": pax,
                    "ekip_sayisi": 6 if pax >= 180 else 5,
                }
            )
    return pd.DataFrame(rows)


def seed_requests(employees: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"isim": employees.iloc[5]["isim"], "gun": "Salı", "talep": "DO", "not": "Haftalık izin"},
            {"isim": employees.iloc[12]["isim"], "gun": "Perşembe", "talep": "Yıllık İzin", "not": "Plan dışı"},
        ]
    )


def init_state():
    if "employees" not in st.session_state:
        st.session_state.employees = seed_employees()
    if "flights" not in st.session_state:
        st.session_state.flights = seed_flights()
    if "requests" not in st.session_state:
        st.session_state.requests = seed_requests(st.session_state.employees)
    if "week_start" not in st.session_state:
        st.session_state.week_start = date.today()
    if "plan" not in st.session_state:
        st.session_state.plan = {}


def has_qualification(emp: pd.Series, flight_airline: str) -> bool:
    quals = {q.strip().upper() for q in str(emp.get("yetkinlikler", "")).split(",") if q.strip()}
    airline = str(flight_airline).upper().strip()
    if airline in POOL_FLIGHTS:
        return True
    if airline in SPECIAL_FLIGHT_RULES or airline in {"ETD", "EY", "ETIHAD"}:
        return emp["isim"] in SPECIAL_FLIGHT_RULES.get(airline, SPECIAL_FLIGHT_RULES.get("ETD", [])) or airline in quals
    return True


def is_supervisor(emp: pd.Series) -> bool:
    quals = {q.strip().upper() for q in str(emp.get("yetkinlikler", "")).split(",") if q.strip()}
    return str(emp.get("rol", "")).upper() == "S" or "S" in quals


def request_lookup(requests: pd.DataFrame):
    lookup = set()
    for _, r in requests.iterrows():
        if str(r.get("talep", "")).strip():
            lookup.add((str(r.get("isim", "")).strip(), str(r.get("gun", "")).strip()))
    return lookup


def service_for_shift(day_name: str, start: str, end: str):
    return f"{day_name} {start}", f"{day_name} {end}"


def create_shift_plan(employees: pd.DataFrame, requests: pd.DataFrame, base_date: date) -> pd.DataFrame:
    req = request_lookup(requests)
    active = employees[employees["aktif"].astype(bool)].copy()
    rows = []

    for day_i, day in enumerate(DAYS):
        available = active[~active["isim"].apply(lambda x: (x, day) in req)].copy()
        for route_i, route in enumerate(ROUTES):
            route_people = available[available["guzergah"] == route].copy().sort_values(["rol", "isim"], ascending=[False, True])
            if route_people.empty:
                continue
            # Aynı güzergahı en az 4 kişilik bloklar halinde aynı servis saatine toplamaya çalışır.
            people = route_people.to_dict("records")
            chunk_size = 4
            for chunk_no, start_idx in enumerate(range(0, len(people), chunk_size)):
                chunk = people[start_idx:start_idx + chunk_size]
                template = SHIFT_TEMPLATES[(route_i + day_i + chunk_no) % len(SHIFT_TEMPLATES)]
                s_dt, e_dt = shift_interval(base_date, day, template["baslangic"], template["bitis"])
                for emp in chunk:
                    paid_hours = max(0, hours_between(s_dt, e_dt) - 1)
                    if emp["sozlesme"] == "Part-time" and paid_hours > 8:
                        paid_hours = 8
                    rows.append(
                        {
                            "gun": day,
                            "isim": emp["isim"],
                            "guzergah": emp["guzergah"],
                            "sozlesme": emp["sozlesme"],
                            "rol": emp["rol"],
                            "vardiya_kodu": template["kod"],
                            "giris": template["baslangic"],
                            "cikis": template["bitis"],
                            "yemek_molasi": "1 saat",
                            "ucretli_saat": paid_hours,
                            "gelis_servisi": f"{emp['guzergah']} {template['baslangic']}",
                            "donus_servisi": f"{emp['guzergah']} {template['bitis']}",
                            "gorevler": "",
                            "uyari": "",
                        }
                    )
        # Talep/izinli personeli ayrıca göster.
        for _, emp in active.iterrows():
            if (emp["isim"], day) in req:
                talep = requests[(requests["isim"] == emp["isim"]) & (requests["gun"] == day)]["talep"].iloc[0]
                rows.append(
                    {
                        "gun": day,
                        "isim": emp["isim"],
                        "guzergah": emp["guzergah"],
                        "sozlesme": emp["sozlesme"],
                        "rol": emp["rol"],
                        "vardiya_kodu": talep,
                        "giris": "-",
                        "cikis": "-",
                        "yemek_molasi": "-",
                        "ucretli_saat": 0,
                        "gelis_servisi": "-",
                        "donus_servisi": "-",
                        "gorevler": talep,
                        "uyari": "Planlama dışı",
                    }
                )
    shifts = pd.DataFrame(rows)
    return enforce_weekly_limits(shifts)


def enforce_weekly_limits(shifts: pd.DataFrame) -> pd.DataFrame:
    if shifts.empty:
        return shifts
    shifts = shifts.copy()
    totals = shifts.groupby(["isim", "sozlesme"], as_index=False)["ucretli_saat"].sum()
    warn_map = {}
    for _, r in totals.iterrows():
        limit = 25 if r["sozlesme"] == "Part-time" else 50
        minimum = 40 if r["sozlesme"] == "Full-time" else 0
        warns = []
        if r["ucretli_saat"] > limit:
            warns.append(f"Haftalık saat üst sınırı aşıldı: {r['ucretli_saat']}h/{limit}h")
        if r["sozlesme"] == "Full-time" and r["ucretli_saat"] < minimum:
            warns.append(f"Full-time minimum saat eksik: {r['ucretli_saat']}h/{minimum}h")
        if warns:
            warn_map[r["isim"]] = " | ".join(warns)
    if warn_map:
        shifts["uyari"] = shifts.apply(lambda x: (str(x["uyari"]) + " | " + warn_map.get(x["isim"], "")).strip(" |"), axis=1)
    return shifts


def task_interval_for_flight(base_date: date, day: str, departure_hhmm: str):
    dep = build_dt(base_date, day, departure_hhmm)
    report = dep - timedelta(minutes=95)
    release = dep + timedelta(minutes=30)
    return report, dep, release


def assign_flights(employees: pd.DataFrame, flights: pd.DataFrame, shifts: pd.DataFrame, base_date: date):
    assignments = []
    alerts = []
    task_book = {name: [] for name in employees["isim"].tolist()}
    flight_counts = {name: 0 for name in employees["isim"].tolist()}

    shift_lookup = shifts[(shifts["giris"] != "-") & (shifts["cikis"] != "-")].copy()
    emp_by_name = employees.set_index("isim")

    for _, fl in flights.sort_values(["gun", "kalkis"]).iterrows():
        day = fl["gun"]
        report, dep, release = task_interval_for_flight(base_date, day, fl["kalkis"])
        team_size = int(fl.get("ekip_sayisi", 5)) if not pd.isna(fl.get("ekip_sayisi", 5)) else 5
        airline = str(fl["havayolu"]).upper().strip()

        day_shifts = shift_lookup[shift_lookup["gun"] == day].copy()
        available_names = []
        for _, s in day_shifts.iterrows():
            s_start, s_end = shift_interval(base_date, day, s["giris"], s["cikis"])
            if s_start <= report and release <= s_end:
                overlaps = False
                for a, b in task_book.get(s["isim"], []):
                    if not (release <= a or report >= b):
                        overlaps = True
                        break
                if not overlaps:
                    available_names.append(s["isim"])

        candidate_rows = []
        for name in available_names:
            emp = emp_by_name.loc[name]
            if has_qualification(emp, airline):
                candidate_rows.append(emp)

        selected = []
        # Pool uçaklarında en az 1 Supervisor zorunlu.
        if airline in POOL_FLIGHTS:
            supervisors = [c for c in candidate_rows if is_supervisor(c)]
            supervisors.sort(key=lambda e: (flight_counts.get(e["isim"], 0), e["isim"]))
            if supervisors:
                selected.append(supervisors[0])
            else:
                alerts.append({"gun": day, "sefer": fl["sefer_kodu"], "uyari": "Pool uçuşu için uygun Supervisor bulunamadı."})

        # Özel yetkinlik uçuşları için önce özel yetkiliyi seç.
        if airline in SPECIAL_FLIGHT_RULES or airline in {"EY", "ETD", "ETIHAD"}:
            special_names = SPECIAL_FLIGHT_RULES.get(airline, SPECIAL_FLIGHT_RULES.get("ETD", []))
            specials = [c for c in candidate_rows if c["isim"] in special_names or airline in str(c.get("yetkinlikler", "")).upper()]
            specials.sort(key=lambda e: (flight_counts.get(e["isim"], 0), e["isim"]))
            if specials and all(x["isim"] != specials[0]["isim"] for x in selected):
                selected.append(specials[0])
            if not specials:
                alerts.append({"gun": day, "sefer": fl["sefer_kodu"], "uyari": "Özel yetkinlikli personel bulunamadı."})

        remaining = [c for c in candidate_rows if all(c["isim"] != s["isim"] for s in selected)]
        remaining.sort(key=lambda e: (flight_counts.get(e["isim"], 0), 0 if is_supervisor(e) else 1, e["isim"]))
        selected.extend(remaining[: max(0, team_size - len(selected))])

        if len(selected) < team_size:
            alerts.append(
                {
                    "gun": day,
                    "sefer": fl["sefer_kodu"],
                    "uyari": f"Ekip eksik: gereken {team_size}, bulunan {len(selected)}. Vardiya veya servis saati değiştirilmeli.",
                }
            )

        for order_no, emp in enumerate(selected[:team_size], start=1):
            name = emp["isim"]
            task_book[name].append((report, release))
            flight_counts[name] = flight_counts.get(name, 0) + 1
            assignments.append(
                {
                    "gun": day,
                    "sefer_kodu": fl["sefer_kodu"],
                    "havayolu": fl["havayolu"],
                    "gate": fl["gate"],
                    "kalkis": fl["kalkis"],
                    "hazir_olma": report.strftime("%H:%M"),
                    "gorev_bitis": release.strftime("%H:%M"),
                    "personel": name,
                    "rol": emp["rol"],
                    "sira": order_no,
                }
            )

    assign_df = pd.DataFrame(assignments)
    alert_df = pd.DataFrame(alerts)
    if not assign_df.empty:
        gorev_map = assign_df.groupby(["gun", "personel"])["sefer_kodu"].apply(lambda x: ", ".join(x)).to_dict()
        shifts = shifts.copy()
        shifts["gorevler"] = shifts.apply(
            lambda r: gorev_map.get((r["gun"], r["isim"]), r["gorevler"]), axis=1
        )
    return assign_df, shifts, alert_df, task_book


def analyze_service_quota(shifts: pd.DataFrame) -> pd.DataFrame:
    active = shifts[(shifts["giris"] != "-") & (shifts["cikis"] != "-")].copy()
    if active.empty:
        return pd.DataFrame()
    arr = active.groupby(["gun", "guzergah", "giris"], as_index=False).agg(personel_sayisi=("isim", "count"), personeller=("isim", lambda x: ", ".join(x)))
    arr["yon"] = "Geliş"
    arr = arr.rename(columns={"giris": "servis_saati"})
    dep = active.groupby(["gun", "guzergah", "cikis"], as_index=False).agg(personel_sayisi=("isim", "count"), personeller=("isim", lambda x: ", ".join(x)))
    dep["yon"] = "Dönüş"
    dep = dep.rename(columns={"cikis": "servis_saati"})
    service = pd.concat([arr, dep], ignore_index=True)
    service["durum"] = np.where(service["personel_sayisi"] >= 4, "Servis kalkabilir", "Risk: 4 kişi altında")
    service["onerilen_aksiyon"] = service.apply(service_suggestion, axis=1)
    return service[["gun", "yon", "guzergah", "servis_saati", "personel_sayisi", "durum", "onerilen_aksiyon", "personeller"]]


def service_suggestion(row) -> str:
    if row["personel_sayisi"] >= 4:
        return "Uygun"
    return f"Aynı güzergâhta {row['servis_saati']} servisi için en az {4 - int(row['personel_sayisi'])} kişi daha gerekir. Alternatif: aynı güzergâhta bir önceki/sonraki vardiya saatine kaydır veya görevini vardiyada boş yetkin personele devret."


def check_rest_constraints(shifts: pd.DataFrame, base_date: date) -> pd.DataFrame:
    rows = []
    valid = shifts[(shifts["giris"] != "-") & (shifts["cikis"] != "-")].copy()
    for name, grp in valid.groupby("isim"):
        intervals = []
        for _, r in grp.iterrows():
            intervals.append((*shift_interval(base_date, r["gun"], r["giris"], r["cikis"]), r["gun"]))
        intervals.sort(key=lambda x: x[0])
        for prev, cur in zip(intervals, intervals[1:]):
            rest = hours_between(prev[1], cur[0])
            if rest < 11:
                rows.append({"isim": name, "onceki_gun": prev[2], "sonraki_gun": cur[2], "dinlenme_saati": rest, "durum": "11 saat altı"})
    return pd.DataFrame(rows)


def run_planning(employees: pd.DataFrame, flights: pd.DataFrame, requests: pd.DataFrame, base_date: date):
    shifts = create_shift_plan(employees, requests, base_date)
    flight_assignments, shifts, alerts, task_book = assign_flights(employees, flights, shifts, base_date)
    service = analyze_service_quota(shifts)
    rest = check_rest_constraints(shifts, base_date)
    return {
        "shifts": shifts,
        "flight_assignments": flight_assignments,
        "service": service,
        "alerts": alerts,
        "rest": rest,
        "task_book": task_book,
    }


def excel_bytes(plan: dict) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet, df in [
            ("Personel_Vardiya", plan.get("shifts", pd.DataFrame())),
            ("Ucak_Atamalari", plan.get("flight_assignments", pd.DataFrame())),
            ("Servis_Plani", plan.get("service", pd.DataFrame())),
            ("Uyarilar", plan.get("alerts", pd.DataFrame())),
            ("Dinlenme_Kontrol", plan.get("rest", pd.DataFrame())),
        ]:
            if df is not None and not df.empty:
                df.to_excel(writer, sheet_name=sheet[:31], index=False)
    return output.getvalue()


def home_page():
    logo_b64 = image_as_base64(str(ASSET_DIR / LOGO_FILE)) if (ASSET_DIR / LOGO_FILE).exists() else ""
    col1, col2 = st.columns([1.7, 1])
    with col1:
        st.markdown(
            """
            <div class='hero-card'>
                <div class='hero-title'>Akıllı Vardiya ve Servis Planlama Sistemi</div>
                <div class='hero-subtitle'>
                    YHM-Shift; personel vardiyası, uçak görev ataması, servis kotası, izin/DO talepleri ve delay durumlarında görev devri önerisini tek panelde toplar.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        if logo_b64:
            st.markdown(
                f"<div class='hero-card' style='text-align:center'><img src='data:image/png;base64,{logo_b64}' style='width:230px;max-width:100%;'></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown("<div class='hero-card'><b>Çelebi logosu:</b> logo dosyasını aynı klasöre koy.</div>", unsafe_allow_html=True)

    st.write("")
    plan = st.session_state.get("plan", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aktif Personel", int(st.session_state.employees["aktif"].sum()))
    c2.metric("Haftalık Uçuş", len(st.session_state.flights))
    c3.metric("Güzergâh", len(ROUTES))
    c4.metric("Plan Durumu", "Hazır" if plan else "Oluşturulmadı")

    st.markdown("### Haftalık özet")
    if plan:
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Atanan uçak görevi", len(plan.get("flight_assignments", pd.DataFrame())))
        service_risk = plan.get("service", pd.DataFrame())
        risk_count = 0 if service_risk.empty else int((service_risk["durum"] != "Servis kalkabilir").sum())
        col_b.metric("Servis riski", risk_count)
        rest_risk = plan.get("rest", pd.DataFrame())
        col_c.metric("Dinlenme ihlali", 0 if rest_risk.empty else len(rest_risk))
    else:
        st.info("Planlama sayfasından haftalık planı oluşturduğunda özet burada görünecek.")


def planning_page():
    st.title("Planlama Sayfası")
    st.caption("Bu sayfa otomatik vardiya, uçak ekipleri ve servis kota kontrolünü üretir.")
    st.session_state.week_start = st.date_input("Hafta başlangıç tarihi", value=st.session_state.week_start)

    if st.button("Haftalık Planı Oluştur", type="primary"):
        st.session_state.plan = run_planning(
            st.session_state.employees,
            st.session_state.flights,
            st.session_state.requests,
            st.session_state.week_start,
        )
        st.success("Plan oluşturuldu. Aşağıdaki sekmelerden kontrol edebilirsin.")

    plan = st.session_state.get("plan", {})
    if not plan:
        st.warning("Henüz plan oluşturulmadı.")
        return

    shifts = plan.get("shifts", pd.DataFrame())
    flights = plan.get("flight_assignments", pd.DataFrame())
    service = plan.get("service", pd.DataFrame())
    alerts = plan.get("alerts", pd.DataFrame())
    rest = plan.get("rest", pd.DataFrame())

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Personel vardiyası", "Uçak atamaları", "Servis planı", "AI Delay önerisi", "Rapor indir"])
    with tab1:
        st.subheader("İsim isim gün gün vardiya listesi")
        day_filter = st.multiselect("Gün filtresi", DAYS, default=DAYS, key="shift_day_filter")
        show_grid(shifts[shifts["gun"].isin(day_filter)], "shift_grid", editable=False, height=520)
        if not rest.empty:
            st.error("11 saat dinlenme kuralı riski var.")
            show_grid(rest, "rest_grid", height=220)
    with tab2:
        st.subheader("Hangi uçağa kimler çıkacak?")
        show_grid(flights, "flight_grid", editable=False, height=520)
        if not alerts.empty:
            st.warning("Operasyonel uyarılar")
            show_grid(alerts, "alerts_grid", height=250)
    with tab3:
        st.subheader("Servis listesi ve 4 kişi kotası")
        show_grid(service, "service_grid", editable=False, height=540)
    with tab4:
        disruption_panel(plan)
    with tab5:
        st.download_button(
            "20. Hafta YHM Formatı Excel Raporu İndir",
            data=excel_bytes(plan),
            file_name="YHM_20_Hafta_Vardiya_Servis_Raporu.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.caption("Excel içinde Personel_Vardiya, Ucak_Atamalari, Servis_Plani, Uyarilar ve Dinlenme_Kontrol sayfaları bulunur.")


def disruption_panel(plan: dict):
    st.subheader("AI destekli delay / görev devri önerisi")
    fl = plan.get("flight_assignments", pd.DataFrame())
    shifts = plan.get("shifts", pd.DataFrame())
    if fl.empty:
        st.info("Önce uçak ataması oluşturulmalı.")
        return
    flight_options = fl[["gun", "sefer_kodu", "havayolu", "kalkis", "gate"]].drop_duplicates()
    labels = [f"{r.gun} | {r.sefer_kodu} | {r.kalkis} | Gate {r.gate}" for r in flight_options.itertuples()]
    selected_label = st.selectbox("Delay olan uçuş", labels)
    delay_min = st.number_input("Delay süresi / dakika", min_value=0, max_value=600, value=60, step=15)
    if st.button("Devir önerisi üret"):
        idx = labels.index(selected_label)
        row = flight_options.iloc[idx]
        suggestions = suggest_delay_replacements(row, delay_min, fl, shifts, st.session_state.employees, st.session_state.week_start)
        if suggestions.empty:
            st.success("Bu delay için görünen çakışma yok veya uygun değişiklik gerekmiyor.")
        else:
            show_grid(suggestions, "delay_suggestion_grid", height=360)


def suggest_delay_replacements(flight_row, delay_min: int, assignments: pd.DataFrame, shifts: pd.DataFrame, employees: pd.DataFrame, base_date: date) -> pd.DataFrame:
    day = flight_row["gun"]
    code = flight_row["sefer_kodu"]
    old_dep = build_dt(base_date, day, flight_row["kalkis"])
    new_release = old_dep + timedelta(minutes=delay_min + 30)
    affected = assignments[(assignments["gun"] == day) & (assignments["sefer_kodu"] == code)].copy()
    emp_index = employees.set_index("isim")
    rows = []

    for _, a in affected.iterrows():
        person = a["personel"]
        person_tasks = assignments[(assignments["gun"] == day) & (assignments["personel"] == person) & (assignments["sefer_kodu"] != code)].copy()
        conflict = False
        conflict_code = ""
        for _, t in person_tasks.iterrows():
            next_report, _, _ = task_interval_for_flight(base_date, day, t["kalkis"])
            if new_release > next_report:
                conflict = True
                conflict_code = t["sefer_kodu"]
                break
        if not conflict:
            continue

        role_needed = a["rol"]
        airline = str(a["havayolu"]).upper()
        old_report, _, _ = task_interval_for_flight(base_date, day, flight_row["kalkis"])
        candidates = []
        for _, s in shifts[(shifts["gun"] == day) & (shifts["giris"] != "-")].iterrows():
            if s["isim"] == person:
                continue
            emp = emp_index.loc[s["isim"]]
            if role_needed == "S" and not is_supervisor(emp):
                continue
            if not has_qualification(emp, airline):
                continue
            s_start, s_end = shift_interval(base_date, day, s["giris"], s["cikis"])
            if s_start <= old_report and new_release <= s_end:
                same_time_tasks = assignments[(assignments["gun"] == day) & (assignments["personel"] == s["isim"])]
                busy = False
                for _, bt in same_time_tasks.iterrows():
                    b_report, _, b_release = task_interval_for_flight(base_date, day, bt["kalkis"])
                    if not (new_release <= b_report or old_report >= b_release):
                        busy = True
                        break
                if not busy:
                    candidates.append(s)
        candidates = sorted(candidates, key=lambda x: (0 if x["guzergah"] == emp_index.loc[person]["guzergah"] else 1, x["isim"]))
        suggested = candidates[0]["isim"] if candidates else "Uygun kişi bulunamadı"
        rows.append(
            {
                "delay_ucusu": code,
                "etkilenen_personel": person,
                "cakisan_sonraki_gorev": conflict_code,
                "delay_sonrasi_bitis": new_release.strftime("%H:%M"),
                "onerilen_devir_personeli": suggested,
                "not": "Aynı vardiyada, uygun yetkinlikte ve boş görev aralığında kişi önerildi." if candidates else "Vardiya/güzergâh servis saati manuel revize edilmeli.",
            }
        )
    return pd.DataFrame(rows)


def management_page():
    st.title("Yönetim Paneli")
    st.caption("Personel, yetkinlik, uçuş ve izin/DO kayıtlarını buradan güncelleyebilirsin.")

    tab1, tab2, tab3 = st.tabs(["Personel & Yetkinlik", "Departure / Uçuşlar", "İzin ve DO"])
    with tab1:
        st.info("Yetkinlikler alanına S, L, Check-in, ETD gibi değerleri virgülle yaz. Örnek: S,L,Check-in,ETD")
        edited = show_grid(st.session_state.employees, "employees_edit", editable=True, height=520)
        if st.button("Personel listesini kaydet"):
            st.session_state.employees = edited.copy()
            st.success("Personel listesi kaydedildi.")
    with tab2:
        edited_flights = show_grid(st.session_state.flights, "flights_edit", editable=True, height=520)
        if st.button("Uçuş listesini kaydet"):
            st.session_state.flights = edited_flights.copy()
            st.success("Uçuş listesi kaydedildi.")
    with tab3:
        edited_req = show_grid(st.session_state.requests, "requests_edit", editable=True, height=360)
        if st.button("İzin/DO listesini kaydet"):
            st.session_state.requests = edited_req.copy()
            st.success("İzin/DO listesi kaydedildi.")


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="✈️", layout="wide")
    init_state()
    render_css()
    render_planes()

    page = st.sidebar.radio("Menü", ["Ana Sayfa", "Planlama Sayfası", "Yönetim Paneli"], index=0)
    st.sidebar.markdown("---")
    st.sidebar.caption("Tema: beyaz + lacivert. Turuncu detay yok.")

    if page == "Ana Sayfa":
        home_page()
    elif page == "Planlama Sayfası":
        planning_page()
    else:
        management_page()


if __name__ == "__main__":
    main()
