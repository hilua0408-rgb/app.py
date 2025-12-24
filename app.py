import streamlit as st
import re
import os
import time
from google import genai
from google.genai import types

# Page Setup
st.set_page_config(page_title="Gemini Subtitle Pro V2.6", layout="wide", page_icon="🎬")

# --- 🎨 CUSTOM CSS ---
st.markdown("""
<style>
    .stButton>button { border-radius: 8px; font-weight: bold; }
    .status-wait { color: #e67e22; font-weight: bold; }
    .status-stream { color: #27ae60; font-weight: bold; animation: blink 1s infinite; }
    @keyframes blink { 50% { opacity: 0.5; } }
</style>
""", unsafe_allow_html=True)

# --- 📦 SESSION STATE ---
if 'api_keys' not in st.session_state: st.session_state.api_keys = []
if 'active_key' not in st.session_state: st.session_state.active_key = None
if 'skipped_files' not in st.session_state: st.session_state.skipped_files = []
if 'file_edits' not in st.session_state: st.session_state.file_edits = {}
if 'job_progress' not in st.session_state: st.session_state.job_progress = {}

# --- 📱 SIDEBAR ---
with st.sidebar:
    st.header("📁 File Upload")
    uploaded_files = st.file_uploader("Upload Subtitles", type=['srt', 'vtt', 'ass'], accept_multiple_files=True)
    st.markdown("---")
    
    # Cleanup removed files
    if uploaded_files:
        current_names = [f.name for f in uploaded_files]
        for k in list(st.session_state.job_progress.keys()):
            if k not in current_names: del st.session_state.job_progress[k]
    else: st.session_state.job_progress = {}

    if st.session_state.skipped_files:
        if st.button(f"Clear Skipped ({len(st.session_state.skipped_files)})"):
            st.session_state.skipped_files = []; st.rerun()

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

# --- MAIN INTERFACE ---
st.markdown("### ✨ Gemini Subtitle Pro V2.6")

# --- 1. SETTINGS ---
with st.expander("🛠️ API & Settings", expanded=False):
    c1, c2 = st.columns([0.85, 0.15])
    with c1: new_key = st.text_input("Key", placeholder="Paste AIza key...", label_visibility="collapsed")
    with c2: 
        if st.button("Add"):
            cl = new_key.strip()
            if cl.startswith("AIza") and cl not in st.session_state.api_keys:
                st.session_state.api_keys.append(cl); st.session_state.active_key = cl; st.rerun()

    if st.session_state.active_key:
        st.caption(f"Active: ...{st.session_state.active_key[-6:]}")
        if st.button("🗑️ Remove"): st.session_state.api_keys.remove(st.session_state.active_key); st.session_state.active_key = None; st.rerun()
        
        st.markdown("---")
        # Hidden Tech Params
        with st.expander("🎛️ Tech Parameters", expanded=False):
            c_t1, c_t2 = st.columns(2)
            with c_t1: temp_val = st.slider("Temperature", 0.0, 2.0, 0.3)
            with c_t2: max_tok = st.number_input("Max Tokens", 100, 65536, 65536)
            enable_cool = st.checkbox("Smart Cooldown (429 Fix)", True)
            delay_ms = 500
    else: temp_val=0.3; max_tok=65536; enable_cool=True; delay_ms=500

# --- 2. EDITOR ---
with st.expander("📝 File Editor", expanded=False):
    if uploaded_files:
        fn = [f.name for f in uploaded_files]; sel = st.selectbox("Select", fn)
        cur = next((f for f in uploaded_files if f.name == sel), None)
        if cur:
            if sel in st.session_state.file_edits: dt = st.session_state.file_edits[sel]
            else:
                p = SubtitleProcessor(sel, cur.getvalue()); p.parse()
                dt = "\n\n".join([f"[{l['id']}]\n{l['txt']}" for l in p.lines])
            
            # Search
            cs1, cs2 = st.columns([0.8, 0.2])
            sq = cs1.text_input("Find", label_visibility="collapsed", placeholder="Search...")
            nr = cs2.checkbox("Non-Roman")
            if sq or nr:
                mts = re.finditer(r'\[(\d+)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[\d+\]|$)', dt, re.DOTALL)
                fnds = []
                for m in mts:
                    t = m.group(2).strip()
                    # Logic: Remove symbols, check if non-ascii remains
                    clean_t = re.sub(r'[^\w\s]', '', t)
                    if (sq and sq.lower() in t.lower()) or (nr and re.search(r'[^\x00-\x7F]', clean_t)):
                        fnds.append(m.group(1))
                st.caption(f"Found in: {', '.join(fnds[:10])}..." if fnds else "No match")
            
            new_dt = st.text_area("Edit", dt, height=250)
            if new_dt != dt: st.session_state.file_edits[sel] = new_dt; st.success("Saved!")

