
# ============================================================
# streamlit_app.py
# 기존 함수는 위에 그대로 붙여넣고,
# 아래 Streamlit 화면 코드만 추가하면 됨
# ============================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path


def log_message(*args, **kwargs):
    return None



DEFAULT_COLLECT_START_DATE = "20260101"
DEFAULT_COLLECT_END_DATE = "20260625"


@st.cache_data(show_spinner="FUNETF 데이터를 불러오는 중입니다. 첫 실행은 몇 분 걸릴 수 있습니다.")
def load_etf_holdings(collection_start_date, collection_end_date, force_refresh=False):


    # ------------------------------------------------------------
    # 1.  데이터 수집
    # ------------------------------------------------------------

    #1. etf_info <- 기본 정보 및 링크
    #2. etf_holdings <- 구성종목 및 비중, 가격효과, 수량효과



    # ------------------------------------------------------------
    # 1. 기본 설정
    # ------------------------------------------------------------

    base_url = "https://www.funetf.co.kr"

    filter_page_url = base_url + "/product/etf/filter"
    etf_list_api_url = base_url + "/api/public/product/etf/filter/search"
    holding_api_url = base_url + "/api/public/product/view/etfpdf"

    ################################################################# 수집할 날짜
    start_date = collection_start_date
    end_date = collection_end_date
    cache_path = Path(__file__).with_name(f"funetf_cached_data_{start_date}_{end_date}.pkl")
    legacy_cache_path = Path(__file__).with_name("funetf_cached_data.pkl")

    if cache_path.exists() and not force_refresh:
        return pd.read_pickle(cache_path)

    if (
        start_date == DEFAULT_COLLECT_START_DATE
        and end_date == DEFAULT_COLLECT_END_DATE
        and legacy_cache_path.exists()
        and not force_refresh
    ):
        return pd.read_pickle(legacy_cache_path)



    # 저장 파일명
    #out_file = "FUNETF_국내주식_액티브_ETF_구성종목.xlsx"


    # ------------------------------------------------------------
    # 2. 세션과 헤더 설정
    # ------------------------------------------------------------

    session = requests.Session()

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": filter_page_url,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }


    # ------------------------------------------------------------
    # 3. 필터 페이지 접속 후 CSRF 토큰 가져오기
    # ------------------------------------------------------------

    res = session.get(filter_page_url, headers=headers)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    csrf_tag = soup.find("input", {"name": "_csrf"})

    if csrf_tag is not None:
        csrf_token = csrf_tag.get("value")
    else:
        csrf_token = ""

    log_message("CSRF:", csrf_token)


    # ------------------------------------------------------------
    # 4. 국내주식 + 액티브 ETF 목록 가져오기
    # ------------------------------------------------------------

    params = {
        "gijunYmd": end_date,
        "page": 0,
        "size": 50,
        "_csrf": csrf_token,

        # 핵심 필터
        "schActiveDvsnM": "A",   # 액티브
        "schEtfTypeCdM": "11",   # 국내주식
        "prodType": "ETF",
        "schActiveDvsn": "A",    # 액티브
        "schEtfTypeCd": "11",    # 국내주식

    }

    all_rows = []
    page_no = 0

    while True:
        params["page"] = page_no

        res = session.get(etf_list_api_url, headers=headers, params=params)
        res.raise_for_status()

        data = res.json()

        # 첫 페이지에서 응답 구조 확인
        if page_no == 0:
            log_message("ETF 목록 응답 key:", data.keys())

        # 응답 구조에 따라 실제 데이터 꺼내기
        if "content" in data:
            rows = data["content"]
        elif "data" in data:
            rows = data["data"]
        elif "list" in data:
            rows = data["list"]
        else:
            rows = data

        if rows is None or len(rows) == 0:
            break

        all_rows.extend(rows)

        log_message(page_no, "페이지 수집:", len(rows))

        # 한 페이지 크기보다 적게 오면 마지막 페이지로 판단
        if len(rows) < params["size"]:
            break

        page_no += 1


    etf = pd.DataFrame(all_rows)
    etf["기준일자"] = end_date

    log_message("수집된 ETF 수:", len(etf))
    # display(etf.head())
    # log_message(etf.columns)


    # ------------------------------------------------------------
    # 5. 컬럼명 및 컬럼 순서 변경
    # ------------------------------------------------------------

    cols = """
    기준일자 : 기준일자
    itemId : 표준코드
    sotCd : 상품코드
    itemNm : 상품명
    etfTypeCd : ETF유형코드
    etfSTypeNm : ETF유형
    investGrade : 위험등급
    feeTot : 총보수
    lstnDt : 상장일
    unyongCd :운용사코드
    unyongNm :운용사명
    bmIdx : 기초지수
    univCd : 대분류코드
    univCdNm : 대분류명
    univSCd : 소분류코드
    univSCdNm : 소분류명
    curp : 현재가
    nav : 운용규모
    avgRat : 3개월괴리율
    suikRt : 1일
    suikRt0 : 0주
    suikRt1 : 1개월
    suikRt3 : 3개월
    suikRt6 : 6개월
    suikRt99 : YTD
    suikRt12 : 1년
    """

    # 텍스트를 딕셔너리로 변환
    rename_map = {}

    for line in cols.strip().splitlines():
        old_col, new_col = line.split(":", 1)
        rename_map[old_col.strip()] = new_col.strip()

    # 선택할 컬럼 목록
    selected_cols = list(rename_map.keys())

    # 특정 컬럼만 가져오고 동시에 컬럼명 변경
    etf_info = etf[selected_cols].rename(columns=rename_map)


    # ------------------------------------------------------------
    # 6. 상세링크 만들기
    # ------------------------------------------------------------

    base_url = "https://www.funetf.co.kr"
    etf_info["ETF링크"] = base_url + "/product/etf/view/" + etf_info["표준코드"]

    # 중복 제거
    etf_info = etf_info.drop_duplicates().reset_index(drop=True)

    # 확인
    log_message("최종 수집 대상 ETF 수:", len(etf_info))
    # display(etf_info.head())


    # ------------------------------------------------------------
    # 7. 날짜 리스트 만들기
    # ------------------------------------------------------------

    date_list = []

    cur = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")

    while cur <= end:
        date_list.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)

    log_message("수집 날짜:", date_list)



    # # ------------------------------------------------------------
    # # 구성종목 API 테스트
    # # ------------------------------------------------------------

    # test_row = etf_info.iloc[0]

    # code = test_row["상품코드"]
    # name = test_row["상품명"]
    # item_id = test_row["표준코드"]

    # ymd = date_list[0]

    # detail_url = base_url + "/product/etf/view/" + item_id

    # test_headers = headers.copy()
    # test_headers["Referer"] = detail_url

    # holding_params = {
    #     "itemId": item_id,
    #     "etfPdfYmd": ymd,
    # }

    # res = session.get(
    #     holding_api_url,
    #     headers=test_headers,
    #     params=holding_params
    # )

    # log_message("요청 URL:")
    # log_message(res.url)

    # log_message("상태코드:", res.status_code)

    # try:
    #     data = res.json()
    #     log_message("응답 타입:", type(data))
    #     log_message(data)
    # except:
    #     log_message(res.text[:1000]) 



    # ------------------------------------------------------------
    # 8. 구성종목 수집
    # ------------------------------------------------------------

    all_holdings = []
    error_list = []

    for i, row in etf_info.iterrows():

        code = row["상품코드"]
        name = row["상품명"]
        item_id = row["표준코드"]

        log_message(f"{i+1}/{len(etf_info)}", code, name, item_id)

        detail_url = base_url + "/product/etf/view/" + item_id

        holding_headers = headers.copy()
        holding_headers["Referer"] = detail_url

        for ymd in date_list:

            holding_params = {
                "itemId": item_id,
                "etfPdfYmd": ymd,
            }

            try:
                res = session.get(
                    holding_api_url,
                    headers=holding_headers,
                    params=holding_params
                )
                res.raise_for_status()

                data = res.json()

                if i == 0 and ymd == date_list[0]:
                    log_message("요청 URL:")
                    log_message(res.url)
                    log_message("구성종목 응답 key:", data.keys() if isinstance(data, dict) else type(data))
                    log_message(data)

                rows = None

                if isinstance(data, dict):
                    for key in ["data", "list", "content", "result", "etfPdfList", "pdfList"]:
                        if key in data:
                            rows = data[key]
                            break

                    if rows is None:
                        for k, v in data.items():
                            if isinstance(v, list):
                                rows = v
                                break

                elif isinstance(data, list):
                    rows = data

                if rows is None:
                    continue

                if isinstance(rows, list):
                    if len(rows) == 0:
                        continue

                    temp = pd.DataFrame(rows)

                elif isinstance(rows, dict):
                    list_value = None

                    for k, v in rows.items():
                        if isinstance(v, list):
                            list_value = v
                            break

                    if list_value is None or len(list_value) == 0:
                        continue

                    temp = pd.DataFrame(list_value)

                else:
                    continue

                temp.insert(0, "조회날짜", ymd)
                temp.insert(1, "상품코드", code)
                temp.insert(2, "상품명", name)
                temp.insert(3, "표준코드", item_id)

                all_holdings.append(temp)

            except Exception as e:
                error_list.append({
                    "상품코드": code,
                    "상품명": name,
                    "표준코드": item_id,
                    "조회날짜": ymd,
                    "오류": str(e)
                })

                log_message("구성종목 오류:", ymd, e)


    # ------------------------------------------------------------
    # 9. 결과 확인
    # ------------------------------------------------------------

    if len(all_holdings) > 0:
        holdings = pd.concat(all_holdings, ignore_index=True)
    else:
        holdings = pd.DataFrame()

    error_df = pd.DataFrame(error_list)

    log_message("구성종목 수집 건수:", len(all_holdings))
    log_message("구성종목 전체 행 수:", len(holdings))

    # display(holdings.head())

    # log_message("오류 건수:", len(error_df))
    # display(error_df.head())



    # ------------------------------------------------------------
    # 10. 수집 데이터 정리
    # ------------------------------------------------------------


    cols = """
    조회날짜 : 기준일자
    표준코드 : 표준코드
    상품코드 : 상품코드
    상품명 : 상품명
    grpItmNo : 종목표준코드
    ticker : 종목코드
    citmNm : 종목명
    evAmt : 평가금액
    evP : 비중
    curp : 종가
    icuStkc : 수량
    clacRt : 1주수익률
    clac: 등락
    pcurp : 1주전종가
    """

    # 텍스트를 딕셔너리로 변환
    rename_map = {}

    for line in cols.strip().splitlines():
        old_col, new_col = line.split(":", 1)
        rename_map[old_col.strip()] = new_col.strip()

    # 선택할 컬럼 목록
    selected_cols = list(rename_map.keys())

    # 특정 컬럼만 가져오고 동시에 컬럼명 변경
    etf_holdings = holdings[selected_cols].rename(columns=rename_map)






    ######################################################################################################################################




    def make_log_base(etf_holdings):

        # ============================================================
        # 목적
        # 1. 일자별 ln_가격변화, ln_수량변화 적재
        # 2. 시작일~종료일을 선택하면
        #    최종 결과를 비중(%), 비중변동(%p), 가격효과(%p), 수량효과(%p)로 계산
        #
        # 사용 데이터프레임: etf_holdings
        #
        # 필요 컬럼:
        # 기준일자, 상품코드, 상품명, 종목코드, 종목명, 평가금액, 비중, 종가, 수량
        # ============================================================


        # ------------------------------------------------------------
        # 1. 기본 설정
        # ------------------------------------------------------------

        df = etf_holdings.copy()

        date_col = "기준일자"
        fund_code_col = "상품코드"
        fund_name_col = "상품명"
        stock_code_col = "종목코드"
        stock_name_col = "종목명"

        value_col = "평가금액"
        weight_col = "비중"
        price_col = "종가"
        qty_col = "수량"



        # ------------------------------------------------------------
        # 2. 타입 정리
        # ------------------------------------------------------------
        df[date_col] = pd.to_datetime(
            df[date_col].astype(str).str[:10].str.replace("-", "", regex=False),
            format="%Y%m%d",
            errors="coerce"
        )

        df[fund_code_col] = (
            df[fund_code_col]
            .astype(str)
            .str.replace(".0", "", regex=False)
            .str.zfill(6)
        )

        df[stock_code_col] = (
            df[stock_code_col]
            .astype(str)
            .str.replace(".0", "", regex=False)
            .str.zfill(6)
        )

        for c in [value_col, weight_col, price_col, qty_col]:
            df[c] = (
                df[c]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("%", "", regex=False)
                .replace(["", "nan", "None", "NaN"], np.nan)
                .astype(float)
            )



        # ------------------------------------------------------------
        # 2-1. 현금 / 선물 제외
        # 로그 계산, 비중 계산 전에 제외해야 함
        # ------------------------------------------------------------

        df[stock_name_col] = df[stock_name_col].astype(str).str.strip()

        exclude_pattern = (
            "원화현금|현금|예수금|"
            "선물|F 20|F202|"
            "코스피200 F|KOSPI200 F|"
            "KRW CASH|CASH|"
            "코스닥150 F|KOSDAQ150 F"
        )

        df = df[
            ~df[stock_name_col].str.contains(exclude_pattern, case=False, na=False)
        ].copy()

        # 제외 후 인덱스 정리
        df = df.reset_index(drop=True)



        # ------------------------------------------------------------
        # 3. 분석용 가격, 비중 생성
        # ------------------------------------------------------------

        # 가격: 종가 사용
        df["가격"] = df[price_col]

        # 종가가 없거나 0이면 평가금액 / 수량으로 대체
        df["가격_대체값"] = df[value_col] / df[qty_col]

        df.loc[df["가격"].isna() | (df["가격"] <= 0), "가격"] = df.loc[
            df["가격"].isna() | (df["가격"] <= 0),
            "가격_대체값"
        ]

        # 비중: 원자료 비중이 % 단위라고 가정
        # 예: 26.491221 -> 0.26491221
        df["비중_소수"] = df[weight_col] / 100

        # 혹시 비중이 비어 있으면 평가금액 기준으로 계산
        df["펀드일자_평가금액합계"] = df.groupby([fund_code_col, date_col])[value_col].transform("sum")
        df["비중_평가금액기준"] = df[value_col] / df["펀드일자_평가금액합계"]

        df.loc[df["비중_소수"].isna(), "비중_소수"] = df.loc[
            df["비중_소수"].isna(),
            "비중_평가금액기준"
        ]


        # ------------------------------------------------------------
        # 4. 일자별 로그 변화율 적재
        # ------------------------------------------------------------
        df = df.sort_values([fund_code_col, stock_code_col, date_col]).reset_index(drop=True)

        group_keys = [fund_code_col, stock_code_col]

        df["전기준일자"] = df.groupby(group_keys)[date_col].shift(1)
        df["전일가격"] = df.groupby(group_keys)["가격"].shift(1)
        df["전일수량"] = df.groupby(group_keys)[qty_col].shift(1)
        df["전일비중_소수"] = df.groupby(group_keys)["비중_소수"].shift(1)


        def safe_log_ratio(now, prev):
            return np.where(
                now.notna() & prev.notna() & (now > 0) & (prev > 0),
                np.log(now / prev),
                np.nan
            )


        df["ln_가격변화"] = safe_log_ratio(df["가격"], df["전일가격"])
        df["ln_수량변화"] = safe_log_ratio(df[qty_col], df["전일수량"])
        df["ln_비중변화"] = safe_log_ratio(df["비중_소수"], df["전일비중_소수"])

        # 로그 적재용 테이블
        log_base = df[
            [
                date_col,
                "전기준일자",
                fund_code_col,
                fund_name_col,
                stock_code_col,
                stock_name_col,
                "비중_소수",
                "가격",
                qty_col,
                value_col,
                "ln_가격변화",
                "ln_수량변화",
                "ln_비중변화",
            ]
        ].copy()

        log_base = log_base.rename(
            columns={
                date_col: "기준일자",
                fund_code_col: "상품코드",
                fund_name_col: "상품명",
                stock_code_col: "종목코드",
                stock_name_col: "종목명",
                qty_col: "수량",
                value_col: "평가금액",
            }
        )

        log_base = log_base.sort_values(
            ["상품코드", "종목코드", "기준일자"]
        ).reset_index(drop=True)

        return log_base



    # ------------------------------------------------------------
    # 5. log_base 실행 및 etf_holdings에 병합
    # ------------------------------------------------------------


    # log_base 실행 및 필요 컬럼만 남기기
    log_base = make_log_base(etf_holdings)

    log_base_F = log_base.copy()
    log_base_F = log_base_F[["기준일자","상품코드","종목코드","비중_소수","ln_가격변화","ln_수량변화","ln_비중변화"]]


    # etf_holdings 기준일자 양식 변환
    etf_holdings_F = etf_holdings.copy()
    etf_holdings_F["기준일자"] = pd.to_datetime(
        etf_holdings_F["기준일자"].astype(str).str[:10].str.replace("-", "", regex=False),
        format="%Y%m%d",
        errors="coerce"
    )

    # etf_holdings_F로 합치기
    etf_holdings_F = etf_holdings_F.merge(
        log_base_F,
        on=["기준일자", "상품코드", "종목코드"],
        how="left"
    )

    # 최종 결과물
    # display(etf_holdings_F)

    pd.to_pickle((etf_info, etf_holdings_F), cache_path)
    return etf_info, etf_holdings_F


