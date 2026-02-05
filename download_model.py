#!/usr/bin/env python3
"""
모델 다운로드 스크립트
HuggingFace에서 모델을 미리 다운로드합니다.
"""
import os
import sys
from pathlib import Path

def download_model():
    """HuggingFace에서 모델 다운로드"""
    model_name = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-20B-Instruct")
    cache_dir = os.getenv("HF_HOME", "/root/.cache/huggingface")

    print(f"🔍 모델 다운로드 확인: {model_name}")
    print(f"📁 캐시 디렉토리: {cache_dir}")

    try:
        from huggingface_hub import snapshot_download

        # 모델이 이미 다운로드되어 있는지 확인
        model_path = Path(cache_dir) / "hub" / f"models--{model_name.replace('/', '--')}"

        if model_path.exists():
            print(f"✅ 모델이 이미 다운로드되어 있습니다: {model_path}")
        else:
            print(f"⬇️  모델 다운로드 중: {model_name}")
            print("⏳ 첫 실행시 10-20분 소요될 수 있습니다...")

            # 모델 다운로드
            downloaded_path = snapshot_download(
                repo_id=model_name,
                cache_dir=cache_dir,
                resume_download=True,
                local_files_only=False,
            )

            print(f"✅ 모델 다운로드 완료: {downloaded_path}")

    except ImportError:
        print("⚠️  huggingface_hub가 설치되어 있지 않습니다. vLLM이 자동으로 다운로드합니다.")
    except Exception as e:
        print(f"⚠️  모델 다운로드 실패: {str(e)}")
        print("vLLM이 자동으로 다운로드를 시도합니다.")

if __name__ == "__main__":
    download_model()
