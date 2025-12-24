# src/core/constants.py

"""
Central storage for large, relatively static data structures like
subtitle matching criteria, language codes, etc.
"""

import collections
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Subtitle Matching Criteria & Weights ---
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"}

# --- Skip Patterns ---
SKIP_PATTERNS = {"SAMPLE", "TRAILER"}  # Use a set

# --- Configuration Constants (loaded from settings) ---
# from app.core.config import settings # Moved to top

FUZZY_MATCH_THRESHOLD = settings.FUZZY_MATCH_THRESHOLD

# --- Subtitle Extensions
SUBTITLE_EXTENSIONS_LIST = [".srt", ".sub", ".ass"]
SUBTITLE_EXTENSIONS_TUPLE = tuple(SUBTITLE_EXTENSIONS_LIST)
SUBTITLE_EXTENSIONS_LOWER_TUPLE = tuple(ext.lower() for ext in SUBTITLE_EXTENSIONS_LIST)

# --- Subtitle Codec Types ---
TEXT_SUBTITLE_CODECS = {
    "subrip",
    "srt",
    "ssa",
    "ass",
    "vtt",
    "webvtt",
    "mov_text",
    "eia_608",
    "cea_608",
    "cea_708",
    "timed_text",
    "subviewer",
}

IMAGE_SUBTITLE_CODECS_RO = {"hdmv_pgs_subtitle", "pgssub", "pgs", "xsub"}

IMAGE_SUBTITLE_CODECS_EN = {"hdmv_pgs_subtitle", "pgssub", "pgs"}

# Codecs known to have poor OCR quality or other issues, to be skipped with a warning
IGNORED_OCR_CODECS = {"dvd_subtitle"}


# IMDb type mapping (Ensure comprehensive coverage)
TYPE_MAP = {
    # Movies
    "movie": "movie",
    "tv movie": "movie",
    "video movie": "movie",
    "video": "movie",
    "short": "movie",  # Treat shorts as movies for simplicity? Or 'short'? Let's use movie for now.
    "tv short": "movie",
    # Series
    "tv series": "series",
    "tv mini series": "series",
    "tv special": "series",
    "web series": "series",
    "reality-tv": "series",
    "game-show": "series",
    "talk-show": "series",
    "podcast series": "series",
    "podcast episode": "series",  # Map podcast episode to series ID for lookup
    # Other (Less common for subtitle lookup?)
    "documentary": "documentary",
    "tv documentary": "documentary",
    "video game": "game",
    "music video": "music_video",
    "animation": "animation",  # Often movie or series, but can be distinct
}

