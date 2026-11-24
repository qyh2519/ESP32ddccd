#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电动车电池安全监测服务器（印尼公网服务器）
功能：特殊码判定、报警邮件、指令队列、曲线统计。
后端 SQLite 单文件，零第三方依赖。
"""
import json, sqlite3, datetime, threading, smtplib, logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr

DB = "/root/records.db"
PORT = 5000
MAX_WD = 60.0
TEMP_DISCONNECT = 9999.0
TEMP_SOS = 505.0

# 报警邮件配置
send_mail_flag = True
smtp_server = "smtp.qq.com"; smtp_port = 465
my_qq = "q221147@qq.com"; my_pass = "hkqtujeomfonjbib"
to_mails = ["19377293324@163.com", "q221147@qq.com"]
last_mail_time = 0

_db_lock = threading.Lock()

def db():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with _db_lock, db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            temp REAL, sulv REAL DEFAULT 0, yanwu INTEGER DEFAULT 0,
            jdqzt INTEGER DEFAULT 0,
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command TEXT, status INTEGER DEFAULT 0)""")
init_db()

with open("/root/evserver/dashboard.html", "r", encoding="utf-8") as f:
    DASHBOARD = f.read()

def fa_youjian(wd, yuanyin):
    global last_mail_time
    now = datetime.datetime.now().timestamp()
    if now - last_mail_time < 15:
        return
    last_mail_time = now
    text = ("电动车电池异常报警\n\n当前温度: %.1f℃\n报警原因: %s\n\n"
            "请及时登录仪表盘查看详情:\nhttp://8.215.16.101/dashboard") % (wd, yuanyin)
    def do_send():
        try:
            msg = MIMEText(text, "plain", "utf-8")
            msg["From"] = formataddr((str(Header("电池安全监测系统", "utf-8")), my_qq))
            msg["To"] = ", ".join(to_mails)
            msg["Subject"] = Header("【严重警告】检测到电池安全隐患", "utf-8")
            s = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15)
            s.login(my_qq, my_pass)
            for mail in to_mails:
                s.sendmail(my_qq, [mail], msg.as_string())
            s.quit()
        except Exception as e:
            print("邮件发送失败:", e)
    threading.Thread(target=do_send, daemon=True).start()


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, fmt, *args):
        pass
    def _send(self, code, obj=None, html=None):
        if html is not None:
            body = html.encode("utf-8"); ctype = "text/html; charset=utf-8"
        else:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            ctype = "application/json; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass
    def _body_json(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n).decode("utf-8")) if n > 0 else {}
        except Exception:
            return {}

    def do_GET(self):
        u = urlparse(self.path); path = u.path; q = parse_qs(u.query)
        if path in ("/", "/dashboard"):
            return self._send(200, html=DASHBOARD)
        if path == "/api/latest":
            with _db_lock, db() as c:
                row = c.execute("SELECT * FROM records ORDER BY id DESC LIMIT 1").fetchone()
                pending = c.execute("SELECT COUNT(*) n FROM commands WHERE status=0").fetchone()["n"]
                total = c.execute("SELECT COUNT(*) n FROM records").fetchone()["n"]
            res = {
                "temp": float(row["temp"]) if row and row["temp"] is not None else 0,
                "sulv": float(row["sulv"]) if row and row["sulv"] is not None else 0,
                "yanwu": row["yanwu"] if row else 0,
                "jdqzt": row["jdqzt"] if row else 0,
                "time": row["time"] if row else "--",
                "pending_commands": pending, "total_records": total, "status": "ok",
            }
            return self._send(200, res)
        if path == "/api/history":
            with _db_lock, db() as c:
                cutoff = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
                rows = c.execute("SELECT temp,sulv,yanwu,time FROM records WHERE time >= ? ORDER BY time ASC LIMIT 200", (cutoff,)).fetchall()
            points, temps = [], []
            for r in rows:
                t = float(r["temp"]) if r["temp"] is not None else 0
                if t >= 9998.5 or t == TEMP_SOS or t > 200: continue
                temps.append(t); ts = r["time"]
                points.append({"t": ts[11:16] if len(ts)>=16 else ts, "ts": ts, "temp": t, "count": 1, "alarm": 1 if r["yanwu"]==1 else 0})
            stats = {"count":len(points), "max":max(temps) if temps else None,
                     "min":min(temps) if temps else None, "avg":round(sum(temps)/len(temps),2) if temps else None}
            return self._send(200, {"status":"ok","has_data":len(points)>0,"points":points,"stats":stats})
        if path == "/query":
            limit = min(max(int(q.get("limit",[50])[0]),1),500)
            with _db_lock, db() as c:
                rows = c.execute("SELECT * FROM records ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            records = [{"id":r["id"],"temp":float(r["temp"]) if r["temp"] is not None else 0,
                        "sulv":float(r["sulv"]) if r["sulv"] is not None else 0,
                        "yanwu":r["yanwu"],"jdqzt":r["jdqzt"],"time":r["time"]} for r in rows]
            return self._send(200, {"status":"ok","records":records})
        return self._send(404, {"status":"error","msg":"not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/sbsj":
            data = self._body_json() or parse_qs(urlparse(self.path).query)
            def num(k, default=0.0):
                try: return float(data.get(k, default))
                except: return default
            wd = num("temp"); sulv = num("sulv")
            try: yw = int(float(data.get("yanwu",0)))
            except: yw = 0
            try: jdqzt = int(float(data.get("jdqzt",0)))
            except: jdqzt = 0
            row = None
            with _db_lock, db() as c:
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("INSERT INTO records (temp,sulv,yanwu,jdqzt,time) VALUES (?,?,?,?,?)", (wd,sulv,yw,jdqzt,now_str))
                row = c.execute("SELECT id,command FROM commands WHERE status=0 ORDER BY id ASC LIMIT 1").fetchone()
                if row: c.execute("UPDATE commands SET status=1 WHERE id=?", (row["id"],))
            reasons = []
            if wd == TEMP_DISCONNECT: reasons.append("传感器断线/未接入")
            elif wd == TEMP_SOS: reasons.append("主电源被断开，系统正在使用备用电源求救")
            elif wd > 200: reasons.append("温度数据异常（读数超出量程，请检查传感器）")
            elif wd > MAX_WD: reasons.append("电池温度过高")
            if yw == 1: reasons.append("检测到环境烟雾")
            if sulv > 0.5: reasons.append("电池升温速率异常")
            res = {"status":"ok"}
            if row: res["command"] = row["command"]
            if reasons:
                res["alarm"] = "，".join(reasons)
                if send_mail_flag: fa_youjian(wd, "，".join(reasons))
                else: print("[邮件已关闭] 报警原因:", "，".join(reasons))
            return self._send(200, res)
        if path == "/send_cmd":
            data = self._body_json()
            cmd = str(data.get("cmd") or parse_qs(urlparse(self.path).query).get("cmd",[""])[0]).strip()
            if not cmd: return self._send(400, {"status":"error","msg":"缺少 cmd 参数"})
            with _db_lock, db() as c:
                cur = c.execute("INSERT INTO commands (command,status) VALUES (?,0)", (cmd,))
                new_id = cur.lastrowid
            return self._send(200, {"status":"ok","id":new_id,"command":cmd})
        return self._send(404, {"status":"error","msg":"not found"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print("EV Server (full) on 0.0.0.0:%d DB=%s mail=%s" % (PORT, DB, send_mail_flag), flush=True)
    srv.serve_forever()
