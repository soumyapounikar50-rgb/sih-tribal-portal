"""
SIH26239 — AI Engine for Tribal Scholarship Verification
Modules: OCR Certificate Verification, Face Biometric Match, Bhashini Translation, Fraud Detection
"""
import hashlib
import os
import re
from datetime import datetime
from difflib import SequenceMatcher

import cv2
import numpy as np
import pytesseract
import requests
from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter

load_dotenv()

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

SCHEDULED_TRIBES = [
    "gond", "bhil", "santal", "oraon", "munda", "mina", "meena", "ho",
    "khasi", "kol", "warli", "korku", "sahariya", "bhumij", "birhor",
    "chenchu", "irula", "toda", "badaga", "koya", "kondh", "savara",
    "tharu", "lodha", "rabha", "dimasa", "karbi", "mising", "deori",
    "bodo", "tripuri", "jamatia", "reang", "lepcha", "limbu", "tamang",
    "sherpa", "gaddi", "jaunsari", "kinnara", "lahaula", "pangwal",
    "baiga", "pardhi", "katkari", "kolam", "thakar", "mahadev koli",
    "malhar koli", "tokre koli", "dhangar", "kokna", "varli",
    "koli mahadev", "thakur", "halba", "bhilala", "patelia",
    "gamit", "chaudhri", "dubla", "naikda", "dhodia", "kukna",
]

ST_KEYWORDS = [
    "scheduled tribe", "scheduled tribes", "st certificate",
    "tribal certificate", "tribe certificate", "caste certificate",
    "anusuchit janjati", "anusuchit jan jati",
    "अनुसूचित जनजाति", "अनुसुचित जनजाति", "जनजाति",
]

NON_ST_KEYWORDS = [
    "scheduled caste", "sc certificate", "अनुसूचित जाति",
    "other backward class", "obc", "socially and educationally backward",
    "sebc", "maratha", "non-creamy layer", "backward class",
    "economically weaker", "ews", "general category",
]

INDIAN_STATES = [
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
]

ISSUING_AUTHORITIES = [
    ("sub divisional officer", "Sub Divisional Officer"),
    ("district magistrate", "District Magistrate"),
    ("tehsildar", "Tehsildar"),
    ("deputy collector", "Deputy Collector"),
    ("collector", "Collector"),
    ("sdm", "SDM"),
    ("sdo", "SDO"),
    ("tahsildar", "Tahsildar"),
]

DATE_PATTERNS = [
    r"\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})\b",
    r"\b(\d{1,2}[-/.][A-Za-z]{3,9}[-/.]\d{4})\b",
    r"\b(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\b",
]

CERT_NUMBER_PATTERNS = [
    r"\b(ST[/\-\s][A-Z]{2}[/\-\s]\d{4}[/\-\s]\d{3,6})\b",
    r"\b([A-Z]{2,4}[/\-]\d{4}[/\-]\d{3,8})\b",
    r"\bcertificate\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z0-9/\-]{6,25})\b",
]

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s\u0900-\u097F]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(raw: str):
    raw = raw.strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    match = re.match(r"(\d{1,2})[-/.]([A-Za-z]{3,9})[-/.](\d{4})", raw)
    if match:
        day, month_str, year = match.groups()
        month = MONTH_MAP.get(month_str[:3].lower())
        if month:
            try:
                return datetime(int(year), month, int(day)).date()
            except ValueError:
                return None
    return None


def _extract_dates(text: str) -> list:
    found = []
    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            parsed = _parse_date(match.group(1))
            if parsed:
                found.append({"raw": match.group(1), "parsed": parsed.isoformat()})
    return found


def _extract_certificate_number(text: str) -> str:
    for pattern in CERT_NUMBER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper().strip()
    return ""


def _assess_image_quality(image_path: str) -> dict:
    img = cv2.imread(image_path)
    if img is None:
        return {"blur_score": 0.0, "quality": "poor", "width": 0, "height": 0}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    height, width = gray.shape

    if blur_score < 60 or min(width, height) < 400:
        quality = "poor"
    elif blur_score < 120 or min(width, height) < 700:
        quality = "fair"
    else:
        quality = "good"

    return {
        "blur_score": round(blur_score, 1),
        "quality": quality,
        "width": width,
        "height": height,
    }


