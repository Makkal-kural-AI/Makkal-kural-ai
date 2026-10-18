
const int BUTTON_PIN = 4;

int lastButtonState = HIGH;
int currentButtonState = HIGH;

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  Serial.println("Makkal Kural AI Ready");
}

void loop() {
  currentButtonState = digitalRead(BUTTON_PIN);

  // Detect a new button press
  if (lastButtonState == HIGH &&
      currentButtonState == LOW) {

    Serial.println("VOICE_START");
    delay(250);
  }

  lastButtonState = currentButtonState;
}