# --- Matching Criteria Definition ---
# (Keep the large priority_criteria dictionary definition here)
try:
    priority_criteria = {
        "High Definition and Ultra High Definition": [
            "8K",
            "4320p",
            "4K",
            "UHD",
            "2160p",
            "2048p",
            "2K",
            "QHD",
            "1080i",
            "1080p",
            "1440p",
            "HD",
            "720p",
            "HQ",
        ],
        "Rips from Physical Media": [
            "BluRay",
            "Blu-Ray",
            "HDBluRay",
            "HD-BluRay",
            "PAL",
            "NTSC",
            "HDDVD",
            "HD-DVD",
            "D-Theater",
            "DVD",
            "BRRip",
            "BR-Rip",
            "DVDRip",
            "DVD-Rip",
            "BDRip",
            "BD",
            "BD-Rip",
            "DVD5",
            "DVD9",
            "VCD",
            "SVCD",
        ],
        "Digital and Streaming Rips": [
            "WEB-8K",
            "WEB-4K",
            "WEBRip",
            "WEB-DL",
            "WEBDL",
            "DL",
            "WEB",
            "Web-Rip",
            "Rip",
            "WEBHD",
            "WEB-HD",
            "HDRip",
            "HD-Rip",
            "HDWEBRip",
            "HD-WEBRip",
            "HDTS",
            "WEBHDRip",
            "WEB-HDRip",
            "WEBMux",
            "WEB-Mux",
            "WEB-DLMux",
            "WEB-DLRip",
            "VODRip",
            "HDWeb",
            "HDFilm",
        ],
        "Broadcast Captures": [
            "HDTV",
            "HD-TV",
            "HDTVMux",
            "TVRip",
            "TV",
            "TV-Rip",
            "DSR",
            "PDTV",
            "SDTV",
            "SATRip",
            "IPTV",
            "VHSRip",
            "DVBRip",
            "DTV",
            "SatelliteRip",
            "CableRip",
            "LiveTVRip",
        ],
        "Camcorder and Screeners": [
            "CAM",
            "HDCAM",
            "CamRip",
            "DVDCam",
            "TS",
            "TeleSync",
            "Telesync",
            "TC",
            "Telecine",
            "TeleCine",
            "DVDScr",
            "DVDScreener",
            "Screener",
            "SCR",
            "WP",
            "PDVDRip",
            "PreDVDRip",
        ],
        "Enhanced and High Dynamic Range": [
            "HDR",
            "HDR10",
            "HDR10+",
            "HLG",
            "HLG10",
            "10bit",
            "10-bit",
            "12-bit",
            "12bit",
            "Dolby",
            "DolbyVision",
            "DoVi",
        ],
        "Video Codecs": [
            "x265",
            "h265",
            "265",
            "x264",
            "h264",
            "264",
            "HEVC",
            "AV1",
            "AVC",
            "XviD",
            "DivX",
        ],
        "Audio Codecs": [
            "AAC",
            "AC3",
            "EAC3",
            "DDP5.1",
            "DDP5",
            "DDP7.1",
            "DTS",
            "DTS-ES",
            "DTS-HD",
            "DTS-HD.MA",
            "DTS-HDMA",
            "DTS.MA",
            "TrueHD",
            "Atmos",
            "DD+",
            "DTS-X",
            "DPP5",
            "DD5",
            "BD5",
        ],
        "Web Series": ["WebSeries", "WebEpisode", "WebSeason"],
        "Specific Streaming Service Sources": {
            "Netflix": ["NF", "NFPD", "NFDRip", "NFD-Rip", "NFWEBRip", "NF-WEBRip", "NETFLIX"],
            "Apple TV+": ["APPLE", "APPLETV", "APTV", "iTunesWEB", "APTVHD", "ATVP"],
            "Amazon Prime Video": [
                "AMZN",
                "AmazonHD",
                "Amazon-HD",
                "AMZNWEB",
                "AMZN-WEB",
                "Prime",
                "PrimeWEB",
                "Prime-WEB",
                "PrimeRip",
                "Prime-Rip",
                "AMZ",
            ],
            "HBO Max": [
                "HBO",
                "HMAX",
                "H-MAX",
                "MAX",
                "HMAXWEB",
                "HMAX-WEB",
                "HMAXRip",
                "HMAX-Rip",
                "HMAX-Web",
            ],  # Keep HMAX for compatibility
            "Disney+": ["DSNP", "DSNY", "DSNPWEB", "DSNP-WEB", "DSNPHD", "DSNP-HD"],
            "Peacock": ["Peacock", "PeacockWEB", "Peacock-WEB", "PeacockHD", "Peacock-HD", "PCOK"],
            "Paramount+": ["PMP", "PMTP", "ParamountWEB", "P+", "PM", "PRMT", "PRMNT", "PARAMOUNT"],
            "HULU": ["HULU", "HULUWEB", "HULU-WEB", "HULUHD", "HULU-HD", "HULURip", "HULU-Rip"],
            "Other Services": [
                "WeTV",
                "TUBI",
                "PMTV",
                "PLUTO",
                "VRV",
                "VIKI",
                "YOUTUBE",
                "TIKTOK",
                "YAHOO",
                "MSN",
                "CBSAA",
                "SKST",
                "CRAV",
                "ANTP",
                "DSCP",
                "CEE",
                "DV",
                "ZEE",
                "MA",
                "STAN",
                "iP",
                "iPLAYER",
                "CRITERION",
            ],
        },
        "Special Editions": [
            "International",
            "Extended",
            "IMAX",
            "Directors",
            "Director's",
            "Unrated",
            "Anniversary",
            "Criterion",
            "Final",
            "Cut",
            "Special",
            "Redux",
            "Ultimate",
            "Collectors",
            "Collector's",
            "Complete",
            "Complet",
            "Series",
            "TVSpecial",
            "HolidaySpecial",
            "Pilot",
            "Finale",
            "Deluxe",
            "Limited",
            "Theatrical",
            "Alternate",
            "Restored",
            "Definitive",
            "Premier",
            "Festival",
            "UNCUT",
            "UNCENSORED",
        ],
        "File Modifications": [
            "REPACK",
            "REPACK2",
            "REMUX",
            "Proper",
            "Real",
            "Fix",
            "INTERNAL",
            "LIMITED",
            "MultiSubs",
            "DualAudio",
            "Dubbed",
            "Subbed",
            "HardSub",
            "SoftSub",
            "Remastered",
            "SyncFix",
            "ReEncode",
            "PROPER",
            "SUB",
            "MULTi",
            "LiMiTED",
            "ReEncode2",
            "Proper2",
            "RealFix",
            "FinalVersion",
            "MultiLang",
            "DualLang",
            "DubbedMulti",
            "SubbedMulti",
            "2in1",
            "READ.NFO",
            "READNFO",
        ],
    }

    category_weights = {
        "High Definition and Ultra High Definition": 25,
        "Specific Streaming Service Sources": 15,
        "Enhanced and High Dynamic Range": 12,
        "Digital and Streaming Rips": 10,
        "Rips from Physical Media": 9,
        "Broadcast Captures": 8,
        "Special Editions": 7,
        "File Modifications": 5,
        "Video Codecs": 4,
        "Audio Codecs": 3,
        "Web Series": 1,
        "Camcorder and Screeners": -20,
    }
