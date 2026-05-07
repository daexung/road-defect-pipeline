'''
블랙박스를 구현하기위해 핸드폰 카메라로 샘플 영상을 촬영하는 로직을 구현하려 했지만, 무료로 사용가능한 어플리케이션 중 화질이 좋은 어플을 찾지 못해,
모니터에 영상을 띄우고 일정 프레임마다 캡쳐하여 모델에 넣는 로직으로 구현함.
'''

{
  "event_id": "evt_20250430_001234",
  "frame_id": 1234,
  "timestamp": "2025-04-30T14:23:45.123456",
  "source": "mss_capture",
  
  "bus_id": "ydp_01",
  "direction": "forward",
  
  "prob_normal": 0.8766,
  "prob_pothole": 0.1234,
  "confidence": 0.8766,
  "cp_class": 0,
  "cp_class_name": "N",
  "inference_time_ms": 45.67,
  
  "gps_lat": 37.5136789,
  "gps_lng": 126.9021234,
  "speed_kmh": 35.2
}

# 블랙박스 로그 생성기
- capture_realtime.py

# 가짜 로그 생성기

- log_gen_13.py
