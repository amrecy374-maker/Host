# 🤖 بوت الاستضافة

## رفع على GitHub

1. افتح GitHub وسوّي **New Repository**
2. ارفع هذي الملفات كلها:
   - `final_hosting.py`
   - `requirements.txt`
   - `Procfile`
   - `runtime.txt`
   - `.gitignore`

---

## ربط بـ Railway (مجاناً)

1. روح [railway.app](https://railway.app) وسجّل بحساب GitHub
2. اضغط **New Project** ← **Deploy from GitHub repo**
3. اختر الـ repository
4. Railway راح يشغّله تلقائياً ✅

---

## ربط بـ Render (مجاناً)

1. روح [render.com](https://render.com) وسجّل بحساب GitHub
2. اضغط **New** ← **Web Service**
3. اختر الـ repository
4. غيّر هذي الإعدادات:
   - **Environment:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python final_hosting.py`
5. اضغط **Create Web Service** ✅

---

## ربط بـ Koyeb (مجاناً)

1. روح [koyeb.com](https://koyeb.com) وسجّل
2. **Create App** ← **GitHub**
3. اختر الـ repository
4. **Run command:** `python final_hosting.py`
5. Deploy ✅
