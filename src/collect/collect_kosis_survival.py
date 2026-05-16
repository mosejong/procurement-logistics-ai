"""
KOSIS 신생기업 생존율 + 기업 소멸률 수집 스크립트

1순위: DT_6BD1109 -- 시도별 산업대분류별 신생기업 생존율 (최근 5년)
2순위: DT_6BD1105 -- 시도별 산업별 기업수(활동/신생/소멸) + 소멸률 (최근 3년)

출력: outputs/tables/kosis_survival_rate.csv
컬럼: city, item_category, survival_1y, survival_3y, survival_5y, dissolution_rate, year
"""
from pathlib import Path
import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

ROOT     = Path(__file__).parent.parent.parent
OUT_DIR  = ROOT / "outputs" / "tables"
OUT_PATH = OUT_DIR / "kosis_survival_rate.csv"

API_KEY = os.getenv("KOSIS_API_KEY", "")

URL_1 = (
    "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    "?method=getList"
    f"&apiKey={API_KEY}"
    "&itmId=T01+T02+T03+T04+T05+T06+T07+T001+T002+T003+T004+T005+T006+T007+"
    "&objL1=ALL&objL2=ALL&objL3=&objL4=&objL5=&objL6=&objL7=&objL8="
    "&format=json&jsonVD=Y&prdSe=Y&newEstPrdCnt=5"
    "&outputFields=OBJ_NM+NM+ITM_NM+UNIT_NM+PRD_DE+"
    "&orgId=101&tblId=DT_6BD1109"
)

URL_2 = (
    "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    "?method=getList"
    f"&apiKey={API_KEY}"
    "&itmId=T01+T02+T03+T04+T05+"
    "&objL1=ALL&objL2=ALL&objL3=0+1+5+&objL4=&objL5=&objL6=&objL7=&objL8="
    "&format=json&jsonVD=Y&prdSe=Y&newEstPrdCnt=3"
    "&outputFields=OBJ_NM+NM+ITM_NM+UNIT_NM+PRD_DE+"
    "&orgId=101&tblId=DT_6BD1105"
)

# C1=시도, C2=산업대분류, C3=기업규모(계/대기업/중소기업)
INDUSTRY_MAP: dict[str, str] = {
    "농업, 임업 및 어업":                           "식품/농업",
    "광업":                                         "기타",
    "제조업":                                       "IT/전자",
    "전기, 가스, 증기 및 공기조절 공급업":          "환경/에너지",
    "수도, 하수 및 폐기물 처리, 원료재생업":        "환경/에너지",
    "건설업":                                       "건설/시설",
    "도매 및 소매업":                               "기타",
    "운수 및 창고업":                               "기타",
    "숙박 및 음식점업":                             "식품/농업",
    "정보통신업":                                   "IT/전자",
    "금융 및 보험업":                               "기타",
    "부동산업":                                     "기타",
    "전문, 과학 및 기술 서비스업":                  "IT/전자",
    "사업시설 관리, 사업 지원 및 임대 서비스업":    "기타",
    "공공행정, 국방 및 사회보장 행정":              "기타",
    "교육 서비스업":                                "교육/문화",
    "보건업 및 사회복지 서비스업":                  "의료/복지",
    "예술, 스포츠 및 여가관련 서비스업":            "교육/문화",
    "협회 및 단체, 수리 및 기타 개인 서비스업":     "기타",
}

SURVIVAL_COL = {"1년": "survival_1y", "3년": "survival_3y", "5년": "survival_5y"}


def _fetch(url: str, label: str) -> list[dict]:
    print(f"  API [{label}] 호출 중...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "err" in data:
        raise RuntimeError(f"KOSIS 오류: {data}")
    print(f"  >> {len(data)}건 수신")
    return data


def parse_survival(raw: list[dict]) -> pd.DataFrame:
    """1순위: C1=시도, C2=산업대분류, ITM_NM에 생존율+연차 포함"""
    rows = []
    for item in raw:
        itm_nm = str(item.get("ITM_NM", ""))
        city   = str(item.get("C1_NM", ""))
        ind    = str(item.get("C2_NM", ""))
        year   = str(item.get("PRD_DE", ""))

        col = None
        for kw, c in SURVIVAL_COL.items():
            if kw in itm_nm and "생존율" in itm_nm:
                col = c
                break
        if col is None or city in ("전국", ""):
            continue
        try:
            val = float(item.get("DT", ""))
        except (TypeError, ValueError):
            continue

        rows.append({"city": city, "industry": ind, "col": col, "value": val, "year": year})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df[df["year"] == df["year"].max()]
    pivot = df.pivot_table(
        index=["city", "industry"], columns="col", values="value", aggfunc="mean"
    ).reset_index()
    pivot.columns.name = None
    pivot["item_category"] = pivot["industry"].map(INDUSTRY_MAP).fillna("기타")

    cols = [c for c in ["survival_1y", "survival_3y", "survival_5y"] if c in pivot.columns]
    result = pivot.groupby(["city", "item_category"])[cols].mean().round(2).reset_index()
    # 전체 평균 행 추가
    overall = pivot.groupby("city")[cols].mean().round(2).reset_index()
    overall["item_category"] = "전체"
    return pd.concat([result, overall], ignore_index=True)


def parse_dissolution(raw: list[dict]) -> pd.DataFrame:
    """2순위: C3_NM='계', ITM_NM='소멸률' 행 직접 사용 (이미 % 값 제공)"""
    rows = []
    for item in raw:
        if item.get("C3_NM") != "계":
            continue
        if item.get("ITM_NM") != "소멸률":
            continue
        city = str(item.get("C1_NM", ""))
        ind  = str(item.get("C2_NM", ""))
        year = str(item.get("PRD_DE", ""))
        if city in ("전국", ""):
            continue
        try:
            val = float(item.get("DT", ""))
        except (TypeError, ValueError):
            continue
        rows.append({"city": city, "industry": ind, "dissolution_rate": val / 100, "year": year})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df[df["year"] == df["year"].max()]
    df["item_category"] = df["industry"].map(INDUSTRY_MAP).fillna("기타")
    return (
        df.groupby(["city", "item_category"])["dissolution_rate"]
        .mean().round(4).reset_index()
    )


def run() -> None:
    if not API_KEY:
        raise EnvironmentError("KOSIS_API_KEY가 .env에 없습니다")

    print("[1/4] 1순위 신생기업 생존율 수집")
    df_surv = parse_survival(_fetch(URL_1, "DT_6BD1109"))

    print("[2/4] 2순위 기업 소멸률 수집")
    df_diss = parse_dissolution(_fetch(URL_2, "DT_6BD1105"))

    print("[3/4] 통합")
    merged = df_surv.copy() if not df_surv.empty else pd.DataFrame()
    if not df_diss.empty and not merged.empty:
        merged = merged.merge(df_diss, on=["city", "item_category"], how="left")
    print(f"  >> {len(merged)}행 생성")

    print("[4/4] 저장")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"[OK] {OUT_PATH.name}")
    print(merged.head(10).to_string(index=False))


if __name__ == "__main__":
    run()
