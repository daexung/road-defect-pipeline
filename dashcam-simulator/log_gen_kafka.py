"""
페이크 로그 제너레이터 - 13개 노선 멀티프로세싱
────────────────────────────────────────────────
- 13개 노선을 동시에 병렬 실행
- 노선별 운행시간 / 왕복 여부 / turnpoint 개별 설정
- 왕복: forward / return, 편도: one_way
- 3fps로 로그 생성
- Kafka 토픽 'raw.logs' 로 전송
- Ctrl+C 시 전체 노선 정상 종료
"""

import csv
import json
import math
import random
import time
import uuid
from datetime import datetime, timedelta
from multiprocessing import Process
from pathlib import Path
from zoneinfo import ZoneInfo

from kafka import KafkaProducer
import os
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# 전역 설정
# ─────────────────────────────────────────────

ROUTE_DIR = Path(__file__).parent / "get_bus_route" / "cleaned_routes"

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
KAFKA_TOPIC             = os.getenv("KAFKA_TOPIC")

if not KAFKA_BOOTSTRAP_SERVERS:
    raise ValueError(".env 파일에 KAFKA_BOOTSTRAP_SERVERS가 없습니다.")
if not KAFKA_TOPIC:
    raise ValueError(".env 파일에 KAFKA_TOPIC이 없습니다.")

print(f"[INFO] Kafka 브로커: {KAFKA_BOOTSTRAP_SERVERS}")
print(f"[INFO] Kafka 토픽:   {KAFKA_TOPIC}")

RUN_ID = "middle"   # first | middle | last

FPS              = 3
FRAME_INTERVAL   = 1.0 / FPS
STOP_WAIT_SEC    = 15
STOP_NEAR_DIST_M = 10

SPEED_NORMAL_KMH    = (25, 35)
SPEED_NEAR_STOP_KMH = (10, 15)
GPS_NOISE_STD       = 0.000015

# ── 확률 설정 ────────────────────────────────
CLASS_PROB = {
    "N":   0.9500,
    "U_N": 0.9992,
    "U_P": 0.9997,
    "P":   1.0000,
}

PROB_RANGE = {
    "N":   (0.6027, 0.9900),
    "U_N": (0.5293, 0.6026),
    "U_P": (0.4709, 0.5292),
    "P":   (0.0100, 0.4708),
}

# ─────────────────────────────────────────────
# 노선별 설정
# ─────────────────────────────────────────────

ROUTES = {
    "ydp_01": {"turnpoint": "신대림한솔솔파크아파트.충심교회", "is_roundtrip": True,  "duration_sec": 50 * 60},
    "ydp_02": {"turnpoint": "한국환경수도연구원",               "is_roundtrip": True,  "duration_sec": 50 * 60},
    "ydp_03": {"turnpoint": None,                               "is_roundtrip": False, "duration_sec": 40 * 60},
    "ydp_04": {"turnpoint": None,                               "is_roundtrip": False, "duration_sec": 40 * 60},
    "ydp_05": {"turnpoint": None,                               "is_roundtrip": False, "duration_sec": 40 * 60},
    "ydp_06": {"turnpoint": None,                               "is_roundtrip": False, "duration_sec": 30 * 60},
    "ydp_07": {"turnpoint": None,                               "is_roundtrip": False, "duration_sec": 30 * 60},
    "ydp_08": {"turnpoint": None,                               "is_roundtrip": False, "duration_sec": 20 * 60},
    "ydp_09": {"turnpoint": None,                               "is_roundtrip": False, "duration_sec": 35 * 60},
    "ydp_10": {"turnpoint": "대방역",                           "is_roundtrip": True,  "duration_sec": 25 * 60},
    "ydp_11": {"turnpoint": "대방역",                           "is_roundtrip": True,  "duration_sec": 20 * 60},
    "ydp_12": {"turnpoint": None,                               "is_roundtrip": False, "duration_sec": 40 * 60},
    "ydp_13": {"turnpoint": None,                               "is_roundtrip": False, "duration_sec": 30 * 60},
}


