import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import plotly.express as px

# ---------------------------------------------------------
# 1. 데이터 수집: BeautifulSoup을 활용한 환율 크롤링
# ---------------------------------------------------------
@st.cache_data(ttl=3600) # 1시간마다 갱신
def get_exchange_rates():
    """네이버 금융 환율 크롤링 (개별 실패 시 기본값 유지)"""
    # 1. 만약을 대비한 통화별 기본값(Fallback) 사전 정의
    rates = {
        'KRW': 1.0,
        'USD': 1500.0,
        'JPY': 9.5,
        'EUR': 1700.0
    }
    
    url = "https://finance.naver.com/marketindex/exchangeList.naver"
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        rows = soup.select('table.tbl_exchange tbody tr')
        
        # 2. 크롤링한 데이터로 성공한 것만 덮어쓰기
        for row in rows:
            try:
                currency_name = row.select_one('td.tit a').text.strip()
                
                # 명확하게 우리가 타겟팅하는 통화 코드만 추출
                currency_code = None
                if 'USD' in currency_name: currency_code = 'USD'
                elif 'JPY' in currency_name: currency_code = 'JPY'
                elif 'EUR' in currency_name: currency_code = 'EUR'
                
                # 타겟 통화인 경우에만 환율 추출 시도
                if currency_code:
                    rate_str = row.select_one('td.sale').text.strip().replace(',', '')
                    rate = float(rate_str)
                    
                    # 일본 엔화(JPY)는 100엔 기준이므로 1엔 기준으로 보정
                    if currency_code == 'JPY':
                        rate = rate / 100
                        
                    # 크롤링 및 계산에 성공했다면 해당 통화의 값 업데이트
                    rates[currency_code] = rate
                    
            except Exception:
                # 개별 행(특정 통화) 파싱 중 에러가 나면 해당 통화는 건너뜀
                # -> 사전에 정의한 rates의 기본값이 그대로 유지됨
                continue
                
    except Exception as e:
        # 사이트 접속 자체가 안 되는 등 치명적 오류 시 전체 기본값 사용 및 경고
        st.warning(f"웹 사이트 연결 오류로 전체 환율 기본값을 사용합니다. (사유: {e})")
        
    return rates

exchange_rates = get_exchange_rates()

# ---------------------------------------------------------
# 2. 최소 송금 횟수 최적화 알고리즘
# ---------------------------------------------------------
def optimize_transactions(balances):
    """Net Balance를 기반으로 최소 송금 경로를 계산합니다."""
    # 빚진 사람(Debtors: 잔액 < 0)과 받을 사람(Creditors: 잔액 > 0) 분리
    debtors = [[k, -v] for k, v in balances.items() if v < -0.1]
    creditors = [[k, v] for k, v in balances.items() if v > 0.1]

    # 금액이 큰 순서대로 정렬
    debtors.sort(key=lambda x: x[1], reverse=True)
    creditors.sort(key=lambda x: x[1], reverse=True)

    transactions = []
    i, j = 0, 0
    
    while i < len(debtors) and j < len(creditors):
        debtor, debt_amt = debtors[i]
        creditor, cred_amt = creditors[j]

        # 송금할 금액은 둘 중 작은 금액
        settle_amt = min(debt_amt, cred_amt)
        transactions.append({'보내는 사람': debtor, '받는 사람': creditor, '금액(원)': round(settle_amt)})

        # 잔액 차감
        debtors[i][1] -= settle_amt
        creditors[j][1] -= settle_amt

        if debtors[i][1] <= 0.1: i += 1
        if creditors[j][1] <= 0.1: j += 1
        
    return transactions

# ---------------------------------------------------------
# 3. 화면 구성 및 상태 관리 (Streamlit UI)
# ---------------------------------------------------------
st.set_page_config(page_title="스마트 여행 정산", layout="wide")

# 세션 상태 초기화 (지출 내역 저장용)
if 'expenses' not in st.session_state:
    st.session_state.expenses = []

# --- 사이드바: 기본 설정 ---
st.sidebar.title("✈️ 여행 기본 설정")
project_name = st.sidebar.text_input("프로젝트/여행명", "제주도 워크샵")
participants_str = st.sidebar.text_input("참여자 명단 (쉼표로 구분)", "김철수, 이영희, 박지민")
participants = [p.strip() for p in participants_str.split(',') if p.strip()]

st.sidebar.markdown("---")
st.sidebar.subheader("💱 현재 적용 환율 (1 단위 당 원화)")
st.sidebar.info(f"USD: {exchange_rates.get('USD', 0):.2f}원\n\nJPY: {exchange_rates.get('JPY', 0):.2f}원\n\nEUR: {exchange_rates.get('EUR', 0):.2f}원")


st.title(f"📊 {project_name} - 지출 최적화 대시보드")

# --- 메인 화면 탭 구성 ---
tab1, tab2, tab3 = st.tabs(["📝 지출 내역 등록", "📈 분석 대시보드", "💸 최종 정산 리포트"])

