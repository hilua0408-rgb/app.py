import streamlit as st
import re
import os
import time
import json
import zipfile
import io
from google import genai
from google.genai import types

# Page Setup
st.set_page_config(page_title="Gemini Subtitle Pro V4.0 (Final)", layout="wide", page_icon="🎬")

# --- 🎨 CUSTOM CSS ---
st.markdown("""
<style>
    .stButton>button { border-radius: 8px; font-weight: bold; }
    
    /* 🔥 COMPACT FILE UPLOADER */
    [data-testid='stFileUploader'] { padding-top: 0px; margin-top: -20px; }
    [data-testid='stFileUploader'] section { padding: 0px; min-height: 0px; border: none; background-color: transparent; }
    [data-testid='stFileUploader'] .st-emotion-cache-1ae8axi, 
    [data-testid='stFileUploader'] .st-emotion-cache-1erivf3 { display: none; }
    [data-testid='stFileUploader'] button { width: 100%; margin-top: 0px; }

    /* 🔥 ALIGNMENT */
    div[data-testid="column"] { align-items: center; display: flex; }
    
    /* 🔥 EDITOR TEXT AREAS */
    .stTextArea textarea { font-family: monospace; font-size: 14px; }
    
    /* 🔥 PROGRESS BAR COLOR */
    .stProgress > div > div > div > div { background-color: #ff4b4b; }
</style>
""", unsafe_allow_html=True)

# --- 📦 SESSION STATE ---
if 'api_keys' not in st.session_state: st.session_state.api_keys = []
if 'active_key' not in st.session_state: st.session_state.active_key = None
if 'api_status' not in st.session_state: st.session_state.api_status = "Unknown"
if 'skipped_files' not in st.session_state: st.session_state.skipped_files = []
if 'file_edits' not in st.session_state: st.session_state.file_edits = {}
if 'job_progress' not in st.session_state: st.session_state.job_progress = {}

# 🔥 Glossary State
if 'glossary' not in st.session_state: st.session_state.glossary = [] 
if 'edit_index' not in st.session_state: st.session_state.edit_index = None 

# --- 📱 SIDEBAR ---
with st.sidebar:
    st.header("📁 File Upload")
    uploaded_files = st.file_uploader("Upload Subtitle Files", type=['srt', 'vtt', 'ass'], accept_multiple_files=True)
    st.markdown("---")
    
    if uploaded_files:
        current_filenames = [f.name for f in uploaded_files]
        progress_keys = list(st.session_state.job_progress.keys())
        for key in progress_keys:
            if key not in current_filenames: del st.session_state.job_progress[key]
    else: st.session_state.job_progress = {}

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

# --- 1. API CONFIGURATION ---
with st.expander("🛠️ API Configuration & Keys", expanded=False):
    st.markdown("###### ➕ Add New API Key")
    c1, c2 = st.columns([0.85, 0.15])
    with c1: new_key_input = st.text_input("Key Input", placeholder="Paste 'AIza...' key here", label_visibility="collapsed")
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
                        if st.button(f"⚪ {masked}", key=f"sel_{idx}", use_container_width=True): st.session_state.active_key = key; st.rerun()
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
                    with genai.Client(api_key=st.session_state.active_key) as client: list(client.models.list(config={'page_size': 1}))
                    st.session_state.api_status = "Alive 🟢"
                except: st.session_state.api_status = "Dead 🔴"
                st.rerun()
        with st.expander("🎛️ Advanced Tech Parameters", expanded=False):
            c_a1, c_a2, c_a3 = st.columns(3)
            with c_a1: enable_cooldown = st.checkbox("Smart Cooldown", value=True)
            with c_a2: temp_val = st.slider("Temperature", 0.0, 2.0, 0.3)
            with c_a3: max_tok_val = st.number_input("Max Output Tokens", 100, 65536, 65536)
            delay_ms = 500
    else: enable_cooldown=True; temp_val=0.3; max_tok_val=65536; delay_ms=500

