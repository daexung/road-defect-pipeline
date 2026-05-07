"""
Fake 데이터 생성기 (2분 영상용 간단 버전)

도림새마을금고 → 도림사거리 (일직선 구간)
- Frame 0~359: 360개 프레임 (2분 @ 3fps)
- direction: "forward" 고정 (한 방향으로만 전진)
- GPS: 일직선 이동 (선형 보간)
- 속도: 15 km/h 고정

나중에 Google Maps API 버전으로 업그레이드 예정
"""
# ============================================================
# 사용 예시
# ============================================================
# 
# from fake_data_generator import FakeDataGenerator
# 
# generator = FakeDataGenerator(bus_id="ydp_01")
# 
# for i in range(360):
#     data = generator.get_next_data()
#     print(data)

class FakeDataGenerator:    
    def __init__(self, bus_id="ydp_01"):
        """
        초기화
        
        Args:
            bus_id: 버스 노선 ID (기본값: "ydp_01")
        """
        self.bus_id = bus_id
        self.frame_count = 0
        
        # 일직선 구간 (도림사거리 근처)
        # 시작점과 끝점만 설정
        self.start_lat = 37.5103  # 도림사거리 남쪽
        self.start_lng = 126.8987
        
        self.end_lat = 37.5145    # 도림사거리 북쪽 (약 500m)
        self.end_lng = 126.9012
        
        # 총 프레임 수 (2분 @ 3fps = 360프레임)
        self.total_frames = 540
        
        # direction 고정 (forward만)
        self.direction = "forward"
        
        # 속도 고정 (15 km/h)
        self.speed = 15.0
    
    def get_next_data(self):
        """
        다음 프레임의 Fake 데이터 생성
        
        Returns:
            dict: {
                "bus_id": str,
                "direction": str,
                "gps_lat": float,
                "gps_lng": float,
                "speed_kmh": float
            }
        """
        frame_id = self.frame_count
        
        # 진행도 계산 (0.0 ~ 0.997...)
        # 360프레임 동안 시작점 → 끝점 (한 방향으로만 전진)
        progress = frame_id / 540.0
        
        # GPS 선형 보간 (시작점 → 끝점)
        lat = self.start_lat + (self.end_lat - self.start_lat) * progress
        lng = self.start_lng + (self.end_lng - self.start_lng) * progress
        
        # 결과 데이터
        data = {
            "bus_id": self.bus_id,
            "direction": self.direction,  # forward 고정
            "gps_lat": round(lat, 7),      # 소수점 7자리
            "gps_lng": round(lng, 7),
            "speed_kmh": self.speed        # 15 km/h 고정
        }
        
        self.frame_count += 1
        
        return data
    
    def reset(self):
        """프레임 카운터 리셋"""
        self.frame_count = 0


