import streamlit as st
import re
import os
import time
import math
from google import genai

# Page Setup
st.set_page_config(page_title="Gemini Subtitle Pro", layout="wide")

# --- 📱 SIDEBAR (File Upload & Progress) ---
with st.sidebar:
    st.header("📁 File Upload")
    uploaded_file = st.file_uploader("Upload Subtitle File (.srt, .vtt, .ass)", type=['srt', 'vtt', 'ass'])
    st.markdown("---")
    status_text = st.empty()
    progress_bar = st.progress(0)

# --- 🖥️ MAIN INTERFACE (Settings) ---
st.title("✨ Gemini Subtitle Translator")

api_key = st.text_input("GOOGLE_API_KEY", type="password", help="Paste your Gemini API Key")

col1, col2 = st.columns(2)
with col1:
    # Updated Model List (Standard 2025 Models)
    model_list = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-pro-exp"]
    model_name = st.selectbox("MODEL_NAME", model_list)
    source_lang = st.text_input("SOURCE_LANGUAGE", "English")

with col2:
    target_lang = st.text_input("TARGET_LANGUAGE", "Roman Hindi")
    batch_sz = st.number_input("BATCH_SIZE", value=50, step=1)

user_instr = st.text_area("USER_INSTRUCTION", "Translate into natural Roman Hindi. Keep Anime terms in English.")

start_button = st.button("🚀 START TRANSLATION NOW", use_container_width=True)

# --- SUBTITLE PROCESSOR ---
class SubtitleProcessor:
    def __init__(self, filename, content):
        self.ext = os.path.splitext(filename)[1].lower()
        try: self.raw = content.decode('utf-8').replace('\r\n', '\n')
        except: self.raw = content.decode('latin-1').replace('\r\n', '\n')
        self.lines = []

    def parse(self):
        if self.ext == '.srt': self.srt()
        elif self.ext == '.vtt': self.vtt()
        elif self.ext == '.ass': self.ass()
        return len(self.lines)

    def srt(self):
        for b in re.split(r'\n\s*\n', self.raw.strip()):
            l = b.split('\n')
            if len(l) >= 3: self.lines.append({'id': l[0].strip(), 't': l[1].strip(), 'txt': "\n".join(l[2:])})

    def vtt(self):
        c = {'id': None, 't': None, 'txt': []}; cnt = 1
        lines = self.raw.split('\n')
        if lines and lines[0].strip() == "WEBVTT": lines = lines[1:]
        for l in lines:
            l = l.strip()
            if "-->" in l: c['t'] = l; c['id'] = str(cnt); cnt += 1
            elif l == "" and c['t']:
                if c['txt']: self.lines.append(c.copy())
                c = {'id': None, 't': None, 'txt': []}
            elif c['t']: c['txt'].append(l)
        if c['t'] and c['txt']: self.lines.append(c)
        for x in self.lines: x['txt'] = "\n".join(x['txt'])

    def ass(self):
        cnt = 1
        for l in self.raw.split('\n'):
            if l.startswith("Dialogue:"):
                p = l.split(',', 9)
                if len(p) == 10: self.lines.append({'id': str(cnt), 'raw': l, 'txt': p[9].strip()}); cnt += 1

    def get_output(self, data):
        output = ""
        if self.ext == '.srt':
            for x in self.lines: output += f"{x['id']}\n{x['t']}\n{data.get(x['id'], x['txt'])}\n\n"
        elif self.ext == '.vtt':
            output += "WEBVTT\n\n"
            for x in self.lines: output += f"{x['t']}\n{data.get(x['id'], x['txt'])}\n\n"
        elif self.ext == '.ass':
            cnt = 1
            for l in self.raw.split('\n'):
                if l.startswith("Dialogue:"):
                    p = l.split(',', 9)
                    if len(p) == 10:
                        output += ",".join(p[:9]) + "," + data.get(str(cnt), p[9].strip()) + "\n"; cnt += 1
                    else: output += l + "\n"
                else: output += l + "\n"
        return output

# --- EXECUTION ---
if start_button:
    if not api_key or not uploaded_file:
        st.error("❌ API Key aur File dono zaroori hain!")
    else:
        try:
            client = genai.Client(api_key=api_key)
            proc = SubtitleProcessor(uploaded_file.name, uploaded_file.getvalue())
            total_lines = proc.parse()
            
            trans_map = {}
            total_batches = math.ceil(total_lines / batch_sz)
            
            for i in range(0, total_lines, batch_sz):
                current_batch_num = (i // batch_sz) + 1
                chunk = proc.lines[i : i + batch_sz]
                batch_txt = "".join([f"[{x['id']}]\n{x['txt']}\n\n" for x in chunk])
                
                prompt = f"TASK: Translate from {source_lang} to {target_lang}\nNOTE: {user_instr}\n\nFORMAT:\n[ID]\nTranslated Text\n\nBatch:\n{batch_txt}"
                
                retry = 3
                success = False
                while retry > 0:
                    try:
                        status_text.text(f"⏳ Processing Batch {current_batch_num}/{total_batches}")
                        resp = client.models.generate_content(model=model_name, contents=prompt)
                        
                        matches = list(re.finditer(r'\[(\d+)\]\s*\n(.*?)(?=\n\[\d+\]|$)', resp.text, re.DOTALL))
                        if matches:
                            for m in matches: trans_map[m.group(1)] = m.group(2).strip()
                            success = True; break
                        else:
                            st.warning(f"Batch {current_batch_num}: Format mismatch. Retrying...")
                            retry -= 1
                    except Exception as e:
                        st.error(f"Batch {current_batch_num} Error: {str(e)}") # Ye line asli error batayegi
                        retry -= 1
                        time.sleep(2)
                
                progress_bar.progress(min((i + batch_sz) / total_lines, 1.0))
                time.sleep(1)

            if trans_map:
                st.success("🎉 Done!")
                out_content = proc.get_output(trans_map)
                st.download_button("⬇️ DOWNLOAD", data=out_content, file_name=f"translated_{uploaded_file.name}")
            else:
                st.error("❌ Translation failed. Check errors above.")
        
        except Exception as e:
            st.error(f"Fatal Error: {e}")