# ─────────────────────────────────────────────
# 유틸 함수
# ─────────────────────────────────────────────

def haversine_m(lat1, lng1, lat2, lng2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def add_gps_noise(lat, lng, std=GPS_NOISE_STD):
    return (
        round(lat + random.gauss(0, std), 7),
        round(lng + random.gauss(0, std), 7),
    )


def generate_prob():
    r = random.random()

    if r < CLASS_PROB["N"]:
        cls, cp_class = "N", 0
    elif r < CLASS_PROB["U_N"]:
        cls, cp_class = "U_N", 1
    elif r < CLASS_PROB["U_P"]:
        cls, cp_class = "U_P", 2
    else:
        cls, cp_class = "P", 3

    lo, hi = PROB_RANGE[cls]
    if lo > hi:
        lo, hi = hi, lo

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
                "stop_name": row["stop_name"].strip(),
            })
    return points


def find_turnpoint_idx(points, stop_name):
    for i, p in enumerate(points):
        if p["is_stop"] and p["stop_name"] == stop_name:
            return i
    raise ValueError(f"turnpoint '{stop_name}' 를 찾지 못했습니다.")


# ─────────────────────────────────────────────
# 프레임 생성
# ─────────────────────────────────────────────

def build_frames(points, turnpoint_idx, total_sec, stop_wait_sec, is_roundtrip):
    n = len(points)
    stop_positions = [(p["lat"], p["lng"]) for p in points if p["is_stop"]]

    segments = []
    for i in range(n - 1):
        p0, p1   = points[i], points[i + 1]
        dist_m   = haversine_m(p0["lat"], p0["lng"], p1["lat"], p1["lng"])

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

    total_drive  = sum(s["drive_sec"] for s in segments)
    total_wait   = sum(s["wait_sec"]  for s in segments)
    drive_budget = total_sec - total_wait

    if drive_budget <= 0:
        raise ValueError("정차 시간이 총 운행시간을 초과합니다.")

    scale = drive_budget / total_drive

    waypoints = [{
        "lat":       points[0]["lat"],
        "lng":       points[0]["lng"],
        "t_arrive":  0.0,
        "t_depart":  0.0,
        "speed_kmh": 0.0,
    }]

    for s in segments:
        scaled_drive = s["drive_sec"] * scale
        t_arrive     = waypoints[-1]["t_depart"] + scaled_drive
        t_depart     = t_arrive + s["wait_sec"]
        waypoints.append({
            "lat":       s["end_lat"],
            "lng":       s["end_lng"],
            "t_arrive":  t_arrive,
            "t_depart":  t_depart,
            "speed_kmh": s["speed_kmh"],
        })

    total_frames = int(total_sec * FPS)
    frames       = []
    wp_idx       = 0

    direction         = "one_way" if not is_roundtrip else "forward"
    turnpoint_reached = False
    tp = points[turnpoint_idx] if is_roundtrip and turnpoint_idx is not None else None

    for f in range(total_frames):
        t = f / FPS

        while wp_idx < len(waypoints) - 2 and t > waypoints[wp_idx + 1]["t_depart"]:
            wp_idx += 1

        wp_cur = waypoints[wp_idx]
        wp_nxt = waypoints[wp_idx + 1]

        if t <= wp_nxt["t_arrive"]:
            drive_dur = wp_nxt["t_arrive"] - wp_cur["t_depart"]
            if drive_dur <= 0:
                lat, lng  = wp_nxt["lat"], wp_nxt["lng"]
                speed_kmh = 0.0
            else:
                ratio     = max(0.0, min(1.0, (t - wp_cur["t_depart"]) / drive_dur))
                lat       = wp_cur["lat"] + ratio * (wp_nxt["lat"] - wp_cur["lat"])
                lng       = wp_cur["lng"] + ratio * (wp_nxt["lng"] - wp_cur["lng"])
                speed_kmh = wp_nxt["speed_kmh"]
        else:
            lat, lng  = wp_nxt["lat"], wp_nxt["lng"]
            speed_kmh = 0.0

        if is_roundtrip and tp and not turnpoint_reached:
            if haversine_m(lat, lng, tp["lat"], tp["lng"]) < 20:
                direction         = "return"
                turnpoint_reached = True

        frames.append({
            "lat":       lat,
            "lng":       lng,
            "speed_kmh": round(speed_kmh, 1),
            "direction": direction,
        })

    return frames