# --- 3. TRANSLATION SETUP ---
with st.expander("⚙️ Translation Config", expanded=False):
    c1, c2 = st.columns(2)
    with c1: 
        mod = st.selectbox("Model", st.session_state.get('model_list', ["gemini-2.0-flash", "gemini-1.5-flash"]))
        if st.button("Refresh Models") and st.session_state.active_key:
            try: 
                with genai.Client(api_key=st.session_state.active_key) as c:
                    st.session_state['model_list'] = sorted([m.name.replace("models/","") for m in c.models.list() if 'gemini' in m.name.lower()], reverse=True)
                    st.rerun()
            except: pass
        sl = st.text_input("Source", "English")
    with c2: tl = st.text_input("Target", "Roman Hindi"); bs = st.number_input("Batch Size", 1, 500, 20)

# --- FEATURES ---
st.markdown("### ⚡ Workflow")
mem = st.checkbox("🧠 1. Context Memory", True)
st.divider()
ana = st.checkbox("🧐 2. Analysis", False); ana_inst = st.text_area("Note", height=68) if ana else ""
st.divider()
rev = st.checkbox("✨ 3. Revision", False); rev_inst = st.text_area("Note", height=68) if rev else ""
st.markdown("---")
u_inst = st.text_area("Instructions", "Translate into natural Roman Hindi.")

# --- START/RESUME BUTTON ---
has_paused = any(st.session_state.job_progress.get(f.name, {}).get('status') == 'paused' for f in uploaded_files)
c_b1, c_b2 = st.columns([0.8, 0.2])
with c_b1:
    btn_txt = "▶️ RESUME" if has_paused else "🚀 START"
    btn_col = "primary" if has_paused else "secondary"
    start = st.button(btn_txt, type=btn_col, use_container_width=True)
with c_b2:
    if st.button("🗑️ Reset"): st.session_state.job_progress = {}; st.rerun()

