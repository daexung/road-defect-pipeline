"""
실시간 블랙박스 시뮬레이터 (특정 윈도우 캡처 버전)
─────────────────────────────────────

특정 윈도우만 캡처 → SD 저장 + 실시간 추론 + 로그 생성

실행 방법:
    1. 영상을 윈도우 플레이어로 재생 (VLC, PotPlayer 등)
    2. python capture_realtime.py --model ./best.pt --cpjson ./cp_results_90.json
    3. 캡처할 윈도우 선택
    4. Ctrl+C로 종료

특징:
  - 특정 윈도우만 캡처 (전체화면 불필요)
  - 터미널과 영상창 동시에 볼 수 있음
  - 나머지는 동일
"""

# 모듈 불러오기 

import cv2
import json
import torch
import argparse
import time
import uuid
import numpy as np
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image
import pyautogui
import pygetwindow as gw
from torchvision import transforms

from config import create_model
from fake_data_gen_for_capture import FakeDataGenerator


# 전역 설정

FPS_TARGET = 3                  # 3fps로 캡처
FRAME_INTERVAL = 1.0 / FPS_TARGET  # 0.333초
BONNET_CROP_RATIO = 0.2        # 사용할 샘플에는 본넷이 없지만, 실제 반영으로 하부 20% 크롭
IMGSZ = 224                     # 모델 입력 크기
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"

# CP 클래스 매핑
CP_CLASS_MAP = {
    0: "N",
    1: "U_N",
    2: "U_P",
    3: "P"
}

# 버스 정보
BUS_ID = "ydp_01"
RUN_ID = "first" # 첫차 중간 막차 fisrt,middle,last
# 윈도우 선택 함수

def select_window():
    print("윈도우 선택")

    
    # 모든 윈도우 목록 가져오기
    windows = gw.getAllTitles()
    
    # 빈 제목 제외
    windows = [w for w in windows if w.strip()]
    
    if not windows:
        raise RuntimeError("❌ 열린 윈도우를 찾을 수 없습니다.")
    
    print("\n사용 가능한 윈도우:")
    for idx, title in enumerate(windows, 1):
        print(f"  {idx}. {title}")
    
    while True:
        try:
            choice = input(f"\n캡처할 윈도우 번호 입력 (1-{len(windows)}): ")
            choice_idx = int(choice) - 1
            
            if 0 <= choice_idx < len(windows):
                selected_title = windows[choice_idx]
                window = gw.getWindowsWithTitle(selected_title)[0]
                
                print(f"\n 선택된 윈도우: {selected_title}")
                print(f"   위치: ({window.left}, {window.top})")
                print(f"   크기: {window.width} x {window.height}")
                
                return window
            else:
                print("❌ 잘못된 번호입니다. 다시 입력해주세요.")
        except (ValueError, IndexError):
            print("❌ 잘못된 입력입니다. 숫자를 입력해주세요.")

# 윈도우 캡처 함수

def capture_window(window):
    # 윈도우 영역 캡처
    screenshot = pyautogui.screenshot(region=(
        window.left,
        window.top,
        window.width,
        window.height
    ))
    
    frame = np.array(screenshot)
    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    
    return frame

# 캡쳐 영상 전처리(하단 본네트 가정, 이미지 사이즈 조정)

def preprocess_frame(frame, imgsz=224, bonnet_crop_ratio=0.2):
    """프레임 전처리"""
    height = frame.shape[0]
    crop_px = int(height * bonnet_crop_ratio)
    frame_cropped = frame[:height - crop_px, :]
    
    frame_rgb = cv2.cvtColor(frame_cropped, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(frame_rgb)
    
    transform = transforms.Compose([
        transforms.Resize((imgsz, imgsz)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225]
        )
    ])
    
    return transform(img).unsqueeze(0)


# CP 로직 적용 (동일)


def apply_cp_logic(prob_normal, prob_pothole, q0, q1):
    """CP 로직"""
    s0 = 1 - prob_normal
    s1 = 1 - prob_pothole
    
    pred_set = set()
    if s0 <= q0:
        pred_set.add(0)
    if s1 <= q1:
        pred_set.add(1)
    
    if len(pred_set) == 1:
        label = list(pred_set)[0]
        if label == 0:
            cp_class = 0
        else:
            cp_class = 3
    else:
        if prob_pothole >= prob_normal:
            cp_class = 2
        else:
            cp_class = 1
    
    return cp_class, CP_CLASS_MAP[cp_class]


# 실시간 모델 결과 + fake 
# 로그 출력기


