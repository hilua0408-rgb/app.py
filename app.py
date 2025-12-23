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

# --- 📦 SESSION STATE ---
if 'api_keys' not in st.session_state: st.session_state.api_keys = []
if 'active_key' not in st.session_state: st.session_state.active_key = None
if 'api_status' not in st.session_state: st.session_state.api_status = "Unknown"
if 'skipped_files' not in st.session_state: st.session_state.skipped_files = [] # Track skipped files

# --- 📱 SIDEBAR ---
with st.sidebar:
    st.header("📁 File Upload")
    uploaded_files = st.file_uploader(
        "Upload Subtitle Files", 
        type=['srt', 'vtt', 'ass'], 
        accept_multiple_files=True
    )
    st.markdown("---")
    
    # Show Skipped Files Status
    if st.session_state.skipped_files:
        st.warning(f"⏩ Skipped Files: {len(st.session_state.skipped_files)}")
        if st.button("Clear Skipped History"):
            st.session_state.skipped_files = []
            st.rerun()

# --- 🖥️ MAIN INTERFACE ---
st.title("✨ Gemini Subtitle Translator")

# --- ⚙️ API CONFIGURATION ---
with st.expander("🛠️ API Configuration & Keys", expanded=False):
    st.markdown("###### ➕ Add New API Key")
    c1, c2 = st.columns([0.85, 0.15])
    with c1:
        new_key_input = st.text_input("Key Input", placeholder="Paste 'AIza...' key here", label_visibility="collapsed")
    with c2:
        if st.button("Add", use_container_width=True):
            clean_key = new_key_input.strip()
            if len(clean_key) > 30 and (clean_key.startswith("AIza") or clean_key.startswith("Alza")): 
                if clean_key not in st.session_state.api_keys:
                    st.session_state.api_keys.append(clean_key)
                    if not st.session_state.active_key: st.session_state.active_key = clean_key
                    st.rerun()
            else: st.toast("❌ Invalid Key! Google Keys usually start with 'AIza'.")

    st.markdown("###### 🔑 Saved Keys")
    with st.container(height=180, border=True):
        if not st.session_state.api_keys: st.caption("No keys saved.")
        else:
            for idx, key in enumerate(st.session_state.api_keys):
                masked = f"{key[:6]}...{key[-4:]}"
                k1, k2 = st.columns([0.88, 0.12])
                with k1:
                    if key == st.session_state.active_key: st.success(f"✅ {masked}", icon=None)
                    else: 
                        if st.button(f"⚪ {masked}", key=f"sel_{idx}", use_container_width=True):
                            st.session_state.active_key = key; st.rerun()
                with k2:
                    if st.button("🗑️", key=f"del_{idx}"):
                        st.session_state.api_keys.pop(idx)
                        if st.session_state.active_key == key: st.session_state.active_key = None
                        st.rerun()

    if st.session_state.active_key:
        st.markdown("---")
        c_s1, c_s2 = st.columns([0.7, 0.3])
        with c_s1: st.caption(f"Status: **{st.session_state.api_status}**")
        with c_s2: 
            if st.button("Check Status", use_container_width=True):
                try: 
                    genai.Client(api_key=st.session_state.active_key).models.list(config={'page_size': 1})
                    st.session_state.api_status = "Alive 🟢"
                except: st.session_state.api_status = "Dead 🔴"
                st.rerun()
        
        with st.expander("⚙️ Advanced Tech Settings", expanded=False):
            enable_cooldown = st.checkbox("Smart Cooldown (90s on 429)", value=True)
            temp_val = st.slider("Temperature", 0.0, 2.0, 0.3)
            # Max Tokens - Unlimited Input
            max_tok_val = st.number_input("Max Output Tokens", min_value=100, value=8192, step=100, help="Higher is better for long translations.")
            delay_ms = st.number_input("Batch Delay (ms)", 0, 5000, 500)
    else:
        enable_cooldown=True; temp_val=0.3; max_tok_val=8192; delay_ms=500

