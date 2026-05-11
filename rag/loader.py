"""
전세계약 위험 진단 에이전트 - 통합 데이터 로더
역할: 전체 데이터 인제스천 파이프라인을 순서대로 실행하는 진입점

실행 순서:
  Step 1. PDF → PostgreSQL (rag_documents 테이블)
  Step 2. CSV → PostgreSQL (jeonse_transactions, sale_transactions, price_ratio)
  Step 3. rag_documents chunk_text 정제
  Step 4. PostgreSQL → pgvector (임베딩 적재)
  Step 5. PostgreSQL + Neo4j → 지식 그래프 구축

실행: python rag/loader.py [--step 1|2|3|4|5|all]
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def step1_pdf_pipeline():
    """PDF → PostgreSQL"""
    print("\n" + "="*60)
    print("  STEP 1: PDF 파이프라인 (docs/pdf → PostgreSQL)")
    print("="*60)
    from rag.scripts.pdf_pipeline import run
    run(pdf_dir="docs/pdf")


def step2_csv_pipeline():
    """CSV → PostgreSQL"""
    print("\n" + "="*60)
    print("  STEP 2: CSV 전처리 + DB 적재")
    print("="*60)
    from rag.scripts.preprocess_load import (
        preprocess_jeonse, preprocess_sale, calc_price_ratio, load_to_postgres
    )
    import pandas as pd

    JEONSE_PATH        = "data/2025_전세_종로구_통합_cleaned.csv"
    SALE_연립_PATH     = "data/fixed_연립다세대(매매)_실거래가_20260507195717.csv"
    SALE_오피스텔_PATH  = "data/fixed_오피스텔(매매)_실거래가_20260507195801.csv"

    jeonse_df   = preprocess_jeonse(JEONSE_PATH)
    sale_연립    = preprocess_sale(SALE_연립_PATH, '연립다세대')
    sale_오피스텔 = preprocess_sale(SALE_오피스텔_PATH, '오피스텔')
    ratio_df    = calc_price_ratio(jeonse_df, pd.concat([sale_연립, sale_오피스텔]))
    load_to_postgres(jeonse_df, sale_연립, sale_오피스텔, ratio_df)


def step3_clean_chunks():
    """rag_documents chunk_text 노이즈 정제"""
    print("\n" + "="*60)
    print("  STEP 3: chunk_text 정제 (HTML·마크다운·특수문자 제거)")
    print("="*60)
    from rag.ingestion.clean_chunks import run
    run(dry_run=False)


def step4_embed_pg():
    """PostgreSQL rag_documents → pgvector"""
    print("\n" + "="*60)
    print("  STEP 4: pgvector 임베딩 적재 (PostgreSQL → pgvector)")
    print("="*60)
    from rag.ingestion.embed_to_pg import run
    run()


def step5_build_graph():
    """PostgreSQL + Neo4j → 지식 그래프"""
    print("\n" + "="*60)
    print("  STEP 5: Neo4j 지식 그래프 구축")
    print("="*60)
    from rag.ingestion.build_graph import run
    run()


def main():
    parser = argparse.ArgumentParser(description="전세계약 위험 진단 - 데이터 로더")
    parser.add_argument(
        "--step",
        choices=["1", "2", "3", "4", "5", "all"],
        default="all",
        help="실행할 단계 (기본: all = 전체 실행)",
    )
    args = parser.parse_args()

    print("\n🚀 전세계약 위험 진단 에이전트 - 데이터 인제스천 파이프라인")
    print(f"   실행 모드: {args.step}\n")

    step_map = {
        "1": step1_pdf_pipeline,
        "2": step2_csv_pipeline,
        "3": step3_clean_chunks,
        "4": step4_embed_pg,
        "5": step5_build_graph,
    }

    if args.step == "all":
        step1_pdf_pipeline()
        step2_csv_pipeline()
        step3_clean_chunks()
        step4_embed_pg()
        step5_build_graph()
    else:
        step_map[args.step]()

    print("\n🎉 파이프라인 완료!")


if __name__ == "__main__":
    main()
