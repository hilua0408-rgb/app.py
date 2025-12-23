import streamlit as st
import re
import os
import time
from google import genai
from google.genai import types

# Page Setup
st.set_page_config(page_title="Gemini Subtitle Pro V2", layout="wide")

# --- 📦 SESSION STATE ---
if 'api_keys' not in st.session_state: st.session_state.api_keys = []
if 'active_key' not in st.session_state: st.session_state.active_key = None
if 'api_status' not in st.session_state: st.session_state.api_status = "Unknown"
if 'skipped_files' not in st.session_state: st.session_state.skipped_files = [] 

# --- 📱 SIDEBAR ---
with st.sidebar:
    st.header("📁 File Upload")
    uploaded_files = st.file_uploader(
        "Upload Subtitle Files", 
        type=['srt', 'vtt', 'ass'], 
        accept_multiple_files=True
    )
    st.markdown("---")
    
    if st.session_state.skipped_files:
        st.warning(f"⏩ Skipped Files: {len(st.session_state.skipped_files)}")
        if st.button("Clear Skipped History"):
            st.session_state.skipped_files = []
            st.rerun()

# --- 🖥️ MAIN INTERFACE ---
st.markdown("### ✨ Gemini Subtitle Translator & Polisher")

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
                    with genai.Client(api_key=st.session_state.active_key) as client:
                        list(client.models.list(config={'page_size': 1}))
                    st.session_state.api_status = "Alive 🟢"
                except: st.session_state.api_status = "Dead 🔴"
                st.rerun()
        
        with st.expander("⚙️ Advanced Tech Settings", expanded=False):
            enable_cooldown = st.checkbox("Smart Cooldown (90s on 429)", value=True)
            temp_val = st.slider("Temperature", 0.0, 2.0, 0.3)
            max_tok_val = st.number_input("Max Output Tokens", min_value=100, value=8192, step=100)
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
                with genai.Client(api_key=st.session_state.active_key) as client:
                    api_models = list(client.models.list())
                    
                fetched = [m.name.replace("models/", "") for m in api_models if 'gemini' in m.name.lower()]
                if fetched:
                    st.session_state['model_list'] = sorted(list(set(default_models + fetched)), reverse=True)
                    st.success(f"Found {len(fetched)} models!"); time.sleep(1); st.rerun()
            except Exception as e: st.error(f"Error: {e}")

    source_lang = st.text_input("SOURCE_LANGUAGE", "English")

with col2:
    target_lang = st.text_input("TARGET_LANGUAGE", "Roman Hindi")
    batch_sz = st.number_input("BATCH_SIZE", 1, 500, 20)

# --- FEATURES SECTION (UPDATED LAYOUT) ---
st.markdown("### ⚡ Workflow Steps")

# 1. Memory
enable_memory = st.checkbox("🧠 1. Context Memory (Maintains story flow)", value=True)

st.divider()

# 2. Analysis
enable_analysis = st.checkbox("🧐 2. Deep File Analysis (Read full file first)", value=False)
if enable_analysis:
    analysis_instr = st.text_area(
        "Analysis Context Note", 
        placeholder="E.g. 'Main character is female, keep tone serious...'",
        height=68
    )
else: analysis_instr = ""

st.divider()

# 3. Revision (Placed directly after Analysis as requested)
enable_revision = st.checkbox("✨ 3. Revision / Polish (Fix grammar & flow after translation)", value=False)
if enable_revision:
    revision_instr = st.text_area(
        "Revision Instructions",
        placeholder="E.g. 'Fix grammar, check gender consistency, make it sound like Anime...'",
        height=68
    )
else: revision_instr = ""


