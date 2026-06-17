import streamlit as st
import pandas as pd
import requests
import base64
import json
import uuid
import re
import html
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

# ยาที่มีในสถานพยาบาล ตาม medList.pdf อัปเดต 25 พ.ค. 2569
# เพิ่ม synonym เพื่อให้ AI/แพทย์พิมพ์ชื่อทั่วไปแล้วยังจับคู่ได้
MED_LIST = {
    # antibiotics - bacteria
    "amoxicillin": "Amoxicillin 500 mg",
    "dicloxacillin 250": "Dicloxacillin 250 mg",
    "dicloxacillin 500": "Dicloxacillin 500 mg",
    "dicloxacillin": "Dicloxacillin 500 mg",
    "doxycycline": "Doxycycline 100 mg",
    "clindamycin": "Clindamycin 300 mg",
    "amoxicillin clavulanate": "Amoxicillin + clavulanate 1 g",
    "amoxicillin + clavulanate": "Amoxicillin + clavulanate 1 g",
    "augmentin": "Amoxicillin + clavulanate 1 g",
    "metronidazole": "Metronidazole 400 mg",
    "roxithromycin": "Roxithromycin 150 mg",
    "norfloxacin": "Norfloxacin 400 mg",
    "ofloxacin": "Ofloxacin 200 mg",
    "ciprofloxacin": "Ciprofloxacin 500 mg",
    "azithromycin": "Azithromycin 250 mg",
    # antiviral / antifungal
    "acyclovir": "Acyclovir 400 mg",
    "acyclovir cream": "Acyclovir cream 1 g",
    "itraconazole": "Itraconazole 100 mg",
    # GI
    "antacid": "Al750mg + Mg 300mg (Antacid) susp.",
    "aluminium magnesium": "Al750mg + Mg 300mg (Antacid) susp.",
    "simeticone": "Simeticone 80 mg",
    "simethicone": "Simeticone 80 mg",
    "domperidone": "Domperidone 10 mg",
    "metoclopramide": "Metoclopramide 10 mg",
    "hyoscine": "Hyoscine 10 mg",
    "dicyclomine": "Dicyclomine 10 mg + simethicone 100 mg",
    "omeprazole": "Omeprazole 20 mg",
    "ors": "ORS",
    "oral rehydration": "ORS",
    "activated charcoal": "Activated charcoal 260 mg",
    "charcoal": "Activated charcoal 260 mg",
    "magnesium hydroxide": "Magnesium hydroxide (MOM) susp.",
    "mom": "Magnesium hydroxide (MOM) susp.",
    "senna": "Senna",
    "diosmin": "Diosmin + Hesperidine",
    "hesperidine": "Diosmin + Hesperidine",
    "doproct": "Doproct suppo",
    # respiratory / allergy
    "cpm": "CPM 4 mg",
    "chlorpheniramine": "CPM 4 mg",
    "hydroxyzine": "Hydroxyzine 10 mg",
    "cetirizine": "Cetirizine 10 mg",
    "loratadine": "Loratadine 10 mg",
    "prednisolone": "Prednisolone 5 mg",
    "salbutamol": "Salbutamol 2 mg",
    "nasotapp": "Nasotapp (Bromphe4 + Phenyl10)",
    "nss syringe": "NSS 0.9% + syringe 20 mL",
    "inhalex": "Inhalex Forte (Ipratropium + Fenoterol)",
    "salbutamol neb": "Salbutamol sulfate 2.5 mg/2.5 ml",
    # cough
    "dextromethorphan": "Dextromethorphan 15 mg",
    "brown mixture": "Brown Mixture/Mist tussis",
    "mist tussis": "Brown Mixture/Mist tussis",
    "acetylcysteine": "Acetylcysteine 200 mg",
    "nac": "Acetylcysteine 200 mg",
    "bromhexine": "Bromhexine 8 mg",
    "มะขามป้อม": "ยาน้ำมะขามป้อม",
    "มะแว้ง": "มะแว้งอม",
    # analgesic
    "paracetamol": "Paracetamol 500 mg",
    "acetaminophen": "Paracetamol 500 mg",
    "diclofenac": "Diclofenac 25 mg",
    "ibuprofen": "Ibuprofen 400 mg",
    "naproxen": "Naproxen 250 mg",
    "mefenamic": "Mefenamic acid 500 mg",
    "aspirin 300": "Aspirin 300 mg",
    "aspirin": "Aspirin 300 mg",
    "norgesic": "สูตร Norgesic",
    "tolperisone": "Tolperisone 50 mg",
    "tramadol": "Tramadol 50 mg",
    "celecoxib": "Celecoxib 200 mg",
    "balm": "Balm ทานวด",
    "diclofenac gel": "Diclofenac gel",
    "gabapentin": "Gabapentin 300 mg",
    # eye/ear
    "hista oph": "Hista-oph",
    "chloramphenicol eye": "Chloramphenicol eye drop",
    "poly oph": "Poly-oph",
    "terramycin": "Terramycin ointment",
    "artificial tear": "น้ำตาเทียม (Opsil tear, lac oph)",
    "opsil": "น้ำตาเทียม (Opsil tear, lac oph)",
    "dewax": "Dewax ear drop",
    "tobramycin": "Tobramycin 0.3% eye drop 5 ml",
    "dex oph": "สูตร Dex-oph",
    # neuro
    "dimenhydrinate": "Dimenhydrinate 50 mg",
    "cinnarizine": "Cinnarizine 25 mg",
    "betahistine": "Betahistine 6 mg",
    "amitriptyline": "Amitriptyline 10 mg",
    "lorazepam": "Lorazepam 0.5 / 1 mg",
    "sertraline": "Sertraline 50 mg",
    # vitamins
    "vitamin b complex": "Vitamin B complex",
    "vitamin b1": "Vitamin B1-6-12",
    "vitamin c": "Vitamin C 50 mg",
    "folic acid": "Folic acid 5 mg",
    "multivitamin": "MultiVitamin",
    "ferrous": "Ferrous fumarate 200 mg",
    # external
    "triamcinolone oral": "Triamcinolone oral paste",
    "ta lotion": "TA 0.1% lotion",
    "ta cream": "TA 0.1% cream",
    "ta 0.02": "TA 0.02% cream",
    "betamethasone": "Betamet val 0.1% cream",
    "clobetasol": "Clobetasol 0.05% cream",
    "calamine": "Calamine lotion",
    "clotrimazole": "Clotrimazole cream",
    "mupirocin": "Mupirocin 2% ointment",
    "salicylic": "Con Con (salicylic acid)",
    # hormone / chronic
    "norethisterone": "Norethisterone 5 mg",
    "metformin": "Metformin 500 mg",
    "amlodipine 5": "Amlodipine 5 mg",
    "amlodipine 10": "Amlodipine 10 mg",
    "amlodipine": "Amlodipine 5 mg",
    "atenolol": "Atenolol 50 mg",
    "enalapril 5": "Enalapril 5 mg",
    "enalapril 20": "Enalapril 20 mg",
    "enalapril": "Enalapril 5 mg",
    "simvastatin 10": "Simvastatin 10 mg",
    "simvastatin 20": "Simvastatin 20 mg",
    "simvastatin": "Simvastatin 10 mg",
    "propranolol": "Propanolol 10 mg",
    "propanolol": "Propanolol 10 mg",
    "losartan": "Losartan 50 mg",
    "aspirin 81": "Aspirin 81 mg",
    # injection / fluids included for completeness
    "adrenaline": "Adrenaline 1 mg/ml (HAD)",
    "ceftriaxone": "Ceftriaxone 1 g",
    "lincomycin": "Lincomycin 300 mg/2ml",
    "lidocaine": "Lidocaine HCl inj. 2% w/v 2 mL",
    "nss 100": "NSS 0.9% sodium chloride inj. 100 ml",
    "nss 500": "NSS 0.9% sodium chloride inj. 500 ml",
    "nss 1000": "NSS 0.9% sodium chloride inj. 1000 ml",
    "d5w": "D5W 5% dextrose in water inj. 100 ml",
    "acetate ringer": "Acetate ringer's injection 1000 ml",
    "d-5-1/2": "D-5-1/2 saline inj 1000 mL",
}

