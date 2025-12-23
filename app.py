import streamlit as st
import re
import os
import time
import math
from google import genai

# Page Setup
st.set_page_config(page_title="Gemini Subtitle Pro", layout="wide")

# --- 📱 SIDEBAR (File Section) ---
with st.sidebar:
    st.header("📁 File Upload")
    [cite_start]uploaded_file = st.file_uploader("Upload Subtitle File (.srt, .vtt, .ass)", type=['srt', 'vtt', 'ass']) [cite: 5]
    st.markdown("---")
    status_text = st.empty()
    progress_bar = st.progress(0)
    # Streaming Preview Box in Sidebar
    st.subheader("📺 Live Stream")
    st_stream_box = st.empty() 

# --- 🖥️ MAIN INTERFACE (Settings) ---
st.title("✨ Gemini Subtitle Translator")

[cite_start]api_key = st.text_input("GOOGLE_API_KEY", type="password") [cite: 2]

col1, col2 = st.columns(2)
with col1:
    model_list = [
        "gemini-3-pro-preview", "gemini-3-flash-preview", 
        "gemini-2.5-pro", "gemini-2.5-flash",
        "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"
    [cite_start]] [cite: 2]
    [cite_start]model_name = st.selectbox("MODEL_NAME", model_list) [cite: 2]
    [cite_start]source_lang = st.text_input("SOURCE_LANGUAGE", "English") [cite: 2]

with col2:
    [cite_start]target_lang = st.text_input("TARGET_LANGUAGE", "Roman Hindi") [cite: 2]
    [cite_start]batch_sz = st.number_input("BATCH_SIZE", value=50, step=1) [cite: 3]

[cite_start]user_instr = st.text_area("USER_INSTRUCTION", "Translate into natural Roman Hindi. Keep Anime terms in English.") [cite: 3]

start_button = st.button("🚀 START TRANSLATION NOW", use_container_width=True)

# --- SUBTITLE PROCESSOR ---
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
        [cite_start]if self.ext == '.srt': [cite: 13]
            [cite_start]for x in self.lines: output += f"{x['id']}\n{x['t']}\n{data.get(x['id'], x['txt'])}\n\n" [cite: 13]
        [cite_start]elif self.ext == '.vtt': [cite: 13]
            [cite_start]output += "WEBVTT\n\n" [cite: 13]
            [cite_start]for x in self.lines: output += f"{x['t']}\n{data.get(x['id'], x['txt'])}\n\n" [cite: 13]
        [cite_start]elif self.ext == '.ass': [cite: 14]
            cnt = 1
            for l in self.raw.split('\n'):
                [cite_start]if l.startswith("Dialogue:"): [cite: 14]
                    p = l.split(',', 9)
                    if len(p) == 10:
                        [cite_start]output += ",".join(p[:9]) + "," + data.get(str(cnt), p[9].strip()) + "\n"; cnt += 1 [cite: 14, 15]
                    else: output += l + "\n"
                else: output += l + "\n"
        return output

# --- EXECUTION ---
if start_button:
    if not api_key or not uploaded_file:
        st.error("❌ API Key aur File dono zaroori hain!")
    else:
        try:
            [cite_start]client = genai.Client(api_key=api_key) [cite: 3]
            proc = SubtitleProcessor(uploaded_file.name, uploaded_file.getvalue())
            total_lines = proc.parse()
            
            trans_map = {}
            total_batches = math.ceil(total_lines / batch_sz)
            
            for i in range(0, total_lines, batch_sz):
                current_batch_num = (i // batch_sz) + 1
                chunk = proc.lines[i : i + batch_sz]
                [cite_start]batch_txt = "".join([f"[{x['id']}]\n{x['txt']}\n\n" for x in chunk]) [cite: 18]
                
                prompt = f"""You are a professional subtitle translator.
TASK: Translate from {source_lang} to {target_lang}
USER NOTE: {user_instr}

FORMAT:
[ID]
Translated Text

Batch:
[cite_start]{batch_txt}""" [cite: 17]
                
                [cite_start]retry = 3 [cite: 23]
                success = False
                while retry > 0:
                    try:
                        status_text.text(f"⏳ Batch {current_batch_num}/{total_batches}")
                        full_response = ""
                        
                        # --- 🚀 STREAMING START ---
                        [cite_start]for chunk_resp in client.models.generate_content_stream(model=model_name, contents=prompt): [cite: 19]
                            full_response += chunk_resp.text
                            st_stream_box.text_area("Live Preview:", value=full_response, height=200) # Typewriter effect
                        
                        # [cite_start]Extraction after full stream 
                        [cite_start]matches = list(re.finditer(r'\[(\d+)\]\s*\n(.*?)(?=\n\[\d+\]|$)', full_response, re.DOTALL)) [cite: 20]
                        if matches:
                            [cite_start]for m in matches: trans_map[m.group(1)] = m.group(2).strip() [cite: 20]
                            [cite_start]success = True; break [cite: 21]
                        else: retry -= 1
                    except Exception as e:
                        st.error(f"Error in Batch {current_batch_num}: {e}")
                        retry -= 1
                        [cite_start]time.sleep(2) [cite: 23]
                
                progress_bar.progress(min((i + batch_sz) / total_lines, 1.0))
                [cite_start]time.sleep(1) [cite: 23]

            if trans_map:
                st.success("🎉 Done!")
                out_content = proc.get_output(trans_map)
                [cite_start]st.download_button("⬇️ DOWNLOAD TRANSLATED FILE", data=out_content, file_name=f"translated_{uploaded_file.name}") [cite: 24]
        
        except Exception as e:
            st.error(f"❌ Fatal Error: {e}")
