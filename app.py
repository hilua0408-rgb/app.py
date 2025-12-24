import streamlit as st
import re
import os
import time
from google import genai
from google.genai import types

# Page Setup
st.set_page_config(page_title="Gemini Subtitle Pro V2.7 (Resume Edition)", layout="wide")

# --- 📦 SESSION STATE ---
if 'api_keys' not in st.session_state: st.session_state.api_keys = []
if 'active_key' not in st.session_state: st.session_state.active_key = None
if 'api_status' not in st.session_state: st.session_state.api_status = "Unknown"
if 'skipped_files' not in st.session_state: st.session_state.skipped_files = []
if 'file_edits' not in st.session_state: st.session_state.file_edits = {}

# 🔥 NEW: Job Progress Database for Resume Feature
# Format: {'filename.srt': {'status': 'paused', 'done_ids': [], 'trans_map': {}, 'analysis': None}}
if 'job_progress' not in st.session_state: st.session_state.job_progress = {}

# --- 📱 SIDEBAR & RESET LOGIC ---
with st.sidebar:
    st.header("📁 File Upload")
    uploaded_files = st.file_uploader(
        "Upload Subtitle Files",
        type=['srt', 'vtt', 'ass'],
        accept_multiple_files=True
    )
    st.markdown("---")
    
    # 🛑 RESET LOGIC: Agar user file delete kare, to progress bhi delete ho jaye
    if uploaded_files:
        current_filenames = [f.name for f in uploaded_files]
        # Check existing progress keys
        progress_keys = list(st.session_state.job_progress.keys())
        for key in progress_keys:
            if key not in current_filenames:
                del st.session_state.job_progress[key] # Delete progress for removed file
    else:
        st.session_state.job_progress = {} # Clear all if no files

    if st.session_state.skipped_files:
        st.warning(f"⏩ Skipped Files: {len(st.session_state.skipped_files)}")
        if st.button("Clear Skipped History"):
            st.session_state.skipped_files = []
            st.rerun()

# --- 🖥️ MAIN INTERFACE ---
st.markdown("### ✨ Gemini Subtitle Translator & Polisher")

# --- PROCESSOR CLASS ---
class SubtitleProcessor:
    def __init__(self, filename, content_bytes):
        self.ext = os.path.splitext(filename)[1].lower()
        try: self.raw = content_bytes.decode('utf-8').replace('\r\n', '\n')
        except: self.raw = content_bytes.decode('latin-1').replace('\r\n', '\n')
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

# --- 1. API CONFIGURATION & ADVANCED SETTINGS ---
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
            else: st.toast("❌ Invalid Key!")

    st.markdown("###### 🔑 Saved Keys")
    with st.container(height=120, border=True):
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
        st.divider()
        c_s1, c_s2 = st.columns([0.7, 0.3])
        with c_s1: st.caption(f"API Status: **{st.session_state.api_status}**")
        with c_s2:
            if st.button("Check Status", use_container_width=True):
                try:
                    with genai.Client(api_key=st.session_state.active_key) as client:
                        list(client.models.list(config={'page_size': 1}))
                    st.session_state.api_status = "Alive 🟢"
                except: st.session_state.api_status = "Dead 🔴"
                st.rerun()
        
        with st.expander("🎛️ Advanced Tech Parameters", expanded=False):
            c_a1, c_a2, c_a3 = st.columns(3)
            with c_a1: enable_cooldown = st.checkbox("Smart Cooldown", value=True)
            with c_a2: temp_val = st.slider("Temperature", 0.0, 2.0, 0.3)
            with c_a3: max_tok_val = st.number_input("Max Output Tokens", 100, 65536, 65536)
            delay_ms = 500
    else:
        enable_cooldown=True; temp_val=0.3; max_tok_val=65536; delay_ms=500

