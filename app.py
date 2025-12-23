import streamlit as st
import re
import os
import time
import math
import datetime
from google import genai
from google.genai import types

# Page Setup
st.set_page_config(page_title="Gemini Subtitle Pro", layout="wide")

# --- 📦 SESSION STATE INITIALIZATION ---
if 'api_keys' not in st.session_state:
    st.session_state.api_keys = []
if 'active_key' not in st.session_state:
    st.session_state.active_key = None
if 'api_status' not in st.session_state:
    st.session_state.api_status = "Unknown"

# --- 📱 SIDEBAR ---
with st.sidebar:
    st.header("📁 File Upload")
    uploaded_files = st.file_uploader(
        "Upload Subtitle Files", 
        type=['srt', 'vtt', 'ass'], 
        accept_multiple_files=True
    )
    st.markdown("---")
    st.info("💡 Tip: Upload multiple files to translate them one by one.")

# --- 🖥️ MAIN INTERFACE ---
st.title("✨ Gemini Subtitle Translator")

# --- ⚙️ FOLDABLE API CONFIGURATION MENU (UPDATED UI) ---
with st.expander("🛠️ API Configuration & Keys", expanded=False):
    
    # 1. Add New Key Section (Compact)
    st.markdown("### ➕ Add New API Key")
    c1, c2 = st.columns([0.8, 0.2])
    with c1:
        new_key_input = st.text_input("Enter Gemini API Key", placeholder="Paste key here...", label_visibility="collapsed")
    with c2:
        if st.button("Add", use_container_width=True):
            if new_key_input and new_key_input not in st.session_state.api_keys:
                st.session_state.api_keys.append(new_key_input)
                if not st.session_state.active_key:
                    st.session_state.active_key = new_key_input
                st.rerun()

    # 2. SCROLLABLE KEY MANAGER BOX
    st.markdown("### 🔑 Saved Keys (Tap to Select)")
    
    # Ye hai wo SCROLLABLE BOX (Height fixed hai, content zyada hoga to scroll hoga)
    with st.container(height=200, border=True):
        if not st.session_state.api_keys:
            st.caption("No keys saved yet. Add one above.")
        else:
            for idx, key in enumerate(st.session_state.api_keys):
                # Mask Key (Show only first 8 chars)
                masked_label = f"🔑 {key[:8]}............{key[-4:]}"
                
                # Check if this key is ACTIVE
                if key == st.session_state.active_key:
                    # ACTIVE KEY DESIGN (Green Highlight)
                    col_txt, col_del = st.columns([0.85, 0.15])
                    with col_txt:
                        st.success(f"✅ Active: {masked_label}")
                    with col_del:
                        if st.button("🗑️", key=f"del_{idx}", help="Delete Key"):
                            st.session_state.api_keys.pop(idx)
                            if st.session_state.active_key == key:
                                st.session_state.active_key = None
                            st.rerun()
                else:
                    # INACTIVE KEY DESIGN (Click button to select)
                    col_btn, col_del = st.columns([0.85, 0.15])
                    with col_btn:
                        # Pura button click karne par select ho jayega
                        if st.button(masked_label, key=f"sel_{idx}", use_container_width=True):
                            st.session_state.active_key = key
                            st.rerun()
                    with col_del:
                        if st.button("❌", key=f"del_{idx}"):
                            st.session_state.api_keys.pop(idx)
                            st.rerun()

    # 3. Status & Config
    if st.session_state.active_key:
        st.markdown("---")
        # Status Check
        col_s1, col_s2 = st.columns([0.7, 0.3])
        with col_s1:
            st.write(f"**Current Status:** {st.session_state.api_status}")
        with col_s2:
            if st.button("🔄 Check Status", use_container_width=True):
                try:
                    client = genai.Client(api_key=st.session_state.active_key)
                    list(client.models.list(config={'page_size': 1}))
                    st.session_state.api_status = "🟢 Online"
                except:
                    st.session_state.api_status = "🔴 Offline / Invalid"
                st.rerun()
        
        # Advanced Settings Toggle
        with st.expander("⚙️ Advanced Settings (Batch, Temperature)", expanded=False):
            enable_cooldown = st.checkbox("Enable API Cooldown", value=True)
            batch_sz = st.number_input("Batch Size", 1, 500, 20)
            temperature_val = st.slider("Temperature", 0.0, 2.0, 0.3)
            max_tokens_val = st.number_input("Max Tokens", 1000, 32000, 8192)
            batch_delay_ms = st.number_input("Delay (ms)", 0, 5000, 500)
    else:
        # Default values agar key na ho
        enable_cooldown = True
        batch_sz = 20
        temperature_val = 0.3
        max_tokens_val = 8192
        batch_delay_ms = 500

