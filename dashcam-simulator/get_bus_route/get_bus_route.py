import json
import csv
import os

# 1. 설정: 처리할 노선 번호 리스트 (01~13)
route_numbers = [f"{i:02d}" for i in range(1, 14)]  # ['01', '02', ..., '13']
input_prefix = 'ydp_'  # 파일명이 ydp_01.json 형식이라고 가정
output_folder = 'cleaned_routes'

# 결과물을 저장할 폴더 생성
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

print(f"🚀 총 {len(route_numbers)}개 노선 전처리를 시작합니다.")

for num in route_numbers:
    input_file = f"{input_prefix}{num}.json"
    output_file = os.path.join(output_folder, f"ydp_{num}_cleaned_path.csv")
    
    # 파일 존재 여부 확인
    if not os.path.exists(input_file):
        print(f"⚠️ {input_file} 파일을 찾을 수 없어 건너뜁니다.")
        continue

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 정류장 좌표 정보를 딕셔너리로 캐싱 (좌표: 이름)
        stop_map = {
            (stop['point']['x'], stop['point']['y']): stop['name']
            for stop in data.get('busStops', [])
        }

        path_points = data.get('points', [])
        
        with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
            fieldnames = ['x', 'y', 'is_stop', 'stop_name']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            last_coord = None
            write_count = 0
            
            for pt in path_points:
                current_coord = (pt['x'], pt['y'])
                
                # 연속 중복 제거
                if current_coord == last_coord:
                    continue
                
                stop_name = stop_map.get(current_coord, "")
                is_stop = 1 if stop_name else 0

                writer.writerow({
                    'x': pt['x'],
                    'y': pt['y'],
                    'is_stop': is_stop,
                    'stop_name': stop_name
                })
                
                last_coord = current_coord
                write_count += 1

        print(f"✅ 노선 {num} 완료: {write_count}개 좌표 저장됨 -> {output_file}")

    except Exception as e:
        print(f"❌ 노선 {num} 처리 중 오류 발생: {e}")

print("\n✨ 모든 노선의 전처리가 완료되었습니다!")