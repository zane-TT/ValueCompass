from __future__ import annotations

import json
import math
import os
import re
import sys
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import akshare as ak
import akshare.stock_feature.stock_disclosure_cninfo as disclosure_cninfo
import httpx
import pandas as pd
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv

try:
    from pypdf import PdfReader
except ImportError:
    bundled_python_packages = r"C:\Users\1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages"
    if bundled_python_packages not in sys.path:
        sys.path.append(bundled_python_packages)
    from pypdf import PdfReader

app = Flask(__name__)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": ["http://127.0.0.1:3000", "http://localhost:3000"],
        }
    },
)

YI = 100000000
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
load_dotenv(BASE_DIR / ".env")
DEFAULT_OPENAI_BASE_URL = "https://api.openai-proxy.org/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.4-nano-2026-03-17"
DEFAULT_OPENAI_TEMPERATURE = 0.1

COST_ANALYSIS_FRAMEWORK = {
    "dimensions": [
        {
            "name": "按会计科目",
            "items": ["人工", "采购", "原材料", "租金物业", "水电能耗", "市场投放", "差旅招待", "软件系统", "折旧摊销", "利息税费"],
        },
        {
            "name": "按部门",
            "items": ["销售", "运营", "研发", "生产", "行政", "财务", "HR"],
        },
        {
            "name": "按业务线/产品线",
            "items": ["A产品", "B产品", "C项目"],
        },
        {
            "name": "按固定/变动",
            "items": {
                "固定成本": ["房租", "固定工资", "系统年费"],
                "变动成本": ["提成", "物流", "原料", "佣金", "广告投放"],
            },
        },
        {
            "name": "按可控/不可控",
            "items": {
                "可控": ["投放", "招聘", "差旅", "采购议价"],
                "不可控": ["税费", "政策性社保", "已签长期租约"],
            },
        },
    ],
    "usage": [
        "先判断公司赚什么钱，再判断为了赚这笔钱主要承担哪些成本与支出。",
        "如果缺少完整成本明细，要结合主营构成、毛利率、资产结构、现金流和行业特征做近似判断。",
        "不能假装拿到了不存在的成本明细；缺口必须明确写出来。",
    ],
}

AI_ANALYSIS_SYSTEM_PROMPT = """
浣犳槸涓€鍚岮鑲¤储鎶ュ垎鏋愬姪鎵嬨€?
璇峰熀浜庣粰瀹氱殑缁撴瀯鍖栨暟鎹紝鐢ㄧ畝娲併€佷笓涓氥€佸亸涓氬姟瑙ｈ鐨勪腑鏂囪緭鍑哄垎鏋愮粨璁恒€?瑕佹眰锛?1. 涓嶈缂栭€犱笉瀛樺湪鐨勬暟鎹€?2. 鍏堢粰涓€娈垫€昏瘎锛屽啀缁?鏉¤鐐广€?3. 閲嶇偣缁撳悎璧勪骇璐熷€虹粨鏋勩€佽惀鏀朵笌甯傚€艰秼鍔裤€佸噣鍒╂鼎涓庡競鍊艰秼鍔裤€佸競鐩堢巼鍖洪棿銆?4. 璇█灏介噺璁╅潪璐㈠姟鑳屾櫙鐨勪骇鍝佺粡鐞嗕篃鑳界湅鎳傘€?5. 涓嶈鍐欐姇璧勫缓璁紝涓嶈鎵胯鏀剁泭銆?""".strip()

BUSINESS_TYPE_SYSTEM_PROMPT = """
浣犳槸涓€鍚嶄笓涓氱殑涓婂競鍏徃鍟嗕笟妯″紡鍒嗘瀽甯堛€?
浠诲姟锛?璇锋牴鎹彁渚涚殑鍏徃骞存姤銆佽储鎶ユ暟鎹€佷富钀ヤ笟鍔¤鏄庯紝浠ュ強缁撴瀯鍖栬储鍔¤秼鍔挎暟鎹紝鍒ゆ柇杩欏鍏徃灞炰簬浠€涔堢被鍨嬬殑鍏徃銆?
閲嶈瑕佹眰锛?1. 涓嶈鍙牴鎹涓氬悕绉板垽鏂€?2. 涓嶈鍙牴鎹叧閿瘝鍒ゆ柇銆?3. 蹇呴』鏍规嵁浠ヤ笅璇佹嵁鍒ゆ柇锛?   - 鏀跺叆涓昏鏉ヨ嚜鍝噷
   - 鍒╂鼎涓昏鏉ヨ嚜鍝噷
   - 鏀跺叆澧為暱涓昏鏉ヨ嚜鍝噷
   - 鎴愭湰缁撴瀯鏄粈涔?   - 璧勪骇缁撴瀯鏄粈涔?   - 鐜伴噾娴佺壒寰佹槸浠€涔?4. 濡傛灉淇℃伅涓嶈冻锛屽繀椤昏鏄庘€滄棤娉曠‘瀹氣€濓紝涓嶈缂栭€犮€?5. 鎵€鏈夊垽鏂兘瑕佺粰鍑轰緷鎹€?6. 鏈€缁堣緭鍑?JSON锛屼笖鍙兘杈撳嚭 JSON銆?
棰濆鍒ゆ柇绾︽潫锛?1. 涓嶈鍥犱负鍏徃鏈夆€滅敓浜с€佸埗閫犮€佸寘瑁呪€濈瓑鐜妭锛屽氨鐩存帴鍒や负鈥滄垚鏈埗閫犲瀷鈥濄€?2. 濡傛灉鏀跺叆涓昏鏉ヨ嚜浜у搧閿€鍞紝鍚屾椂姣涘埄鐜囬珮涓旂ǔ瀹氥€佸埄娑﹂泦涓簬鏍稿績鍝佺墝浜у搧銆佸叕鍙告鍐垫垨涓昏惀鏋勬垚鏄剧ず鍝佺墝/娓犻亾/瀹氫环鏉冮噸瑕侊紝搴斾紭鍏堝垽涓衡€滃搧鐗屼骇鍝佸瀷鈥濄€?3. 鈥滄垚鏈埗閫犲瀷鈥濇洿閫傜敤浜庢瘺鍒╃巼涓嶉珮锛屾牳蹇冪珵浜夊姏涓昏鏉ヨ嚜瑙勬ā銆佹垚鏈帶鍒躲€佷骇鑳芥晥鐜囷紝鑰屼笉鏄搧鐗屾孩浠枫€?4. 濡傛灉璇佹嵁鍚屾椂鏀寔鈥滃搧鐗屼骇鍝佸瀷鈥濆拰鈥滄垚鏈埗閫犲瀷鈥濓紝瑕佹槑纭瘮杈冩瘺鍒╃巼銆佸埄娑﹂泦涓害銆佸搧鐗岃〃杩板拰璧勪骇缁撴瀯鍚庡啀鍒ゆ柇锛屼笉鑳藉伔鎳掋€?
鍒ゆ柇鏍囧噯锛?
鍝佺墝浜у搧鍨嬶細
鏀跺叆涓昏鏉ヨ嚜浜у搧閿€鍞紝姣涘埄鐜囬珮涓旂ǔ瀹氾紝鏍稿績绔炰簤鍔涙潵鑷搧鐗屻€佹笭閬撱€佸畾浠锋潈銆?
鎴愭湰鍒堕€犲瀷锛?鏀跺叆涓昏鏉ヨ嚜浜у搧閿€鍞紝浣嗘瘺鍒╃巼涓嶉珮锛屾牳蹇冪珵浜夊姏鏉ヨ嚜瑙勬ā銆佹垚鏈帶鍒躲€佷骇鑳芥晥鐜囥€?
鎶€鏈骇鍝佸瀷锛?鏀跺叆鏉ヨ嚜鎶€鏈骇鍝併€佽澶囥€佽蒋浠舵垨楂樻妧鏈埗閫狅紝鐮斿彂鎶曞叆杈冮珮锛屾妧鏈鍨掗噸瑕併€?
灞ョ害鏈嶅姟鍨嬶細
鏀跺叆鏉ヨ嚜鏈嶅姟浜や粯锛屾瘮濡傜墿娴併€侀楗€侀厭搴椼€侀厤閫併€佽繍缁达紝鍒╂鼎鍙椾汉宸ャ€佸饱绾︽垚鏈奖鍝嶈緝澶с€?
骞冲彴鎾悎鍨嬶細
鏀跺叆鏉ヨ嚜浣ｉ噾銆佸箍鍛娿€佸钩鍙版湇鍔¤垂銆佷氦鏄撴挳鍚堬紝鏍稿績鐪?GMV銆佺敤鎴锋暟銆佸晢瀹舵暟銆佹娊浣ｇ巼銆?
璁㈤槄鏈嶅姟鍨嬶細
鏀跺叆鏉ヨ嚜浼氬憳璐广€丼aaS 璁㈤槄銆侀暱鏈熸湇鍔″悎鍚岋紝鏍稿績鐪嬬画璐圭巼銆佸鎴风暀瀛樸€丄RPU銆?
椤圭洰浜や粯鍨嬶細
鏀跺叆鏉ヨ嚜宸ョ▼銆佸湴浜с€佽蒋浠跺畾鍒躲€佸ぇ椤圭洰浜や粯锛屾牳蹇冪湅鍚堝悓銆佸畬宸ヨ繘搴︺€佸簲鏀惰处娆俱€佺幇閲戞祦銆?
璧勪骇杩愯惀鍨嬶細
鏀跺叆鏉ヨ嚜鍥哄畾璧勪骇鎴栫█缂鸿祫浜ц繍钀ワ紝姣斿楂橀€熴€佹満鍦恒€佹腐鍙ｃ€佺數鍔涖€佹按鍔°€佺璧侊紝鏍稿績鐪嬭祫浜ф敹鐩婄巼鍜岀幇閲戞祦绋冲畾鎬с€?
閲戣瀺鍒╁樊鍨嬶細
鏀跺叆鏉ヨ嚜鍒╂伅鏀跺叆銆侀噾铻嶈祫浜ф敹鐩娿€佽祫閲戞垚鏈樊锛屾牳蹇冪湅鍑€鎭樊銆佷笉鑹巼銆佹嫧澶囥€佽祫鏈厖瓒崇巼銆?
璧勬簮鍛ㄦ湡鍨嬶細
鏀跺叆鍜屽埄娑﹀彈鍟嗗搧浠锋牸鍛ㄦ湡褰卞搷锛屾瘮濡傜叅鐐€佹湁鑹层€佺煶娌广€侀挗閾併€佸寲宸ュ懆鏈熷搧銆?
娣峰悎鍨嬶細
濡傛灉鍏徃鏈変袱涓互涓婇噸瑕佷笟鍔★紝涓旀敹鍏ユ垨鍒╂鼎鍗犳瘮閮借緝澶э紝璇峰垽鏂负娣峰悎鍨嬶紝骞惰鏄庡悇涓氬姟鍗犳瘮
""".strip()

PROXY_ENV_KEYS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
]

