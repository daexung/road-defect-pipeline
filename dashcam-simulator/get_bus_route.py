import requests
import pandas as pd
import os
import time
from dotenv import load_dotenv

load_dotenv()
SEOUL_API_KEY = os.getenv('SEOUL_API_KEY')

ROUTE_NAMES = {
    '01': '영등포01',
    '02': '영등포02',
    '03': '영등포03',
    '04': '영등포04',
    '05': '영등포05',
    '06': '영등포06',
    '07': '영등포07',
    '08': '영등포08',
    '09': '영등포09',
    '10': '영등포10',
    '11': '영등포11',
    '12': '영등포12',
    '13': '영등포13',
}

def get_route_id(route_name):
    url = "http://ws.bus.go.kr/api/rest/busRouteInfo/getBusRouteList"
    params = {
        'serviceKey': SEOUL_API_KEY,
        'strSrch': route_name,
        'resultType': 'json'
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"  ❌ 요청 실패: {e}")
        return None

    try:
        data = res.json()
    except Exception as e:
        print(f"  ❌ JSON 파싱 실패: {e}")
        print(f"  응답 원문: {res.text[:300]}")
        return None

    # 응답 구조 디버깅 (처음 한 번만 확인용)
    msg_body = data.get('msgBody')
    if msg_body is None:
        print(f"  ❌ msgBody 없음. 응답 구조: {list(data.keys())}")
        return None

    items = msg_body.get('itemList')
    if not items:
        print(f"  ❌ itemList 없음 또는 비어있음")
        return None

    # 정확히 일치하는 노선명 찾기
    for item in items:
        if item.get('busRouteNm') == route_name:
            return item['busRouteId']

    # 정확 매칭 실패 시 첫 번째 결과라도 출력
    print(f"  ⚠️ 정확 매칭 실패. 검색된 노선들: {[i.get('busRouteNm') for i in items]}")
    return None


def get_stations(route_id):
    url = "http://ws.bus.go.kr/api/rest/busRouteInfo/getStaionByRoute"
    params = {
        'serviceKey': SEOUL_API_KEY,
        'busRouteId': route_id,
        'resultType': 'json'
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"  ❌ 요청 실패: {e}")
        return []

    try:
        data = res.json()
    except Exception as e:
        print(f"  ❌ JSON 파싱 실패: {e}")
        return []

    msg_body = data.get('msgBody')
    if msg_body is None:
        print(f"  ❌ msgBody 없음")
        return []

    stations = msg_body.get('itemList')
    if not stations:
        print(f"  ❌ 정류장 데이터 없음")
        return []

    result = []
    for idx, st in enumerate(stations, 1):
        try:
            result.append({
                '순번': idx,
                '정류장명': st['stationNm'],
                '정류장ID': st['station'],
                '위도': float(st['gpsY']),
                '경도': float(st['gpsX']),
            })
        except (KeyError, ValueError) as e:
            print(f"  ⚠️ {idx}번 정류장 파싱 오류: {e} / 데이터: {st}")
            continue

    return result


os.makedirs('bus_stops', exist_ok=True)

for num, name in ROUTE_NAMES.items():
    print(f"\n{'='*50}")
    print(f"[{num}/13] {name} 처리 중...")

    route_id = get_route_id(name)
    if not route_id:
        print(f"  ❌ 노선 ID 못 찾음 → 스킵")
        continue

    print(f"  ✓ 노선 ID: {route_id}")

    stations = get_stations(route_id)
    if not stations:
        print(f"  ❌ 정류장 없음 → 스킵")
        continue

    df = pd.DataFrame(stations)
    filename = f'bus_stops/yeongdeungpo{num}_stops.csv'
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"  ✓ 저장: {filename} ({len(stations)}개 정류장)")

    time.sleep(0.5)

print("\n\n전체 완료!")