# ─────────────────────────────────────────────
# 노선 단위 실행 함수
# ─────────────────────────────────────────────

def run_route(bus_id, config):
    csv_path     = str(Path(ROUTE_DIR) / f"{bus_id}_cleaned_path.csv")
    is_roundtrip = config["is_roundtrip"]
    total_sec    = config["duration_sec"]
    turnpoint    = config["turnpoint"]

    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8"),
        )
    except Exception as e:
        import traceback
        print(f"\n[{bus_id}] 오류 발생: {e}")
        traceback.print_exc()

    print(f"[{bus_id}] 시작")

    try:
        points = load_route(csv_path)

        turnpoint_idx = None
        if is_roundtrip and turnpoint:
            turnpoint_idx = find_turnpoint_idx(points, turnpoint)

        frames = build_frames(points, turnpoint_idx, total_sec, STOP_WAIT_SEC, is_roundtrip)

        now        = datetime.now(ZoneInfo("Asia/Seoul"))
        event_date = now.strftime("%Y%m%d")

        class_counts = {"N": 0, "U_N": 0, "U_P": 0, "P": 0}

        for frame_id, frame in enumerate(frames):
            lat, lng = add_gps_noise(frame["lat"], frame["lng"])

            prob_normal, prob_pothole, confidence, cp_class, cp_class_name = generate_prob()
            inference_time_ms = round(random.uniform(40, 120), 2)
            class_counts[cp_class_name] += 1

            frame_time = now + timedelta(seconds=frame_id / FPS)
            timestamp  = frame_time.strftime("%Y-%m-%dT%H:%M:%S") + "+09:00"
            event_id   = f"evt_{bus_id}_{RUN_ID}_{event_date}_{frame_id:06d}_{uuid.uuid4().hex[:8]}"

            log = {
                "event_id":          event_id,
                "frame_id":          frame_id,
                "timestamp":         timestamp,
                "source":            "log_gen",
                "run_id":            RUN_ID,
                "bus_id":            bus_id,
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

            producer.send(KAFKA_TOPIC, key=bus_id, value=log)
            
            time.sleep(FRAME_INTERVAL)

        producer.flush()

        total_frames = len(frames)
        print(f"\n[{bus_id}] 완료")
        print(
            f"[{bus_id}] 총 {total_frames:,}프레임 | "
            + " | ".join(f"{k}:{v}({v / total_frames * 100:.1f}%)" for k, v in class_counts.items())
        )

    except KeyboardInterrupt:
        print(f"\n[{bus_id}] 중단됨 (Ctrl+C)")

    except Exception as e:
        print(f"\n[{bus_id}] 오류 발생: {e}")

    finally:
        producer.close()


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[INFO] 13개 노선 동시 실행 시작")
    print(f"[INFO] Kafka 브로커: {KAFKA_BOOTSTRAP_SERVERS}\n")

    processes = []
    try:
        for bus_id, config in ROUTES.items():
            p = Process(target=run_route, args=(bus_id, config))
            processes.append(p)
            p.start()

        for p in processes:
            p.join()

    except KeyboardInterrupt:
        print("\n[INFO] Ctrl+C 감지 → 전체 노선 종료 중...")
        for p in processes:
            if p.is_alive():
                p.terminate()
        for p in processes:
            p.join()
        print("[INFO] 전체 노선 종료 완료")

    else:
        print("\n[INFO] 전체 노선 로그 생성 완료")