# --- MAIN SETTINGS ---
col1, col2 = st.columns(2)
with col1:
    default_models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.5-flash"]
    if 'model_list' not in st.session_state: st.session_state['model_list'] = default_models
    model_name = st.selectbox("MODEL_NAME", st.session_state['model_list'])
    
    if st.button("🔄 Fetch Models"):
        if st.session_state.active_key:
            try:
                api_models = genai.Client(api_key=st.session_state.active_key).models.list()
                fetched = [m.name.replace("models/", "") for m in api_models if 'gemini' in m.name.lower()]
                if fetched:
                    st.session_state['model_list'] = sorted(list(set(default_models + fetched)), reverse=True)
                    st.success(f"Found {len(fetched)} models!"); time.sleep(1); st.rerun()
            except Exception as e: st.error(f"Error: {e}")

    source_lang = st.text_input("SOURCE_LANGUAGE", "English")

with col2:
    target_lang = st.text_input("TARGET_LANGUAGE", "Roman Hindi")
    batch_sz = st.number_input("BATCH_SIZE", 1, 500, 20)

user_instr = st.text_area("USER_INSTRUCTION", "Translate into natural Roman Hindi. Keep Anime terms in English.")
start_button = st.button("🚀 START TRANSLATION NOW", use_container_width=True)

# --- PROCESSOR ---
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
            l = b.split('\n'); 
            if len(l)>=3: self.lines.append({'id':l[0].strip(), 't':l[1].strip(), 'txt':"\n".join(l[2:])})
    def vtt(self):
        c={'id':None,'t':None,'txt':[]}; cnt=1; lines=self.raw.split('\n')
        if lines and lines[0].strip()=="WEBVTT": lines=lines[1:]
        for l in lines:
            l=l.strip()
            if "-->" in l: c['t']=l; c['id']=str(cnt); cnt+=1
            elif l=="" and c['t']: 
                if c['txt']: self.lines.append(c.copy())
                c={'id':None,'t':None,'txt':[]}
            elif c['t']: c['txt'].append(l)
        if c['t'] and c['txt']: self.lines.append(c)
        for x in self.lines: x['txt']="\n".join(x['txt'])
    def ass(self):
        cnt=1
        for l in self.raw.split('\n'):
            if l.startswith("Dialogue:"):
                p=l.split(',',9); 
                if len(p)==10: self.lines.append({'id':str(cnt),'raw':l,'txt':p[9].strip()}); cnt+=1
    def get_output(self, data):
        output = ""
        if self.ext=='.srt': 
            for x in self.lines: output+=f"{x['id']}\n{x['t']}\n{data.get(x['id'],x['txt'])}\n\n"
        elif self.ext=='.vtt': 
            output+="WEBVTT\n\n"; 
            for x in self.lines: output+=f"{x['t']}\n{data.get(x['id'],x['txt'])}\n\n"
        elif self.ext=='.ass':
            cnt=1
            for l in self.raw.split('\n'):
                if l.startswith("Dialogue:"):
                    p=l.split(',',9)
                    if len(p)==10: output+=",".join(p[:9])+","+data.get(str(cnt),p[9].strip())+"\n"; cnt+=1
                    else: output+=l+"\n"
                else: output+=l+"\n"
        return output