# --- EXECUTION ---
if start:
    if not st.session_state.active_key or not uploaded_files: st.error("No Key/Files!"); st.stop()

    with st.spinner("🔄 Initializing..."):
        try:
            with genai.Client(api_key=st.session_state.active_key) as client:
                st.markdown("## 📊 Live Progress")
                
                # --- UPDATED STATS LAYOUT (Removed Speed, Added Status) ---
                st_c1, st_c2 = st.columns(2)
                status_ph = st_c1.empty() # For "Waiting/Streaming"
                token_ph = st_c2.empty()
                
                prog_bar = st.progress(0)
                cons = st.container(height=300, border=True).empty()
                total_tok = 0

                for idx, file in enumerate(uploaded_files):
                    fname = file.name
                    if fname in st.session_state.skipped_files: continue

                    # Init Progress
                    if fname not in st.session_state.job_progress:
                        st.session_state.job_progress[fname] = {'done_ids': [], 'trans_map': {}, 'analysis': "None", 'status': 'paused'}
                    job = st.session_state.job_progress[fname]
                    
                    # Parse (Handle Edits)
                    if fname in st.session_state.file_edits:
                        proc = SubtitleProcessor(fname, file.getvalue()); proc.parse()
                        u_map = {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r'\[(.*?)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[.*?\]|$)', st.session_state.file_edits[fname], re.DOTALL)}
                        for l in proc.lines: 
                            if l['id'] in u_map: l['txt'] = u_map[l['id']]
                    else:
                        proc = SubtitleProcessor(fname, file.getvalue()); proc.parse()

                    tot_lines = len(proc.lines)
                    status_ph.markdown(f"**📂 File:** {fname}")
                    
                    # Analysis
                    if ana and job['analysis'] == "None":
                        cons.info("🧠 Analyzing..."); full = "\n".join([f"{x['id']}: {x['txt']}" for x in proc.lines])
                        try: job['analysis'] = client.models.generate_content(mod, contents=f"Analyze:\n{full[:30000]}").text; st.session_state.job_progress[fname]=job
                        except: pass

                    # Translation Loop
                    t_map = job['trans_map']
                    done = set(job['done_ids'])
                    
                    if len(done) < tot_lines:
                        for i in range(0, tot_lines, bs):
                            chunk = proc.lines[i:i+bs]
                            if all(x['id'] in done for x in chunk): continue
                            
                            b_num = (i//bs)+1
                            b_txt = "".join([f"[{x['id']}]\n{x['txt']}\n\n" for x in chunk])
                            
                            # Memory
                            ctx = ""
                            if mem and t_map:
                                last = sorted(t_map.keys(), key=lambda x:int(x) if x.isdigit() else x)[-3:]
                                ctx = "\n".join([f"[{i}] {t_map[i]}" for i in last])

                            prompt = f"Role: Translator {sl}->{tl}.\nContext: {job['analysis']}\nMem: {ctx}\nNote: {u_inst}\nFmt: [ID]\nTxt\n\nInput:\n{b_txt}"
                            
                            retry = 3
                            while retry > 0:
                                try:
                                    if i > 0: time.sleep(delay_ms/1000)
                                    
                                    # --- STATUS: WAITING ---
                                    # This is where the user wanted "1-2-3", replaced with Spinner/Text
                                    cons.markdown(f"<span class='status-wait'>⏳ Batch {b_num}: Sending Request & Waiting...</span>", unsafe_allow_html=True)
                                    batch_start_time = time.time()
                                    
                                    stream = client.models.generate_content_stream(mod, contents=prompt, config=types.GenerateContentConfig(temperature=temp_val, max_output_tokens=max_tok))
                                    
                                    full_resp = ""
                                    first_chunk = True
                                    
                                    for c in stream:
                                        if first_chunk:
                                            # --- STATUS: STREAMING ---
                                            # Waiting text is replaced immediately
                                            cons.markdown(f"<span class='status-stream'>⚡ Batch {b_num}: Receiving Data...</span>", unsafe_allow_html=True)
                                            first_chunk = False
                                        
                                        if c.text: full_resp += c.text; cons.code(full_resp, language="text")
                                        if c.usage_metadata: total_tok += c.usage_metadata.total_token_count; token_ph.markdown(f"🪙 **Tokens:** {total_tok}")

                                    # Save
                                    clean = full_resp.replace("```", "").replace("**", "")
                                    saved_count = 0
                                    for m in re.finditer(r'\[(\d+)\]\s*(?:^|\n|\s+)(.*?)(?=\n\[\d+\]|$)', clean, re.DOTALL):
                                        t_map[m.group(1).strip()] = m.group(2).strip()
                                        done.add(m.group(1).strip())
                                        saved_count += 1
                                    
                                    if saved_count > 0:
                                        job['trans_map'] = t_map; job['done_ids'] = list(done)
                                        st.session_state.job_progress[fname] = job
                                        prog_bar.progress(len(done)/tot_lines)
                                        
                                        # Show Batch Time
                                        batch_dur = time.time() - batch_start_time
                                        st.toast(f"✅ Saved! ({batch_dur:.1f}s)", icon="💾")
                                        break
                                    else: retry-=1; time.sleep(1)
                                except Exception as e:
                                    if "429" in str(e) and enable_cool: cons.error("🛑 429 Limit. Cooling 60s..."); time.sleep(60)
                                    else: cons.error(f"Error: {e}"); retry-=1; time.sleep(2)

                    job['status'] = 'completed'
                    st.session_state.job_progress[fname] = job
                    
                    final = proc.get_output(t_map)
                    st.success(f"🎉 {fname} Done!")
                    st.download_button(f"⬇️ {fname}", final, f"trans_{fname}")

                st.balloons()

        except Exception as e: st.error(f"Fatal Error: {e}")
