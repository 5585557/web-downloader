#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" 网页资源下载器 v1.3.0 """
__version__ = '1.3.0'
import sys, os, subprocess
# ==================== 环境检查 ====================
def _check_env():
    """启动前检查Python版本和依赖，缺什么装什么"""
    if sys.version_info < (3, 7):
        print("✗ 需要 Python 3.7+，当前版本: " + sys.version.split()[0])
        print(" 请去 https://www.python.org 下载安装")
        input("按回车退出..."); sys.exit(1)
    _REQUIRED = {'requests': 'requests', 'bs4': 'beautifulsoup4'}
    _OPTIONAL = {'pystray': 'pystray', 'PIL': 'Pillow', 'brotli': 'brotli'}
    missing_req, missing_opt = [], []
    for mod, pkg in _REQUIRED.items():
        try: __import__(mod)
        except ImportError: missing_req.append(pkg)
    for mod, pkg in _OPTIONAL.items():
        try: __import__(mod)
        except ImportError: missing_opt.append(pkg)
    if missing_req:
        print(f"📦 缺少必需依赖: {', '.join(missing_req)}")
        print(f" 正在自动安装...")
        for pkg in missing_req:
            print(f" pip install {pkg} ...", end=" ", flush=True)
            r = subprocess.run([sys.executable, '-m', 'pip', 'install', pkg, '-q'], capture_output=True, text=True, timeout=120)
            if r.returncode == 0: print("✓")
            else:
                print("✗"); print(f" 安装失败: {r.stderr.strip()}")
                input("按回车退出..."); sys.exit(1)
        print(" ✓ 必需依赖安装完成\n")
    if missing_opt:
        print(f"💡 缺少可选依赖: {', '.join(missing_opt)}")
        print(f" 不影响基本功能，安装后体验更好:")
        print(f" pip install {' '.join(missing_opt)}\n")
    for mod in _REQUIRED:
        try: __import__(mod)
        except ImportError:
            print(f"✗ {mod} 安装后仍无法导入，请检查Python环境")
            input("按回车退出..."); sys.exit(1)
_check_env()
import os, sys, re, socket, shutil, socketserver, threading, time, json, subprocess
from datetime import datetime
from urllib.parse import urlparse, urljoin, unquote, quote
from http.server import HTTPServer, BaseHTTPRequestHandler
for _pkg, _mod in [('requests', 'requests'), ('beautifulsoup4', 'bs4')]:
    try: __import__(_mod)
    except ImportError: os.system(f"{sys.executable} -m pip install {_pkg}")
import requests
from bs4 import BeautifulSoup, NavigableString
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser
try:
    import pystray; from PIL import Image, ImageDraw; HAS_TRAY = True
except ImportError: HAS_TRAY = False
try:
    import brotli; HAS_BROTLI = True
except ImportError: HAS_BROTLI = False
# ==================== 工具函数 ====================
def normalize_url(base, raw):
    if not raw or raw.startswith(('data:','blob:','javascript:','mailto:','#')): return None
    raw = raw.strip().split('#')[0].strip()
    if not raw: return None
    if raw.startswith('//'): raw = urlparse(base).scheme + ':' + raw
    return urljoin(base, raw)
def is_cross(url, netloc): return bool(urlparse(url).netloc and urlparse(url).netloc != netloc)
def to_proxy(url): return '/__p__/' + quote(url, safe='')
def from_proxy(path): return unquote(path[7:]) if path.startswith('/__p__/') else None
_VERIFY = frozenset({'challenges.cloudflare.com','challenges.tls13.com','recaptcha.net','www.recaptcha.net','www.google.com','recaptcha.google.com','hcaptcha.com','www.hcaptcha.com','assets.hcaptcha.com','geetest.com','static.geetest.com','api.geetest.com','dynamic.geetest.com','www.gstatic.com','cap.4399.com','captchas.4399.com'})
def is_verify(url):
    try: return urlparse(url).netloc.lower() in _VERIFY
    except: return False
def folder_name(url):
    p = urlparse(url); n = p.netloc.replace(':', '_'); pa = p.path.strip('/')
    if pa and pa not in ('','index.html','index.htm'): n += '_' + re.sub(r'[\\/:*?"<>|]', '_', pa)[:60]
    return n
def html_rel(url):
    p = urlparse(url).path
    if not p or p == '/': return 'index.html'
    if p.endswith('/'): return p.rstrip('/') + '/index.html'
    if not os.path.splitext(p)[1]: return p + '.html'
    return p.lstrip('/')
def fmt_size(s):
    if s < 1024: return f"{s} B"
    if s < 1048576: return f"{s / 1024:.1f} KB"
    if s < 1073741824: return f"{s / 1048576:.1f} MB"
    return f"{s / 1073741824:.2f} GB"
def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s: s.bind(('', 0)); return s.getsockname()[1]
def safe_filename(name):
    if not name: return 'unnamed'
    name = name.split('?')[0]; name = re.sub(r'[\\/:*?"<>|]', '_', name); name = name.strip('. ')
    return name if name else 'unnamed'
def guess_ct(url, rct):
    if rct and rct not in ('application/octet-stream','binary/octet-stream',''): return rct
    e = os.path.splitext(urlparse(url).path)[1].lstrip('.').lower()
    m = {'jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png','gif':'image/gif','svg':'image/svg+xml','webp':'image/webp','ico':'image/x-icon','css':'text/css','js':'application/javascript','woff':'font/woff','woff2':'font/woff2','ttf':'font/ttf','otf':'font/otf','mp4':'video/mp4','webm':'video/webm','mp3':'audio/mpeg','swf':'application/x-shockwave-flash','json':'application/json','xml':'application/xml','html':'text/html','wasm':'application/wasm'}
    return m.get(e, rct or 'application/octet-stream')
def ext_from_ct(ct):
    if not ct: return ''
    m = {'image/jpeg':'.jpg','image/png':'.png','image/gif':'.gif','image/svg+xml':'.svg','image/webp':'.webp','image/x-icon':'.ico','text/css':'.css','application/javascript':'.js','font/woff':'.woff','font/woff2':'.woff2','font/ttf':'.ttf','font/otf':'.otf','application/x-shockwave-flash':'.swf','video/mp4':'.mp4','video/webm':'.webm','audio/mpeg':'.mp3','application/json':'.json','application/xml':'.xml','text/html':'.html','application/octet-stream':'.bin'}
    for k, v in m.items():
        if k in ct: return v
    return ''
CT_MAP = {'html':'text/html; charset=utf-8','htm':'text/html; charset=utf-8','css':'text/css; charset=utf-8','js':'application/javascript; charset=utf-8','png':'image/png','jpg':'image/jpeg','gif':'image/gif','svg':'image/svg+xml','webp':'image/webp','ico':'image/x-icon','swf':'application/x-shockwave-flash','woff':'font/woff','woff2':'font/woff2','ttf':'font/ttf','mp4':'video/mp4','webm':'video/webm','json':'application/json','xml':'application/xml'}
def dec_utf8(r):
    raw = r.content; c = r.headers.get('Content-Type','')
    if 'charset=' in c:
        cs = c.split('charset=')[-1].strip().split(';')[0].strip().lower()
        if cs and cs != 'utf-8':
            try: return raw.decode(cs)
            except: pass
    for enc in ['utf-8','gbk','gb18030','big5']:
        try: return raw.decode(enc)
        except UnicodeDecodeError: pass
    return raw.decode('utf-8', errors='replace')
_DEFAULT_INDEX = ('index.html','index.htm','default.html','default.htm','Index.html','Index.htm','Default.html','Default.htm','INDEX.HTML','INDEX.HTM','DEFAULT.HTML','DEFAULT.HTM')
def _find_default_html(directory):
    for name in _DEFAULT_INDEX:
        p = os.path.join(directory, name)
        if os.path.isfile(p): return p
    return None
def _find_any_html(directory):
    for r, d, fs in os.walk(directory):
        for fn in fs:
            if fn.lower().endswith(('.html', '.htm')) and not fn.endswith('.raw'): return os.path.join(r, fn)
    return None
# ==================== Hosts ====================
def _hosts_path(): return r'C:\Windows\System32\drivers\etc\hosts' if sys.platform == 'win32' else '/etc/hosts'
def _inject(domain):
    p = _hosts_path()
    try:
        enc = 'utf-8' if sys.platform != 'win32' else 'gbk'
        with open(p,'r',encoding=enc,errors='ignore') as f: c = f.read()
        if f'127.0.0.1 {domain}' in c:
            if sys.platform == 'win32': subprocess.run(['ipconfig','/flushdns'],capture_output=True,timeout=5)
            return True
        with open(p,'a',encoding=enc) as f: f.write(f"\n# === WEB_DL_START ===\n127.0.0.1 {domain}\n# === WEB_DL_END ===\n")
        if sys.platform == 'win32': subprocess.run(['ipconfig','/flushdns'],capture_output=True,timeout=5)
        return True
    except PermissionError: return False
    except: return False
def _clean():
    p = _hosts_path()
    try:
        enc = 'utf-8' if sys.platform != 'win32' else 'gbk'
        with open(p,'r',encoding=enc,errors='ignore') as f: ls = f.readlines()
        nl, skip = [], False
        for l in ls:
            if '=== WEB_DL_START ===' in l: skip=True; continue
            if '=== WEB_DL_END ===' in l: skip=False; continue
            if not skip: nl.append(l)
        with open(p,'w',encoding=enc) as f: f.writelines(nl)
        if sys.platform == 'win32': subprocess.run(['ipconfig','/flushdns'],capture_output=True,timeout=5)
    except: pass
# ==================== 翻译引擎 ====================
LANGS = {'自动检测':'auto','中文(简体)':'zh-CN','中文(繁体)':'zh-TW','英语':'en','日语':'ja','韩语':'ko','法语':'fr','德语':'de','西班牙语':'es','俄语':'ru','葡萄牙语':'pt','意大利语':'it','阿拉伯语':'ar','泰语':'th','越南语':'vi','印尼语':'id','马来语':'ms','印地语':'hi','荷兰语':'nl','波兰语':'pl','土耳其语':'tr'}
_LANG_CONV = {'google': {'auto':'auto','zh-CN':'zh-CN','zh-TW':'zh-TW'}, 'mymemory': {'auto':'autodetect','zh-CN':'zh','zh-TW':'zh-TW'}, 'argos': {'auto':'auto','zh-CN':'zh','zh-TW':'zt'}, 'lingva': {'auto':'auto','zh-CN':'zh','zh-TW':'zh-TW'}}
def _conv_lang(lang, engine):
    if lang in _LANG_CONV.get(engine, {}): return _LANG_CONV[engine][lang]
    return lang.split('-')[0] if engine != 'google' else lang