# --- EXECUTION ---
if start_button:
    if not st.session_state.active_key or not uploaded_files:
        st.error("❌ Add API Key & Upload Files!")
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
            
            for file_idx, uploaded_file in enumerate(uploaded_files):
                # --- SKIP LOGIC ---
                if uploaded_file.name in st.session_state.skipped_files:
                    st.warning(f"⏩ Skipping {uploaded_file.name} (as per user request).")
                    time.sleep(1)
                    continue
                
                proc = SubtitleProcessor(uploaded_file.name, uploaded_file.getvalue())
                total_lines = proc.parse()
                file_status_ph.markdown(f"### 📂 File {file_idx+1}/{len(uploaded_files)}: **{uploaded_file.name}**")
                
                trans_map = {}
                progress_text_ph.text(f"✅ Completed: 0 / {total_lines}")
                progress_bar.progress(0)
                
                cooldown_hits = 0 
                MAX_COOLDOWN_HITS = 3
                
                for i in range(0, total_lines, batch_sz):
                    current_batch_num = (i // batch_sz) + 1
                    chunk = proc.lines[i : i + batch_sz]
                    batch_txt = "".join([f"[{x['id']}]\n{x['txt']}\n\n" for x in chunk])
                    
                    prompt = f"""You are a translator.
TASK: Translate {source_lang} to {target_lang}.
NOTE: {user_instr}
STRICT OUTPUT RULES:
1. NO Code Blocks/Bolding.
2. ONLY format:
[ID]
Translated Text
Batch:
{batch_txt}"""
                    
                    retry = 3
                    success = False
                    
                    while retry > 0:
                        try:
                            start_line = i + 1
                            end_line = min(i + batch_sz, total_lines)
                            console_box.markdown(f"**⏳ Batch {current_batch_num} ({start_line}-{end_line})...**")
                            
                            if i > 0: time.sleep(delay_ms / 1000.0)

                            response_stream = client.models.generate_content_stream(
                                model=model_name, contents=prompt,
                                config=types.GenerateContentConfig(temperature=temp_val, max_output_tokens=max_tok_val)
                            )
                            
                            full_resp = ""
                            for chunk_resp in response_stream:
                                if chunk_resp.text:
                                    full_resp += chunk_resp.text
                                    console_box.markdown(f"**Translating...**\n\n```text\n{full_resp}\n```")
                                if chunk_resp.usage_metadata:
                                    total_session_tokens += chunk_resp.usage_metadata.total_token_count
                                    token_stats_ph.markdown(f"**Tokens:** `{total_session_tokens}`")

                            clean_text = full_resp.replace("```", "").replace("**", "")
                            matches = list(re.finditer(r'\[(\d+)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[\d+\]|$)', clean_text, re.DOTALL))
                            
                            if matches:
                                for m in matches: trans_map[m.group(1)] = m.group(2).strip()
                                success = True; break
                            else: 
                                console_box.warning("⚠️ Parsing Error. Retrying...")
                                retry -= 1; time.sleep(1)

                        except Exception as e:
                            err_msg = str(e).lower()
                            if ("429" in err_msg or "quota" in err_msg) and enable_cooldown:
                                if cooldown_hits < MAX_COOLDOWN_HITS:
                                    console_box.error(f"🛑 Rate Limit! Waiting 90s... ({cooldown_hits+1}/{MAX_COOLDOWN_HITS})")
                                    bar = st.progress(0)
                                    for s in range(90): time.sleep(1); bar.progress((s+1)/90)
                                    bar.empty(); cooldown_hits += 1; console_box.info("♻️ Resuming..."); continue 
                                else: console_box.error("❌ Max Cooldowns reached."); retry=0; break
                            else: console_box.error(f"Error: {e}"); retry -= 1; time.sleep(2)

                    if success:
                        fin = min(i + batch_sz, total_lines)
                        progress_text_ph.text(f"✅ Completed: {fin} / {total_lines}")
                        progress_bar.progress(fin / total_lines)
                    else:
                        # --- 🚨 FAILURE OPTIONS MENU ---
                        st.error(f"❌ Batch {current_batch_num} FAILED after multiple attempts.")
                        
                        st.markdown("### ⚠️ Choose Action:")
                        opt_c1, opt_c2 = st.columns(2)
                        
                        with opt_c1:
                            if st.button("🔄 Try Again (Restart File)", key=f"retry_{file_idx}_{current_batch_num}", use_container_width=True):
                                st.rerun()
                        
                        with opt_c2:
                            # Only show 'Next File' if there is a next file
                            if file_idx < len(uploaded_files) - 1:
                                if st.button("⏭️ Skip to Next File", key=f"skip_{file_idx}", use_container_width=True):
                                    st.session_state.skipped_files.append(uploaded_file.name)
                                    st.rerun()
                            else:
                                st.warning("🚫 No Next File Available")

                        st.stop() # Stops execution here to wait for user input
                
                if trans_map:
                    out = proc.get_output(trans_map)
                    st.success(f"✅ {uploaded_file.name} Done!")
                    st.download_button(f"⬇️ DOWNLOAD", out, f"trans_{uploaded_file.name}", key=f"d{file_idx}")

            st.balloons()
            st.success("🎉 Process Complete!")
    
        except Exception as e: st.error(f"❌ Fatal Error: {e}")
