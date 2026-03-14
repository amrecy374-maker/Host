# -*- coding: utf-8 -*-
# ============================================================
#  بوت استضافة متكامل — نسخة نهائية مدمجة
#  يشمل: زيكو + BCS + BoT5 + حماية Gemini
# ============================================================

import telebot
from telebot import types
import os, sys, re, ast, io, json, uuid, time, signal
import sqlite3, logging, threading, subprocess, traceback
import hashlib, zipfile, shutil, requests, atexit, random
import tempfile, importlib
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

# ============================================================
#  الإعدادات — غيّر هنا فقط
# ============================================================
TOKEN        = "8645478080:AAFvkKiemIpb17AV4GF-YpSZFmZ9_hEQqsQ"
DEVELOPER_ID = 8206539702
GEMINI_KEY   = "AIzaSyCGo9K-UuAqiYwBASiPMvfrbSheejF3aZ0"
developer    = "HJ_K6"   # يوزر المطور بدون @

# ============================================================
#  Gemini AI
# ============================================================
try:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)
    gemini_model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config={"temperature": 0.4, "top_p": 0.95,
                           "top_k": 64, "max_output_tokens": 8192,
                           "response_mime_type": "text/plain"}
    )
    GEMINI_AVAILABLE = True
except Exception:
    GEMINI_AVAILABLE = False

# ============================================================
#  Flask Keep-Alive
# ============================================================
app = Flask('')

@app.route('/')
def home():
    return "Hosting Bot — Running"

def keep_alive():
    t = Thread(target=lambda: app.run(host='0.0.0.0',
               port=int(os.environ.get("PORT", 8080))))
    t.daemon = True
    t.start()

# ============================================================
#  المجلدات والمسارات
# ============================================================
BASE_DIR           = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_FOLDER      = os.path.join(BASE_DIR, "uploaded_files")
PROJECTS_DIR       = os.path.join(BASE_DIR, "projects")
TOKENS_FOLDER      = os.path.join(BASE_DIR, "tokens_data")
HACK_FOLDER        = os.path.join(BASE_DIR, "hack_attempts")
PROTECTION_FOLDER  = os.path.join(BASE_DIR, "protection")
DB_FILE            = os.path.join(BASE_DIR, "hosting_bot.db")
PROTECTION_STATE   = os.path.join(PROTECTION_FOLDER, "state.json")

for _d in [UPLOAD_FOLDER, PROJECTS_DIR, TOKENS_FOLDER,
           HACK_FOLDER, PROTECTION_FOLDER]:
    os.makedirs(_d, exist_ok=True)

# ============================================================
#  لوجنج
# ============================================================
logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
#  البوت
# ============================================================
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ============================================================
#  أنماط الأمان
# ============================================================
HACK_PATTERNS = [
    (r"__import__\s*\(\s*['\"]os['\"]\s*\)",          "استيراد os ديناميكي",            10),
    (r"os\.system\s*\(|subprocess\.Popen\s*\(",        "استدعاء أوامر نظام",             9),
    (r"eval\s*\(|exec\s*\(",                           "eval/exec",                       8),
    (r"open\s*\(\s*['\"](/etc/passwd|/etc/shadow)",    "قراءة ملفات نظام حساسة",         10),
    (r"shutil\.rmtree\s*\(|os\.rmdir\s*\(",            "حذف مجلدات",                     9),
    (r"subprocess\.run\s*\(.*shell\s*=\s*True",        "shell=True",                      9),
    (r"os\.popen\s*\(|popen2\s*\(",                    "فتح عمليات نظام",                 8),
    (r"import\s+ctypes|import\s+paramiko",             "مكتبات نظام/شبكة خطيرة",         8),
    (r"pickle\.loads|pickle\.dump",                    "pickle خطير",                     7),
    (r"eval\(.*decode\(.*base64",                      "base64+eval",                    10),
    (r"__builtins__\s*\.|globals\s*\(|locals\s*\(",    "التلاعب بالبيئة التنفيذية",       8),
    (r"\.replace\s*\(\s*['\"]https://api.telegram",    "تغيير API تيليجرام",              8),
    (r"#.*bypass|#.*hack|#.*exploit",                  "تعليقات اختراق",                  5),
]

BLOCKED_LIBRARIES = [
    'ctypes','paramiko','ftplib','selenium','scrapy',
    'mechanize','webbrowser','pyautogui','pynput',
]

THREAT_PATTERNS = [
    r"eval\s*\(", r"exec\s*\(", r"__import__\s*\(",
    r"subprocess\.Popen\s*\(", r"os\.system\s*\(",
    r"shutil\.rmtree\s*\(", r"os\.remove\s*\(",
    r"while True:", r"fork\s*\(",
]

# ============================================================
#  قاعدة البيانات
# ============================================================
DB_LOCK = threading.Lock()

def db_execute(q, p=()):
    with DB_LOCK:
        conn = sqlite3.connect(DB_FILE, timeout=30)
        try:
            conn.execute(q, p)
            conn.commit()
        except Exception as e:
            logger.error(f"db_execute: {e}")
            raise
        finally:
            conn.close()

def db_fetchone(q, p=()):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    try:
        cur = conn.execute(q, p)
        return cur.fetchone()
    except Exception as e:
        logger.error(f"db_fetchone: {e}")
        return None
    finally:
        conn.close()

def db_fetchall(q, p=()):
    conn = sqlite3.connect(DB_FILE, timeout=30)
    try:
        cur = conn.execute(q, p)
        return cur.fetchall()
    except Exception as e:
        logger.error(f"db_fetchall: {e}")
        return []
    finally:
        conn.close()

