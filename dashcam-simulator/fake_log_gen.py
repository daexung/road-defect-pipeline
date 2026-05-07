"""
페이크 로그 제너레이터
────────────────────────────────────────────────
- 노선 CSV 경로 포인트 기반으로 GPS 시뮬레이션
- 속도를 먼저 정하고 → 시간 계산 → 60분 스케일 조정
- 정류소 정차 포인트 분리로 speed=0 정상 처리
- 60분 왕복 운행 1회 / 3fps로 로그 생성
"""



import csv
import json
import math
import random
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────
# 설정값 (하드코딩)
# ─────────────────────────────────────────────

BUS_ID  = "ydp_01"
RUN_ID  = "first"   # first | middle | last

ROUTE_CSV   = r"C:\Users\daeseong\Desktop\pothall-pjt\get_bus_route\log_pipeline\cleaned_routes\ydp_01_cleaned_path.csv"
OUTPUT_LOG  = r"C:\Users\daeseong\Desktop\pothall-pjt\log_pipeline\fake_log_gen_output.jsonl"

TOTAL_DURATION_SEC  = 60 * 60  # 60분 (테스트시 60으로 줄여서 사용)
FPS                 = 3
FRAME_INTERVAL      = 1.0 / FPS

STOP_WAIT_SEC       = 15        # 정류소 정차 시간(초)
STOP_NEAR_DIST_M    = 10        # 정류소 근처 판단 기준(m)

SPEED_NORMAL_KMH    = (25, 35)  # 일반 구간 속도 범위
SPEED_NEAR_STOP_KMH = (10, 15)  # 정류소 근처 속도 범위

GPS_NOISE_STD = 0.000015        # 가우시안 노이즈 표준편차 (약 1~2m)

TURNPOINT_STOP_NAME = "신대림한솔솔파크아파트.충심교회"  # 두 번째 등장 시 return 전환

CP_CLASS_MAP = {0: "N", 1: "U_N", 2: "U_P", 3: "P"}

# 목표 분포
CLASS_PROB = {
    "N":   0.9000,
    "U_N": 0.9460,
    "U_P": 0.9488,   # U_P 0.28% → 약 30개
    "P":   0.9493,   # P 0.05% → 약 5개
}


# ─────────────────────────────────────────────
# 유틸 함수
# ─────────────────────────────────────────────