# --- MAIN SETTINGS ---
col1, col2 = st.columns(2)
with col1:
    default_models = [
        "gemini-2.0-flash",
        "gemini-1.5-flash", 
        "gemini-1.5-pro",
        "gemini-2.5-flash"
    ]
    if 'model_list' not in st.session_state:
        st.session_state['model_list'] = default_models

    model_name = st.selectbox("MODEL_NAME", st.session_state['model_list'])
    
    if st.button("🔄 Fetch Available Models"):
        if st.session_state.active_key:
            try:
                client = genai.Client(api_key=st.session_state.active_key)
                api_models = client.models.list()
                fetched_names = []
                for m in api_models:
                    if hasattr(m, 'name') and 'gemini' in m.name.lower():
                        fetched_names.append(m.name.replace("models/", ""))
                if fetched_names:
                    updated_list = list(set(default_models + fetched_names))
                    updated_list.sort(reverse=True)
                    st.session_state['model_list'] = updated_list
                    st.success(f"✅ Found {len(fetched_names)} models!")
                    time.sleep(1); st.rerun()
            except Exception as e: st.error(f"Error: {e}")
        else: st.error("Select an API Key first!")

    source_lang = st.text_input("SOURCE_LANGUAGE", "English")

with col2:
    target_lang = st.text_input("TARGET_LANGUAGE", "Roman Hindi")
    st.caption(f"Settings: Batch {batch_sz} | Delay {batch_delay_ms}ms")

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
    if not st.session_state.active_key or not uploaded_files:
        st.error("❌ Please Add & Select an API Key and Upload Files!")
    else:
        try:
            client = genai.Client(api_key=st.session_state.active_key)
            
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

            for file_idx, uploaded_file in enumerate(uploaded_files):
                file_num = file_idx + 1
                proc = SubtitleProcessor(uploaded_file.name, uploaded_file.getvalue())
                total_lines = proc.parse()
                
                file_status_ph.markdown(f"### 📂 Processing file {file_num} / {total_files_count}: **{uploaded_file.name}**")
                
                trans_map = {}
                progress_text_ph.text(f"✅ Completed: 0 / {total_lines} Subtitles")
                progress_bar.progress(0)
                
                for i in range(0, total_lines, batch_sz):
                    current_batch_num = (i // batch_sz) + 1
                    chunk = proc.lines[i : i + batch_sz]
                    batch_txt = "".join([f"[{x['id']}]\n{x['txt']}\n\n" for x in chunk])
                    
                    prompt = f"""You are a translator.
TASK: Translate {source_lang} to {target_lang}.
NOTE: {user_instr}
STRICT OUTPUT RULES:
1. DO NOT use Code Blocks (```).
2. DO NOT use Bolding (**).
3. ONLY provide the format:
[ID]
Translated Text
Batch to translate:
{batch_txt}"""
                    
                    retry = 3
                    success = False
                    batch_tokens = 0
                    
                    while retry > 0:
                        try:
                            start_line = i + 1
                            end_line = min(i + batch_sz, total_lines)
                            console_box.markdown(f"**⏳ Processing Batch {current_batch_num} (Lines {start_line}-{end_line})...**")
                            
                            if enable_cooldown and i > 0:
                                time.sleep(batch_delay_ms / 1000.0)

                            response_stream = client.models.generate_content_stream(
                                model=model_name, 
                                contents=prompt,
                                config=types.GenerateContentConfig(
                                    temperature=temperature_val,
                                    max_output_tokens=max_tokens_val
                                )
                            )
                            
                            full_batch_response = ""
                            
                            for chunk_resp in response_stream:
                                if chunk_resp.text:
                                    full_batch_response += chunk_resp.text
                                    console_box.markdown(f"**Batch {current_batch_num} Translating...**\n\n```text\n{full_batch_response}\n```")
                                if chunk_resp.usage_metadata:
                                    batch_tokens = chunk_resp.usage_metadata.total_token_count

                            total_session_tokens += batch_tokens
                            token_stats_ph.markdown(f"**Batch Tokens:** `{batch_tokens}` | **Total Tokens:** `{total_session_tokens}`")

                            clean_text = full_batch_response.replace("```", "").replace("**", "")
                            matches = list(re.finditer(r'\[(\d+)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[\d+\]|$)', clean_text, re.DOTALL))
                            
                            if matches and len(matches) > 0:
                                for m in matches: trans_map[m.group(1)] = m.group(2).strip()
                                success = True; break
                            else: 
                                console_box.warning(f"⚠️ Parsing Issue. Retrying...")
                                retry -= 1
                                time.sleep(1)
                        except Exception as e:
                            console_box.error(f"Error: {e}. Retrying...")
                            retry -= 1
                            time.sleep(2)
                    
                    if success:
                        completed_count = min(i + batch_sz, total_lines)
                        progress_text_ph.text(f"✅ Completed: {completed_count} / {total_lines} Subtitles")
                        progress_bar.progress(completed_count / total_lines)
                    else:
                        st.error(f"❌ Batch {current_batch_num} Failed.")
                
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
            st.success("🎉 All Files Processed!")
        
        except Exception as e:
            st.error(f"❌ Fatal Error: {e}")
