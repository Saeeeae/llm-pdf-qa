import streamlit as st
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import io
import os
import requests
import json

# 백엔드 설정 (vllm 또는 ollama)
BACKEND = os.getenv("BACKEND", "vllm")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-20B-Instruct" if BACKEND == "vllm" else "qwen2.5:14b")

def extract_text_from_pdf(pdf_file):
    """PDF 파일에서 텍스트 추출"""
    pdf_reader = PdfReader(io.BytesIO(pdf_file.read()))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

def split_text_into_chunks(text, chunk_size=1000, chunk_overlap=200):
    """텍스트를 청크로 분할"""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    chunks = text_splitter.split_text(text)
    return chunks

def check_server_health():
    """서버 상태 확인"""
    try:
        if BACKEND == "vllm":
            base_url = os.getenv("VLLM_API_BASE", "http://localhost:8000/v1")
            url = base_url.replace("/v1", "/health")
        else:
            base_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
            url = f"{base_url}/api/tags"

        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except:
        return False

def generate_response_ollama(prompt, context_chunks, model=None):
    """Ollama를 통해 응답 생성 (스트리밍)"""
    if model is None:
        model = MODEL_NAME

    # 컨텍스트와 프롬프트를 결합
    context_text = "\n\n".join([f"[Document Part {i+1}]\n{chunk}" for i, chunk in enumerate(context_chunks)])

    system_message = "당신은 문서를 분석하고 질문에 답변하는 AI 어시스턴트입니다. 주어진 문서 내용을 바탕으로 정확하게 답변해주세요."
    user_message = f"문서 내용:\n\n{context_text}\n\n질문: {prompt}"

    full_prompt = f"{system_message}\n\n{user_message}"

    ollama_base_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

    payload = {
        "model": model,
        "prompt": full_prompt,
        "stream": True,
        "options": {
            "temperature": 0.7,
            "num_predict": 2000
        }
    }

    try:
        response = requests.post(
            f"{ollama_base_url}/api/generate",
            json=payload,
            stream=True,
            timeout=300
        )
        response.raise_for_status()
        return response
    except Exception as e:
        st.error(f"Ollama API 오류: {str(e)}")
        return None

def generate_response_vllm(prompt, context_chunks, model=None):
    """vLLM을 통해 응답 생성 (스트리밍) - HTTP 직접 사용"""
    if model is None:
        model = MODEL_NAME

    # 컨텍스트와 프롬프트를 결합
    context_text = "\n\n".join([f"[Document Part {i+1}]\n{chunk}" for i, chunk in enumerate(context_chunks)])

    system_message = "당신은 문서를 분석하고 질문에 답변하는 AI 어시스턴트입니다. 주어진 문서 내용을 바탕으로 정확하게 답변해주세요."
    user_message = f"문서 내용:\n\n{context_text}\n\n질문: {prompt}"

    vllm_base_url = os.getenv("VLLM_API_BASE", "http://localhost:8000/v1")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        "stream": True,
        "max_tokens": 2000,
        "temperature": 0.7
    }

    try:
        response = requests.post(
            f"{vllm_base_url}/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=300
        )
        response.raise_for_status()
        return response
    except Exception as e:
        st.error(f"vLLM API 오류: {str(e)}")
        return None

# Streamlit UI
st.set_page_config(page_title="PDF Q&A with LLM", page_icon="📄", layout="wide")

# 백엔드 표시
backend_emoji = "🚀" if BACKEND == "vllm" else "🍎"
backend_name = "vLLM (GPU)" if BACKEND == "vllm" else "Ollama (CPU)"

st.title(f"📄 PDF 질의응답 시스템 {backend_emoji}")
st.markdown(f"**{backend_name} + {MODEL_NAME}**")

# 서버 상태 확인
server_status = check_server_health()
if server_status:
    st.success(f"✅ {backend_name} 서버 연결됨")
else:
    st.error(f"❌ {backend_name} 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")

# 사이드바: PDF 업로드 및 설정
with st.sidebar:
    st.header("⚙️ 설정")

    # 시스템 정보
    with st.expander("🖥️ 시스템 정보"):
        st.write(f"**백엔드**: {backend_name}")
        st.write(f"**모델**: {MODEL_NAME}")
        st.write(f"**서버 상태**: {'🟢 온라인' if server_status else '🔴 오프라인'}")

    st.divider()

    uploaded_file = st.file_uploader("PDF 파일 업로드", type=["pdf"])

    st.divider()

    chunk_size = st.slider("청크 크기", min_value=500, max_value=2000, value=1000, step=100)
    chunk_overlap = st.slider("청크 오버랩", min_value=0, max_value=500, value=200, step=50)

    if uploaded_file:
        with st.spinner("PDF 처리 중..."):
            # PDF에서 텍스트 추출
            pdf_text = extract_text_from_pdf(uploaded_file)

            # 청크로 분할
            text_chunks = split_text_into_chunks(pdf_text, chunk_size, chunk_overlap)

            # 세션 스테이트에 저장
            st.session_state.pdf_text = pdf_text
            st.session_state.text_chunks = text_chunks

            st.success(f"✅ PDF 처리 완료!")
            st.info(f"총 {len(text_chunks)}개의 청크로 분할됨")

            # 텍스트 미리보기
            with st.expander("텍스트 미리보기"):
                st.text_area("추출된 텍스트 (처음 1000자)", pdf_text[:1000], height=200)