except Exception as e:
    logger.critical(f"Error defining priority_criteria or category_weights: {e}", exc_info=True)
    priority_criteria = {}
    category_weights = {}


# --- Language Code Mappings ---
# (Use the large mapping from langcodes.py)
try:
    from .langcodes import LANGUAGE_CODE_MAPPING_3_TO_2 as LANG_MAP_3_TO_2_IMPORT

    # Validate the import slightly
    if not isinstance(LANG_MAP_3_TO_2_IMPORT, dict) or not LANG_MAP_3_TO_2_IMPORT:
        raise ValueError("Imported language map is not a valid dictionary or is empty.")
    LANGUAGE_CODE_MAPPING_3_TO_2 = LANG_MAP_3_TO_2_IMPORT
    logger.info(
        f"Successfully imported language code mapping (3->2) with {len(LANGUAGE_CODE_MAPPING_3_TO_2)} entries."
    )
except (ImportError, ValueError, Exception) as e:
    logger.error(
        f"Failed to import or validate language codes from langcodes.py: {e}. Using minimal fallback."
    )
    LANGUAGE_CODE_MAPPING_3_TO_2 = {
        "aar": "aa",
        "abk": "ab",
        "ave": "ae",
        "afr": "af",
        "aka": "ak",
        "amh": "am",
        "arg": "an",
        "ara": "ar",
        "asm": "as",
        "ava": "av",
        "aym": "ay",
        "aze": "az",
        "bak": "ba",
        "bel": "be",
        "bul": "bg",
        "bih": "bh",
        "bis": "bi",
        "bam": "bm",
        "ben": "bn",
        "bod": "bo",
        "bre": "br",
        "bos": "bs",
        "cat": "ca",
        "che": "ce",
        "cha": "ch",
        "cos": "co",
        "cre": "cr",
        "ces": "cs",
        "chu": "cu",
        "chv": "cv",
        "cym": "cy",
        "dan": "da",
        "deu": "de",
        "div": "dv",
        "dzo": "dz",
        "ewe": "ee",
        "ell": "el",
        "eng": "en",
        "epo": "eo",
        "spa": "es",
        "est": "et",
        "eus": "eu",
        "fas": "fa",
        "ful": "ff",
        "fin": "fi",
        "fij": "fj",
        "fao": "fo",
        "fra": "fr",
        "fry": "fy",
        "gle": "ga",
        "gla": "gd",
        "glg": "gl",
        "grn": "gn",
        "guj": "gu",
        "glv": "gv",
        "hau": "ha",
        "heb": "he",
        "hin": "hi",
        "hmo": "ho",
        "hrv": "hr",
        "hat": "ht",
        "hun": "hu",
        "hye": "hy",
        "her": "hz",
        "ina": "ia",
        "ind": "id",
        "ile": "ie",
        "ibo": "ig",
        "iii": "ii",
        "ipk": "ik",
        "ido": "io",
        "isl": "is",
        "ita": "it",
        "iku": "iu",
        "jpn": "ja",
        "jav": "jv",
        "kat": "ka",
        "kon": "kg",
        "kik": "ki",
        "kua": "kj",
        "kaz": "kk",
        "kal": "kl",
        "khm": "km",
        "kan": "kn",
        "kor": "ko",
        "kau": "kr",
        "kas": "ks",
        "kur": "ku",
        "kom": "kv",
        "cor": "kw",
        "kir": "ky",
        "lat": "la",
        "ltz": "lb",
        "lug": "lg",
        "lim": "li",
        "lin": "ln",
        "lao": "lo",
        "lit": "lt",
        "lub": "lu",
        "lav": "lv",
        "mlg": "mg",
        "mah": "mh",
        "mri": "mi",
        "mkd": "mk",
        "mal": "ml",
        "mon": "mn",
        "mar": "mr",
        "msa": "ms",
        "mlt": "mt",
        "mya": "my",
        "nau": "na",
        "nob": "nb",
        "nde": "nd",
        "nep": "ne",
        "ndo": "ng",
        "nld": "nl",
        "nno": "nn",
        "nor": "no",
        "nbl": "nr",
        "nav": "nv",
        "nya": "ny",
        "oci": "oc",
        "oji": "oj",
        "orm": "om",
        "ori": "or",
        "oss": "os",
        "pan": "pa",
        "pli": "pi",
        "pol": "pl",
        "pus": "ps",
        "por": "pt",
        "que": "qu",
        "roh": "rm",
        "run": "rn",
        "ron": "ro",
        "rum": "ro",
        "rus": "ru",
        "kin": "rw",
        "san": "sa",
        "srd": "sc",
        "snd": "sd",
        "sme": "se",
        "sag": "sg",
        "sin": "si",
        "slk": "sk",
        "slv": "sl",
        "smo": "sm",
        "sna": "sn",
        "som": "so",
        "sqi": "sq",
        "srp": "sr",
        "ssw": "ss",
        "sot": "st",
        "sun": "su",
        "swe": "sv",
        "swa": "sw",
        "tam": "ta",
        "tel": "te",
        "tgk": "tg",
        "tha": "th",
        "tir": "ti",
        "tuk": "tk",
        "tgl": "tl",
        "tsn": "tn",
        "ton": "to",
        "tur": "tr",
        "tso": "ts",
        "tat": "tt",
        "twi": "tw",
        "tah": "ty",
        "uig": "ug",
        "ukr": "uk",
        "urd": "ur",
        "uzb": "uz",
        "ven": "ve",
        "vie": "vi",
        "vol": "vo",
        "wln": "wa",
        "wol": "wo",
        "xho": "xh",
        "yid": "yi",
        "yor": "yo",
        "zha": "za",
        "zho": "zh",
        "zul": "zu",
        # Common full names/aliases
        "albanian": "sq",
        "arabic": "ar",
        "armenian": "hy",
        "basque": "eu",
        "bosnian": "bs",
        "bulgarian": "bg",
        "catalan": "ca",
        "chinese": "zh",
        "croatian": "hr",
        "czech": "cs",
        "danish": "da",
        "dutch": "nl",
        "english": "en",
        "estonian": "et",
        "finnish": "fi",
        "french": "fr",
        "georgian": "ka",
        "german": "de",
        "greek": "el",
        "hebrew": "he",
        "hindi": "hi",
        "hungarian": "hu",
        "icelandic": "is",
        "indonesian": "id",
        "italian": "it",
        "japanese": "ja",
        "korean": "ko",
        "latvian": "lv",
        "lithuanian": "lt",
        "macedonian": "mk",
        "malay": "ms",
        "norwegian": "no",
        "persian": "fa",
        "polish": "pl",
        "portuguese": "pt",
        "romanian": "ro",
        "russian": "ru",
        "serbian": "sr",
        "slovak": "sk",
        "slovenian": "sl",
        "spanish": "es",
        "swedish": "sv",
        "thai": "th",
        "turkish": "tr",
        "ukrainian": "uk",
        "vietnamese": "vi",
        # Specific 3-letter aliases not covered by standard mapping (if any)
        "alb": "sq",
        "arm": "hy",
        "baq": "eu",
        "bur": "my",
        "chi": "zh",
        "cze": "cs",
        "dut": "nl",
        "fre": "fr",
        "geo": "ka",
        "ger": "de",
        "gre": "el",
        "ice": "is",
        "mac": "mk",
        "mao": "mi",
        "may": "ms",
        "per": "fa",
        "slo": "sk",
        "tib": "bo",
        "wel": "cy",
        "rom": "ro",
        "rou": "ro",
    }