# --- 2. CLEAN FILE EDITOR WITH SEARCH ---
with st.expander("📝 File Editor (Search & Fix)", expanded=False):
    if not uploaded_files:
        st.info("⚠️ Please upload files in the sidebar first.")
    else:
        file_names = [f.name for f in uploaded_files]
        selected_file_name = st.selectbox("Select File to Edit", file_names)
        current_file_obj = next((f for f in uploaded_files if f.name == selected_file_name), None)
        
        if current_file_obj:
            if selected_file_name in st.session_state.file_edits:
                display_content = st.session_state.file_edits[selected_file_name]
            else:
                temp_proc = SubtitleProcessor(selected_file_name, current_file_obj.getvalue())
                temp_proc.parse()
                display_content = "\n\n".join([f"[{line['id']}]\n{line['txt']}" for line in temp_proc.lines])

            c_search1, c_search2 = st.columns([0.8, 0.2])
            search_query = c_search1.text_input("Find text...", label_visibility="collapsed", placeholder="Find text...")
            is_non_roman = c_search2.checkbox("Non-Roman")
            
            found_count = 0
            if search_query or is_non_roman:
                found_lines = []
                matches = list(re.finditer(r'\[(\d+)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[\d+\]|$)', display_content, re.DOTALL))
                for m in matches:
                    lid = m.group(1)
                    txt = m.group(2).strip()
                    match_found = False
                    if search_query and search_query.lower() in txt.lower(): match_found = True
                    
                    if is_non_roman:
                        clean_txt = re.sub(r'[^\w\s]', '', txt)
                        if re.search(r'[^\x00-\x7F]', clean_txt): match_found = True
                    
                    if match_found: found_lines.append(lid)
                
                found_count = len(found_lines)
                st.caption(f"🔍 Found in IDs: {', '.join(found_lines[:20])}..." if found_count > 0 else "🔍 No matches.")

            edited_content = st.text_area(f"Edit Content ({selected_file_name})", value=display_content, height=300, key=f"editor_{selected_file_name}")
            
            if edited_content != display_content:
                st.session_state.file_edits[selected_file_name] = edited_content
                st.success("✅ Changes saved! (AI will use this text)")