def _build_ocr_variants(image_path: str) -> list[tuple[str, Image.Image]]:
    pil_image = Image.open(image_path).convert("RGB")
    variants: list[tuple[str, Image.Image]] = [("original", pil_image.copy())]

    width, height = pil_image.size
    if max(width, height) < 1800:
        scale = 1800 / max(width, height)
        resized = pil_image.resize(
            (int(width * scale), int(height * scale)),
            Image.Resampling.LANCZOS,
        )
        variants.append(("upscaled", resized))

    gray = np.array(pil_image.convert("L"))
    denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("enhanced_binary", Image.fromarray(binary)))

    contrast = ImageEnhance.Contrast(pil_image).enhance(1.8)
    sharpened = ImageEnhance.Sharpness(contrast).enhance(1.5).filter(ImageFilter.MedianFilter(size=3))
    variants.append(("contrast_sharp", sharpened))

    return variants


def _run_ocr_on_image(image: Image.Image, lang: str) -> dict:
    config = "--oem 3 --psm 6"
    text = pytesseract.image_to_string(image, lang=lang, config=config)
    data = pytesseract.image_to_data(
        image, lang=lang, config=config, output_type=pytesseract.Output.DICT
    )

    confidences = [
        int(conf) for conf, word in zip(data["conf"], data["text"])
        if conf != "-1" and word.strip()
    ]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    word_count = len([w for w in text.split() if w.strip()])

    return {
        "text": text.strip(),
        "avg_confidence": round(avg_conf, 1),
        "word_count": word_count,
    }


def _extract_text_multipass(image_path: str) -> dict:
    variants = _build_ocr_variants(image_path)
    langs = ["eng+hin", "eng"]
    best = {"text": "", "avg_confidence": 0.0, "word_count": 0, "variant": "", "lang": ""}

    for variant_name, image in variants:
        for lang in langs:
            try:
                result = _run_ocr_on_image(image, lang)
            except pytesseract.TesseractError:
                if lang == "eng+hin":
                    continue
                raise

            score = (result["avg_confidence"] * 0.55) + (min(result["word_count"], 120) * 0.45)
            best_score = (best["avg_confidence"] * 0.55) + (min(best["word_count"], 120) * 0.45)
            if score > best_score:
                best = {
                    **result,
                    "variant": variant_name,
                    "lang": lang,
                }

    if not best["text"]:
        fallback = pytesseract.image_to_string(Image.open(image_path))
        best = {
            "text": fallback.strip(),
            "avg_confidence": 0.0,
            "word_count": len(fallback.split()),
            "variant": "fallback",
            "lang": "eng",
        }

    return best


def _match_name(expected_name: str, text: str) -> dict:
    expected = _normalize_text(expected_name)
    normalized_text = _normalize_text(text)
    parts = [p for p in expected.split() if len(p) > 1]

    if not parts:
        return {"found": False, "ratio": 0.0, "method": "empty_name"}

    part_hits = sum(1 for part in parts if part in normalized_text)
    part_ratio = part_hits / len(parts)

    full_ratio = _similarity(expected, normalized_text)
    token_best = 0.0
    text_tokens = normalized_text.split()
    for i in range(len(text_tokens)):
        for size in (2, 3, 4):
            chunk = " ".join(text_tokens[i:i + size])
            if chunk:
                token_best = max(token_best, _similarity(expected, chunk))

    final_ratio = max(part_ratio, full_ratio, token_best)
    return {
        "found": final_ratio >= 0.62,
        "ratio": round(final_ratio * 100, 1),
        "method": "fuzzy_multipass",
        "part_matches": part_hits,
        "part_total": len(parts),
    }


def _detect_category(text_lower: str) -> tuple[bool, bool, str]:
    is_st = any(kw in text_lower for kw in ST_KEYWORDS)
    is_non_st = any(kw in text_lower for kw in NON_ST_KEYWORDS)

    if is_st:
        return True, is_non_st, "Scheduled Tribe (ST)"
    if is_non_st:
        if "obc" in text_lower or "other backward" in text_lower:
            return False, True, "Other Backward Class (OBC)"
        if "scheduled caste" in text_lower or "sc certificate" in text_lower:
            return False, True, "Scheduled Caste (SC)"
        if "sebc" in text_lower or "maratha" in text_lower:
            return False, True, "SEBC / Maratha (Non-Tribal)"
        if "ews" in text_lower or "economically weaker" in text_lower:
            return False, True, "EWS (Non-Tribal)"
        return False, True, "Non-ST Category"
    return False, False, "Unknown"