BUSINESS_EXPLANATION_RULES = [
    {
        "keywords": ["闆嗚绠辫埅杩?, "鑸繍涓氬姟", "鐝疆"],
        "businessDescription": "杩欏潡鏈川涓婃槸娴疯繍鏈嶅姟锛屼笉鏄埗閫犱骇鍝併€傚叕鍙告妸瀹㈡埛鐨勮揣鐗╄杩涢泦瑁呯锛屽湪鍏ㄧ悆鑸嚎涔嬮棿瀹屾垚杩愯緭锛屾敹鍏ヤ富瑕佹潵鑷繍浠枫€佽埍浣嶅埄鐢ㄧ巼鍜屽悇绫婚檮鍔犺垂銆?,
        "priceDrivers": ["鍏ㄧ悆璐告槗闇€姹?, "鑸嚎杩愪环", "鑸硅埗杩愬姏渚涚粰", "娓彛鎷ュ牭", "鐕冩补鎴愭湰", "姹囩巼"],
        "businessCategory": "service",
    },
    {
        "keywords": ["鐮佸ご涓氬姟", "娓彛", "鐮佸ご"],
        "businessDescription": "杩欏潡涔熸槸鏈嶅姟銆傚叕鍙镐緷鎵樻腐鍙ｅ拰鐮佸ご璧勬簮锛屽悜鑸瑰叕鍙稿拰璐т富鎻愪緵瑁呭嵏銆佸爢瀛樺拰涓浆鏈嶅姟锛屾敹鍏ラ€氬父鍜屽悶鍚愰噺銆佹腐鍙ｈ垂鐜囥€佹灑绾藉湴浣嶇浉鍏炽€?,
        "priceDrivers": ["娓彛鍚炲悙閲?, "鍖哄煙璐告槗娲昏穬搴?, "鏀惰垂鏍囧噯", "鏋㈢航娓湴浣?, "浜哄伐涓庤兘鑰楁垚鏈?],
        "businessCategory": "service",
    },
    {
        "keywords": ["鑼呭彴閰?, "鐧介厭", "绯诲垪閰?],
        "businessDescription": "鏍稿績鏄厭绫讳骇鍝侀攢鍞紝鏀跺叆閫氬父鏉ヨ嚜鍑哄巶浠枫€佹笭閬撶粨鏋勩€侀攢閲忓拰楂樼浜у搧鍗犳瘮銆?,
        "priceDrivers": ["缁堢闇€姹?, "鍝佺墝鍔?, "娓犻亾缁撴瀯", "鍑哄巶浠疯皟鏁?, "浜у搧缁撴瀯鍗囩骇", "鏀跨瓥鐜"],
        "businessCategory": "product",
    },
    {
        "keywords": ["瀹剁敤绌鸿皟", "娑堣垂鐢靛櫒", "鍐扮", "娲楄。鏈?, "鍘ㄧ數"],
        "businessDescription": "鏍稿績鏄€愮敤娑堣垂鍝侀攢鍞紝鏀跺叆閫氬父鏉ヨ嚜閿€閲忋€丄SP銆佹笭閬撴姌鎵ｅ拰鏂板搧杩唬銆?,
        "priceDrivers": ["缁堢娑堣垂闇€姹?, "鍘熸潗鏂欎环鏍?, "娓犻亾鍘诲簱瀛?, "浠ユ棫鎹㈡柊鏀跨瓥", "浜у搧鍗囩骇"],
        "businessCategory": "product",
    },
    {
        "keywords": ["杞欢", "SaaS", "浜戞湇鍔?],
        "businessDescription": "杩欏潡鏇存帴杩戞寔缁湇鍔°€傚叕鍙搁€氳繃杞欢璁稿彲銆佽闃呮垨浜戞湇鍔℃寔缁悜瀹㈡埛浜や粯鑳藉姏锛屾敹鍏ラ€氬父鏉ヨ嚜瀹㈡埛鏁般€佺画璐圭巼鍜屽鍗曚环銆?,
        "priceDrivers": ["瀹㈡埛鎵╁紶", "缁垂鐜?, "ARPU", "浜у搧杩唬鑳藉姏", "琛屼笟鏁板瓧鍖栨姇鍏?],
        "businessCategory": "service",
    },
]

ASSET_MAPPING = {
    "鐜伴噾": [["璐у竵璧勯噾"], ["鎬荤幇閲?]],
    "搴旀敹娆?: [
        ["搴旀敹璐︽", "搴旀敹绁ㄦ嵁", "搴旀敹娆鹃」铻嶈祫"],
        ["搴旀敹璐︽", "鍏朵腑锛氬簲鏀剁エ鎹?, "搴旀敹娆鹃」铻嶈祫"],
        ["搴旀敹绁ㄦ嵁鍙婂簲鏀惰处娆?],
    ],
    "棰勪粯娆?: [["棰勪粯娆鹃」"]],
    "瀛樿揣": [["瀛樿揣"]],
    "鍏朵粬娴佸姩": [["鍏朵粬娴佸姩璧勪骇"]],
    "闀挎湡鎶曡祫": [
        ["闀挎湡鑲℃潈鎶曡祫", "鍏朵粬鏉冪泭宸ュ叿鎶曡祫"],
        ["闀挎湡鑲℃潈鎶曡祫", "鍏朵粬闈炴祦鍔ㄩ噾铻嶈祫浜?],
        ["闀挎湡鑲℃潈鎶曡祫"],
    ],
    "鍥哄畾璧勪骇": [["鍥哄畾璧勪骇"], ["鍏朵腑锛氬浐瀹氳祫浜?], ["鍥哄畾璧勪骇鍚堣"]],
    "鏃犲舰&鍟嗚獕": [["鏃犲舰璧勪骇", "鍟嗚獕"], ["鏃犲舰璧勪骇"]],
    "鍏朵粬鍥哄畾": [["鍏朵粬闈炴祦鍔ㄨ祫浜?]],
}

LIABILITY_MAPPING = {
    "鐭湡鍊熸": [["鐭湡鍊熸"]],
    "搴斾粯娆?: [
        ["搴斾粯璐︽", "搴斾粯绁ㄦ嵁"],
        ["搴斾粯璐︽", "搴斾粯绁ㄦ嵁鍙婂簲浠樿处娆?],
        ["搴斾粯绁ㄦ嵁鍙婂簲浠樿处娆?],
    ],
    "棰勬敹娆?: [["棰勬敹娆鹃」", "鍚堝悓璐熷€?], ["鍚堝悓璐熷€?], ["棰勬敹娆鹃」"]],
    "钖叕&绋?: [["搴斾粯鑱屽伐钖叕", "搴斾氦绋庤垂"]],
    "鍏朵粬娴佸姩": [["鍏朵粬娴佸姩璐熷€?]],
    "闀挎湡鍊熸": [["闀挎湡鍊熸"]],
    "鍏朵粬闈炴祦鍔?: [["鍏朵粬闈炴祦鍔ㄨ礋鍊?], ["鍏朵粬闈炴祦鍔ㄨ礋鍊哄悎璁?], ["闈炴祦鍔ㄨ礋鍊哄悎璁?]],
}

REVENUE_CANDIDATES = ["钀ヤ笟鎬绘敹鍏?, "钀ヤ笟鏀跺叆", "TOTAL_OPERATE_INCOME", "OPERATE_INCOME"]

NET_PROFIT_CANDIDATES = [
    "褰掑睘浜庢瘝鍏徃鎵€鏈夎€呯殑鍑€鍒╂鼎",
    "褰掑睘浜庢瘝鍏徃鑲′笢鐨勫噣鍒╂鼎",
    "褰掓瘝鍑€鍒╂鼎",
    "鍑€鍒╂鼎",
    "PARENT_NETPROFIT",
    "NETPROFIT_PARENT_COMPANY_OWNERS",
    "NETPROFIT",
]


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def temporary_disable_proxy_env():
    original_values = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
    try:
        for key in PROXY_ENV_KEYS:
            os.environ[key] = ""
        yield
    finally:
        for key, value in original_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def sanitize_cache_part(value: object) -> str:
    text = str(value).strip()
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in text)
    return safe or "default"


def cache_file_path(prefix: str, *parts: object) -> Path:
    filename = "__".join([sanitize_cache_part(prefix), *[sanitize_cache_part(part) for part in parts]])
    return CACHE_DIR / f"{filename}.json"


def load_cached_payload(prefix: str, *parts: object) -> dict | None:
    path = cache_file_path(prefix, *parts)
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as cache_file:
            print(f"[INFO] Cache hit: {path.name}")
            return json.load(cache_file)
    except json.JSONDecodeError:
        print(f"[WARN] Cache corrupted, rebuilding: {path.name}")
        path.unlink(missing_ok=True)
        return None


def save_cached_payload(payload: dict, prefix: str, *parts: object) -> dict:
    ensure_cache_dir()
    path = cache_file_path(prefix, *parts)
    with path.open("w", encoding="utf-8") as cache_file:
        json.dump(payload, cache_file, ensure_ascii=False, indent=2)
    print(f"[INFO] Cache saved: {path.name}")
    return payload


def parse_ak_value(value: object) -> float:
    if value is None or pd.isna(value) or value is False:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "")
    if not text or text in {"False", "None", "nan", "--"}:
        return 0.0

    multiplier = 1.0
    if text.endswith("浜?):
        multiplier = YI
        text = text[:-1]
    elif text.endswith("涓?):
        multiplier = 10000
        text = text[:-1]
    elif text.endswith("鍏?):
        text = text[:-1]

    return float(text) * multiplier


def to_yi(value: float) -> float:
    return round(value / YI, 2)


def normalize_period(period: str | None) -> str | None:
    if not period:
        return None
    cleaned = str(period).strip().replace("-", "").replace("/", "")
    if len(cleaned) != 8 or not cleaned.isdigit():
        raise ValueError("period 鏍煎紡搴斾负 YYYYMMDD锛屼緥濡?20250630")
    return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"


def normalize_years(years: str | None, default: int = 8) -> int:
    if not years:
        return default
    value = int(years)
    if value <= 0:
        raise ValueError("years 蹇呴』鏄鏁存暟")
    return value


def to_em_symbol(stock: str) -> str:
    stock = stock.strip()
    if stock.startswith(("SH", "SZ")):
        return stock.upper()
    if stock.startswith(("60", "68", "90")):
        return f"SH{stock}"
    return f"SZ{stock}"


def pick_value(row: pd.Series, field_groups: list[list[str]], item_name: str) -> float:
    for group in field_groups:
        matched = [field for field in group if field in row.index]
        if matched:
            total = sum(parse_ak_value(row.get(field)) for field in matched)
            return to_yi(total)

    print(f"[WARN] Balance field not matched for: {item_name}")
    print("[DEBUG] Available columns:")
    print(list(row.index))
    return 0.0


def build_tree_and_bar(row: pd.Series) -> tuple[dict, list[dict]]:
    asset_children = []
    liability_children = []
    bar_data: list[dict] = []

    for label, field_groups in ASSET_MAPPING.items():
        value = pick_value(row, field_groups, label)
        asset_children.append({"name": label, "value": value})
        bar_data.append({"name": label, "value": value, "type": "asset"})

    for label, field_groups in LIABILITY_MAPPING.items():
        value = pick_value(row, field_groups, label)
        liability_children.append({"name": label, "value": value})
        bar_data.append({"name": label, "value": value, "type": "liability"})

    tree_data = {
        "name": "璧勪骇璐熷€鸿〃",
        "children": [
            {"name": "璧勪骇", "children": asset_children},
            {"name": "璐熷€?, "children": liability_children},
        ],
    }
    return tree_data, bar_data


def generate_balance_conclusion(bar_data: list[dict]) -> str:
    asset_total = sum(item["value"] for item in bar_data if item["type"] == "asset")
    liability_total = sum(item["value"] for item in bar_data if item["type"] == "liability")
    lookup = {item["name"]: item["value"] for item in bar_data}

    cash_ratio = lookup.get("鐜伴噾", 0) / asset_total if asset_total else 0
    inventory_ratio = lookup.get("瀛樿揣", 0) / asset_total if asset_total else 0
    receivable_ratio = lookup.get("搴旀敹娆?, 0) / asset_total if asset_total else 0
    liability_ratio = liability_total / asset_total if asset_total else 0

    if liability_ratio < 0.5 and cash_ratio > 0.25:
        return "璐㈠姟缁撴瀯姣旇緝鍋ュ悍"
    if inventory_ratio > 0.2 or receivable_ratio > 0.2:
        return "瀛樿揣/搴旀敹鍘嬪姏杈冨ぇ"
    return "璧勪骇缁撴瀯闇€瑕佺户缁瀵?


def load_balance_sheet(stock: str) -> pd.DataFrame:
    print(f"[INFO] Fetching balance sheet, stock={stock}")
    with temporary_disable_proxy_env():
        df = ak.stock_financial_debt_ths(symbol=stock, indicator="鎸夋姤鍛婃湡")
    print("[DEBUG] Balance columns:")
    print(df.columns.tolist())
    return df


def get_balance_payload(stock: str, period: str | None) -> dict:
    normalized_period = normalize_period(period)
    df = load_balance_sheet(stock)

    if df is None or df.empty:
        raise ValueError(f"鏈幏鍙栧埌鑲＄エ {stock} 鐨勮祫浜ц礋鍊鸿〃鏁版嵁")

    df = df.copy()
    df["鎶ュ憡鏈焈dt"] = pd.to_datetime(df["鎶ュ憡鏈?], errors="coerce")
    df = df.sort_values("鎶ュ憡鏈焈dt", ascending=False)

    if normalized_period:
        df = df[df["鎶ュ憡鏈?] == normalized_period]
        if df.empty:
            raise ValueError(f"鏈壘鍒拌偂绁?{stock} 鍦?{normalized_period} 鐨勬姤鍛婃湡鏁版嵁")

    row = df.iloc[0]
    tree_data, bar_data = build_tree_and_bar(row)

    return {
        "stock": stock,
        "title": f"{stock} 璧勪骇璐熷€鸿〃",
        "reportDate": row["鎶ュ憡鏈?],
        "unit": "浜垮厓",
        "treeData": tree_data,
        "barData": bar_data,
        "conclusion": generate_balance_conclusion(bar_data),
    }


def load_profit_sheet(stock: str) -> pd.DataFrame:
    em_symbol = to_em_symbol(stock)
    print(f"[INFO] Fetching quarterly profit sheet, symbol={em_symbol}")
    with temporary_disable_proxy_env():
        df = ak.stock_profit_sheet_by_quarterly_em(symbol=em_symbol)
    print("[DEBUG] Profit columns:")
    print(df.columns.tolist())
    return df


def load_market_cap(stock: str, years: int) -> pd.DataFrame:
    if years <= 1:
        period = "杩戜竴骞?
    elif years <= 3:
        period = "杩戜笁骞?
    elif years <= 5:
        period = "杩戜簲骞?
    elif years <= 10:
        period = "杩戝崄骞?
    else:
        period = "鍏ㄩ儴"

    print(f"[INFO] Fetching valuation, stock={stock}, period={period}")
    with temporary_disable_proxy_env():
        df = ak.stock_zh_valuation_baidu(symbol=stock, indicator="鎬诲競鍊?, period=period)
    print("[DEBUG] Valuation columns:")
    print(df.columns.tolist())
    return df


def find_revenue_column(df: pd.DataFrame) -> str:
    for column in REVENUE_CANDIDATES:
        if column in df.columns:
            return column

    print("[ERROR] Revenue field not matched, available columns:")
    print(df.columns.tolist())
    raise ValueError("鍒╂鼎琛ㄤ腑鏈壘鍒拌惀涓氭€绘敹鍏ュ瓧娈碉紝璇锋煡鐪嬪悗绔墦鍗扮殑 columns")


def find_net_profit_column(df: pd.DataFrame) -> str:
    for column in NET_PROFIT_CANDIDATES:
        if column in df.columns:
            return column

    print("[ERROR] Net profit field not matched, available columns:")
    print(df.columns.tolist())
    raise ValueError("鍒╂鼎琛ㄤ腑鏈壘鍒板噣鍒╂鼎瀛楁锛岃鏌ョ湅鍚庣鎵撳嵃鐨?columns")


def build_revenue_bars(df: pd.DataFrame, years: int) -> list[dict]:
    if df is None or df.empty:
        raise ValueError("鏈幏鍙栧埌鍒╂鼎琛ㄦ暟鎹?)

    revenue_column = find_revenue_column(df)
    date_column = "REPORT_DATE" if "REPORT_DATE" in df.columns else "鎶ュ憡鏈?
    if date_column not in df.columns:
        print("[ERROR] Profit date field not matched, available columns:")
        print(df.columns.tolist())
        raise ValueError("鍒╂鼎琛ㄤ腑鏈壘鍒版姤鍛婃湡瀛楁锛岃鏌ョ湅鍚庣鎵撳嵃鐨?columns")

    revenue_df = df[[date_column, revenue_column]].copy()
    revenue_df["date"] = pd.to_datetime(revenue_df[date_column], errors="coerce")
    revenue_df["value"] = revenue_df[revenue_column].apply(parse_ak_value)
    revenue_df = revenue_df.dropna(subset=["date"]).sort_values("date")

    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(years=years)
    revenue_df = revenue_df[revenue_df["date"] >= cutoff]
    if revenue_df.empty:
        raise ValueError(f"鏈€杩?{years} 骞存病鏈夊彲鐢ㄧ殑钀ヤ笟鏀跺叆鏁版嵁")

    return [
        {"date": row.date.strftime("%Y-%m-%d"), "value": to_yi(row.value)}
        for row in revenue_df.itertuples()
    ]


def build_profit_bars(df: pd.DataFrame, years: int) -> list[dict]:
    if df is None or df.empty:
        raise ValueError("鏈幏鍙栧埌鍒╂鼎琛ㄦ暟鎹?)

    profit_column = find_net_profit_column(df)
    date_column = "REPORT_DATE" if "REPORT_DATE" in df.columns else "鎶ュ憡鏈?
    if date_column not in df.columns:
        print("[ERROR] Profit date field not matched, available columns:")
        print(df.columns.tolist())
        raise ValueError("鍒╂鼎琛ㄤ腑鏈壘鍒版姤鍛婃湡瀛楁锛岃鏌ョ湅鍚庣鎵撳嵃鐨?columns")

    profit_df = df[[date_column, profit_column]].copy()
    profit_df["date"] = pd.to_datetime(profit_df[date_column], errors="coerce")
    profit_df["value"] = profit_df[profit_column].apply(parse_ak_value)
    profit_df = profit_df.dropna(subset=["date"]).sort_values("date")

    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(years=years)
    profit_df = profit_df[profit_df["date"] >= cutoff]
    if profit_df.empty:
        raise ValueError(f"鏈€杩?{years} 骞存病鏈夊彲鐢ㄧ殑鍑€鍒╂鼎鏁版嵁")

    return [
        {"date": row.date.strftime("%Y-%m-%d"), "value": to_yi(row.value)}
        for row in profit_df.itertuples()
    ]


def build_market_cap_line(df: pd.DataFrame, years: int, report_points: list[dict]) -> list[dict]:
    if df is None or df.empty:
        raise ValueError("鏈幏鍙栧埌鎬诲競鍊兼暟鎹?)

    if "date" not in df.columns or "value" not in df.columns:
        print("[ERROR] Valuation fields not matched, available columns:")
        print(df.columns.tolist())
        raise ValueError("鎬诲競鍊兼暟鎹瓧娈典笉绗﹀悎棰勬湡锛岃鏌ョ湅鍚庣鎵撳嵃鐨?columns")

    line_df = df[["date", "value"]].copy()
    line_df["date"] = pd.to_datetime(line_df["date"], errors="coerce")
    line_df["value"] = pd.to_numeric(line_df["value"], errors="coerce")
    line_df = line_df.dropna(subset=["date", "value"]).sort_values("date")

    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(years=years)
    line_df = line_df[line_df["date"] >= cutoff]
    if line_df.empty:
        raise ValueError(f"鏈€杩?{years} 骞存病鏈夊彲鐢ㄧ殑鎬诲競鍊兼暟鎹?)

    report_dates = []
    for item in report_points:
        report_date = pd.to_datetime(item["date"], errors="coerce")
        if pd.notna(report_date):
            report_dates.append(report_date.normalize())

    if not report_dates:
        raise ValueError("鏈幏鍙栧埌鍙敤浜庡榻愬競鍊肩殑鎶ュ憡鏈熸棩鏈?)

    quarterly_points: list[dict] = []
    for report_date in report_dates:
        matched = line_df[line_df["date"] <= report_date]
        if matched.empty:
            continue

        latest_row = matched.iloc[-1]
        quarterly_points.append(
            {
                "date": report_date.strftime("%Y-%m-%d"),
                "value": round(float(latest_row["value"]), 2),
            }
        )

    if not quarterly_points:
        raise ValueError(f"鏈€杩?{years} 骞存病鏈夊彲鐢ㄤ簬瀛ｅ害瀵归綈鐨勬€诲競鍊兼暟鎹?)

    return quarterly_points


def generate_revenue_market_cap_conclusion(
    revenue_bars: list[dict], market_cap_line: list[dict]
) -> str:
    if not revenue_bars or not market_cap_line:
        return "涓氱哗澧為暱鍜屽競鍊艰蛋鍔块渶瑕佺粨鍚堣瀵?

    revenue_growth = revenue_bars[-1]["value"] - revenue_bars[0]["value"]
    market_cap_growth = market_cap_line[-1]["value"] - market_cap_line[0]["value"]

    if revenue_growth > 0 and market_cap_growth <= 0:
        return "濡傛灉涓氱哗澧為暱浣嗗競鍊间笉娑紝鍙兘鏄及鍊煎帇缂?
    if revenue_growth > 0 and market_cap_growth > revenue_growth:
        return "濡傛灉甯傚€兼定寰楁瘮涓氱哗蹇紝鍙兘鏄及鍊兼墿寮?
    return "涓氱哗澧為暱鍜屽競鍊艰蛋鍔块渶瑕佺粨鍚堣瀵?


def generate_profit_market_cap_conclusion(
    profit_bars: list[dict], market_cap_line: list[dict]
) -> str:
    if not profit_bars or not market_cap_line:
        return "鍑€鍒╂鼎鍜屽競鍊艰蛋鍔块渶瑕佺粨鍚堣瀵?

    profit_growth = profit_bars[-1]["value"] - profit_bars[0]["value"]
    market_cap_growth = market_cap_line[-1]["value"] - market_cap_line[0]["value"]

    if profit_growth > 0 and market_cap_growth <= 0:
        return "濡傛灉鍑€鍒╂鼎澧為暱浣嗗競鍊间笉娑紝鍙兘鏄及鍊煎帇缂?
    if profit_growth <= 0 and market_cap_growth > 0:
        return "濡傛灉鍑€鍒╂鼎涓嬮檷浣嗗競鍊间笂娑紝鍙兘鏄競鍦哄湪鎻愬墠浜ゆ槗棰勬湡"
    if profit_growth > 0 and market_cap_growth > profit_growth:
        return "濡傛灉甯傚€兼定寰楁瘮鍑€鍒╂鼎蹇紝鍙兘鏄及鍊兼墿寮?
    return "鍑€鍒╂鼎鍜屽競鍊艰蛋鍔块渶瑕佺粨鍚堣瀵?


def get_revenue_market_cap_payload(stock: str, years: int) -> dict:
    revenue_bars = build_revenue_bars(load_profit_sheet(stock), years)
    market_cap_line = build_market_cap_line(load_market_cap(stock, years), years, revenue_bars)

    return {
        "stock": stock,
        "title": f"{stock} 甯傚€间笌涓氱哗澧為暱瓒嬪娍",
        "unit": "浜垮厓",
        "leftAxisName": "钀ヤ笟鎬绘敹鍏?,
        "rightAxisName": "鎬诲競鍊?,
        "revenueBars": revenue_bars,
        "marketCapLine": market_cap_line,
        "conclusion": generate_revenue_market_cap_conclusion(revenue_bars, market_cap_line),
    }


def get_profit_market_cap_payload(stock: str, years: int) -> dict:
    profit_bars = build_profit_bars(load_profit_sheet(stock), years)
    market_cap_line = build_market_cap_line(load_market_cap(stock, years), years, profit_bars)

    return {
        "stock": stock,
        "title": f"{stock} 鍑€鍒╂鼎涓庡競鍊煎姣?,
        "unit": "浜垮厓",
        "leftAxisName": "褰掓瘝鍑€鍒╂鼎",
        "rightAxisName": "鎬诲競鍊?,
        "profitBars": profit_bars,
        "marketCapLine": market_cap_line,
        "conclusion": generate_profit_market_cap_conclusion(profit_bars, market_cap_line),
    }


def valuation_period_from_years(years: int) -> str:
    if years <= 1:
        return "杩戜竴骞?
    if years <= 3:
        return "杩戜笁骞?
    if years <= 5:
        return "杩戜簲骞?
    if years <= 10:
        return "杩戝崄骞?
    return "鍏ㄩ儴"


def load_pe_ttm(stock: str, years: int) -> pd.DataFrame:
    period = valuation_period_from_years(years)
    print(f"[INFO] Fetching PE TTM, stock={stock}, period={period}")

    with temporary_disable_proxy_env():
        df = ak.stock_zh_valuation_baidu(
            symbol=stock,
            indicator="甯傜泩鐜?TTM)",
            period=period,
        )

    print("[DEBUG] PE columns:")
    print(df.columns.tolist())
    return df


def build_pe_trend_payload(stock: str, years: int) -> dict:
    df = load_pe_ttm(stock, years)

    if df is None or df.empty:
        raise ValueError("鏈幏鍙栧埌甯傜泩鐜囨暟鎹?)

    if "date" not in df.columns or "value" not in df.columns:
        print("[ERROR] PE fields not matched, available columns:")
        print(df.columns.tolist())
        raise ValueError("甯傜泩鐜囨暟鎹瓧娈典笉绗﹀悎棰勬湡锛岃鏌ョ湅鍚庣鎵撳嵃鐨?columns")

    pe_df = df[["date", "value"]].copy()
    pe_df["date"] = pd.to_datetime(pe_df["date"], errors="coerce")
    pe_df["value"] = pd.to_numeric(pe_df["value"], errors="coerce")

    # 淇濇寔浣犲綋鍓嶉€昏緫锛氬彧灞曠ず姝ｅ競鐩堢巼銆?    pe_df = pe_df.dropna(subset=["date", "value"])
    pe_df = pe_df[pe_df["value"] > 0]
    pe_df = pe_df.sort_values("date")

    cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(years=years)
    pe_df = pe_df[pe_df["date"] >= cutoff]

    if pe_df.empty:
        raise ValueError(f"鏈€杩?{years} 骞存病鏈夊彲鐢ㄧ殑甯傜泩鐜囨暟鎹?)

    mean_line = round(float(pe_df["value"].mean()), 2)

    # 淇濇寔浣犲綋鍓嶉€昏緫锛氬潎鍊肩嚎涓婁笅鍚?1 涓爣鍑嗗樊銆?    std_value = float(pe_df["value"].std())
    low_line = round(max(0, mean_line - std_value), 2)
    high_line = round(mean_line + std_value, 2)

    pe_line = [
        {
            "date": row.date.strftime("%Y-%m-%d"),
            "value": round(float(row.value), 2),
        }
        for row in pe_df.itertuples()
    ]

    latest_pe = pe_line[-1]["value"]
    if latest_pe <= low_line:
        conclusion = "褰撳墠甯傜泩鐜囨帴杩戜綆浼板尯闂?
    elif latest_pe >= high_line:
        conclusion = "褰撳墠甯傜泩鐜囨帴杩戦珮浼板尯闂?
    else:
        conclusion = "褰撳墠甯傜泩鐜囧浜庢甯镐及鍊煎尯闂?

    return {
        "stock": stock,
        "title": f"{stock} 甯傜泩鐜囪秼鍔?,
        "unit": "鍊?,
        "peLine": pe_line,
        "meanLine": mean_line,
        "lowLine": low_line,
        "highLine": high_line,
        "conclusion": conclusion,
    }


def normalize_openai_base_url(base_url: str | None) -> str:
    text = (base_url or DEFAULT_OPENAI_BASE_URL).strip().rstrip("/")
    if not text:
        text = DEFAULT_OPENAI_BASE_URL
    if not text.endswith("/v1"):
        text = f"{text}/v1"
    return text


def get_openai_settings() -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing OPENAI_API_KEY. Please configure it in your local environment before using /api/ai-analysis.")

    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    base_url = normalize_openai_base_url(os.getenv("OPENAI_BASE_URL"))

    temperature_text = os.getenv("OPENAI_TEMPERATURE", str(DEFAULT_OPENAI_TEMPERATURE)).strip()
    try:
        temperature = float(temperature_text)
    except ValueError as exc:
        raise ValueError("OPENAI_TEMPERATURE must be a number.") from exc

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
    }


def get_balance_payload_with_cache(stock: str, period: str | None) -> dict:
    normalized_period = normalize_period(period)
    cached_payload = load_cached_payload("balance", stock, normalized_period or "latest")
    if cached_payload is not None:
        return cached_payload

    payload = get_balance_payload(stock=stock, period=period)
    save_cached_payload(payload, "balance", stock, normalized_period or "latest")
    return payload


def get_revenue_market_cap_payload_with_cache(stock: str, years: int) -> dict:
    cached_payload = load_cached_payload("revenue_market_cap_v2", stock, years)
    if cached_payload is not None:
        return cached_payload

    payload = get_revenue_market_cap_payload(stock=stock, years=years)
    save_cached_payload(payload, "revenue_market_cap_v2", stock, years)
    return payload


def get_profit_market_cap_payload_with_cache(stock: str, years: int) -> dict:
    cached_payload = load_cached_payload("profit_market_cap_v1", stock, years)
    if cached_payload is not None:
        return cached_payload

    payload = get_profit_market_cap_payload(stock=stock, years=years)
    save_cached_payload(payload, "profit_market_cap_v1", stock, years)
    return payload


def get_pe_trend_payload_with_cache(stock: str, years: int) -> dict:
    cached_payload = load_cached_payload("pe_trend_v1", stock, years)
    if cached_payload is not None:
        return cached_payload

    payload = build_pe_trend_payload(stock=stock, years=years)
    save_cached_payload(payload, "pe_trend_v1", stock, years)
    return payload


def load_company_profile(stock: str) -> pd.DataFrame:
    print(f"[INFO] Fetching company profile, stock={stock}")
    with temporary_disable_proxy_env():
        df = ak.stock_profile_cninfo(symbol=stock)
    print("[DEBUG] Company profile columns:")
    print(df.columns.tolist())
    return df


def load_main_business_composition(stock: str) -> pd.DataFrame:
    symbol = to_em_symbol(stock)
    print(f"[INFO] Fetching main business composition, symbol={symbol}")
    with temporary_disable_proxy_env():
        df = ak.stock_zygc_em(symbol=symbol)
    print("[DEBUG] Main business columns:")
    print(df.columns.tolist())
    return df


def get_company_profile_payload_with_cache(stock: str) -> dict:
    cached_payload = load_cached_payload("company_profile_v1", stock)
    if cached_payload is not None:
        return cached_payload

    df = load_company_profile(stock)
    if df is None or df.empty:
        raise ValueError(f"Unable to fetch company profile for stock {stock}.")

    row = df.iloc[0]
    payload = {
        "stock": stock,
        "companyName": row.get("鍏徃鍚嶇О", ""),
        "industry": row.get("鎵€灞炶涓?, ""),
        "mainBusiness": row.get("涓昏惀涓氬姟", ""),
        "businessScope": row.get("缁忚惀鑼冨洿", ""),
        "companyIntro": row.get("鏈烘瀯绠€浠?, ""),
    }
    save_cached_payload(payload, "company_profile_v1", stock)
    return payload


def get_main_business_payload_with_cache(stock: str) -> dict:
    cached_payload = load_cached_payload("main_business_v1", stock)
    if cached_payload is not None:
        return cached_payload

    df = load_main_business_composition(stock)
    if df is None or df.empty:
        raise ValueError(f"Unable to fetch main business composition for stock {stock}.")

    df = df.copy()
    if "鎶ュ憡鏃ユ湡" in df.columns:
        df["鎶ュ憡鏃ユ湡_dt"] = pd.to_datetime(df["鎶ュ憡鏃ユ湡"], errors="coerce")
        latest_date = df["鎶ュ憡鏃ユ湡_dt"].max()
        if pd.notna(latest_date):
            df = df[df["鎶ュ憡鏃ユ湡_dt"] == latest_date]

    summary_items = []
    for row in df.itertuples(index=False):
        row_dict = row._asdict()
        summary_items.append(
            {
                "reportDate": str(row_dict.get("鎶ュ憡鏃ユ湡") or ""),
                "categoryType": row_dict.get("鍒嗙被绫诲瀷"),
                "itemName": row_dict.get("涓昏惀鏋勬垚"),
                "revenue": to_yi(parse_ak_value(row_dict.get("涓昏惀鏀跺叆"))),
                "revenueRatio": round(float(row_dict.get("鏀跺叆姣斾緥", 0) or 0), 4),
                "cost": to_yi(parse_ak_value(row_dict.get("涓昏惀鎴愭湰"))),
                "costRatio": round(float(row_dict.get("鎴愭湰姣斾緥", 0) or 0), 4),
                "profit": to_yi(parse_ak_value(row_dict.get("涓昏惀鍒╂鼎"))),
                "profitRatio": round(float(row_dict.get("鍒╂鼎姣斾緥", 0) or 0), 4),
                "grossMargin": round(float(row_dict.get("姣涘埄鐜?, 0) or 0), 4),
            }
        )

    payload = {
        "stock": stock,
        "items": summary_items,
    }
    save_cached_payload(payload, "main_business_v1", stock)
    return payload


def is_supplementary_item(item_name: str) -> bool:
    normalized_name = (item_name or "").strip()
    return (
        not normalized_name
        or "鍏朵粬" in normalized_name
        or "琛ュ厖" in normalized_name
        or "鎶甸攢" in normalized_name
        or "鐩镐簰鎶甸攢" in normalized_name
    )


def filter_business_items(items: list[dict], category_type: str) -> list[dict]:
    filtered_items = [
        sanitize_business_item(item)
        for item in items
        if item.get("categoryType") == category_type and not is_supplementary_item(item.get("itemName", ""))
    ]
    return sorted(filtered_items, key=lambda item: item.get("revenue") or 0, reverse=True)


def build_dominance_summary(items: list[dict]) -> dict | None:
    if not items:
        return None

    leader = items[0]
    ratio = float(leader.get("revenueRatio", 0) or 0)
    return {
        "itemName": leader.get("itemName", ""),
        "revenue": leader.get("revenue", 0),
        "revenueRatio": round(ratio, 4),
        "isHighlyConcentrated": ratio >= 0.6,
    }


def build_margin_summary(items: list[dict]) -> dict | None:
    if not items:
        return None

    finite_items = [item for item in items if item.get("grossMargin") is not None]
    if not finite_items:
        return None

    sorted_items = sorted(finite_items, key=lambda item: item.get("grossMargin") or 0, reverse=True)
    leader = sorted_items[0]
    return {
        "itemName": leader.get("itemName", ""),
        "grossMargin": round(float(leader.get("grossMargin", 0) or 0), 4),
        "revenue": leader.get("revenue", 0),
        "revenueRatio": round(float(leader.get("revenueRatio", 0) or 0), 4),
    }


def parse_percentage_value(raw_value: str) -> float:
    cleaned = (raw_value or "").replace(",", "").replace("%", "").strip()
    if not cleaned:
        return 0.0
    return float(cleaned) / 100


def sanitize_numeric(value: object) -> float | None:
    if value is None:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric_value):
        return None
    return numeric_value


def sanitize_business_item(item: dict) -> dict:
    sanitized = dict(item)
    numeric_fields = [
        "revenue",
        "revenueRatio",
        "cost",
        "costRatio",
        "profit",
        "profitRatio",
        "grossMargin",
        "revenueGrowth",
        "costGrowth",
    ]
    for field in numeric_fields:
        if field in sanitized:
            sanitized[field] = sanitize_numeric(sanitized.get(field))
    return sanitized


POSITIONING_WATCH_METRICS = {
    "product": ["閿€閲?, "鍗曚环", "姣涘埄鐜?, "瀛樿揣鍛ㄨ浆", "娓犻亾缁撴瀯"],
    "service": ["璁㈠崟閲?, "灞ョ害鑳藉姏", "鍒╃敤鐜?, "鍗曚綅鏈嶅姟浠锋牸", "鍥炴鏁堢巼"],
    "platform": ["GMV", "鎶戒剑鐜?, "鍟嗗鏁?, "娲昏穬鐢ㄦ埛", "骞垮憡/鏈嶅姟璐瑰彉鐜?],
}


def _positioning_keywords() -> dict[str, list[str]]:
    return {
        "product": [
            "浜у搧",
            "鍟嗗搧",
            "鐧介厭",
            "瀹剁數",
            "璁惧",
            "鑽搧",
            "鑺墖",
            "姹借溅",
            "鏉愭枡",
            "鍒堕€?,
            "鐢熶骇",
            "闆堕儴浠?,
        ],
        "service": [
            "鏈嶅姟",
            "鑸繍",
            "鐗╂祦",
            "杩愯緭",
            "绉熻祦",
            "娓彛",
            "鐮佸ご",
            "浜や粯",
            "灞ョ害",
            "宸ョ▼",
            "杩愮淮",
        ],
        "platform": [
            "骞冲彴",
            "浣ｉ噾",
            "鎶戒剑",
            "骞垮憡",
            "鎾悎",
            "淇℃伅鏈嶅姟",
            "鎶€鏈湇鍔¤垂",
            "鍟嗗",
            "鐢ㄦ埛",
            "娴侀噺",
            "浜ゆ槗鏈嶅姟",
            "鏈嶅姟璐?,
            "浼氬憳璐?,
        ],
    }


def build_positioning_evidence_item(signal_type: str, label: str, detail: str) -> dict:
    return {
        "type": signal_type,
        "label": label,
        "detail": detail,
    }


def infer_company_positioning(
    company_main_business: str,
    industry: str,
    product_items: list[dict],
    channel_items: list[dict] | None = None,
) -> dict:
    keywords = _positioning_keywords()
    item_names = [str(item.get("itemName", "")).strip() for item in product_items if str(item.get("itemName", "")).strip()]
    top_item_names = item_names[:3]
    top_items_text = "銆?.join(top_item_names)
    channel_names = [str(item.get("itemName", "")).strip() for item in (channel_items or []) if str(item.get("itemName", "")).strip()]
    search_text = " ".join(top_item_names + channel_names + [company_main_business or "", industry or ""])

    score_map = {"product": 0.0, "service": 0.0, "platform": 0.0}
    evidence_map = {"product": [], "service": [], "platform": []}

    def add_signal(target: str, score: float, signal_type: str, label: str, detail: str) -> None:
        score_map[target] += score
        evidence_map[target].append(build_positioning_evidence_item(signal_type, label, detail))

    for target, keyword_list in keywords.items():
        matched = [keyword for keyword in keyword_list if keyword in search_text]
        if matched:
            sample = "銆?.join(matched[:3])
            label_map = {
                "product": "涓昏惀鎻忚堪鏇村儚鍗栬揣",
                "service": "涓昏惀鎻忚堪鏇村儚鍗栬兘鍔?,
                "platform": "涓昏惀鎻忚堪鏇村儚骞冲彴鏀惰垂",
            }
            detail_map = {
                "product": f"涓昏惀涓氬姟銆佽涓氭垨鏀跺叆椤归噷鍑虹幇浜?{sample} 绛夎〃杩帮紝鏇存帴杩戣嚜鏈夊晢鍝佹垨璁惧閿€鍞€?,
                "service": f"涓昏惀涓氬姟銆佽涓氭垨鏀跺叆椤归噷鍑虹幇浜?{sample} 绛夎〃杩帮紝鏇存帴杩戣繍杈撱€佷氦浠樸€佺璧佹垨宸ョ▼鏈嶅姟銆?,
                "platform": f"涓昏惀涓氬姟銆佽涓氭垨鏀跺叆椤归噷鍑虹幇浜?{sample} 绛夎〃杩帮紝鏇存帴杩戜剑閲戙€佸箍鍛婃垨鎾悎鏀惰垂銆?,
            }
            add_signal(target, 1.6 if target != "platform" else 2.0, "keyword", label_map[target], detail_map[target])

    if product_items:
        top_item = product_items[0]
        top_ratio = float(top_item.get("revenueRatio") or 0)
        top_margin = top_item.get("grossMargin")
        if top_ratio >= 0.5 and top_items_text:
            add_signal(
                "product",
                1.0,
                "revenue_structure",
                "鏀跺叆鎸夊叿浣撳搧绫绘媶鍒嗚緝鏄庢樉",
                f"鍓嶅嚑澶ф敹鍏ラ」闆嗕腑鍦?{top_items_text}锛屾洿鍍忔寜鍏蜂綋鍟嗗搧鎴栦骇鍝佺嚎绠＄悊鏀跺叆銆?,
            )
        if top_margin is not None and float(top_margin) >= 0.45:
            add_signal(
                "platform",
                0.8,
                "margin_profile",
                "楂樻瘺鍒╂洿鍍忚交璧勪骇鏀惰垂",
                "鏍稿績鏀跺叆椤规瘺鍒╃巼杈冮珮锛屽拰骞冲彴鍨嬪叕鍙稿父瑙佺殑浣ｉ噾銆佸箍鍛婃垨鎶€鏈湇鍔℃敹璐规洿鎺ヨ繎銆?,
            )

    if channel_names:
        direct_indicators = [name for name in channel_names if any(keyword in name for keyword in ["鐩磋惀", "缁忛攢", "绾夸笅", "闂ㄥ簵"])]
        if direct_indicators:
            add_signal(
                "product",
                0.7,
                "channel_structure",
                "娓犻亾鎷嗗垎鏇村儚鍗栬揣鍏徃",
                f"娓犻亾閲屽嚭鐜?{ '銆?.join(direct_indicators[:2]) } 绛夎〃杩帮紝璇存槑鍏徃鏇村儚鍥寸粫鍟嗗搧閿€鍞潵缁勭粐娓犻亾銆?,
            )
        platform_indicators = [name for name in channel_names if any(keyword in name for keyword in ["骞冲彴", "绾夸笂", "骞垮憡", "鍟嗗", "鎾悎"])]
        if platform_indicators:
            add_signal(
                "platform",
                1.1,
                "channel_structure",
                "娓犻亾鎷嗗垎甯︽湁骞冲彴鐢熸€佺壒寰?,
                f"娓犻亾閲屽嚭鐜?{ '銆?.join(platform_indicators[:2]) } 绛夎〃杩帮紝璇存槑鏀跺叆鏇村彲鑳芥潵鑷钩鍙版祦閲忔垨浜ゆ槗鎾悎銆?,
            )

    if not any(score_map.values()):
        add_signal(
            "service",
            0.2,
            "fallback",
            "鍏紑绾跨储鏈夐檺",
            "褰撳墠鍏紑鎻忚堪涓嶈冻浠ュ己鍒ゅ叿浣撴ā寮忥紝鍏堟寜鏈嶅姟/涓氬姟鍗曞厓瑙嗚鐞嗚В涓昏惀鏀跺叆銆?,
        )

    sorted_scores = sorted(score_map.items(), key=lambda item: item[1], reverse=True)
    company_nature, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1]
    total_score = sum(score_map.values())
    confidence = 0.45 if total_score <= 0 else min(0.95, round(0.45 + max(top_score - second_score, 0) / max(total_score, 1) * 0.5, 2))

    primary_unit_label = {
        "product": "浜у搧",
        "service": "涓氬姟",
        "platform": "骞冲彴涓氬姟",
    }[company_nature]
    rationale_map = {
        "product": "杩欏鍏徃鏇村儚闈犻攢鍞嚜鏈夊晢鍝佹垨璁惧璧氶挶锛屾墍浠ユ媶鏀跺叆鏃剁洿鎺ユ寜浜у搧绾跨湅鏈€鍚堥€傘€?,
        "service": "杩欏鍏徃鏇村儚鍗栬繍杈撱€佷氦浠樸€佺璧佹垨宸ョ▼鑳藉姏锛屾墍浠ヨ繖閲岀殑鈥滄寜浜у搧鈥濇洿閫傚悎鐞嗚В鎴愨€滄寜涓氬姟鍗曞厓鈥濈湅銆?,
        "platform": "杩欏鍏徃鏇村儚閫氳繃鎾悎銆佹祦閲忋€佸箍鍛婃垨鎶€鏈湇鍔℃敹璐硅禋閽憋紝鎵€浠ヨ繖閲岀殑鏍稿績涓嶆槸鍗栬揣锛岃€屾槸鐪嬪钩鍙颁笟鍔℃€庝箞鍙樼幇銆?,
    }

    support_evidence = evidence_map[company_nature][:4]
    conflict_evidence = []
    for other_type, _score in sorted_scores[1:]:
        if score_map[other_type] <= 0:
            continue
        dominant_label = {
            "product": "浠嶆湁鍗栬揣鐗瑰緛",
            "service": "浠嶆湁鏈嶅姟灞ョ害鐗瑰緛",
            "platform": "浠嶆湁骞冲彴鏀惰垂鐗瑰緛",
        }[other_type]
        dominant_detail = {
            "product": "閮ㄥ垎鎻忚堪浠嶇劧鍍忚嚜钀ュ晢鍝佹垨璁惧閿€鍞紝璇存槑瀹冧笉涓€瀹氭槸绾交璧勪骇妯″紡銆?,
            "service": "閮ㄥ垎鎻忚堪浠嶇劧鍍忚繍杈撱€佷氦浠樻垨宸ョ▼灞ョ害锛岃鏄庡畠涓嶅彧鏄崟绾崠璐с€?,
            "platform": "閮ㄥ垎鎻忚堪浠嶇劧鍍忓钩鍙版娊浣ｃ€佸箍鍛婃垨鎾悎鏀惰垂锛岃鏄庡畠鍙兘甯︽湁骞冲彴鐢熸€併€?,
        }[other_type]
        conflict_evidence.append(build_positioning_evidence_item("cross_signal", dominant_label, dominant_detail))

    return {
        "companyNature": company_nature,
        "confidence": confidence,
        "primaryUnitLabel": primary_unit_label,
        "rationale": rationale_map[company_nature],
        "evidence": {
            "supports": support_evidence,
            "conflicts": conflict_evidence[:3],
        },
        "watchMetrics": POSITIONING_WATCH_METRICS[company_nature],
    }


def build_interpreted_main_business_summary(
    company_main_business: str,
    company_positioning: dict,
    product_items: list[dict],
) -> str:
    top_item_names = [str(item.get("itemName", "")).strip() for item in product_items[:2] if str(item.get("itemName", "")).strip()]
    top_items_text = "銆?.join(top_item_names)
    company_nature = company_positioning.get("companyNature", "service")

    if company_nature == "service":
        if top_items_text:
            return f"鍙互鎶婂畠鐞嗚В鎴愪竴瀹朵互{top_items_text}涓烘牳蹇冪殑鏈嶅姟鍨嬪叕鍙搞€傚畠涓昏涓嶆槸鍗栧疄浣撲骇鍝侊紝鑰屾槸鍚戝鎴峰嚭鍞繍杈撱€佷氦浠樸€佺璧佹垨缁勭粐鑳藉姏銆?
        return "鍙互鎶婂畠鐞嗚В鎴愪竴瀹舵湇鍔″瀷鍏徃銆傚畠涓昏涓嶆槸鍗栧疄浣撲骇鍝侊紝鑰屾槸鍚戝鎴峰嚭鍞繍杈撱€佷氦浠樸€佺璧佹垨鐗╂祦鑳藉姏銆?

    if company_nature == "product":
        if top_items_text:
            return f"鍙互鎶婂畠鐞嗚В鎴愪竴瀹朵互{top_items_text}涓烘牳蹇冪殑浜у搧鍨嬪叕鍙搞€傚畠涓昏閫氳繃閿€鍞嚜宸辩殑鍟嗗搧銆佽澶囨垨娑堣垂鍝佹潵璧氶挶锛屼环鏍煎拰閿€閲忛€氬父鏄渶鍏抽敭鐨勮瀵熺偣銆?
        return "鍙互鎶婂畠鐞嗚В鎴愪竴瀹朵骇鍝佸瀷鍏徃銆傚畠涓昏閫氳繃閿€鍞嚜宸辩殑鍟嗗搧銆佽澶囨垨娑堣垂鍝佹潵璧氶挶銆?

    if top_items_text:
        return f"鍙互鎶婂畠鐞嗚В鎴愪竴瀹朵互{top_items_text}涓烘牳蹇冪殑骞冲彴鍨嬪叕鍙搞€傚畠鏇村儚闈犳挳鍚堜氦鏄撱€佸箍鍛婃垨鎶€鏈湇鍔℃敹璐硅禋閽憋紝閲嶇偣涓嶆槸鍥よ揣锛岃€屾槸骞冲彴鐢熸€佸拰鍙樼幇鏁堢巼銆?
    return "鍙互鎶婂畠鐞嗚В鎴愪竴瀹跺钩鍙板瀷鍏徃銆傚畠鏇村儚闈犳挳鍚堜氦鏄撱€佸箍鍛婃垨鎶€鏈湇鍔℃敹璐硅禋閽憋紝鑰屼笉鏄緷璧栨寔鏈夎揣鐗╄禋浠峰樊銆?


def infer_business_explanation(
    item_name: str,
    company_main_business: str,
    industry: str,
    dimension: str,
    company_positioning: dict,
) -> dict:
    if dimension == "region":
        return {
            "businessDescription": "杩欎笉鏄崟鐙殑涓€椤逛骇鍝佹垨鏈嶅姟锛岃€屾槸鍏徃鍦ㄨ繖涓湴鍖烘嬁鍒扮殑鏀跺叆銆傜湅鍦板尯鎷嗗垎锛屼富瑕佹槸涓轰簡鍒ゆ柇鍏徃渚濊禆鍝簺甯傚満锛屼互鍙婃捣澶栧拰鍥藉唴鐨勯渶姹傚樊寮傘€?,
            "priceDrivers": ["鍖哄煙闇€姹傛櫙姘斿害", "褰撳湴杩愪环鎴栨姤浠锋按骞?, "姹囩巼", "璐告槗鏀跨瓥", "绔炰簤鏍煎眬"],
        }

    if dimension == "channel":
        return {
            "businessDescription": "杩欎笉鏄骇鍝佸垎绫伙紝鑰屾槸鏀跺叆閫氳繃浠€涔堥攢鍞垨浜や粯娓犻亾瀹炵幇銆傜湅娓犻亾鎷嗗垎锛屼富瑕佹槸涓轰簡鍒ゆ柇鍒╂鼎鏈夋病鏈夊洖娴佸埌鍏徃鑷繁鎵嬮噷銆?,
            "priceDrivers": ["鐩撮攢鍗犳瘮", "缁忛攢浣撶郴璁环鑳藉姏", "瀹㈡埛缁撴瀯", "娓犻亾璐圭敤", "鍥炴鏁堢巼"],
        }

    if dimension == "industry":
        return {
            "businessDescription": "杩欏弽鏄犵殑鏄叕鍙告妸鏀跺叆鍒嗛厤鍒板摢浜涜涓氭垨搴旂敤鍦烘櫙锛屼笉鏄崟鐙殑涓€娆句骇鍝併€傜湅杩欏潡涓昏鏄负浜嗗垽鏂叕鍙告渶缁堟湇鍔＄殑鏄摢浜涗笅娓搁渶姹傘€?,
            "priceDrivers": ["涓嬫父琛屼笟鏅皵搴?, "瀹㈡埛璧勬湰寮€鏀?, "琛屼笟闇€姹傛尝鍔?, "绔炰簤鏍煎眬", "瀹氫环鑳藉姏"],
        }

    search_sources = [item_name or "", company_main_business or "", industry or ""]
    item_text = search_sources[0]
    fallback_text = " ".join(search_sources[1:])
    for rule in BUSINESS_EXPLANATION_RULES:
        if any(keyword in item_text for keyword in rule["keywords"]):
            return {
                "businessDescription": rule["businessDescription"],
                "priceDrivers": rule["priceDrivers"],
            }

    for rule in BUSINESS_EXPLANATION_RULES:
        if any(keyword in fallback_text for keyword in rule["keywords"]):
            label = company_positioning.get("primaryUnitLabel", "涓氬姟")
            business_category = rule.get("businessCategory", "service")
            if business_category == "product":
                description = f"杩欏潡鍙互鐞嗚В鎴愬叕鍙哥殑涓€涓獅label}鍗曞厓锛屾牳蹇冭繕鏄洿缁曞叿浣撳晢鍝侀攢鍞睍寮€銆傚缓璁户缁粨鍚堝鎴风粨鏋勩€佹笭閬撶粨鏋勫拰鎴愭湰缁撴瀯涓€璧风湅銆?
            elif company_positioning.get("companyNature") == "platform":
                description = f"杩欏潡鏇撮€傚悎鐞嗚В鎴愬叕鍙哥殑涓€涓獅label}鍗曞厓锛屾牳蹇冧笉鏄寔鏈夎揣鐗╄禋宸环锛岃€屾槸鐪嬪钩鍙版祦閲忋€佸晢瀹剁敓鎬佸拰鏀惰垂鏁堢巼鎬庝箞鍙樸€?
            else:
                description = f"杩欏潡鏇撮€傚悎鐞嗚В鎴愬叕鍙哥殑涓€涓獅label}鍗曞厓锛屾牳蹇冨崠鐨勬槸杩愯緭銆佷氦浠樸€佽闃呮垨鍏朵粬鏈嶅姟鑳藉姏锛岃€屼笉鏄嫮涔変笂鐨勫疄浣撲骇鍝併€?
            return {
                "businessDescription": description,
                "priceDrivers": rule["priceDrivers"],
            }

    label = company_positioning.get("primaryUnitLabel", "涓氬姟")
    if company_positioning.get("companyNature") == "platform":
        return {
            "businessDescription": f"杩欐槸鍏徃涓昏惀鏀跺叆閲岀殑涓€涓獅label}鍗曞厓銆傚垽鏂畠閲嶈涓嶉噸瑕侊紝寤鸿浼樺厛鐪嬫祦閲忋€佸晢瀹剁敓鎬併€佹娊浣ｇ巼鍜屽钩鍙板彉鐜版晥鐜囷紝鑰屼笉鏄彧鐪嬪崠浜嗗灏戣揣銆?,
            "priceDrivers": ["娴侀噺澧為暱", "鍟嗗娲昏穬搴?, "鎶戒剑鐜?, "骞垮憡鍙樼幇", "绔炰簤鏍煎眬"],
        }
    return {
        "businessDescription": f"杩欐槸鍏徃涓昏惀鏀跺叆閲岀殑涓€涓獅label}鍗曞厓銆傚垽鏂畠閲嶈涓嶉噸瑕侊紝寤鸿涓€璧风湅瀹㈡埛鏄皝銆佹€庝箞鏀惰垂銆佹垚鏈€庝箞鍙樸€?,
        "priceDrivers": ["琛屼笟渚涢渶", "浜у搧鎴栨湇鍔″畾浠?, "閿€閲忔垨鍒╃敤鐜?, "鎴愭湰鍙樺寲", "绔炰簤鏍煎眬"],
    }


def enrich_business_items(
    items: list[dict],
    company_main_business: str,
    industry: str,
    dimension: str,
    company_positioning: dict,
) -> list[dict]:
    enriched_items: list[dict] = []
    for item in items:
        enriched_item = dict(item)
        enriched_item.update(
            infer_business_explanation(
                item_name=str(item.get("itemName", "")),
                company_main_business=company_main_business,
                industry=industry,
                dimension=dimension,
                company_positioning=company_positioning,
            )
        )
        enriched_items.append(enriched_item)
    return enriched_items


def extract_sales_mode_breakdown(report_text: str) -> list[dict]:
    if not report_text:
        return []

    start_markers = ["涓昏惀涓氬姟鍒嗛攢鍞ā寮忔儏鍐?, "涓昏惀涓氬姟鍒嗛攢鍞ā寮?]
    end_markers = ["浜ч攢閲忔儏鍐靛垎鏋愯〃", "閲嶅ぇ閲囪喘鍚堝悓", "鎴愭湰鍒嗘瀽琛?, "涓昏閿€鍞鎴峰強涓昏渚涘簲鍟嗘儏鍐?]
    row_pattern = re.compile(
        r"^(?P<name>[A-Za-z\u4e00-\u9fff锛堬級()路\-]+)\s+"
        r"(?P<revenue>-?[\d,]+(?:\.\d+)?)\s+"
        r"(?P<cost>-?[\d,]+(?:\.\d+)?)\s+"
        r"(?P<gross_margin>-?[\d,]+(?:\.\d+)?)\s+"
        r"(?P<revenue_growth>-?[\d,]+(?:\.\d+)?)\s+"
        r"(?P<cost_growth>-?[\d,]+(?:\.\d+)?)\s+"
        r"(?P<margin_change>.+)$"
    )

    started = False
    items: list[dict] = []
    for raw_line in report_text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue

        if not started and any(marker in line for marker in start_markers):
            started = True
            continue

        if not started:
            continue

        if any(marker in line for marker in end_markers):
            break

        match = row_pattern.match(line)
        if not match:
            continue

        item_name = match.group("name")
        if is_supplementary_item(item_name):
            continue

        items.append(
            sanitize_business_item(
                {
                    "itemName": item_name,
                    "revenue": to_yi(parse_ak_value(match.group("revenue"))),
                    "cost": to_yi(parse_ak_value(match.group("cost"))),
                    "grossMargin": round(parse_percentage_value(match.group("gross_margin")), 4),
                    "revenueGrowth": round(parse_percentage_value(match.group("revenue_growth")), 4),
                    "costGrowth": round(parse_percentage_value(match.group("cost_growth")), 4),
                    "grossMarginChangeText": match.group("margin_change").strip(),
                }
            )
        )

    total_revenue = sum((item.get("revenue") or 0) for item in items)
    for item in items:
        revenue = item.get("revenue") or 0
        item["revenueRatio"] = round(revenue / total_revenue, 4) if total_revenue else 0.0

    return sorted(items, key=lambda item: item.get("revenue") or 0, reverse=True)


def find_bar_item(bar_data: list[dict], item_name: str) -> dict | None:
    for item in bar_data:
        if item.get("name") == item_name:
            return item
    return None


def build_revenue_insight_points(
    product_items: list[dict],
    region_items: list[dict],
    channel_items: list[dict],
    contract_liability_item: dict | None,
) -> list[str]:
    insights: list[str] = []

    product_dominance = build_dominance_summary(product_items)
    if product_dominance:
        ratio = product_dominance["revenueRatio"] * 100
        if product_dominance["isHighlyConcentrated"]:
            insights.append(f"鏀跺叆楂樺害闆嗕腑鍦▄product_dominance['itemName']}锛屾敹鍏ュ崰姣旂害{ratio:.1f}%銆?)
        else:
            insights.append(f"褰撳墠绗竴澶т骇鍝佹槸{product_dominance['itemName']}锛屾敹鍏ュ崰姣旂害{ratio:.1f}%銆?)

    product_margin = build_margin_summary(product_items)
    if product_margin:
        insights.append(
            f"{product_margin['itemName']}姣涘埄鐜囩害{product_margin['grossMargin'] * 100:.1f}%锛屾槸鏈€鍊煎緱浼樺厛璺熻釜鐨勭泩鍒╁崟鍏冦€?
        )

    region_dominance = build_dominance_summary(region_items)
    if region_dominance:
        ratio = region_dominance["revenueRatio"] * 100
        insights.append(f"{region_dominance['itemName']}甯傚満璐＄尞鏀跺叆绾ratio:.1f}%锛屽尯鍩熺粨鏋勮緝涓烘竻鏅般€?)

    if len(channel_items) >= 2:
        direct_items = [item for item in channel_items if "鐩撮攢" in item.get("itemName", "")]
        wholesale_items = [
            item
            for item in channel_items
            if "鎵瑰彂" in item.get("itemName", "") or "浠ｇ悊" in item.get("itemName", "")
        ]
        if direct_items and wholesale_items:
            direct_item = direct_items[0]
            wholesale_item = wholesale_items[0]
            if direct_item["grossMargin"] > wholesale_item["grossMargin"]:
                insights.append(
                    f"鐩撮攢姣涘埄鐜囬珮浜庢壒鍙戜唬鐞嗭紝璇存槑娓犻亾鍒╂鼎鍥炴祦瀵圭泩鍒╄川閲忔湁鏄庢樉甯姪銆?
                )
            if direct_item["revenueGrowth"] > wholesale_item["revenueGrowth"]:
                insights.append(
                    f"鐩撮攢澧為€熷揩浜庢壒鍙戜唬鐞嗭紝璇存槑鍏徃鍦ㄤ富鍔ㄥ己鍖栬嚜钀ユ垨鏁板瓧鍖栨笭閬撱€?
                )

    if contract_liability_item and contract_liability_item.get("value", 0) > 0:
        insights.append(
            f"棰勬敹/鍚堝悓璐熷€虹害{contract_liability_item['value']}浜垮厓锛屽彲浣滀负瀹㈡埛棰勪粯娆炬剰鎰跨殑杈呭姪瑙傚療鎸囨爣銆?
        )

    return insights


def get_revenue_structure_payload(stock: str, years: int = 8) -> dict:
    profile_payload = get_company_profile_payload_with_cache(stock=stock)
    main_business_payload = get_main_business_payload_with_cache(stock=stock)
    annual_report_payload = get_latest_report_text_payload_v2(stock=stock, category="骞存姤", cache_key="annual_report_v1")
    balance_payload = get_balance_payload_with_cache(stock=stock, period=None)
    revenue_market_cap_payload = get_revenue_market_cap_payload_with_cache(stock=stock, years=years)

    items = main_business_payload.get("items", [])
    company_main_business = str(profile_payload.get("mainBusiness", ""))
    industry = str(profile_payload.get("industry", ""))
    raw_product_items = filter_business_items(items, "鎸変骇鍝佸垎绫?)
    raw_channel_items = extract_sales_mode_breakdown(annual_report_payload.get("textExcerpt", ""))
    company_positioning = infer_company_positioning(
        company_main_business=company_main_business,
        industry=industry,
        product_items=raw_product_items,
        channel_items=raw_channel_items,
    )

    product_items = enrich_business_items(
        raw_product_items,
        company_main_business=company_main_business,
        industry=industry,
        dimension="product",
        company_positioning=company_positioning,
    )
    region_items = enrich_business_items(
        filter_business_items(items, "鎸夊湴鍖哄垎绫?),
        company_main_business=company_main_business,
        industry=industry,
        dimension="region",
        company_positioning=company_positioning,
    )
    industry_items = enrich_business_items(
        filter_business_items(items, "鎸夎涓氬垎绫?),
        company_main_business=company_main_business,
        industry=industry,
        dimension="industry",
        company_positioning=company_positioning,
    )
    channel_items = enrich_business_items(
        raw_channel_items,
        company_main_business=company_main_business,
        industry=industry,
        dimension="channel",
        company_positioning=company_positioning,
    )
    contract_liability_item = find_bar_item(balance_payload.get("barData", []), "棰勬敹娆?)

    insight_points = build_revenue_insight_points(
        product_items=product_items,
        region_items=region_items,
        channel_items=channel_items,
        contract_liability_item=contract_liability_item,
    )

    payload = {
        "stock": stock,
        "companyName": profile_payload.get("companyName", ""),
        "industry": profile_payload.get("industry", ""),
        "reportDate": annual_report_payload.get("date", ""),
        "analysisDimensionCoverage": {
            "product": bool(product_items),
            "region": bool(region_items),
            "channel": bool(channel_items),
            "industry": bool(industry_items),
            "contractLiability": contract_liability_item is not None,
        },
        "businessSummary": {
            "mainBusiness": profile_payload.get("mainBusiness", ""),
            "interpretedMainBusiness": build_interpreted_main_business_summary(
                company_main_business=company_main_business,
                company_positioning=company_positioning,
                product_items=product_items,
            ),
            "companyIntro": profile_payload.get("companyIntro", ""),
            "trendConclusion": revenue_market_cap_payload.get("conclusion", ""),
        },
        "companyPositioning": company_positioning,
        "breakdowns": {
            "byProduct": product_items,
            "byRegion": region_items,
            "byChannel": channel_items,
            "byIndustry": industry_items,
        },
        "highlights": {
            "topProduct": build_dominance_summary(product_items),
            "topRegion": build_dominance_summary(region_items),
            "topChannel": build_dominance_summary(channel_items),
            "bestGrossMarginProduct": build_margin_summary(product_items),
            "bestGrossMarginChannel": build_margin_summary(channel_items),
            "contractLiability": contract_liability_item,
        },
        "insightPoints": insight_points,
        "sourceDocuments": {
            "annualReportTitle": annual_report_payload.get("title", ""),
            "annualReportPdfUrl": annual_report_payload.get("pdfUrl", ""),
        },
    }
    return payload


def load_disclosure_reports(stock: str, category: str, start_date: str = "20200101", end_date: str = "20300101") -> pd.DataFrame:
    print(f"[INFO] Fetching disclosure reports, stock={stock}, category={category}")
    with temporary_disable_proxy_env():
        df = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=stock,
            category=category,
            start_date=start_date,
            end_date=end_date,
        )
    print("[DEBUG] Disclosure report columns:")
    print(df.columns.tolist())
    return df


def fetch_pdf_text_from_cninfo(adjunct_url: str, max_pages: int = 15, max_chars: int = 20000) -> str:
    if not adjunct_url:
        return ""

    pdf_url = adjunct_url
    if not pdf_url.startswith("http"):
        pdf_url = f"http://static.cninfo.com.cn/{adjunct_url.lstrip('/')}"

    with temporary_disable_proxy_env():
        response = requests.get(pdf_url, timeout=60, proxies={"http": None, "https": None})
        response.raise_for_status()

    reader = PdfReader(BytesIO(response.content))
    parts: list[str] = []
    for page in reader.pages[:max_pages]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            parts.append(text)
        if sum(len(item) for item in parts) >= max_chars:
            break

    combined_text = "\n".join(parts).strip()
    return combined_text[:max_chars]


def get_latest_report_text_payload_with_cache(stock: str, category: str, cache_key: str) -> dict:
    cached_payload = load_cached_payload(cache_key, stock)
    if cached_payload is not None:
        return cached_payload

    df = load_disclosure_reports(stock=stock, category=category)
    if df is None or df.empty:
        payload = {"stock": stock, "category": category, "title": "", "date": "", "pdfUrl": "", "textExcerpt": ""}
        save_cached_payload(payload, cache_key, stock)
        return payload

    df = df.copy()
    df["鍏憡鏃堕棿_dt"] = pd.to_datetime(df["鍏憡鏃堕棿"], errors="coerce")
    df = df.sort_values("鍏憡鏃堕棿_dt", ascending=False)
    latest_row = df.iloc[0]

    # Rebuild raw payload to get adjunctUrl / PDF path.
    with temporary_disable_proxy_env():
        report_df = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=stock,
            category=category,
            start_date="20200101",
            end_date="20300101",
        )

    # Call raw endpoint directly for PDF path because AKShare output hides adjunctUrl.
    with temporary_disable_proxy_env():
        import akshare as _ak
        stock_json = _ak.stock_feature.stock_disclosure_cninfo.__get_stock_json("娌繁浜?)
        category_dict = _ak.stock_feature.stock_disclosure_cninfo.__get_category_dict()
        payload = {
            "pageNum": "1",
            "pageSize": "30",
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{stock},{stock_json[stock]}",
            "searchkey": "",
            "secid": "",
            "category": f"{category_dict[category]}",
            "trade": "",
            "seDate": "2020-01-01~2030-01-01",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        raw_response = requests.post(
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            data=payload,
            timeout=60,
            proxies={"http": None, "https": None},
        )
        raw_response.raise_for_status()
        raw_json = raw_response.json()

    selected_item = None
    for item in raw_json.get("announcements", []):
        announcement_title = item.get("announcementTitle", "")
        if announcement_title == latest_row["鍏憡鏍囬"]:
            selected_item = item
            break

    adjunct_url = selected_item.get("adjunctUrl", "") if selected_item else ""
    pdf_url = f"http://static.cninfo.com.cn/{adjunct_url.lstrip('/')}" if adjunct_url else ""
    text_excerpt = fetch_pdf_text_from_cninfo(adjunct_url) if adjunct_url else ""

    payload = {
        "stock": stock,
        "category": category,
        "title": latest_row["鍏憡鏍囬"],
        "date": str(latest_row["鍏憡鏃堕棿"]),
        "pdfUrl": pdf_url,
        "textExcerpt": text_excerpt,
    }
    save_cached_payload(payload, cache_key, stock)
    return payload


def get_latest_report_text_payload_v2(stock: str, category: str, cache_key: str) -> dict:
    cached_payload = load_cached_payload(cache_key, stock)
    if cached_payload is not None:
        return cached_payload

    df = load_disclosure_reports(stock=stock, category=category)
    if df is None or df.empty:
        payload = {"stock": stock, "category": category, "title": "", "date": "", "pdfUrl": "", "textExcerpt": ""}
        save_cached_payload(payload, cache_key, stock)
        return payload

    df = df.copy()
    df["鍏憡鏃堕棿_dt"] = pd.to_datetime(df["鍏憡鏃堕棿"], errors="coerce")
    df = df.sort_values("鍏憡鏃堕棿_dt", ascending=False)
    latest_row = df.iloc[0]

    with temporary_disable_proxy_env():
        stock_json = disclosure_cninfo.__get_stock_json("娌繁浜?)
        category_dict = disclosure_cninfo.__get_category_dict()
        query_payload = {
            "pageNum": "1",
            "pageSize": "30",
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{stock},{stock_json[stock]}",
            "searchkey": "",
            "secid": "",
            "category": f"{category_dict[category]}",
            "trade": "",
            "seDate": "2020-01-01~2030-01-01",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        raw_response = requests.post(
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            data=query_payload,
            timeout=60,
            proxies={"http": None, "https": None},
        )
        raw_response.raise_for_status()
        raw_json = raw_response.json()

    selected_item = None
    for item in raw_json.get("announcements", []):
        if item.get("announcementTitle", "") == latest_row["鍏憡鏍囬"]:
            selected_item = item
            break

    adjunct_url = selected_item.get("adjunctUrl", "") if selected_item else ""
    pdf_url = f"http://static.cninfo.com.cn/{adjunct_url.lstrip('/')}" if adjunct_url else ""
    text_excerpt = fetch_pdf_text_from_cninfo(adjunct_url) if adjunct_url else ""

    payload = {
        "stock": stock,
        "category": category,
        "title": latest_row["鍏憡鏍囬"],
        "date": str(latest_row["鍏憡鏃堕棿"]),
        "pdfUrl": pdf_url,
        "textExcerpt": text_excerpt,
    }
    save_cached_payload(payload, cache_key, stock)
    return payload


def top_bar_items(items: list[dict], item_type: str, limit: int = 4) -> list[dict]:
    filtered_items = [item for item in items if item.get("type") == item_type]
    sorted_items = sorted(filtered_items, key=lambda item: item.get("value", 0), reverse=True)
    return [{"name": item["name"], "value": item["value"]} for item in sorted_items[:limit]]


def sample_series_points(items: list[dict], max_points: int = 6) -> list[dict]:
    if len(items) <= max_points:
        return items

    sampled: list[dict] = []
    step = max(1, len(items) // max_points)
    for index in range(0, len(items), step):
        sampled.append(items[index])
        if len(sampled) >= max_points - 1:
            break

    sampled.append(items[-1])
    return sampled


def build_ai_analysis_context(stock: str, period: str | None, years: int) -> dict:
    balance_payload = get_balance_payload_with_cache(stock=stock, period=period)
    revenue_payload = get_revenue_market_cap_payload_with_cache(stock=stock, years=years)
    profit_payload = get_profit_market_cap_payload_with_cache(stock=stock, years=years)
    pe_payload = get_pe_trend_payload_with_cache(stock=stock, years=years)
    profile_payload = get_company_profile_payload_with_cache(stock=stock)
    main_business_payload = get_main_business_payload_with_cache(stock=stock)
    annual_report_payload = get_latest_report_text_payload_v2(stock=stock, category="骞存姤", cache_key="annual_report_v1")
    semiannual_report_payload = get_latest_report_text_payload_v2(stock=stock, category="鍗婂勾鎶?, cache_key="semiannual_report_v1")

    return {
        "stock": stock,
        "period": period or "latest",
        "years": years,
        "unit": "浜垮厓",
        "costAnalysisFramework": COST_ANALYSIS_FRAMEWORK,
        "companyProfile": profile_payload,
        "mainBusinessComposition": main_business_payload.get("items", []),
        "latestAnnualReport": annual_report_payload,
        "latestSemiannualReport": semiannual_report_payload,
        "balance": {
            "reportDate": balance_payload.get("reportDate"),
            "conclusion": balance_payload.get("conclusion"),
            "topAssets": top_bar_items(balance_payload.get("barData", []), "asset"),
            "topLiabilities": top_bar_items(balance_payload.get("barData", []), "liability"),
        },
        "revenueMarketCap": {
            "conclusion": revenue_payload.get("conclusion"),
            "revenueBars": sample_series_points(revenue_payload.get("revenueBars", [])),
            "marketCapLine": sample_series_points(revenue_payload.get("marketCapLine", [])),
        },
        "profitMarketCap": {
            "conclusion": profit_payload.get("conclusion"),
            "profitBars": sample_series_points(profit_payload.get("profitBars", [])),
            "marketCapLine": sample_series_points(profit_payload.get("marketCapLine", [])),
        },
        "peTrend": {
            "conclusion": pe_payload.get("conclusion"),
            "meanLine": pe_payload.get("meanLine"),
            "lowLine": pe_payload.get("lowLine"),
            "highLine": pe_payload.get("highLine"),
            "peLine": sample_series_points(pe_payload.get("peLine", [])),
        },
    }


def normalize_business_type_label(raw_label: object) -> str:
    text = str(raw_label or "").strip().lower()
    if any(keyword in text for keyword in ["平台", "platform"]):
        return "platform"
    if any(keyword in text for keyword in ["产品", "product"]):
        return "product"
    return "service"


def normalize_business_type_analysis_payload(payload: dict) -> dict:
    normalized = dict(payload or {})
    company_nature = normalize_business_type_label(normalized.get("business_type"))
    normalized["company_nature"] = company_nature
    normalized["business_type"] = {
        "product": "产品型",
        "service": "服务型",
        "platform": "平台型",
    }[company_nature]

    supports = normalized.get("supports")
    if not isinstance(supports, list) or not supports:
        key_evidence = normalized.get("key_evidence")
        supports = []
        if isinstance(key_evidence, list):
            supports = [
                {
                    "point": str(item.get("evidence_type", "")).strip() or "关键证据",
                    "evidence": str(item.get("description", "")).strip(),
                }
                for item in key_evidence
                if isinstance(item, dict) and str(item.get("description", "")).strip()
            ]
    normalized["supports"] = supports[:4]

    conflicts = normalized.get("conflicts")
    if not isinstance(conflicts, list) or not conflicts:
        reasons = normalized.get("not_other_types_reason")
        conflicts = []
        if isinstance(reasons, list):
            conflicts = [
                {
                    "point": str(item.get("type", "")).strip() or "反向证据",
                    "evidence": str(item.get("reason", "")).strip(),
                }
                for item in reasons
                if isinstance(item, dict) and str(item.get("reason", "")).strip()
            ]
    normalized["conflicts"] = conflicts[:3]

    watch_metrics = normalized.get("watch_metrics")
    if not isinstance(watch_metrics, list) or not watch_metrics:
        watch_metrics = POSITIONING_WATCH_METRICS[company_nature]
    normalized["watch_metrics"] = [str(item).strip() for item in watch_metrics if str(item).strip()][:5]

    evidence_strength = str(normalized.get("evidence_strength", "")).strip().lower()
    if evidence_strength not in {"strong", "medium", "weak"}:
        evidence_strength = "strong" if len(normalized["supports"]) >= 3 else "medium" if len(normalized["supports"]) >= 2 else "weak"
    normalized["evidence_strength"] = evidence_strength

    uncertainty = str(normalized.get("uncertainty", "")).strip()
    if not uncertainty and evidence_strength == "weak":
        uncertainty = "当前证据偏弱，这个商业模式判断更适合作为分析起点，建议继续结合原始年报复核。"
    normalized["uncertainty"] = uncertainty

    return normalized


def generate_ai_analysis(stock: str, period: str | None, years: int, company_material: str | None = None) -> dict:
    settings = get_openai_settings()
    context = build_ai_analysis_context(stock=stock, period=period, years=years)
    business_type_result = generate_business_type_analysis(
        stock=stock,
        period=period,
        years=years,
        company_material=company_material,
    )
    business_type_analysis = business_type_result.get("analysis")

    client = OpenAI(
        api_key=settings["api_key"],
        base_url=settings["base_url"],
        http_client=httpx.Client(trust_env=False),
    )

    prompt_sections = [
        "璇峰熀浜庝笅闈㈢殑璐㈡姤鍜屼及鍊兼暟鎹紝鐢熸垚涓€娈典腑鏂囧垎鏋愩€俓n"
        "杈撳嚭鏍煎紡锛歕n"
        "1. 绗竴娈碉細鎬昏瘎锛?鍒?鍙ャ€俓n"
        "2. 绗簩娈碉細鐢ㄢ€滆鐐癸細鈥濆紑澶达紝鍒楀嚭3鏉℃牳蹇冭瀵燂紝姣忔潯鍗曠嫭涓€琛岋紝浠モ€? 鈥濆紑澶淬€俓n"
        "3. 绗笁娈碉細鐢ㄢ€滈闄╂彁绀猴細鈥濆紑澶达紝鍐?鍒?鍙ャ€俓n"
        "4. 涓嶈浣跨敤 markdown 鏍囬锛屼笉瑕佽緭鍑?JSON銆俓n"
        "5. 璇峰湪鎬昏瘎閲屾樉寮忚鏄庤鍏徃鏇存帴杩戝摢涓€绫诲晢涓氭ā寮忥紝浠ュ強杩欎釜鍒嗙被濡備綍瑙ｉ噴褰撳墠璐㈠姟缁撴瀯鍜屽闀跨壒寰併€俓n"
        "6. 请显式使用给定的“成本五维框架”去分析成本和支出：按会计科目、按部门、按业务线/产品线、按固定/变动、按可控/不可控。\n"
        "7. 如果没有足够的成本明细，请基于主营构成、毛利率、资产结构、现金流和行业特征做近似判断，并明确哪些结论是推断、哪些数据仍然缺失。\n\n",
        "銆愮粨鏋勫寲璐㈠姟瓒嬪娍鏁版嵁銆慭n",
        json.dumps(context, ensure_ascii=False, indent=2),
    ]

    if company_material and company_material.strip():
        prompt_sections.extend(
            [
                "\n\n銆愮敤鎴锋彁渚涚殑鍏徃璧勬枡銆慭n",
                company_material.strip(),
            ]
        )

    if business_type_analysis:
        prompt_sections.extend(
            [
                "\n\n銆愬晢涓氭ā寮忓垎绫荤粨鏋溿€慭n",
                json.dumps(business_type_analysis, ensure_ascii=False, indent=2),
            ]
        )

    user_prompt = "".join(prompt_sections)

    response = client.chat.completions.create(
        model=settings["model"],
        temperature=settings["temperature"],
        messages=[
            {"role": "system", "content": AI_ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    analysis_text = response.choices[0].message.content if response.choices else ""
    analysis_text = (analysis_text or "").strip()
    if not analysis_text:
        raise ValueError("OpenAI returned an empty analysis.")

    return {
        "stock": stock,
        "period": period or "latest",
        "years": years,
        "model": settings["model"],
        "analysis": analysis_text,
        "businessTypeAnalysis": business_type_analysis,
        "dataContext": context,
    }


def generate_business_type_analysis(
    stock: str,
    period: str | None,
    years: int,
    company_material: str | None = None,
) -> dict:
    settings = get_openai_settings()
    context = build_ai_analysis_context(stock=stock, period=period, years=years)
    client = OpenAI(
        api_key=settings["api_key"],
        base_url=settings["base_url"],
        http_client=httpx.Client(trust_env=False),
    )

    schema_template = {
        "company_name": "",
        "business_type": "product_or_service_or_platform",
        "evidence_strength": "strong|medium|weak",
        "confidence": 0.0,
        "main_revenue_source": "",
        "main_profit_source": "",
        "growth_driver": "",
        "supports": [
            {"point": "", "evidence": ""},
            {"point": "", "evidence": ""},
        ],
        "conflicts": [{"point": "", "evidence": ""}],
        "watch_metrics": [],
        "uncertainty": "",
        "key_evidence": [
            {"evidence_type": "revenue_structure", "description": ""},
            {"evidence_type": "profit_structure", "description": ""},
            {"evidence_type": "asset_structure", "description": ""},
            {"evidence_type": "cashflow_profile", "description": ""},
        ],
        "why_this_type": "",
        "not_other_types_reason": [{"type": "", "reason": ""}],
        "risks": [],
        "missing_data": [],
        "final_summary": "",
    }

    user_prompt = (
        "璇峰熀浜庝互涓嬩袱閮ㄥ垎淇℃伅瀹屾垚鍒ゆ柇锛屽苟涓ユ牸杈撳嚭 JSON锛歕n"
        "A. 鐢ㄦ埛鎻愪緵鐨勫叕鍙歌祫鏂橽n"
        "B. 绯荤粺鏁寸悊鐨勭粨鏋勫寲璐㈠姟瓒嬪娍鏁版嵁\n\n"
        "鍒ゆ柇鏃朵竴瀹氳鏄惧紡鑰冭檻鏀跺叆鏉ユ簮銆佸埄娑︽潵婧愩€佸闀块┍鍔ㄣ€佹垚鏈粨鏋勩€佽祫浜х粨鏋勩€佺幇閲戞祦鐗瑰緛銆?
        "濡傛灉鐢ㄦ埛璧勬枡閲岀己灏戞垚鏈粨鏋勬垨鐜伴噾娴佺壒寰侊紝璇风粨鍚堢粨鏋勫寲鏁版嵁鍒ゆ柇锛涘鏋滀粛涓嶈冻锛岃鍐欏叆 missing_data锛屼笖蹇呰鏃惰緭鍑衡€滄棤娉曠‘瀹氣€濄€俓n"
        "请特别按这5个维度理解成本与支出：按会计科目、按部门、按业务线/产品线、按固定/变动、按可控/不可控；如果只能近似判断，也要写清楚推断依据。\n\n"
        f"JSON 妯℃澘锛歕n{json.dumps(schema_template, ensure_ascii=False, indent=2)}\n\n"
        f"銆愬叕鍙歌祫鏂欍€慭n{(company_material or '鏃犻澶栧叕鍙歌祫鏂欙紝浠呬娇鐢ㄧ粨鏋勫寲璐㈠姟瓒嬪娍鏁版嵁鍒ゆ柇銆?).strip()}\n\n"
        f"銆愮粨鏋勫寲璐㈠姟瓒嬪娍鏁版嵁銆慭n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )

    response = client.chat.completions.create(
        model=settings["model"],
        temperature=settings["temperature"],
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": BUSINESS_TYPE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content if response.choices else ""
    content = (content or "").strip()
    if not content:
        raise ValueError("OpenAI returned an empty business type analysis.")

    try:
        analysis_json = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenAI did not return valid JSON: {content}") from exc

    analysis_json = normalize_business_type_analysis_payload(analysis_json)

    return {
        "stock": stock,
        "period": period or "latest",
        "years": years,
        "model": settings["model"],
        "analysis": analysis_json,
        "dataContext": context,
    }


@app.get("/api/pe-trend")
def api_pe_trend():
    stock = request.args.get("stock", "000333").strip() or "000333"
    years_param = request.args.get("years", "8")
    refresh = request.args.get("refresh") == "1"

    try:
        years = normalize_years(years_param, default=8)

        if not refresh:
            cached_payload = load_cached_payload("pe_trend_v1", stock, years)
            if cached_payload is not None:
                return jsonify(cached_payload)

        payload = build_pe_trend_payload(stock=stock, years=years)
        save_cached_payload(payload, "pe_trend_v1", stock, years)
        return jsonify(payload)

    except Exception as exc:
        print(f"[ERROR] {exc}")
        return jsonify({"error": str(exc), "stock": stock, "years": years_param}), 400


@app.get("/api/balance")
def api_balance():
    stock = request.args.get("stock", "600519").strip() or "600519"
    period = request.args.get("period")

    try:
        normalized_period = normalize_period(period)
        cached_payload = load_cached_payload("balance", stock, normalized_period or "latest")
        if cached_payload is not None:
            return jsonify(cached_payload)

        payload = get_balance_payload(stock=stock, period=period)
        save_cached_payload(payload, "balance", stock, normalized_period or "latest")
        return jsonify(payload)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return jsonify({"error": str(exc), "stock": stock, "period": period}), 400


@app.get("/api/revenue-market-cap")
def api_revenue_market_cap():
    stock = request.args.get("stock", "000333").strip() or "000333"
    years_param = request.args.get("years", "8")

    try:
        years = normalize_years(years_param, default=8)
        cached_payload = load_cached_payload("revenue_market_cap_v2", stock, years)
        if cached_payload is not None:
            return jsonify(cached_payload)

        payload = get_revenue_market_cap_payload(stock=stock, years=years)
        save_cached_payload(payload, "revenue_market_cap_v2", stock, years)
        return jsonify(payload)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return jsonify({"error": str(exc), "stock": stock, "years": years_param}), 400


@app.get("/api/revenue-structure")
def api_revenue_structure():
    stock = request.args.get("stock", "600519").strip() or "600519"
    years_param = request.args.get("years", "8")
    refresh = request.args.get("refresh") == "1"

    try:
        years = normalize_years(years_param, default=8)

        if not refresh:
            cached_payload = load_cached_payload("revenue_structure_v1", stock, years)
            if cached_payload is not None:
                return jsonify(cached_payload)

        payload = get_revenue_structure_payload(stock=stock, years=years)
        save_cached_payload(payload, "revenue_structure_v1", stock, years)
        return jsonify(payload)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return jsonify({"error": str(exc), "stock": stock, "years": years_param}), 400


@app.get("/api/profit-market-cap")
def api_profit_market_cap():
    stock = request.args.get("stock", "600519").strip() or "600519"
    years_param = request.args.get("years", "8")
    refresh = request.args.get("refresh") == "1"

    try:
        years = normalize_years(years_param, default=8)

        if not refresh:
            cached_payload = load_cached_payload("profit_market_cap_v1", stock, years)
            if cached_payload is not None:
                return jsonify(cached_payload)

        payload = get_profit_market_cap_payload(stock=stock, years=years)
        save_cached_payload(payload, "profit_market_cap_v1", stock, years)
        return jsonify(payload)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return jsonify({"error": str(exc), "stock": stock, "years": years_param}), 400


@app.post("/api/ai-analysis")
def api_ai_analysis():
    payload = request.get_json(silent=True) or {}

    stock = str(payload.get("stock", "600519")).strip() or "600519"
    period = payload.get("period")
    years_param = str(payload.get("years", "8")).strip() or "8"
    company_material = str(payload.get("companyMaterial", "")).strip()

    try:
        years = normalize_years(years_param, default=8)
        result = generate_ai_analysis(
            stock=stock,
            period=period,
            years=years,
            company_material=company_material or None,
        )
        return jsonify(result)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return (
            jsonify(
                {
                    "error": str(exc),
                    "stock": stock,
                    "period": period,
                    "years": years_param,
                }
            ),
            400,
        )


@app.post("/api/business-type-analysis")
def api_business_type_analysis():
    payload = request.get_json(silent=True) or {}

    stock = str(payload.get("stock", "600519")).strip() or "600519"
    period = payload.get("period")
    years_param = str(payload.get("years", "8")).strip() or "8"
    company_material = str(payload.get("companyMaterial", "")).strip()

    try:
        if not company_material:
            raise ValueError("companyMaterial is required.")

        years = normalize_years(years_param, default=8)
        result = generate_business_type_analysis(
            stock=stock,
            period=period,
            years=years,
            company_material=company_material,
        )
        return jsonify(result)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return (
            jsonify(
                {
                    "error": str(exc),
                    "stock": stock,
                    "period": period,
                    "years": years_param,
                }
            ),
            400,
        )


@app.get("/")
def health_message():
    return jsonify(
        {
            "message": "Flask API is running. Use the Next frontend for the UI.",
            "balanceApi": "/api/balance?stock=600519",
            "trendApi": "/api/revenue-market-cap?stock=000333&years=8",
            "revenueStructureApi": "/api/revenue-structure?stock=600519&years=8",
            "profitTrendApi": "/api/profit-market-cap?stock=600519&years=8",
            "peApi": "/api/pe-trend?stock=600519&years=8",
            "aiAnalysisApi": "POST /api/ai-analysis",
            "businessTypeAnalysisApi": "POST /api/business-type-analysis",
        }
    )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5001)
