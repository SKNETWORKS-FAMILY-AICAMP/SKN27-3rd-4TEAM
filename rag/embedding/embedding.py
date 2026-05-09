from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv 

load_dotenv()

# 사용할 HuggingFace 임베딩 모델 (Qwen의 4B 임베딩 모델)
model_name = "Qwen/Qwen3-Embedding-4B"

def similarity(a, b):
    """
    두 벡터 a, b의 코사인 유사도를 계산하여 반환하는 함수.

    코사인 유사도(cosine similarity):
    - 두 벡터의 방향이 얼마나 유사한지를 0~1 사이 값으로 계산
    - 1에 가까울수록 두 벡터가 더 비슷한 의미를 가진다고 해석할 수 있음
    - NLP 임베딩 벡터 비교에서 가장 널리 사용되는 방식

    cosine_similarity의 입력 형식:
    - 2D 배열을 입력으로 받기 때문에 [a], [b]처럼 리스트로 한 번 더 감싸야 함
    """

    # sklearn의 cosine_similarity는 2차원 배열을 입력받기 때문에
    # 각각의 벡터를 [a], [b] 형태로 감싸서 전달
    return cosine_similarity([a], [b])[0][0]


def test_embedding(embedding_model):
    # 임베딩을 테스트할 문장 리스트
    sentences = [
        '안녕하세요!',
        '어! 오랜만이에요',
        '이름이 어떻게 되세요?',
        '날씨가 추워요',
        'Hello LLM!'
    ]

    # 임베딩된 문장들과 유사도를 비교할 질의(query)
    query = '첫인사를 하고 이름을 물어봤나요?'

    # 문장 리스트에 대해 임베딩 벡터 생성
    embeddings = embedding_model.embed_documents(sentences)

    # 질의(query) 문장에 대한 임베딩 벡터 생성
    embedded_query = embedding_model.embed_query(query)

    # 각 문장 임베딩과 질의 임베딩 간 유사도 계산 및 출력
    for i, embedding in enumerate(embeddings):
        print(
            f"""
            [유사도 {similarity(embedding, embedded_query):.4f}] {query} \t <=====> \t {sentences[i]}
            """
        )










# HuggingFace Embedding 모델 초기화
embeddings_huggingface = HuggingFaceEmbeddings(
    model_name=model_name,          # 로드할 임베딩 모델 이름 (HF Hub 기준)
    
    cache_folder="./models/",       # 모델 다운로드 및 로컬 캐싱 경로
                                    # 동일 경로에 있으면 재다운로드하지 않음
    
    model_kwargs={
        "device": "cpu"             # 모델이 실행될 디바이스 설정
                                    # "cpu", "cuda", "mps" 등 지원
    },
    
    encode_kwargs={
        'normalize_embeddings': True    # 임베딩 벡터 L2 정규화 여부
                                        # True → 코사인 유사도 계산 시 더 안정적
    },
)

input_text = "The meaning of life is 42"
vector = embeddings_huggingface.embed_query(input_text)

print(f"변환된 벡터의 크기: {len(vector)}")

test_embedding(embeddings_huggingface)