# 电动车安全监测系统

基于边缘计算与掉电保护技术

随车安装的电动车电池安全监测装置。装置固定在电池旁边跟着车走，全程监测电池温度与周围烟雾，用滑动窗口算法计算升温速率实现超前预警；供电被切断的瞬间依靠超级电容继续工作约 10 秒，把求救信号发出去。

## 系统架构

```
感知层   DS18B20温度  MQ-2烟雾  LM393比较器 + 5F超级电容
            ↓            ↓              ↓
主控层   ESP32-S3：滑动窗口算法 / 时间片轮询 / 掉电中断
            ↓  HTTP POST JSON 经手机热点
云端层   Caddy 反向代理 → Python 服务 → SQLite 数据库
            ↓                    ↓
        网页看板            SMTP 邮件告警
```

## 目录结构

```
firmware/main.cpp         ESP32-S3 固件（Arduino 框架）
server/server.py          后端服务（Python 标准库，零第三方依赖）
server/dashboard.html     网页看板（单文件 HTML/CSS/JS）
platformio.ini            PlatformIO 工程配置
```

## 硬件连接

| 功能 | ESP32-S3 引脚 | 说明 |
|---|---|---|
| DS18B20 数据 | GPIO4 | 单总线，需 4.7k 上拉 |
| MQ-2 数字输出 | GPIO5 | 低电平有效 |
| LM393 掉电检测 | GPIO6 | INPUT_PULLUP，FALLING 触发中断 |
| 蜂鸣器 | GPIO47 | 有源蜂鸣器，高电平响 |
| RGB 灯 | GPIO48 | WS2812 单线控制 |

## 关键参数

| 参数 | 值 | 说明 |
|---|---|---|
| 采样周期 | 180ms | `cy` |
| 上报周期 | 5000ms | `sbsj` |
| MQ-2 预热 | 30000ms | `ywyr` |
| 温度阈值 | 60.0℃ | `fazhi` |
| 速率阈值 | 0.5 ℃/步 | `swsl` |
| 速率报警保持 | 5000ms | `sulv_keep` |
| 断线码 | 9999 | `wdcwm` |
| 掉电求救码 | 505 | `sos` |

## 掉电检测电路

LM393 电压比较器：

- 检测端 IN+：5V 经 4.7k / 2k 分压 → 1.49V
- 基准端 IN-：3.3V 经 4.6k / 2k 分压 → 1.00V
- 供电正常时 IN+ > IN-，输出高电平
- 掉电时 IN+ 跌破 1.00V，输出下降沿，触发中断

⚠️ 注意：LM393 输入电压上限是 Vcc − 1.5V，3.3V 供电时只有 1.8V，设计分压必须留余量。

储能：5F 超级电容，串 10Ω 限流电阻（上电冲击电流 0.5A）和肖特基二极管（防倒灌）。充电时间常数 50 秒，充满约 2.5 分钟，实测掉电后续航约 10 秒。

## 部署

```bash
# 服务器
mkdir -p /root/evserver
cp server/server.py server/dashboard.html /root/evserver/
cp server/ev_server.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now ev_server

# 固件
pio run -t upload
```

## 接口

| 端点 | 方法 | 说明 |
|---|---|---|
| `/sbsj` | POST | 设备上报数据 |
| `/api/latest` | GET | 最新一条记录 |
| `/api/history` | GET | 最近 24 小时曲线 |
| `/query?limit=50` | GET | 历史表格 |
| `/dashboard` | GET | 网页看板 |

## 特殊码约定

| 代码 | 含义 |
|---|---|
| 9999 | 温度传感器断线 |
| 505 | 主电源断开求救 |
| >200 | 超量程异常（服务器端过滤） |

## 许可

仅供学习交流使用。
