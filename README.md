# 基于 ESP32 的电动车充电监测装置

电动车充电时监测电池温度、环境烟雾和主电源状态，异常时声光报警并推送邮件通知。硬件端用 ESP32-S3，服务端是 Flask + MySQL，带一个网页仪表盘。

## 系统结构

```
ESP32-S3 ──WiFi──> Flask 服务端 ──> MySQL
   │                    │
   │                    └──> 邮件报警
   └── 温度/烟雾/继电器采集
```

ESP32 每 5 秒通过 HTTP POST 上报一次数据，服务端入库后判断是否触发报警。

## 硬件

### 主控

ESP32-S3-DevKitC-1，16MB Flash。

### 引脚定义

| 引脚 | 宏名 | 连接 | 说明 |
|---|---|---|---|
| GPIO4 | `wd` | DS18B20 数据线 | 温度传感器，单总线 |
| GPIO5 | `yw` | 烟雾传感器数字输出 | 高电平表示检测到烟雾 |
| GPIO6 | `zd` | 主电源检测 | 内部上拉，下降沿触发中断 |
| GPIO47 | `fmq` | 蜂鸣器 | 高电平响 |
| GPIO48 | `led` | 板载 WS2812 | 状态指示 |

### 依赖库

- `paulstoffregen/OneWire`
- `milesburton/DallasTemperature`

PlatformIO 会自动安装，见 `platformio.ini`。

## 设备端

### 工作流程

1. 上电自检，WS2812 依次闪红、绿、蓝，蜂鸣器短鸣
2. 连接 WiFi，不同错误状态用不同颜色提示
3. 主循环每 180 毫秒读一次温度
4. 每 5 秒向服务端上报一次数据

### 状态指示灯

| 颜色 | 含义 |
|---|---|
| 蓝色常亮 | 正常工作 |
| 红色常亮 | 触发报警 |
| 红色闪烁 | WiFi 连接失败 |
| 绿色闪烁 | 上报成功 |
| 红绿蓝循环 | 开机自检 |

### WiFi 状态提示

连接过程中，不同失败原因对应不同闪烁颜色：

| WiFi.status() | 含义 | 提示色 |
|---|---|---|
| 0 | 空闲，正在连接 | 绿色 |
| 1 | 找不到指定网络 | 蓝色 |
| 4 | 密码错误 | 红色 |
| 其他 | 未知错误 | 蜂鸣器短鸣 |

重试超过 100 次后蜂鸣器长鸣 5 秒并放弃连接。

### 温度处理

用 5 个采样值的滑动窗口算升温速率：

```
升温速率 = (最新温度 - 最旧温度) / 5
```

单位是摄氏度每采样周期。超过 1.0 判定为异常升温。

### 特殊码

| 值 | 含义 |
|---|---|
| 9999 | DS18B20 未连接或断线 |
| 505 | 主电源被断开，设备靠备用电源工作 |

主电源断开时通过 GPIO6 下降沿中断触发，进入死循环持续发送求救信号，同时蜂鸣器长鸣、指示灯红色。

### 上报格式

```json
{
  "device_id": "001",
  "temp": 25.5,
  "sulv": 0.05,
  "yanwu": 0,
  "jdqzt": 0
}
```

服务端只用到 `temp`、`sulv`、`yanwu`、`jdqzt` 四个字段，`device_id` 保留但会被忽略。

### 编译烧录

```bash
pio run              # 编译
pio run -t upload    # 烧录
pio device monitor   # 查看串口输出，波特率 115200
```

烧录前修改 `src/main.cpp` 顶部的 WiFi 名称和密码。

## 服务端

### 运行环境

Python 3，依赖：

```bash
pip install flask pymysql
```

### 环境变量

服务端从环境变量读取数据库和邮件配置，模板见 `.env.example`。

```bash
cp .env.example .env
vi .env
```

| 变量 | 说明 |
|---|---|
| `DB_HOST` / `DB_PORT` | 数据库地址和端口，默认 127.0.0.1:3307 |
| `DB_USER` / `DB_PASSWORD` | 数据库账号密码 |
| `DB_NAME` | 数据库名，默认 stm32 |
| `SEND_MAIL` | 设为 1 才发报警邮件，默认 0 |
| `SMTP_HOST` / `SMTP_PORT` | SMTP 服务器，默认 smtp.qq.com:465 |
| `SMTP_USER` / `SMTP_PASS` | 发件邮箱和授权码，QQ 邮箱需在设置里开启 SMTP 服务获取授权码 |
| `MAIL_TO` | 收件人，多个用英文逗号分隔 |

### 数据库

```sql
CREATE TABLE records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  temp FLOAT,
  sulv FLOAT,
  yanwu INT,
  jdqzt INT,
  time DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE commands (
  id INT AUTO_INCREMENT PRIMARY KEY,
  command VARCHAR(255),
  status INT DEFAULT 0
);
```

`records` 存上报数据，`commands` 存下发给设备的指令，`status` 为 0 表示待发送，1 表示已发送。

### 启动

```bash
set -a; source .env; set +a
python3 server.py
```

默认监听 5000 端口。用 systemd 托管时在 service 文件里写 `EnvironmentFile=/root/.env`。

## 接口

### POST /sbsj

接收设备上报。也接受 GET 加 URL 参数的形式。

请求体：

```json
{"temp": 25.5, "sulv": 0.05, "yanwu": 0, "jdqzt": 0}
```

返回：

```json
{"status": "ok"}
```

触发报警时额外返回 `alarm` 字段说明原因。

### POST /send_cmd

下发指令给设备。支持 JSON body 和 URL 参数两种方式。

```bash
curl -X POST http://127.0.0.1:5000/send_cmd -H "Content-Type: application/json" -d '{"cmd":"relay_off"}'
```

### GET /api/latest

返回最新一条记录。

### GET /api/history

返回最近 24 小时的曲线数据和统计信息。

### GET /query?limit=50

按条数查询历史记录。

### GET /dashboard

网页仪表盘。

## 报警逻辑

满足任一条件即报警：

| 条件 | 说明 |
|---|---|
| `temp > 60` | 电池温度过高 |
| `temp == 9999` | 传感器断线 |
| `temp == 505` | 主电源断开 |
| `yanwu == 1` | 检测到烟雾 |
| `sulv > 1.0` | 升温速率异常 |

报警时设备端蜂鸣器响、指示灯变红，服务端在开关打开的情况下发送邮件。邮件有 15 秒限流，避免短时间内重复发送。

## 目录结构

```
platformio.ini           PlatformIO 配置
src/main.cpp             ESP32 主程序
server.py                Flask 服务端
.env.example             环境变量模板
include/                 头文件目录
lib/                     自定义库目录
test/                    测试目录
```