def _gt(text, tgt='zh-CN', src='auto'):
    s, t = _conv_lang(src,'google'), _conv_lang(tgt,'google')
    for _ in range(3):
        try:
            r = requests.get("https://translate.googleapis.com/translate_a/single", params={'client':'gtx','sl':s,'tl':t,'dt':'t','q':text}, timeout=15)
            r.raise_for_status(); return ''.join(i[0] for i in r.json()[0] if i[0])
        except:
            if _ < 2: time.sleep(1.5*(_+1))
            else: raise
def _mymemory(text, tgt='zh-CN', src='auto'):
    s, t = _conv_lang(src,'mymemory'), _conv_lang(tgt,'mymemory')
    r = requests.get("https://api.mymemory.translated.net/get", params={'q':text,'langpair':f'{s}|{t}'}, timeout=15)
    r.raise_for_status(); d = r.json()
    if d.get('responseStatus') == 200: return d['responseData']['translatedText']
    raise Exception(d.get('responseDetails','Error'))
def _argos(text, tgt='zh-CN', src='auto'):
    s, t = _conv_lang(src,'argos'), _conv_lang(tgt,'argos')
    r = requests.post("https://translate.argosopentech.com/translate", data={'text':text,'source':s,'target':t}, timeout=15)
    r.raise_for_status(); return r.text.strip()
def _lingva(text, tgt='zh-CN', src='auto'):
    s, t = _conv_lang(src,'lingva'), _conv_lang(tgt,'lingva')
    r = requests.get(f"https://lingva.thedaviddelta.com/api/v1/{s}/{t}/{quote(text,safe='')}", timeout=15)
    r.raise_for_status(); return r.json()['translation']
def _translate(text, engine, tgt, src):
    if engine == 'google': return _gt(text, tgt, src)
    elif engine == 'mymemory': return _mymemory(text, tgt, src)
    elif engine == 'argos': return _argos(text, tgt, src)
    elif engine == 'lingva': return _lingva(text, tgt, src)
    raise ValueError(f"未知引擎: {engine}")
AI_PRESETS = {'自定义': {'ep':'','mdl':'','hint':''}, 'DeepSeek': {'ep':'https://api.deepseek.com/chat/completions','mdl':'deepseek-chat','hint':'注册送额度，极便宜'}, '通义千问': {'ep':'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions','mdl':'qwen-turbo','hint':'注册送额度'}, '智谱GLM': {'ep':'https://open.bigmodel.cn/api/paas/v4/chat/completions','mdl':'glm-4-flash','hint':'注册送额度'}, 'Groq': {'ep':'https://api.groq.com/openai/v1/chat/completions','mdl':'llama-3.3-70b-versatile','hint':'免费额度，速度快'}, 'SiliconFlow': {'ep':'https://api.siliconflow.cn/v1/chat/completions','mdl':'Qwen/Qwen2.5-7B-Instruct','hint':'注册送额度'}, '零一万物': {'ep':'https://api.lingyiwanwu.com/v1/chat/completions','mdl':'yi-lightning','hint':'注册送额度'}, 'OpenAI': {'ep':'https://api.openai.com/v1/chat/completions','mdl':'gpt-4o-mini','hint':'官方付费'}}
def _ai(text, tgt, src, ep, key, mdl):
    h = {'Authorization':f'Bearer {key}','Content-Type':'application/json'}
    s = '自动检测' if src=='auto' else src
    r = requests.post(ep, headers=h, json={'model':mdl,'messages':[{'role':'system','content':f'你是翻译器。{s}→{tgt}。只输出结果，保持格式换行。'},{'role':'user','content':text}],'temperature':0.1}, timeout=60)
    r.raise_for_status(); return r.json()['choices'][0]['message']['content'].strip()
def _trans_html(html, sl, tl, engine, prog=None, acfg=None):
    soup = BeautifulSoup(html,'html.parser')
    SKIP = {'script','style','noscript','code','pre','kbd','samp','var','textarea','svg','canvas'}
    TT = {'p','span','div','h1','h2','h3','h4','h5','h6','li','td','th','label','button','a','figcaption','blockquote','caption','summary','dt','dd','b','i','em','strong','small','mark','section','article','header','footer','nav','main','aside'}
    items = []
    tt = soup.find('title')
    if tt and tt.string and tt.string.strip(): items.append(('s',tt,tt.string.strip()))
    for o in soup.find_all('option'):
        v = o.get('value','')
        if v and v.strip() and not v.strip().isdigit() and len(v.strip())>1: items.append(('a',o,v.strip()))
    for t in soup.find_all(True):
        if t.name in SKIP or t.name not in TT: continue
        for ch in list(t.children):
            if isinstance(ch, NavigableString):
                tx = ch.strip()
                if tx and len(tx)>1 and not re.match(r'^[\d\s\.\,\-\+\:\;\/\\\|\*\(\)\[\]\{\}<>@#$%^&_=]+$', tx): items.append(('t',ch,tx))
    if not items: return html
    seen=set(); uq=[]
    for it in items:
        if it[2] not in seen: seen.add(it[2]); uq.append(it)
    tm={}
    for i,(_,_,tx) in enumerate(uq):
        try:
            if engine == 'ai': tr=_ai(tx,tl,sl,acfg['ep'],acfg['key'],acfg['mdl'])
            else: tr=_translate(tx,engine,tl,sl)
            tm[tx]=tr
        except: tm[tx]=tx
        if prog: prog(i+1,len(uq))
        if engine in ('google','lingva'): time.sleep(0.3)
        elif engine == 'mymemory': time.sleep(0.1)
    for k,el,tx in items:
        tr=tm.get(tx,tx)
        if k=='s': el.string=tr
        elif k=='a': el['value']=tr
        elif k=='t':
            o=str(el); ld=o[:len(o)-len(o.lstrip())]; tr2=o[len(o.rstrip()):]
            el.replace_with(NavigableString(ld+tr+tr2))
    return str(soup)
# ==================== 代理HTML ====================
def make_proxy(raw_path, orig_url):
    with open(raw_path,'r',encoding='utf-8') as f: soup = BeautifulSoup(f.read(),'html.parser')
    p = urlparse(orig_url); nl,base = p.netloc, f"{p.scheme}://{p.netloc}{p.path}"
    for t in soup.find_all('base'): t.decompose()
    TAGS={'img':['src','data-src','data-original','data-lazy-src','data-srcset'],'link':['href'],'script':['src'],'video':['src','poster'],'audio':['src'],'source':['src'],'embed':['src'],'iframe':['src'],'object':['data'],'input':['src']}
    for tag,attrs in TAGS.items():
        for el in soup.find_all(tag):
            for attr in attrs:
                v=el.get(attr)
                if v:
                    au=normalize_url(base,v)
                    if au and is_cross(au,nl) and not is_verify(au): el[attr]=to_proxy(au)
    for el in soup.find_all(attrs={'srcset':True}):
        ents=[]
        for en in el['srcset'].split(','):
            en=en.strip()
            if not en: continue
            ps=en.rsplit(None,1); up,sf=ps[0],(ps[1] if len(ps)>1 else '')
            au=normalize_url(base,up)
            if au and is_cross(au,nl) and not is_verify(au): ents.append(f"{to_proxy(au)} {sf}".strip())
            else: ents.append(en)
        el['srcset']=', '.join(ents)
    def cr(text):
        def r(m):
            au=normalize_url(base,m.group(1))
            if au and is_cross(au,nl) and not is_verify(au): return f'url({to_proxy(au)})'
            return m.group(0)
        return re.sub(r'url\(["\']?(.*?)["\']?\)',r,text)
    for s in soup.find_all('style'):
        if s.string: s.string=cr(s.string)
    for el in soup.find_all(style=True): el['style']=cr(el['style'])
    for el in soup.find_all(attrs={'integrity':True}): del el['integrity']
    for el in soup.find_all(attrs={'crossorigin':True}): del el['crossorigin']
    if not soup.find('meta',attrs={'charset':True}):
        m=soup.new_tag('meta',attrs={'charset':'utf-8'})
        (soup.head and soup.head.insert(0,m)) or soup.insert(0,m)
    return str(soup)
# ==================== HTTP服务器 ====================
class TServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads=True; allow_reuse_address=True
    _HOP=frozenset({'host','connection','transfer-encoding','keep-alive','proxy-authorization','proxy-authenticate','te','trailer','upgrade','content-length'})
    _SKIP_RESP=_HOP|frozenset({'content-encoding'})