# ------------------------------------------------------------
# 5. 시작일~종료일 가격효과 / 수량효과 분해 함수
# ------------------------------------------------------------

@st.cache_data
def get_period_pp_decomp(
    log_df,
    start_date,
    end_date,
    fund_code=None,
    fund_name=None,
    stock_code=None,
    stock_name=None,
    include_codes= False
):
    """
    최종 산출:
    기준일자, 상품명, 종목명, 비중(%), 비중변동(%p), 가격효과(%p), 수량효과(%p)

    계산 방식:
    1. 시작일 비중 w0 확보
    2. 시작일 초과 ~ 종료일 이하 ln_가격변화, ln_수량변화 합산
    3. 가격배율 = exp(sum ln_가격변화)
    4. 수량배율 = exp(sum ln_수량변화)
    5. 가격만 반영한 가상 비중 계산
    6. 가격효과, 수량효과를 %p로 계산
    """

    temp = log_df.copy()




    # --------------------------------------------------------
    # 1. 날짜 / 문자 컬럼 정리
    # --------------------------------------------------------
    temp["기준일자"] = pd.to_datetime(temp["기준일자"])

    temp["상품코드"] = (
        temp["상품코드"]
        .astype(str)
        .str.replace(".0", "", regex=False)
        .str.strip()
        .str.zfill(6)
    )

    temp["종목코드"] = (
        temp["종목코드"]
        .astype(str)
        .str.replace(".0", "", regex=False)
        .str.strip()
        .str.zfill(6)
    )

    temp["상품명"] = temp["상품명"].astype(str).str.strip()
    temp["종목명"] = temp["종목명"].astype(str).str.strip()

    start_date = pd.to_datetime(str(start_date)[:10].replace("-", ""), format="%Y%m%d")
    end_date = pd.to_datetime(str(end_date)[:10].replace("-", ""), format="%Y%m%d")




    # --------------------------------------------------------
    # 1. 펀드 필터
    # --------------------------------------------------------
    if fund_code is not None:
        fund_code = str(fund_code).replace(".0", "").zfill(6)
        temp = temp[temp["상품코드"] == fund_code].copy()

    if fund_name is not None:
        temp = temp[temp["상품명"] == fund_name].copy()

    # # --------------------------------------------------------
    # # 2. 종목 필터
    # # --------------------------------------------------------
    # if stock_code is not None:
    #     stock_code = str(stock_code).replace(".0", "").zfill(6)
    #     temp = temp[temp["종목코드"] == stock_code].copy()

    # if stock_name is not None:
    #     temp = temp[temp["종목명"] == stock_name].copy()

    # --------------------------------------------------------
    # 3. 시작일 데이터
    # --------------------------------------------------------
    start_df = temp[temp["기준일자"] == start_date].copy()

    start_df = start_df[
        [
            "상품코드",
            "상품명",
            "종목코드",
            "종목명",
            "비중_소수",
        ]
    ].rename(columns={"비중_소수": "시작비중_소수"})

    # --------------------------------------------------------
    # 4. 종료일 실제 비중
    # --------------------------------------------------------
    end_df = temp[temp["기준일자"] == end_date].copy()

    end_df = end_df[
        [
            "상품코드",
            "종목코드",
            "비중_소수",
        ]
    ].rename(columns={"비중_소수": "종료비중_소수"})

    # --------------------------------------------------------
    # 5. 기간 로그 변화율
    # --------------------------------------------------------
    period_ln = temp[
        (temp["기준일자"] > start_date)
        & (temp["기준일자"] <= end_date)
    ].copy()

    period_ln = (
        period_ln.groupby(["상품코드", "상품명", "종목코드", "종목명"], as_index=False)
        .agg(
            ln_가격변화=("ln_가격변화", "sum"),
            ln_수량변화=("ln_수량변화", "sum"),
            관측일수=("기준일자", "nunique"),
        )
    )

    # --------------------------------------------------------
    # 6. 시작일, 종료일, 로그 변화율 합치기
    # --------------------------------------------------------
    base = (
        start_df
        .merge(
            period_ln,
            on=["상품코드", "상품명", "종목코드", "종목명"],
            how="inner"
        )
        .merge(
            end_df,
            on=["상품코드", "종목코드"],
            how="inner"
        )
    )

    # --------------------------------------------------------
    # 7. 결과가 비어 있으면 안내용 빈 데이터프레임 반환
    # --------------------------------------------------------
    if base.empty:
        log_message("조건에 맞는 데이터가 없습니다. 시작일/종료일/펀드명/종목명을 확인하세요.")
        return pd.DataFrame()

    # --------------------------------------------------------
    # 8. 로그 합산값을 가격배율, 수량배율로 변환
    # --------------------------------------------------------
    base["가격배율"] = np.exp(base["ln_가격변화"])
    base["수량배율"] = np.exp(base["ln_수량변화"])

    # --------------------------------------------------------
    # 9. 가격만 반영한 가상 비중
    # 원자료 비중을 그대로 유지하는 버전
    #
    # 현금/선물을 제외했기 때문에 남은 종목 비중 합계가 100%가 아닐 수 있음.
    # 따라서 제외된 비중은 '기타/현금/선물'로 보고 가격 변화 없음, 즉 배율 1로 둠.
    # --------------------------------------------------------

    base["가격만반영_비중분자"] = base["시작비중_소수"] * base["가격배율"]

    # 남아 있는 주식들의 시작 비중 합계
    base["시작비중합계_주식"] = base.groupby(["상품코드"])["시작비중_소수"].transform("sum")

    # 제외된 현금/선물/기타 비중
    base["제외비중"] = 1 - base["시작비중합계_주식"]

    # 혹시 원자료 비중 합계가 100%를 살짝 넘는 경우 방어
    base["제외비중"] = base["제외비중"].clip(lower=0)

    # 가격 반영된 주식 비중 합계
    base["가격반영비중합계_주식"] = base.groupby(["상품코드"])["가격만반영_비중분자"].transform("sum")

    # 전체 분모 = 가격 반영 주식 비중 합계 + 제외비중
    base["가격만반영_분모"] = base["가격반영비중합계_주식"] + base["제외비중"]

    base["가격만반영_비중"] = (
        base["가격만반영_비중분자"] / base["가격만반영_분모"]
    )

    # --------------------------------------------------------
    # 10. %p 기준 분해
    # --------------------------------------------------------
    base["비중"] = base["종료비중_소수"] * 100

    base["비중변동"] = (
        base["종료비중_소수"] - base["시작비중_소수"]
    ) * 100

    base["가격효과"] = (
        base["가격만반영_비중"] - base["시작비중_소수"]
    ) * 100

    base["수량효과"] = (
        base["종료비중_소수"] - base["가격만반영_비중"]
    ) * 100

    base["검산"] = base["가격효과"] + base["수량효과"]
    base["분해오차"] = base["비중변동"] - base["검산"]

    base["기준일자"] = end_date.strftime("%Y%m%d")
    base["시작일자"] = start_date.strftime("%Y%m%d")


    # --------------------------------------------------------
    # 10-1. 종목 필터는 계산 후 마지막에 적용
    # --------------------------------------------------------
    if stock_code is not None:
        stock_code = str(stock_code).replace(".0", "").strip().zfill(6)
        base = base[
            base["종목코드"].astype(str).str.replace(".0", "", regex=False).str.strip().str.zfill(6) == stock_code
        ].copy()

    if stock_name is not None:
        stock_name = str(stock_name).strip()
        base = base[
            base["종목명"].astype(str).str.strip() == stock_name
        ].copy()

    if base.empty:
        log_message("계산은 완료됐지만, 선택한 종목 조건에 맞는 결과가 없습니다.")
        return pd.DataFrame()

    # --------------------------------------------------------
    # 11. 최종 컬럼
    # --------------------------------------------------------
    if include_codes:
        result_cols = [
            "시작일자",
            "기준일자",
            "상품코드",
            "상품명",
            "종목코드",
            "종목명",
            "관측일수",
            "비중",
            "비중변동",
            "가격효과",
            "수량효과",
            "분해오차",
        ]
    else:
        result_cols = [
            "시작일자",
            "기준일자",
            "상품명",
            "종목명",
            "비중",
            "비중변동",
            "가격효과",
            "수량효과",
        ]



    result = base[result_cols].copy()

    num_cols = result.select_dtypes(include=[np.number]).columns
    result[num_cols] = result[num_cols].round(6)

    result = result.sort_values(
        ["상품명", "비중"],
        ascending=[True, False]
    ).reset_index(drop=True)

    return result