# --- 2. 📚 GLOSSARY ---
with st.expander("📚 Words Menu (Glossary)", expanded=False):
    st.info("💡 Add specific words here. The AI will be instructed to STRICTLY use these translations.")
    gc1, gc2 = st.columns(2)
    default_src = ""; default_tgt = ""; btn_label = "Save Word"
    if st.session_state.edit_index is not None:
        idx = st.session_state.edit_index
        if 0 <= idx < len(st.session_state.glossary):
            default_src = st.session_state.glossary[idx]['src']; default_tgt = st.session_state.glossary[idx]['tgt']; btn_label = "Update Word"
    with gc1: src_in = st.text_input("Source Word", value=default_src, placeholder="e.g. Hello")
    with gc2: tgt_in = st.text_input("Target Word", value=default_tgt, placeholder="e.g. Aslam o alaikum")
    if st.button(btn_label, type="primary"):
        if src_in and tgt_in:
            if st.session_state.edit_index is not None: st.session_state.glossary[st.session_state.edit_index] = {'src': src_in, 'tgt': tgt_in}; st.session_state.edit_index = None; st.success("Word Updated!")
            else: st.session_state.glossary.append({'src': src_in, 'tgt': tgt_in}); st.success("Word Added!")
            st.rerun()
        else: st.warning("⚠️ Both fields are required.")
    if st.session_state.edit_index is not None:
        if st.button("Cancel Edit"): st.session_state.edit_index = None; st.rerun()

    st.markdown("---"); st.markdown("###### List of Words")
    with st.container(height=250, border=True):
        if not st.session_state.glossary: st.caption("No words added yet.")
        else:
            for i, item in enumerate(st.session_state.glossary):
                try: cg1, cg2, cg3 = st.columns([0.55, 0.22, 0.23], vertical_alignment="center")
                except: cg1, cg2, cg3 = st.columns([0.55, 0.22, 0.23])
                with cg1: st.markdown(f"**{item['src']}** → {item['tgt']}")
                with cg2: 
                    if st.button("Edit", key=f"edit_g_{i}", use_container_width=True): st.session_state.edit_index = i; st.rerun()
                with cg3: 
                    if st.button("Delete", key=f"del_g_{i}", use_container_width=True): st.session_state.glossary.pop(i); st.session_state.edit_index = None; st.rerun()
                st.divider()
    st.markdown("###### 📤 Import / Export")
    gj1, gj2 = st.columns(2, vertical_alignment="bottom")
    with gj1: st.download_button("Export (JSON)", json.dumps(st.session_state.glossary, indent=2), "glossary.json", "application/json", use_container_width=True)
    with gj2:
        uploaded_json = st.file_uploader("Import (JSON)", type=['json'], label_visibility="collapsed")
        if uploaded_json:
            try: st.session_state.glossary = json.load(uploaded_json); st.success("Imported!"); time.sleep(1); st.rerun()
            except: st.error("Invalid JSON")

