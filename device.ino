#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <U8g2lib.h>
#include <driver/i2s.h>
#include <Audio.h>          // Provided by ESP32-audioI2S library
#include "secrets.h"        // Secure Wi-Fi credentials

// --- Wi-Fi Credentials from secrets.h ---
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;

// --- Server Endpoint ---
const char* serverUrl = "https://makkal-kural-ai.onrender.com/upload_audio"; 

// --- Pin Definitions ---
#define BUTTON_PIN 4        // Push button to trigger recording

// --- I²S Digital Microphone Pins (INMP441) ---
#define I2S_MIC_WS 15   
#define I2S_MIC_SD 32   
#define I2S_MIC_SCK 14  
#define I2S_MIC_PORT I2S_NUM_0

// --- I²S Amplifier Pins (MAX98357A) ---
#define I2S_AMP_BCLK 26
#define I2S_AMP_LRC  25
#define I2S_AMP_DIN  22

// --- OLED Display Setup (U8g2 Hardware I2C for SSD1306 128x64) ---
U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);

// --- Audio Player Instance ---
Audio audio;

void setupMicI2S() {
  const i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = 16000,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = 1024,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  const i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_MIC_SCK,
    .ws_io_num = I2S_MIC_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_MIC_SD
  };

  i2s_driver_install(I2S_MIC_PORT, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_MIC_PORT, &pin_config);
}

void showStartupScreen() {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(12, 12, "MAKKAL KURAL AI");
  u8g2.setFont(u8g2_font_ncenB10_tr);
  u8g2.drawStr(10, 35, "Press to Speak");
  u8g2.setFont(u8g2_font_6x10_tr);
  u8g2.drawStr(5, 58, "Your Voice - Priority");
  u8g2.sendBuffer();
}

void triggerGrievanceRecording() {
  Serial.println("Recording grievance...");
  
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB10_tr);
  u8g2.drawStr(20, 25, "Listening...");
  u8g2.setFont(u8g2_font_6x10_tr);
  u8g2.drawStr(15, 45, "Speak Now / Pesungal");
  u8g2.sendBuffer();

  unsigned long startTime = millis();
  const size_t bufferSize = 1024;
  uint8_t readBuffer[bufferSize];
  size_t bytesRead = 0;
  
  String audioDataPayload = "";

  while (millis() - startTime < 5000) { 
    i2s_read(I2S_MIC_PORT, (void*)&readBuffer, bufferSize, &bytesRead, portMAX_DELAY);
    if (bytesRead > 0) {
      for (int i = 0; i < bytesRead; i += 2) {
        int16_t sample = (readBuffer[i + 1] << 8) | readBuffer[i];
        audioDataPayload += String(sample) + ",";
      }
    }
  }

  Serial.println("Recording finished. Sending to server...");
  
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB10_tr);
  u8g2.drawStr(10, 35, "Processing AI...");
  u8g2.sendBuffer();

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverUrl);
    http.setTimeout(15000); 
    http.addHeader("Content-Type", "text/plain");
    
    int httpResponseCode = http.POST(audioDataPayload);
    
    if (httpResponseCode > 0) {
      Serial.println("Complaint processed successfully!");
      
      u8g2.clearBuffer();
      u8g2.setFont(u8g2_font_ncenB10_tr);
      u8g2.drawStr(5, 25, "Complaint Saved!");
      u8g2.drawStr(15, 45, "Playing Audio...");
      u8g2.sendBuffer();

      // Play audio response stream from server through MAX98357A speaker
      audio.connecttohost(serverUrl);
      while(audio.isRunning()) {
        audio.loop();
      }
      
    } else {
      Serial.print("HTTP Error: ");
      Serial.println(httpResponseCode);
      
      u8g2.clearBuffer();
      u8g2.setFont(u8g2_font_ncenB10_tr);
      u8g2.drawStr(10, 35, "Upload Failed!");
      u8g2.sendBuffer();
    }
    http.end();
  }

  delay(2000);
  showStartupScreen();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(BUTTON_PIN, INPUT_PULLUP);

  u8g2.begin();
  
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(15, 30, "Connecting WiFi...");
  u8g2.sendBuffer();

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected.");
  
  setupMicI2S();
  audio.setPinout(I2S_AMP_BCLK, I2S_AMP_LRC, I2S_AMP_DIN);
  audio.setVolume(21); 

  showStartupScreen();
}

void loop() {
  audio.loop(); 

  if (digitalRead(BUTTON_PIN) == LOW) {
    delay(50); 
    if (digitalRead(BUTTON_PIN) == LOW) {
      triggerGrievanceRecording();
    }
  }
}
