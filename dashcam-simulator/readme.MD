# dashcam-simulator

버스 블랙박스에서 포트홀을 실시간 감지하고 Kafka로 전송하는 엣지 파이프라인입니다.
YOLOv8-CLS + Conformal Prediction(CP)을 적용해 단순 이진 분류가 아닌 **4단계 불확실성 기반 분류**를 구현했습니다.

> 전체 파이프라인 중 **엣지 디바이스(블랙박스) 및 로그 생성** 파트를 담당합니다.

---

## 시스템 아키텍처

```
[버스 블랙박스]
    │
    ▼
capture_realtime.py          # 화면 캡처 → YOLOv8 추론 → CP 적용
    │  (또는 개발/테스트 시)
    ▼
log_gen_kafka.py             # 13개 노선 페이크 로그 생성 (멀티프로세싱)
    │
    ▼ Kafka Topic: raw.logs
    │
    ├─▶ consumer_s3   → S3 (Parquet)
    └─▶ consumer_rds  → RDS (PostgreSQL)
              │
              ▼
         Airflow DAG  → 클러스터링 · HNM 후보 추출 · 알림
```

---

## Conformal Prediction 4-class 분류

일반적인 이진 분류(정상/포트홀) 대신 CP를 적용해 모델의 불확실성을 명시합니다.

| CP Class | 의미 | 처리 |
|----------|------|------|
| `N` (0) | 명확한 정상 | 무시 |
| `U_N` (1) | 애매한 정상 | 모니터링 |
| `U_P` (2) | 애매한 포트홀 | HNM 후보 수집 |
| `P` (3) | 명확한 포트홀 | 즉시 알림 대상 |

`U_P`와 `U_N` 데이터는 Airflow를 통해 **Hard Negative Mining(HNM) 후보**로 추출되어 라벨링 파이프라인으로 연결됩니다.

---

## 파일 구조

```
dashcam-simulator/
│
├── capture_realtime.py          # 실시간 블랙박스 시뮬레이터
│                                #   특정 윈도우 캡처 → YOLOv8+CP 추론 → Kafka 로그 생성
├── log_gen_kafka.py             # 페이크 로그 생성기 (13개 노선, 멀티프로세싱)
│                                #   GPS 경로 기반 시뮬레이션 → Kafka 전송
│
├── config.py                    # YOLOv8 모델 구조 정의 및 Freeze 설정
├── fake_data_gen_for_capture.py # capture_realtime.py용 임시 GPS 데이터 생성기
├── make_map.py                  # 페이크 로그 분포 시각화 (folium, 검증용)
│
├── models/
│   ├── best.pt                  # Fine-tuned YOLOv8 체크포인트
│   └── cp_results_90.json       # Conformal Prediction quantile 값
│
├── yolov8s-cls.pt               # YOLOv8s-CLS 베이스 모델
│
├── get_bus_route/               # 영등포구 13개 버스 노선 GPS 데이터
│   ├── cleaned_routes/          #   Naver 지도 크롤링으로 수집 → 정제 CSV
│   └── *.json                   #   원본 크롤링 결과
│
├── .env.example                 # 환경변수 템플릿
└── proto/
    └── inference_proto.py       # 오프라인 배치 추론 프로토타입
                                 #   동영상 파일 → 3fps 추출 → CP 추론 → JSON 저장
```

---

## 설치 및 실행

### 환경 변수 설정

```bash
cp .env.example .env
# .env 파일에 Kafka 브로커 주소 입력
```

```
KAFKA_BOOTSTRAP_SERVERS=<EC2_IP>:9092
KAFKA_TOPIC=raw.logs
```

### 1. 실시간 블랙박스 시뮬레이터

```bash
# VLC 등으로 영상을 재생한 뒤 실행
python capture_realtime.py     --model ./models/best.pt     --cpjson ./models/cp_results_90.json
```

실행 후 캡처할 윈도우를 번호로 선택하면 3fps로 캡처하며 추론 결과를 Kafka로 전송합니다.

### 2. 페이크 로그 생성기 (13개 노선)

```bash
python log_gen_kafka.py
```

13개 노선이 멀티프로세싱으로 동시에 실행되며 `Ctrl+C`로 전체 종료됩니다.

---

## GPS 데이터 수집

서울시 버스 API가 정상 동작하지 않아 **Naver 지도 크롤링**으로 대체 수집했습니다.
영등포구 13개 노선(ydp_01 ~ ydp_13)의 정류소 좌표 및 경로 GPS 포인트를 수집하여
`get_bus_route/cleaned_routes/`에 정제 CSV로 저장했습니다.

---

## 주요 의존성

```bash
pip install -r requirements.txt
```

```
ultralytics    # YOLOv8
torch
kafka-python
python-dotenv
folium
pyautogui
pygetwindow
```