# Create reverse mapping (2-letter to primary 3-letter) dynamically
LANGUAGE_CODE_MAPPING_2_TO_3 = {}
try:
    # Prefer standard 3-letter codes if multiple map to the same 2-letter
    standard_3_letter_codes = {
        "aa": "aar",
        "ab": "abk",
        "ae": "ave",
        "af": "afr",
        "ak": "aka",
        "am": "amh",
        "an": "arg",
        "ar": "ara",
        "as": "asm",
        "av": "ava",
        "ay": "aym",
        "az": "aze",
        "ba": "bak",
        "be": "bel",
        "bg": "bul",
        "bh": "bih",
        "bi": "bis",
        "bm": "bam",
        "bn": "ben",
        "bo": "bod",
        "br": "bre",
        "bs": "bos",
        "ca": "cat",
        "ce": "che",
        "ch": "cha",
        "co": "cos",
        "cr": "cre",
        "cs": "ces",
        "cu": "chu",
        "cv": "chv",
        "cy": "cym",
        "da": "dan",
        "de": "deu",
        "dv": "div",
        "dz": "dzo",
        "ee": "ewe",
        "el": "ell",
        "en": "eng",
        "eo": "epo",
        "es": "spa",
        "et": "est",
        "eu": "eus",
        "fa": "fas",
        "ff": "ful",
        "fi": "fin",
        "fj": "fij",
        "fo": "fao",
        "fr": "fra",
        "fy": "fry",
        "ga": "gle",
        "gd": "gla",
        "gl": "glg",
        "gn": "grn",
        "gu": "guj",
        "gv": "glv",
        "ha": "hau",
        "he": "heb",
        "hi": "hin",
        "ho": "hmo",
        "hr": "hrv",
        "ht": "hat",
        "hu": "hun",
        "hy": "hye",
        "hz": "her",
        "ia": "ina",
        "id": "ind",
        "ie": "ile",
        "ig": "ibo",
        "ii": "iii",
        "ik": "ipk",
        "io": "ido",
        "is": "isl",
        "it": "ita",
        "iu": "iku",
        "ja": "jpn",
        "jv": "jav",
        "ka": "kat",
        "kg": "kon",
        "ki": "kik",
        "kj": "kua",
        "kk": "kaz",
        "kl": "kal",
        "km": "khm",
        "kn": "kan",
        "ko": "kor",
        "kr": "kau",
        "ks": "kas",
        "ku": "kur",
        "kv": "kom",
        "kw": "cor",
        "ky": "kir",
        "la": "lat",
        "lb": "ltz",
        "lg": "lug",
        "li": "lim",
        "ln": "lin",
        "lo": "lao",
        "lt": "lit",
        "lu": "lub",
        "lv": "lav",
        "mg": "mlg",
        "mh": "mah",
        "mi": "mri",
        "mk": "mkd",
        "ml": "mal",
        "mn": "mon",
        "mr": "mar",
        "ms": "msa",
        "mt": "mlt",
        "my": "mya",
        "na": "nau",
        "nb": "nob",
        "nd": "nde",
        "ne": "nep",
        "ng": "ndo",
        "nl": "nld",
        "nn": "nno",
        "no": "nor",
        "nr": "nbl",
        "nv": "nav",
        "ny": "nya",
        "oc": "oci",
        "oj": "oji",
        "om": "orm",
        "or": "ori",
        "os": "oss",
        "pa": "pan",
        "pi": "pli",
        "pl": "pol",
        "ps": "pus",
        "pt": "por",
        "qu": "que",
        "rm": "roh",
        "rn": "run",
        "ro": "ron",  # Prioritize 'ron' for Romanian
        "ru": "rus",
        "rw": "kin",
        "sa": "san",
        "sc": "srd",
        "sd": "snd",
        "se": "sme",
        "sg": "sag",
        "si": "sin",
        "sk": "slk",
        "sl": "slv",
        "sm": "smo",
        "sn": "sna",
        "so": "som",
        "sq": "sqi",
        "sr": "srp",
        "ss": "ssw",
        "st": "sot",
        "su": "sun",
        "sv": "swe",
        "sw": "swa",
        "ta": "tam",
        "te": "tel",
        "tg": "tgk",
        "th": "tha",
        "ti": "tir",
        "tk": "tuk",
        "tl": "tgl",
        "tn": "tsn",
        "to": "ton",
        "tr": "tur",
        "ts": "tso",
        "tt": "tat",
        "tw": "twi",
        "ty": "tah",
        "ug": "uig",
        "uk": "ukr",
        "ur": "urd",
        "uz": "uzb",
        "ve": "ven",
        "vi": "vie",
        "vo": "vol",
        "wa": "wln",
        "wo": "wol",
        "xh": "xho",
        "yi": "yid",
        "yo": "yor",
        "za": "zha",
        "zh": "zho",
        "zu": "zul",
    }
    # First pass: add priority mappings
    for code2, code3_standard in standard_3_letter_codes.items():
        # Check if the standard code is actually in our main 3->2 map and maps correctly
        if (
            code3_standard in LANGUAGE_CODE_MAPPING_3_TO_2
            and LANGUAGE_CODE_MAPPING_3_TO_2[code3_standard] == code2
        ):
            LANGUAGE_CODE_MAPPING_2_TO_3[code2] = code3_standard

    # Second pass: fill in remaining 2-letter codes not yet mapped from the main dict
    for code3, code2 in LANGUAGE_CODE_MAPPING_3_TO_2.items():
        if code2 and code2 not in LANGUAGE_CODE_MAPPING_2_TO_3:
            LANGUAGE_CODE_MAPPING_2_TO_3[code2] = code3
    logger.info(
        f"Created reverse language code mapping (2->3) with {len(LANGUAGE_CODE_MAPPING_2_TO_3)} entries."
    )