def _extract_expiry_info(text_lower: str, dates: list) -> tuple[bool, str | None]:
    today = datetime.now().date()
    expiry_hint = None

    for pattern in (
        r"valid\s+(?:upto|until|till|uptil)\s*[:\-]?\s*([^\n\r,;]{4,20})",
        r"validity\s*[:\-]?\s*([^\n\r,;]{4,20})",
    ):
        match = re.search(pattern, text_lower)
        if match:
            expiry_hint = match.group(0).strip()

    parsed_dates = [_parse_date(item["raw"]) for item in dates]
    parsed_dates = [d for d in parsed_dates if d]

    if parsed_dates:
        latest = max(parsed_dates)
        if latest < today:
            return True, expiry_hint or latest.isoformat()

    for raw in re.findall(r"20[12]\d", text_lower):
        year = int(raw)
        if year < today.year - 1:
            return True, expiry_hint or raw

    return False, expiry_hint


def _file_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ScholarshipAI:
    """Core AI engine for SIH26239 Tribal Scholarship Verification."""

    @staticmethod
    def verify_caste_certificate(image_path: str, expected_name: str) -> dict:
        try:
            quality = _assess_image_quality(image_path)
            ocr = _extract_text_multipass(image_path)
            extracted_text = ocr["text"]
            text_lower = extracted_text.lower()

            name_result = _match_name(expected_name, extracted_text)
            is_st_cert, is_non_st_cert, detected_caste_type = _detect_category(text_lower)
            detected_tribes = [t for t in SCHEDULED_TRIBES if t in text_lower]
            dates = _extract_dates(extracted_text)
            is_expired, expiry_date_str = _extract_expiry_info(text_lower, dates)
            certificate_number = _extract_certificate_number(extracted_text)

            issuing_authority = ""
            for keyword, label in ISSUING_AUTHORITIES:
                if keyword in text_lower:
                    issuing_authority = label
                    break

            state_detected = next((s.title() for s in INDIAN_STATES if s in text_lower), "")
            district_detected = ""
            dist_match = re.search(r"district[\s:-]+([A-Za-z\s]{3,30})", extracted_text, re.IGNORECASE)
            if dist_match:
                district_detected = dist_match.group(1).strip().title()

            father_name = ""
            father_match = re.search(
                r"(?:son|daughter|s/o|d/o|father(?:'?s)?\s*name)\s*[:\-]?\s*([A-Za-z\s]{3,40})",
                extracted_text,
                re.IGNORECASE,
            )
            if father_match:
                father_name = father_match.group(1).strip().title()

            issue_date = dates[0]["parsed"] if dates else ""

            flags = []
            fraud_score = 0

            if quality["quality"] == "poor":
                flags.append({
                    "type": "LOW_DOCUMENT_QUALITY",
                    "severity": "MEDIUM",
                    "detail": (
                        f"Document quality is poor (blur score {quality['blur_score']}, "
                        f"{quality['width']}x{quality['height']}). Re-upload a clearer scan."
                    ),
                })
                fraud_score += 12

            if ocr["avg_confidence"] < 45 and ocr["word_count"] < 20:
                flags.append({
                    "type": "LOW_OCR_CONFIDENCE",
                    "severity": "MEDIUM",
                    "detail": (
                        f"OCR confidence is low ({ocr['avg_confidence']}%). "
                        "Text may be unreadable or document may not be a certificate."
                    ),
                })
                fraud_score += 15

            if not name_result["found"]:
                flags.append({
                    "type": "NAME_MISMATCH",
                    "severity": "HIGH",
                    "detail": (
                        f"Applicant name '{expected_name}' matched only "
                        f"{name_result['ratio']}% against OCR text. Possible proxy application."
                    ),
                })
                fraud_score += 35
            elif name_result["ratio"] < 80:
                flags.append({
                    "type": "PARTIAL_NAME_MATCH",
                    "severity": "LOW",
                    "detail": f"Name partially matched at {name_result['ratio']}%. Manual name check advised.",
                })
                fraud_score += 8

            if is_non_st_cert and not is_st_cert:
                flags.append({
                    "type": "WRONG_CERTIFICATE_TYPE",
                    "severity": "CRITICAL",
                    "detail": (
                        f"Certificate appears to be '{detected_caste_type}', not Scheduled Tribe. "
                        "Applicant may be submitting a non-tribal certificate."
                    ),
                })
                fraud_score += 40

            if not is_st_cert and not is_non_st_cert:
                flags.append({
                    "type": "UNRECOGNIZED_CERTIFICATE",
                    "severity": "MEDIUM",
                    "detail": "Could not identify certificate category from OCR text. Manual verification required.",
                })
                fraud_score += 15

            if is_expired:
                flags.append({
                    "type": "EXPIRED_CERTIFICATE",
                    "severity": "HIGH",
                    "detail": f"Certificate appears expired ({expiry_date_str}). Submit a renewed certificate.",
                })
                fraud_score += 25

            if is_st_cert and not detected_tribes:
                flags.append({
                    "type": "TRIBE_NOT_LISTED",
                    "severity": "LOW",
                    "detail": "Tribe name not found in central ST list. Cross-check with state gazette recommended.",
                })
                fraud_score += 5

            if is_st_cert and not issuing_authority:
                flags.append({
                    "type": "MISSING_ISSUING_AUTHORITY",
                    "severity": "LOW",
                    "detail": "No recognized issuing authority detected on certificate.",
                })
                fraud_score += 5

            if is_st_cert and not certificate_number:
                flags.append({
                    "type": "MISSING_CERTIFICATE_NUMBER",
                    "severity": "LOW",
                    "detail": "Certificate number not detected. Manual document audit recommended.",
                })
                fraud_score += 4

            fraud_score = min(fraud_score, 100)
            confidence_score = max(100 - fraud_score, 0)

            if ocr["avg_confidence"] >= 60:
                confidence_score = min(100.0, confidence_score + 3)
            if quality["quality"] == "good":
                confidence_score = min(100.0, confidence_score + 2)

            if fraud_score >= 40:
                status = "⚠️ FRAUD ALERT — Application Flagged"
                recommendation = (
                    f"REJECTED: Application for '{expected_name}' flagged with {len(flags)} issue(s). "
                    f"Fraud risk score: {fraud_score}/100. Immediate manual review required. "
                    f"Do NOT approve for DBT disbursement."
                )
            elif fraud_score >= 15:
                status = "⏳ Requires Manual Review"
                recommendation = (
                    f"PENDING: Application for '{expected_name}' has discrepancies. "
                    f"Fraud risk score: {fraud_score}/100. Forward to District Nodal Officer."
                )
            else:
                status = "✅ Verified Successfully"
                recommendation = (
                    f"APPROVED: Applicant '{expected_name}' and Scheduled Tribe certificate validated "
                    f"via multi-pass OCR + fraud analytics. Confidence: {confidence_score:.1f}%. "
                    f"Eligible for Direct Benefit Transfer (DBT) scholarship disbursement."
                )

            return {
                "status": status,
                "confidence_score": round(confidence_score, 1),
                "fraud_score": fraud_score,
                "extracted_text": extracted_text,
                "system_recommendation": recommendation,
                "detected_category": detected_caste_type,
                "detected_tribes": detected_tribes,
                "detected_state": state_detected,
                "detected_district": district_detected,
                "issuing_authority": issuing_authority,
                "certificate_number": certificate_number,
                "father_name": father_name,
                "issue_date": issue_date,
                "name_match": name_result["found"],
                "name_match_ratio": name_result["ratio"],
                "is_expired": is_expired,
                "flags": flags,
                "flags_count": len(flags),
                "ocr_confidence": ocr["avg_confidence"],
                "ocr_variant_used": ocr["variant"],
                "ocr_language": ocr["lang"],
                "document_quality": quality["quality"],
                "blur_score": quality["blur_score"],
                "analysis_engine": "multi-pass-ocr-v2",
            }

        except Exception as e:
            return {
                "status": "Error",
                "confidence_score": 0,
                "fraud_score": 0,
                "extracted_text": str(e),
                "system_recommendation": "System error — Manual Review Required",
                "flags": [{"type": "SYSTEM_ERROR", "severity": "HIGH", "detail": str(e)}],
                "flags_count": 1,
                "analysis_engine": "error",
            }

    @staticmethod
    def verify_identity(id_card_path: str, live_selfie_path: str) -> dict:
        try:
            if _file_hash(id_card_path) == _file_hash(live_selfie_path):
                return {
                    "is_match": False,
                    "similarity_distance": 999.0,
                    "confidence_percent": 0.0,
                    "status": "⚠️ Same image submitted for ID and selfie — verification rejected",
                    "mode": "anti-spoof",
                    "model_used": None,
                    "face_detected_id": False,
                    "face_detected_selfie": False,
                }

            from deepface import DeepFace

            models = [
                ("ArcFace", "retinaface"),
                ("Facenet512", "retinaface"),
                ("VGG-Face", "opencv"),
            ]

            best_result = None
            last_error = None

            for model_name, detector in models:
                try:
                    result = DeepFace.verify(
                        img1_path=id_card_path,
                        img2_path=live_selfie_path,
                        model_name=model_name,
                        detector_backend=detector,
                        enforce_detection=True,
                        align=True,
                    )
                    distance = float(result["distance"])
                    threshold = float(result.get("threshold", 0.4))
                    confidence = max(0.0, min(100.0, (1 - (distance / max(threshold * 2, 0.01))) * 100))

                    candidate = {
                        "is_match": bool(result["verified"]),
                        "similarity_distance": round(distance, 4),
                        "confidence_percent": round(confidence, 1),
                        "threshold": round(threshold, 4),
                        "model_used": model_name,
                        "detector_used": detector,
                    }

                    if best_result is None or candidate["confidence_percent"] > best_result["confidence_percent"]:
                        best_result = candidate
                except Exception as err:
                    last_error = err
                    continue

            if best_result is None:
                raise last_error or RuntimeError("All face verification models failed")

            face_detected_id = ScholarshipAI._has_face(id_card_path)
            face_detected_selfie = ScholarshipAI._has_face(live_selfie_path)

            if not face_detected_id or not face_detected_selfie:
                best_result["is_match"] = False
                status = "⚠️ Face not detected in one or both images"
            elif best_result["is_match"]:
                status = "Identity Confirmed"
            else:
                status = "⚠️ Biometric Mismatch — Possible Proxy"

            return {
                "is_match": best_result["is_match"],
                "similarity_distance": best_result["similarity_distance"],
                "confidence_percent": best_result["confidence_percent"],
                "status": status,
                "mode": "ai-deepface-ensemble",
                "model_used": best_result["model_used"],
                "detector_used": best_result["detector_used"],
                "match_threshold": best_result["threshold"],
                "face_detected_id": face_detected_id,
                "face_detected_selfie": face_detected_selfie,
            }
        except Exception as e:
            return {
                "is_match": False,
                "similarity_distance": 999.0,
                "confidence_percent": 0.0,
                "status": f"Error: {str(e)}",
                "mode": "error",
            }

    @staticmethod
    def _has_face(image_path: str) -> bool:
        try:
            from deepface import DeepFace
            faces = DeepFace.extract_faces(
                img_path=image_path,
                detector_backend="retinaface",
                enforce_detection=False,
            )
            return len(faces) > 0
        except Exception:
            return False

    @staticmethod
    def translate_text(text: str, source_lang: str, target_lang: str) -> str:
        url = "https://dhruva-api.bhashini.gov.in/services/inference/pipeline"
        payload = {
            "pipelineTasks": [{
                "taskType": "translation",
                "config": {
                    "language": {
                        "sourceLanguage": source_lang,
                        "targetLanguage": target_lang,
                    },
                    "serviceId": "ai4bharat/indictransv2-en-indic-1B",
                },
            }],
            "inputData": {"input": [{"source": text}]},
        }
        headers = {
            "Content-Type": "application/json",
            "ulcaApiKey": os.getenv("BHASHINI_ULCA_API_KEY"),
            "userID": os.getenv("BHASHINI_USER_ID"),
            "Authorization": os.getenv("BHASHINI_INFERENCE_KEY"),
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            res_data = response.json()
            return res_data["pipelineResponse"][0]["output"][0]["target"]
        except Exception:
            return text
