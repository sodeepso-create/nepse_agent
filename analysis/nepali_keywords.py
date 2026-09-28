"""Nepali (Devanagari) keyword dictionaries for NEPSE news."""

# Category keywords (mirror of English CATEGORIES)
NP_CATEGORIES = {
    "index_movement": ["नेप्से", "सेयर बजार", "बजार परिसूचक", "कारोबार", "परिसूचक", "अंकले"],
    "monetary_policy": [
        "नेपाल राष्ट्र बैंक", "राष्ट्र बैंक", "मौद्रिक नीति", "ब्याजदर", "ब्याज दर",
        "नीति दर", "सीआरआर", "एसएलआर", "पुनर्कर्जा", "शेयर धितो", "मार्जिन लेन्डिङ",
    ],
    "regulation": ["धितोपत्र बोर्ड", "सेबोन", "धितोपत्र", "नियमन", "परिपत्र", "निर्देशन", "निलम्बन", "जरिवाना", "छानबिन"],
    "macro": ["बजेट", "राजकोषीय", "कुल ग्राहस्थ", "मुद्रास्फीति", "रेमिट्यान्स", "विदेशी मुद्रा", "व्यापार घाटा", "पूँजीगत लाभ कर", "आर्थिक सर्वेक्षण"],
    "ipo_listing": ["आईपीओ", "प्रारम्भिक सार्वजनिक", "सूचीकरण", "एफपीओ", "डिबेन्चर", "म्युचुअल फन्ड", "प्राथमिक निष्कासन"],
    "sector_banking": ["बैंकिङ", "वाणिज्य बैंक", "विकास बैंक", "वित्त कम्पनी", "खराब कर्जा"],
    "sector_insurance": ["बीमा", "जीवन बीमा", "निर्जीवन बीमा", "बीमा प्राधिकरण", "बीमा समिति", "बीमा दाबी"],
    "sector_hydro": ["जलविद्युत", "विद्युत", "ऊर्जा", "प्राधिकरण", "मेगावाट", "विद्युत प्राधिकरण"],
    "sector_microfinance": ["लघुवित्त", "माइक्रोफाइनान्स", "लघु वित्त"],
    "corporate_action": ["लाभांश", "नगद लाभांश", "बोनस सेयर", "बोनस", "हकप्रद", "हकप्रद सेयर", "वार्षिक साधारण सभा", "साधारण सभा", "किताब बन्द", "सेयर बिक्री", "मर्जर", "गाभ्ने"],
    "rating_action": ["रेटिङ", "मूल्यांकन"],
    "political": ["संसद", "निर्वाचन", "प्रधानमन्त्री", "बजेट अधिवेशन", "राजनीतिक"],
}

# Direction keywords
NP_BULLISH = [
    "वृद्धि", "बढ्यो", "बढ्न", "बढाउन", "बढाएको", "बढी", "माथि", "उकालो",
    "लाभ", "नाफा", "फाइदा", "सुधार", "राम्रो", "मजबुत", "उच्च",
    "सकारात्मक", "आकर्षक", "प्रगति", "सफल", "उपलब्धि", "रिकभरी",
]
NP_BEARISH = [
    "घट्यो", "घट्न", "घटाउन", "गिरावट", "ह्रास", "ओरालो", "कमजोर",
    "नोक्सान", "घाटा", "समस्या", "जरिवाना", "निलम्बन", "रोक्का",
    "नकारात्मक", "संकट", "चिन्ता", "दबाब", "गम्भीर", "असफल",
    "अभाव", "कमी", "घटी",
]
# Sentiment scoring
NP_POSITIVE = ["लाभांश", "बोनस", "नाफा", "वृद्धि", "बढ्यो", "फाइदा", "बढाउन", "सुधार", "उच्च", "मजबुत", "लाभ"]
NP_NEGATIVE = ["घाटा", "नोक्सान", "गिरावट", "घट्यो", "घट्न", "जरिवाना", "निलम्बन", "कमजोर", "समस्या", "रोक्का", "छानबिन"]


def has_nepali(text: str) -> bool:
    """True if text contains Devanagari characters."""
    return any("\u0900" <= c <= "\u097F" for c in (text or ""))


def tag_category_np(text: str) -> list[str]:
    t = text or ""
    return [cat for cat, kws in NP_CATEGORIES.items() if any(k in t for k in kws)]


def score_sentiment_np(text: str) -> float:
    t = text or ""
    pos = sum(1 for w in NP_POSITIVE if w in t)
    neg = sum(1 for w in NP_NEGATIVE if w in t)
    if pos == 0 and neg == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / max(pos + neg, 1)))


def direction_np(text: str) -> str:
    t = text or ""
    b = sum(1 for w in NP_BULLISH if w in t)
    s = sum(1 for w in NP_BEARISH if w in t)
    if b > s:
        return "bullish"
    if s > b:
        return "bearish"
    return "neutral"