# --- 3. 📝 SMART FILE EDITOR (DUAL MODE) ---
with st.expander("📝 File Editor (Original & Translated)", expanded=True):
    if not uploaded_files:
        st.info("⚠️ Please upload files in the sidebar first.")
    else:
        file_names = [f.name for f in uploaded_files]
        selected_file_name = st.selectbox("Select File to View/Edit", file_names)
        current_file_obj = next((f for f in uploaded_files if f.name == selected_file_name), None)
        
        if current_file_obj:
            temp_proc = SubtitleProcessor(selected_file_name, current_file_obj.getvalue()); temp_proc.parse()
            is_translated = False; translated_content = ""
            if selected_file_name in st.session_state.job_progress:
                job = st.session_state.job_progress[selected_file_name]
                if 'trans_map' in job and job['trans_map']:
                    is_translated = True
                    sorted_ids = sorted(job['trans_map'].keys(), key=lambda x: int(x) if x.isdigit() else x)
                    translated_content = "\n\n".join([f"[{vid}]\n{job['trans_map'][vid]}" for vid in sorted_ids])

            if is_translated:
                st.success("✅ Translation available. You can edit the result on the right.")
                col_orig, col_trans = st.columns(2)
                with col_orig:
                    st.markdown("**Original Text (Reference)**")
                    orig_text = "\n\n".join([f"[{line['id']}]\n{line['txt']}" for line in temp_proc.lines])
                    st.text_area("Original", value=orig_text, height=600, disabled=True, key=f"orig_view_{selected_file_name}")
                with col_trans:
                    st.markdown("**Translated Text (Editable)**")
                    new_trans_text = st.text_area("Edit Translation Here", value=translated_content, height=600, key=f"trans_edit_{selected_file_name}")
                    if new_trans_text != translated_content:
                        new_map = {}
                        matches = list(re.finditer(r'\[(\d+)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[\d+\]|$)', new_trans_text, re.DOTALL))
                        for m in matches: new_map[m.group(1).strip()] = m.group(2).strip()
                        st.session_state.job_progress[selected_file_name]['trans_map'].update(new_map)
                        st.toast("💾 Changes Saved to Memory!", icon="✅"); time.sleep(1); st.rerun()
            else:
                st.info("ℹ️ No translation yet. You can edit the Source Text below before starting.")
                if selected_file_name in st.session_state.file_edits: display_content = st.session_state.file_edits[selected_file_name]
                else: display_content = "\n\n".join([f"[{line['id']}]\n{line['txt']}" for line in temp_proc.lines])
                c_search1, c_search2 = st.columns([0.8, 0.2])
                search_query = c_search1.text_input("Find text...", label_visibility="collapsed", placeholder="Find text...")
                is_non_roman = c_search2.checkbox("Non-Roman")
                if search_query or is_non_roman:
                    found_lines = []
                    matches = list(re.finditer(r'\[(\d+)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[\d+\]|$)', display_content, re.DOTALL))
                    for m in matches:
                        lid = m.group(1); txt = m.group(2).strip(); match_found = False
                        if search_query and search_query.lower() in txt.lower(): match_found = True
                        if is_non_roman:
                            clean_txt = re.sub(r'[^\w\s]', '', txt)
                            if re.search(r'[^\x00-\x7F]', clean_txt): match_found = True
                        if match_found: found_lines.append(lid)
                    st.caption(f"🔍 Found in IDs: {', '.join(found_lines[:20])}..." if found_lines else "🔍 No matches.")
                edited_content = st.text_area(f"Edit Source ({selected_file_name})", value=display_content, height=400, key=f"editor_{selected_file_name}")
                if edited_content != display_content: st.session_state.file_edits[selected_file_name] = edited_content; st.success("✅ Source Updated! AI will use this text.")

# --- 4. TRANSLATION SETTINGS ---
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

# --- FEATURES & EXECUTION ---
st.markdown("### ⚡ Workflow Steps")
enable_memory = st.checkbox("🧠 1. Context Memory", value=True)
st.divider()
enable_analysis = st.checkbox("🧐 2. Deep File Analysis", value=False)
analysis_instr = st.text_area("Analysis Note", placeholder="Context...", height=68) if enable_analysis else ""
st.divider()
enable_revision = st.checkbox("✨ 3. Revision / Polish", value=False)
revision_instr = st.text_area("Revision Note", placeholder="Instructions...", height=68) if enable_revision else ""
st.markdown("---")
user_instr = st.text_area("USER_INSTRUCTION", "Translate into natural Roman Hindi. Keep Anime terms in English.")

work_status = "new" 
for f in uploaded_files:
    if f.name in st.session_state.job_progress and st.session_state.job_progress[f.name]['status'] == 'paused':
        work_status = "paused"; break
btn_label = "▶️ CONTINUE / RESUME" if work_status == "paused" else "🚀 START TRANSLATION"
btn_type = "primary" if work_status == "paused" else "secondary"
start_button = st.button(btn_label, type=btn_type, use_container_width=True)