# ============================================================
# 6. Streamlit 대시보드 화면
# ============================================================

DATE = "기준일자"
START_DATE = "시작일자"
FUND_CODE = "상품코드"
FUND_NAME = "상품명"
STOCK_CODE = "종목코드"
STOCK_NAME = "종목명"
WEIGHT = "비중"
WEIGHT_DECIMAL = "비중_소수"
WEIGHT_CHANGE = "비중변동"
PRICE_EFFECT = "가격효과"
QTY_EFFECT = "수량효과"

DISPLAY_COLS = [
    START_DATE,
    DATE,
    FUND_NAME,
    STOCK_NAME,
    WEIGHT,
    WEIGHT_CHANGE,
    PRICE_EFFECT,
    QTY_EFFECT,
]

TOP_DISPLAY_COLS = [
    STOCK_NAME,
    "포함펀드수",
    WEIGHT,
    WEIGHT_CHANGE,
    PRICE_EFFECT,
    QTY_EFFECT,
]

EFFECT_DISPLAY_COLS = [
    STOCK_NAME,
    "포함펀드수",
    WEIGHT,
    WEIGHT_CHANGE,
    PRICE_EFFECT,
    QTY_EFFECT,
]

NUMERIC_FORMATS = {
    WEIGHT: "%.3f",
    WEIGHT_CHANGE: "%.4f",
    PRICE_EFFECT: "%.4f",
    QTY_EFFECT: "%.4f",
}

