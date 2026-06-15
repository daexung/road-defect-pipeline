"""
Pothole Detection Prototype Pipeline
─────────────────────────────────────

비디오 → 3fps 프레임 추출 → 본네트 크롭 → CP Inference → JSON 저장

사용법:
    python inference_proto.py \
        --video ./sample_video.mp4 \
        --model ./best.pt \
        --cpjson ./cp_results_90.json \
        --output ./results

특징:
  - 3fps로 자동 추출 (프레임 스킵)
  - 하부 20% 크롭 (본네트 제거)
  - Conformal Prediction 적용
  - 결과를 JSON으로 저장
"""

import os
import cv2
import json
import torch
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime
from PIL import Image
from torchvision import transforms

from config import create_model, NUM_CLASSES


# ============================================================
# 전역 설정 (프로토타입)
# ============================================================

FPS_TARGET = 3                  # 3fps로 추출
BONNET_CROP_RATIO = 0.2        # 하부 20% 크롭
IMGSZ = 224                     # 모델 입력 크기
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"

# CP 클래스 매핑
CP_CLASS_MAP = {
    0: "명확한 정상",
    1: "애매한 정상",
    2: "애매한 포트홀",
    3: "명확한 포트홀"
}


# ============================================================
# 비디오 정보 추출
# ============================================================

