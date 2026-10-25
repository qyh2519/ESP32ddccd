#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>

//服务器及wifi相关参数
const char* wifiid = "ESP32";
const char* sjrdid = "vivo iQOO Pro";
const char* sjrdmm = "12345678";
const char* wz = "http://stm32.202519.eu.cc/sbsj";

//引脚定义
#define wd 4
#define yw 5
#define zd 6
#define fmq 47
#define led 48

//定义一些雷霆常量
#define ywyr 20000
#define cy 180
#define wdcwm 9999
#define sos 505

#define fazhi 60.0
#define swsl 1

#define sbsj 5000

//定义一些神秘变量
float wdsz[5]={0,0,0,0,0};
float dqwd;
float shengwensulv;
bool huangziquan = false;//算法是否启用
int wangjingwei = 0;//温度数据指向的数组索引

unsigned long last_wd_Time = 0;
unsigned long last_sb_Time = 0;
unsigned long ywTime = 0;

bool dqyw;

volatile bool zdbzw = false;

//自检用的二维数组
const int zijian [3] [3] = {
    {255,0,0},
    {0,255,0},
    {0,0,255},
};

OneWire oneWire(wd);
DallasTemperature sensors(&oneWire);

//一些神秘中断函数
  void IRAM_ATTR zdhs() {
 zdbzw = true;
}

float sf(float dqwd);
void sb(float dqwd, bool dqyw, float sulv, bool baojing);

//写一些初始化函数
void setup() {
 pinMode(fmq,OUTPUT);
 pinMode(led,OUTPUT);
 pinMode(yw,INPUT);
 pinMode(zd,INPUT_PULLUP);
 sensors.begin();
 sensors.setResolution(9);

 //自检
 digitalWrite(fmq,1);
 for(int i = 0;i<3;i++){
 neopixelWrite(led,zijian[i][0],zijian[i][1],zijian[i][2]);
 delay(300);
 neopixelWrite(led, 0, 0, 0);
 }
 digitalWrite(fmq,0);

 attachInterrupt(digitalPinToInterrupt(zd), zdhs, FALLING);

 WiFi.begin(sjrdid, sjrdmm);
 while (WiFi.status() != 3) {
    static int i = 0;//static的作用是保持i的值不被重置
    delay(100);
    //等待连接
    if(WiFi.status() == 0){
        neopixelWrite(led,zijian[1][0],zijian[1][1],zijian[1][2]);
        delay(100);
        neopixelWrite(led, 0, 0, 0);
        i++;
     }
     //找不到网络
     else if(WiFi.status() == 1){
        neopixelWrite(led,zijian[2][0],zijian[2][1],zijian[2][2]);
        delay(100);
        neopixelWrite(led, 0, 0, 0);
        i++;
     }
     //密码错误
     else if(WiFi.status() == 4){
        neopixelWrite(led,zijian[0][0],zijian[0][1],zijian[0][2]);
        delay(100);
        neopixelWrite(led, 0, 0, 0);
        i++;
     }
     //不知道什么乱七八糟的错误
     else{
        digitalWrite(fmq,1);
        delay(30);
        digitalWrite(fmq,0);
        i++;
     }
     if(i > 100){
        digitalWrite(fmq,1);
        delay(5000);
        digitalWrite(fmq,0);
        break;
     }
 }
 neopixelWrite(led,0,0,75);//正常工作显示蓝灯
last_wd_Time = last_sb_Time = ywTime = millis();
}

void loop(){
 //掉电处理
 if(zdbzw == true){
    zdbzw = false;
    while(1){
        sb(sos,true,-1.0,true);
        delay(3000);
        digitalWrite(fmq,1);
        neopixelWrite(led, 50, 0, 0);
    }
 }
 unsigned long now = millis();
 if(now-last_wd_Time>=cy){
     last_wd_Time = now;
     sensors.requestTemperatures();
     dqwd = sensors.getTempCByIndex(0);
     if (dqwd == DEVICE_DISCONNECTED_C){
        dqwd = wdcwm;
     } 
        
        if (now - ywTime > ywyr) { 
            dqyw = (digitalRead(yw) == 1); 
        } 
        else {
            dqyw = false; 
        }
    
     sf(dqwd);
     bool baojing = (dqwd >= fazhi) or dqyw or (shengwensulv > swsl) or (dqwd == wdcwm);
     if (baojing) {
        neopixelWrite(led, 50, 0, 0);
        digitalWrite(fmq, 1);
     } else {
        neopixelWrite(led, 0, 0, 75);
        digitalWrite(fmq, 0);
     }
     //上报数据
     if (now - last_sb_Time >= sbsj) {
        last_sb_Time = now;
        sb(dqwd, dqyw, shengwensulv, baojing); 
     }
    }
}

//一些雷霆算法函数
float sf(float dqwd){
if(huangziquan == false){
    for(int i = 0;i<5;i++){
        wdsz[i] = dqwd;
    }
    huangziquan = true;
    return 0.0;
 }
 wdsz[wangjingwei] = dqwd;
 int oled = (wangjingwei+1)%5;
 float oledwd = wdsz[oled];
 shengwensulv = (wdsz[wangjingwei]-oledwd)/5;
 wangjingwei = (wangjingwei+1)%5;
 return shengwensulv;
 }

 //一些神秘且雷霆的上报函数
 void sb(float dqwd, bool dqyw, float sulv, bool baojing){
     if (WiFi.status() != 3) {
        return; 
    }
    HTTPClient http;
    http.begin(wz);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(2000);
   
    String payload = "{\"device_id\":\"001\",\"temp\":" + String(dqwd, 1) + 
                     ",\"yanwu\":" + String(dqyw ? 1 : 0) + 
                     ",\"sulv\":" + String(sulv, 2) + 
                     ",\"jdqzt\":" + String(baojing ? 1 : 0) + "}";
    
    http.POST(payload);
    http.end(); 
    neopixelWrite(led, 0, 0, 0);
    neopixelWrite(led, 0, 100, 0);
}