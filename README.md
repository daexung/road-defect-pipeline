# 도로안전 알리미 (Road Defect Detection Pipeline)

영등포구 버스 블랙박스 영상에서 포트홀을 실시간 감지하고, 데이터를 수집·분석·시각화하는 end-to-end 파이프라인입니다.

YOLOv8-CLS + Conformal Prediction을 적용해 불확실성 기반 4단계 분류를 구현하고,
감지 로그를 Kafka → S3/RDS → Airflow → FastAPI → React 프론트엔드까지 연결했습니다.

---

## 시스템 아키텍처

```
[버스 블랙박스 시뮬레이터]
  capture_realtime.py / log_gen_kafka.py
          │
          ▼ Kafka Topic: raw.logs
          │
    ┌─────┴──────┐
    ▼            ▼
consumer_s3   consumer_rds
  (S3 Parquet)  (PostgreSQL)
    └─────┬──────┘
          │
          ▼
     Airflow DAG
  (클러스터링 · HNM 추출 · 일일 리포트)
          │
          ▼
      FastAPI (백엔드)
          │
          ▼
    React 프론트엔드
  (지도 시각화 · 관리자 대시보드)
```

---

## Conformal Prediction 4-class 분류

| CP Class | 의미 | 처리 |
|----------|------|------|
|  (0) | 명확한 정상 | 무시 |
|  (1) | 애매한 정상 | HNM 후보 수집 |
|  (2) | 애매한 포트홀 | HNM 후보 수집 |
|  (3) | 명확한 포트홀 | 즉시 알림 대상 |

 /  데이터는 Airflow DAG를 통해 Hard Negative Mining(HNM) 후보로 추출되어
재학습 파이프라인으로 연결됩니다.

---

## 폴더 구조

```
road-defect-pipeline/
│
├── dashcam-simulator/      # 엣지 디바이스 시뮬레이터
│   ├── capture_realtime.py #   실시간 화면 캡처 → YOLOv8+CP 추론 → Kafka 전송
│   ├── log_gen_kafka.py    #   13개 노선 페이크 로그 생성 (멀티프로세싱)
│   ├── models/             #   Fine-tuned YOLOv8 체크포인트 + CP quantile
│   └── get_bus_route/      #   Naver 지도 크롤링으로 수집한 GPS 경로 데이터
│
├── kafka_consumer/         # Kafka 컨슈머 (팀원 담당)
│   ├── consumer_s3/        #   S3 Parquet 적재
│   ├── consumer_rds/       #   RDS PostgreSQL 적재
│   └── docker-compose.yaml
│
├── airflow/                # Airflow DAG
│   └── dags/
│       ├── dag_daily_report.py         # 일일 리포트 생성 (S3 분석 · HNM 추출 · 요약 JSON)
│       └── cluster_potholes_12min_dag.py  # 12분마다 포트홀 클러스터링
│
└── frontend/               # React 웹 프론트엔드 (팀원 담당)
    └── src/
        ├── App.js          #   Leaflet 지도 · 포트홀 마커 · 관리자 대시보드
        └── admin.css
```

---

## 본인 기여 (주대성)

| 파트 | 내용 |
|------|------|
| **dashcam-simulator** | 전담 — YOLOv8+CP 실시간 추론, 13개 노선 페이크 로그 생성기, Naver 지도 크롤링 기반 GPS 데이터 수집 |
| **airflow** | 전담 — 일일 리포트 DAG, 12분 클러스터링 DAG 설계 및 구현 |
| **kafka_consumer** | 팀원 담당 |
| **frontend** | 팀원 담당 |
| **backend (FastAPI)** | 팀원 담당 (별도 레포) |

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| ML/AI | YOLOv8-CLS, PyTorch, Conformal Prediction |
| 데이터 파이프라인 | Kafka, Airflow, S3 (Parquet), RDS (PostgreSQL) |
| 인프라 | AWS EC2, Docker, docker-compose |
| 웹 | React, Leaflet, FastAPI |
| 데이터 수집 | Naver 지도 크롤링 (서울시 버스 API 대체) |

---

## 발표자료

- [프로젝트 발표자료 (PDF)](./docs/presentation.pdf)

---

## 실행 환경

각 컴포넌트별 실행 방법은 하위 폴더의 README를 참고하세요.

- [dashcam-simulator/README.md](./dashcam-simulator/README.md)
- [airflow/readme.MD](./airflow/readme.MD)