COLOR_POSITIVE = "#0F766E"
COLOR_NEGATIVE = "#B91C1C"
COLOR_PRICE = "#2563EB"
COLOR_QTY = "#F59E0B"
COLOR_NEUTRAL = "#64748B"


def normalize_code(series):
    return (
        series.astype(str)
        .str.replace(".0", "", regex=False)
        .str.strip()
        .str.zfill(6)
    )


def prepare_log_df(etf_holdings):
    required_cols = [
        DATE,
        FUND_CODE,
        FUND_NAME,
        STOCK_CODE,
        STOCK_NAME,
        WEIGHT_DECIMAL,
        "ln_가격변화",
        "ln_수량변화",
        "ln_비중변화",
    ]
    missing_cols = [col for col in required_cols if col not in etf_holdings.columns]
    if missing_cols:
        st.error(f"필수 컬럼이 없습니다: {', '.join(missing_cols)}")
        st.stop()

    log_df = etf_holdings[required_cols].copy()
    log_df[DATE] = pd.to_datetime(log_df[DATE], errors="coerce")
    log_df[FUND_CODE] = normalize_code(log_df[FUND_CODE])
    log_df[STOCK_CODE] = normalize_code(log_df[STOCK_CODE])
    log_df[FUND_NAME] = log_df[FUND_NAME].astype(str).str.strip()
    log_df[STOCK_NAME] = log_df[STOCK_NAME].astype(str).str.strip()
    log_df = log_df.dropna(subset=[DATE, WEIGHT_DECIMAL]).copy()
    return log_df


