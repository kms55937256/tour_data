import streamlit as st
import pandas as pd
import requests
import time
import os
import re
import io
from PIL import Image
import streamlit.components.v1 as components
from dotenv import load_dotenv
from math import radians, sin, cos, sqrt, atan2

load_dotenv()
google_key = os.getenv("Google_key")
kakao_key = os.getenv("KAKAO_KEY")

# ✅ 좌표 거리 계산
def haversine(lat1, lon1, lat2, lon2):
    R = 6371e3
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))

# ✅ 구글 Place Details API → 전화번호 가져오기
def get_place_details(place_id, api_key):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number",
        "language": "ko",
        "key": api_key
    }
    res = requests.get(url, params=params).json()
    return res.get("result", {})

# ✅ Kakao place_id 가져오기
def get_kakao_place_id(name, lat, lng, kakao_key, address="", phone=None):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {kakao_key}"}

    queries = []
    if phone:
        queries.append(phone)

    korean = re.sub(r"[^가-힣]", "", name)
    region = ""
    if "시" in address:
        region = address.split("시")[0] + "시"
    elif "도" in address:
        region = address.split("도")[0] + "도"

    if korean:
        queries.append(f"{region} {korean}")
    else:
        queries.append(f"{region} {name}")

    best_doc, best_dist = None, float("inf")

    for q in queries:
        params = {"query": q, "x": lng, "y": lat, "radius": 300}
        res = requests.get(url, headers=headers, params=params).json()

        if not res.get("documents"):
            continue

        for d in res["documents"]:
            dist = haversine(lat, lng, float(d["y"]), float(d["x"]))
            if dist < best_dist:
                best_dist = dist
                best_doc = d

        if best_doc and best_dist < 100:
            break

    return best_doc["id"] if best_doc else None

# ✅ 맛집 데이터 전처리
def preprocess_restaurant_data(df):
    df['이름'] = df['이름'].astype(str).str.strip()
    df = df[~df['이름'].isin(['-', '없음', '', None])]
    df = df.drop_duplicates(subset='이름')
    df['평점'] = pd.to_numeric(df['평점'], errors='coerce')
    df = df.dropna(subset=['평점'])
    df['주소'] = df['주소'].astype(str).str.strip()
    df['주소'] = df['주소'].str.replace(r'^KR, ?', '', regex=True)
    df['주소'] = df['주소'].str.replace(r'^South Korea,?\s*', '', regex=True)
    df['주소'] = df['주소'].str.rstrip('/')
    df = df[~df['주소'].apply(lambda x: bool(re.fullmatch(r'[A-Za-z0-9 ,.-]+', x)))]
    df = df[df['주소'].str.strip() != '']
    df = df.dropna(subset=['주소'])
    df = df.sort_values(by='평점', ascending=False)
    return df.reset_index(drop=True)

# ✅ 구글 좌표 가져오기
def get_lat_lng(address, api_key):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {'address': address, 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    if res['status'] == 'OK':
        location = res['results'][0]['geometry']['location']
        return location['lat'], location['lng']
    return None, None

# ✅ 구글 주변 맛집 검색 (전화번호 포함)
def find_nearby_restaurants(lat, lng, api_key):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        'location': f'{lat},{lng}',
        'radius': 2000,
        'type': 'restaurant',
        'language': 'ko',
        'key': api_key
    }
    res = requests.get(url, params=params).json()
    time.sleep(1)

    restaurants = []
    for r in res.get("results", [])[:15]:
        name = r.get("name")
        address = r.get("vicinity")
        r_lat = r["geometry"]["location"]["lat"]
        r_lng = r["geometry"]["location"]["lng"]

        place_id_google = r.get("place_id")
        phone = None
        if place_id_google:
            details = get_place_details(place_id_google, api_key)
            phone = details.get("formatted_phone_number")

        place_id_kakao = get_kakao_place_id(name, r_lat, r_lng, kakao_key, address, phone)

        restaurants.append({
            "이름": name,
            "주소": address,
            "평점": r.get("rating", "없음"),
            "위도": r_lat,
            "경도": r_lng,
            "전화번호": phone if phone else "없음",
            "place_id": place_id_kakao
        })
    return restaurants

