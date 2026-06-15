import streamlit as st
import pandas as pd
import requests
import base64
import json
import uuid
from datetime import datetime
import pytz
from openai import OpenAI

st.set_page_config(page_title="OPD e-Prescribing", layout="wide")

BKK = pytz.timezone("Asia/Bangkok")

CSV_COLUMNS = [
    "order_id", "timestamp_bkk",
    "first_name", "last_name", "student_id",
    "sex", "age", "weight_kg",
    "allergy", "underlying_disease", "current_med_supplement",
    "diagnosis",
    "medications_json",
    "medrec_summary",
    "status",
    "dispensed_timestamp_bkk"
]


def now_bkk():
    return datetime.now(BKK).strftime("%Y-%m-%d %H:%M:%S")


def get_secret(name, default=None):
    if name in st.secrets:
        return st.secrets[name]
    return default


def github_headers():
    return {
        "Authorization": f"Bearer {get_secret('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github+json"
    }


def github_url():
    owner = get_secret("GITHUB_OWNER")
    repo = get_secret("GITHUB_REPO")
    path = get_secret("GITHUB_CSV_PATH")
    return f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"


def load_csv_from_github():
    params = {"ref": get_secret("GITHUB_BRANCH", "main")}
    r = requests.get(github_url(), headers=github_headers(), params=params)

    if r.status_code == 404:
        return pd.DataFrame(columns=CSV_COLUMNS), None

    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")

    from io import StringIO
    df = pd.read_csv(StringIO(content), dtype=str).fillna("")

    for c in CSV_COLUMNS:
        if c not in df.columns:
            df[c] = ""

    return df[CSV_COLUMNS], data["sha"]


