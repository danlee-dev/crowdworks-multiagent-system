"""
평가 결과 시각화
Visualize Evaluation Results
"""

import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from pathlib import Path
from typing import Dict, Any

# 한글 폰트 설정
matplotlib.rc('font', family='DejaVu Sans')
plt.rcParams['axes.unicode_minus'] = False


def create_visualizations(results: Dict[str, Any], output_dir: str = "/tmp"):
    """
    벤치마크 결과 시각화

    Args:
        results: 벤치마크 결과 딕셔너리
        output_dir: 출력 디렉토리
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_results = results.get('raw_results', [])
    if not raw_results:
        print("❌ 시각화할 데이터가 없습니다.")
        return

    df = pd.DataFrame(raw_results)

    # 1. 점수 분포 히스토그램
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(df['overall_score'], bins=10, edgecolor='black', alpha=0.7)
    ax.set_xlabel('Score', fontsize=12)
    ax.set_ylabel('Count', fontsize=12)
    ax.set_title('Score Distribution', fontsize=14, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)

    output_path = output_dir / 'score_distribution.png'
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ 점수 분포 저장: {output_path}")

    # 2. 팀별 평균 점수 비교
    team_scores = df.groupby('team_type')['overall_score'].mean().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(range(len(team_scores)), team_scores.values, color=['#FF6B6B', '#4ECDC4', '#45B7D1'])
    ax.set_xticks(range(len(team_scores)))
    ax.set_xticklabels(team_scores.index, fontsize=11)
    ax.set_ylabel('Average Score', fontsize=12)
    ax.set_title('Average Score by Team', fontsize=14, fontweight='bold')
    ax.set_ylim(0, 10)
    ax.grid(axis='y', alpha=0.3)

    # 값 표시
    for i, (bar, value) in enumerate(zip(bars, team_scores.values)):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                f'{value:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

    output_path = output_dir / 'team_comparison.png'
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ 팀별 비교 저장: {output_path}")

    # 3. 실행 시간 vs 점수 산점도
    fig, ax = plt.subplots(figsize=(10, 6))

    for team in df['team_type'].unique():
        team_df = df[df['team_type'] == team]
        ax.scatter(team_df['total_time'], team_df['overall_score'],
                  label=team, alpha=0.7, s=100)

    ax.set_xlabel('Execution Time (seconds)', fontsize=12)
    ax.set_ylabel('Score', fontsize=12)
    ax.set_title('Execution Time vs Score', fontsize=14, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)

    output_path = output_dir / 'time_vs_score.png'
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ 시간 vs 점수 저장: {output_path}")

    # 4. 등급 분포 파이 차트
    grade_counts = df['grade'].value_counts()

    fig, ax = plt.subplots(figsize=(8, 8))
    colors = {'A+': '#2ECC71', 'A': '#27AE60', 'B+': '#3498DB', 'B': '#2980B9',
              'C+': '#F39C12', 'C': '#E67E22', 'D': '#E74C3C', 'F': '#C0392B'}
    grade_colors = [colors.get(grade, '#95A5A6') for grade in grade_counts.index]

    wedges, texts, autotexts = ax.pie(grade_counts.values, labels=grade_counts.index,
                                        autopct='%1.1f%%', startangle=90,
                                        colors=grade_colors, textprops={'fontsize': 11})

    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')

    ax.set_title('Grade Distribution', fontsize=14, fontweight='bold')

    output_path = output_dir / 'grade_distribution.png'
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ 등급 분포 저장: {output_path}")

    # 5. 환각 현상 분석
    if 'hallucination_count' in df.columns:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # 환각 건수 분포
        ax1.hist(df['hallucination_count'], bins=10, edgecolor='black', alpha=0.7, color='#E74C3C')
        ax1.set_xlabel('Hallucination Count', fontsize=12)
        ax1.set_ylabel('Count', fontsize=12)
        ax1.set_title('Hallucination Distribution', fontsize=13, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3)

        # 팀별 평균 환각
        team_hall = df.groupby('team_type')['hallucination_count'].mean().sort_values(ascending=True)
        bars = ax2.barh(range(len(team_hall)), team_hall.values, color='#E74C3C', alpha=0.7)
        ax2.set_yticks(range(len(team_hall)))
        ax2.set_yticklabels(team_hall.index, fontsize=11)
        ax2.set_xlabel('Average Hallucination Count', fontsize=12)
        ax2.set_title('Hallucinations by Team', fontsize=13, fontweight='bold')
        ax2.grid(axis='x', alpha=0.3)

        # 값 표시
        for i, (bar, value) in enumerate(zip(bars, team_hall.values)):
            ax2.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height()/2,
                    f'{value:.1f}', ha='left', va='center', fontsize=10, fontweight='bold')

        output_path = output_dir / 'hallucination_analysis.png'
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"✅ 환각 분석 저장: {output_path}")

    # 6. 종합 대시보드
    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

    # 6.1 점수 분포
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.hist(df['overall_score'], bins=10, edgecolor='black', alpha=0.7, color='#3498DB')
    ax1.set_xlabel('Score', fontsize=10)
    ax1.set_ylabel('Count', fontsize=10)
    ax1.set_title('Score Distribution', fontsize=11, fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)

    # 6.2 팀별 점수
    ax2 = fig.add_subplot(gs[0, 1])
    team_scores = df.groupby('team_type')['overall_score'].mean()
    ax2.bar(range(len(team_scores)), team_scores.values, color=['#FF6B6B', '#4ECDC4', '#45B7D1'])
    ax2.set_xticks(range(len(team_scores)))
    ax2.set_xticklabels(team_scores.index, fontsize=9, rotation=15)
    ax2.set_ylabel('Avg Score', fontsize=10)
    ax2.set_title('Team Comparison', fontsize=11, fontweight='bold')
    ax2.grid(axis='y', alpha=0.3)

    # 6.3 등급 분포
    ax3 = fig.add_subplot(gs[0, 2])
    grade_counts = df['grade'].value_counts()
    grade_colors = [colors.get(grade, '#95A5A6') for grade in grade_counts.index]
    ax3.pie(grade_counts.values, labels=grade_counts.index, autopct='%1.0f%%',
            colors=grade_colors, textprops={'fontsize': 9})
    ax3.set_title('Grade Distribution', fontsize=11, fontweight='bold')

    # 6.4 시간 vs 점수
    ax4 = fig.add_subplot(gs[1, :2])
    for team in df['team_type'].unique():
        team_df = df[df['team_type'] == team]
        ax4.scatter(team_df['total_time'], team_df['overall_score'],
                   label=team, alpha=0.6, s=80)
    ax4.set_xlabel('Time (s)', fontsize=10)
    ax4.set_ylabel('Score', fontsize=10)
    ax4.set_title('Execution Time vs Score', fontsize=11, fontweight='bold')
    ax4.legend(fontsize=9)
    ax4.grid(alpha=0.3)

    # 6.5 출처 품질
    ax5 = fig.add_subplot(gs[1, 2])
    ax5.scatter(df['sources_count'], df['overall_score'], alpha=0.6, s=80, color='#9B59B6')
    ax5.set_xlabel('Sources Count', fontsize=10)
    ax5.set_ylabel('Score', fontsize=10)
    ax5.set_title('Sources vs Score', fontsize=11, fontweight='bold')
    ax5.grid(alpha=0.3)

    # 6.6 주요 통계
    ax6 = fig.add_subplot(gs[2, :])
    ax6.axis('off')

    stats_text = f"""
    EVALUATION SUMMARY

    Total Reports: {len(df)}
    Success Rate: {df['success'].sum() / len(df) * 100:.1f}%

    Average Score: {df['overall_score'].mean():.2f} / 10
    Average Time: {df['total_time'].mean():.1f} seconds
    Average Quality: {df['quality_score'].mean():.2f} / 10

    Best Score: {df['overall_score'].max():.2f} ({df.loc[df['overall_score'].idxmax(), 'query_text'][:50]}...)
    Worst Score: {df['overall_score'].min():.2f} ({df.loc[df['overall_score'].idxmin(), 'query_text'][:50]}...)
    """

    ax6.text(0.5, 0.5, stats_text, ha='center', va='center',
            fontsize=11, family='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))

    fig.suptitle('EVALUATION BENCHMARK DASHBOARD', fontsize=16, fontweight='bold', y=0.98)

    output_path = output_dir / 'dashboard.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ 종합 대시보드 저장: {output_path}")

    print(f"\n📊 모든 시각화 완료! 출력 디렉토리: {output_dir}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python visualize_results.py <benchmark_results.json> [output_dir]")
        sys.exit(1)

    json_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "/tmp"

    with open(json_path, 'r', encoding='utf-8') as f:
        results = json.load(f)

    create_visualizations(results, output_dir)