def format_date(value):
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def round_numbers(df, digits=4):
    result_df = df.copy()
    num_cols = result_df.select_dtypes(include=np.number).columns
    result_df[num_cols] = result_df[num_cols].round(digits)
    return result_df


def make_top_change(result_df, n):
    stock_rank = (
        result_df.groupby(STOCK_NAME, as_index=False)
        .agg(
            포함펀드수=(FUND_NAME, "nunique"),
            **{
                WEIGHT: (WEIGHT, "mean"),
                WEIGHT_CHANGE: (WEIGHT_CHANGE, "sum"),
                PRICE_EFFECT: (PRICE_EFFECT, "sum"),
                QTY_EFFECT: (QTY_EFFECT, "sum"),
            },
        )
    )

    top_up = stock_rank.nlargest(n, WEIGHT_CHANGE).copy()
    top_down = stock_rank.nsmallest(n, WEIGHT_CHANGE).copy()
    top_change = (
        pd.concat([top_up, top_down], ignore_index=True)
        .drop_duplicates(subset=[STOCK_NAME, WEIGHT_CHANGE])
        .copy()
    )
    top_change["방향"] = np.where(top_change[WEIGHT_CHANGE] >= 0, "증가", "감소")
    top_change["표시명"] = top_change[STOCK_NAME]
    return top_up, top_down, top_change


def make_effect_rank(result_df, effect_col, n):
    effect_rank = (
        result_df.groupby(STOCK_NAME, as_index=False)
        .agg(
            포함펀드수=(FUND_NAME, "nunique"),
            **{
                WEIGHT: (WEIGHT, "mean"),
                WEIGHT_CHANGE: (WEIGHT_CHANGE, "sum"),
                PRICE_EFFECT: (PRICE_EFFECT, "sum"),
                QTY_EFFECT: (QTY_EFFECT, "sum"),
            },
        )
    )

    top_up = effect_rank.nlargest(n, effect_col).copy()
    top_down = effect_rank.nsmallest(n, effect_col).copy()
    top_change = (
        pd.concat([top_up, top_down], ignore_index=True)
        .drop_duplicates(subset=[STOCK_NAME, effect_col])
        .copy()
    )
    top_change["방향"] = np.where(top_change[effect_col] >= 0, "증가", "감소")
    top_change["표시명"] = top_change[STOCK_NAME]
    return top_up, top_down, top_change


def summarize_by_fund(result_df):
    summary = (
        result_df.groupby(FUND_NAME, as_index=False)
        .agg(
            종목수=(STOCK_NAME, "nunique"),
            평균비중=(WEIGHT, "mean"),
            비중변동합계=(WEIGHT_CHANGE, "sum"),
            가격효과합계=(PRICE_EFFECT, "sum"),
            수량효과합계=(QTY_EFFECT, "sum"),
            비중변동강도=(WEIGHT_CHANGE, lambda x: x.abs().sum() / 2),
            가격효과강도=(PRICE_EFFECT, lambda x: x.abs().sum() / 2),
            수량효과강도=(QTY_EFFECT, lambda x: x.abs().sum() / 2),
        )
        .sort_values("비중변동강도", ascending=False)
        .reset_index(drop=True)
    )
    return round_numbers(summary)


def summarize_by_stock(result_df):
    summary = (
        result_df.groupby(STOCK_NAME, as_index=False)
        .agg(
            포함펀드수=(FUND_NAME, "nunique"),
            평균비중=(WEIGHT, "mean"),
            평균비중변동=(WEIGHT_CHANGE, "mean"),
            평균가격효과=(PRICE_EFFECT, "mean"),
            평균수량효과=(QTY_EFFECT, "mean"),
            비중변동합계=(WEIGHT_CHANGE, "sum"),
            가격효과합계=(PRICE_EFFECT, "sum"),
            수량효과합계=(QTY_EFFECT, "sum"),
        )
        .sort_values("평균비중", ascending=False)
        .reset_index(drop=True)
    )
    return round_numbers(summary)


def apply_common_layout(fig, height=480, x_zero_line=True):
    fig.update_layout(
        height=height,
        margin=dict(l=20, r=24, t=58, b=28),
        legend_title_text="",
        hovermode="closest",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=13),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#E5E7EB", zeroline=x_zero_line, zerolinecolor="#111827")
    fig.update_yaxes(showgrid=False)
    return fig


def styled_table(df, height=460):
    return st.dataframe(
        round_numbers(df),
        use_container_width=True,
        height=height,
    )


