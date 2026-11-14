
import re
import unicodedata

COMPLAINT_CATEGORIES = {
    "Garbage": [
        "garbage", "trash", "rubbish", "waste",
        "dustbin", "litter", "குப்பை", "குப்பைகள்",
        "குப்பை அள்ள", "குப்பை அகற்ற"
    ],
    "Drainage": [
        "drainage", "drain", "sewage", "blocked drain",
        "drain overflow", "dirty water", "சாக்கடை",
        "கழிவுநீர்", "கால்வாய் அடைப்பு"
    ],
    "Water Supply": [
        "no water", "water shortage", "water supply",
        "drinking water", "no drinking water",
        "தண்ணீர் இல்லை", "குடிநீர்", "தண்ணீர் வரவில்லை",
        "குடிநீர் பிரச்சனை"
    ],
    "Water Leakage": [
        "water leakage", "water leak", "leaking pipe",
        "pipe burst", "tap leaking", "தண்ணீர் கசிவு",
        "குழாய் உடைப்பு", "குழாயில் கசிவு"
    ],
    "Road Damage": [
        "pothole", "damaged road", "broken road",
        "road damage", "road repair", "சாலை சேதம்",
        "சாலையில் பள்ளம்", "சாலை பழுது"
    ],
    "Street Light": [
        "street light", "streetlight", "road light",
        "light not working", "lamp not working",
        "தெருவிளக்கு", "விளக்கு எரியவில்லை"
    ],
    "Electricity": [
        "power cut", "no electricity", "electricity problem",
        "power outage", "broken electric wire",
        "மின்தடை", "மின்சாரம் இல்லை",
        "மின்சார பிரச்சனை"
    ],
    "Public Safety": [
        "unsafe", "dangerous area", "open manhole",
        "fallen tree", "exposed wire", "accident risk",
        "திறந்த சாக்கடை மூடி", "ஆபத்தான இடம்",
        "அபாயகரமான மின்கம்பி"
    ],
    "Public Toilets": [
        "public toilet", "toilet not clean",
        "toilet problem", "dirty toilet",
        "பொது கழிப்பிடம்", "கழிப்பறை சுத்தம்"
    ],
    "Stray Animals": [
        "stray dog", "street dog", "stray cattle",
        "stray animals", "நாய்கள் தொல்லை",
        "தெருநாய்", "தெரு மாடுகள்"
    ],
    "Mosquitoes and Pests": [
        "mosquito", "mosquitoes", "mosquito breeding",
        "pest problem", "insect problem",
        "கொசு தொல்லை", "கொசுக்கள்"
    ],
    "Other": []
}


def normalize_text(text):
    """Normalize English and Tamil complaint text."""
    text = unicodedata.normalize("NFC", text)
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def keyword_matches(text, keyword):
    """Match English whole words and Tamil phrases."""
    keyword = normalize_text(keyword)

    # English matching avoids accidental partial-word matches.
    if keyword.isascii():
        pattern = r"(?<!\w)" + re.escape(keyword) + r"(?!\w)"
        return bool(re.search(pattern, text))

    # Tamil matching uses phrase matching.
    return keyword in text


def classify_complaint(complaint_text):
    """
    Classify civic complaints into categories.
    Supports common Tamil and English keywords.
    """

    if not isinstance(complaint_text, str):
        return "Other"

    text = normalize_text(complaint_text)

    if not text:
        return "Other"

    scores = {}

    for category, keywords in COMPLAINT_CATEGORIES.items():
        matched = [
            keyword for keyword in keywords
            if keyword_matches(text, keyword)
        ]

        if matched:
            # Longer, more specific phrases receive more weight.
            scores[category] = sum(len(k) for k in matched)

    if not scores:
        return "Other"

    # Highest keyword score wins.
    return max(scores, key=scores.get)


if __name__ == "__main__":

    test_complaints = [
        "Garbage is not collected in our village",
        "The drainage is blocked",
        "There is no drinking water",
        "Water is leaking from the pipe",
        "There is a pothole on our road",
        "The street light is not working",
        "There is a power cut in our area",
        "There is an open manhole near the school",
        "The public toilet is very dirty",
        "Stray dogs are creating problems",
        "There are too many mosquitoes",
        "My college bus is late",
        "எங்கள் பகுதியில் குப்பைகள் அகற்றப்படவில்லை",
        "குடிநீர் வரவில்லை",
        "சாலையில் பள்ளம் உள்ளது"
    ]

    for complaint in test_complaints:
        category = classify_complaint(complaint)

        print(f"Complaint: {complaint}")
        print(f"Category: {category}")
        print("-" * 40)