def get_video_info(video_path):
    """비디오 메타데이터 추출"""
    cap = cv2.VideoCapture(str(video_path))
    
    if not cap.isOpened():
        raise RuntimeError(f"❌ 비디오를 열 수 없습니다: {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    cap.release()
    
    return {
        "fps": fps,
        "total_frames": total_frames,
        "width": width,
        "height": height,
        "duration_sec": total_frames / fps if fps > 0 else 0
    }


# ============================================================
# 프레임 추출 (3fps 기반)
# ============================================================

def extract_frames_at_fps(video_path, target_fps=3):
    """
    비디오에서 target_fps로 프레임 추출
    
    Returns:
        list of dict: [
            {
                'frame_id': int,
                'frame_index': int (원본 인덱스),
                'timestamp_sec': float,
                'frame': numpy array (BGR)
            },
            ...
        ]
    """
    cap = cv2.VideoCapture(str(video_path))
    
    if not cap.isOpened():
        raise RuntimeError(f"❌ 비디오를 열 수 없습니다: {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # 몇 프레임마다 추출할지 계산
    frame_interval = max(1, int(fps / target_fps))
    
    print(f"\n{'='*80}")
    print(f"🎬 비디오 정보")
    print(f"{'='*80}")
    print(f"파일: {Path(video_path).name}")
    print(f"원본 FPS: {fps:.2f}")
    print(f"총 프레임: {total_frames}")
    print(f"재생 시간: {total_frames/fps:.2f}초")
    print(f"추출 FPS: {target_fps}")
    print(f"프레임 간격: {frame_interval}")
    print(f"추출 예상 프레임: {total_frames // frame_interval}")
    print(f"{'='*80}\n")
    
    frames = []
    frame_id = 0
    frame_index = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # frame_interval마다 추출
        if frame_index % frame_interval == 0:
            timestamp_sec = frame_index / fps
            frames.append({
                'frame_id': frame_id,
                'frame_index': frame_index,
                'timestamp_sec': timestamp_sec,
                'frame': frame.copy()
            })
            frame_id += 1
        
        frame_index += 1
    
    cap.release()
    
    print(f"✅ {len(frames)}개 프레임 추출 완료\n")
    
    return frames


# ============================================================
# 전처리 (본네트 크롭 포함)
# ============================================================

def preprocess_frame(frame, imgsz=224, bonnet_crop_ratio=0.2):
    """
    프레임 전처리
    
    Args:
        frame: numpy array (BGR)
        imgsz: 출력 크기
        bonnet_crop_ratio: 본네트 크롭 비율
    
    Returns:
        torch tensor (1, 3, 224, 224)
    """
    # 본네트 제거 (하단)
    height = frame.shape[0]
    crop_px = int(height * bonnet_crop_ratio)
    frame_cropped = frame[:height - crop_px, :]
    
    # BGR → RGB
    frame_rgb = cv2.cvtColor(frame_cropped, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(frame_rgb)
    
    # 전처리
    transform = transforms.Compose([
        transforms.Resize((imgsz, imgsz)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225]
        )
    ])
    
    return transform(img).unsqueeze(0)


# ============================================================
# CP (Conformal Prediction) 적용
# ============================================================

def apply_cp_logic(prob_normal, prob_pothole, q0, q1):
    """
    Conformal Prediction 로직
    
    Args:
        prob_normal: class 0 확률
        prob_pothole: class 1 확률
        q0: class 0 quantile
        q1: class 1 quantile
    
    Returns:
        tuple: (cp_class, cp_class_name)
    """
    s0 = 1 - prob_normal
    s1 = 1 - prob_pothole
    
    # Prediction set 계산
    pred_set = set()
    if s0 <= q0:
        pred_set.add(0)
    if s1 <= q1:
        pred_set.add(1)
    
    # CP 클래스 결정
    if len(pred_set) == 1:
        # 확실한 예측
        label = list(pred_set)[0]
        if label == 0:
            cp_class = 0  # 명확한 정상
        else:
            cp_class = 3  # 명확한 포트홀
    else:
        # 애매한 예측 (pred_set = {0, 1})
        if prob_pothole >= prob_normal:
            cp_class = 2  # 애매한 포트홀
        else:
            cp_class = 1  # 애매한 정상
    
    return cp_class, CP_CLASS_MAP[cp_class]


# ============================================================
# Inference 실행
# ============================================================

def run_inference(frames, model_path, cp_json_path, output_dir):
    """
    모든 프레임에 대해 inference 실행
    
    Args:
        frames: 추출된 프레임 리스트
        model_path: 모델 경로
        cp_json_path: CP JSON 경로
        output_dir: 결과 저장 폴더
    
    Returns:
        list: 예측 결과 리스트
    """
    
    print(f"{'='*80}")
    print(f"🔍 Inference 시작")
    print(f"{'='*80}\n")
    
    # CP JSON 로드
    with open(cp_json_path, "r") as f:
        cp_data = json.load(f)
    
    quantiles = cp_data["cp_results"]["quantiles"]
    q0 = float(quantiles["0"])
    q1 = float(quantiles["1"])
    
    print(f"✅ CP Quantiles")
    print(f"   q0 (Normal):  {q0:.4f}")
    print(f"   q1 (Pothole): {q1:.4f}\n")
    
    # 모델 로드
    model, _ = create_model("last_4_blocks", DEVICE)
    
    ckpt = torch.load(model_path, map_location=DEVICE)
    if "model_state_dict" in ckpt:
        model.model.load_state_dict(ckpt["model_state_dict"])
    else:
        model.model.load_state_dict(ckpt)
    
    model.eval()
    print(f"✅ 모델 로드 완료 (장치: {DEVICE})\n")
    
    # 프레임 저장 폴더
    frames_dir = Path(output_dir) / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    
    predictions = []
    total = len(frames)
    
    print(f"🔍 {total}개 프레임 분석 중...\n")
    
    for idx, frame_data in enumerate(frames, 1):
        frame_id = frame_data['frame_id']
        timestamp_sec = frame_data['timestamp_sec']
        frame = frame_data['frame']
        
        # 프레임 저장
        frame_filename = f"frame_{frame_id:06d}_{timestamp_sec:.3f}s.jpg"
        frame_path = frames_dir / frame_filename
        cv2.imwrite(str(frame_path), frame)
        
        # 전처리
        img_tensor = preprocess_frame(
            frame,
            imgsz=IMGSZ,
            bonnet_crop_ratio=BONNET_CROP_RATIO
        ).to(DEVICE)
        
        # Inference
        with torch.no_grad():
            logits = model.model(img_tensor)
            logits = logits[0] if isinstance(logits, tuple) else logits
            prob = torch.softmax(logits, dim=1).cpu().numpy()[0]
        
        prob_normal = float(prob[0])
        prob_pothole = float(prob[1])
        confidence = float(max(prob_normal, prob_pothole))
        
        # CP 적용
        cp_class, cp_class_name = apply_cp_logic(
            prob_normal, prob_pothole, q0, q1
        )
        
        # 결과 기록
        prediction = {
            "frame_id": frame_id,
            "timestamp_sec": timestamp_sec,
            "frame_path": str(frame_path.relative_to(output_dir)),
            "prob_normal": round(prob_normal, 4),
            "prob_pothole": round(prob_pothole, 4),
            "confidence": round(confidence, 4),
            "cp_class": cp_class,
            "cp_class_name": cp_class_name
        }
        predictions.append(prediction)
        
        if idx % max(1, total // 10) == 0 or idx == total:
            print(f"   {idx}/{total} 완료 ({idx/total*100:.1f}%)...")
    
    print(f"\n✅ Inference 완료!\n")
    
    return predictions


# ============================================================
# 통계 계산
# ============================================================

def compute_statistics(predictions):
    """예측 결과 통계 계산"""
    
    cp_classes = [p["cp_class"] for p in predictions]
    
    stats = {
        "total_processed": len(predictions),
        "pothole_count": sum(1 for c in cp_classes if c in [2, 3]),
        "pothole_ratio": sum(1 for c in cp_classes if c in [2, 3]) / len(predictions) if predictions else 0,
        "normal_count": sum(1 for c in cp_classes if c in [0, 1]),
        "uncertain_count": sum(1 for c in cp_classes if c in [1, 2]),
        "certain_count": sum(1 for c in cp_classes if c in [0, 3]),
        "cp_class_distribution": {
            "명확한 정상": sum(1 for c in cp_classes if c == 0),
            "애매한 정상": sum(1 for c in cp_classes if c == 1),
            "애매한 포트홀": sum(1 for c in cp_classes if c == 2),
            "명확한 포트홀": sum(1 for c in cp_classes if c == 3),
        }
    }
    
    return stats


# ============================================================
# 결과 저장
# ============================================================

def save_results(predictions, metadata, output_dir, video_path, model_path, cp_json_path):
    """결과를 JSON으로 저장"""
    
    print(f"{'='*80}")
    print(f"💾 결과 저장")
    print(f"{'='*80}\n")
    
    # 통계 계산
    statistics = compute_statistics(predictions)
    
    # 최종 결과 JSON
    results = {
        "metadata": {
            "video_path": str(video_path),
            "video_info": metadata,
            "model_path": str(model_path),
            "cp_json_path": str(cp_json_path),
            "fps_extracted": FPS_TARGET,
            "bonnet_crop_ratio": BONNET_CROP_RATIO,
            "imgsz": IMGSZ,
            "device": DEVICE,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "predictions": predictions,
        "statistics": statistics
    }
    
    # JSON 저장
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = output_dir / "results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"📊 결과 저장 완료")
    print(f"   경로: {json_path}\n")
    
    # 통계 출력
    print(f"{'='*80}")
    print(f"📈 통계")
    print(f"{'='*80}")
    print(f"총 처리 프레임: {statistics['total_processed']}")
    print(f"포트홀 감지: {statistics['pothole_count']}개 ({statistics['pothole_ratio']*100:.1f}%)")
    print(f"정상: {statistics['normal_count']}개")
    print(f"불확실: {statistics['uncertain_count']}개")
    print(f"확실: {statistics['certain_count']}개")
    print(f"\nCP 클래스 분포:")
    for class_name, count in statistics['cp_class_distribution'].items():
        pct = count / statistics['total_processed'] * 100 if statistics['total_processed'] > 0 else 0
        print(f"  {class_name}: {count}개 ({pct:.1f}%)")
    print(f"{'='*80}\n")
    
    return json_path


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pothole Detection Prototype (3fps + Bonnet Crop + CP)"
    )
    parser.add_argument("--video", type=str, required=True,
                       help="입력 비디오 파일 경로")
    parser.add_argument("--model", type=str, default="./best.pt",
                       help="모델 파일 경로 (기본값: ./best.pt)")
    parser.add_argument("--cpjson", type=str, default="./cp_results_90.json",
                       help="CP JSON 파일 경로 (기본값: ./cp_results_90.json)")
    parser.add_argument("--output", type=str, default="./inference_proto_results",
                       help="결과 저장 폴더 (기본값: ./inference_proto_results)")
    
    args = parser.parse_args()
    
    # 경로 확인
    video_path = Path(args.video)
    model_path = Path(args.model)
    cp_json_path = Path(args.cpjson)
    output_dir = Path(args.output)
    
    if not video_path.exists():
        raise FileNotFoundError(f"❌ 비디오 파일을 찾을 수 없습니다: {video_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"❌ 모델 파일을 찾을 수 없습니다: {model_path}")
    if not cp_json_path.exists():
        raise FileNotFoundError(f"❌ CP JSON 파일을 찾을 수 없습니다: {cp_json_path}")
    
    try:
        # Step 1: 비디오 정보 추출
        video_info = get_video_info(video_path)
        
        # Step 2: 3fps로 프레임 추출
        frames = extract_frames_at_fps(video_path, target_fps=FPS_TARGET)
        
        # Step 3: Inference 실행
        predictions = run_inference(frames, model_path, cp_json_path, output_dir)
        
        # Step 4: 결과 저장
        json_path = save_results(
            predictions, video_info, output_dir,
            video_path, model_path, cp_json_path
        )
        
        print(f"{'='*80}")
        print(f"✅ 완료!")
        print(f"{'='*80}")
        print(f"📁 프레임: {output_dir}/frames")
        print(f"📊 결과 JSON: {json_path}")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())