class ResServer(TServer):
    def __init__(self, addr, orig_url, save_dir, mode='cors', domain='', settings=None):
        super().__init__(addr, ResHandler)
        self.orig_url=orig_url; pp=urlparse(orig_url)
        self.orig_base=f"{pp.scheme}://{pp.netloc}"; self.orig_netloc=pp.netloc
        self.save_dir=save_dir; self.mode=mode; self.domain=domain
        self.settings=settings or {}
        self.sess=requests.Session()
        mc=self.settings.get('max_concurrent',50)
        a=requests.adapters.HTTPAdapter(pool_connections=mc,pool_maxsize=mc,max_retries=0)
        self.sess.mount('http://',a); self.sess.mount('https://',a)
        self.downloaded={}; self.in_progress=set()
        self.stats={'ok':0,'skip':0,'fail':0,'active':0,'sz':0}
        self.failed=[]; self.lock=threading.Lock()
        self.stop=False; self.paused=False; self.on_log=None
        self.current_file="-"; self.speed=0; self._lsz=0; self._lt=time.time()
    def log(self,msg,lv='INFO'):
        if self.on_log: self.on_log(msg,lv)
    def save_path_for(self,url):
        pp=urlparse(url); path=unquote(pp.path)
        if not path or path=='/': path='/index.html'
        d=os.path.dirname(path).lstrip('/'); fn=safe_filename(os.path.basename(path))
        if pp.netloc and pp.netloc!=self.orig_netloc: rel=os.path.join('external',safe_filename(pp.netloc.replace(':','_')),d,fn)
        else: rel=os.path.join(d,fn) if d else fn
        return os.path.join(self.save_dir,rel),rel
    def cache_file(self): return os.path.join(self.save_dir,'.proxy_cache.json')
    def save_cache(self):
        try:
            with self.lock:
                data={'downloaded':dict(self.downloaded),'failed':list(self.failed),'stats':dict(self.stats)}
            with open(self.cache_file(),'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
            return len(data['downloaded']), data['stats'].get('sz',0)
        except Exception as e: self.log(f"✗ 缓存保存失败: {e}",'ERROR'); return 0, 0
    def load_cache(self):
        cf=self.cache_file()
        if not os.path.exists(cf): return 0, 0
        try:
            with open(cf,'r',encoding='utf-8') as f: data=json.load(f)
            with self.lock:
                dl=data.get('downloaded',{}); valid={}
                for url, rel in dl.items():
                    if os.path.isfile(os.path.join(self.save_dir, rel)): valid[url]=rel
                self.downloaded=valid; self.failed=data.get('failed',[])
                st=data.get('stats',{})
                for k in ('ok','skip','fail','sz'): self.stats[k]=st.get(k,0)
            return len(valid), self.stats['sz']
        except Exception as e: self.log(f"✗ 缓存加载失败: {e}",'ERROR'); return 0, 0
    def clear_cache(self):
        cf=self.cache_file()
        if os.path.exists(cf):
            try: os.remove(cf)
            except: pass
class ResHandler(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def do_GET(self): self._h('GET')
    def do_POST(self): self._h('POST')
    def do_HEAD(self): self._h('HEAD')
    def do_PUT(self): self._h('PUT')
    def do_DELETE(self): self._h('DELETE')
    def do_PATCH(self): self._h('PATCH')
    def do_OPTIONS(self):
        if self.server.mode=='hosts': return self._err(405)
        o=self.headers.get('Origin','*'); h=self.headers.get('Access-Control-Request-Headers','*')
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin',o); self.send_header('Access-Control-Allow-Credentials','true')
        self.send_header('Access-Control-Allow-Methods','*'); self.send_header('Access-Control-Allow-Headers',h)
        self.send_header('Content-Length','0'); self.end_headers()
    def _try_local(self, path):
        if os.path.isfile(path): return path
        if os.path.isdir(path):
            p = _find_default_html(path)
            if p: return p
        if not os.path.splitext(path)[1]:
            for name in _DEFAULT_INDEX:
                t2 = path + os.path.splitext(name)[1]
                for t in (os.path.join(os.path.dirname(path), name), t2):
                    if os.path.isfile(t): return t
        return None
    def _h(self,method):
        srv=self.server
        if srv.stop: return self._err(503)
        if srv.paused:
            self.send_response(503); b=b"Paused"
            self.send_header('Content-Type','text/plain'); self.send_header('Content-Length',str(len(b)))
            self._cors(); self.end_headers(); self.wfile.write(b); return
        self._origin=self.headers.get('Origin','*'); body=None
        try:
            cl=int(self.headers.get('Content-Length',0))
            if cl>0: body=self.rfile.read(cl)
        except: pass
        if srv.mode=='hosts':
            local=self._try_local(os.path.join(srv.save_dir,self.path.lstrip('/')))
            if local: return self._serve(local)
            return self._proxy(srv,f"http://{srv.domain}{self.path}",method,body)
        else:
            real=from_proxy(self.path)
            if real:
                if is_verify(real):
                    self.send_response(302); self.send_header('Location',real)
                    self.send_header('Content-Length','0'); self._cors(); self.end_headers(); return
                return self._proxy(srv,real,method,body)
            local=self._try_local(os.path.join(srv.save_dir,self.path.lstrip('/')))
            if local: return self._serve(local)
            self._proxy(srv,srv.orig_base.rstrip('/')+self.path,method,body)
    def _proxy(self,srv,url,method,body=None):
        if srv.stop: return self._err(503)
        with srv.lock: srv.stats['active']+=1
        try:
            cached=None
            with srv.lock:
                if url in srv.downloaded:
                    sp=os.path.join(srv.save_dir,srv.downloaded[url])
                    if os.path.isfile(sp): srv.stats['skip']+=1; cached=sp
            if cached is not None: return self._serve(cached)
            with srv.lock:
                if url in srv.in_progress: srv.stats['skip']+=1; cached='__skip__'
                else: srv.in_progress.add(url)
            if cached=='__skip__':
                self.send_response(204); self.send_header('Content-Length','0'); self._cors(); self.end_headers(); return
            p=urlparse(url); pl=(p.path or '').lower(); ql=(p.query or '').lower()
            if ('xlsc.aspx' in pl and 'dl=' in ql) or 'lsp.aspx' in pl or 'fd/ls/' in pl:
                with srv.lock: srv.stats['skip']+=1
                self.send_response(204); self.send_header('Content-Length','0'); self._cors(); self.end_headers(); return
            try:
                srv.current_file=os.path.basename(p.path) or url[:30]
                rh={}
                for key,value in self.headers.items():
                    kl=key.lower()
                    if kl in _HOP: continue
                    if kl=='accept-encoding':
                        if HAS_BROTLI: rh[key]=value
                        else:
                            v=re.sub(r',?\s*br\s*,?','',value).strip(', ')
                            rh[key]=v if v else 'gzip, deflate'
                    else: rh[key]=value
                rh.pop('Origin',None)
                ref=rh.get('Referer','')
                lp=f"http://127.0.0.1:{self.server.server_address[1]}"
                if ref.startswith(lp): rh['Referer']=srv.orig_base+ref[len(lp):]
                elif '127.0.0.1' in ref: rh['Referer']=ref.replace('127.0.0.1',srv.orig_netloc)
                timeout=srv.settings.get('request_timeout',15)
                r=srv.sess.request(method,url,headers=rh,data=body,timeout=timeout,allow_redirects=True)
                r.raise_for_status(); data=r.content
                max_mb=srv.settings.get('max_file_size_mb',0)
                if max_mb > 0 and len(data) > max_mb * 1048576:
                    with srv.lock: srv.stats['skip']+=1
                    srv.log(f" ⊙ 跳过(>{max_mb}MB): {p.path[-40:]}",'WARNING')
                    self.send_response(200)
                    self.send_header('Content-Type',r.headers.get('Content-Type','application/octet-stream'))
                    self.send_header('Content-Length',str(len(data))); self._cors(); self.end_headers()
                    self.wfile.write(data); return
                raw_ct=r.headers.get('Content-Type','application/octet-stream').split(';')[0]
                final_ct=guess_ct(url,raw_ct)
                if 'text/html' in final_ct:
                    try: data=dec_utf8(r).encode('utf-8'); final_ct='text/html; charset=utf-8'
                    except: pass
                if srv.settings.get('skip_empty_html',True) and 'text/html' in final_ct and not data.strip():
                    with srv.lock: srv.stats['skip']+=1
                    self.send_response(204); self.send_header('Content-Length','0'); self._cors(); self.end_headers(); return
                sf,sr=srv.save_path_for(url)
                if not os.path.splitext(sf)[1]:
                    ext=ext_from_ct(final_ct)
                    if ext: sf+=ext; sr+=ext
                os.makedirs(os.path.dirname(sf),exist_ok=True)
                with open(sf,'wb') as f: f.write(data)
                with srv.lock:
                    srv.stats['ok']+=1; srv.stats['sz']+=len(data); srv.downloaded[url]=sr
                now=time.time(); dt=now-srv._lt
                if dt>=0.3: srv.speed=(srv.stats['sz']-srv._lsz)/dt; srv._lt=now; srv._lsz=srv.stats['sz']
                srv.log(f" ✓ {os.path.basename(sf)} — {fmt_size(len(data))}")
                self.send_response(200)
                try:
                    for hk,hv in r.raw.headers.items():
                        if hk.lower() in _SKIP_RESP: continue
                        self.send_header(hk,hv)
                except: pass
                self.send_header('Content-Type',final_ct); self.send_header('Content-Length',str(len(data)))
                self._cors(); self.end_headers(); self.wfile.write(data)
            except requests.exceptions.HTTPError as e:
                c=e.response.status_code if e.response is not None else '???'
                with srv.lock: srv.stats['fail']+=1; srv.failed.append((url,f"HTTP {c}"))
                srv.log(f" ✗ HTTP {c}: {url[:60]}",'ERROR'); self._err(502)
            except requests.exceptions.Timeout:
                with srv.lock: srv.stats['fail']+=1; srv.failed.append((url,"Timeout"))
                srv.log(f" ✗ 超时: {url[:60]}",'ERROR'); self._err(504)
            except requests.exceptions.ConnectionError:
                with srv.lock: srv.stats['fail']+=1; srv.failed.append((url,"ConnErr"))
                srv.log(f" ✗ 连接失败: {url[:60]}",'ERROR'); self._err(502)
            except Exception as e:
                with srv.lock: srv.stats['fail']+=1; srv.failed.append((url,type(e).__name__))
                srv.log(f" ✗ {type(e).__name__}: {url[:60]}",'ERROR'); self._err(500)
        finally:
            with srv.lock: srv.stats['active']-=1; srv.in_progress.discard(url)
    def _serve(self,path):
        try:
            with open(path,'rb') as f: data=f.read()
            ext=os.path.splitext(path)[1].lstrip('.').lower()
            self.send_response(200)
            self.send_header('Content-Type',CT_MAP.get(ext,'application/octet-stream'))
            self.send_header('Content-Length',str(len(data))); self.send_header('Content-Disposition','inline')
            self._cors(); self.end_headers(); self.wfile.write(data)
        except: self._err(500)
    def _cors(self):
        if self.server.mode=='hosts': return
        self.send_header('Access-Control-Allow-Origin',getattr(self,'_origin','*'))
        self.send_header('Access-Control-Allow-Credentials','true')
    def _err(self,code):
        self.send_response(code); b=f"Error {code}".encode()
        self.send_header('Content-Type','text/plain'); self.send_header('Content-Length',str(len(b)))
        self._cors(); self.end_headers(); self.wfile.write(b)
    def log_message(self,*a): pass
# ==================== HTML路径替换 ====================
def replace_paths(html_path,orig_url,rmap,save_dir):
    if not rmap: return 0
    with open(html_path,'r',encoding='utf-8') as f: soup=BeautifulSoup(f.read(),'html.parser')
    base=f"{urlparse(orig_url).scheme}://{urlparse(orig_url).netloc}{urlparse(orig_url).path}"
    hd=os.path.relpath(os.path.dirname(html_path),save_dir)
    if hd=='.': hd=''
    rm={u:(os.path.relpath(r,hd).replace('\\','/') if hd else r) for u,r in rmap.items()}
    def gl(au):
        if not au: return None
        if au in rm: return rm[au]
        b=au.split('?')[0].split('#')[0]; return rm.get(b) if b!=au else None
    TAGS={'img':['src','data-src','data-original','data-lazy-src'],'link':['href'],'script':['src'],'video':['src','poster'],'audio':['src'],'source':['src'],'embed':['src'],'iframe':['src'],'object':['data']}
    c=[0]
    for tag,attrs in TAGS.items():
        for el in soup.find_all(tag):
            for attr in attrs:
                v=el.get(attr)
                if v:
                    au=normalize_url(base,v); l=gl(au)
                    if l: el[attr]=l; c[0]+=1
    def cr(text):
        def r(m):
            au=normalize_url(base,m.group(1)); l=gl(au)
            if l: c[0]+=1; return f'url({l})'
            return m.group(0)
        return re.sub(r'url\(["\']?(.*?)["\']?\)',r,text)
    for s in soup.find_all('style'):
        if s.string: s.string=cr(s.string)
    for el in soup.find_all(style=True): el['style']=cr(el['style'])
    with open(html_path,'w',encoding='utf-8') as f: f.write(str(soup))
    return c[0]
# ==================== 默认设置 ====================
DEFAULT_SETTINGS = {
    'port': 8899,
    'request_timeout': 15,
    'max_concurrent': 50,
    'skip_empty_html': True,
    'max_file_size_mb': 0,
    'auto_replace_paths': True,
    'clear_log_on_new': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}
# ==================== GUI ====================
class App:
    def __init__(self):
        self.root=tk.Tk()
        self.root.title(f"网页资源下载器 v{__version__}")
        self.root.geometry("1100x720"); self.root.minsize(950,550)
        self.base_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)),'web')
        os.makedirs(self.base_dir,exist_ok=True)
        self.cfg_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)),'.config')
        os.makedirs(self.cfg_dir,exist_ok=True)
        self.server=None; self._tray=None; self._quitting=False; self._hosts_dom=None
        self.cur_url=self.cur_dir=self.cur_html=self.cur_raw=self.cur_rel=None
        self.stm=None; self.items=[]; self._rdata=None
        self.settings=self._load_settings()
        self._ai_cfg=self._load_ai_cfg()
        self._ui(); self._ref_list()
        self.root.protocol("WM_DELETE_WINDOW",self._on_close)
        self.url_v.trace_add('write',lambda *_: self.btn_go.config(state='normal' if self.url_v.get().strip() else 'disabled'))
        if HAS_TRAY: self._setup_tray()
    def _load_settings(self):
        p=os.path.join(self.cfg_dir,'settings.json')
        if os.path.exists(p):
            try:
                with open(p,'r',encoding='utf-8') as f: s=json.load(f)
                d=dict(DEFAULT_SETTINGS); d.update(s); return d
            except: pass
        return dict(DEFAULT_SETTINGS)
    def _save_settings(self):
        try:
            with open(os.path.join(self.cfg_dir,'settings.json'),'w',encoding='utf-8') as f:
                json.dump(self.settings,f,ensure_ascii=False,indent=2)
        except: pass
    def _load_ai_cfg(self):
        p=os.path.join(self.cfg_dir,'ai.json')
        if os.path.exists(p):
            try:
                with open(p,'r',encoding='utf-8') as f: return json.load(f)
            except: pass
        return {'preset':'DeepSeek','ep':AI_PRESETS['DeepSeek']['ep'],'key':'','mdl':AI_PRESETS['DeepSeek']['mdl']}
    def _save_ai_cfg(self):
        try:
            with open(os.path.join(self.cfg_dir,'ai.json'),'w',encoding='utf-8') as f:
                json.dump(self._ai_cfg,f,ensure_ascii=False)
        except: pass
    def _setup_tray(self):
        def img():
            im=Image.new('RGBA',(64,64),(0,0,0,0)); d=ImageDraw.Draw(im)
            d.ellipse([6,6,58,58],fill=(46,125,50),outline=(200,200,200),width=2)
            d.rectangle([26,32,38,48],fill='white'); d.polygon([(32,20),(20,34),(44,34)],fill='white')
            return im
        self._tray=pystray.Icon("wdl",img(),"网页资源下载器",pystray.Menu(
            pystray.MenuItem("显示窗口",lambda i,t: self.root.after(0,self.root.deiconify)),
            pystray.MenuItem("退出",lambda i,t: (setattr(self,'_quitting',True),i.stop(),self.root.after(0,self._do_quit)))))
        threading.Thread(target=self._tray.run,daemon=True).start()
    def _on_close(self):
        if HAS_TRAY and self._tray: self.root.withdraw()
        else: self._do_quit()
    def _do_quit(self):
        self._clean_hosts()
        if self.server: self.server.stop=True
        if self._tray:
            try: self._tray.stop()
            except: pass
        self.root.quit(); self.root.destroy()
    def _clean_hosts(self):
        if self._hosts_dom: _clean(); self._hosts_dom=None
    def _scan(self):
        items=[]
        if not os.path.exists(self.base_dir): return items
        for n in os.listdir(self.base_dir):
            sd=os.path.join(self.base_dir,n)
            if not os.path.isdir(sd): continue
            mp=os.path.join(sd,'meta.json')
            if not os.path.exists(mp): continue
            try:
                with open(mp,'r',encoding='utf-8') as f: m=json.load(f)
                items.append({'dir':sd,'url':m.get('url',''),'status':m.get('status','html'),'ok':m.get('ok',0),'fail':m.get('fail',0),'sz':m.get('sz',0),'time':datetime.fromtimestamp(os.path.getmtime(sd)).strftime('%Y-%m-%d %H:%M')})
            except: continue
        items.sort(key=lambda x:x['time'],reverse=True); return items
    def _save_meta(self,d,data):
        with open(os.path.join(d,'meta.json'),'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False)
    def _mk_ctx(self,w,it=False):
        m=tk.Menu(w,tearoff=0)
        def cp():
            try: t=w.get("sel.first","sel.last") if it else w.selection_get(); self.root.clipboard_clear(); self.root.clipboard_append(t)
            except: pass
        def ct():
            try: t=w.get("sel.first","sel.last") if it else w.selection_get(); self.root.clipboard_clear(); self.root.clipboard_append(t); w.delete("sel.first","sel.last")
            except: pass
        def ps():
            try: w.insert("insert",self.root.clipboard_get())
            except: pass
        def sa(): w.tag_add("sel","1.0","end") if it else w.select_range(0,"end")
        def cl(): w.delete("1.0","end") if it else w.delete(0,"end")
        m.add_command(label="剪切",command=ct); m.add_command(label="复制",command=cp)
        m.add_command(label="粘贴",command=ps); m.add_separator()
        m.add_command(label="全选",command=sa); m.add_command(label="清空",command=cl)
        def show(e):
            if not it:
                w.focus_set(); i=w.index("@%d,%d"%(e.x,e.y))
                try:
                    if w.selection_present() and w.index("sel.first")<=i<=w.index("sel.last"): pass
                    else: w.selection_clear(); w.icursor(i)
                except: w.icursor(i)
            try: m.tk_popup(e.x_root,e.y_root)
            finally: m.grab_release()
        w.bind("<Button-3>",show)
        if sys.platform=='darwin': w.bind("<Button-2>",show)
    def _find_html(self, it):
        d = it['dir']
        mp = os.path.join(d, 'meta.json')
        if os.path.exists(mp):
            try:
                with open(mp,'r',encoding='utf-8') as f: m=json.load(f)
                rel = m.get('rel','')
                if rel:
                    exact = os.path.join(d, rel)
                    if os.path.isfile(exact) and not exact.endswith('.raw'): return exact
            except: pass
        p = _find_default_html(d)
        if p: return p
        return _find_any_html(d)
    def _get_fails(self):
        fails=[]
        if self.server:
            with self.server.lock: fails=list(self.server.failed)
        if not fails and self._rdata: fails=list(self._rdata['failed'])
        return fails
    def _show_failed(self):
        fails=self._get_fails()
        if not fails: messagebox.showinfo("失败列表","暂无失败项 ✓"); return
        dlg=tk.Toplevel(self.root); dlg.title(f"失败列表 ({len(fails)}项)")
        dlg.geometry("750x480"); dlg.resizable(True,True); dlg.transient(self.root); dlg.grab_set()
        hf=ttk.Frame(dlg); hf.pack(fill='x',padx=10,pady=(10,5))
        ttk.Label(hf,text=f"共 {len(fails)} 个失败项",font=('',10,'bold')).pack(side='left')
        ttk.Button(hf,text="复制全部",command=lambda:self._cp_f(fails)).pack(side='right',padx=3)
        if self._rdata: ttk.Button(hf,text="重试全部",command=lambda:(dlg.destroy(),self._retry())).pack(side='right',padx=3)
        ttk.Button(hf,text="关闭",command=dlg.destroy).pack(side='right',padx=3)
        fr=ttk.Frame(dlg); fr.pack(fill='both',expand=True,padx=10,pady=5)
        tree=ttk.Treeview(fr,columns=('idx','reason','url'),show='headings',height=12)
        tree.heading('idx',text='#',width=40,anchor='center'); tree.heading('reason',text='原因',width=120,anchor='w'); tree.heading('url',text='URL',width=500,anchor='w')
        tree.column('idx',width=40); tree.column('reason',width=120); tree.column('url',width=500)
        sb=ttk.Scrollbar(fr,orient='vertical',command=tree.yview); tree.configure(yscrollcommand=sb.set)
        tree.pack(side='left',fill='both',expand=True); sb.pack(side='right',fill='y')
        for i,(url,reason) in enumerate(fails): tree.insert('','end',iid=str(i),values=(i+1,reason,url))
        def cps():
            sel=tree.selection()
            if sel: self.root.clipboard_clear(); self.root.clipboard_append('\n'.join(tree.item(s,'values')[2] for s in sel))
        tree.bind('<Double-Button-1>',lambda e:cps())
        ctx=tk.Menu(tree,tearoff=0)
        ctx.add_command(label="复制选中URL",command=cps); ctx.add_command(label="复制全部URL",command=lambda:self._cp_f(fails))
        tree.bind('<Button-3>',lambda e:(tree.focus_set(),ctx.tk_popup(e.x_root,e.y_root)))
        x=self.root.winfo_x()+(self.root.winfo_width()-750)//2; y=self.root.winfo_y()+(self.root.winfo_height()-480)//2
        dlg.geometry(f'+{max(0,x)}+{max(0,y)}')
    def _cp_f(self,fails):
        self.root.clipboard_clear(); self.root.clipboard_append('\n'.join(u for u,_ in fails))
    # ==================== 设置对话框 ====================
    def _settings_dlg(self):
        dlg=tk.Toplevel(self.root); dlg.title("⚙ 设置"); dlg.geometry("640x560")
        dlg.resizable(False,False); dlg.transient(self.root); dlg.grab_set()
        nb=ttk.Notebook(dlg); nb.pack(fill='both',expand=True,padx=10,pady=10)
        # --- Tab 1: 网络设置 ---
        net=ttk.Frame(nb,padding=10); nb.add(net,text=" 🌐 网络设置 ")
        net.columnconfigure(1,weight=1)
        row=0
        ttk.Label(net,text="代理端口:").grid(row=row,column=0,sticky='w',pady=6)
        port_v=tk.StringVar(value=str(self.settings.get('port',8899)))
        port_e=ttk.Entry(net,textvariable=port_v,width=20); port_e.grid(row=row,column=1,sticky='w',pady=6)
        ttk.Label(net,text="兼容代理模式监听端口 (1-65535)",foreground='gray').grid(row=row,column=2,sticky='w',padx=5)
        row+=1
        ttk.Label(net,text="请求超时(秒):").grid(row=row,column=0,sticky='w',pady=6)
        timeout_v=tk.StringVar(value=str(self.settings.get('request_timeout',15)))
        ttk.Entry(net,textvariable=timeout_v,width=20).grid(row=row,column=1,sticky='w',pady=6)
        ttk.Label(net,text="代理转发到源站的单次超时",foreground='gray').grid(row=row,column=2,sticky='w',padx=5)
        row+=1
        ttk.Label(net,text="最大并发数:").grid(row=row,column=0,sticky='w',pady=6)
        concur_v=tk.StringVar(value=str(self.settings.get('max_concurrent',50)))
        ttk.Entry(net,textvariable=concur_v,width=20).grid(row=row,column=1,sticky='w',pady=6)
        ttk.Label(net,text="同时下载的最大连接数",foreground='gray').grid(row=row,column=2,sticky='w',padx=5)
        row+=1
        ttk.Label(net,text="User-Agent:").grid(row=row,column=0,sticky='nw',pady=6)
        ua_v=tk.StringVar(value=self.settings.get('user_agent',''))
        ua_e=ttk.Entry(net,textvariable=ua_v,width=60); ua_e.grid(row=row,column=1,columnspan=2,sticky='ew',pady=6)
        ua_show=tk.BooleanVar(value=False)
        def toggle_ua(): ua_e.config(show='' if ua_show.get() else '•')
        ttk.Checkbutton(net,text="显示",variable=ua_show,command=toggle_ua).grid(row=row,column=2,sticky='e',padx=5)
        row+=1
        ttk.Separator(net,orient='horizontal').grid(row=row,column=0,columnspan=3,sticky='ew',pady=8)
        row+=1
        ttk.Label(net,text="⚠️ hosts模式使用80端口，不受此设置影响",foreground='#cc8800').grid(row=row,column=0,columnspan=3,sticky='w')
        # --- Tab 2: 下载设置 ---
        dl_f=ttk.Frame(nb,padding=10); nb.add(dl_f,text=" ⬇ 下载设置 ")
        dl_f.columnconfigure(1,weight=1)
        row=0
        skip_v=tk.BooleanVar(value=self.settings.get('skip_empty_html',True))
        ttk.Checkbutton(dl_f,text="跳过空HTML文件",variable=skip_v).grid(row=row,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Label(dl_f,text="下载到的HTML内容为空时自动跳过",foreground='gray').grid(row=row,column=2,sticky='w',padx=10)
        row+=1
        size_v=tk.StringVar(value=str(self.settings.get('max_file_size_mb',0)))
        ttk.Label(dl_f,text="最大文件大小(MB):").grid(row=row,column=0,sticky='w',pady=6)
        ttk.Entry(dl_f,textvariable=size_v,width=20).grid(row=row,column=1,sticky='w',pady=6)
        ttk.Label(dl_f,text="0 = 不限制",foreground='gray').grid(row=row,column=2,sticky='w',padx=5)
        row+=1
        repl_v=tk.BooleanVar(value=self.settings.get('auto_replace_paths',True))
        ttk.Checkbutton(dl_f,text="完成后自动替换路径",variable=repl_v).grid(row=row,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Label(dl_f,text="将远程URL替换为本地相对路径",foreground='gray').grid(row=row,column=2,sticky='w',padx=10)
        row+=1
        clear_v=tk.BooleanVar(value=self.settings.get('clear_log_on_new',True))
        ttk.Checkbutton(dl_f,text="新任务时清空日志",variable=clear_v).grid(row=row,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Label(dl_f,text="开始新下载时自动清空上次的日志",foreground='gray').grid(row=row,column=2,sticky='w',padx=10)
        # --- Tab 3: AI翻译设置 ---
        ai_f=ttk.Frame(nb,padding=10); nb.add(ai_f,text=" 🤖 AI翻译 ")
        ai_f.columnconfigure(1,weight=1)
        row=0
        ttk.Label(ai_f,text="预设:").grid(row=row,column=0,sticky='w',pady=4)
        preset_v=tk.StringVar(value=self._ai_cfg.get('preset','DeepSeek'))
        preset_cb=ttk.Combobox(ai_f,textvariable=preset_v,values=list(AI_PRESETS.keys()),state='readonly',width=18)
        preset_cb.grid(row=row,column=1,sticky='w',pady=4)
        hint_lbl=ttk.Label(ai_f,text="",font=('',8),foreground='gray'); hint_lbl.grid(row=row,column=2,sticky='w',padx=5)
        row+=1
        ttk.Label(ai_f,text="Endpoint:").grid(row=row,column=0,sticky='w',pady=4)
        ep_v=tk.StringVar(value=self._ai_cfg.get('ep',''))
        ttk.Entry(ai_f,textvariable=ep_v,width=50).grid(row=row,column=1,columnspan=2,sticky='ew',pady=4)
        row+=1
        ttk.Label(ai_f,text="API Key:").grid(row=row,column=0,sticky='w',pady=4)
        key_v=tk.StringVar(value=self._ai_cfg.get('key',''))
        ttk.Entry(ai_f,textvariable=key_v,show='*',width=50).grid(row=row,column=1,columnspan=2,sticky='ew',pady=4)
        row+=1
        ttk.Label(ai_f,text="Model:").grid(row=row,column=0,sticky='w',pady=4)
        mdl_v=tk.StringVar(value=self._ai_cfg.get('mdl',''))
        ttk.Entry(ai_f,textvariable=mdl_v,width=50).grid(row=row,column=1,columnspan=2,sticky='ew',pady=4)
        def on_preset(*_):
            name=preset_v.get()
            if name in AI_PRESETS and name!='自定义':
                p=AI_PRESETS[name]; ep_v.set(p['ep']); mdl_v.set(p['mdl']); hint_lbl.config(text=p.get('hint',''))
            else: hint_lbl.config(text='')
        preset_cb.bind('<<ComboboxSelected>>',on_preset); on_preset()
        # --- 底部按钮 ---
        bf=ttk.Frame(dlg); bf.pack(fill='x',padx=10,pady=(0,10))
        def reset():
            port_v.set('8899'); timeout_v.set('15'); concur_v.set('50')
            ua_v.set(DEFAULT_SETTINGS['user_agent'])
            skip_v.set(True); size_v.set('0'); repl_v.set(True); clear_v.set(True)
            preset_v.set('DeepSeek'); on_preset(); key_v.set('')
        ttk.Button(bf,text="恢复默认",command=reset,width=10).pack(side='left')
        def save():
            try: port=int(port_v.get()); assert 1<=port<=65535
            except: messagebox.showwarning("提示","端口必须是 1-65535 的整数",parent=dlg); return
            try: timeout=int(timeout_v.get()); assert timeout>0
            except: messagebox.showwarning("提示","超时必须是正整数",parent=dlg); return
            try: concur=int(concur_v.get()); assert concur>0
            except: messagebox.showwarning("提示","并发数必须是正整数",parent=dlg); return
            try: max_mb=int(size_v.get()); assert max_mb>=0
            except: messagebox.showwarning("提示","文件大小限制必须≥0",parent=dlg); return
            self.settings['port']=port; self.settings['request_timeout']=timeout
            self.settings['max_concurrent']=concur; self.settings['skip_empty_html']=skip_v.get()
            self.settings['max_file_size_mb']=max_mb; self.settings['auto_replace_paths']=repl_v.get()
            self.settings['clear_log_on_new']=clear_v.get(); self.settings['user_agent']=ua_v.get().strip()
            self._ai_cfg={'preset':preset_v.get(),'ep':ep_v.get(),'key':key_v.get(),'mdl':mdl_v.get()}
            self._save_settings(); self._save_ai_cfg()
            self.repl_v.set(repl_v.get())
            messagebox.showinfo("设置","✓ 设置已保存",parent=dlg); dlg.destroy()
        ttk.Button(bf,text="保存",command=save,width=10).pack(side='right',padx=5)
        ttk.Button(bf,text="取消",command=dlg.destroy,width=8).pack(side='right')
        x=self.root.winfo_x()+(self.root.winfo_width()-640)//2; y=self.root.winfo_y()+(self.root.winfo_height()-560)//2
        dlg.geometry(f'+{max(0,x)}+{max(0,y)}')
    # ==================== 翻译对话框 ====================
    def _trans_dlg(self):
        it=self._get_sel()
        if not it: return messagebox.showwarning("提示","请先选择一个已下载的网页")
        hf=self._find_html(it)
        if not hf: return messagebox.showerror("错误","找不到HTML文件")
        dlg=tk.Toplevel(self.root); dlg.title("网页翻译器"); dlg.geometry("580x480")
        dlg.resizable(False,False); dlg.transient(self.root); dlg.grab_set()
        f1=ttk.LabelFrame(dlg,text="翻译设置",padding=10); f1.pack(fill='x',padx=10,pady=(10,5))
        f1.columnconfigure(1,weight=1)
        ttk.Label(f1,text="文件:").grid(row=0,column=0,sticky='w',pady=2)
        ttk.Label(f1,text=os.path.basename(hf),font=('',9,'bold')).grid(row=0,column=1,sticky='w',pady=2)
        ttk.Label(f1,text="引擎:").grid(row=1,column=0,sticky='w',pady=2)
        eng_names=['Google 翻译','MyMemory 翻译','Argos 翻译','Lingva 翻译','AI 翻译']
        eng_keys=['google','mymemory','argos','lingva','ai']
        eng_v=tk.StringVar(value='Google 翻译')
        ttk.Combobox(f1,textvariable=eng_v,values=eng_names,state='readonly',width=18).grid(row=1,column=1,sticky='w',pady=2)
        ttk.Label(f1,text="源语言:").grid(row=2,column=0,sticky='w',pady=2)
        sl_v=tk.StringVar(value='自动检测')
        ttk.Combobox(f1,textvariable=sl_v,values=list(LANGS.keys()),state='readonly',width=18).grid(row=2,column=1,sticky='w',pady=2)
        ttk.Label(f1,text="目标语言:").grid(row=3,column=0,sticky='w',pady=2)
        tl_v=tk.StringVar(value='中文(简体)')
        ttk.Combobox(f1,textvariable=tl_v,values=list(LANGS.keys()),state='readonly',width=18).grid(row=3,column=1,sticky='w',pady=2)
        pf=ttk.Frame(dlg); pf.pack(fill='x',padx=10,pady=5)
        tr_lbl=ttk.Label(pf,text="就绪",font=('',9)); tr_lbl.pack(side='left')
        tr_pb=ttk.Progressbar(pf,mode='determinate'); tr_pb.pack(side='left',fill='x',expand=True,padx=(10,0))
        log_f=ttk.LabelFrame(dlg,text="翻译日志",padding=3); log_f.pack(fill='both',expand=True,padx=10,pady=(0,10))
        tr_log=tk.Text(log_f,font=('Consolas',9),wrap='word',height=6,state='disabled'); tr_log.pack(fill='both',expand=True)
        bf=ttk.Frame(dlg); bf.pack(pady=(0,10))
        def go():
            eng_key=eng_keys[eng_names.index(eng_v.get())]
            sl=LANGS.get(sl_v.get(),'auto'); tl=LANGS.get(tl_v.get(),'zh-CN')
            if eng_key=='ai':
                if not self._ai_cfg.get('key','').strip():
                    return messagebox.showwarning("提示","AI翻译需要填写 API Key（请在设置中配置）",parent=dlg)
            for b in bf.winfo_children(): b.config(state='disabled')
            threading.Thread(target=_do,args=(hf,eng_key,sl,tl),daemon=True).start()
        ttk.Button(bf,text="开始翻译",command=go,width=12).pack(side='left',padx=5)
        ttk.Button(bf,text="关闭",command=dlg.destroy,width=8).pack(side='left',padx=5)
        def _do(hf,eng,sl,tl):
            try:
                with open(hf,'r',encoding='utf-8') as f: html=f.read()
                acfg=self._ai_cfg if eng=='ai' else None
                def on_p(i,tot):
                    self.root.after(0,tr_lbl.config,{"text":f"翻译中 {i}/{tot}"})
                    self.root.after(0,tr_pb.config,{"value":i/tot*100})
                self.root.after(0,self._log,f"开始翻译 ({eng_v.get()})…")
                result=_trans_html(html,sl,tl,eng,on_p,acfg)
                out=hf.replace('.html','_translated.html').replace('.htm','_translated.htm')
                with open(out,'w',encoding='utf-8') as f: f.write(result)
                self.root.after(0,tr_lbl.config,{"text":"✓ 完成"})
                self.root.after(0,self._log,f"✓ 翻译完成: {out}",'OK')
                self.root.after(0,lambda: messagebox.showinfo("完成",f"翻译已保存到:\n{out}",parent=dlg))
            except Exception as e:
                self.root.after(0,tr_lbl.config,{"text":"✗ 失败"})
                self.root.after(0,self._log,f"✗ 翻译失败: {e}",'ERROR')
                self.root.after(0,lambda: messagebox.showerror("失败",str(e),parent=dlg))
            finally:
                self.root.after(0,lambda: [b.config(state='normal') for b in bf.winfo_children()])
        x=self.root.winfo_x()+(self.root.winfo_width()-580)//2; y=self.root.winfo_y()+(self.root.winfo_height()-480)//2
        dlg.geometry(f'+{max(0,x)}+{max(0,y)}')
    # ==================== 主界面 ====================
    def _ui(self):
        paned=ttk.PanedWindow(self.root,orient=tk.HORIZONTAL); paned.pack(fill=tk.BOTH,expand=True,padx=5,pady=5)
        lf=ttk.LabelFrame(paned,text="已下载网页列表"); paned.add(lf,weight=1)
        bf=ttk.Frame(lf); bf.pack(fill='x',padx=5,pady=(5,0))
        ttk.Button(bf,text="刷新",command=self._ref_list).pack(side='left')
        ttk.Button(bf,text="翻译",command=self._trans_dlg).pack(side='left',padx=3)
        ttk.Button(bf,text="⚙ 设置",command=self._settings_dlg).pack(side='left',padx=3)
        ttk.Button(bf,text="打开目录",command=self._open_dir).pack(side='right',padx=2)
        ttk.Button(bf,text="删除",command=self._del_sel).pack(side='right',padx=2)
        fr=ttk.Frame(lf); fr.pack(fill=tk.BOTH,expand=True,padx=5,pady=5)
        self.lb=tk.Listbox(fr,font=('Consolas',10),activestyle='dotbox')
        sb=ttk.Scrollbar(fr,command=self.lb.yview); self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side=tk.LEFT,fill=tk.BOTH,expand=True); sb.pack(side=tk.RIGHT,fill=tk.Y)
        self.lb.bind('<<ListboxSelect>>',self._on_sel); self.lb.bind('<Double-Button-1>',self._on_dbl)
        self.ctx=tk.Menu(self.root,tearoff=0)
        self.ctx.add_command(label="代理模式打开（推荐）",command=self._open_proxy_sel)
        self.ctx.add_command(label="离线打开 file://",command=self._open_offline_sel)
        self.ctx.add_separator(); self.ctx.add_command(label="删除选中",command=self._del_sel)
        self.ctx.add_command(label="重新下载",command=self._redownload)
        self.ctx.add_separator(); self.ctx.add_command(label="全部删除",command=self._del_all)
        self.lb.bind('<Button-3>',lambda e:self._popup(e))
        rf=ttk.Frame(paned); paned.add(rf,weight=3)
        f1=ttk.LabelFrame(rf,text="下载",padding=5); f1.pack(fill='x',padx=5,pady=(0,5))
        ttk.Label(f1,text="网址:").grid(row=0,column=0,sticky='w',pady=2)
        self.url_v=tk.StringVar(); self.url_e=ttk.Entry(f1,textvariable=self.url_v,font=('Consolas',11))
        self.url_e.grid(row=0,column=1,sticky='ew',padx=5,pady=2); self.url_e.bind('<Return>',lambda _:self._start())
        f1.columnconfigure(1,weight=1)
        ttk.Label(f1,text="目录:").grid(row=1,column=0,sticky='w',pady=2)
        self.dir_v=tk.StringVar(value=self.base_dir); self.dir_e=ttk.Entry(f1,textvariable=self.dir_v,font=('Consolas',10))
        self.dir_e.grid(row=1,column=1,sticky='ew',padx=5,pady=2)
        ttk.Button(f1,text="更改",command=self._chg_dir,width=6).grid(row=1,column=2)
        self._mk_ctx(self.url_e); self._mk_ctx(self.dir_e)
        f2=ttk.Frame(rf); f2.pack(fill='x',padx=5,pady=(0,5))
        self.repl_v=tk.BooleanVar(value=self.settings.get('auto_replace_paths',True))
        ttk.Checkbutton(f2,text="替换路径",variable=self.repl_v).pack(side='left',padx=5)
        self.btn_go=ttk.Button(f2,text="下载网页",command=self._start,state='disabled'); self.btn_go.pack(side='left',padx=3,ipady=2)
        self.btn_batch=ttk.Button(f2,text="批量下载",command=self._batch_dlg); self.btn_batch.pack(side='left',padx=3)
        self.btn_redl=ttk.Button(f2,text="重新下载",command=self._redownload,state='disabled'); self.btn_redl.pack(side='left',padx=3)
        ttk.Separator(f2,orient='vertical').pack(side='left',fill='y',padx=6)
        self.btn_done=ttk.Button(f2,text="完成下载",command=self._done,state='disabled'); self.btn_done.pack(side='left',padx=3)
        self.btn_pause=ttk.Button(f2,text="⏸ 暂停",command=self._pause,state='disabled'); self.btn_pause.pack(side='left',padx=3)
        self.btn_stop=ttk.Button(f2,text="停止",command=self._stop,state='disabled'); self.btn_stop.pack(side='left',padx=3)
        ttk.Separator(f2,orient='vertical').pack(side='left',fill='y',padx=6)
        self.btn_retry=ttk.Button(f2,text="重试失败",command=self._retry,state='disabled'); self.btn_retry.pack(side='left',padx=3)
        ttk.Button(f2,text="⚙",command=self._settings_dlg,width=3).pack(side='right',padx=2)
        f3=ttk.LabelFrame(rf,text="实时统计",padding=8); f3.pack(fill='x',padx=5,pady=(0,5))
        for i in range(3): f3.columnconfigure(i,weight=1)
        self.lbl_ok=ttk.Label(f3,text="✓ 成功: 0",foreground="green",font=('',10,'bold')); self.lbl_ok.grid(row=0,column=0,sticky='w',padx=10)
        self.lbl_sk=ttk.Label(f3,text="⊙ 跳过: 0",foreground="gray",font=('',10)); self.lbl_sk.grid(row=0,column=1,sticky='w',padx=10)
        self.lbl_fl=ttk.Label(f3,text="✗ 失败: 0",foreground="red",font=('',10,'bold'),cursor='arrow'); self.lbl_fl.grid(row=0,column=2,sticky='w',padx=10)
        self.lbl_fl.bind('<Button-1>',lambda e:self._show_failed())
        self.lbl_fl.bind('<Enter>',lambda e:self.lbl_fl.config(cursor='hand2' if self._get_fails() else 'arrow'))
        self.lbl_fl.bind('<Leave>',lambda e:self.lbl_fl.config(cursor='arrow'))
        self.lbl_ac=ttk.Label(f3,text="↓ 下载中: 0",foreground="#0055ff",font=('',11,'bold')); self.lbl_ac.grid(row=1,column=0,sticky='w',padx=10,pady=3)
        self.lbl_sz=ttk.Label(f3,text="■ 大小: 0 B",font=('',10)); self.lbl_sz.grid(row=1,column=1,sticky='w',padx=10,pady=3)
        self.lbl_sp=ttk.Label(f3,text="↻ 速度: 0 KB/s",font=('',10)); self.lbl_sp.grid(row=1,column=2,sticky='w',padx=10,pady=3)
        self.pb=ttk.Progressbar(f3,mode='indeterminate',length=200); self.pb.grid(row=2,column=0,columnspan=3,sticky='ew',padx=10,pady=(5,0))
        f4=ttk.LabelFrame(rf,text="日志",padding=3); f4.pack(fill='both',expand=True,padx=5,pady=(0,5))
        self.logw=tk.Text(f4,font=('Consolas',9),wrap='word',state='disabled',padx=4,pady=4)
        sb2=ttk.Scrollbar(f4,command=self.logw.yview); self.logw.configure(yscrollcommand=sb2.set)
        self.logw.pack(side=tk.LEFT,fill=tk.BOTH,expand=True); sb2.pack(side=tk.RIGHT,fill=tk.Y)
        self.logw.tag_configure('ERROR',foreground='red'); self.logw.tag_configure('WARNING',foreground='#cc8800')
        self.logw.tag_configure('OK',foreground='green'); self._mk_ctx(self.logw,it=True)
    def _ref_list(self):
        self.items=self._scan(); self.lb.delete(0,tk.END)
        for it in self.items:
            s="✓" if it['status']=='done' else "◇"
            self.lb.insert(tk.END,f"{s} {it['time']} {it['ok']}文件 {it['fail']}失败 {fmt_size(it['sz'])}\n {it['url'][:50]}")
    def _get_sel(self):
        s=self.lb.curselection(); return self.items[s[0]] if s and s[0]<len(self.items) else None
    def _on_sel(self,e):
        it=self._get_sel()
        if it:
            self.url_v.set(it['url']); self.dir_v.set(self.base_dir)
            self.btn_redl.config(state='normal' if it and not self.server else 'disabled')
    def _on_dbl(self,e):
        it=self._get_sel()
        if not it: return
        if self.server: return messagebox.showwarning("提示","当前有服务正在运行，请先停止。")
        self._open_proxy(it)
    def _open_offline_sel(self):
        it=self._get_sel()
        if not it: return
        f=self._find_html(it)
        if f: webbrowser.open(f'file://{os.path.abspath(f)}')
        else: messagebox.showerror("错误","找不到HTML文件")
    def _open_proxy_sel(self):
        it=self._get_sel()
        if not it: return
        if self.server: return messagebox.showwarning("提示","当前有服务正在运行，请先停止。")
        self._open_proxy(it)
    def _popup(self,e):
        i=self.lb.nearest(e.y)
        if i>=0:
            self.lb.selection_clear(0,tk.END); self.lb.selection_set(i); self.lb.activate(i); self._on_sel(e)
        try: self.ctx.tk_popup(e.x_root,e.y_root)
        finally: self.ctx.grab_release()
    def _del_sel(self):
        it=self._get_sel()
        if it and messagebox.askyesno("确认",f"删除 {it['url']} ?"):
            shutil.rmtree(it['dir'],ignore_errors=True); self._ref_list(); self.btn_redl.config(state='disabled')
    def _del_all(self):
        if self.items and messagebox.askyesno("警告",f"删除全部 {len(self.items)} 条？"):
            for it in self.items: shutil.rmtree(it['dir'],ignore_errors=True)
            self._ref_list(); self.btn_redl.config(state='disabled')
    def _open_dir(self):
        it=self._get_sel()
        if it and os.path.isdir(it['dir']):
            os.startfile(it['dir']) if sys.platform=='win32' else os.system(f'xdg-open "{it["dir"]}"')
    def _redownload(self):
        it=self._get_sel()
        if not it: return
        if not messagebox.askyesno("重新下载",f"重新下载 {it['url']}？"): return
        if self.server: self.server.stop=True; time.sleep(0.3); self._close_srv()
        shutil.rmtree(it['dir'],ignore_errors=True); self.url_v.set(it['url']); self._start()
    def _chg_dir(self):
        d=filedialog.askdirectory(initialdir=self.base_dir)
        if d: self.base_dir=d; self.dir_v.set(d); os.makedirs(d,exist_ok=True); self._ref_list()
    def _set_idle(self):
        self.btn_go.config(state='normal' if self.url_v.get().strip() else 'disabled')
        self.btn_batch.config(state='normal')
        self.btn_redl.config(state='normal' if self._get_sel() else 'disabled')
        self.btn_done.config(state='disabled'); self.btn_pause.config(state='disabled',text='⏸ 暂停')
        self.btn_stop.config(state='disabled')
        self.btn_retry.config(state='normal' if self._rdata else 'disabled')
        self.pb.stop(); self.lbl_fl.config(cursor='hand2' if self._rdata else 'arrow')
    def _set_run(self):
        self.btn_go.config(state='disabled'); self.btn_batch.config(state='disabled')
        self.btn_redl.config(state='disabled'); self.btn_done.config(state='normal')
        self.btn_pause.config(state='normal'); self.btn_stop.config(state='normal')
        self.btn_retry.config(state='disabled'); self.pb.start(15)
    def _set_busy(self):
        for b in (self.btn_go,self.btn_batch,self.btn_redl,self.btn_done,self.btn_pause,self.btn_stop,self.btn_retry):
            b.config(state='disabled')
    def _log(self,m,lv='INFO'):
        self.logw.configure(state='normal'); self.logw.insert('end',m+'\n',lv)
        self.logw.see('end'); self.logw.configure(state='disabled')
    def _clr_log(self):
        self.logw.configure(state='normal'); self.logw.delete('1.0','end'); self.logw.configure(state='disabled')
    def _reset_st(self):
        for l,t in [(self.lbl_ok,"✓ 成功: 0"),(self.lbl_sk,"⊙ 跳过: 0"),(self.lbl_fl,"✗ 失败: 0"),(self.lbl_ac,"↓ 下载中: 0"),(self.lbl_sz,"■ 大小: 0 B"),(self.lbl_sp,"↻ 速度: 0 KB/s")]:
            l.config(text=t)
        self.pb.stop(); self.lbl_fl.config(cursor='arrow')
    def _upd_st(self):
        if self.server and not self.server.stop:
            with self.server.lock: s=self.server.stats; sp=self.server.speed
            self.lbl_ok.config(text=f"✓ 成功: {s['ok']}"); self.lbl_sk.config(text=f"⊙ 跳过: {s['skip']}")
            fc=s['fail']; self.lbl_fl.config(text=f"✗ 失败: {fc}",cursor='hand2' if fc>0 else 'arrow')
            self.lbl_ac.config(text=f"↓ 下载中: {s['active']}")
            self.lbl_sz.config(text=f"■ 大小: {fmt_size(s['sz'])}")
            self.lbl_sp.config(text=f"↻ 速度: {fmt_size(int(sp))}/s")
            if s['active']>0: self.pb.start(15)
            else: self.pb.stop()
            self.stm=self.root.after(300,self._upd_st)
        else: self.stm=None; self.pb.stop()
    def _pause(self):
        if not self.server: return
        self.server.paused=not self.server.paused
        if self.server.paused: self.btn_pause.config(text='▶ 继续'); self._log("⏸ 已暂停",'WARNING')
        else: self.btn_pause.config(text='⏸ 暂停'); self._log("▶ 已继续",'OK')
    def _retry(self):
        if not self._rdata: return messagebox.showinfo("提示","没有可重试的失败项。")
        self._log(f"🔄 重试 {len(self._rdata['failed'])} 项…"); self._set_busy()
        threading.Thread(target=self._do_retry,daemon=True).start()
    def _do_retry(self):
        for url,_ in self._rdata['failed']:
            try:
                r=requests.get(url,headers={'User-Agent':self.settings.get('user_agent','Mozilla/5.0')},timeout=10)
                r.raise_for_status(); data=r.content
                if self.cur_dir:
                    pp=urlparse(url); path=unquote(pp.path)
                    if not path or path=='/': path='/index.html'
                    d=os.path.dirname(path).lstrip('/'); fn=safe_filename(os.path.basename(path))
                    rel=os.path.join(d,fn) if d else fn; sf=os.path.join(self.cur_dir,rel)
                    if not os.path.splitext(sf)[1]:
                        ext=ext_from_ct(r.headers.get('Content-Type',''))
                        if ext: sf+=ext
                    os.makedirs(os.path.dirname(sf),exist_ok=True)
                    with open(sf,'wb') as f: f.write(data)
                    self._rdata['downloaded'][url]=rel
                    self.root.after(0,self._log,f" ✓ [重试] {os.path.basename(sf)}")
            except Exception as e:
                self.root.after(0,self._log,f" ✗ [重试] {url[:50]}: {e}",'ERROR')
        self._rdata=None; self.root.after(0,self._set_idle)
    def _batch_dlg(self):
        dlg=tk.Toplevel(self.root); dlg.title("批量下载"); dlg.geometry("500x400")
        dlg.transient(self.root); dlg.grab_set()
        ttk.Label(dlg,text="每行一个网址：",font=('',10)).pack(padx=10,pady=(10,5))
        txt=tk.Text(dlg,font=('Consolas',10),wrap='word'); txt.pack(fill=tk.BOTH,expand=True,padx=10,pady=5)
        self._mk_ctx(txt,it=True)
        bl=ttk.Label(dlg,text=""); bl.pack(padx=10,pady=2)
        bp=ttk.Progressbar(dlg,mode='determinate'); bp.pack(fill='x',padx=10,pady=(0,5))
        bf=ttk.Frame(dlg); bf.pack(pady=(0,10))
        def go():
            urls=[l.strip() for l in txt.get('1.0','end').splitlines() if l.strip() and l.strip().startswith(('http://','https://'))]
            if not urls: messagebox.showwarning("提示","请输入有效网址",parent=dlg); return
            for b in bf.winfo_children(): b.config(state='disabled'); txt.config(state='disabled')
            threading.Thread(target=self._do_batch,args=(urls,bl,bp),daemon=True).start()
        ttk.Button(bf,text="开始",command=go,width=12).pack(side='left',padx=5)
        ttk.Button(bf,text="关闭",command=dlg.destroy,width=8).pack(side='left',padx=5)
        x=self.root.winfo_x()+(self.root.winfo_width()-500)//2; y=self.root.winfo_y()+(self.root.winfo_height()-400)//2
        dlg.geometry(f'+{max(0,x)}+{max(0,y)}')
    def _do_batch(self,urls,bl,bp):
        t=len(urls)
        for i,url in enumerate(urls):
            try:
                self.root.after(0,bl.config,{"text":f"({i+1}/{t}) {url[:40]}…"})
                self.root.after(0,bp.config,{"value":(i+1)/t*100})
                r=requests.get(url,headers={'User-Agent':self.settings.get('user_agent','Mozilla/5.0'),'Accept':'text/html'},timeout=15)
                html=dec_utf8(r); fu=r.url; sd=os.path.join(self.base_dir,folder_name(fu)); os.makedirs(sd,exist_ok=True)
                rel=html_rel(fu); hp=os.path.join(sd,rel); os.makedirs(os.path.dirname(hp),exist_ok=True)
                with open(hp+'.raw','w',encoding='utf-8') as f: f.write(html)
                self._save_meta(sd,{'url':fu,'status':'html','ok':0,'fail':0,'sz':0,'rel':rel})
                self.root.after(0,self._log,f" ✓ [{i+1}/{t}] {fu[:50]}"); self.root.after(0,self._ref_list)
            except Exception as e: self.root.after(0,self._log,f" ✗ [{i+1}/{t}] {url[:40]}: {e}",'ERROR')
        self.root.after(0,bl.config,{"text":f"完成！共 {t} 个"})
    def _start(self):
        url=self.url_v.get().strip()
        if not url: return messagebox.showwarning("提示","请输入网址")
        if not url.startswith(('http://','https://')): url='https://'+url; self.url_v.set(url)
        bdir=self.dir_v.get().strip()
        if not bdir: return messagebox.showwarning("提示","请选择保存路径")
        if self.settings.get('clear_log_on_new',True): self._clr_log()
        self._reset_st(); self._log(f"目标: {url}"); self._set_busy()
        threading.Thread(target=self._dl_html,args=(url,bdir),daemon=True).start()
    def _dl_html(self,url,bdir):
        try:
            s=requests.Session()
            s.headers.update({'User-Agent':self.settings.get('user_agent','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),'Accept':'text/html,*/*;q=0.8'})
            self.root.after(0,self._log,"正在下载HTML…")
            r=s.get(url,timeout=15); html=dec_utf8(r); fu=r.url
            sd=os.path.join(bdir,folder_name(fu)); os.makedirs(sd,exist_ok=True)
            rel=html_rel(fu); hp=os.path.join(sd,rel); os.makedirs(os.path.dirname(hp),exist_ok=True)
            raw=hp+'.raw'; self.cur_url,self.cur_dir,self.cur_html=fu,sd,hp; self.cur_raw,self.cur_rel=raw,rel
            with open(raw,'w',encoding='utf-8') as f: f.write(html)
            self.root.after(0,self._save_meta,sd,{'url':fu,'status':'html','ok':0,'fail':0,'sz':0,'rel':rel})
            self.root.after(0,self._log,f"✓ HTML已保存 ({fmt_size(len(html))})")
            self.root.after(0,self._log,f" 目录: {sd}")
            self.root.after(0,self._ref_list); self.root.after(0,self._prompt)
        except Exception as e:
            self.root.after(0,self._log,f"✗ 下载失败: {e}",'ERROR'); self.root.after(0,self._set_idle)
    def _prompt(self):
        dlg=tk.Toplevel(self.root); dlg.title("提示"); dlg.resizable(False,False)
        dlg.transient(self.root); dlg.grab_set()
        ttk.Label(dlg,text="网页已下载完成",font=('',14,'bold')).pack(pady=(24,8))
        pp=urlparse(self.cur_url)
        h="\n📌 HTTP网站 — 同源劫持，Cookie/Session全保留！（需管理员权限）" if pp.scheme=='http' and not pp.port else "\n⚠️ HTTPS网站 — 兼容代理模式" if pp.scheme=='https' else ""
        port_info = f"\n🔧 代理端口: {self.settings.get('port',8899)}" if pp.scheme=='https' else ""
        ttk.Label(dlg,text=f"是否打开浏览器开始下载资源？{h}{port_info}",font=('',10),justify='center').pack(pady=(0,6))
        bf=ttk.Frame(dlg); bf.pack(pady=(8,24))
        ttk.Button(bf,text="确定",command=lambda:(dlg.destroy(),self.root.after(100,self._launch)),width=10).pack(side='left',padx=12)
        ttk.Button(bf,text="稍后",command=lambda:(dlg.destroy(),self.root.after(0,self._set_idle)),width=10).pack(side='left',padx=12)
        w,h=dlg.winfo_width(),dlg.winfo_height()
        dlg.geometry(f'+{self.root.winfo_x()+(self.root.winfo_width()-w)//2}+{self.root.winfo_y()+(self.root.winfo_height()-h)//2}')
        dlg.wait_window()
    def _launch(self): self._set_run(); threading.Thread(target=self._do_launch,daemon=True).start()
    def _do_launch(self):
        try:
            r=self._start_server(self.cur_url,self.cur_dir,self.cur_raw,self.cur_html,is_launch=True)
            if not r: self.root.after(0,self._set_idle)
        except Exception as e:
            self.root.after(0,self._log,f"✗ 启动失败: {e}",'ERROR'); self.root.after(0,self._set_idle)
    def _start_server(self, url, save_dir, raw_path, html_path, is_launch=False):
        ph=make_proxy(raw_path,url)
        with open(html_path,'w',encoding='utf-8') as f: f.write(ph)
        rel=os.path.relpath(html_path,save_dir).replace('\\','/')
        pp=urlparse(url); ok=False
        if pp.scheme=='http' and not pp.port:
            dom=pp.netloc
            if _inject(dom):
                self._hosts_dom=dom
                try:
                    self.server=ResServer(('0.0.0.0',80),url,save_dir,mode='hosts',domain=dom,settings=self.settings)
                    self._log("🌐 [同源劫持模式]",'OK'); ok=True
                except PermissionError:
                    self._log("⚠️ 80端口需管理员权限，降级兼容模式",'WARNING'); _clean(); self._hosts_dom=None; self.server=None
                except OSError as e:
                    self._log(f"⚠️ 80端口占用({e})，降级兼容模式",'WARNING'); _clean(); self._hosts_dom=None; self.server=None
            else: self._log("⚠️ Hosts写入失败，降级兼容模式",'WARNING'); self._hosts_dom=None
        if not ok:
            port=self.settings.get('port',8899)
            try:
                self.server=ResServer(('127.0.0.1',port),url,save_dir,mode='cors',settings=self.settings)
                self._log(f"🔄 [兼容代理模式] 端口: {port}",'WARNING')
            except OSError as e:
                self._log(f"⚠️ 端口 {port} 被占用({e})，请到设置中更换端口",'WARNING')
                self.server=None; return None
            except Exception as e:
                self._log(f"✗ 启动失败: {e}",'ERROR'); self.server=None; return None
        cnt,sz=self.server.load_cache()
        if cnt>0: self._log(f"📦 已恢复缓存: {cnt} 个资源 ({fmt_size(sz)})",'OK')
        else: self._log("📦 无缓存（首次打开或缓存为空）")
        if self.server.mode=='hosts': addr=f"http://{self.server.domain}/{rel}"
        else: addr=f"http://127.0.0.1:{self.server.server_address[1]}/{rel}"
        self._log(f" {addr}"); self._log("─"*50)
        self.server.on_log=lambda m,lv: self.root.after(0,self._log,m,lv)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        if is_launch: webbrowser.open(addr)
        self._set_run(); self.root.after(0,self._upd_st)
        return self.server,addr,rel
    def _open_proxy(self, it):
        url=it['url']; sd=it['dir']; hf=self._find_html(it)
        if not hf: return messagebox.showerror("错误","找不到HTML文件")
        raw=hf+'.raw'
        if not os.path.exists(raw): shutil.copy2(hf,raw)
        if self.settings.get('clear_log_on_new',True): self._clr_log()
        self._reset_st(); self._log(f"代理打开: {url}")
        try:
            r=self._start_server(url,sd,raw,hf,is_launch=True)
            if not r: self._set_idle()
        except Exception as e:
            self._log(f"✗ 启动失败: {e}",'ERROR'); self._set_idle()
    def _stop(self):
        if self.server: self.server.stop=True
        if self.stm: self.root.after_cancel(self.stm)
        self.root.after(300,self._do_stop)
    def _do_stop(self):
        if self.server:
            for _ in range(20):
                with self.server.lock:
                    if self.server.stats['active']==0: break
                time.sleep(0.1)
            cnt,sz=self.server.save_cache()
            if cnt>0: self._log(f"📦 已保存缓存: {cnt} 个资源 ({fmt_size(sz)})",'OK')
            else: self._log("📦 无需保存缓存")
        self._clean_hosts(); self._close_srv()
        self._log("─"*50); self._log("已停止"); self._set_idle()
    def _done(self):
        if not self.server: return
        self.root.after(0,self._log,"\n正在结束…"); self.server.stop=True
        if self.stm: self.root.after_cancel(self.stm); time.sleep(0.3)
        rmap=dict(self.server.downloaded); stats=dict(self.server.stats); failed=list(self.server.failed)
        self._clean_hosts(); self._close_srv()
        if self.cur_raw and os.path.exists(self.cur_raw): shutil.copy2(self.cur_raw,self.cur_html)
        self._log("─"*50)
        self._log(f"成功: {stats.get('ok',0)} | 跳过: {stats.get('skip',0)} | 失败: {stats.get('fail',0)} | 大小: {fmt_size(stats.get('sz',0))}")
        if failed:
            self._log("失败列表:")
            self._rdata={'failed':failed,'save_dir':self.cur_dir,'downloaded':rmap}
            for u,m in failed[:15]: self._log(f" ✗ {m}: {u[:70]}",'ERROR')
        else: self._rdata=None
        if self.repl_v.get() and rmap:
            sm={u:r for u,r in rmap.items()}
            for u in list(rmap.keys()):
                b=u.split('?')[0].split('#')[0]
                if b!=u and b not in sm: sm[b]=rmap[u]
            try:
                n=replace_paths(self.cur_html,self.cur_url,sm,self.cur_dir)
                self._log(f"✓ 已替换 {n} 个路径",'OK')
            except Exception as e: self._log(f"替换出错: {e}",'ERROR')
        self._log("─"*50)
        self._save_meta(self.cur_dir,{'url':self.cur_url,'status':'done','ok':stats.get('ok',0),'fail':stats.get('fail',0),'sz':stats.get('sz',0),'rel':self.cur_rel})
        self.server.clear_cache()
        self._ref_list(); self._set_idle()
    def _close_srv(self):
        if self.server:
            try: self.server.shutdown()
            except: pass
            self.server=None
    def run(self): self.root.mainloop()
if __name__=='__main__': App().run()