# ✅ 관광지 검색
def search_places(query, api_key):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {'query': f"{query} 관광지", 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    return res.get('results', [])

def get_place_photo_url(photo_reference, api_key, maxwidth=400):
    return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={maxwidth}&photoreference={photo_reference}&key={api_key}"

# ✅ 관광지 Top 5 표시
def display_top_attractions(places: list):
    rated_places = [p for p in places if isinstance(p.get('rating'), (int, float))]
    rated_places = sorted(rated_places, key=lambda p: p['rating'], reverse=True)
    top_five = rated_places[:5]
    if not top_five:
        return

    st.markdown("#### ⭐ 추천 관광지 Top 5")
    cols = st.columns(len(top_five))
    for idx, place in enumerate(top_five):
        with cols[idx]:
            st.markdown(f"**{place['name']}**")
            st.markdown(f"평점: {place['rating']}")
            photos = place.get('photos')
            if photos:
                ref = photos[0].get('photo_reference')
                if ref:
                    url = get_place_photo_url(ref, google_key)
                    try:
                        resp = requests.get(url)
                        img = Image.open(io.BytesIO(resp.content))
                        img = img.resize((300, 200))
                        st.image(img)
                    except:
                        st.image(url, width=300)

# ✅ 메인 실행
def main():
    st.set_page_config(page_title="관광지 주변 맛집 추천", layout="wide")
    st.title("📍 관광지 주변 맛집 추천 시스템")

    if not google_key:
        st.error("❗ .env 파일에 'Google_key'가 설정되지 않았습니다.")
        return

    query = st.text_input("가고 싶은 지역을 입력하세요", "제주")

    if st.button("관광지 검색"):
        st.session_state.places = search_places(query, google_key)
        st.session_state.selected_place = None

    if "places" not in st.session_state:
        st.session_state.places = None
    if "selected_place" not in st.session_state:
        st.session_state.selected_place = None

    if st.session_state.places:
        display_top_attractions(st.session_state.places)
        place_names = [p['name'] for p in st.session_state.places]
        selected = st.selectbox("관광지를 선택하세요", place_names, key="place_select")
        st.session_state.selected_place = selected

        selected_place = next(p for p in st.session_state.places if p['name'] == selected)
        address = selected_place.get('formatted_address')
        rating = selected_place.get('rating', '없음')

        st.markdown(f"### 🏞 관광지: {selected}")
        st.write(f"📍 주소: {address}")
        st.write(f"⭐ 평점: {rating}")

        lat, lng = get_lat_lng(address, google_key)
        if lat is None:
            st.error("위치 정보를 불러오지 못했습니다.")
            return

        st.subheader("🍽 주변 3km 맛집 Top 10")
        restaurants = find_nearby_restaurants(lat, lng, google_key)
        df = pd.DataFrame(restaurants)
        df = preprocess_restaurant_data(df)
        st.dataframe(df[['이름', '주소', '평점', '전화번호']].head(10))

        # ✅ Kakao 지도 출력 (전화번호 있으면 전화번호 검색, 없으면 주소+가게명 검색)
        st.subheader("🗺 지도에서 보기 (카카오맵)")
        places_js = ""
        for _, row in df.head(10).iterrows():
            if row["전화번호"] != "없음":
                search_key = row["전화번호"]
            else:
                search_key = f"{row['주소']} {row['이름']}"
            places_js += f'''
                {{
                    name: "{row["이름"]}",
                    address: "{row["주소"]}",
                    phone: "{row["전화번호"]}",
                    lat: {row["위도"]},
                    lng: {row["경도"]},
                    search_key: "{search_key}"
                }},
            '''

        html_code = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <script src="//dapi.kakao.com/v2/maps/sdk.js?appkey={kakao_key}"></script>
        </head>
        <body>
            <div id="map" style="width:100%; height:500px;"></div>
            <script>
                var map = new kakao.maps.Map(document.getElementById('map'), {{
                    center: new kakao.maps.LatLng({lat}, {lng}),
                    level: 4
                }});

                var places = [{places_js}];

                places.forEach(function(p) {{
                    var marker = new kakao.maps.Marker({{
                        map: map,
                        position: new kakao.maps.LatLng(p.lat, p.lng)
                    }});

                    var infowindow = new kakao.maps.InfoWindow({{
                        content: "<div style='padding:5px; font-size:13px;'>" +
                                 p.name + "<br>" + p.address + "</div>"
                    }});
                    infowindow.open(map, marker);

                    kakao.maps.event.addListener(marker, 'click', function() {{
                        let kakaoUrl = "https://map.kakao.com/?q=" + encodeURIComponent(p.search_key);
                        window.open(kakaoUrl, "_blank");
                    }});
                }});
            </script>
        </body>
        </html>
        """

        components.html(html_code, height=550)

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📅 맛집 목록 CSV 다운로드",
            data=csv,
            file_name=f"{selected}_맛집목록.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