# 메인 영역: 질문 및 응답
if "text_chunks" in st.session_state:
    st.header("💬 질문하기")

    # 프롬프트 입력
    user_prompt = st.text_area(
        "질문을 입력하세요:",
        placeholder="예: 이 문서의 주요 내용을 요약해주세요.",
        height=100
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        submit_button = st.button("질문하기", type="primary", use_container_width=True, disabled=not server_status)
    with col2:
        if st.button("대화 초기화", use_container_width=True):
            if "chat_history" in st.session_state:
                st.session_state.chat_history = []
                st.rerun()

    # 채팅 히스토리 초기화
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # 질문 제출
    if submit_button and user_prompt:
        if not server_status:
            st.error("서버에 연결할 수 없습니다.")
        else:
            # 사용자 메시지 추가
            st.session_state.chat_history.append({"role": "user", "content": user_prompt})

            # 응답 생성
            with st.spinner("응답 생성 중..."):
                try:
                    response_placeholder = st.empty()
                    full_response = ""

                    if BACKEND == "vllm":
                        # vLLM 스트리밍 응답
                        stream = generate_response_vllm(user_prompt, st.session_state.text_chunks)
                        if stream:
                            for line in stream.iter_lines():
                                if line:
                                    line_str = line.decode('utf-8')
                                    if line_str.startswith("data: "):
                                        line_str = line_str[6:]  # "data: " 제거
                                    if line_str.strip() == "[DONE]":
                                        break
                                    try:
                                        json_response = json.loads(line_str)
                                        if "choices" in json_response and len(json_response["choices"]) > 0:
                                            delta = json_response["choices"][0].get("delta", {})
                                            content = delta.get("content", "")
                                            if content:
                                                full_response += content
                                                response_placeholder.markdown(f"**AI:** {full_response}▌")
                                    except json.JSONDecodeError:
                                        continue
                    else:
                        # Ollama 스트리밍 응답
                        stream = generate_response_ollama(user_prompt, st.session_state.text_chunks)
                        if stream:
                            for line in stream.iter_lines():
                                if line:
                                    try:
                                        json_response = json.loads(line)
                                        if "response" in json_response:
                                            full_response += json_response["response"]
                                            response_placeholder.markdown(f"**AI:** {full_response}▌")
                                        if json_response.get("done", False):
                                            break
                                    except json.JSONDecodeError:
                                        continue

                    response_placeholder.markdown(f"**AI:** {full_response}")

                    # AI 응답 저장
                    if full_response:
                        st.session_state.chat_history.append({"role": "assistant", "content": full_response})
                    else:
                        st.warning("응답이 비어있습니다. 다시 시도해주세요.")

                except Exception as e:
                    st.error(f"오류 발생: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
                    if BACKEND == "vllm":
                        st.info("vLLM 서버가 실행 중인지 확인해주세요. (http://localhost:8000)")
                    else:
                        st.info("Ollama 서버가 실행 중인지 확인해주세요. (http://localhost:11434)")

    # 채팅 히스토리 표시
    if st.session_state.chat_history:
        st.divider()
        st.header("💭 대화 히스토리")

        for message in st.session_state.chat_history:
            if message["role"] == "user":
                st.markdown(f"**👤 사용자:** {message['content']}")
            else:
                st.markdown(f"**🤖 AI:** {message['content']}")
            st.divider()

else:
    st.info("👈 왼쪽 사이드바에서 PDF 파일을 업로드해주세요.")

    # 사용 방법 안내
    st.header("📖 사용 방법")

    if BACKEND == "vllm":
        st.markdown("""
        ### Linux GPU 환경 (vLLM)

        1. **실행**: `docker-compose --profile linux up -d`
        2. **PDF 업로드**: 왼쪽 사이드바에서 PDF 파일 업로드
        3. **질문 입력**: 업로드된 PDF에 대해 질문 입력
        4. **응답 확인**: AI가 문서 내용을 바탕으로 답변 생성

        ### 필수 사항
        - vLLM 서버가 실행 중이어야 합니다
        - GPU: NVIDIA L40s 이상
        - VRAM: 40GB 이상 권장
        - CUDA: 12.1 이상
        """)
    else:
        st.markdown("""
        ### macOS M2 환경 (Ollama)

        1. **실행**: `docker-compose --profile mac up -d`
        2. **모델 준비**: 첫 실행시 자동으로 모델 다운로드
        3. **PDF 업로드**: 왼쪽 사이드바에서 PDF 파일 업로드
        4. **질문 입력**: 업로드된 PDF에 대해 질문 입력
        5. **응답 확인**: AI가 문서 내용을 바탕으로 답변 생성

        ### 필수 사항
        - Ollama 서버가 실행 중이어야 합니다
        - Apple Silicon (M1/M2/M3) Mac
        - RAM: 16GB 이상 권장
        """)

# 푸터
st.divider()
st.caption(f"Powered by {backend_name} | Model: {MODEL_NAME}")
