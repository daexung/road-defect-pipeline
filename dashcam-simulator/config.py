"""
sample_maker용 설정 파일 (간소화 버전)
"""

import torch
import torch.nn as nn
from ultralytics import YOLO
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module='ultralytics')

# ============================================================================
# 모델 설정
# ============================================================================

MODEL_SIZE = "yolov8s-cls.pt"
NUM_CLASSES = 2

# 모델 구조 확인
temp_model = YOLO(MODEL_SIZE)
IN_FEATURES = temp_model.model.model[9].linear.in_features  # 1280
del temp_model
torch.cuda.empty_cache()


# ============================================================================
# 모델 생성 & Freeze 함수
# ============================================================================

def create_model(freeze_option, device):
    """모델 생성 및 Freeze 적용"""
    model = YOLO(MODEL_SIZE)
    
    # 모델을 디바이스로 이동
    model.model = model.model.to(device)
    
    # Head를 2클래스로 교체
    model.model.model[9].linear = nn.Linear(IN_FEATURES, NUM_CLASSES).to(device)
    
    # Freeze 매핑
    freeze_map = {
        "head_only": list(range(9)),
        "last_2_blocks": list(range(6)),
        "last_4_blocks": list(range(2)),
    }
    freeze_layers = freeze_map[freeze_option]
    
    # 전체를 trainable=True
    for p in model.model.parameters():
        p.requires_grad = True
    
    # Freeze 적용
    for idx in freeze_layers:
        for p in model.model.model[idx].parameters():
            p.requires_grad = False
    
    trainable_params = [p for p in model.model.parameters() if p.requires_grad]
    
    return model, trainable_params