if start_button:
    if not st.session_state.active_key or not uploaded_files: st.error("❌ Add API Key & Upload Files!")
    else:
        with st.spinner("🔄 Processing..."):
            try:
                with genai.Client(api_key=st.session_state.active_key) as client:
                    st.markdown("## Translation Status")
                    st.markdown("---")
                    file_status_ph = st.empty(); progress_text_ph = st.empty(); progress_bar = st.progress(0); token_stats_ph = st.empty()
                    st.markdown("### Live Console:"); 
                    with st.container(height=300, border=True): console_box = st.empty()
                    total_session_tokens = 0
                    glossary_text = ""
                    if st.session_state.glossary:
                        g_list = [f"- {item['src']} = {item['tgt']}" for item in st.session_state.glossary]
                        glossary_text = "\n[STRICT GLOSSARY - MUST USE THESE TRANSLATIONS]:\n" + "\n".join(g_list) + "\n"

                    for file_idx, uploaded_file in enumerate(uploaded_files):
                        if uploaded_file.name in st.session_state.skipped_files: continue
                        fname = uploaded_file.name
                        if fname not in st.session_state.job_progress: st.session_state.job_progress[fname] = {'status': 'paused', 'done_ids': [], 'trans_map': {}, 'analysis': None}
                        job = st.session_state.job_progress[fname]
                        proc = SubtitleProcessor(fname, uploaded_file.getvalue()); proc.parse()
                        
                        if fname in st.session_state.file_edits:
                            clean_edit_str = st.session_state.file_edits[fname]
                            user_edit_map = {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r'\[(.*?)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[.*?\]|$)', clean_edit_str, re.DOTALL)}
                            for line in proc.lines:
                                if line['id'] in user_edit_map: line['txt'] = user_edit_map[line['id']]
                        
                        total_lines = len(proc.lines); file_status_ph.markdown(f"### 📂 File {file_idx+1}/{len(uploaded_files)}: **{fname}**")
                        
                        # Analysis
                        file_context_summary = "No analysis requested."
                        if enable_analysis:
                            if job['analysis']: file_context_summary = job['analysis']; console_box.info("🧠 Using Saved Analysis.")
                            else:
                                try:
                                    console_box.info("🧠 Analyzing content...")
                                    full_script = "\n".join([f"{x['id']}: {x['txt']}" for x in proc.lines])
                                    ana_stream = client.models.generate_content_stream(model=model_name, contents=f"ANALYZE ({total_lines} lines). Genre, Tone, Characters.\n{glossary_text}\nInput:\n{full_script[:30000]}", config=types.GenerateContentConfig(temperature=0.3))
                                    full_analysis_text = ""
                                    for chunk in ana_stream:
                                        if chunk.text: full_analysis_text += chunk.text; console_box.markdown(f"**Analyzing...**\n\n{full_analysis_text}")
                                    file_context_summary = full_analysis_text; job['analysis'] = full_analysis_text; st.session_state.job_progress[fname] = job
                                    console_box.success("✅ Analysis Complete!"); time.sleep(1)
                                except Exception as e: console_box.error(f"⚠️ Analysis Failed: {e}"); file_context_summary = "Failed."

                        # Translation
                        trans_map = job['trans_map']; completed_set = set(job['done_ids'])
                        progress_text_ph.text(f"✅ Completed: {len(completed_set)} / {total_lines}"); progress_bar.progress(len(completed_set) / total_lines)
                        cooldown_hits = 0; 
                        
                        for i in range(0, total_lines, batch_sz):
                            chunk = proc.lines[i : i + batch_sz]
                            if all(x['id'] in completed_set for x in chunk): continue
                            current_batch_num = (i // batch_sz) + 1
                            batch_txt = "".join([f"[{x['id']}]\n{x['txt']}\n\n" for x in chunk])
                            memory_block = ""
                            if enable_memory and trans_map:
                                sorted_keys = sorted(trans_map.keys(), key=lambda x: int(x) if x.isdigit() else x)
                                if sorted_keys: memory_block = "\n[PREVIOUS CONTEXT]:\n" + "\n".join([f"[{k}] {trans_map[k]}" for k in sorted_keys[-3:]]) + "\n"

                            prompt = f"""You are a professional translator.\nTASK: Translate {source_lang} to {target_lang}.\n[CONTEXT]: {file_context_summary}\n{glossary_text}\n{memory_block}\n[INSTRUCTIONS]: {user_instr}\n[FORMAT]:\n[ID]\nTranslated Text\n\n[INPUT]:\n{batch_txt}"""
                            retry = 3; success = False
                            
                            while retry > 0:
                                try:
                                    if i > 0: time.sleep(delay_ms / 1000.0)
                                    response_stream = client.models.generate_content_stream(model=model_name, contents=prompt, config=types.GenerateContentConfig(temperature=temp_val, max_output_tokens=max_tok_val))
                                    full_resp = ""
                                    batch_tokens = 0
                                    for chunk_resp in response_stream:
                                        if chunk_resp.text: full_resp += chunk_resp.text; console_box.markdown(f"**Translating Batch {current_batch_num}...**\n\n```text\n{full_resp}\n```")
                                        # 🔥 ACCURATE TOKEN COUNTING
                                        if chunk_resp.usage_metadata:
                                            batch_tokens = chunk_resp.usage_metadata.total_token_count
                                    
                                    # Add batch usage to global
                                    total_session_tokens += batch_tokens
                                    token_stats_ph.markdown(f"**Tokens (Batch):** `{batch_tokens}` | **Total:** `{total_session_tokens}`")

                                    clean_text = full_resp.replace("```", "").replace("**", "")
                                    matches = list(re.finditer(r'\[(\d+)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[\d+\]|$)', clean_text, re.DOTALL))
                                    if matches:
                                        found_any = False
                                        for m in matches: mid = m.group(1).strip(); trans_map[mid] = m.group(2).strip(); completed_set.add(mid); found_any = True
                                        if found_any: job['trans_map'] = trans_map; job['done_ids'] = list(completed_set); st.session_state.job_progress[fname] = job; success = True; break
                                    if not success: console_box.warning("⚠️ Formatting Error. Retrying..."); retry -= 1; time.sleep(1)
                                
                                except Exception as e:
                                    if "429" in str(e).lower() and enable_cooldown:
                                        # 🔥 429 LOGIC WITH VISUAL SLIDER
                                        if cooldown_hits < 1: # Only 1 retry allowed
                                            console_box.empty()
                                            err_box = console_box.container()
                                            prog_bar = err_box.progress(1.0)
                                            for t in range(60, 0, -1):
                                                err_box.error(f"🛑 Rate Limit Hit (429). Cooling down... {t}s")
                                                prog_bar.progress(t / 60.0)
                                                time.sleep(1)
                                            err_box.empty()
                                            cooldown_hits += 1
                                            continue # Retry loop
                                        else:
                                            st.error("❌ CHECK API: Quota Exceeded or Limit Reached (429)."); st.stop()
                                    else: console_box.error(f"Error: {e}"); retry -= 1; time.sleep(2)
                            
                            if success: progress_text_ph.text(f"✅ Completed: {len(completed_set)} / {total_lines}"); progress_bar.progress(len(completed_set) / total_lines)
                            else: st.error("❌ Batch Failed. Progress Saved. Click Resume."); st.stop()

                        # Revision
                        if enable_revision and trans_map:
                            console_box.info("✨ Revising...")
                            sorted_ids = sorted(trans_map.keys(), key=lambda x: int(x) if x.isdigit() else x)
                            full_draft = "\n\n".join([f"[{vid}]\n{trans_map[vid]}" for vid in sorted_ids])
                            glossary_note = ""
                            if glossary_text: glossary_note = "\n[CRITICAL: DO NOT CHANGE THESE TERMS]:\n" + "\n".join([f"- {item['tgt']}" for item in st.session_state.glossary])
                            rev_prompt = f"ROLE: Editor.\nTASK: Polish grammar/flow.\nCONTEXT: {file_context_summary}\n{glossary_note}\nNOTE: {revision_instr}\nINPUT FORMAT: [ID] Text\nOUTPUT FORMAT: [ID] Fixed Text\n\n{full_draft}"
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

                        # Finalize File
                        if trans_map:
                            job['status'] = 'completed'; st.session_state.job_progress[fname] = job
                            out = proc.get_output(trans_map)
                            st.success(f"✅ {fname} Done!"); st.download_button(f"⬇️ DOWNLOAD", out, f"trans_{fname}", key=f"d{file_idx}")

                    # ZIP & FINISH
                    if len(uploaded_files) > 1:
                        st.divider(); st.subheader("📦 Bulk Download")
                        completed_files = []
                        for f in uploaded_files:
                            if f.name in st.session_state.job_progress and st.session_state.job_progress[f.name]['status'] == 'completed': completed_files.append(f)
                        if len(completed_files) > 1:
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, "w") as zf:
                                for f_obj in completed_files:
                                    fname = f_obj.name
                                    temp_proc = SubtitleProcessor(fname, f_obj.getvalue()); temp_proc.parse()
                                    final_map = st.session_state.job_progress[fname]['trans_map']
                                    zf.writestr(f"trans_{fname}", temp_proc.get_output(final_map))
                            st.download_button(label="⬇️ Download All (ZIP)", data=zip_buffer.getvalue(), file_name="translated_subtitles.zip", mime="application/zip", type="primary", use_container_width=True)

                    st.balloons(); st.success("🎉 Process Complete!")
            except Exception as e: st.error(f"❌ Fatal Error: {e}")