def save_csv_to_github(df, sha=None):
    csv_text = df.to_csv(index=False)
    encoded = base64.b64encode(csv_text.encode("utf-8")).decode("utf-8")

    payload = {
        "message": f"Update pharmacy orders {now_bkk()}",
        "content": encoded,
        "branch": get_secret("GITHUB_BRANCH", "main")
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(github_url(), headers=github_headers(), json=payload)
    r.raise_for_status()


def safe_json_loads(text, default):
    try:
        return json.loads(text)
    except Exception:
        return default


def ai_suggest_meds(patient):
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))

    system_prompt = """
You are an assisting clinical pharmacist for a Thai university infirmary OPD.
Return ONLY valid JSON.
Suggest oral medications using generic names only, with Thai local names in parentheses.
Include dose, route, frequency, duration, instructions, warnings.
Do NOT suggest unsafe medication if allergy, pregnancy risk, severe disease, contraindication, or unclear diagnosis.
Emphasize physician must confirm.
Avoid controlled sedatives unless clearly justified.
For antibiotics, suggest only when clinically appropriate.
"""

    user_prompt = f"""
Patient:
- Sex: {patient['sex']}
- Age: {patient['age']}
- Weight kg: {patient['weight_kg']}
- Allergy: {patient['allergy']}
- Underlying disease: {patient['underlying_disease']}
- Current meds/supplements: {patient['current_med_supplement']}
- Diagnosis: {patient['diagnosis']}

Return JSON format:
{{
  "safety_alerts": ["..."],
  "medications": [
    {{
      "generic_name": "Paracetamol (พาราเซตามอล)",
      "strength": "500 mg tablet",
      "dose": "1 tablet",
      "route": "oral",
      "frequency": "every 6 hours as needed",
      "duration": "3 days",
      "quantity": "12 tablets",
      "thai_label": "รับประทานครั้งละ 1 เม็ด ทุก 6 ชั่วโมง เมื่อปวดหรือมีไข้",
      "counseling": "Do not exceed 8 tablets/day in adults."
    }}
  ],
  "medrec_summary": "..."
}}
"""

    response = client.chat.completions.create(
        model=get_secret("OPENAI_MODEL", "gpt-4.1-mini"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.2
    )

    return json.loads(response.choices[0].message.content)


def status_badge(status):
    color = {
        "รอจัดยา": "🟡",
        "จัดยาแล้ว": "🔵",
        "จ่ายยาแล้ว": "🟢"
    }.get(status, "⚪")
    return f"{color} {status}"


st.title("OPD e-Prescribing → ห้องยา")

mode = st.sidebar.radio("เลือกโหมด", ["แพทย์สั่งยา", "ห้องยา"])

if mode == "แพทย์สั่งยา":
    st.subheader("แพทย์: ข้อมูลผู้ป่วยและการสั่งยา")

    with st.form("doctor_form"):
        c1, c2, c3 = st.columns(3)
        first_name = c1.text_input("ชื่อ")
        last_name = c2.text_input("นามสกุล")
        student_id = c3.text_input("เลขประจำตัวนักศึกษา/รหัสบุคลากร")

        c4, c5, c6 = st.columns(3)
        sex = c4.selectbox("เพศ", ["", "ชาย", "หญิง", "อื่น ๆ"])
        age = c5.number_input("อายุ", min_value=0, max_value=120, step=1)
        weight_kg = c6.number_input("น้ำหนักตัว kg", min_value=0.0, max_value=250.0, step=0.5)

        allergy = st.text_area("ประวัติแพ้ยา/สาร/อาหาร", placeholder="เช่น แพ้ penicillin ผื่นลมพิษ")
        underlying = st.text_area("โรคประจำตัว", placeholder="เช่น asthma, G6PD, CKD, pregnancy")
        current_med = st.text_area("ยาประจำ/อาหารเสริม")
        diagnosis = st.text_area("การวินิจฉัย", placeholder="เช่น acute tonsillitis, dysmenorrhea, cellulitis")

        submitted = st.form_submit_button("ให้ AI เสนอรายการยา")

    if submitted:
        if not first_name or not last_name or not diagnosis:
            st.error("กรุณากรอกชื่อ นามสกุล และการวินิจฉัย")
        else:
            patient = {
                "sex": sex,
                "age": age,
                "weight_kg": weight_kg,
                "allergy": allergy or "ไม่มีข้อมูล",
                "underlying_disease": underlying or "ไม่มีข้อมูล",
                "current_med_supplement": current_med or "ไม่มีข้อมูล",
                "diagnosis": diagnosis
            }

            with st.spinner("AI กำลังเสนอรายการยา แพทย์ต้องตรวจสอบก่อนยืนยัน"):
                result = ai_suggest_meds(patient)

            st.session_state["ai_result"] = result
            st.session_state["patient"] = {
                "first_name": first_name,
                "last_name": last_name,
                "student_id": student_id,
                "sex": sex,
                "age": str(age),
                "weight_kg": str(weight_kg),
                "allergy": allergy,
                "underlying_disease": underlying,
                "current_med_supplement": current_med,
                "diagnosis": diagnosis
            }

    if "ai_result" in st.session_state:
        result = st.session_state["ai_result"]

        st.warning("AI เป็นเพียงผู้ช่วยเสนอรายการยา แพทย์เป็นผู้ตรวจสอบและยืนยันคำสั่งยา")

        alerts = result.get("safety_alerts", [])
        if alerts:
            st.markdown("### Safety alerts")
            for a in alerts:
                st.error(a)

        meds = result.get("medications", [])
        med_df = pd.DataFrame(meds)

        st.markdown("### รายการยาที่ AI เสนอ")
        edited_df = st.data_editor(
            med_df,
            num_rows="dynamic",
            use_container_width=True,
            key="edited_meds"
        )

        medrec_summary = st.text_area(
            "Medication reconciliation summary สำหรับครั้งต่อไป",
            value=result.get("medrec_summary", ""),
            height=120
        )

        confirm = st.checkbox("แพทย์ตรวจสอบ allergy, contraindication, dose, duration แล้ว และยืนยันคำสั่งยา")

        if st.button("บันทึกคำสั่งยาไปห้องยา", type="primary"):
            if not confirm:
                st.error("กรุณาติ๊กยืนยันก่อนบันทึก")
            elif edited_df.empty:
                st.error("ไม่มีรายการยา")
            else:
                df, sha = load_csv_from_github()
                p = st.session_state["patient"]

                new_row = {
                    "order_id": str(uuid.uuid4())[:8],
                    "timestamp_bkk": now_bkk(),
                    **p,
                    "medications_json": edited_df.to_json(orient="records", force_ascii=False),
                    "medrec_summary": medrec_summary,
                    "status": "รอจัดยา",
                    "dispensed_timestamp_bkk": ""
                }

                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                save_csv_to_github(df, sha)

                st.success("บันทึกคำสั่งยาเรียบร้อยแล้ว ส่งไปที่ห้องยาแล้ว")


elif mode == "ห้องยา":
    st.subheader("ห้องยา")

    pharma_code = st.text_input("รหัสห้องยา", type="password")

    if pharma_code != get_secret("PHARMA_CODE", "pharma"):
        st.info("กรุณาใส่รหัสห้องยา")
        st.stop()

    df, sha = load_csv_from_github()

    if df.empty:
        st.info("ยังไม่มีคำสั่งยา")
        st.stop()

    df = df.sort_values("timestamp_bkk", ascending=False).reset_index(drop=True)

    display_df = df[[
        "order_id", "timestamp_bkk", "first_name", "last_name",
        "sex", "age", "diagnosis", "status"
    ]].copy()

    display_df["status"] = display_df["status"].apply(status_badge)

    st.markdown("### รายการคำสั่งยาทั้งหมด")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    selected_id = st.selectbox(
        "คลิก/เลือก record",
        df["order_id"].tolist(),
        format_func=lambda x: f"{x} | {df.loc[df['order_id']==x, 'timestamp_bkk'].values[0]} | "
                              f"{df.loc[df['order_id']==x, 'first_name'].values[0]} "
                              f"{df.loc[df['order_id']==x, 'last_name'].values[0]}"
    )

    record = df[df["order_id"] == selected_id].iloc[0]

    st.markdown("### รายละเอียดผู้ป่วย")
    c1, c2, c3 = st.columns(3)
    c1.write(f"**ชื่อ:** {record['first_name']} {record['last_name']}")
    c2.write(f"**เพศ/อายุ:** {record['sex']} / {record['age']}")
    c3.write(f"**สถานะ:** {status_badge(record['status'])}")

    st.write(f"**วินิจฉัย:** {record['diagnosis']}")
    st.error(f"**แพ้ยา/สาร/อาหาร:** {record['allergy']}")
    st.info(f"**โรคประจำตัว:** {record['underlying_disease']}")
    st.info(f"**ยาประจำ/อาหารเสริม:** {record['current_med_supplement']}")

    meds = safe_json_loads(record["medications_json"], [])
    meds_df = pd.DataFrame(meds)

    st.markdown("### รายการยา")
    st.dataframe(meds_df, use_container_width=True, hide_index=True)

    st.markdown("### ป้ายยา")
    for i, med in enumerate(meds, start=1):
        label = f"""
ยา: {med.get('generic_name', '')}
ความแรง: {med.get('strength', '')}
วิธีใช้: {med.get('thai_label', '')}
คำแนะนำ: {med.get('counseling', '')}
ชื่อผู้ป่วย: {record['first_name']} {record['last_name']}
วันที่: {record['timestamp_bkk']}
"""
        with st.expander(f"ป้ายยา {i}: {med.get('generic_name', '')}"):
            st.text_area("คัดลอกเพื่อติดฉลากยา", value=label, height=180, key=f"label_{i}")

    st.markdown("### Medication reconciliation summary")
    st.text_area(
        "สรุปรายการเพื่อใช้ครั้งต่อไป",
        value=record["medrec_summary"],
        height=120
    )

    new_status = st.radio(
        "อัปเดตสถานะยา",
        ["รอจัดยา", "จัดยาแล้ว", "จ่ายยาแล้ว"],
        index=["รอจัดยา", "จัดยาแล้ว", "จ่ายยาแล้ว"].index(record["status"])
        if record["status"] in ["รอจัดยา", "จัดยาแล้ว", "จ่ายยาแล้ว"] else 0,
        horizontal=True
    )

    if st.button("บันทึกสถานะยา", type="primary"):
        idx = df[df["order_id"] == selected_id].index[0]
        df.loc[idx, "status"] = new_status

        if new_status == "จ่ายยาแล้ว":
            df.loc[idx, "dispensed_timestamp_bkk"] = now_bkk()

        save_csv_to_github(df, sha)
        st.success("อัปเดตสถานะยาเรียบร้อยแล้ว")
        st.rerun()