MED_OPTIONS = sorted(set(MED_LIST.values()))


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

    if not r.ok:
        st.error(f"GitHub save failed: {r.status_code}")
        st.code(r.text)
        st.stop()

    return r.json()


def safe_json_loads(text, default):
    try:
        return json.loads(text)
    except Exception:
        return default


def norm_text(x):
    return re.sub(r"[^a-z0-9ก-๙+/.-]+", " ", str(x).lower()).strip()


def find_med_in_stock(med_name, strength=""):
    text = norm_text(f"{med_name} {strength}")
    if not text:
        return None

    # direct display-name match first
    for item in MED_OPTIONS:
        if norm_text(item) in text or text in norm_text(item):
            return item

    # synonym/keyword match: longest keys first avoids aspirin 300 overriding aspirin 81, etc.
    for key in sorted(MED_LIST.keys(), key=len, reverse=True):
        if key in text:
            return MED_LIST[key]
    return None


def add_stock_status(meds_df):
    if meds_df is None or meds_df.empty:
        return meds_df
    df = meds_df.copy()
    if "generic_name" not in df.columns:
        df["generic_name"] = ""
    if "strength" not in df.columns:
        df["strength"] = ""
    df["stock_item"] = df.apply(lambda r: find_med_in_stock(r.get("generic_name", ""), r.get("strength", "")) or "ไม่มีในสถานพยาบาล", axis=1)
    df["in_stock"] = df["stock_item"] != "ไม่มีในสถานพยาบาล"
    return df