except Exception as e:
    logger.error(f"Failed to create reverse language map: {e}", exc_info=True)
    LANGUAGE_CODE_MAPPING_2_TO_3 = {"en": "eng", "ro": "ron"}  # Minimal fallback


# --- Validation Function ---
def _validate_constants():  # noqa: C901
    """Perform basic checks on the defined constants."""
    valid = True
    warnings = []

    # 1. Check criteria vs weights consistency
    if isinstance(priority_criteria, dict) and isinstance(category_weights, dict):
        criteria_keys = set(priority_criteria.keys())
        weight_keys = set(category_weights.keys())
        if criteria_keys != weight_keys:
            missing_weights = criteria_keys - weight_keys
            extra_weights = weight_keys - criteria_keys
            if missing_weights:
                warnings.append(f"Categories missing weights: {missing_weights}")
            if extra_weights:
                warnings.append(f"Categories have weights but no criteria: {extra_weights}")
    else:
        warnings.append(
            "priority_criteria or category_weights are not dictionaries or failed to load."
        )
        valid = False  # Critical if they aren't dicts

    # 2. Check language mapping consistency (3->2)
    if isinstance(LANGUAGE_CODE_MAPPING_3_TO_2, dict):
        invalid_targets = {
            k: v
            for k, v in LANGUAGE_CODE_MAPPING_3_TO_2.items()
            if not isinstance(v, str) or len(v) != 2
        }
        if invalid_targets:
            warnings.append(
                f"Invalid 2-letter target codes in LANGUAGE_CODE_MAPPING_3_TO_2: {invalid_targets}"
            )
            valid = False  # Likely a critical definition error

        target_counts = collections.Counter(
            v for v in LANGUAGE_CODE_MAPPING_3_TO_2.values() if v
        )  # Count non-empty targets
        duplicates = {code2: count for code2, count in target_counts.items() if count > 1}
        if duplicates:
            warnings.append(
                f"Multiple 3-letter codes map to the same 2-letter code: {len(duplicates)} instances found."
            )
            for code2, count in duplicates.items():
                sources = [
                    code3 for code3, c2 in LANGUAGE_CODE_MAPPING_3_TO_2.items() if c2 == code2
                ]
                logger.debug(
                    f"  -> '{code2}' ({count} sources): {sources}"
                )  # Log details at debug level
    else:
        warnings.append("LANGUAGE_CODE_MAPPING_3_TO_2 is not a dictionary or failed to load.")
        valid = False

    # 3. Basic check of reverse mapping (2->3)
    if not isinstance(LANGUAGE_CODE_MAPPING_2_TO_3, dict) or not LANGUAGE_CODE_MAPPING_2_TO_3:
        warnings.append("LANGUAGE_CODE_MAPPING_2_TO_3 failed to generate or is empty.")
        # Not necessarily critical failure, but indicates mapping issues
        # valid = False # Decide if this is critical

    # Log warnings
    if warnings:
        logger.warning("Constant validation issues found:")
        for warning in warnings:
            logger.warning(f"  - {warning}")

    if not valid:
        logger.critical(
            "Critical errors found during constant validation. Application may malfunction."
        )
        # Uncomment to halt execution if needed
        # raise RuntimeError("Critical constant validation errors found.")

    return valid


# Run validation on import and log potential issues
_validate_constants()