def run_realtime_capture(model, q0, q1, output_dir, window):
    """
    실시간 윈도우 캡처 + 추론 + 로그 생성
    
    Args:
        model: YOLOv8 모델
        q0: CP quantile (Normal)
        q1: CP quantile (Pothole)
        output_dir: 결과 저장 폴더
        window: 캡처할 윈도우 객체
    """
    
    # 저장 경로 설정
    frames_dir = Path(output_dir) / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    
    log_path = Path(output_dir) / "results.json"
    
    # Fake 데이터 생성기
    generator = FakeDataGenerator(bus_id=BUS_ID)
    
    frame_count = 0
    start_time = time.time()
    print("로그 발생 시작")

    
    try:
        while True:
            loop_start = time.time()
            try:
                frame = capture_window(window)
            except Exception as e:
                print(f"\n  윈도우 캡처 실패 (창이 닫혔을 수 있음): {e}")
                break
            
            # 로컬에 프레임 이미지 저장(실제 블랙박스 SD카드에 저장 로직 구현)
           
            elapsed_time = time.time() - start_time
            frame_filename = f"frame_{frame_count:06d}_{elapsed_time:.3f}s.jpg"
            frame_path = frames_dir / frame_filename
            cv2.imwrite(str(frame_path), frame)
            
            
            # Fake 데이터 생성
            gps_data = generator.get_next_data()
            
            # YOLOv8 + CP 추론
            inference_start = time.time()
            
            img_tensor = preprocess_frame(
                frame,
                imgsz=IMGSZ,
                bonnet_crop_ratio=BONNET_CROP_RATIO
            ).to(DEVICE)
            
            with torch.no_grad():
                logits = model.model(img_tensor)
                logits = logits[0] if isinstance(logits, tuple) else logits
                prob = torch.softmax(logits, dim=1).cpu().numpy()[0]
            
            prob_normal = float(prob[0])
            prob_pothole = float(prob[1])
            confidence = float(max(prob_normal, prob_pothole))
            
            cp_class, cp_class_name = apply_cp_logic(
                prob_normal, prob_pothole, q0, q1
            )
            
            inference_time_ms = (time.time() - inference_start) * 1000
            
            # 로그 생성
            timestamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%dT%H:%M:%S") + "+09:00"

            event_date = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")

            event_id = f"evt_{BUS_ID}_{RUN_ID}_{event_date}_{frame_count:06d}_{uuid.uuid4().hex[:8]}"

            log = {
                "event_id": event_id,
                "frame_id": frame_count,
                "timestamp": timestamp,
                "source": "mss_capture",
                
                "run_id" : RUN_ID,
                "bus_id": gps_data["bus_id"],
                "direction": gps_data["direction"],
            
                "prob_normal": round(prob_normal, 4),
                "prob_pothole": round(prob_pothole, 4),
                "confidence": round(confidence, 4),
                "cp_class": cp_class,
                "cp_class_name": cp_class_name,
                "inference_time_ms": round(inference_time_ms, 2),
                
                "gps_lat": gps_data["gps_lat"],     
                "gps_lng": gps_data["gps_lng"],      
                "speed_kmh": gps_data["speed_kmh"]
            }
            
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log, ensure_ascii=False) + "\n")

            console_log = log.copy()
            console_log["timestamp"] = timestamp

            # | 구분자로 전체 필드 출력
            log_str = " | ".join([f'"{k}": {json.dumps(v)}' for k, v in console_log.items()])
            print(log_str)
            # --------------------------------------------------------
            # 8. 3fps 유지
            # --------------------------------------------------------
            loop_elapsed = time.time() - loop_start
            sleep_time = max(0, FRAME_INTERVAL - loop_elapsed)
            frame_count += 1
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        print("로그 생성 종료")

# 메인

def main():
    parser = argparse.ArgumentParser(
        description="실시간 블랙박스 시뮬레이터 (윈도우 캡처 버전)"
    )
    parser.add_argument("--model", type=str, default="./models/best.pt",
                       help="모델 파일 경로 (기본값: ./models/best.pt)")
    parser.add_argument("--cpjson", type=str, default="./models/cp_results_90.json",
                       help="CP JSON 파일 경로 (기본값: ./models/cp_results_90.json)")
    parser.add_argument("--output", type=str, default="./inference_proto_results",
                       help="결과 저장 폴더 (기본값: ./inference_proto_results)")
    
    args = parser.parse_args()
    
    # 경로 확인
    model_path = Path(args.model)
    cp_json_path = Path(args.cpjson)
    output_dir = Path(args.output)
    
    if not model_path.exists():
        raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {model_path}")
    if not cp_json_path.exists():
        raise FileNotFoundError(f"CP JSON 파일을 찾을 수 없습니다: {cp_json_path}")
    
    try:
       
        # CP JSON 로드
        with open(cp_json_path, "r") as f:
            cp_data = json.load(f)
        
        quantiles = cp_data["cp_results"]["quantiles"]
        q0 = float(quantiles["0"])
        q1 = float(quantiles["1"])
        
  
        
        # 모델 로드
        model, _ = create_model("last_4_blocks", DEVICE)
        
        ckpt = torch.load(model_path, map_location=DEVICE)
        if "model_state_dict" in ckpt:
            model.model.load_state_dict(ckpt["model_state_dict"])
        else:
            model.model.load_state_dict(ckpt)
        
        model.eval()
      
        
        # 윈도우 선택 
        window = select_window()
        
        # pyautogui 설정
        pyautogui.FAILSAFE = False
        
        # 실시간 캡처 시작
        run_realtime_capture(model, q0, q1, output_dir, window)
        
    except Exception as e:
        print(f"\n 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())