st.set_page_config(
    page_title="ETF 구성종목 비중변화 대시보드",
    layout="wide",
)

st.title("ETF 구성종목 비중변화 대시보드")
st.caption("기간별 구성종목 비중변화를 가격효과와 수량효과로 분해하고, 변동이 큰 ETF와 종목을 시각적으로 비교합니다.")

with st.sidebar:
    st.header("데이터 수집")
    collection_start_date = st.text_input("수집 시작일", DEFAULT_COLLECT_START_DATE)
    collection_end_date = st.text_input("수집 종료일", DEFAULT_COLLECT_END_DATE)
    force_refresh = st.checkbox(
        "데이터 새로 수집",
        value=False,
        help="끄면 입력한 수집 기간에 해당하는 캐시 파일 또는 Streamlit 캐시를 먼저 사용합니다.",
    )

collection_start_date = collection_start_date.strip().replace("-", "")
collection_end_date = collection_end_date.strip().replace("-", "")

try:
    pd.to_datetime(collection_start_date, format="%Y%m%d")
    pd.to_datetime(collection_end_date, format="%Y%m%d")
except ValueError:
    st.error("수집 시작일과 종료일은 YYYYMMDD 형식으로 입력하세요. 예: 20260501")
    st.stop()

if pd.to_datetime(collection_start_date, format="%Y%m%d") > pd.to_datetime(collection_end_date, format="%Y%m%d"):
    st.error("수집 시작일은 수집 종료일보다 이전이어야 합니다.")
    st.stop()

etf_info, etf_holdings_F = load_etf_holdings(
    collection_start_date=collection_start_date,
    collection_end_date=collection_end_date,
    force_refresh=force_refresh,
)
log_df = prepare_log_df(etf_holdings_F)

if log_df.empty:
    st.error("분석 가능한 데이터가 없습니다.")
    st.stop()

date_list = sorted(log_df[DATE].dropna().unique())
if len(date_list) < 2:
    st.error("기준일자가 2개 이상 필요합니다.")
    st.stop()

fund_list = sorted(log_df[FUND_NAME].dropna().unique())
stock_list = sorted(log_df[STOCK_NAME].dropna().unique())

with st.sidebar:
    st.header("분석 조건")
    st_date = st.selectbox(
        "시작일자",
        date_list,
        index=0,
        format_func=format_date,
    )
    ed_date = st.selectbox(
        "기준일자",
        date_list,
        index=len(date_list) - 1,
        format_func=format_date,
    )

    top_n = st.slider("Top N", min_value=5, max_value=50, value=20, step=5)
    show_raw = st.checkbox("원본 데이터 미리보기", value=False)

if pd.to_datetime(st_date) >= pd.to_datetime(ed_date):
    st.warning("시작일자는 기준일자보다 이전이어야 합니다.")
    st.stop()

result = get_period_pp_decomp(
    log_df,
    start_date=st_date,
    end_date=ed_date,
    include_codes=True,
)

if result.empty:
    st.warning("선택 조건에 맞는 결과가 없습니다.")
    st.stop()

result = round_numbers(result)
top_up, top_down, top_change = make_top_change(result, top_n)
fund_summary = summarize_by_fund(result)
stock_summary = summarize_by_stock(result)
price_up, price_down, price_change = make_effect_rank(result, PRICE_EFFECT, top_n)
qty_up, qty_down, qty_change = make_effect_rank(result, QTY_EFFECT, top_n)

period_label = f"{format_date(st_date)} ~ {format_date(ed_date)}"
abs_change = result[WEIGHT_CHANGE].abs().sum() / 2
price_strength = result[PRICE_EFFECT].abs().sum() / 2
qty_strength = result[QTY_EFFECT].abs().sum() / 2

st.markdown(f"**분석 기간:** {period_label}")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("펀드 수", f"{result[FUND_NAME].nunique():,.0f}")
m2.metric("종목 수", f"{result[STOCK_NAME].nunique():,.0f}")
m3.metric("비중변동 강도", f"{abs_change:,.2f}%p")
m4.metric("가격효과 강도", f"{price_strength:,.2f}%p")
m5.metric("수량효과 강도", f"{qty_strength:,.2f}%p")

tab_overview, tab_change, tab_effect, tab_effect_rank, tab_stock, tab_fund, tab_data, tab_etf = st.tabs(
    ["개요", "Top 변동", "효과 분해", "효과별 변동", "종목 분석", "펀드 분석", "상세 데이터", "ETF 정보"]
)