def allergy_and_interaction_alerts(meds, allergy_text, current_med_text):
    alerts = []
    allergy = norm_text(allergy_text)
    current = norm_text(current_med_text)
    names = [norm_text(m.get("generic_name", "") + " " + m.get("strength", "") + " " + m.get("stock_item", "")) for m in meds]
    all_ordered = " | ".join(names)

    def has_any(text, words):
        return any(w in text for w in words)

    # Allergy alerts
    if has_any(allergy, ["penicillin", "เพนิซิล", "amoxicillin", "ampicillin", "augmentin"]):
        for n in names:
            if has_any(n, ["amoxicillin", "clavulanate", "dicloxacillin"]):
                alerts.append("Drug allergy alert: มีประวัติแพ้ penicillin/amoxicillin แต่มีคำสั่งยากลุ่ม penicillin")
                break
    if has_any(allergy, ["sulfa", "ซัลฟา"]):
        for n in names:
            if "sulf" in n:
                alerts.append("Drug allergy alert: มีประวัติแพ้ sulfa และมียาที่อาจเกี่ยวข้อง")
                break
    if has_any(allergy, ["aspirin", "asa", "แอสไพริน", "nsaid", "เอ็นเสด", "ibuprofen", "diclofenac", "naproxen", "mefenamic", "celecoxib"]):
        for n in names:
            if has_any(n, ["aspirin", "ibuprofen", "diclofenac", "naproxen", "mefenamic", "celecoxib"]):
                alerts.append("Drug allergy alert: มีประวัติแพ้ aspirin/NSAIDs แต่มีคำสั่งยา NSAID/aspirin")
                break
    if has_any(allergy, ["macrolide", "azithromycin", "roxithromycin", "erythromycin"]):
        for n in names:
            if has_any(n, ["azithromycin", "roxithromycin"]):
                alerts.append("Drug allergy alert: มีประวัติแพ้ macrolide แต่มีคำสั่งยา azithromycin/roxithromycin")
                break
    if has_any(allergy, ["quinolone", "floxacin", "cipro", "ofloxacin", "norfloxacin"]):
        for n in names:
            if has_any(n, ["ciprofloxacin", "ofloxacin", "norfloxacin"]):
                alerts.append("Drug allergy alert: มีประวัติแพ้ quinolone แต่มีคำสั่งยา quinolone")
                break

    # Common interaction alerts, practical OPD rules (physician must confirm)
    if has_any(all_ordered, ["ibuprofen", "diclofenac", "naproxen", "mefenamic", "celecoxib", "aspirin"]):
        if has_any(current, ["warfarin", "rivaroxaban", "apixaban", "dabigatran", "clopidogrel", "aspirin"]):
            alerts.append("Drug interaction alert: NSAID/aspirin ร่วมกับ anticoagulant/antiplatelet เพิ่มความเสี่ยงเลือดออก")
        if has_any(current, ["enalapril", "losartan", "acei", "arb", "furosemide", "hctz", "diuretic"]):
            alerts.append("Drug interaction alert: NSAID ร่วมกับ ACEI/ARB/diuretic อาจเพิ่มความเสี่ยงไตเสื่อม/ความดันคุมยาก")
    if "simvastatin" in current and has_any(all_ordered, ["azithromycin", "roxithromycin", "itraconazole"]):
        alerts.append("Drug interaction alert: simvastatin ร่วมกับ macrolide/itraconazole เพิ่มความเสี่ยง myopathy/rhabdomyolysis")
    if has_any(current, ["sertraline", "fluoxetine", "paroxetine", "ssri", "snri"]) and has_any(all_ordered, ["tramadol", "dextromethorphan"]):
        alerts.append("Drug interaction alert: SSRI/SNRI ร่วมกับ tramadol/dextromethorphan เพิ่มความเสี่ยง serotonin syndrome")
    if has_any(current, ["amitriptyline", "lorazepam", "diazepam", "alcohol", "เหล้า", "สุรา"]) and has_any(all_ordered, ["tramadol", "hydroxyzine", "cpm", "chlorpheniramine", "dimenhydrinate", "lorazepam"]):
        alerts.append("Drug interaction alert: ยากดประสาท/แอลกอฮอล์ร่วมกับยาง่วงซึมหรือ tramadol เพิ่มความเสี่ยงง่วง ซึม หกล้ม กดหายใจ")
    if "metformin" in current and has_any(all_ordered, ["ciprofloxacin", "ofloxacin", "norfloxacin"]):
        alerts.append("Drug interaction alert: fluoroquinolone อาจรบกวนระดับน้ำตาลในผู้ใช้ metformin/เบาหวาน")

    return list(dict.fromkeys(alerts))


