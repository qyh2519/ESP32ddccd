#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, render_template
import pymysql
import datetime
import threading
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr

port = 5000
max_wd = 60

mysql_info = {
    "host": "127.0.0.1",
    "port": 3307, 
    "user": "stm32",
    "password": "qyh20091117",
    "database": "stm32",
    "charset": "utf8mb4",
    "autocommit": True,
    "cursorclass": pymysql.cursors.DictCursor 
}

send_mail_flag = False 
smtp_server = "smtp.qq.com"
smtp_port = 465
my_qq = "q221147@qq.com"
my_pass = "hkqtujeomfonjbib"
to_mails = ["19377293324@163.com", "q221147@qq.com"]
last_mail_time = 0 

app = Flask(__name__)

def get_conn():
    return pymysql.connect(**mysql_info)

# ================= 邮件报警 =================
def fa_youjian(wd, yuanyin):
    global last_mail_time
    now = datetime.datetime.now().timestamp()
    if now - last_mail_time < 15:
        return
    last_mail_time = now

    text = "电动车充电异常报警\n\n当前温度: %.1f℃\n报警原因: %s\n\n请及时登录仪表盘查看详情:\nhttps://stm32.202519.eu.cc/dashboard" % (wd, yuanyin)

    def do_send():
        try:
            msg = MIMEText(text, "plain", "utf-8")
            msg["From"] = formataddr((str(Header("充电桩监控系统", "utf-8")), my_qq))
            msg["To"] = ", ".join(to_mails)
            msg["Subject"] = Header("【严重警告】检测到充电安全隐患", "utf-8")
            
            s = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15)
            s.login(my_qq, my_pass)
            for mail in to_mails:
                s.sendmail(my_qq, [mail], msg.as_string())
            s.quit()
        except Exception as e:
            print("邮件发送失败:", e)

    t = threading.Thread(target=do_send)
    t.daemon = True
    t.start()

# ================= 1. 接收单片机数据 =================
@app.route("/sbsj", methods=["POST", "GET"])
def sbsj():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
    else:
        data = request.args.to_dict()
    if not data:
        data = {}

    try: wd = float(data.get("temp", 0))
    except: wd = 0.0
        
    try: sulv = float(data.get("sulv", 0))
    except: sulv = 0.0
        
    try: yw = int(data.get("yanwu", 0))
    except: yw = 0
        
    try: jdqzt = int(data.get("jdqzt", 0))
    except: jdqzt = 0

    try:
        conn = get_conn()
        cur = conn.cursor()
        sql = "INSERT INTO records (temp, sulv, yanwu, jdqzt) VALUES (%s, %s, %s, %s)"
        cur.execute(sql, (wd, sulv, yw, jdqzt))
        
        cur.execute("SELECT id, command FROM commands WHERE status = 0 ORDER BY id ASC LIMIT 1")
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE commands SET status = 1 WHERE id = %s", (row["id"],))
        conn.close()
    except Exception as e:
        print("数据入库异常:", e)

    bj_yuanyin = []
    # ⭐️ 加入 9999 断线特判
    if wd == 9999.0:
        bj_yuanyin.append("传感器断线/未接入")
    elif wd == 505.0:
        bj_yuanyin.append("主电源被断开，系统正在使用备用电源求救")
    elif wd > max_wd:
        bj_yuanyin.append("电池温度过高")
        
    if yw == 1:
        bj_yuanyin.append("检测到环境烟雾")
    if sulv > 1.0:
        bj_yuanyin.append("电池升温速率异常")

    res = {"status": "ok"}
    if len(bj_yuanyin) > 0:
        all_yuanyin = "，".join(bj_yuanyin)
        res["alarm"] = all_yuanyin
        if send_mail_flag:
            fa_youjian(wd, all_yuanyin)

    return jsonify(res)

# ================= 2. 网页下发指令接口 =================
@app.route("/send_cmd", methods=["POST", "GET"])
def send_cmd():
    #  兼容 JSON 和 URL 参数两种请求
    data = request.get_json(silent=True) or {}
    cmd = data.get("cmd") or request.args.get("cmd", "")
    cmd = str(cmd).strip()
    
    if not cmd:
        return jsonify({"status": "error", "msg": "缺少 cmd 参数"}), 400
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO commands (command, status) VALUES (%s, 0)", (cmd,))
        new_id = cur.lastrowid
        conn.close()
        # 返回 id，防止前端显示 undefined
        return jsonify({"status": "ok", "id": new_id})
    except:
        return jsonify({"status": "error"}), 500

# ================= 3. 最新数据（网页顶部卡片） =================
@app.route("/api/latest")
def api_latest():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT temp, sulv, yanwu, jdqzt, time FROM records ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        
        if row:
            res = {
                "temp": float(row["temp"]) if row["temp"] is not None else 0.0,
                "sulv": float(row["sulv"]) if row["sulv"] is not None else 0.0,
                "yanwu": row["yanwu"],
                "jdqzt": row["jdqzt"],
                "time": row["time"].strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            res = {"temp": 0, "sulv": 0, "yanwu": 0, "jdqzt": 0, "time": "--"}
        res["status"] = "ok"
        return jsonify(res)
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})

# ================= 4. 历史表格数据（网页底部列表） =================
@app.route("/query")
def query():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, temp, sulv, yanwu, jdqzt, time FROM records ORDER BY id DESC LIMIT 50")
        rows = cur.fetchall()
        conn.close()
        
        records = []
        for r in rows:
            records.append({
                "id": r["id"],
                "temp": float(r["temp"]) if r["temp"] is not None else 0.0,
                "sulv": float(r["sulv"]) if r["sulv"] is not None else 0.0,
                "yanwu": r["yanwu"], 
                "jdqzt": r["jdqzt"],
                "time": r["time"].strftime("%Y-%m-%d %H:%M:%S")
            })
        return jsonify({"status": "ok", "records": records})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})

# ================= 5. 曲线数据（网页中间的折线图） =================
@app.route("/api/history")
def api_history():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT temp, yanwu, time FROM records WHERE time >= NOW() - INTERVAL 24 HOUR ORDER BY time ASC LIMIT 200")
        rows = cur.fetchall()
        conn.close()

        points = []
        temps = [] 
        for r in rows:
            t = float(r["temp"]) if r["temp"] is not None else 0
            temps.append(t)
            points.append({
                "t": r["time"].strftime("%H:%M"),
                "ts": r["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "temp": t, 
                "count": 1,
                "alarm": 1 if r["yanwu"] == 1 else 0
            })
       
        stats = {
            "count": len(points),
            "max": max(temps) if temps else 0,
            "min": min(temps) if temps else 0,
            "avg": round(sum(temps) / len(temps), 2) if temps else 0
        }
            
        return jsonify({"status": "ok", "has_data": len(points) > 0, "points": points, "stats": stats})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})

# ================= 6. 网页渲染 =================
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/")
def index():
    return jsonify({
        "service": "EV Charging Monitor Server",
        "status": "running",
        "dashboard_url": "/dashboard"
    })

# ================= 启动与建表 =================
if __name__ == "__main__":
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS records (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            temp FLOAT, 
            sulv FLOAT, 
            yanwu INT, 
            jdqzt INT, 
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS commands (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            command VARCHAR(50), 
            status INT DEFAULT 0)""")
        conn.close()
        print("Database tables ready.")
    except Exception as e:
        print("Database initialization failed:", e)

    print("Server started successfully.")
    app.run(host="0.0.0.0", port=port, threaded=True)