def init_db():
    stmts = [
        # مستخدمون
        '''CREATE TABLE IF NOT EXISTS known_users
           (user_id INTEGER PRIMARY KEY, first_seen TEXT, last_seen TEXT)''',
        # ملفات
        '''CREATE TABLE IF NOT EXISTS files
           (id INTEGER PRIMARY KEY, filename TEXT, user_id INTEGER,
            upload_time TEXT, status TEXT, token TEXT, libraries TEXT,
            security_level TEXT, hack_score INTEGER DEFAULT 0,
            requires_approval INTEGER DEFAULT 0,
            approved_by INTEGER, approval_time TEXT, rejection_reason TEXT,
            folder_name TEXT)''',
        # أدمن
        '''CREATE TABLE IF NOT EXISTS admins
           (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_time TEXT)''',
        # محظورون
        '''CREATE TABLE IF NOT EXISTS banned_users
           (user_id INTEGER PRIMARY KEY, banned_by INTEGER,
            ban_time TEXT, reason TEXT)''',
        # محظورو الرفع
        '''CREATE TABLE IF NOT EXISTS blocked_uploads
           (user_id INTEGER PRIMARY KEY, blocked_by INTEGER,
            block_time TEXT, reason TEXT)''',
        # اشتراك إجباري
        '''CREATE TABLE IF NOT EXISTS force_subscribe
           (channel_id TEXT PRIMARY KEY, channel_username TEXT,
            added_by INTEGER, added_time TEXT)''',
        # إعدادات
        '''CREATE TABLE IF NOT EXISTS bot_settings
           (setting_key TEXT PRIMARY KEY, setting_value TEXT)''',
        # إعدادات أمان
        '''CREATE TABLE IF NOT EXISTS security_settings
           (setting_key TEXT PRIMARY KEY, setting_value TEXT, description TEXT)''',
        # VIP
        '''CREATE TABLE IF NOT EXISTS vip_users
           (user_id INTEGER PRIMARY KEY, activated_by INTEGER,
            activation_time TEXT, expiry_date TEXT, status TEXT)''',
        # PRO
        '''CREATE TABLE IF NOT EXISTS pro_users
           (user_id INTEGER PRIMARY KEY, activated_by INTEGER,
            activation_time TEXT, expiry_date TEXT, status TEXT)''',
        # نقاط
        '''CREATE TABLE IF NOT EXISTS users_points
           (user_id INTEGER PRIMARY KEY, points INTEGER DEFAULT 0,
            first_free_used INTEGER DEFAULT 0)''',
        # دعوات
        '''CREATE TABLE IF NOT EXISTS referral_links
           (id INTEGER PRIMARY KEY, user_id INTEGER, code TEXT UNIQUE,
            created_at TEXT, points_per_ref INTEGER DEFAULT 2, uses INTEGER DEFAULT 0)''',
        '''CREATE TABLE IF NOT EXISTS referrals
           (id INTEGER PRIMARY KEY, referrer_id INTEGER, referred_id INTEGER,
            code TEXT, time TEXT)''',
        # هدايا
        '''CREATE TABLE IF NOT EXISTS gift_codes
           (id INTEGER PRIMARY KEY, code TEXT UNIQUE, creator_id INTEGER,
            points INTEGER, max_uses INTEGER, used_count INTEGER DEFAULT 0,
            expires_at TEXT)''',
        # أسعار
        '''CREATE TABLE IF NOT EXISTS prices
           (price_type TEXT PRIMARY KEY, price_value INTEGER DEFAULT 0)''',
        # محاولات اختراق
        '''CREATE TABLE IF NOT EXISTS hack_attempts
           (id INTEGER PRIMARY KEY, user_id INTEGER, filename TEXT,
            hack_score INTEGER, detection_time TEXT, patterns_found TEXT,
            action_taken TEXT)''',
        # إشعارات أدمن
        '''CREATE TABLE IF NOT EXISTS admin_notifications
           (id INTEGER PRIMARY KEY, notification_type TEXT, user_id INTEGER,
            filename TEXT, details TEXT, notification_time TEXT,
            status TEXT DEFAULT 'pending', admin_action TEXT, action_time TEXT)''',
        # ملفات انتظار موافقة (نظام زيكو)
        '''CREATE TABLE IF NOT EXISTS pending_files
           (file_id TEXT PRIMARY KEY, user_id INTEGER, file_name TEXT,
            original_file_id TEXT, upload_time TEXT)''',
        # معاملات نقاط
        '''CREATE TABLE IF NOT EXISTS points_transactions
           (id INTEGER PRIMARY KEY, user_id INTEGER, admin_id INTEGER,
            amount INTEGER, transaction_type TEXT, reason TEXT, transaction_time TEXT)''',
        # رسائل البوت
        '''CREATE TABLE IF NOT EXISTS bot_messages
           (user_id INTEGER, message_type TEXT, chat_id INTEGER,
            message_id INTEGER, timestamp TEXT,
            PRIMARY KEY(user_id, message_type))''',
    ]
    for s in stmts:
        db_execute(s)

    # إعدادات افتراضية
    defaults = [
        ('bot_status',            'enabled'),
        ('paid_mode',             'disabled'),
        ('ai_security',           'enabled'),
        ('auto_block_hackers',    'enabled'),
        ('hack_score_threshold',  '15'),
        ('upload_price',          '0'),
        ('referral_price',        '2'),
    ]
    for k, v in defaults:
        db_execute("INSERT OR IGNORE INTO bot_settings (setting_key,setting_value) VALUES (?,?)", (k, v))

    sec_defaults = [
        ('max_file_size',       '10240',           'الحجم الأقصى KB'),
        ('allowed_file_types',  'py,zip',          'الأنواع المسموحة'),
        ('auto_install_libs',   'true',            'تثبيت تلقائي للمكتبات'),
        ('auto_fix_files',      'false',           'إصلاح تلقائي'),
        ('vip_mode',            'false',           'وضع VIP'),
    ]
    for k, v, d in sec_defaults:
        db_execute("INSERT OR IGNORE INTO security_settings (setting_key,setting_value,description) VALUES (?,?,?)", (k, v, d))

    price_defaults = [('upload_price', 0), ('referral_price', 2)]
    for pt, pv in price_defaults:
        db_execute("INSERT OR IGNORE INTO prices (price_type,price_value) VALUES (?,?)", (pt, pv))

    # إضافة DEVELOPER_ID كأدمن
    db_execute("INSERT OR IGNORE INTO admins (user_id,added_by,added_time) VALUES (?,?,?)",
               (DEVELOPER_ID, DEVELOPER_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    logger.info("✅ قاعدة البيانات جاهزة")

init_db()

# ============================================================
#  دوال الإعدادات
# ============================================================
def get_setting(key, default=''):
    r = db_fetchone("SELECT setting_value FROM bot_settings WHERE setting_key=?", (key,))
    return r[0] if r else default

def get_sec_setting(key, default=''):
    r = db_fetchone("SELECT setting_value FROM security_settings WHERE setting_key=?", (key,))
    return r[0] if r else default

def bot_enabled():      return get_setting('bot_status') == 'enabled'
def is_paid_mode():     return get_setting('paid_mode')  == 'enabled'
def ai_enabled():       return get_setting('ai_security') == 'enabled'
def auto_block():       return get_setting('auto_block_hackers') == 'enabled'
def hack_threshold():
    try:    return int(get_setting('hack_score_threshold', '15'))
    except: return 15

# ============================================================
#  دوال الصلاحيات
# ============================================================
def is_admin(uid):
    r = db_fetchone("SELECT user_id FROM admins WHERE user_id=?", (uid,))
    return r is not None or uid == DEVELOPER_ID

def is_vip(uid):
    r = db_fetchone("SELECT user_id FROM vip_users WHERE user_id=? AND status='active'", (uid,))
    return r is not None

def is_pro(uid):
    r = db_fetchone("SELECT user_id FROM pro_users WHERE user_id=? AND status='active'", (uid,))
    return r is not None

def is_banned(uid):
    return db_fetchone("SELECT user_id FROM banned_users WHERE user_id=?", (uid,)) is not None

def is_upload_blocked(uid):
    return db_fetchone("SELECT user_id FROM blocked_uploads WHERE user_id=?", (uid,)) is not None

def ban_user(uid, banned_by=None, reason="محظور"):
    db_execute("INSERT OR IGNORE INTO banned_users (user_id,banned_by,ban_time,reason) VALUES (?,?,?,?)",
               (uid, banned_by or DEVELOPER_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reason))

def unban_user(uid):
    db_execute("DELETE FROM banned_users WHERE user_id=?", (uid,))

def block_uploads(uid, by=None, reason="محظور من رفع الملفات"):
    db_execute("INSERT OR IGNORE INTO blocked_uploads (user_id,blocked_by,block_time,reason) VALUES (?,?,?,?)",
               (uid, by or DEVELOPER_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reason))

def unblock_uploads(uid):
    db_execute("DELETE FROM blocked_uploads WHERE user_id=?", (uid,))

# ============================================================
#  الاشتراك الإجباري
# ============================================================
def check_subscription(uid):
    if is_admin(uid):
        return True
    channels = db_fetchall("SELECT channel_id, channel_username FROM force_subscribe")
    if not channels:
        return True
    for cid, cusr in channels:
        targets = [t for t in [cid, cusr, cusr.lstrip('@') if cusr else None] if t]
        ok = False
        for t in targets:
            try:
                m = bot.get_chat_member(t, uid)
                if getattr(m, 'status', '') in ['member','administrator','creator']:
                    ok = True; break
            except: continue
        if not ok:
            return False
    return True

def get_sub_markup():
    channels = db_fetchall("SELECT channel_id, channel_username FROM force_subscribe")
    markup = types.InlineKeyboardMarkup()
    for cid, cusr in channels:
        if cusr:
            u = cusr.lstrip('@')
            markup.add(types.InlineKeyboardButton(f"📢 @{u}", url=f"https://t.me/{u}"))
    markup.add(types.InlineKeyboardButton("✅ تحقق", callback_data="check_sub"))
    return markup

# ============================================================
#  المستخدمون والنقاط
# ============================================================
def register_user(uid, first_name, username, payload=None):
    existing = db_fetchone("SELECT user_id FROM known_users WHERE user_id=?", (uid,))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not existing:
        db_execute("INSERT INTO known_users (user_id,first_seen,last_seen) VALUES (?,?,?)", (uid, now, now))
        db_execute("INSERT OR IGNORE INTO users_points (user_id,points,first_free_used) VALUES (?,0,0)", (uid,))
        if payload:
            if payload.startswith("ref_"):
                ok, msg = process_referral(payload[4:], uid)
                try: bot.send_message(uid, f"<pre>{msg}</pre>")
                except: pass
            elif payload.startswith("gift_"):
                ok, msg = redeem_gift(payload[5:], uid)
                try: bot.send_message(uid, f"<pre>{msg}</pre>")
                except: pass
        try:
            uinfo = f"@{username}" if username else f"{first_name} ({uid})"
            bot.send_message(DEVELOPER_ID,
                f"<pre>👤 مستخدم جديد!\n• {uinfo}\n• ID: {uid}\n• {now}</pre>")
        except: pass
    else:
        db_execute("UPDATE known_users SET last_seen=? WHERE user_id=?", (now, uid))

def get_points(uid):
    db_execute("INSERT OR IGNORE INTO users_points (user_id,points,first_free_used) VALUES (?,0,0)", (uid,))
    r = db_fetchone("SELECT points FROM users_points WHERE user_id=?", (uid,))
    return r[0] if r else 0

def add_points(uid, amount, admin_id=None, reason=None):
    db_execute("INSERT OR IGNORE INTO users_points (user_id,points,first_free_used) VALUES (?,0,0)", (uid,))
    if admin_id:
        db_execute("INSERT INTO points_transactions (user_id,admin_id,amount,transaction_type,reason,transaction_time) VALUES (?,?,?,'add',?,?)",
                   (uid, admin_id, amount, reason or 'إضافة', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db_execute("UPDATE users_points SET points=points+? WHERE user_id=?", (amount, uid))
    return get_points(uid)

def deduct_points(uid, amount, admin_id=None, reason=None):
    pts = get_points(uid)
    if pts < amount:
        return False, "رصيد غير كافٍ"
    if admin_id:
        db_execute("INSERT INTO points_transactions (user_id,admin_id,amount,transaction_type,reason,transaction_time) VALUES (?,?,?,'deduct',?,?)",
                   (uid, admin_id, amount, reason or 'خصم', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db_execute("UPDATE users_points SET points=points-? WHERE user_id=?", (amount, uid))
    return True, f"تم خصم {amount} نقطة"

def spend_points(uid, amount):
    ok, _ = deduct_points(uid, amount)
    return ok

def get_price(t):
    r = db_fetchone("SELECT price_value FROM prices WHERE price_type=?", (t,))
    return int(r[0]) if r else 0

def generate_referral(uid):
    code = uuid.uuid4().hex[:8]
    db_execute("INSERT OR IGNORE INTO referral_links (user_id,code,created_at,points_per_ref,uses) VALUES (?,?,?,?,0)",
               (uid, code, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), get_price('referral_price')))
    r = db_fetchone("SELECT code FROM referral_links WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,))
    return r[0] if r else code

def process_referral(code, new_uid):
    r = db_fetchone("SELECT user_id,points_per_ref FROM referral_links WHERE code=?", (code,))
    if not r: return False, "كود غير صالح"
    ref_uid, pts = r
    if ref_uid == new_uid: return False, "لا يمكنك دعوة نفسك"
    ex = db_fetchone("SELECT id FROM referrals WHERE referrer_id=? AND referred_id=?", (ref_uid, new_uid))
    if ex: return False, "تم استخدام هذه الدعوة مسبقاً"
    add_points(ref_uid, pts)
    db_execute("INSERT INTO referrals (referrer_id,referred_id,code,time) VALUES (?,?,?,?)",
               (ref_uid, new_uid, code, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db_execute("UPDATE referral_links SET uses=uses+1 WHERE code=?", (code,))
    return True, f"تم منح {pts} نقطة للمُحيل"

def redeem_gift(code, uid):
    r = db_fetchone("SELECT id,points,max_uses,used_count,expires_at FROM gift_codes WHERE code=?", (code,))
    if not r: return False, "كود غير موجود"
    gid, pts, max_u, used, exp = r
    if max_u and used >= max_u: return False, "انتهت صلاحيات الكود"
    if exp:
        try:
            if datetime.now() > datetime.strptime(exp, "%Y-%m-%d %H:%M:%S"):
                return False, "انتهى تاريخ الصلاحية"
        except: pass
    add_points(uid, pts)
    db_execute("UPDATE gift_codes SET used_count=used_count+1 WHERE id=?", (gid,))
    return True, f"✅ تمت إضافة {pts} نقطة"

# ============================================================
#  تشغيل الملفات
# ============================================================
running_processes = {}

def run_file(file_path, uid, file_name):
    key = f"{uid}_{file_name}"
    try:
        # تثبيت requirements إن وجد
        req = os.path.join(os.path.dirname(file_path), 'requirements.txt')
        if os.path.exists(req):
            subprocess.Popen([sys.executable, '-m', 'pip', 'install', '-r', req])

        log_path = os.path.join(os.path.dirname(file_path),
                                f"{os.path.splitext(file_name)[0]}.log")
        log_f = open(log_path, 'w', encoding='utf-8', errors='ignore')
        proc = subprocess.Popen(
            [sys.executable, file_path],
            cwd=os.path.dirname(file_path),
            stdout=log_f, stderr=log_f,
            stdin=subprocess.PIPE
        )
        running_processes[key] = {'process': proc, 'log': log_f,
                                   'file_name': file_name, 'uid': uid,
                                   'start': datetime.now()}
        logger.info(f"▶️ تشغيل {key} PID={proc.pid}")
        return True, proc.pid
    except Exception as e:
        logger.error(f"run_file: {e}")
        return False, str(e)

def stop_file(uid, file_name):
    key = f"{uid}_{file_name}"
    info = running_processes.get(key)
    if not info:
        return False, "الملف لا يعمل"
    try:
        proc = info['process']
        try:
            import psutil
            parent = psutil.Process(proc.pid)
            for c in parent.children(recursive=True):
                c.terminate()
            parent.terminate()
            parent.wait(timeout=3)
        except Exception:
            proc.terminate()
        lf = info.get('log')
        if lf and not lf.closed:
            lf.close()
        del running_processes[key]
        db_execute("UPDATE files SET status='stopped' WHERE filename=? AND user_id=?",
                   (file_name, uid))
        return True, "✅ تم الإيقاف"
    except Exception as e:
        return False, str(e)

def is_running(uid, file_name):
    key = f"{uid}_{file_name}"
    info = running_processes.get(key)
    if not info: return False
    try:
        import psutil
        p = psutil.Process(info['process'].pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except: return False

# ============================================================
#  استخراج التوكن
# ============================================================
def extract_token(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        for pat in [
            r'telebot\.TeleBot\(["\']([^"\']+)["\']\)',
            r'TOKEN\s*=\s*["\']([^"\']+)["\']',
            r'["\']([0-9]{8,10}:[a-zA-Z0-9_-]{35})["\']'
        ]:
            m = re.search(pat, content)
            if m: return m.group(1)
    except: pass
    return None

def validate_token(token):
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=8)
        return r.status_code == 200
    except: return False

# ============================================================
#  تحليل الأمان (محلي + Gemini)
# ============================================================
def analyze_hack(content, filename, uid):
    score = 0
    patterns_found = []
    details = []
    for pat, desc, s in HACK_PATTERNS:
        if re.search(pat, content, re.IGNORECASE | re.MULTILINE):
            score += s
            patterns_found.append(desc)
            details.append(f"• {desc} (+{s})")
    for lib in BLOCKED_LIBRARIES:
        if re.search(rf'^\s*import\s+{lib}|^\s*from\s+{lib}\s+import', content, re.MULTILINE):
            score += 8
            patterns_found.append(f"مكتبة محظورة: {lib}")
    if score >= 25:   lvl = "🚨 خطير جداً"; needs_approval = True
    elif score >= 15: lvl = "⚠️ خطير";       needs_approval = True
    elif score >= 8:  lvl = "🔶 مشتبه به";   needs_approval = True
    else:             lvl = "✅ آمن";         needs_approval = False
    if score >= hack_threshold():
        try:
            db_execute("INSERT INTO hack_attempts (user_id,filename,hack_score,detection_time,patterns_found,action_taken) VALUES (?,?,?,?,?,?)",
                       (uid, filename, score, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        " | ".join(patterns_found[:10]), "كشف تلقائي"))
        except: pass
    return {'score': score, 'level': lvl, 'needs_approval': needs_approval,
            'patterns': patterns_found, 'details': details}

def analyze_with_gemini(content_bytes, file_info_path):
    """فحص إضافي بـ Gemini — يرجع (is_safe, message)"""
    if not GEMINI_AVAILABLE:
        return True, "✅ Gemini غير متاح — تم قبول الملف محلياً"
    result = [True, "✅ Gemini: تم قبول الملف"]
    def _run():
        try:
            lines = content_bytes.decode('utf-8', errors='ignore').splitlines()
            lines = [l for l in lines if l.strip()]
            if not lines:
                result[0], result[1] = False, "❌ الملف فارغ"; return
            first50 = "\n".join(lines[:50])  # 50 سطر فقط لتوفير الذاكرة
            chat = gemini_model.start_chat(history=[
                {"role": "user",  "parts": ["Analyze code. Reply ONLY: safe OR no"]},
                {"role": "model", "parts": ["ok"]}
            ])
            res = chat.send_message(f"analyze:\n{first50}").text.strip().lower()
            if res != "safe":
                result[0], result[1] = False, "⚠️ Gemini: الملف يحتوي على كود خطير"
            else:
                result[0], result[1] = True, "✅ Gemini: الملف آمن"
        except Exception as e:
            logger.error(f"Gemini: {e}")
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=10)  # انتظر 10 ثواني بحد أقصى
    if t.is_alive():
        logger.warning("Gemini timeout — تم تجاهله")
        return True, "✅ Gemini: انتهت المهلة — تم قبول الملف"
    return result[0], result[1]

def full_security_check(content_bytes, filename, uid):
    """فحص شامل: محلي + Gemini — يرجع (is_safe, report_text, hack_result)"""
    content_str = content_bytes.decode('utf-8', errors='ignore')

    # نتائج مشتركة
    results = {}

    def run_local():
        results['hack'] = analyze_hack(content_str, filename, uid)
        try:    ast.parse(content_str); results['syntax'] = True
        except: results['syntax'] = False

    def run_gemini():
        results['gem_safe'], results['gem_msg'] = analyze_with_gemini(content_bytes, filename)

    # تشغيل الفحصين بالتوازي — بحد أقصى 15 ثانية
    t1 = threading.Thread(target=run_local, daemon=True)
    t2 = threading.Thread(target=run_gemini, daemon=True)
    t1.start(); t2.start()
    t1.join(timeout=8)
    t2.join(timeout=12)

    # قيم افتراضية إذا انتهت المهلة
    hack      = results.get('hack') or analyze_hack(content_str, filename, uid)
    syntax_ok = results.get('syntax', True)
    gem_safe  = results.get('gem_safe', True)
    gem_msg   = results.get('gem_msg', "✅ Gemini: انتهت المهلة")

    # القرار النهائي
    if hack['score'] >= hack_threshold() or not gem_safe:
        is_safe = False
    else:
        is_safe = syntax_ok or True  # نقبل حتى مع أخطاء syntax بسيطة
    report = (
        f"<pre>🛡️ تقرير الأمان\n\n"
        f"• الملف: {filename}\n"
        f"• درجة الخطر (محلي): {hack['score']}\n"
        f"• مستوى الأمان: {hack['level']}\n"
        f"• Gemini: {gem_msg}\n"
        f"• Syntax: {'✅' if syntax_ok else '❌ خطأ'}\n"
    )
    if hack['details']:
        report += "\n⚠️ الأنماط المكتشفة:\n" + "\n".join(hack['details'][:5])
    report += "</pre>"
    return is_safe, report, hack

# ============================================================
#  معالجة ZIP
# ============================================================
def extract_zip(zip_path, uid):
    extract_dir = os.path.join(UPLOAD_FOLDER, f"zip_{uid}_{int(time.time())}")
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_dir)
    py_files = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.endswith('.py'):
                py_files.append(os.path.join(root, f))
    return py_files, extract_dir

# ============================================================
#  إشعار الأدمن باختراق
# ============================================================
def notify_admin_hack(uid, filename, hack):
    try:
        patterns_txt = "\n".join([f"• {p}" for p in hack['patterns'][:5]])
        msg = (
            f"🚨 <b>تنبيه اختراق!</b>\n\n"
            f"📄 الملف: <code>{filename}</code>\n"
            f"👤 المستخدم: <code>{uid}</code>\n"
            f"📊 درجة الخطر: {hack['score']}\n"
            f"🔒 المستوى: {hack['level']}\n\n"
            f"⚠️ الأنماط:\n{patterns_txt}"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ قبول", callback_data=f"admin_accept:{filename}:{uid}"),
            types.InlineKeyboardButton("❌ رفض",  callback_data=f"admin_reject:{filename}:{uid}")
        )
        markup.add(
            types.InlineKeyboardButton("⛔ حظر المستخدم", callback_data=f"admin_ban:{uid}:hack")
        )
        bot.send_message(DEVELOPER_ID, msg, reply_markup=markup)
    except Exception as e:
        logger.error(f"notify_admin_hack: {e}")

# ============================================================
#  اللوحات
# ============================================================
def main_panel(uid):
    mk = types.InlineKeyboardMarkup(row_width=2)
    status = "⭐ VIP" if is_vip(uid) else ("🚀 PRO" if is_pro(uid) else "👤 عادي")
    mk.add(
        types.InlineKeyboardButton("📤 رفع ملف (PY/ZIP)", callback_data="upload"),
        types.InlineKeyboardButton(f"حالتي: {status}",    callback_data="my_status")
    )
    mk.add(
        types.InlineKeyboardButton("📂 ملفاتي",  callback_data="list_files"),
        types.InlineKeyboardButton("💎 نقاطي",   callback_data="points")
    )
    mk.add(
        types.InlineKeyboardButton("🎁 الهدايا", callback_data="gifts"),
        types.InlineKeyboardButton("🔗 دعوة",    callback_data="referral")
    )
    mk.add(
        types.InlineKeyboardButton("ℹ️ مساعدة",  callback_data="help"),
        types.InlineKeyboardButton("👨‍💻 المطور", url=f"https://t.me/{developer}")
    )
    if is_admin(uid):
        mk.add(types.InlineKeyboardButton("🛠️ لوحة الأدمن", callback_data="admin_panel"))
    return mk

def admin_panel_markup():
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton("📊 الإحصائيات",      callback_data="adm_stats"),
        types.InlineKeyboardButton("👥 المستخدمون",       callback_data="adm_users")
    )
    mk.add(
        types.InlineKeyboardButton("📁 الملفات",          callback_data="adm_files"),
        types.InlineKeyboardButton("📢 بث رسالة",         callback_data="adm_broadcast")
    )
    mk.add(
        types.InlineKeyboardButton("⭐ VIP/PRO",          callback_data="adm_vip"),
        types.InlineKeyboardButton("🎁 إنشاء هدية",      callback_data="adm_gift")
    )
    mk.add(
        types.InlineKeyboardButton("➕ نقاط",             callback_data="adm_add_pts"),
        types.InlineKeyboardButton("➖ خصم نقاط",         callback_data="adm_deduct_pts")
    )
    mk.add(
        types.InlineKeyboardButton("⛔ حظر مستخدم",      callback_data="adm_ban"),
        types.InlineKeyboardButton("✅ فك حظر",           callback_data="adm_unban")
    )
    mk.add(
        types.InlineKeyboardButton("🚫 منع رفع",          callback_data="adm_block_upload"),
        types.InlineKeyboardButton("📤 فك منع رفع",       callback_data="adm_unblock_upload")
    )
    mk.add(
        types.InlineKeyboardButton("📢 قنوات إجبارية",   callback_data="adm_channels"),
        types.InlineKeyboardButton("🚨 سجل الاختراقات",  callback_data="adm_hack_logs")
    )
    mk.add(
        types.InlineKeyboardButton("🔒 تعطيل البوت",     callback_data="adm_toggle_bot"),
        types.InlineKeyboardButton("💵 وضع مدفوع",       callback_data="adm_toggle_paid")
    )
    mk.add(
        types.InlineKeyboardButton("🔑 تغيير التوكن",    callback_data="adm_change_token"),
        types.InlineKeyboardButton("🪪 تغيير الأيدي",    callback_data="adm_change_devid")
    )
    mk.add(
        types.InlineKeyboardButton("🔄 تحديث البوت",     callback_data="adm_update_bot"),
        types.InlineKeyboardButton("✉️ رسالة لمستخدم",  callback_data="adm_msg_user")
    )
    mk.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    return mk

def file_panel(filename, uid):
    running = is_running(uid, filename)
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton("⏸ إيقاف" if running else "▶️ تشغيل",
                                   callback_data=f"toggle_{filename}"),
        types.InlineKeyboardButton("🗑 حذف", callback_data=f"del_{filename}")
    )
    mk.add(
        types.InlineKeyboardButton("🔁 تغيير التوكن", callback_data=f"chtoken_{filename}"),
        types.InlineKeyboardButton("📥 تنزيل",        callback_data=f"download_{filename}")
    )
    mk.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="list_files"))
    return mk

# ============================================================
#  رسالة الترحيب
# ============================================================
WELCOME = (
    "╔══════════════════════╗\n"
    "       🚀 <b>بوت الاستضافة</b> 🚀\n"
    "╚══════════════════════╝\n\n"
    "مرحباً بك في أقوى بوت استضافة! 🎉\n\n"
    "⚡ <b>مميزاتنا:</b>\n"
    "┣ 📤 رفع وتشغيل ملفات <code>Python</code> و <code>ZIP</code>\n"
    "┣ 💎 نظام نقاط ودعوات وهدايا\n"
    "┣ 🛡️ حماية <b>AI</b> متقدمة بـ Gemini\n"
    "┣ 👑 مستويات: عادي | VIP | PRO\n"
    "┗ ⏱️ تشغيل مستمر <b>24/7</b>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "👇 اختر من القائمة أدناه"
)

# ============================================================
#  /start
# ============================================================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid = message.from_user.id
    payload = message.text.split()[1] if len(message.text.split()) > 1 else None

    if is_banned(uid):
        r = db_fetchone("SELECT reason FROM banned_users WHERE user_id=?", (uid,))
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("📨 طلب فك الحظر", callback_data=f"req_unban:{uid}"))
        bot.send_message(uid,
            "🚫 <b>تم حظرك من البوت</b>\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"📋 <b>السبب:</b> <code>{r[0] if r else 'غير محدد'}</code>\n"
            "━━━━━━━━━━━━━━━\n"
            "يمكنك طلب فك الحظر من الزر أدناه 👇",
            reply_markup=mk)
        return

    register_user(uid, message.from_user.first_name,
                  message.from_user.username, payload)

    if not bot_enabled():
        bot.send_message(uid,
            "⚙️ <b>البوت في وضع الصيانة</b>\n\n"
            "🔧 نعمل على تحسين الخدمة\n"
            "⏳ يرجى المحاولة لاحقاً"); return

    if is_paid_mode() and not is_admin(uid):
        bot.send_message(uid,
            "💎 <b>البوت في الوضع المدفوع</b>\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"📩 للاشتراك تواصل مع: @{developer}\n"
            "━━━━━━━━━━━━━━━"); return

    if not check_subscription(uid):
        bot.send_message(uid,
            "📢 <b>الاشتراك الإجباري</b>\n\n"
            "يجب الاشتراك في القنوات التالية\nللاستمرار في استخدام البوت 👇",
            reply_markup=get_sub_markup()); return

    bot.send_message(uid, WELCOME, reply_markup=main_panel(uid))

# ============================================================
#  /admin
# ============================================================
@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    uid = message.from_user.id
    if not is_admin(uid):
        bot.send_message(uid, "<pre>🚫 لا تمتلك صلاحيات</pre>"); return
    bot.send_message(uid, "<pre>🛠️ لوحة تحكم الأدمن</pre>",
                     reply_markup=admin_panel_markup())

# ============================================================
#  /help
# ============================================================
@bot.message_handler(commands=['help'])
def cmd_help(message):
    bot.send_message(message.chat.id, """<pre>
📋 الأوامر:
/start  — القائمة الرئيسية
/admin  — لوحة الأدمن
/help   — هذه الرسالة

📤 ارفع ملف .py أو .zip مباشرة للبوت
</pre>""")

# ============================================================
#  رفع الملفات — handler وحيد
# ============================================================
@bot.message_handler(content_types=['document'])
def handle_document(message):
    threading.Thread(target=_handle_document_worker, args=(message,), daemon=True).start()

def _handle_document_worker(message):
    uid     = message.from_user.id
    chat_id = message.chat.id

    # فحوصات أولية
    if is_banned(uid):
        bot.reply_to(message, "<pre>⛔ أنت محظور</pre>"); return
    if is_upload_blocked(uid):
        r = db_fetchone("SELECT reason FROM blocked_uploads WHERE user_id=?", (uid,))
        bot.reply_to(message, f"<pre>🚫 محظور من رفع الملفات\nالسبب: {r[0] if r else ''}</pre>"); return
    if not bot_enabled():
        bot.reply_to(message, "<pre>🚫 البوت معطل</pre>"); return
    if is_paid_mode() and not is_admin(uid):
        bot.reply_to(message, f"<pre>💵 البوت مدفوع\nتواصل: @{developer}</pre>"); return
    if not check_subscription(uid):
        bot.reply_to(message, "<pre>📢 اشترك أولاً</pre>",
                     reply_markup=get_sub_markup()); return

    file_name = message.document.file_name
    file_ext  = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''
    allowed   = (get_sec_setting('allowed_file_types', 'py,zip')).split(',')

    if file_ext not in allowed:
        bot.reply_to(message, f"<pre>❌ نوع غير مسموح\nالمسموح: {', '.join(allowed)}</pre>"); return

    # خصم نقاط إن وجد سعر
    price = get_price('upload_price')
    if price > 0 and not is_admin(uid) and not is_vip(uid) and not is_pro(uid):
        if not spend_points(uid, price):
            bot.reply_to(message, f"<pre>❌ تحتاج {price} نقطة\nرصيدك: {get_points(uid)}</pre>"); return

    prog = bot.reply_to(message, f"<pre>📤 جاري رفع الملف...</pre>")

    try:
        file_info   = bot.get_file(message.document.file_id)
        downloaded  = bot.download_file(file_info.file_path)

        # تأكد من اسم فريد
        save_name = file_name
        save_path = os.path.join(UPLOAD_FOLDER, save_name)
        c = 1
        while os.path.exists(save_path):
            n, e = os.path.splitext(file_name)
            save_name = f"{n}_{c}{e}"; c += 1
            save_path = os.path.join(UPLOAD_FOLDER, save_name)

        with open(save_path, 'wb') as f:
            f.write(downloaded)

        # ===== ZIP =====
        if file_ext == 'zip':
            bot.edit_message_text("<pre>📦 استخراج ZIP وفحصه...</pre>",
                                  chat_id, prog.message_id)
            try:
                py_files, _ = extract_zip(save_path, uid)
            except Exception as ze:
                bot.edit_message_text(f"<pre>❌ فشل فك الضغط: {ze}</pre>",
                                      chat_id, prog.message_id); return
            if not py_files:
                bot.edit_message_text("<pre>❌ لا يحتوي ZIP على ملفات .py</pre>",
                                      chat_id, prog.message_id); return

            results = ""
            for pf in py_files:
                pname = os.path.basename(pf)
                with open(pf, 'rb') as f:
                    pbytes = f.read()
                is_safe, sec_report, hack = full_security_check(pbytes, pname, uid)
                token = extract_token(pf)
                db_execute("INSERT OR IGNORE INTO files (filename,user_id,upload_time,status,token,security_level,hack_score,requires_approval) VALUES (?,?,?,?,?,?,?,?)",
                           (pname, uid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'pending' if not is_safe else 'stopped',
                            token, hack['level'], hack['score'],
                            1 if not is_safe else 0))
                if not is_safe:
                    notify_admin_hack(uid, pname, hack)
                    results += f"⚠️ {pname} — يتطلب موافقة\n"
                else:
                    ok, pid = run_file(pf, uid, pname)
                    if ok:
                        db_execute("UPDATE files SET status='active' WHERE filename=? AND user_id=?",
                                   (pname, uid))
                    results += f"{'✅' if ok else '❌'} {pname}\n"
            bot.edit_message_text(f"<pre>📦 نتائج ZIP:\n\n{results}</pre>",
                                  chat_id, prog.message_id)
            return

        # ===== PY =====
        bot.edit_message_text("<pre>🔍 فحص أمني...</pre>", chat_id, prog.message_id)
        is_safe, sec_report, hack = full_security_check(downloaded, save_name, uid)
        token = extract_token(save_path)

        # عرض تقرير للمستخدم دائماً
        bot.edit_message_text(sec_report, chat_id, prog.message_id)

        db_execute("INSERT OR IGNORE INTO files (filename,user_id,upload_time,status,token,security_level,hack_score,requires_approval) VALUES (?,?,?,?,?,?,?,?)",
                   (save_name, uid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'pending' if not is_safe else 'stopped',
                    token, hack['level'], hack['score'],
                    1 if not is_safe else 0))

        if not is_safe:
            # خطير جداً — رفض تلقائي + حظر عند الضرورة
            if hack['score'] >= 25 and auto_block():
                db_execute("UPDATE files SET status='rejected' WHERE filename=? AND user_id=?",
                           (save_name, uid))
                bot.send_message(uid, "<pre>🚫 تم رفض الملف تلقائياً بسبب خطر عالٍ</pre>")
                if hack['score'] >= 30:
                    ban_user(uid, DEVELOPER_ID, f"محاولة اختراق: {save_name}")
                    bot.send_message(uid, "<pre>⛔ تم حظرك من البوت</pre>")
            else:
                bot.send_message(uid,
                    "<pre>⏳ الملف في انتظار مراجعة الأدمن\nسيتم إعلامك بالقرار</pre>")
            notify_admin_hack(uid, save_name, hack)
            return

        # ===== تشغيل =====
        ok, pid = run_file(save_path, uid, save_name)
        if ok:
            db_execute("UPDATE files SET status='active' WHERE filename=? AND user_id=?",
                       (save_name, uid))
            bot.send_message(uid,
                f"<pre>✅ تم رفع وتشغيل الملف!\n\n"
                f"• الاسم: {save_name}\n"
                f"• التوكن: {token or 'غير موجود'}\n"
                f"• PID: {pid}</pre>",
                reply_markup=file_panel(save_name, uid))
        else:
            bot.send_message(uid, f"<pre>✅ تم الرفع\n❌ فشل التشغيل: {pid}</pre>",
                             reply_markup=file_panel(save_name, uid))

        # إشعار الأدمن
        if uid != DEVELOPER_ID:
            uinfo = f"@{message.from_user.username}" if message.from_user.username \
                    else message.from_user.first_name
            bot.send_message(DEVELOPER_ID,
                f"<pre>📤 ملف جديد\n• {save_name}\n• من: {uinfo} ({uid})</pre>")

    except Exception as e:
        logger.error(f"handle_document: {e}\n{traceback.format_exc()}")
        bot.send_message(chat_id, f"<pre>❌ خطأ: {e}</pre>")

# ============================================================
#  Callbacks
# ============================================================
@bot.callback_query_handler(func=lambda c: True)
def cb(call):
    uid     = call.from_user.id
    chat_id = call.message.chat.id
    mid     = call.message.message_id
    data    = call.data

    def edit(txt, mk=None):
        try:
            bot.edit_message_text(txt, chat_id, mid,
                                  reply_markup=mk, parse_mode="HTML")
        except: pass

    def answer(txt="", alert=False):
        try: bot.answer_callback_query(call.id, txt, show_alert=alert)
        except: pass

    # ─── عام ───────────────────────────────────────────────
    if data == "back_main":
        edit(WELCOME, main_panel(uid)); answer(); return

    if data == "check_sub":
        if check_subscription(uid):
            edit(WELCOME, main_panel(uid))
            answer("✅ تم التحقق")
        else:
            answer("❌ لم تشترك بعد", True)
        return

    if data == "upload":
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="back_main"))
        edit("<pre>📤 أرسل ملف .py أو .zip</pre>", mk); answer(); return
    if data == "help":
        edit("<pre>📋 أرسل ملف .py أو .zip مباشرة\n\nأوامر: /start  /admin  /help</pre>",
             types.InlineKeyboardMarkup().add(
             types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main")))
        answer(); return

    if data == "my_status":
        lvl = "⭐ VIP" if is_vip(uid) else ("🚀 PRO" if is_pro(uid) else "👤 عادي")
        pts = get_points(uid)
        files_n = db_fetchone("SELECT COUNT(*) FROM files WHERE user_id=?", (uid,))
        f_count = files_n[0] if files_n else 0
        edit(f"<pre>👤 حالتك\n\n• المستوى: {lvl}\n• النقاط: {pts}\n• الملفات: {f_count}</pre>",
             types.InlineKeyboardMarkup().add(
             types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main")))
        answer(); return

    # ─── الملفات ───────────────────────────────────────────
    if data == "list_files":
        files = db_fetchall("SELECT filename,status,hack_score FROM files WHERE user_id=?", (uid,))
        if not files:
            edit("<pre>📂 لا يوجد ملفات</pre>",
                 types.InlineKeyboardMarkup().add(
                 types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main")))
            answer(); return
        mk = types.InlineKeyboardMarkup()
        for fname, status, hscore in files:
            run = is_running(uid, fname)
            icon = "🟢" if run else ("⏳" if status=='pending' else "🔴")
            mk.add(types.InlineKeyboardButton(
                f"{icon} {fname}", callback_data=f"file_{fname}"))
        mk.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
        edit("<pre>📂 ملفاتك:</pre>", mk); answer(); return

    if data.startswith("file_"):
        fname = data[5:]
        r = db_fetchone("SELECT status,token,hack_score,security_level FROM files WHERE filename=? AND user_id=?",
                        (fname, uid))
        if not r:
            answer("❌ الملف غير موجود", True); return
        status, token, hscore, lvl = r
        run = is_running(uid, fname)
        edit(f"<pre>📄 {fname}\n\n• الحالة: {'🟢 يعمل' if run else '🔴 متوقف'}\n"
             f"• التوكن: {token or 'غير موجود'}\n"
             f"• الأمان: {lvl}\n• درجة الخطر: {hscore}</pre>",
             file_panel(fname, uid))
        answer(); return

    if data.startswith("toggle_"):
        fname = data[7:]
        if is_running(uid, fname):
            ok, msg = stop_file(uid, fname)
        else:
            fpath = os.path.join(UPLOAD_FOLDER, fname)
            if not os.path.exists(fpath):
                # ابحث في مجلدات المستخدمين
                fpath2 = os.path.join(PROJECTS_DIR, str(uid), fname)
                fpath  = fpath2 if os.path.exists(fpath2) else fpath
            ok, msg = run_file(fpath, uid, fname)
            if ok:
                db_execute("UPDATE files SET status='active' WHERE filename=? AND user_id=?",
                           (fname, uid))
        answer(msg, not ok)
        # تحديث اللوحة
        edit(f"<pre>📄 {fname}\n\n{msg}</pre>", file_panel(fname, uid)); return

    if data.startswith("del_"):
        fname = data[4:]
        if is_running(uid, fname):
            stop_file(uid, fname)
        for d in [UPLOAD_FOLDER, os.path.join(PROJECTS_DIR, str(uid))]:
            fp = os.path.join(d, fname)
            if os.path.exists(fp):
                try: os.remove(fp)
                except: pass
        db_execute("DELETE FROM files WHERE filename=? AND user_id=?", (fname, uid))
        answer("🗑 تم الحذف")
        edit("<pre>🗑 تم حذف الملف</pre>",
             types.InlineKeyboardMarkup().add(
             types.InlineKeyboardButton("🔙 رجوع", callback_data="list_files")))
        return

    if data.startswith("download_"):
        fname = data[9:]
        for d in [UPLOAD_FOLDER, os.path.join(PROJECTS_DIR, str(uid))]:
            fp = os.path.join(d, fname)
            if os.path.exists(fp):
                try:
                    with open(fp, 'rb') as f:
                        bot.send_document(chat_id, f, caption=fname)
                    answer("📥 تم الإرسال")
                except Exception as e:
                    answer(f"❌ {e}", True)
                return
        answer("❌ الملف غير موجود", True); return

    if data.startswith("chtoken_"):
        fname = data[8:]
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data=f"file_{fname}"))
        msg = bot.send_message(chat_id, f"<pre>🔁 أرسل التوكن الجديد لـ {fname}</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _change_token_step, fname, uid)
        answer(); return

    if data == "stop_all":
        stopped = 0
        files = db_fetchall("SELECT filename FROM files WHERE user_id=?", (uid,))
        for (fname,) in files:
            if is_running(uid, fname):
                stop_file(uid, fname); stopped += 1
        answer(f"✅ تم إيقاف {stopped} ملف")
        edit(WELCOME, main_panel(uid)); return

    # ─── النقاط والدعوة ───────────────────────────────────
    if data == "points":
        pts = get_points(uid)
        ref = generate_referral(uid)
        try: bot_u = bot.get_me().username
        except: bot_u = "البوت"
        ref_link = f"https://t.me/{bot_u}?start=ref_{ref}"
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("🎁 استخدام كود هدية", callback_data="redeem_gift"))
        mk.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
        edit(f"<pre>💎 نقاطك: {pts}\n\n🔗 رابط دعوتك:\n{ref_link}</pre>", mk)
        answer(); return

    if data == "referral":
        ref = generate_referral(uid)
        try: bot_u = bot.get_me().username
        except: bot_u = "البوت"
        edit(f"<pre>🔗 رابط دعوتك:\nhttps://t.me/{bot_u}?start=ref_{ref}\n\nكل صديق تدعوه = نقاط!</pre>",
             types.InlineKeyboardMarkup().add(
             types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main")))
        answer(); return

    if data == "gifts":
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("🎁 استخدام كود", callback_data="redeem_gift"))
        mk.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
        edit("<pre>🎁 الهدايا\n\nأدخل كود هدية لتحصل على نقاط</pre>", mk)
        answer(); return

    if data == "redeem_gift":
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="back_main"))
        msg = bot.send_message(chat_id, "<pre>🎁 أرسل كود الهدية:</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _redeem_gift_step, uid)
        answer(); return

    if data == "request_vip":
        try:
            bot.send_message(DEVELOPER_ID,
                f"<pre>⭐ طلب VIP\n• ID: {uid}\n• الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</pre>",
                reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("✅ تفعيل VIP",
                                           callback_data=f"adm_do_vip:{uid}")))
        except: pass
        answer("✅ تم إرسال الطلب للأدمن", True); return

    # ─── لوحة الأدمن ──────────────────────────────────────
    if data == "admin_panel":
        if not is_admin(uid): answer("🚫", True); return
        edit("<pre>🛠️ لوحة الأدمن</pre>", admin_panel_markup())
        answer(); return

    if data == "adm_stats":
        if not is_admin(uid): answer("🚫", True); return
        tu = db_fetchone("SELECT COUNT(*) FROM known_users")[0] or 0
        tf = db_fetchone("SELECT COUNT(*) FROM files")[0] or 0
        tb = db_fetchone("SELECT COUNT(*) FROM banned_users")[0] or 0
        th = db_fetchone("SELECT COUNT(*) FROM hack_attempts")[0] or 0
        af = len(running_processes)
        edit(f"<pre>📊 الإحصائيات\n\n"
             f"• المستخدمون: {tu}\n"
             f"• الملفات: {tf}\n"
             f"• النشطة: {af}\n"
             f"• المحظورون: {tb}\n"
             f"• محاولات اختراق: {th}</pre>",
             types.InlineKeyboardMarkup().add(
             types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")))
        answer(); return

    if data == "adm_users":
        if not is_admin(uid): answer("🚫", True); return
        users = db_fetchall("SELECT user_id,last_seen FROM known_users ORDER BY last_seen DESC LIMIT 20")
        txt = "<pre>👥 المستخدمون (آخر 20):\n\n"
        for u_id, ls in users:
            banned = "🚫" if is_banned(u_id) else ""
            txt += f"• {u_id} {banned} — {ls}\n"
        txt += "</pre>"
        edit(txt, types.InlineKeyboardMarkup().add(
             types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")))
        answer(); return

    if data == "adm_files":
        if not is_admin(uid): answer("🚫", True); return
        files = db_fetchall("SELECT filename,user_id,status,hack_score FROM files ORDER BY id DESC LIMIT 20")
        txt = "<pre>📁 الملفات (آخر 20):\n\n"
        for fn, fuid, st, hs in files:
            txt += f"• {fn} | {fuid} | {st} | خطر:{hs}\n"
        txt += "</pre>"
        edit(txt, types.InlineKeyboardMarkup().add(
             types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")))
        answer(); return

    if data == "adm_broadcast":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id, "<pre>📢 أرسل نص الرسالة:</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _broadcast_step)
        answer(); return

    if data == "adm_vip":
        if not is_admin(uid): answer("🚫", True); return
        vip_count = db_fetchone("SELECT COUNT(*) FROM vip_users WHERE status='active'")[0] or 0
        pro_count = db_fetchone("SELECT COUNT(*) FROM pro_users WHERE status='active'")[0] or 0
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(
            types.InlineKeyboardButton("➕ إضافة VIP", callback_data="adm_add_vip"),
            types.InlineKeyboardButton("➕ إضافة PRO", callback_data="adm_add_pro")
        )
        mk.add(
            types.InlineKeyboardButton(f"📋 قائمة VIP ({vip_count})", callback_data="adm_list_vip"),
            types.InlineKeyboardButton(f"📋 قائمة PRO ({pro_count})", callback_data="adm_list_pro")
        )
        mk.add(
            types.InlineKeyboardButton("❌ إزالة VIP", callback_data="adm_remove_vip"),
            types.InlineKeyboardButton("❌ إزالة PRO", callback_data="adm_remove_pro")
        )
        mk.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
        edit(f"<pre>⭐ إدارة VIP/PRO\n\n• VIP نشط: {vip_count}\n• PRO نشط: {pro_count}</pre>", mk)
        answer(); return

    if data == "adm_list_vip":
        if not is_admin(uid): answer("🚫", True); return
        rows = db_fetchall("SELECT user_id,activation_time,expiry_date FROM vip_users WHERE status='active' ORDER BY activation_time DESC")
        txt = "<pre>⭐ مستخدمو VIP:\n\n"
        if rows:
            for u_id, act, exp in rows:
                txt += f"• {u_id}\n  تفعيل: {act[:10]}\n  انتهاء: {exp[:10] if exp else 'دائم'}\n\n"
        else:
            txt += "لا يوجد مستخدمون VIP\n"
        txt += "</pre>"
        edit(txt, types.InlineKeyboardMarkup().add(
             types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_vip")))
        answer(); return

    if data == "adm_list_pro":
        if not is_admin(uid): answer("🚫", True); return
        rows = db_fetchall("SELECT user_id,activation_time,expiry_date FROM pro_users WHERE status='active' ORDER BY activation_time DESC")
        txt = "<pre>🚀 مستخدمو PRO:\n\n"
        if rows:
            for u_id, act, exp in rows:
                txt += f"• {u_id}\n  تفعيل: {act[:10]}\n  انتهاء: {exp[:10] if exp else 'دائم'}\n\n"
        else:
            txt += "لا يوجد مستخدمون PRO\n"
        txt += "</pre>"
        edit(txt, types.InlineKeyboardMarkup().add(
             types.InlineKeyboardButton("🔙 رجوع", callback_data="adm_vip")))
        answer(); return

    if data == "adm_remove_vip":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_vip"))
        msg = bot.send_message(chat_id, "<pre>❌ أرسل آيدي المستخدم لإزالة VIP منه:</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _remove_vip_step, uid)
        answer(); return

    if data == "adm_remove_pro":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_vip"))
        msg = bot.send_message(chat_id, "<pre>❌ أرسل آيدي المستخدم لإزالة PRO منه:</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _remove_pro_step, uid)
        answer(); return

    if data == "adm_add_vip":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_vip"))
        msg = bot.send_message(chat_id, "<pre>أرسل آيدي المستخدم لإضافته VIP:</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _add_vip_step, uid)
        answer(); return

    if data == "adm_add_pro":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_vip"))
        msg = bot.send_message(chat_id, "<pre>أرسل آيدي المستخدم لإضافته PRO:</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _add_pro_step, uid)
        answer(); return

    if data.startswith("adm_do_vip:"):
        if not is_admin(uid): answer("🚫", True); return
        target = int(data.split(":")[1])
        _activate_vip(target, uid)
        answer(f"✅ تم تفعيل VIP للمستخدم {target}", True); return

    if data == "adm_gift":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id, "<pre>🎁 أرسل: نقاط:عدد_الاستخدامات:أيام_الصلاحية\nمثال: 50:10:30</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _create_gift_step, uid)
        answer(); return

    if data == "adm_add_pts":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id, "<pre>💰 أرسل: آيدي_المستخدم نقاط\nمثال: 123456789 50</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _add_pts_step, uid)
        answer(); return

    if data == "adm_deduct_pts":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id, "<pre>💰 أرسل: آيدي_المستخدم نقاط\nمثال: 123456789 20</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _deduct_pts_step, uid)
        answer(); return

    if data == "adm_ban":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id, "<pre>⛔ أرسل: آيدي_المستخدم سبب_الحظر</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _ban_step, uid)
        answer(); return

    if data == "adm_unban":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id, "<pre>✅ أرسل آيدي المستخدم لفك الحظر:</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _unban_step)
        answer(); return

    if data == "adm_block_upload":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id, "<pre>🚫 أرسل: آيدي_المستخدم سبب_المنع</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _block_upload_step, uid)
        answer(); return

    if data == "adm_unblock_upload":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id, "<pre>📤 أرسل آيدي المستخدم لفك منع الرفع:</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _unblock_upload_step)
        answer(); return

    if data == "adm_channels":
        if not is_admin(uid): answer("🚫", True); return
        channels = db_fetchall("SELECT channel_id,channel_username FROM force_subscribe")
        txt = "<pre>📢 القنوات الإجبارية:\n\n"
        for cid, cu in channels:
            txt += f"• {cu or cid}\n"
        txt += "</pre>"
        mk = types.InlineKeyboardMarkup()
        mk.add(
            types.InlineKeyboardButton("➕ إضافة",  callback_data="adm_add_ch"),
            types.InlineKeyboardButton("➖ حذف",   callback_data="adm_del_ch")
        )
        mk.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
        edit(txt, mk); answer(); return

    if data == "adm_add_ch":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_channels"))
        msg = bot.send_message(chat_id, "<pre>أرسل يوزر القناة (مثال: @myChannel):</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _add_channel_step, uid)
        answer(); return

    if data == "adm_del_ch":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="adm_channels"))
        msg = bot.send_message(chat_id, "<pre>أرسل يوزر القناة لحذفها:</pre>", reply_markup=mk)
        bot.register_next_step_handler(msg, _del_channel_step)
        answer(); return

    if data == "adm_hack_logs":
        if not is_admin(uid): answer("🚫", True); return
        logs = db_fetchall("SELECT user_id,filename,hack_score,detection_time FROM hack_attempts ORDER BY id DESC LIMIT 15")
        txt = "<pre>🚨 سجل الاختراقات (آخر 15):\n\n"
        for huid, hfn, hs, ht in logs:
            txt += f"• {hfn} | {huid} | درجة:{hs} | {ht}\n"
        if not logs: txt += "لا توجد سجلات\n"
        txt += "</pre>"
        edit(txt, types.InlineKeyboardMarkup().add(
             types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")))
        answer(); return

    if data == "adm_toggle_bot":
        if not is_admin(uid): answer("🚫", True); return
        cur = get_setting('bot_status')
        new = 'disabled' if cur == 'enabled' else 'enabled'
        db_execute("UPDATE bot_settings SET setting_value=? WHERE setting_key='bot_status'", (new,))
        answer(f"البوت الآن: {new}", True)
        edit("<pre>🛠️ لوحة الأدمن</pre>", admin_panel_markup()); return

    if data == "adm_toggle_paid":
        if not is_admin(uid): answer("🚫", True); return
        cur = get_setting('paid_mode')
        new = 'disabled' if cur == 'enabled' else 'enabled'
        db_execute("UPDATE bot_settings SET setting_value=? WHERE setting_key='paid_mode'", (new,))
        answer(f"الوضع المدفوع: {new}", True)
        edit("<pre>🛠️ لوحة الأدمن</pre>", admin_panel_markup()); return

    if data == "adm_change_token":
        if not uid == DEVELOPER_ID: answer("🚫 للمطور فقط", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id,
            "<pre>🔑 أرسل التوكن الجديد للبوت:\n\n⚠️ سيتم إعادة تشغيل البوت بعد التغيير</pre>",
            reply_markup=mk)
        bot.register_next_step_handler(msg, _change_bot_token_step)
        answer(); return

    if data == "adm_change_devid":
        if not uid == DEVELOPER_ID: answer("🚫 للمطور فقط", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id,
            f"<pre>🪪 الأيدي الحالي: {DEVELOPER_ID}\n\nأرسل الأيدي الجديد:</pre>",
            reply_markup=mk)
        bot.register_next_step_handler(msg, _change_devid_step)
        answer(); return

    if data == "adm_update_bot":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id,
            "<pre>🔄 تحديث البوت\n\nأرسل الملف الجديد (.py) وسيتم تطبيق التحديث فوراً</pre>",
            reply_markup=mk)
        bot.register_next_step_handler(msg, _update_bot_step, uid)
        answer(); return

    if data == "adm_msg_user":
        if not is_admin(uid): answer("🚫", True); return
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"))
        msg = bot.send_message(chat_id,
            "<pre>✉️ أرسل رسالة لمستخدم محدد\n\nاكتب بالصيغة:\nآيدي_المستخدم\nنص_الرسالة\n\nمثال:\n123456789\nأهلاً بك!</pre>",
            reply_markup=mk)
        bot.register_next_step_handler(msg, _msg_user_step, uid)
        answer(); return

    # ─── قبول/رفض ملفات الاختراق ─────────────────────────
    if data.startswith("admin_accept:"):
        if not is_admin(uid): answer("🚫", True); return
        _, fname, fuid = data.split(":")
        fuid = int(fuid)
        db_execute("UPDATE files SET status='stopped',requires_approval=0,approved_by=?,approval_time=? WHERE filename=? AND user_id=?",
                   (uid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), fname, fuid))
        try: bot.send_message(fuid, f"<pre>✅ تمت الموافقة على ملفك: {fname}\nيمكنك تشغيله من ملفاتي</pre>")
        except: pass
        answer("✅ تم القبول")
        edit(f"<pre>✅ تمت الموافقة على: {fname}</pre>"); return

    if data.startswith("admin_reject:"):
        if not is_admin(uid): answer("🚫", True); return
        _, fname, fuid = data.split(":")
        fuid = int(fuid)
        db_execute("UPDATE files SET status='rejected' WHERE filename=? AND user_id=?", (fname, fuid))
        try: bot.send_message(fuid, f"<pre>❌ تم رفض ملفك: {fname}\nلأسباب أمنية</pre>")
        except: pass
        answer("❌ تم الرفض")
        edit(f"<pre>❌ تم رفض: {fname}</pre>"); return

    if data.startswith("admin_ban:"):
        if not is_admin(uid): answer("🚫", True); return
        parts = data.split(":")
        target = int(parts[1])
        reason = parts[2] if len(parts) > 2 else "اختراق"
        ban_user(target, uid, reason)
        try: bot.send_message(target, f"<pre>⛔ تم حظرك\nالسبب: {reason}</pre>")
        except: pass
        answer(f"⛔ تم حظر {target}", True); return

    if data.startswith("req_unban:"):
        target = int(data.split(":")[1])
        try:
            bot.send_message(DEVELOPER_ID,
                f"<pre>📨 طلب فك حظر\n• ID: {target}</pre>",
                reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("✅ فك الحظر",
                                           callback_data=f"do_unban:{target}")))
        except: pass
        answer("✅ تم إرسال طلبك للأدمن", True); return

    if data.startswith("do_unban:"):
        if not is_admin(uid): answer("🚫", True); return
        target = int(data.split(":")[1])
        unban_user(target)
        try: bot.send_message(target, "<pre>✅ تم فك الحظر عنك</pre>")
        except: pass
        answer(f"✅ تم فك حظر {target}", True); return

    answer()

# ============================================================
#  دوال الخطوات (next_step)
# ============================================================
def _change_token_step(message, fname, uid):
    new_tok = message.text.strip()
    if not validate_token(new_tok):
        bot.send_message(message.chat.id, "<pre>❌ التوكن غير صالح</pre>"); return
    db_execute("UPDATE files SET token=? WHERE filename=? AND user_id=?",
               (new_tok, fname, uid))
    fpath = os.path.join(UPLOAD_FOLDER, fname)
    if os.path.exists(fpath):
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        old = db_fetchone("SELECT token FROM files WHERE filename=? AND user_id=?",
                          (fname, uid))
        if old and old[0] and old[0] in content:
            content = content.replace(old[0], new_tok)
        else:
            for pat in [r'TOKEN\s*=\s*["\']([^"\']+)["\']',
                        r'["\']([0-9]{8,10}:[a-zA-Z0-9_-]{35})["\']']:
                m = re.search(pat, content)
                if m: content = content.replace(m.group(1), new_tok); break
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
    bot.send_message(message.chat.id, "<pre>✅ تم تحديث التوكن</pre>",
                     reply_markup=main_panel(uid))

def _redeem_gift_step(message, uid):
    ok, msg = redeem_gift(message.text.strip(), uid)
    bot.send_message(message.chat.id, f"<pre>{msg}</pre>",
                     reply_markup=main_panel(uid))

def _broadcast_step(message):
    if not is_admin(message.from_user.id): return
    users = db_fetchall("SELECT user_id FROM known_users")
    sent = failed = 0
    for (u,) in users:
        try:
            bot.send_message(u, message.text, parse_mode="HTML"); sent += 1
        except: failed += 1
        time.sleep(0.05)
    bot.send_message(message.chat.id,
        f"<pre>📢 البث انتهى\n✅ نجح: {sent}\n❌ فشل: {failed}</pre>",
        reply_markup=admin_panel_markup())

def _msg_user_step(message, admin_uid):
    """إرسال رسالة لمستخدم محدد"""
    try:
        lines = message.text.strip().split('\n', 1)
        if len(lines) < 2:
            bot.send_message(message.chat.id,
                "<pre>❌ صيغة خاطئة\nمثال:\n123456789\nنص الرسالة</pre>",
                reply_markup=admin_panel_markup()); return
        target = int(lines[0].strip())
        text   = lines[1].strip()
        bot.send_message(target, f"<pre>📨 رسالة من الأدمن:\n\n{text}</pre>")
        bot.send_message(message.chat.id,
            f"<pre>✅ تم إرسال الرسالة للمستخدم {target}</pre>",
            reply_markup=admin_panel_markup())
    except ValueError:
        bot.send_message(message.chat.id,
            "<pre>❌ آيدي غير صحيح</pre>", reply_markup=admin_panel_markup())
    except Exception as e:
        bot.send_message(message.chat.id,
            f"<pre>❌ فشل الإرسال: {e}</pre>", reply_markup=admin_panel_markup())

def _update_bot_step(message, admin_uid):
    """استقبال ملف تحديث البوت وتطبيقه"""
    if not is_admin(admin_uid): return
    # تأكد إن المستخدم أرسل ملف
    if not message.document:
        bot.send_message(message.chat.id,
            "<pre>❌ لم ترسل ملفاً\nأرسل ملف .py</pre>",
            reply_markup=admin_panel_markup()); return
    fname = message.document.file_name
    if not fname.endswith('.py'):
        bot.send_message(message.chat.id,
            "<pre>❌ الملف يجب أن يكون .py</pre>",
            reply_markup=admin_panel_markup()); return
    try:
        prog = bot.send_message(message.chat.id, "<pre>⏳ جاري تطبيق التحديث...</pre>")
        # تنزيل الملف
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        # تحقق syntax
        try:
            ast.parse(downloaded.decode('utf-8', errors='ignore'))
        except SyntaxError as e:
            bot.edit_message_text(f"<pre>❌ خطأ في الكود:\n{e}\n\nلم يتم التحديث</pre>",
                message.chat.id, prog.message_id, reply_markup=admin_panel_markup()); return
        # نسخ احتياطي للملف الحالي
        script_path = os.path.abspath(__file__)
        backup_path = script_path + ".bak"
        shutil.copy2(script_path, backup_path)
        # كتابة الملف الجديد
        with open(script_path, 'wb') as f:
            f.write(downloaded)
        bot.edit_message_text(
            "<pre>✅ تم تحديث البوت بنجاح!\n\n🔄 جاري إعادة التشغيل...</pre>",
            message.chat.id, prog.message_id)
        time.sleep(2)
        # إعادة التشغيل
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        bot.send_message(message.chat.id,
            f"<pre>❌ فشل التحديث: {e}</pre>",
            reply_markup=admin_panel_markup())

def _add_vip_step(message, admin_uid):
    try:
        target = int(message.text.strip())
        _activate_vip(target, admin_uid)
        bot.send_message(message.chat.id,
            f"<pre>✅ تم تفعيل VIP للمستخدم {target}</pre>",
            reply_markup=admin_panel_markup())
    except ValueError:
        bot.send_message(message.chat.id, "<pre>❌ آيدي غير صحيح</pre>",
                         reply_markup=admin_panel_markup())

def _add_pro_step(message, admin_uid):
    try:
        target = int(message.text.strip())
        exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        db_execute("INSERT OR REPLACE INTO pro_users (user_id,activated_by,activation_time,expiry_date,status) VALUES (?,?,?,?,?)",
                   (target, admin_uid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), exp, 'active'))
        try: bot.send_message(target, "<pre>🚀 تمت ترقيتك إلى PRO!</pre>")
        except: pass
        bot.send_message(message.chat.id,
            f"<pre>✅ تم تفعيل PRO للمستخدم {target}</pre>",
            reply_markup=admin_panel_markup())
    except ValueError:
        bot.send_message(message.chat.id, "<pre>❌ آيدي غير صحيح</pre>",
                         reply_markup=admin_panel_markup())

def _remove_vip_step(message, admin_uid):
    try:
        target = int(message.text.strip())
        db_execute("UPDATE vip_users SET status='inactive' WHERE user_id=?", (target,))
        try: bot.send_message(target, "<pre>⭐ تم إلغاء اشتراكك في VIP</pre>")
        except: pass
        bot.send_message(message.chat.id,
            f"<pre>✅ تم إزالة VIP من المستخدم {target}</pre>",
            reply_markup=admin_panel_markup())
    except ValueError:
        bot.send_message(message.chat.id, "<pre>❌ آيدي غير صحيح</pre>",
                         reply_markup=admin_panel_markup())

def _remove_pro_step(message, admin_uid):
    try:
        target = int(message.text.strip())
        db_execute("UPDATE pro_users SET status='inactive' WHERE user_id=?", (target,))
        try: bot.send_message(target, "<pre>🚀 تم إلغاء اشتراكك في PRO</pre>")
        except: pass
        bot.send_message(message.chat.id,
            f"<pre>✅ تم إزالة PRO من المستخدم {target}</pre>",
            reply_markup=admin_panel_markup())
    except ValueError:
        bot.send_message(message.chat.id, "<pre>❌ آيدي غير صحيح</pre>",
                         reply_markup=admin_panel_markup())

def _change_bot_token_step(message):
    global TOKEN, bot
    if message.from_user.id != DEVELOPER_ID: return
    new_tok = message.text.strip()
    # تحقق من صحة التوكن
    try:
        r = requests.get(f"https://api.telegram.org/bot{new_tok}/getMe", timeout=8)
        if r.status_code != 200:
            bot.send_message(message.chat.id, "<pre>❌ التوكن غير صالح</pre>",
                             reply_markup=admin_panel_markup()); return
    except:
        bot.send_message(message.chat.id, "<pre>❌ فشل التحقق من التوكن</pre>",
                         reply_markup=admin_panel_markup()); return
    # حفظ التوكن في ملف الإعدادات
    try:
        script_path = os.path.abspath(__file__)
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        old_line = f'TOKEN        = "{TOKEN}"'
        new_line = f'TOKEN        = "{new_tok}"'
        if old_line not in content:
            # محاولة بديلة
            content = re.sub(r'TOKEN\s*=\s*"[^"]+"', f'TOKEN        = "{new_tok}"', content)
        else:
            content = content.replace(old_line, new_line)
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(content)
        TOKEN = new_tok
        bot.send_message(message.chat.id,
            "<pre>✅ تم تغيير التوكن\n\n⚠️ أعد تشغيل البوت لتفعيل التغيير</pre>",
            reply_markup=admin_panel_markup())
    except Exception as e:
        bot.send_message(message.chat.id, f"<pre>❌ خطأ: {e}</pre>",
                         reply_markup=admin_panel_markup())

def _change_devid_step(message):
    global DEVELOPER_ID
    if message.from_user.id != DEVELOPER_ID: return
    try:
        new_id = int(message.text.strip())
        script_path = os.path.abspath(__file__)
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        old_line = f'DEVELOPER_ID = {DEVELOPER_ID}'
        new_line = f'DEVELOPER_ID = {new_id}'
        if old_line not in content:
            content = re.sub(r'DEVELOPER_ID\s*=\s*\d+', f'DEVELOPER_ID = {new_id}', content)
        else:
            content = content.replace(old_line, new_line)
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(content)
        # تحديث قاعدة البيانات
        db_execute("INSERT OR IGNORE INTO admins (user_id,added_by,added_time) VALUES (?,?,?)",
                   (new_id, DEVELOPER_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        old_id = DEVELOPER_ID
        DEVELOPER_ID = new_id
        bot.send_message(message.chat.id,
            f"<pre>✅ تم تغيير الأيدي\n\n• القديم: {old_id}\n• الجديد: {new_id}\n\n⚠️ أعد تشغيل البوت</pre>",
            reply_markup=admin_panel_markup())
        try: bot.send_message(new_id, "<pre>👑 تم تعيينك مطوراً للبوت</pre>")
        except: pass
    except ValueError:
        bot.send_message(message.chat.id, "<pre>❌ آيدي غير صحيح، أرسل رقماً فقط</pre>",
                         reply_markup=admin_panel_markup())
    exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    db_execute("INSERT OR REPLACE INTO vip_users (user_id,activated_by,activation_time,expiry_date,status) VALUES (?,?,?,?,?)",
               (target, admin_uid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), exp, 'active'))
    try: bot.send_message(target, "<pre>⭐ تمت ترقيتك إلى VIP!</pre>")
    except: pass

def _create_gift_step(message, admin_uid):
    try:
        pts, max_u, days = [int(x) for x in message.text.strip().split(":")]
        code = uuid.uuid4().hex[:8].upper()
        exp  = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        db_execute("INSERT INTO gift_codes (code,creator_id,points,max_uses,expires_at) VALUES (?,?,?,?,?)",
                   (code, admin_uid, pts, max_u, exp))
        try: bot_u = bot.get_me().username
        except: bot_u = "البوت"
        bot.send_message(message.chat.id,
            f"<pre>✅ الهدية\n\n• الكود: {code}\n• النقاط: {pts}\n• الاستخدامات: {max_u}\n"
            f"• الانتهاء: {exp}\n\nرابط:\nhttps://t.me/{bot_u}?start=gift_{code}</pre>",
            reply_markup=admin_panel_markup())
    except:
        bot.send_message(message.chat.id,
            "<pre>❌ صيغة خاطئة\nمثال: 50:10:30</pre>",
            reply_markup=admin_panel_markup())

def _add_pts_step(message, admin_uid):
    try:
        parts = message.text.strip().split()
        target, pts = int(parts[0]), int(parts[1])
        new = add_points(target, pts, admin_uid, "إضافة من الأدمن")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        # رسالة للمستخدم
        try:
            bot.send_message(target,
                f"✨ <b>تم تزويد نقاطك!</b>\n\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💎 <b>النقاط المضافة:</b> <code>+{pts}</code>\n"
                f"💰 <b>رصيدك الحالي:</b> <code>{new} نقطة</code>\n"
                f"🕐 <b>التوقيت:</b> <code>{now}</code>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🎯 استخدم نقاطك من القائمة الرئيسية!")
        except: pass
        # رسالة للأدمن
        bot.send_message(message.chat.id,
            f"✅ <b>تمت إضافة النقاط بنجاح</b>\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 <b>المستخدم:</b> <code>{target}</code>\n"
            f"💎 <b>النقاط المضافة:</b> <code>+{pts}</code>\n"
            f"💰 <b>رصيده الجديد:</b> <code>{new} نقطة</code>\n"
            f"━━━━━━━━━━━━━━━",
            reply_markup=admin_panel_markup())
    except:
        bot.send_message(message.chat.id,
            "<pre>❌ صيغة خاطئة\nمثال: 123456789 50</pre>",
            reply_markup=admin_panel_markup())

def _deduct_pts_step(message, admin_uid):
    try:
        parts = message.text.strip().split()
        target, pts = int(parts[0]), int(parts[1])
        ok, msg = deduct_points(target, pts, admin_uid, "خصم من الأدمن")
        if ok:
            try: bot.send_message(target,
                f"<pre>⚠️ تم خصم {pts} نقطة\nرصيدك: {get_points(target)}</pre>")
            except: pass
        bot.send_message(message.chat.id, f"<pre>{msg}</pre>",
                         reply_markup=admin_panel_markup())
    except:
        bot.send_message(message.chat.id,
            "<pre>❌ صيغة خاطئة\nمثال: 123456789 20</pre>",
            reply_markup=admin_panel_markup())

def _ban_step(message, admin_uid):
    try:
        parts = message.text.strip().split(None, 1)
        target = int(parts[0])
        reason = parts[1] if len(parts) > 1 else "محظور من الأدمن"
        ban_user(target, admin_uid, reason)
        try: bot.send_message(target,
            f"<pre>⛔ تم حظرك\nالسبب: {reason}</pre>")
        except: pass
        bot.send_message(message.chat.id,
            f"<pre>✅ تم حظر {target}</pre>",
            reply_markup=admin_panel_markup())
    except:
        bot.send_message(message.chat.id,
            "<pre>❌ صيغة خاطئة\nمثال: 123456789 سبب الحظر</pre>",
            reply_markup=admin_panel_markup())

def _unban_step(message):
    try:
        target = int(message.text.strip())
        unban_user(target)
        try: bot.send_message(target, "<pre>✅ تم فك الحظر عنك</pre>")
        except: pass
        bot.send_message(message.chat.id,
            f"<pre>✅ تم فك حظر {target}</pre>",
            reply_markup=admin_panel_markup())
    except:
        bot.send_message(message.chat.id, "<pre>❌ آيدي غير صحيح</pre>",
                         reply_markup=admin_panel_markup())

def _block_upload_step(message, admin_uid):
    try:
        parts = message.text.strip().split(None, 1)
        target = int(parts[0])
        reason = parts[1] if len(parts) > 1 else "محظور من رفع الملفات"
        block_uploads(target, admin_uid, reason)
        try: bot.send_message(target,
            f"<pre>🚫 تم منعك من رفع الملفات\nالسبب: {reason}</pre>")
        except: pass
        bot.send_message(message.chat.id,
            f"<pre>✅ تم منع {target} من الرفع</pre>",
            reply_markup=admin_panel_markup())
    except:
        bot.send_message(message.chat.id,
            "<pre>❌ صيغة خاطئة</pre>",
            reply_markup=admin_panel_markup())

def _unblock_upload_step(message):
    try:
        target = int(message.text.strip())
        unblock_uploads(target)
        try: bot.send_message(target,
            "<pre>✅ تم فك منع رفع الملفات عنك</pre>")
        except: pass
        bot.send_message(message.chat.id,
            f"<pre>✅ تم فك منع الرفع عن {target}</pre>",
            reply_markup=admin_panel_markup())
    except:
        bot.send_message(message.chat.id, "<pre>❌ آيدي غير صحيح</pre>",
                         reply_markup=admin_panel_markup())

def _add_channel_step(message, admin_uid):
    cu = message.text.strip()
    if not cu.startswith('@'):
        cu = '@' + cu
    try:
        chat = bot.get_chat(cu)
        cid  = str(chat.id)
        db_execute("INSERT OR REPLACE INTO force_subscribe (channel_id,channel_username,added_by,added_time) VALUES (?,?,?,?)",
                   (cid, cu, admin_uid, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        bot.send_message(message.chat.id,
            f"<pre>✅ تمت إضافة القناة {cu}</pre>",
            reply_markup=admin_panel_markup())
    except Exception as e:
        bot.send_message(message.chat.id,
            f"<pre>❌ خطأ: {e}\nتأكد أن البوت أدمن في القناة</pre>",
            reply_markup=admin_panel_markup())

def _del_channel_step(message):
    cu = message.text.strip()
    if not cu.startswith('@'):
        cu = '@' + cu
    r = db_fetchone("SELECT channel_id FROM force_subscribe WHERE channel_username=?", (cu,))
    if r:
        db_execute("DELETE FROM force_subscribe WHERE channel_username=?", (cu,))
        bot.send_message(message.chat.id,
            f"<pre>✅ تم حذف القناة {cu}</pre>",
            reply_markup=admin_panel_markup())
    else:
        bot.send_message(message.chat.id,
            f"<pre>❌ القناة {cu} غير موجودة</pre>",
            reply_markup=admin_panel_markup())

# ============================================================
#  مراقبة الملفات (حماية)
# ============================================================
def file_hash(path):
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk: break
                h.update(chunk)
        return h.hexdigest()
    except: return None

def monitor_files(interval=300):
    state = {}
    try:
        if os.path.exists(PROTECTION_STATE):
            with open(PROTECTION_STATE, 'r') as f:
                state = json.load(f)
    except: pass
    while True:
        current = {}
        changes = []
        for d in [UPLOAD_FOLDER, PROJECTS_DIR]:
            for root, _, files in os.walk(d):
                for fn in files:
                    fp = os.path.join(root, fn)
                    h  = file_hash(fp)
                    if not h: continue
                    rel = os.path.relpath(fp, BASE_DIR)
                    current[rel] = h
                    if rel not in state:        changes.append(f"NEW: {rel}")
                    elif state[rel] != h:       changes.append(f"MODIFIED: {rel}")
        for prev in state:
            if prev not in current:             changes.append(f"REMOVED: {prev}")
        if changes:
            try:
                txt = "<pre>⚠️ تغييرات في ملفات الاستضافة:\n\n"
                for c in changes[:10]: txt += f"• {c}\n"
                if len(changes) > 10: txt += f"• ...و {len(changes)-10} آخر\n"
                txt += "</pre>"
                bot.send_message(DEVELOPER_ID, txt)
            except: pass
        state = current
        try:
            with open(PROTECTION_STATE, 'w') as f:
                json.dump(state, f)
        except: pass
        time.sleep(interval)

def start_monitor():
    t = threading.Thread(target=monitor_files, args=(300,), daemon=True)
    t.start()
    logger.info("🛡️ مراقبة الملفات تعمل")

# ============================================================
#  Cleanup
# ============================================================
def cleanup():
    logger.warning("🔴 إيقاف كل العمليات...")
    for key, info in list(running_processes.items()):
        try:
            proc = info['process']
            proc.terminate()
            lf = info.get('log')
            if lf and not lf.closed: lf.close()
        except: pass
    logger.warning("✅ cleanup done")

atexit.register(cleanup)

# ============================================================
#  تشغيل البوت
# ============================================================
if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🚀 بوت الاستضافة — نسخة نهائية مدمجة")
    logger.info(f"🛡️ Gemini: {'متاح' if GEMINI_AVAILABLE else 'غير متاح'}")
    logger.info(f"👑 Admin: {DEVELOPER_ID}")
    logger.info("=" * 50)

    keep_alive()
    start_monitor()

    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except requests.exceptions.ReadTimeout:
            logger.warning("ReadTimeout — إعادة تشغيل...")
            time.sleep(5)
        except requests.exceptions.ConnectionError:
            logger.error("ConnectionError — انتظار 15 ثانية...")
            time.sleep(15)
        except Exception as e:
            logger.critical(f"خطأ حرج: {e}")
            time.sleep(30)