def ai_suggest_meds(patient):
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))
    stock_text = "\n".join(f"- {x}" for x in MED_OPTIONS)

    system_prompt = f"""
You are an assisting clinical pharmacist for a Thai university infirmary OPD.
Return ONLY valid JSON.
Suggest medications using generic names only, with Thai local names in parentheses when useful.
IMPORTANT: Suggest ONLY medications available in this infirmary stock list. If no suitable in-stock medication exists, return no medication and explain in safety_alerts.
Infirmary stock list:
{stock_text}
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


def printable_label_html(label_text, button_text="พิมพ์ป้ายยานี้"):
    safe = html.escape(label_text).replace("\n", "<br>")
    uid = str(uuid.uuid4()).replace("-", "")
    return f"""
<div id="label_{uid}" style="border:1px solid #333; padding:10px; width:360px; font-size:15px; line-height:1.45; background:white; color:black;">
{safe}
</div>
<button onclick="printLabel_{uid}()" style="margin-top:8px; padding:6px 12px; cursor:pointer;">{button_text}</button>
<script>
function printLabel_{uid}() {{
    var contents = document.getElementById('label_{uid}').innerHTML;
    var w = window.open('', '', 'height=500,width=420');
    w.document.write('<html><head><title>Drug label</title>');
    w.document.write('<style>@media print {{ @page {{ size: 80mm auto; margin: 5mm; }} body {{ font-family: Arial, sans-serif; font-size: 14px; }} }}</style>');
    w.document.write('</head><body>');
    w.document.write(contents);
    w.document.write('</body></html>');
    w.document.close();
    w.focus();
    setTimeout(function() {{ w.print(); w.close(); }}, 300);
}}
</script>
"""


st.title("OPD e-Prescribing → ห้องยา")

# Default เป็นห้องยา ไม่ต้องใส่รหัส; หน้าแพทย์ใช้รหัส physician
mode = st.sidebar.radio("เลือกโหมด", ["ห้องยา", "แพทย์สั่งยา"], index=0)

if mode == "แพทย์สั่งยา":
    physician_code = st.sidebar.text_input("รหัสเข้าหน้าแพทย์", type="password")
    if physician_code != "physician":
        st.info("กรุณาใส่รหัสเข้าหน้าแพทย์")
        st.stop()

    st.subheader("แพทย์: ข้อมูลผู้ป่วยและการสั่งยา")

    with st.expander("ดูรายการยาที่มีในสถานพยาบาล", expanded=False):
        st.dataframe(pd.DataFrame({"รายการยา": MED_OPTIONS}), use_container_width=True, hide_index=True)

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
        current_med = st.text_area("ยาประจำ/อาหารเสริม", placeholder="เช่น warfarin, aspirin, simvastatin, sertraline")
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
        p = st.session_state["patient"]

        st.warning("AI เป็นเพียงผู้ช่วยเสนอรายการยา แพทย์เป็นผู้ตรวจสอบและยืนยันคำสั่งยา")

        alerts = result.get("safety_alerts", [])
        if alerts:
            st.markdown("### Safety alerts จาก AI")
            for a in alerts:
                st.error(a)

        meds = result.get("medications", [])
        med_df = add_stock_status(pd.DataFrame(meds))

        st.markdown("### รายการยาที่ AI เสนอ / แพทย์แก้ไขได้")
        edited_df = st.data_editor(
            med_df,
            num_rows="dynamic",
            use_container_width=True,
            key="edited_meds",
            column_config={
                "in_stock": st.column_config.CheckboxColumn("มีในสถานพยาบาล", disabled=True),
                "stock_item": st.column_config.SelectboxColumn("ตรงกับรายการยา", options=["ไม่มีในสถานพยาบาล"] + MED_OPTIONS),
            }
        )

        # ตรวจซ้ำทุกครั้งหลังแพทย์แก้ไข
        checked_df = add_stock_status(edited_df)
        checked_meds = checked_df.to_dict(orient="records") if checked_df is not None and not checked_df.empty else []

        st.markdown("### ระบบตรวจสอบก่อนบันทึก")
        out_of_stock = [m for m in checked_meds if not m.get("in_stock", False)]
        if out_of_stock:
            for m in out_of_stock:
                st.error(f"ไม่มีในสถานพยาบาล: {m.get('generic_name', '')} {m.get('strength', '')}")

        rule_alerts = allergy_and_interaction_alerts(checked_meds, p.get("allergy", ""), p.get("current_med_supplement", ""))
        if p.get("allergy", "").strip():
            st.warning(f"มีประวัติแพ้ยา/สาร/อาหาร: {p.get('allergy')}")
        for a in rule_alerts:
            st.error(a)
        if not out_of_stock and not rule_alerts:
            st.success("ไม่พบยานอกบัญชี/alert จาก rule เบื้องต้น แต่แพทย์ยังต้องยืนยันทางคลินิก")

        medrec_summary = st.text_area(
            "Medication reconciliation summary สำหรับครั้งต่อไป",
            value=result.get("medrec_summary", ""),
            height=120
        )

        confirm = st.checkbox("แพทย์ตรวจสอบ allergy, interaction, contraindication, dose, duration และรายการยาในสถานพยาบาลแล้ว")

        if st.button("บันทึกคำสั่งยาไปห้องยา", type="primary"):
            if not confirm:
                st.error("กรุณาติ๊กยืนยันก่อนบันทึก")
            elif not checked_meds:
                st.error("ไม่มีรายการยา")
            elif out_of_stock:
                st.error("ยังมียาที่ไม่มีในสถานพยาบาล กรุณาลบหรือเปลี่ยนยาก่อนบันทึก")
            else:
                df, sha = load_csv_from_github()

                new_row = {
                    "order_id": str(uuid.uuid4())[:8],
                    "timestamp_bkk": now_bkk(),
                    **p,
                    "medications_json": pd.DataFrame(checked_meds).to_json(orient="records", force_ascii=False),
                    "medrec_summary": medrec_summary,
                    "status": "รอจัดยา",
                    "dispensed_timestamp_bkk": ""
                }

                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                save_csv_to_github(df, sha)

                st.success("บันทึกคำสั่งยาเรียบร้อยแล้ว ส่งไปที่ห้องยาแล้ว")

elif mode == "ห้องยา":
    st.subheader("ห้องยา")
    st.caption("หน้า Default ไม่ต้องใส่รหัส")

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
    if str(record['allergy']).strip():
        st.error(f"**แพ้ยา/สาร/อาหาร:** {record['allergy']}")
    else:
        st.info("**แพ้ยา/สาร/อาหาร:** ไม่มีข้อมูล")
    st.info(f"**โรคประจำตัว:** {record['underlying_disease']}")
    st.info(f"**ยาประจำ/อาหารเสริม:** {record['current_med_supplement']}")

    meds = safe_json_loads(record["medications_json"], [])
    meds_df = add_stock_status(pd.DataFrame(meds))
    meds = meds_df.to_dict(orient="records") if meds_df is not None and not meds_df.empty else []

    st.markdown("### รายการยา")
    st.dataframe(meds_df, use_container_width=True, hide_index=True)

    rule_alerts = allergy_and_interaction_alerts(meds, record["allergy"], record["current_med_supplement"])
    out_of_stock = [m for m in meds if not m.get("in_stock", False)]
    if out_of_stock:
        for m in out_of_stock:
            st.error(f"ไม่มีในสถานพยาบาล: {m.get('generic_name', '')} {m.get('strength', '')}")
    for a in rule_alerts:
        st.error(a)

    st.markdown("### ป้ายยา — คลิกพิมพ์ได้ทีละตัว")
    for i, med in enumerate(meds, start=1):
        label = f"""สถานพยาบาล มก. กำแพงแสน
ชื่อผู้ป่วย: {record['first_name']} {record['last_name']}
วันที่สั่งยา: {record['timestamp_bkk']}
ยา: {med.get('stock_item') or med.get('generic_name', '')}
ความแรง: {med.get('strength', '')}
จำนวน: {med.get('quantity', '')}
วิธีใช้: {med.get('thai_label', '')}
คำแนะนำ: {med.get('counseling', '')}"""
        with st.expander(f"ป้ายยา {i}: {med.get('stock_item') or med.get('generic_name', '')}", expanded=False):
            st.components.v1.html(printable_label_html(label), height=260)
            st.text_area("ข้อความป้ายยา", value=label, height=160, key=f"label_{selected_id}_{i}")

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

