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
    uploaded_file = st.file_uploader("Upload Subtitle File (.srt, .vtt, .ass)", type=['srt', 'vtt', 'ass'])
    st.markdown("---")
    progress_bar = st.progress(0)
    status_text = st.empty()

# --- 🖥️ MAIN INTERFACE (Settings) ---
st.title("✨ Gemini Subtitle Translator")

api_key = st.text_input("GOOGLE_API_KEY", type="password")

col1, col2 = st.columns(2)
with col1:
    # Saare models list mein mojood hain
    model_list = [
        "gemini-3-pro-preview", "gemini-3-flash-preview", 
        "gemini-2.5-pro", "gemini-2.5-flash",
        "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"
    ]
    model_name = st.selectbox("MODEL_NAME", model_list)
    source_lang = st.text_input("SOURCE_LANGUAGE", "English")

with col2:
    target_lang = st.text_input("TARGET_LANGUAGE", "Roman Hindi")
    batch_sz = st.number_input("BATCH_SIZE", value=50, step=1)

user_instr = st.text_area("USER_INSTRUCTION", "Translate into natural Roman Hindi. Keep Anime terms in English.")

start_button = st.button("🚀 START TRANSLATION NOW", use_container_width=True)

# --- SUBTITLE PROCESSOR (SRT, VTT, ASS) ---
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
        for l in self.raw.strip().split('\n'):
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

# --- EXECUTION LOGIC ---
if start_button:
    if not api_key or not uploaded_file:
        st.error("❌ Please provide API Key and Upload a file!")
    else:
        try:
            client = genai.Client(api_key=api_key)
            proc = SubtitleProcessor(uploaded_file.name, uploaded_file.getvalue())
            total_lines = proc.parse()
            
            st.markdown("### 📺 Terminal Stream (Auto-Scroll)")
            st_stream_box = st.empty() 
            
            trans_map = {}
            total_batches = math.ceil(total_lines / batch_sz)
            
            for i in range(0, total_lines, batch_sz):
                current_batch_num = (i // batch_sz) + 1
                chunk = proc.lines[i : i + batch_sz]
                batch_txt = "".join([f"[{x['id']}]\n{x['txt']}\n\n" for x in chunk])
                
                # System Prompt with Strict Formatting
                prompt = f"""You are a pro translator. 
TASK: {source_lang} -> {target_lang}
NOTE: {user_instr}
FORMAT: [ID] then Translated Text. Stream the response.

Batch to process:
{batch_txt}"""
                
                retry = 3
                success = False
                while retry > 0:
                    try:
                        status_text.text(f"⏳ Processing Batch {current_batch_num}/{total_batches}")
                        final_text = "" # 5️⃣ Final Result Buffer

                        # 2️⃣ Stream Loop (Chunk-by-chunk)
                        # google-genai handles the reader and decoder internally
                        for response_chunk in client.models.generate_content_stream(model=model_name, contents=prompt):
                            # 4️⃣ JSON extract + text collect (Simplified for Python SDK)
                            text = response_chunk.text
                            if text:
                                final_text += text
                                # Smooth Auto-scroll UI
                                html_stream = f"""
                                <div id="log-box" style="height:400px; overflow-y:auto; background-color:#101418; color:#00e676; padding:15px; font-family:'Fira Code', monospace; border-radius:8px; border:1px solid #333; white-space:pre-wrap; font-size:13px; line-height:1.6;">
                                    {final_text}<div id="end"></div>
                                </div>
                                <script>
                                    var box = document.getElementById("log-box");
                                    box.scrollTop = box.scrollHeight;
                                </script>
                                """
                                st_stream_box.html(html_stream)

                        # 3️⃣ Line-based parsing after full stream
                        matches = list(re.finditer(r'\[(\d+)\]\s*\n(.*?)(?=\n\[\d+\]|$)', final_text, re.DOTALL))
                        if matches:
                            for m in matches: trans_map[m.group(1)] = m.group(2).strip()
                            success = True; break
                        else: 
                            raise Exception("Incomplete JSON / Format Error")

                    except Exception as e:
                        # ⚠️ Try/Catch for safety
                        st.error(f"⚠️ Batch {current_batch_num} Failed: {e}")
                        retry -= 1
                        time.sleep(2)
                
                progress_bar.progress(min((i + batch_sz) / total_lines, 1.0))
                time.sleep(0.5)

            if trans_map:
                st.success("🎉 Translation Complete!")
                out_content = proc.get_output(trans_map)
                st.download_button("⬇️ DOWNLOAD FILE", data=out_content, file_name=f"translated_{uploaded_file.name}", use_container_width=True)
        
        except Exception as e:
            st.error(f"❌ Critical Error: {e}")
