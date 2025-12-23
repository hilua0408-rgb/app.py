import streamlit as st
import re
import os
import time
import math
from google import genai

# Page Setup
st.set_page_config(page_title="Gemini Subtitle Pro", layout="wide")
st.title("✨ Gemini Subtitle Translator (Mobile Friendly)")

# --- ⚙️ SETTINGS PANEL (Source: Step 2) ---
with st.sidebar:
    st.header("Settings")
    # 1. API KEY
    [cite_start]api_key = st.text_input("GOOGLE_API_KEY", type="password", help="Paste your Gemini API Key here") [cite: 2]
    
    # [cite_start]2. MODEL SELECTION [cite: 2]
    model_list = ["gemini-3-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash"]
    [cite_start]model_name = st.selectbox("MODEL_NAME", model_list) [cite: 2]
    
    # [cite_start]3. LANGUAGE SETTINGS [cite: 2]
    source_lang = st.text_input("SOURCE_LANGUAGE", "English")
    target_lang = st.text_input("TARGET_LANGUAGE", "Roman Hindi")
    
    # [cite_start]4. USER INSTRUCTION [cite: 3]
    user_instr = st.text_area("USER_INSTRUCTION", "Translate into natural Roman Hindi. Keep Anime terms in English.")
    
    # [cite_start]5. BATCH SIZE [cite: 3]
    batch_sz = st.number_input("BATCH_SIZE", value=50, step=1)

# --- MAIN LOGIC & PROCESSOR (Source: Step 2) ---
class SubtitleProcessor:
    def __init__(self, filename, content):
        [cite_start]self.ext = os.path.splitext(filename)[1].lower() [cite: 5]
        [cite_start]try: self.raw = content.decode('utf-8').replace('\r\n', '\n') [cite: 6]
        [cite_start]except: self.raw = content.decode('latin-1').replace('\r\n', '\n') [cite: 6]
        self.lines = []

    def parse(self):
        [cite_start]if self.ext == '.srt': self.srt() [cite: 6]
        [cite_start]elif self.ext == '.vtt': self.vtt() [cite: 6]
        [cite_start]elif self.ext == '.ass': self.ass() [cite: 6]
        return len(self.lines)

    def srt(self):
        [cite_start]for b in re.split(r'\n\s*\n', self.raw.strip()): [cite: 7]
            l = b.split('\n')
            [cite_start]if len(l) >= 3: self.lines.append({'id': l[0].strip(), 't': l[1].strip(), 'txt': "\n".join(l[2:])}) [cite: 8]

    def vtt(self):
        [cite_start]c = {'id': None, 't': None, 'txt': []}; cnt = 1 [cite: 9]
        lines = self.raw.split('\n')
        [cite_start]if lines and lines[0].strip() == "WEBVTT": lines = lines[1:] [cite: 9]
        for l in lines:
            l = l.strip()
            [cite_start]if "-->" in l: c['t'] = l; c['id'] = str(cnt); cnt += 1 [cite: 10]
            elif l == "" and c['t']:
                if c['txt']: self.lines.append(c.copy())
                c = {'id': None, 't': None, 'txt': []}
            elif c['t']: c['txt'].append(l)
        if c['t'] and c['txt']: self.lines.append(c)
        [cite_start]for x in self.lines: x['txt'] = "\n".join(x['txt']) [cite: 11]

    def ass(self):
        cnt = 1
        for l in self.raw.split('\n'):
            [cite_start]if l.startswith("Dialogue:"): [cite: 12]
                p = l.split(',', 9)
                [cite_start]if len(p) == 10: self.lines.append({'id': str(cnt), 'raw': l, 'txt': p[9].strip()}); cnt += 1 [cite: 12]

    def get_output(self, data):
        output = ""
        if self.ext == '.srt':
            [cite_start]for x in self.lines: output += f"{x['id']}\n{x['t']}\n{data.get(x['id'], x['txt'])}\n\n" [cite: 13]
        elif self.ext == '.vtt':
            [cite_start]output += "WEBVTT\n\n" [cite: 13]
            [cite_start]for x in self.lines: output += f"{x['t']}\n{data.get(x['id'], x['txt'])}\n\n" [cite: 13]
        elif self.ext == '.ass':
            cnt = 1
            for l in self.raw.split('\n'):
                [cite_start]if l.startswith("Dialogue:"): [cite: 14]
                    p = l.split(',', 9)
                    if len(p) == 10:
                        [cite_start]output += ",".join(p[:9]) + "," + data.get(str(cnt), p[9].strip()) + "\n"; cnt += 1 [cite: 14, 15]
                    else: output += l + "\n"
                else: output += l + "\n"
        return output

# --- APP UI ---
[cite_start]uploaded_file = st.file_uploader("Upload Subtitle File (.srt, .vtt, .ass)", type=['srt', 'vtt', 'ass']) [cite: 5]

if uploaded_file and api_key:
    if st.button("🚀 Start Translation"):
        [cite_start]client = genai.Client(api_key=api_key) [cite: 3]
        proc = SubtitleProcessor(uploaded_file.name, uploaded_file.getvalue())
        total_lines = proc.parse()
        
        st.info(f"✅ Parsed {total_lines} lines. Starting Translation...")
        
        trans_map = {}
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_batches = math.ceil(total_lines / batch_sz)
        
        for i in range(0, total_lines, batch_sz):
            current_batch_num = (i // batch_sz) + 1
            chunk = proc.lines[i : i + batch_sz]
            
            # [cite_start]Make Batch Text [cite: 18]
            batch_txt = ""
            for x in chunk: batch_txt += f"[{x['id']}]\n{x['txt']}\n\n"
            
            # [cite_start]API Prompt [cite: 17]
            prompt = f"TASK: Translate from {source_lang} to {target_lang}\nNOTE: {user_instr}\n\nFORMAT:\n[ID]\nTranslated Text\n\nBatch:\n{batch_txt}"
            
            [cite_start]retry = 3 [cite: 23]
            success = False
            while retry > 0:
                try:
                    status_text.text(f"Processing Batch {current_batch_num}/{total_batches}...")
                    [cite_start]resp = client.models.generate_content(model=model_name, contents=prompt) [cite: 19]
                    
                    # [cite_start]Extraction [cite: 20]
                    matches = list(re.finditer(r'\[(\d+)\]\s*\n(.*?)(?=\n\[\d+\]|$)', resp.text, re.DOTALL))
                    if matches:
                        for m in matches: trans_map[m.group(1)] = m.group(2).strip()
                        [cite_start]success = True; break [cite: 21]
                    else: raise Exception("Format Error")
                except:
                    retry -= 1
                    [cite_start]time.sleep(2) [cite: 23]
            
            progress_bar.progress(min((i + batch_sz) / total_lines, 1.0))
            [cite_start]time.sleep(1) [cite: 23]

        # Finish
        st.success("✅ Translation Complete!")
        out_content = proc.get_output(trans_map)
        [cite_start]st.download_button(label="⬇️ Download Translated File", data=out_content, file_name=f"translated_{uploaded_file.name}") [cite: 24]