# --- 3. TRANSLATION SETTINGS ---
with st.expander("⚙️ Translation Settings", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        default_models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.5-flash"]
        if 'model_list' not in st.session_state: st.session_state['model_list'] = default_models
        model_name = st.selectbox("MODEL_NAME", st.session_state['model_list'])
        
        if st.button("🔄 Fetch Models"):
            if st.session_state.active_key:
                try:
                    with genai.Client(api_key=st.session_state.active_key) as client:
                        st.session_state['model_list'] = sorted([m.name.replace("models/","") for m in client.models.list() if 'gemini' in m.name.lower()], reverse=True)
                        st.success("Updated!"); st.rerun()
                except Exception as e: st.error(f"Error: {e}")
        source_lang = st.text_input("SOURCE_LANGUAGE", "English")

    with col2:
        target_lang = st.text_input("TARGET_LANGUAGE", "Roman Hindi")
        batch_sz = st.number_input("BATCH_SIZE", 1, 500, 20)

# --- FEATURES SECTION ---
st.markdown("### ⚡ Workflow Steps")
enable_memory = st.checkbox("🧠 1. Context Memory", value=True)
st.divider()

enable_analysis = st.checkbox("🧐 2. Deep File Analysis", value=False)
if enable_analysis: analysis_instr = st.text_area("Analysis Note", placeholder="Context...", height=68)
else: analysis_instr = ""

st.divider()

enable_revision = st.checkbox("✨ 3. Revision / Polish", value=False)
if enable_revision: revision_instr = st.text_area("Revision Note", placeholder="Instructions...", height=68)
else: revision_instr = ""

st.markdown("---")
user_instr = st.text_area("USER_INSTRUCTION", "Translate into natural Roman Hindi. Keep Anime terms in English.")

# --- 🚀 SMART START/RESUME BUTTON ---
# Logic: Check if any file has "paused" work
work_status = "new" # new, paused
for f in uploaded_files:
    if f.name in st.session_state.job_progress:
        if st.session_state.job_progress[f.name]['status'] == 'paused':
            work_status = "paused"
            break

c_btn1, c_btn2 = st.columns([0.8, 0.2])
with c_btn1:
    if work_status == "paused":
        btn_label = "▶️ CONTINUE / RESUME"
        btn_type = "primary"
        st.info("💾 Found saved progress. Clicking Resume will continue from where you left off.")
    else:
        btn_label = "🚀 START TRANSLATION"
        btn_type = "secondary"
    
    start_button = st.button(btn_label, type=btn_type, use_container_width=True)

with c_btn2:
    if st.button("🗑️ Reset All"):
        st.session_state.job_progress = {}
        st.rerun()

# --- EXECUTION ---
if start_button:
    if not st.session_state.active_key or not uploaded_files:
        st.error("❌ Add API Key & Upload Files!")
    else:
        # 🔄 SPINNER ADDED AS REQUESTED
        with st.spinner("🔄 Processing... (Click 'Stop' in browser to Pause)"):
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
                        if uploaded_file.name in st.session_state.skipped_files: continue
                        
                        fname = uploaded_file.name
                        
                        # --- INIT OR LOAD PROGRESS ---
                        if fname not in st.session_state.job_progress:
                            st.session_state.job_progress[fname] = {
                                'status': 'paused', 'done_ids': [], 'trans_map': {}, 'analysis': None
                            }
                        
                        job = st.session_state.job_progress[fname]
                        
                        # Parse
                        proc = SubtitleProcessor(fname, uploaded_file.getvalue())
                        proc.parse()
                        
                        # Apply User Edits if any
                        if fname in st.session_state.file_edits:
                            clean_edit_str = st.session_state.file_edits[fname]
                            user_edit_map = {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r'\[(.*?)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[.*?\]|$)', clean_edit_str, re.DOTALL)}
                            for line in proc.lines:
                                if line['id'] in user_edit_map: line['txt'] = user_edit_map[line['id']]
                        
                        total_lines = len(proc.lines)
                        file_status_ph.markdown(f"### 📂 File {file_idx+1}/{len(uploaded_files)}: **{fname}**")
                        
                        # --- PHASE 1: ANALYSIS (RESUMABLE) ---
                        file_context_summary = "No analysis requested."
                        if enable_analysis:
                            if job['analysis']: # Already done
                                file_context_summary = job['analysis']
                                console_box.info("🧠 Using Saved Analysis.")
                            else:
                                try:
                                    console_box.info("🧠 Analyzing content...")
                                    full_script = "\n".join([f"{x['id']}: {x['txt']}" for x in proc.lines])
                                    ana_stream = client.models.generate_content_stream(
                                        model=model_name,
                                        contents=f"ANALYZE THIS SUBTITLE FILE ({total_lines} lines). Give Genre, Tone, Key Characters, Notes.\nInput:\n{full_script[:30000]}", # Truncate for speed
                                        config=types.GenerateContentConfig(temperature=0.3)
                                    )
                                    full_analysis_text = ""
                                    for chunk in ana_stream:
                                        if chunk.text: full_analysis_text += chunk.text; console_box.markdown(f"**Analyzing...**\n\n{full_analysis_text}")
                                    
                                    file_context_summary = full_analysis_text
                                    # SAVE ANALYSIS
                                    job['analysis'] = full_analysis_text
                                    st.session_state.job_progress[fname] = job
                                    console_box.success("✅ Analysis Complete!"); time.sleep(1)
                                except Exception as e: console_box.error(f"⚠️ Analysis Failed: {e}"); file_context_summary = "Failed."

                        # --- PHASE 2: TRANSLATION (RESUMABLE) ---
                        trans_map = job['trans_map']
                        completed_set = set(job['done_ids'])
                        
                        progress_text_ph.text(f"✅ Completed: {len(completed_set)} / {total_lines}")
                        progress_bar.progress(len(completed_set) / total_lines)
                        
                        cooldown_hits = 0; MAX_COOLDOWN_HITS = 3

                        # Only iterate batches that are NOT fully done
                        for i in range(0, total_lines, batch_sz):
                            chunk = proc.lines[i : i + batch_sz]
                            
                            # Skip if all IDs in this chunk are already done
                            if all(x['id'] in completed_set for x in chunk):
                                continue

                            current_batch_num = (i // batch_sz) + 1
                            batch_txt = "".join([f"[{x['id']}]\n{x['txt']}\n\n" for x in chunk])
                            
                            memory_block = ""
                            if enable_memory and trans_map:
                                # Get last few translated lines for context
                                sorted_keys = sorted(trans_map.keys(), key=lambda x: int(x) if x.isdigit() else x)
                                if sorted_keys:
                                    last_keys = sorted_keys[-3:]
                                    memory_block = "\n[PREVIOUS CONTEXT]:\n" + "\n".join([f"[{k}] {trans_map[k]}" for k in last_keys]) + "\n"

                            prompt = f"""You are a professional translator.
TASK: Translate {source_lang} to {target_lang}.
[CONTEXT]: {file_context_summary}
{memory_block}
[INSTRUCTIONS]: {user_instr}
[FORMAT]:
[ID]
Translated Text

[INPUT]:
{batch_txt}"""
                            
                            retry = 3; success = False
                            while retry > 0:
                                try:
                                    if i > 0: time.sleep(delay_ms / 1000.0)
                                    response_stream = client.models.generate_content_stream(
                                        model=model_name, contents=prompt,
                                        config=types.GenerateContentConfig(temperature=temp_val, max_output_tokens=max_tok_val)
                                    )
                                    full_resp = ""
                                    for chunk_resp in response_stream:
                                        if chunk_resp.text: full_resp += chunk_resp.text; console_box.markdown(f"**Translating Batch {current_batch_num}...**\n\n```text\n{full_resp}\n```")
                                        if chunk_resp.usage_metadata: total_session_tokens += chunk_resp.usage_metadata.total_token_count; token_stats_ph.markdown(f"**Tokens:** `{total_session_tokens}`")

                                    clean_text = full_resp.replace("```", "").replace("**", "")
                                    matches = list(re.finditer(r'\[(\d+)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[\d+\]|$)', clean_text, re.DOTALL))
                                    
                                    found_any = False
                                    if matches:
                                        for m in matches: 
                                            mid = m.group(1).strip()
                                            trans_map[mid] = m.group(2).strip()
                                            completed_set.add(mid)
                                            found_any = True
                                        
                                        if found_any:
                                            # 🔥 AUTO-SAVE POINT
                                            job['trans_map'] = trans_map
                                            job['done_ids'] = list(completed_set)
                                            st.session_state.job_progress[fname] = job
                                            
                                            success = True
                                            break
                                    
                                    if not success: console_box.warning("⚠️ Formatting Error. Retrying..."); retry -= 1; time.sleep(1)
                                except Exception as e:
                                    if "429" in str(e).lower() and enable_cooldown:
                                        if cooldown_hits < MAX_COOLDOWN_HITS:
                                            console_box.error(f"🛑 429 Limit! Waiting 60s..."); time.sleep(60); cooldown_hits+=1; continue
                                        else: break
                                    else: console_box.error(f"Error: {e}"); retry -= 1; time.sleep(2)

                            if success:
                                progress_text_ph.text(f"✅ Completed: {len(completed_set)} / {total_lines}")
                                progress_bar.progress(len(completed_set) / total_lines)
                            else: 
                                st.error("❌ Batch Failed. Progress Saved. Click Resume to try again."); st.stop()

                        # --- PHASE 3: REVISION (Simplified for reliability) ---
                        if enable_revision and trans_map:
                            console_box.info("✨ Revising...")
                            sorted_ids = sorted(trans_map.keys(), key=lambda x: int(x) if x.isdigit() else x)
                            full_draft = "\n\n".join([f"[{vid}]\n{trans_map[vid]}" for vid in sorted_ids])
                            rev_prompt = f"ROLE: Editor.\nTASK: Polish grammar/flow.\nCONTEXT: {file_context_summary}\nNOTE: {revision_instr}\nINPUT FORMAT: [ID] Text\nOUTPUT FORMAT: [ID] Fixed Text\n\n{full_draft}"
                            
                            try:
                                rev_stream = client.models.generate_content_stream(model=model_name, contents=rev_prompt, config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=max_tok_val))
                                full_rev = ""
                                for c in rev_stream: 
                                    if c.text: full_rev += c.text; console_box.markdown(f"**Revising...**\n\n```text\n{full_rev}\n```")
                                
                                rev_matches = list(re.finditer(r'\[(\d+)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[\d+\]|$)', full_rev, re.DOTALL))
                                if rev_matches:
                                    for m in rev_matches: 
                                        if m.group(1) in trans_map: trans_map[m.group(1)] = m.group(2).strip()
                                    console_box.success("✅ Revision Applied!")
                            except Exception as e: console_box.warning(f"Revision skipped: {e}")

                        # --- OUTPUT ---
                        if trans_map:
                            job['status'] = 'completed' # Mark done
                            st.session_state.job_progress[fname] = job
                            
                            out = proc.get_output(trans_map)
                            st.success(f"✅ {fname} Done!")
                            st.download_button(f"⬇️ DOWNLOAD", out, f"trans_{fname}", key=f"d{file_idx}")

                    st.balloons()
                    st.success("🎉 Process Complete!")
        
            except Exception as e: st.error(f"❌ Fatal Error: {e}")