with tab_overview:
    left, right = st.columns([1.2, 1])

    with left:
        chart_df = fund_summary.head(20).melt(
            id_vars=FUND_NAME,
            value_vars=["가격효과강도", "수량효과강도"],
            var_name="효과",
            value_name="강도",
        )
        fig = px.bar(
            chart_df,
            x="강도",
            y=FUND_NAME,
            color="효과",
            orientation="h",
            title="펀드별 변동 강도",
            color_discrete_map={"가격효과강도": COLOR_PRICE, "수량효과강도": COLOR_QTY},
            labels={"강도": "절대 강도(%p)", FUND_NAME: ""},
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(
            apply_common_layout(fig, height=520, x_zero_line=False),
            use_container_width=True,
            key="overview_fund_strength_chart",
        )

    with right:
        donut = go.Figure(
            data=[
                go.Pie(
                    labels=["가격효과", "수량효과"],
                    values=[price_strength, qty_strength],
                    hole=0.62,
                    marker=dict(colors=[COLOR_PRICE, COLOR_QTY]),
                    textinfo="label+percent",
                )
            ]
        )
        donut.update_layout(
            title="효과 기여도",
            height=300,
            margin=dict(l=16, r=16, t=58, b=10),
            legend_title_text="",
        )
        st.plotly_chart(donut, use_container_width=True, key="overview_effect_donut")

        scatter = px.scatter(
            result,
            x=PRICE_EFFECT,
            y=QTY_EFFECT,
            size=result[WEIGHT].clip(lower=0.01),
            color=WEIGHT_CHANGE,
            hover_name=STOCK_NAME,
            hover_data=[FUND_NAME, WEIGHT, WEIGHT_CHANGE],
            color_continuous_scale="RdBu",
            color_continuous_midpoint=0,
            title="가격효과 vs 수량효과",
            labels={PRICE_EFFECT: "가격효과(%p)", QTY_EFFECT: "수량효과(%p)", WEIGHT_CHANGE: "비중변동"},
        )
        st.plotly_chart(
            apply_common_layout(scatter, height=300),
            use_container_width=True,
            key="overview_effect_scatter",
        )

with tab_change:
    top_chart = top_change.sort_values(WEIGHT_CHANGE).copy()
    fig = px.bar(
        top_chart,
        x=WEIGHT_CHANGE,
        y="표시명",
        color="방향",
        orientation="h",
        title=f"비중변동 상위/하위 {top_n}개",
        color_discrete_map={"증가": COLOR_POSITIVE, "감소": COLOR_NEGATIVE},
        labels={WEIGHT_CHANGE: "비중변동(%p)", "표시명": ""},
        hover_data=[STOCK_NAME, "포함펀드수", WEIGHT, PRICE_EFFECT, QTY_EFFECT],
    )
    st.plotly_chart(
        apply_common_layout(fig, height=max(460, 26 * len(top_chart))),
        use_container_width=True,
        key="top_change_bar_chart",
    )

    col_up, col_down = st.columns(2)
    with col_up:
        st.markdown("#### 비중 증가")
        styled_table(top_up[TOP_DISPLAY_COLS], height=420)
    with col_down:
        st.markdown("#### 비중 감소")
        styled_table(top_down[TOP_DISPLAY_COLS], height=420)

with tab_effect:
    effect_long = top_change[["표시명", PRICE_EFFECT, QTY_EFFECT]].melt(
        id_vars="표시명",
        value_vars=[PRICE_EFFECT, QTY_EFFECT],
        var_name="효과",
        value_name="효과값",
    )
    fig = px.bar(
        effect_long,
        x="효과값",
        y="표시명",
        color="효과",
        orientation="h",
        barmode="relative",
        title="Top 변동 종목의 가격효과 / 수량효과",
        color_discrete_map={PRICE_EFFECT: COLOR_PRICE, QTY_EFFECT: COLOR_QTY},
        labels={"효과값": "효과(%p)", "표시명": ""},
    )
    st.plotly_chart(
        apply_common_layout(fig, height=max(460, 26 * top_change["표시명"].nunique())),
        use_container_width=True,
        key="effect_decomp_bar_chart",
    )

    selected_item = st.selectbox("워터폴로 볼 종목", top_change["표시명"].tolist())
    selected_row = top_change[top_change["표시명"] == selected_item].iloc[0]
    waterfall = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["relative", "relative", "total"],
            x=["가격효과", "수량효과", "비중변동"],
            y=[selected_row[PRICE_EFFECT], selected_row[QTY_EFFECT], selected_row[WEIGHT_CHANGE]],
            connector={"line": {"color": COLOR_NEUTRAL}},
            increasing={"marker": {"color": COLOR_POSITIVE}},
            decreasing={"marker": {"color": COLOR_NEGATIVE}},
            totals={"marker": {"color": COLOR_NEUTRAL}},
        )
    )
    waterfall.update_layout(
        title=f"{selected_item} 효과 분해",
        yaxis_title="%p",
        height=380,
        margin=dict(l=20, r=24, t=58, b=28),
    )
    st.plotly_chart(waterfall, use_container_width=True, key="effect_waterfall_chart")

with tab_effect_rank:
    st.markdown("### 효과별 변동 종목")

    price_tab, qty_tab = st.tabs(["가격효과", "수량효과"])

    with price_tab:
        price_chart = price_change.sort_values(PRICE_EFFECT).copy()
        fig = px.bar(
            price_chart,
            x=PRICE_EFFECT,
            y="표시명",
            color="방향",
            orientation="h",
            title=f"가격효과 상위/하위 {top_n}개 종목",
            color_discrete_map={"증가": COLOR_POSITIVE, "감소": COLOR_NEGATIVE},
            labels={PRICE_EFFECT: "가격효과(%p)", "표시명": ""},
            hover_data=[STOCK_NAME, "포함펀드수", WEIGHT, WEIGHT_CHANGE, QTY_EFFECT],
        )
        st.plotly_chart(
            apply_common_layout(fig, height=max(460, 28 * len(price_chart))),
            use_container_width=True,
            key="price_effect_rank_chart",
        )

        p_up, p_down = st.columns(2)
        with p_up:
            st.markdown("#### 가격효과 상위")
            styled_table(price_up[EFFECT_DISPLAY_COLS], height=360)
        with p_down:
            st.markdown("#### 가격효과 하위")
            styled_table(price_down[EFFECT_DISPLAY_COLS], height=360)

    with qty_tab:
        qty_chart = qty_change.sort_values(QTY_EFFECT).copy()
        fig = px.bar(
            qty_chart,
            x=QTY_EFFECT,
            y="표시명",
            color="방향",
            orientation="h",
            title=f"수량효과 상위/하위 {top_n}개 종목",
            color_discrete_map={"증가": COLOR_POSITIVE, "감소": COLOR_NEGATIVE},
            labels={QTY_EFFECT: "수량효과(%p)", "표시명": ""},
            hover_data=[STOCK_NAME, "포함펀드수", WEIGHT, WEIGHT_CHANGE, PRICE_EFFECT],
        )
        st.plotly_chart(
            apply_common_layout(fig, height=max(460, 28 * len(qty_chart))),
            use_container_width=True,
            key="qty_effect_rank_chart",
        )

        q_up, q_down = st.columns(2)
        with q_up:
            st.markdown("#### 수량효과 상위")
            styled_table(qty_up[EFFECT_DISPLAY_COLS], height=360)
        with q_down:
            st.markdown("#### 수량효과 하위")
            styled_table(qty_down[EFFECT_DISPLAY_COLS], height=360)