# --- USER INSTRUCTIONS ---
st.markdown("---")
user_instr = st.text_area("USER_INSTRUCTION (For Main Translation)", "Translate into natural Roman Hindi. Keep Anime terms in English.")

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
            with genai.Client(api_key=st.session_state.active_key) as client:
                st.markdown("## Translation Status")
                st.markdown("---")
                
                file_status_ph = st.empty()
                progress_text_ph = st.empty()
                progress_bar = st.progress(0)
                token_stats_ph = st.empty()
                
                st.markdown("### Live Console:")
                with st.container(height=300, border=True):
                    console_box = st.empty()
                
                total_session_tokens = 0
                
                for file_idx, uploaded_file in enumerate(uploaded_files):
                    if uploaded_file.name in st.session_state.skipped_files:
                        st.warning(f"⏩ Skipping {uploaded_file.name}."); time.sleep(1); continue
                    
                    proc = SubtitleProcessor(uploaded_file.name, uploaded_file.getvalue())
                    total_lines = proc.parse()
                    file_status_ph.markdown(f"### 📂 File {file_idx+1}/{len(uploaded_files)}: **{uploaded_file.name}**")
                    
                    # --- PHASE 1: FULL FILE ANALYSIS ---
                    file_context_summary = "No analysis requested."
                    
                    if enable_analysis:
                        try:
                            console_box.info("🧠 Analyzing the full file context... Please wait.")
                            full_script = "\n".join([f"{x['id']}: {x['txt']}" for x in proc.lines])
                            
                            analysis_system_prompt = f"""
ROLE: You are a LOGIC-ONLY DATA ANALYST.
INPUT CONSTRAINTS: Input contains {total_lines} lines.
YOUR TASK: Provide a context report based ONLY on the provided text.
REQUIRED OUTPUT FORMAT:
1. **Genre & Tone**
2. **Story Flow (Summary)**
3. **Key Characters** (Names + Gender + Relations)
4. **Translation Notes** (Specific terminology)
User Instructions: "{analysis_instr}"

INPUT TEXT:
{full_script}
"""
                            ana_stream = client.models.generate_content_stream(
                                model=model_name,
                                contents=analysis_system_prompt,
                                config=types.GenerateContentConfig(temperature=0.3)
                            )
                            
                            full_analysis_text = ""
                            for chunk in ana_stream:
                                if chunk.text:
                                    full_analysis_text += chunk.text
                                    console_box.markdown(f"**🧠 Analyzing File...**\n\n{full_analysis_text}")
                            
                            file_context_summary = full_analysis_text
                            console_box.success("✅ Analysis Complete! Starting Translation...")
                            time.sleep(1.5)
                            
                        except Exception as e:
                            console_box.error(f"⚠️ Analysis Failed: {e}. Proceeding without context.")
                            file_context_summary = "Analysis failed."
                            time.sleep(2)

                    # --- PHASE 2: BATCH TRANSLATION ---
                    trans_map = {}
                    progress_text_ph.text(f"✅ Completed: 0 / {total_lines}")
                    progress_bar.progress(0)
                    cooldown_hits = 0; MAX_COOLDOWN_HITS = 3
                    
                    previous_batch_context = ""

                    for i in range(0, total_lines, batch_sz):
                        current_batch_num = (i // batch_sz) + 1
                        chunk = proc.lines[i : i + batch_sz]
                        batch_txt = "".join([f"[{x['id']}]\n{x['txt']}\n\n" for x in chunk])
                        
                        memory_block = ""
                        if enable_memory and previous_batch_context:
                            memory_block = f"\n[PREVIOUS TRANSLATED BATCH - FOR FLOW]:\n{previous_batch_context}\n(Continue the story smoothly from here)\n"

                        prompt = f"""You are a professional translator.
TASK: Translate {source_lang} to {target_lang}.

[FILE CONTEXT & SUMMARY]:
{file_context_summary}

{memory_block}

[USER INSTRUCTIONS]:
{user_instr}

[STRICT FORMAT RULES]:
1. NO Code Blocks/Bolding.
2. ONLY format:
[ID]
Translated Text

[BATCH TO TRANSLATE]:
{batch_txt}"""
                        
                        retry = 3; success = False
                        
                        while retry > 0:
                            try:
                                start_line = i + 1; end_line = min(i + batch_sz, total_lines)
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
                                    if enable_memory: previous_batch_context = clean_text[-1000:] 
                                    success = True; break
                                else: console_box.warning("⚠️ Formatting Error. Retrying..."); retry -= 1; time.sleep(1)

                            except Exception as e:
                                err_msg = str(e).lower()
                                if ("429" in err_msg or "quota" in err_msg) and enable_cooldown:
                                    if cooldown_hits < MAX_COOLDOWN_HITS:
                                        console_box.error(f"🛑 Limit Hit! Waiting 90s... ({cooldown_hits+1}/{MAX_COOLDOWN_HITS})")
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
                            st.error(f"❌ Batch {current_batch_num} FAILED.")
                            st.stop()

                    # --- PHASE 3: REVISION (OPTIONAL) ---
                    if enable_revision and trans_map:
                        console_box.info("✨ Starting One-Shot Revision/Polish...")
                        
                        # Prepare Data: Sort by ID numeric
                        sorted_ids = sorted(trans_map.keys(), key=lambda x: int(x) if x.isdigit() else x)
                        full_draft_text = "\n\n".join([f"[{vid}]\n{trans_map[vid]}" for vid in sorted_ids])
                        
                        revision_prompt = f"""
ROLE: Expert Editor & Proofreader & Fixer
TASK: Polish the translated text for grammar, flow, and gender consistency.
INPUT FORMAT: [ID] Text
OUTPUT FORMAT: [ID] Fixed Text
CRITICAL RULES:
1. Keep the EXACT same number of lines.
2. Do NOT merge lines.
3. Output format must match: [ID] Your Fixed Text

[ANALYSIS CONTEXT]:
{file_context_summary}

USER NOTES: "{revision_instr}"

INPUT TEXT:
{full_draft_text}
"""
                        revision_success = False
                        rev_attempts = 0
                        
                        while not revision_success and rev_attempts < 2:
                            try:
                                rev_stream = client.models.generate_content_stream(
                                    model=model_name,
                                    contents=revision_prompt,
                                    config=types.GenerateContentConfig(temperature=0.3)
                                )
                                
                                full_rev_resp = ""
                                for chunk in rev_stream:
                                    if chunk.text:
                                        full_rev_resp += chunk.text
                                        console_box.markdown(f"**✨ Revising...**\n\n```text\n{full_rev_resp}\n```")
                                
                                # Update Map with Revised Text
                                rev_clean = full_rev_resp.replace("```", "").replace("**", "")
                                rev_matches = list(re.finditer(r'\[(\d+)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[\d+\]|$)', rev_clean, re.DOTALL))
                                
                                if rev_matches:
                                    # Update logic
                                    for m in rev_matches:
                                        rid = m.group(1)
                                        if rid in trans_map:
                                            trans_map[rid] = m.group(2).strip()
                                    revision_success = True
                                    console_box.success("✅ Revision Applied Successfully!")
                                else:
                                    raise Exception("Revision output format invalid.")

                            except Exception as e:
                                console_box.error(f"⚠️ Revision Failed (Attempt {rev_attempts+1}): {e}")
                                rev_attempts += 1
                                time.sleep(2)
                        
                        if not revision_success:
                            st.error("❌ Revision Failed. Saving ORIGINAL translated version.")
                            # Show specific error UI
                            st.warning("⚠️ The revision process encountered an error.")
                            c_err1, c_err2 = st.columns(2)
                            with c_err1:
                                # Fallback download for un-revised content
                                orig_out = proc.get_output(trans_map)
                                st.download_button("💾 Save Original (Unrevised)", orig_out, f"ORIGINAL_{uploaded_file.name}")
                            with c_err2:
                                if st.button("🔄 Retry Revision"):
                                    st.rerun()
                            st.stop() # Stop further processing so user deals with error

                    # --- FINAL OUTPUT GENERATION ---
                    if trans_map:
                        out = proc.get_output(trans_map)
                        st.success(f"✅ {uploaded_file.name} Done!")
                        st.download_button(f"⬇️ DOWNLOAD", out, f"trans_{uploaded_file.name}", key=f"d{file_idx}")

                st.balloons()
                st.success("🎉 Process Complete!")
    
        except Exception as e: st.error(f"❌ Fatal Error: {e}")
