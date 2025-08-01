import streamlit as st
import pandas as pd
import requests
import time
import folium
from streamlit_folium import st_folium
from dotenv import load_dotenv
import os
import re
import streamlit.components.v1 as components  # ✅ 카카오 지도 UI 삽입용

load_dotenv()
api_key = os.getenv("Google_key")

def preprocess_restaurant_data(df):
    # 이름 전처리
    df['이름'] = df['이름'].astype(str).str.strip()
    df = df[~df['이름'].isin(['-', '없음', '', None])]
    df = df.drop_duplicates(subset='이름')

    # 평점 전처리
    df['평점'] = pd.to_numeric(df['평점'], errors='coerce')
    df = df.dropna(subset=['평점'])

    # 주소 전처리
    df['주소'] = df['주소'].astype(str).str.strip()
    df['주소'] = df['주소'].str.replace(r'^KR, ?', '', regex=True)
    df['주소'] = df['주소'].str.replace(r'^South Korea,?\s*', '', regex=True)
    df['주소'] = df['주소'].str.rstrip('/')

    # 영어 주소 제거
    df = df[~df['주소'].apply(lambda x: bool(re.fullmatch(r'[A-Za-z0-9 ,.-]+', x)))]

    df = df[df['주소'].str.strip() != '']
    df = df.dropna(subset=['주소'])

    # 정렬
    df = df.sort_values(by='평점', ascending=False)

    return df.reset_index(drop=True)

def get_lat_lng(address, api_key):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {'address': address, 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    if res['status'] == 'OK':
        location = res['results'][0]['geometry']['location']
        return location['lat'], location['lng']
    return None, None

# 3km로 잡긴 했는데 조금 근처에 잡고 싶어서 2km로 했습니다.
def find_nearby_restaurants(lat, lng, api_key, radius=2000):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        'location': f'{lat},{lng}',
        'radius': radius,
        'type': 'restaurant',
        'language': 'ko',
        'key': api_key
    }
    res = requests.get(url, params=params).json()
    time.sleep(1)
    results = res.get('results', [])[:15]
    restaurants = []
    for r in results:
        restaurants.append({
            '이름': r.get('name'),
            '주소': r.get('vicinity'),
            '평점': r.get('rating', '없음'),
            '위도': r['geometry']['location']['lat'],
            '경도': r['geometry']['location']['lng']
        })
    return restaurants

def search_places(query, api_key):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {'query': f"{query} 관광지", 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    return res.get('results', [])

def main():
    st.set_page_config(page_title="관광지 주변 맛집 추천", layout="wide")
    st.title("📍 관광지 주변 맛집 추천 시스템")

    if not api_key:
        st.error("❗ .env 파일에 'Google_key'가 설정되지 않았습니다.")
        return

    query = st.text_input("가고 싶은 지역을 입력하세요", "제주")

    # session_state 초기화
    if "places" not in st.session_state:
        st.session_state.places = None
    if "selected_place" not in st.session_state:
        st.session_state.selected_place = None

    if st.button("관광지 검색"):
        st.session_state.places = search_places(query, api_key)
        st.session_state.selected_place = None  # 관광지 새로 검색하면 선택 초기화

    if st.session_state.places:
        place_names = [p['name'] for p in st.session_state.places]
        selected = st.selectbox("관광지를 선택하세요", place_names)

        if st.session_state.selected_place != selected:
            st.session_state.selected_place = selected

        selected_place = next(p for p in st.session_state.places if p['name'] == st.session_state.selected_place)
        address = selected_place.get('formatted_address')
        rating = selected_place.get('rating', '없음')

        st.markdown(f"### 🏞 관광지: {st.session_state.selected_place}")
        st.write(f"📍 주소: {address}")
        st.write(f"⭐ 평점: {rating}")

        lat, lng = get_lat_lng(address, api_key)
        if lat is None:
            st.error("위치 정보를 불러오지 못했습니다.")
            return

        st.subheader("🍽 주변 3km 맛집 Top 10")

        restaurants = find_nearby_restaurants(lat, lng, api_key)
        df = pd.DataFrame(restaurants)
        df = preprocess_restaurant_data(df)

        st.dataframe(df[['이름', '주소', '평점']].head(10))  # Top 10만 출력

        # ✅ 카카오 지도 UI 삽입
        st.subheader("🗺 지도에서 보기 (카카오맵)")
        kakao_key = os.getenv("KAKAO_KEY")

        # DataFrame → JS 배열로 변환
        places_js = ""
        for _, row in df.iterrows():
            places_js += f'{{name: "{row["이름"]}", address: "{row["주소"]}"}},'

        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <script type="text/javascript" src="//dapi.kakao.com/v2/maps/sdk.js?appkey={kakao_key}&libraries=services"></script>
        </head>
        <body>
        <div id="map" style="width:100%;height:500px;"></div>
        <script>
        var mapContainer = document.getElementById('map');
        var mapOption = {{
            center: new kakao.maps.LatLng({lat}, {lng}),
            level: 4
        }};
        var map = new kakao.maps.Map(mapContainer, mapOption);
        var geocoder = new kakao.maps.services.Geocoder();

        var places = [{places_js}];

        places.forEach(function(p) {{
            geocoder.addressSearch(p.address, function(result, status) {{
                if (status === kakao.maps.services.Status.OK) {{
                    var coords = new kakao.maps.LatLng(result[0].y, result[0].x);
                    var marker = new kakao.maps.Marker({{ map: map, position: coords }});
                    var infowindow = new kakao.maps.InfoWindow({{ content: "<div style='padding:5px;'>" + p.name + "</div>" }});
                    infowindow.open(map, marker);
                }}
            }});
        }});
        </script>
        </body>
        </html>
        """

        components.html(html_code, height=550)

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 맛집 목록 CSV 다운로드",
            data=csv,
            file_name=f"{selected}_맛집목록.csv",
            mime='text/csv'
        )

if __name__ == "__main__":
    main()