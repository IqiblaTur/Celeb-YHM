from __future__ import annotations

import base64
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import streamlit as st

from core import (
    add_service_plan,
    build_shift_plan,
    clean_columns,
    enrich_departures_with_requirements,
    parse_departures,
    parse_hakedis,
    parse_staff,
    read_csv_smart,
    recommend_delay_actions,
    to_excel_bytes,
)

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
ASSET_DIR = APP_DIR / "assets"
NAVY = "#061B3A"
BLUE = "#0B2C59"
LIGHT = "#F5F8FC"

st.set_page_config(
    page_title="Çelebi YHM Shift",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def img_to_base64(path: Path) -> str:
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def inject_css():
    logo_b64 = img_to_base64(ASSET_DIR / "celebi_logo.png")
    plane1 = img_to_base64(ASSET_DIR / "airplane_lufthansa_clean.png")
    plane2 = img_to_base64(ASSET_DIR / "airplane_uzb_clean.png")
    plane3 = img_to_base64(ASSET_DIR / "airplane_emirates_clean.png")
    st.markdown(
        f"""
        <style>
        @keyframes floatPlaneA {{
            0% {{ transform: translateX(-12vw) translateY(0px) rotate(-2deg); opacity: .06; }}
            45% {{ opacity: .16; }}
            100% {{ transform: translateX(110vw) translateY(-18px) rotate(-2deg); opacity: .04; }}
        }}
        @keyframes floatPlaneB {{
            0% {{ transform: translateX(105vw) translateY(0px) rotate(2deg); opacity: .05; }}
            50% {{ opacity: .14; }}
            100% {{ transform: translateX(-20vw) translateY(20px) rotate(2deg); opacity: .04; }}
        }}
        @keyframes fadeUp {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .stApp {{
            background:
                radial-gradient(circle at top left, rgba(11,44,89,0.10), transparent 30%),
                linear-gradient(180deg, #ffffff 0%, #f5f8fc 100%);
        }}
        .stApp:before {{
            content: "";
            position: fixed;
            top: 76px;
            left: 0;
            width: 280px;
            height: 110px;
            background-image: url(data:image/png;base64,{plane1});
            background-size: contain;
            background-repeat: no-repeat;
            animation: floatPlaneA 42s linear infinite;
            z-index: 0;
            pointer-events: none;
        }}
        .stApp:after {{
            content: "";
            position: fixed;
            bottom: 76px;
            left: 0;
            width: 340px;
            height: 120px;
            background-image: url(data:image/png;base64,{plane2});
            background-size: contain;
            background-repeat: no-repeat;
            animation: floatPlaneB 50s linear infinite;
            z-index: 0;
            pointer-events: none;
        }}
        .block-container {{ padding-top: 1.4rem; position: relative; z-index: 2; }}
        section[data-testid="stSidebar"] {{ background: linear-gradient(180deg, {NAVY} 0%, {BLUE} 100%); }}
        section[data-testid="stSidebar"] * {{ color: white !important; }}
        .hero-card {{
            position: relative;
            overflow: hidden;
            border-radius: 26px;
            padding: 34px;
            color: white;
            background: linear-gradient(135deg, #061B3A 0%, #0B2C59 58%, #123C73 100%);
            box-shadow: 0 20px 50px rgba(6, 27, 58, 0.22);
            animation: fadeUp .55s ease-out;
        }}
        .hero-card:after {{
            content: "";
            position: absolute;
            right: -40px;
            top: 18px;
            width: 420px;
            height: 170px;
            background-image: url(data:image/png;base64,{plane3});
            background-size: contain;
            background-repeat: no-repeat;
            opacity: .18;
        }}
        .hero-title {{ font-size: 40px; line-height: 1.1; font-weight: 800; margin-bottom: 8px; }}
        .hero-sub {{ max-width: 760px; font-size: 17px; opacity: .92; }}
        .small-logo {{
            width: 86px; height: 86px;
            background: white url(data:image/png;base64,{logo_b64}) center/contain no-repeat;
            border-radius: 18px;
            box-shadow: 0 10px 30px rgba(0,0,0,.12);
            margin-bottom: 18px;
        }}
        .metric-card {{
            background: rgba(255,255,255,.88);
            border: 1px solid rgba(6,27,58,.08);
            border-radius: 20px;
            padding: 18px 20px;
            box-shadow: 0 10px 26px rgba(6, 27, 58, .08);
        }}
        .metric-label {{ color: #526070; font-size: 13px; font-weight: 700; }}
        .metric-value {{ color: {NAVY}; font-size: 30px; font-weight: 850; margin-top: 4px; }}
        .section-title {{
            color: {NAVY};
            font-size: 24px;
            font-weight: 850;
            margin: 18px 0 8px 0;
        }}
        .info-box {{
            background: white;
            border-left: 5px solid {BLUE};
            border-radius: 16px;
            padding: 16px 18px;
            box-shadow: 0 8px 24px rgba(6, 27, 58, .07);
        }}
        div[data-testid="stMetric"] {{
            background: white;
            border-radius: 18px;
            padding: 14px 16px;
            box-shadow: 0 7px 20px rgba(6, 27, 58, .06);
            border: 1px solid rgba(6,27,58,.06);
        }}
        .stButton > button, .stDownloadButton > button {{
            border-radius: 14px !important;
            border: 0 !important;
            background: linear-gradient(135deg, {NAVY}, {BLUE}) !important;
            color: white !important;
            font-weight: 800 !important;
            min-height: 42px;
        }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 8px; }}
        .stTabs [data-baseweb="tab"] {{
            background: white;
            border-radius: 14px 14px 0 0;
            padding: 10px 16px;
            color: {NAVY};
            font-weight: 700;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def logo_header():
    col1, col2 = st.columns([0.12, 0.88])
    with col1:
        st.image(str(ASSET_DIR / "celebi_logo.png"), width=68)
    with col2:
        st.markdown("### Çelebi Akıllı Vardiya ve Lojistik Planlama Sistemi")
        st.caption("YHM operasyon, kontuar hakediş, yetkinlik ve servis planlama paneli")


def load_default_tables() -> Dict[str, pd.DataFrame]:
    departures_raw = read_csv_smart(DATA_DIR / "Departure.csv", sep=";")
    qualifications = read_csv_smart(DATA_DIR / "Qualifications.csv")
    hakedis = read_csv_smart(DATA_DIR / "hakedis.csv")
    service = read_csv_smart(DATA_DIR / "servis.csv")
    routes = read_csv_smart(DATA_DIR / "Guzergah.csv")
    return {
        "departures_raw": departures_raw,
        "qualifications_raw": qualifications,
        "hakedis_raw": hakedis,
        "service_raw": service,
        "routes_raw": routes,
    }


def prepare_session_tables(force_default: bool = False):
    if force_default or "tables" not in st.session_state:
        st.session_state.tables = load_default_tables()
    tables = st.session_state.tables
    deps = parse_departures(tables["departures_raw"])
    staff = parse_staff(tables["qualifications_raw"], tables["routes_raw"])
    hakedis = parse_hakedis(tables["hakedis_raw"])
    service = tables["service_raw"]
    st.session_state.departures = deps
    st.session_state.staff = staff
    st.session_state.hakedis = hakedis
    st.session_state.service = service


def upload_box(label: str, key: str, default_hint: str):
    uploaded = st.file_uploader(label, type=["csv", "xlsx", "xls"], key=key)
    if uploaded is not None:
        try:
            st.session_state.tables[key] = read_csv_smart(uploaded, sep=";" if "departure" in key.lower() else None)
            st.success(f"{label} yüklendi.")
        except Exception as exc:
            st.error(f"Dosya okunamadı: {exc}")
    else:
        st.caption(default_hint)


def table_preview(title: str, df: pd.DataFrame, rows: int = 8):
    with st.expander(title, expanded=False):
        st.dataframe(df.head(rows), width="stretch")
        st.caption(f"Satır: {len(df):,} | Kolon: {len(df.columns):,}")


def kpi_card(label: str, value: str):
    st.markdown(
        f"""<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>""",
        unsafe_allow_html=True,
    )


def home_page():
    deps = st.session_state.departures
    staff = st.session_state.staff
    service = st.session_state.service
    enriched = enrich_departures_with_requirements(deps) if not deps.empty else deps

    st.markdown(
        """
        <div class="hero-card">
            <div class="small-logo"></div>
            <div class="hero-title">Operasyon, Yetkinlik ve Servis Planlaması Tek Panelde</div>
            <div class="hero-sub">
                Departure listesi, Qualifications, hakediş kuralları ve güzergah verileri birleştirilerek
                haftalık uçuş/personel/servis planı üretir. Sistem manuel müdahale, servis doluluk kontrolü,
                DO/tatil talepleri ve delay önerileri için hazır prototip mantığı içerir.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Uçuş Sayısı", f"{len(deps):,}")
    with c2:
        kpi_card("Personel", f"{len(staff):,}")
    with c3:
        kpi_card("Hafta / Gün", f"{deps['std_dt'].dt.date.nunique() if not deps.empty else 0}")
    with c4:
        kpi_card("Servis Zamanı", f"{len(service):,}")

    st.markdown('<div class="section-title">Başlangıç Adımları</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="info-box">
        <b>1.</b> Veri Yönetimi bölümünde CSV/Excel dosyalarını kontrol et.<br>
        <b>2.</b> Personel Yönetimi bölümünde aktif/pasif, rota, full-time/part-time ve saat limitlerini düzenle.<br>
        <b>3.</b> Vardiya Paneli'nde tarih aralığı seçip planı oluştur.<br>
        <b>4.</b> Servis Paneli'nde 4 kişi kuralına göre servis veya toplu taşıma notlarını incele.<br>
        <b>5.</b> AI Öneri bölümünde delay/devir senaryosu üret.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not enriched.empty:
        st.markdown('<div class="section-title">En Yakın Uçuş Hakediş Özeti</div>', unsafe_allow_html=True)
        st.dataframe(
            enriched[["airline", "out_flight", "std", "aircraft_type", "pax_count", "counter_count", "required_staff", "rule_applied"]].head(12),
            width="stretch",
            hide_index=True,
        )


def data_page():
    logo_header()
    st.markdown('<div class="section-title">Veri Yönetimi</div>', unsafe_allow_html=True)
    st.info("Varsayılan örnek dosyalar ZIP içinde data klasöründe bulunur. Buradan yeni CSV/Excel yükleyerek aynı app içinde test edebilirsin.")

    c1, c2 = st.columns(2)
    with c1:
        upload_box("Departure.csv / uçuş listesi", "departures_raw", "Varsayılan Departure.csv kullanılıyor.")
        upload_box("Qualifications.csv / yetkinlik listesi", "qualifications_raw", "Varsayılan Qualifications.csv kullanılıyor.")
        upload_box("Hakediş.csv / kontuar kuralları", "hakedis_raw", "Varsayılan hakedis.csv kullanılıyor.")
    with c2:
        upload_box("Servis.csv / servis saatleri", "service_raw", "Varsayılan servis.csv kullanılıyor.")
        upload_box("Güzergah.csv / personel rota kodu", "routes_raw", "Varsayılan Guzergah.csv kullanılıyor.")
        if st.button("Örnek Dosyalara Geri Dön"):
            prepare_session_tables(force_default=True)
            st.rerun()

    prepare_session_tables()
    st.markdown('<div class="section-title">Okunan Dosya Önizlemeleri</div>', unsafe_allow_html=True)
    table_preview("Departure normalize edilmiş görünüm", st.session_state.departures)
    table_preview("Qualifications + Güzergah birleştirilmiş personel", st.session_state.staff)
    table_preview("Hakediş kuralları", st.session_state.hakedis)
    table_preview("Servis saatleri", st.session_state.service)


def personnel_page():
    logo_header()
    st.markdown('<div class="section-title">Personel Yönetimi</div>', unsafe_allow_html=True)
    staff = st.session_state.staff.copy()
    if staff.empty:
        st.warning("Personel verisi bulunamadı.")
        return
    st.caption("Buradan yeni personel ekleme, pasife alma, rota düzeltme, part-time/full-time ve saat limitleri düzenlenebilir. Değişiklikler bu oturumdaki planlamaya uygulanır.")
    editable_cols = ["name", "qualifications", "route", "employment_type", "max_weekly_hours", "is_active"]
    edited = st.data_editor(
        staff[editable_cols],
        width="stretch",
        num_rows="dynamic",
        column_config={
            "employment_type": st.column_config.SelectboxColumn("employment_type", options=["Full-time", "Part-time"]),
            "max_weekly_hours": st.column_config.NumberColumn("max_weekly_hours", min_value=1, max_value=60, step=1),
            "is_active": st.column_config.CheckboxColumn("is_active"),
        },
        key="staff_editor",
    )
    if st.button("Personel Değişikliklerini Uygula"):
        edited = edited.copy()
        edited["name_key"] = edited["name"].astype(str).str.upper()
        st.session_state.staff = edited
        st.success("Personel tablosu oturum için güncellendi.")


def requests_page():
    logo_header()
    st.markdown('<div class="section-title">DO / İzin / Tatil Talepleri</div>', unsafe_allow_html=True)
    staff = st.session_state.staff
    if "requests" not in st.session_state:
        st.session_state.requests = pd.DataFrame(columns=["name", "date", "status", "note"])

    default_new = pd.DataFrame({
        "name": [staff["name"].iloc[0] if not staff.empty else ""],
        "date": [date.today()],
        "status": ["DO"],
        "note": [""],
    })
    st.caption("Planlama sırasında DO/İzin/Tatil/Rapor statüsündeki personel ilgili gün için uygun aday listesinden çıkarılır.")
    edited_req = st.data_editor(
        st.session_state.requests if not st.session_state.requests.empty else default_new,
        width="stretch",
        num_rows="dynamic",
        column_config={
            "name": st.column_config.SelectboxColumn("name", options=staff["name"].tolist() if not staff.empty else []),
            "date": st.column_config.DateColumn("date"),
            "status": st.column_config.SelectboxColumn("status", options=["DO", "İzin", "Tatil", "Rapor", "Talep"]),
        },
        key="request_editor",
    )
    if st.button("Talepleri Kaydet"):
        st.session_state.requests = edited_req
        st.success("Talepler oturum için kaydedildi.")


def planning_page():
    logo_header()
    st.markdown('<div class="section-title">Vardiya Paneli</div>', unsafe_allow_html=True)
    deps = st.session_state.departures.copy()
    staff = st.session_state.staff.copy()
    if deps.empty or staff.empty:
        st.warning("Departure veya personel verisi eksik.")
        return

    min_date = deps["std_dt"].dt.date.min()
    max_date = deps["std_dt"].dt.date.max()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        start_date = st.date_input("Başlangıç", value=min_date, min_value=min_date, max_value=max_date)
    with c2:
        end_date = st.date_input("Bitiş", value=max_date, min_value=min_date, max_value=max_date)
    with c3:
        report_minutes = st.number_input("STD öncesi geliş/duty dk", min_value=60, max_value=240, value=150, step=15)
    with c4:
        debrief_minutes = st.number_input("STD sonrası kapanış dk", min_value=15, max_value=120, value=45, step=15)

    filtered = deps[(deps["std_dt"].dt.date >= start_date) & (deps["std_dt"].dt.date <= end_date)].copy()
    enriched = enrich_departures_with_requirements(filtered)
    st.dataframe(
        enriched[["airline", "out_flight", "std", "aircraft_type", "pax_count", "counter_count", "la_required", "required_staff", "requires_supervisor", "rule_applied"]],
        width="stretch",
        hide_index=True,
    )

    if st.button("Haftalık Planı Oluştur", type="primary"):
        assignments, flight_summary, warnings = build_shift_plan(
            filtered,
            st.session_state.staff,
            st.session_state.get("requests", pd.DataFrame()),
            report_minutes=int(report_minutes),
            debrief_minutes=int(debrief_minutes),
        )
        assignments_with_service, service_summary = add_service_plan(assignments, st.session_state.service)
        st.session_state.plan_assignments = assignments_with_service
        st.session_state.flight_summary = flight_summary
        st.session_state.service_summary = service_summary
        st.session_state.plan_warnings = warnings
        st.success("Plan oluşturuldu. Aşağıdaki sekmelerden kontrol edebilirsin.")

    show_plan_results()


def show_plan_results():
    assignments = st.session_state.get("plan_assignments", pd.DataFrame())
    flight_summary = st.session_state.get("flight_summary", pd.DataFrame())
    service_summary = st.session_state.get("service_summary", pd.DataFrame())
    warnings = st.session_state.get("plan_warnings", pd.DataFrame())
    if assignments.empty:
        return
    tab1, tab2, tab3, tab4 = st.tabs(["Personel Shift Tablosu", "Uçuş Özeti", "Servis Özeti", "Uyarılar & Export"])
    with tab1:
        display_cols = [
            "date", "name", "route", "role", "airline", "out_flight", "work_start", "work_end", "arrival_service_time", "arrival_note", "departure_service_time", "departure_note", "rule_applied"
        ]
        edited = st.data_editor(
            assignments[display_cols],
            width="stretch",
            num_rows="dynamic",
            key="assignment_editor",
        )
        st.caption("Bu tablo manuel müdahale içindir. Görev/personel değiştirip Excel'e aktarabilirsin.")
    with tab2:
        st.dataframe(flight_summary, width="stretch", hide_index=True)
    with tab3:
        st.dataframe(service_summary, width="stretch", hide_index=True)
    with tab4:
        if not warnings.empty:
            st.warning("Plan içinde kontrol edilmesi gereken uyarılar var.")
            st.dataframe(warnings, width="stretch", hide_index=True)
        else:
            st.success("Kritik atama uyarısı bulunmadı.")
        excel_bytes = to_excel_bytes({
            "Shift Plan": assignments.drop(columns=[c for c in ["work_start_dt", "work_end_dt", "arrival_service_dt", "departure_service_dt", "name_key"] if c in assignments.columns]),
            "Flight Summary": flight_summary,
            "Service Summary": service_summary,
            "Warnings": warnings,
        })
        st.download_button(
            "Excel Raporu İndir",
            excel_bytes,
            file_name="celebi_yhm_shift_plan.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        csv_bytes = assignments.to_csv(index=False).encode("utf-8-sig")
        st.download_button("CSV Shift Tablosu İndir", csv_bytes, file_name="celebi_yhm_shift_plan.csv", mime="text/csv")


def service_page():
    logo_header()
    st.markdown('<div class="section-title">Servis Paneli</div>', unsafe_allow_html=True)
    assignments = st.session_state.get("plan_assignments", pd.DataFrame())
    service_summary = st.session_state.get("service_summary", pd.DataFrame())
    if assignments.empty:
        st.info("Önce Vardiya Paneli'nde plan oluşturmalısın.")
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Servis OK geliş", int((assignments["arrival_note"] == "Servis OK").sum()))
    with c2:
        st.metric("Toplu taşıma geliş", int((assignments["arrival_note"] != "Servis OK").sum()))
    with c3:
        st.metric("Servis kayıtları", len(service_summary))

    route_filter = st.multiselect("Güzergah filtresi", sorted(assignments["route"].dropna().unique().tolist()))
    view = service_summary.copy()
    if route_filter:
        view = view[view["route"].isin(route_filter)]
    st.dataframe(view, width="stretch", hide_index=True)

    st.markdown("#### Toplu taşıma notu düşen personeller")
    tt = assignments[(assignments["arrival_note"] != "Servis OK") | (assignments["departure_note"] != "Servis OK")]
    st.dataframe(tt[["date", "name", "route", "out_flight", "work_start", "work_end", "arrival_service_time", "arrival_note", "departure_service_time", "departure_note"]], width="stretch", hide_index=True)


def ai_page():
    logo_header()
    st.markdown('<div class="section-title">AI Öneri Sistemi / Delay ve Devir Senaryosu</div>', unsafe_allow_html=True)
    assignments = st.session_state.get("plan_assignments", pd.DataFrame())
    if assignments.empty:
        st.info("Delay önerisi için önce plan oluşturmalısın.")
        return
    flights = sorted(assignments["out_flight"].dropna().unique().tolist())
    c1, c2 = st.columns([0.5, 0.5])
    with c1:
        selected_flight = st.selectbox("Geciken uçuş", flights)
    with c2:
        delay_minutes = st.slider("Delay süresi / dakika", min_value=15, max_value=360, value=60, step=15)
    recs = recommend_delay_actions(assignments, selected_flight, delay_minutes)
    if recs.empty:
        st.warning("Bu uçuş için öneri üretilemedi.")
    else:
        st.dataframe(recs, width="stretch", hide_index=True)
        st.markdown(
            """
            <div class="info-box">
            <b>Yorum:</b> Sistem önce uçuş üzerinde zaten atanmış kişileri devam adayı yapar. Sonra aynı gün vardiyada olup mevcut görevi yakın saatte biten personelleri devir/destek adayı olarak listeler. Bir sonraki aşamada bu bölüme Gemini/OpenAI API bağlanarak yöneticinin doğal dilde soru sorması sağlanabilir.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("#### Operasyon sorusu")
    question = st.text_area("Raporlara göre sormak istediğin soru", placeholder="Örn: UZB uçuşunda delay olursa hangi personel devralabilir?")
    if question:
        st.info("Bu prototipte cevap kural tabanlıdır. API anahtarı eklendiğinde burada LLM yorumu üretilebilir.")
        st.write("En uygun kısa yorum: Plan tablosunda aynı gün, aynı/uygun yetkinlikte ve görevi yakın saatte biten personeller öncelikli devir adayıdır. Servis notu 'Toplu Taşıma' olan personellerde dönüş planı ayrıca kontrol edilmelidir.")


def readme_page():
    logo_header()
    st.markdown('<div class="section-title">Kurulum ve GitHub Kullanımı</div>', unsafe_allow_html=True)
    st.code(
        """# 1) ZIP'i aç
cd celebi_yhm_shift_system

# 2) Sanal ortam oluştur
python -m venv .venv

# Windows PowerShell:
.venv\\Scripts\\activate

# 3) Paketleri kur
pip install -r requirements.txt

# 4) Uygulamayı çalıştır
streamlit run app.py""",
        language="bash",
    )
    st.markdown(
        """
        **Streamlit Cloud için:** GitHub'a tüm klasörü yükle. Main file path alanına `app.py` yaz.  
        **Dosya formatı:** `data/` klasöründeki örnek CSV'ler korunursa uygulama ilk açılışta otomatik veriyle çalışır.  
        **API gerekmiyor:** Mevcut prototip offline çalışır. AI yorum kısmı kural tabanlıdır.
        """
    )


def main():
    inject_css()
    prepare_session_tables()
    with st.sidebar:
        st.image(str(ASSET_DIR / "celebi_logo.png"), width=118)
        st.markdown("## YHM-Shift")
        st.caption("Akıllı vardiya + servis optimizasyon prototipi")
        page = st.radio(
            "Menü",
            [
                "Ana Sayfa",
                "Veri Yönetimi",
                "Personel Yönetimi",
                "DO / Talep Takvimi",
                "Vardiya Paneli",
                "Servis Paneli",
                "AI Öneri",
                "Kurulum",
            ],
        )
    if page == "Ana Sayfa":
        home_page()
    elif page == "Veri Yönetimi":
        data_page()
    elif page == "Personel Yönetimi":
        personnel_page()
    elif page == "DO / Talep Takvimi":
        requests_page()
    elif page == "Vardiya Paneli":
        planning_page()
    elif page == "Servis Paneli":
        service_page()
    elif page == "AI Öneri":
        ai_page()
    else:
        readme_page()


if __name__ == "__main__":
    main()