with tab_stock:
    selected_stock = st.selectbox("분석할 종목", ["선택하세요"] + stock_list, key="stock_analysis_select")

    if selected_stock == "선택하세요":
        st.info("종목을 하나 선택하면, 해당 종목을 보유한 ETF별 비중과 비중변동을 볼 수 있습니다.")
    else:
        stock_result = get_period_pp_decomp(
            log_df,
            start_date=st_date,
            end_date=ed_date,
            stock_name=selected_stock,
            include_codes=True,
        )
        stock_result = round_numbers(stock_result)

    if selected_stock != "선택하세요" and stock_result.empty:
        st.warning("선택한 종목에 대한 기간 분석 결과가 없습니다.")
    elif selected_stock != "선택하세요":
        st.markdown(f"### {selected_stock} ETF별 보유/변동")
        stock_view = stock_result.sort_values(WEIGHT, ascending=False).copy()

        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("보유 ETF 수", f"{stock_view[FUND_NAME].nunique():,.0f}")
        sc2.metric("평균 비중", f"{stock_view[WEIGHT].mean():.3f}%")
        sc3.metric("비중변동 합계", f"{stock_view[WEIGHT_CHANGE].sum():.4f}%p")
        sc4.metric("수량효과 합계", f"{stock_view[QTY_EFFECT].sum():.4f}%p")

        stock_weight_fig = px.bar(
            stock_view.sort_values(WEIGHT),
            x=WEIGHT,
            y=FUND_NAME,
            color=WEIGHT_CHANGE,
            orientation="h",
            title=f"{selected_stock} ETF별 현재 비중",
            color_continuous_scale="RdBu",
            color_continuous_midpoint=0,
            labels={WEIGHT: "비중(%)", FUND_NAME: "", WEIGHT_CHANGE: "비중변동"},
            hover_data=[WEIGHT_CHANGE, PRICE_EFFECT, QTY_EFFECT],
        )
        st.plotly_chart(
            apply_common_layout(stock_weight_fig, height=max(420, 28 * len(stock_view)), x_zero_line=False),
            use_container_width=True,
            key="stock_weight_by_etf_chart",
        )

        stock_effect_long = stock_view[[FUND_NAME, PRICE_EFFECT, QTY_EFFECT]].melt(
            id_vars=FUND_NAME,
            value_vars=[PRICE_EFFECT, QTY_EFFECT],
            var_name="효과",
            value_name="효과값",
        )
        stock_effect_fig = px.bar(
            stock_effect_long,
            x="효과값",
            y=FUND_NAME,
            color="효과",
            orientation="h",
            barmode="relative",
            title=f"{selected_stock} ETF별 가격효과 / 수량효과",
            color_discrete_map={PRICE_EFFECT: COLOR_PRICE, QTY_EFFECT: COLOR_QTY},
            labels={"효과값": "효과(%p)", FUND_NAME: ""},
        )
        st.plotly_chart(
            apply_common_layout(stock_effect_fig, height=max(420, 28 * stock_view[FUND_NAME].nunique())),
            use_container_width=True,
            key="stock_effect_by_etf_chart",
        )

        styled_table(stock_view[[FUND_NAME, WEIGHT, WEIGHT_CHANGE, PRICE_EFFECT, QTY_EFFECT]], height=420)

with tab_fund:
    selected_fund = st.selectbox("분석할 펀드", ["선택하세요"] + fund_list, key="fund_analysis_select")

    if selected_fund == "선택하세요":
        st.info("펀드를 하나 선택하면, 해당 펀드의 구성종목 비중과 비중변동을 볼 수 있습니다.")
    else:
        fund_result = get_period_pp_decomp(
            log_df,
            start_date=st_date,
            end_date=ed_date,
            fund_name=selected_fund,
            include_codes=True,
        )
        fund_result = round_numbers(fund_result)

    if selected_fund != "선택하세요" and fund_result.empty:
        st.warning("선택한 펀드에 대한 기간 분석 결과가 없습니다.")
    elif selected_fund != "선택하세요":
        st.markdown(f"### {selected_fund} 구성종목 변화")
        fund_view = fund_result.sort_values(WEIGHT_CHANGE, ascending=False).copy()
        fund_view["방향"] = np.where(fund_view[WEIGHT_CHANGE] >= 0, "증가", "감소")

        fc1, fc2, fc3, fc4 = st.columns(4)
        fc1.metric("구성종목 수", f"{fund_view[STOCK_NAME].nunique():,.0f}")
        fc2.metric("비중변동 강도", f"{fund_view[WEIGHT_CHANGE].abs().sum() / 2:,.2f}%p")
        fc3.metric("가격효과 강도", f"{fund_view[PRICE_EFFECT].abs().sum() / 2:,.2f}%p")
        fc4.metric("수량효과 강도", f"{fund_view[QTY_EFFECT].abs().sum() / 2:,.2f}%p")

        fund_top = pd.concat(
            [
                fund_view.nlargest(top_n, WEIGHT_CHANGE),
                fund_view.nsmallest(top_n, WEIGHT_CHANGE),
            ],
            ignore_index=True,
        ).drop_duplicates(subset=[STOCK_NAME, WEIGHT_CHANGE])

        fund_change_fig = px.bar(
            fund_top.sort_values(WEIGHT_CHANGE),
            x=WEIGHT_CHANGE,
            y=STOCK_NAME,
            color="방향",
            orientation="h",
            title=f"{selected_fund} 구성종목 비중변동 상위/하위 {top_n}개",
            color_discrete_map={"증가": COLOR_POSITIVE, "감소": COLOR_NEGATIVE},
            labels={WEIGHT_CHANGE: "비중변동(%p)", STOCK_NAME: ""},
            hover_data=[WEIGHT, PRICE_EFFECT, QTY_EFFECT],
        )
        st.plotly_chart(
            apply_common_layout(fund_change_fig, height=max(460, 28 * len(fund_top))),
            use_container_width=True,
            key="fund_constituent_change_chart",
        )

        fund_weight_top = fund_view.nlargest(min(top_n, len(fund_view)), WEIGHT).sort_values(WEIGHT)
        fund_weight_fig = px.bar(
            fund_weight_top,
            x=WEIGHT,
            y=STOCK_NAME,
            color=WEIGHT_CHANGE,
            orientation="h",
            title=f"{selected_fund} 주요 보유종목 현재 비중",
            color_continuous_scale="RdBu",
            color_continuous_midpoint=0,
            labels={WEIGHT: "비중(%)", STOCK_NAME: "", WEIGHT_CHANGE: "비중변동"},
            hover_data=[WEIGHT_CHANGE, PRICE_EFFECT, QTY_EFFECT],
        )
        st.plotly_chart(
            apply_common_layout(fund_weight_fig, height=max(420, 28 * len(fund_weight_top)), x_zero_line=False),
            use_container_width=True,
            key="fund_constituent_weight_chart",
        )

        styled_table(fund_view[DISPLAY_COLS], height=520)

with tab_data:
    st.markdown("### 기간별 분해 결과")
    styled_table(result[DISPLAY_COLS], height=520)

    csv = result[DISPLAY_COLS].to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "결과 CSV 다운로드",
        data=csv,
        file_name="ETF_비중변화_분해결과.csv",
        mime="text/csv",
    )

    st.markdown("### 펀드별 요약")
    styled_table(fund_summary, height=360)

    st.markdown("### 종목별 요약")
    styled_table(stock_summary, height=420)

    if show_raw:
        st.markdown("### 원본 데이터 미리보기")
        st.dataframe(etf_holdings_F.head(200), use_container_width=True, height=420)

with tab_etf:
    st.markdown("### ETF 기본 정보")
    etf_cols = [
        "상품명",
        "운용사명",
        "기초지수",
        "운용규모",
        "상장일",
        "ETF유형",
        "위험등급",
        "총보수",
        "1일",
        "0주",
        "1개월",
        "YTD",
        "ETF링크",
    ]
    available_cols = [col for col in etf_cols if col in etf_info.columns]
    st.dataframe(etf_info[available_cols], use_container_width=True, height=520)

    csv_etf_info = etf_info.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "ETF 정보 CSV 다운로드",
        data=csv_etf_info,
        file_name="ETF_기본정보.csv",
        mime="text/csv",
    )