# Tab 1: 지출 내역 등록
with tab1:
    st.subheader("새 지출 내역 추가")
    if not participants:
        st.warning("사이드바에서 참여자를 먼저 입력해주세요.")
    else:
        with st.form("expense_form"):
            col1, col2, col3 = st.columns(3)
            expense_name = col1.text_input("지출 항목 (예: 흑돼지 회식)")
            payer = col2.selectbox("결제자", participants)
            category = col3.selectbox("카테고리", ["식비", "교통", "숙박", "액티비티", "기타"])
            
            col4, col5 = st.columns(2)
            currency = col4.selectbox("결제 통화", ["KRW", "USD", "JPY", "EUR"])
            amount = col5.number_input("결제 금액", min_value=0.0, step=1000.0)
            
            involved = st.multiselect("혜택을 받은 참여자 (N빵 대상)", participants, default=participants)
            
            submitted = st.form_submit_button("내역 등록")
            
            if submitted and amount > 0 and involved:
                # 원화 환산
                krw_amount = amount * exchange_rates.get(currency, 1.0)
                st.session_state.expenses.append({
                    "항목": expense_name,
                    "결제자": payer,
                    "카테고리": category,
                    "통화": currency,
                    "원래 금액": amount,
                    "원화 환산액": krw_amount,
                    "참여자": ", ".join(involved),
                    "분담 인원수": len(involved)
                })
                st.success("지출 내역이 성공적으로 등록되었습니다.")
        
    st.markdown("---")
    st.subheader("등록된 지출 내역")
    if st.session_state.expenses:
        df_expenses = pd.DataFrame(st.session_state.expenses)
        st.dataframe(df_expenses, use_container_width=True)
    else:
        st.info("아직 등록된 지출 내역이 없습니다.")


# Tab 2: 실시간 분석 대시보드
with tab2:
    if not st.session_state.expenses:
        st.warning("분석할 데이터가 없습니다. Tab 1에서 지출 내역을 등록해주세요.")
    else:
        df_expenses = pd.DataFrame(st.session_state.expenses)
        total_krw = df_expenses["원화 환산액"].sum()
        
        st.subheader("핵심 요약 지표 (KPI)")
        kpi1, kpi2 = st.columns(2)
        kpi1.metric("총 지출 금액 (원화 환산)", f"{total_krw:,.0f} 원")
        kpi2.metric("1인당 평균 지출액", f"{total_krw/len(participants) if participants else 0:,.0f} 원")
        
        st.markdown("---")
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader("카테고리별 지출 비중")
            fig_pie = px.pie(df_expenses, values='원화 환산액', names='카테고리', hole=0.3)
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_chart2:
            st.subheader("결제자별 지출 누적 (원화)")
            fig_bar = px.bar(df_expenses.groupby('결제자')['원화 환산액'].sum().reset_index(), 
                             x='결제자', y='원화 환산액', text_auto='.2s')
            st.plotly_chart(fig_bar, use_container_width=True)


# Tab 3: 최종 최적화 정산 리포트
with tab3:
    if not st.session_state.expenses:
        st.warning("정산할 데이터가 없습니다.")
    else:
        st.subheader("정산 최적화 알고리즘 결과")
        st.write("알고리즘을 통해 계산된 최소 송금 횟수 안내입니다.")
        
        df_expenses = pd.DataFrame(st.session_state.expenses)
        
        # 1. 개인별 순 채무액(Net Balance) 계산
        balances = {p: 0.0 for p in participants}
        
        for idx, row in df_expenses.iterrows():
            payer = row['결제자']
            krw_amount = row['원화 환산액']
            involved_list = [p.strip() for p in row['참여자'].split(',')]
            
            # 결제자는 돈을 받아야 하므로 잔액 플러스
            balances[payer] += krw_amount
            
            # 혜택을 본 사람들은 돈을 내야 하므로 잔액 마이너스
            split_amount = krw_amount / len(involved_list)
            for person in involved_list:
                if person in balances:
                    balances[person] -= split_amount
                    
        # 2. 알고리즘 실행
        final_transactions = optimize_transactions(balances)
        
        # 3. 결과 출력
        st.markdown("### 💸 최종 송금 지시서")
        if not final_transactions:
            st.success("모든 정산이 완벽하게 맞습니다! 추가로 송금할 내역이 없습니다.")
        else:
            for t in final_transactions:
                st.info(f"**{t['보내는 사람']}** ➡️ **{t['받는 사람']}**에게 **{t['금액(원)']:,.0f}원** 송금")
                
            # CSV 내보내기 기능
            result_df = pd.DataFrame(final_transactions)
            csv = result_df.to_csv(index=False).encode('utf-8-sig')
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.download_button(
                label="📥 정산 결과 CSV 다운로드",
                data=csv,
                file_name=f"{project_name}_정산결과.csv",
                mime="text/csv",
            )