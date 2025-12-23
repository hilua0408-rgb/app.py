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
    uploaded_files = st.file_uploader(
        "Upload Subtitle Files", 
        type=['srt', 'vtt', 'ass'], 
        accept_multiple_files=True
    )
    st.markdown("---")
    st.info("💡 Tip: Upload multiple files to translate them one by one.")

# --- 🖥️ MAIN INTERFACE (Settings) ---
st.title("✨ Gemini Subtitle Translator")

api_key = st.text_input("GOOGLE_API_KEY", type="password", help="Paste your Gemini API Key")

col1, col2 = st.columns(2)
with col1:
    # 1. Default List
    default_models = [
        "gemini-2.0-flash",
        "gemini-1.5-flash", 
        "gemini-1.5-pro",
        "gemini-3-pro-preview", 
        "gemini-3-flash-preview", 
        "gemini-2.5-pro", 
        "gemini-2.5-flash"
    ]

    if 'model_list' not in st.session_state:
        st.session_state['model_list'] = default_models

    model_name = st.selectbox("MODEL_NAME", st.session_state['model_list'])

    # --- 🔄 FIXED FETCH BUTTON ---
    if st.button("🔄 Fetch Available Models from API"):
        if not api_key:
            st.error("⚠️ Pehle API Key daalein!")
        else:
            try:
                client = genai.Client(api_key=api_key)
                api_models = client.models.list()
                
                fetched_names = []
                for m in api_models:
                    # Fix: supported_generation_methods check hata diya (causing error)
                    # Sirf Naam check karenge
                    if hasattr(m, 'name') and 'gemini' in m.name.lower():
                        clean_name = m.name.replace("models/", "")
                        fetched_names.append(clean_name)
                
                if fetched_names:
                    # Merge and Sort
                    updated_list = list(set(default_models + fetched_names))
                    updated_list.sort(reverse=True) # Newest first
                    st.session_state['model_list'] = updated_list
                    st.success(f"✅ Found {len(fetched_names)} models! List updated.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("⚠️ No 'Gemini' models found via API.")
                    
            except Exception as e:
                st.error(f"❌ Fetch Error: {e}")

    source_lang = st.text_input("SOURCE_LANGUAGE", "English")

with col2:
    target_lang = st.text_input("TARGET_LANGUAGE", "Roman Hindi")
    batch_sz = st.number_input("BATCH_SIZE", value=20, step=1)

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
    if not api_key or not uploaded_files:
        st.error("❌ API Key aur Files dono zaroori hain!")
    else:
        try:
            client = genai.Client(api_key=api_key)
            
            # --- STATUS DASHBOARD ---
            st.markdown("## Translation Status")
            st.markdown("---")
            
            file_status_ph = st.empty()
            progress_text_ph = st.empty()
            progress_bar = st.progress(0)
            token_stats_ph = st.empty()
            
            st.markdown("### Current Batch Status (Live):")
            with st.container(height=300, border=True):
                console_box = st.empty()
            
            total_session_tokens = 0
            total_files_count = len(uploaded_files)

            # --- FILE LOOP ---
            for file_idx, uploaded_file in enumerate(uploaded_files):
                file_num = file_idx + 1
                
                proc = SubtitleProcessor(uploaded_file.name, uploaded_file.getvalue())
                total_lines = proc.parse()
                
                file_status_ph.markdown(f"### 📂 Processing file {file_num} / {total_files_count}: **{uploaded_file.name}**")
                
                trans_map = {}
                total_batches = math.ceil(total_lines / batch_sz)
                
                for i in range(0, total_lines, batch_sz):
                    current_batch_num = (i // batch_sz) + 1
                    chunk = proc.lines[i : i + batch_sz]
                    batch_txt = "".join([f"[{x['id']}]\n{x['txt']}\n\n" for x in chunk])
                    
                    progress_text_ph.text(f"File Progress: {min(i + batch_sz, total_lines)} / {total_lines} Subtitles")
                    
                    prompt = f"""You are a professional subtitle translation AI.
TASK: Translate from {source_lang} to {target_lang}
USER NOTE: {user_instr}
FORMAT RULES:
1. Format MUST be: [ID] Translated Text
2. One empty line between blocks.
3. No Markdown.
Batch:
{batch_txt}"""
                    
                    retry = 3
                    success = False
                    batch_tokens = 0
                    
                    while retry > 0:
                        try:
                            console_box.markdown(f"**⏳ Batch {current_batch_num} Starting...**")
                            response_stream = client.models.generate_content_stream(model=model_name, contents=prompt)
                            
                            full_batch_response = ""
                            
                            for chunk_resp in response_stream:
                                if chunk_resp.text:
                                    full_batch_response += chunk_resp.text
                                    console_box.markdown(f"**Batch {current_batch_num} Translating...**\n\n```text\n{full_batch_response}\n```")
                                
                                if chunk_resp.usage_metadata:
                                    batch_tokens = chunk_resp.usage_metadata.total_token_count

                            total_session_tokens += batch_tokens
                            token_stats_ph.markdown(f"**Batch Tokens:** `{batch_tokens}` | **Total Tokens:** `{total_session_tokens}`")

                            matches = list(re.finditer(r'\[(\d+)\]\s*\n(.*?)(?=\n\[\d+\]|$)', full_batch_response, re.DOTALL))
                            if matches:
                                for m in matches: trans_map[m.group(1)] = m.group(2).strip()
                                success = True; break
                            else: retry -= 1; time.sleep(1)

                        except Exception as e:
                            st.error(f"Error: {e}")
                            retry -= 1; time.sleep(2)
                    
                    progress_bar.progress(min((i + batch_sz) / total_lines, 1.0))
                
                if trans_map:
                    out_content = proc.get_output(trans_map)
                    st.success(f"✅ {uploaded_file.name} Completed!")
                    st.download_button(
                        f"⬇️ DOWNLOAD {uploaded_file.name}", 
                        data=out_content, 
                        file_name=f"translated_{uploaded_file.name}",
                        key=f"dl_{file_idx}"
                    )

            st.balloons()
            st.success("🎉 All Files Processed Successfully!")
        
        except Exception as e:
            st.error(f"❌ Fatal Error: {e}")
