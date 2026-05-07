# 포트홀 발견 로그 분석 리포트 DAG

## 개요

버스 운행 중 수집된 포트홀 감지 로그를 매일 자동으로
분석하여 관리자 대시보드에 제공할 일일 리포트를 생성하는 Airflow DAG

- S3에 적재된 Parquet 로그를 분석해 모델 성능 및 속도 구간 별 불확실 예측 비율 산출
- RDS에서 당일 포트홀 클러스터 집계
- 결과를 summary.json 형태로 S3에 저장

## 아키텍쳐

- AWS EC2에 Airflow를 도커를 활용해 띄우고 S3, RDS와 연결하여 Task 수행
- 산출물은 S3에 저장되어 FastAPI를 통해 프론트엔드에서 조회


## DAG 흐름

t1 -> t2 -> t3 -> t4 -> t5


Task 1: 모델 성능 모니터링
  - run_id별 평균 inference_time_ms
  - cp_class 분포 (N/U_N/U_P/P 비율)

Task 2: 속도별 불확실 예측 비율 분석
  - speed_kmh 구간별 불확실(U_N+U_P) 비율

Task 3: HNM 후보 추출
  - U_N 전체 → 정상인데 모델이 헷갈린 케이스
  - U_P 전체 → 포트홀인데 확신 낮은 케이스

Task 4: 포트홀 클러스터 일일 집계 (RDS)
  - 오늘 신규 클러스터 수, 전체/미수리/수리 완료 수
  - 어제 대비 증감률

Task 5: 일일 요약 JSON 생성
  - Task 1~4 결과를 집계해 summary.json으로 S3 저장
  - 프론트엔드 관리자 대시보드에서 직접 소비하는 데이터