def haversine_m(lat1, lng1, lat2, lng2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def add_gps_noise(lat, lng, std=GPS_NOISE_STD):
    return (
        round(lat + random.gauss(0, std), 7),
        round(lng + random.gauss(0, std), 7)
    )


def generate_prob():
    """클래스 먼저 결정 후 해당 구간에서 prob_normal 샘플링"""
    r = random.random()
    if r < CLASS_PROB["N"]:
        cls, cp_class = "N", 0
        lo, hi = 0.6027, 0.99
    elif r < CLASS_PROB["U_N"]:
        cls, cp_class = "U_N", 1
        lo, hi = 0.5293, 0.6026
    elif r < CLASS_PROB["U_P"]:
        cls, cp_class = "U_P", 2
        lo, hi = 0.4709, 0.5292
    elif r < CLASS_PROB["P"]:
        cls, cp_class = "P", 3
        lo, hi = 0.01, 0.4708
    else:
        cls, cp_class = "N", 0
        lo, hi = 0.6027, 0.99

    prob_normal  = round(random.uniform(lo, hi), 4)
    prob_pothole = round(1 - prob_normal, 4)
    confidence   = round(max(prob_normal, prob_pothole), 4)
    return prob_normal, prob_pothole, confidence, cp_class, cls


# ─────────────────────────────────────────────
# 경로 로드
# ─────────────────────────────────────────────

def load_route(csv_path):
    points = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            points.append({
                "lat":       float(row["y"]),
                "lng":       float(row["x"]),
                "is_stop":   row["is_stop"] == "1",
                "stop_name": row["stop_name"].strip()
            })
    return points


def find_turnpoint_idx(points, stop_name):
    """stop_name이 두 번째로 등장하는 인덱스 반환"""
    count = 0
    for i, p in enumerate(points):
        if p["is_stop"] and p["stop_name"] == stop_name:
            count += 1
            if count == 2:
                return i
    raise ValueError(f"turnpoint '{stop_name}' 를 두 번 찾지 못했습니다.")


# ─────────────────────────────────────────────
# 속도 기반 타임라인 구성 + 프레임 생성
# ─────────────────────────────────────────────

def build_frames(points, turnpoint_idx, total_sec, stop_wait_sec):
    """
    정류소마다 도착 포인트 / 정차 포인트를 분리해서
    speed=0 구간이 명시적으로 생성되도록 처리.

    내부적으로 확장된 waypoints 리스트를 사용:
      - 일반 포인트: (lat, lng, speed_kmh)
      - 정류소 도착: (lat, lng, 진입속도)
      - 정류소 정차: (lat, lng, 0.0)  ← 같은 좌표, 15초 머무름
    """
    n = len(points)
    stop_positions = [(p["lat"], p["lng"]) for p in points if p["is_stop"]]

    # ── Step 1. 구간별 속도 & 소요시간 계산 ──
    segments = []
    for i in range(n - 1):
        p0, p1 = points[i], points[i + 1]
        dist_m = haversine_m(p0["lat"], p0["lng"], p1["lat"], p1["lng"])

        near_stop = any(
            haversine_m(p1["lat"], p1["lng"], slat, slng) < STOP_NEAR_DIST_M
            for slat, slng in stop_positions
        )

        if dist_m < 0.1:
            speed_kmh = 10.0
        elif near_stop:
            speed_kmh = random.uniform(*SPEED_NEAR_STOP_KMH)
        else:
            speed_kmh = random.uniform(*SPEED_NORMAL_KMH)

        speed_ms  = speed_kmh / 3.6
        drive_sec = dist_m / speed_ms

        is_stop_end = p1["is_stop"] and 0 < i + 1 < n - 1
        wait_sec    = stop_wait_sec if is_stop_end else 0.0

        segments.append({
            "dist_m":    dist_m,
            "speed_kmh": round(speed_kmh, 1),
            "drive_sec": drive_sec,
            "wait_sec":  wait_sec,
            "end_lat":   p1["lat"],
            "end_lng":   p1["lng"],
        })

    # ── Step 2. 스케일 계산 (주행시간만 조정) ──
    total_drive  = sum(s["drive_sec"] for s in segments)
    total_wait   = sum(s["wait_sec"]  for s in segments)
    drive_budget = total_sec - total_wait

    if drive_budget <= 0:
        raise ValueError("정차 시간이 총 운행시간을 초과합니다.")

    scale = drive_budget / total_drive
    print(f"[INFO] 총 정차시간: {total_wait/60:.1f}분")
    print(f"[INFO] 총 주행시간(원본): {total_drive/60:.1f}분")
    print(f"[INFO] 스케일 팩터: {scale:.3f}")

    # ── Step 3. 확장 waypoints 생성 ──
    # 각 waypoint: {"lat", "lng", "t_arrive", "t_depart", "speed_kmh"}
    # t_arrive ~ t_depart 구간은 정차 (speed=0)
    # t_depart ~ 다음 t_arrive 구간은 주행

    waypoints = []
    t = 0.0

    # 출발점
    waypoints.append({
        "lat":      points[0]["lat"],
        "lng":      points[0]["lng"],
        "t_arrive": 0.0,
        "t_depart": 0.0,  # 출발점은 정차 없음
        "speed_kmh": 0.0,
    })

    for i, s in enumerate(segments):
        scaled_drive = s["drive_sec"] * scale
        t_arrive     = waypoints[-1]["t_depart"] + scaled_drive

        t_depart = t_arrive + s["wait_sec"]  # 정차 없으면 t_arrive == t_depart

        waypoints.append({
            "lat":       s["end_lat"],
            "lng":       s["end_lng"],
            "t_arrive":  t_arrive,
            "t_depart":  t_depart,
            "speed_kmh": s["speed_kmh"],
        })

    # ── Step 4. FPS 기반 프레임 보간 ──
    total_frames = int(total_sec * FPS)
    frames = []
    direction = "forward"
    turnpoint_reached = False
    wp_idx = 0  # 현재 구간 (waypoints[wp_idx] → waypoints[wp_idx+1])

    tp = points[turnpoint_idx]

    for f in range(total_frames):
        t = f / FPS

        # 현재 구간 전진
        while wp_idx < len(waypoints) - 2 and t > waypoints[wp_idx + 1]["t_depart"]:
            wp_idx += 1

        wp_cur = waypoints[wp_idx]
        wp_nxt = waypoints[wp_idx + 1]

        if t <= wp_nxt["t_arrive"]:
            # 주행 구간: wp_cur.t_depart ~ wp_nxt.t_arrive
            drive_dur = wp_nxt["t_arrive"] - wp_cur["t_depart"]
            if drive_dur <= 0:
                lat, lng  = wp_nxt["lat"], wp_nxt["lng"]
                speed_kmh = 0.0
            else:
                ratio     = (t - wp_cur["t_depart"]) / drive_dur
                ratio     = max(0.0, min(1.0, ratio))
                lat       = wp_cur["lat"] + ratio * (wp_nxt["lat"] - wp_cur["lat"])
                lng       = wp_cur["lng"] + ratio * (wp_nxt["lng"] - wp_cur["lng"])
                speed_kmh = wp_nxt["speed_kmh"]
        else:
            # 정차 구간: wp_nxt.t_arrive ~ wp_nxt.t_depart
            lat, lng  = wp_nxt["lat"], wp_nxt["lng"]
            speed_kmh = 0.0

        # direction 전환 체크
        if not turnpoint_reached:
            if haversine_m(lat, lng, tp["lat"], tp["lng"]) < 20:
                direction = "return"
                turnpoint_reached = True
                print(f"[INFO] frame {f}: turnpoint 도달 → direction=return")

        frames.append({
            "lat":       lat,
            "lng":       lng,
            "speed_kmh": round(speed_kmh, 1),
            "direction": direction,
        })

    return frames


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

def run():
    print(f"[INFO] 노선 CSV 로드: {ROUTE_CSV}")
    points = load_route(ROUTE_CSV)
    print(f"[INFO] 총 포인트 수: {len(points)}")

    turnpoint_idx = find_turnpoint_idx(points, TURNPOINT_STOP_NAME)
    print(f"[INFO] turnpoint 인덱스: {turnpoint_idx} ({TURNPOINT_STOP_NAME})")

    frames = build_frames(points, turnpoint_idx, TOTAL_DURATION_SEC, STOP_WAIT_SEC)
    print(f"[INFO] 총 프레임 수: {len(frames)}")

    now        = datetime.now(ZoneInfo("Asia/Seoul"))
    event_date = now.strftime("%Y%m%d")

    output_path = Path(OUTPUT_LOG)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] 로그 출력: {OUTPUT_LOG}")
    print("[INFO] 로그 생성 시작 (Ctrl+C로 종료)\n")

    class_counts = {"N": 0, "U_N": 0, "U_P": 0, "P": 0}

    with open(output_path, "w", encoding="utf-8") as f:
        for frame_id, frame in enumerate(frames):

            lat, lng = add_gps_noise(frame["lat"], frame["lng"])

            prob_normal, prob_pothole, confidence, cp_class, cp_class_name = generate_prob()
            inference_time_ms = round(random.uniform(40, 120), 2)

            class_counts[cp_class_name] += 1

            frame_time = now + timedelta(seconds=frame_id / FPS)
            timestamp  = frame_time.strftime("%Y-%m-%dT%H:%M:%S") + "+09:00"
            event_id   = f"evt_{BUS_ID}_{RUN_ID}_{event_date}_{frame_id:06d}_{uuid.uuid4().hex[:8]}"

            log = {
                "event_id":          event_id,
                "frame_id":          frame_id,
                "timestamp":         timestamp,
                "source":            "log_gen",
                "run_id":            RUN_ID,
                "bus_id":            BUS_ID,
                "direction":         frame["direction"],
                "prob_normal":       prob_normal,
                "prob_pothole":      prob_pothole,
                "confidence":        confidence,
                "cp_class":          cp_class,
                "cp_class_name":     cp_class_name,
                "inference_time_ms": inference_time_ms,
                "gps_lat":           lat,
                "gps_lng":           lng,
                "speed_kmh":         frame["speed_kmh"],
            }

            line = json.dumps(log, ensure_ascii=False)
            f.write(line + "\n")
            # print(line)
            # time.sleep(FRAME_INTERVAL)

    print("\n[INFO] 로그 생성 완료")
    print("[INFO] 클래스별 생성 결과:")
    for cls, cnt in class_counts.items():
        print(f"  {cls:4s}: {cnt:>6,}개  ({cnt/len(frames)*100:.2f}%)")


if __name__ == "__main__":
    run()