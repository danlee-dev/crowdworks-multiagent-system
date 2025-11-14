"""
평가 결과 상세 저장 및 시각화
Detailed Evaluation Results Exporter with Charts and CSV

평가 결과를 시간별 폴더에 저장하고, 상세한 CSV와 시각화 차트를 생성합니다.
"""

import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import numpy as np

# 한글 폰트 설정
plt.rcParams['font.family'] = 'NanumGothic'
plt.rcParams['axes.unicode_minus'] = False

# 스타일 설정
sns.set_style("whitegrid")
sns.set_palette("husl")


class DetailedResultsExporter:
    """평가 결과를 상세하게 저장하고 시각화하는 클래스"""

    def __init__(self, output_dir: str = "evaluation_results"):
        """
        초기화

        Args:
            output_dir: 평가 결과 저장 디렉토리
        """
        self.base_dir = Path(output_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 현재 평가 세션 디렉토리 (시간 기준)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = self.base_dir / timestamp
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # 서브 디렉토리
        self.charts_dir = self.session_dir / "charts"
        self.csv_dir = self.session_dir / "csv"
        self.json_dir = self.session_dir / "json"

        for dir_path in [self.charts_dir, self.csv_dir, self.json_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        print(f"✅ 평가 결과 저장 위치: {self.session_dir}")

    def export_detailed_results(
        self,
        results: List[Dict[str, Any]],
        summary_stats: Optional[Dict[str, Any]] = None
    ):
        """
        평가 결과를 상세하게 저장 (CSV + JSON + Charts)

        Args:
            results: 평가 결과 리스트
            summary_stats: 요약 통계
        """
        print("\n=== 평가 결과 상세 저장 중... ===")

        # 1. CSV 저장 (상세)
        self._export_detailed_csv(results)

        # 2. JSON 저장 (전체 raw data)
        self._export_json(results, summary_stats)

        # 3. 차트 생성
        self._create_all_charts(results, summary_stats)

        # 4. 요약 보고서 생성
        self._create_summary_report(results, summary_stats)

        print(f"\n✅ 평가 결과 저장 완료: {self.session_dir}")
        print(f"   - CSV: {self.csv_dir}")
        print(f"   - 차트: {self.charts_dir}")
        print(f"   - JSON: {self.json_dir}")

    def _export_detailed_csv(self, results: List[Dict[str, Any]]):
        """상세한 CSV 파일 생성 - 모든 평가 지표와 근거 포함"""

        # 1. 전체 결과 CSV (모든 컬럼 포함)
        df_all = pd.DataFrame(results)
        csv_path = self.csv_dir / "01_all_results.csv"
        df_all.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"  ✓ 전체 결과: {csv_path}")

        # 2. 점수 상세 분석 CSV
        score_data = []
        for r in results:
            score_data.append({
                'query_id': r.get('query_id', ''),
                'query_text': r.get('query_text', '')[:50],
                'team_type': r.get('team_type', ''),
                'overall_score': r.get('overall_score', 0),
                'grade': r.get('grade', ''),
                'success_rate': r.get('success_rate', 0),
                'quality_score': r.get('quality_score', 0),
                'completeness_rate': r.get('completeness_rate', 0),
                'hallucination_count': r.get('hallucination_count', 0),
                'efficiency_score': r.get('efficiency_score', 0),
                'citation_accuracy': r.get('citation_accuracy', 1.0),
                'total_time': r.get('total_time', 0),
                'sources_count': r.get('sources_count', 0),
            })

        df_scores = pd.DataFrame(score_data)
        csv_path = self.csv_dir / "02_scores_detail.csv"
        df_scores.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"  ✓ 점수 상세: {csv_path}")

        # 3. AI Judge 평가 근거 CSV
        ai_judge_data = []
        for r in results:
            # hallucination_examples 처리 (dict 리스트 → 문자열)
            hallucination_examples = r.get('hallucination_examples', [])
            if hallucination_examples and isinstance(hallucination_examples[0], dict):
                # dict 리스트인 경우 → 문자열로 변환
                examples_str = '; '.join([
                    f"{ex.get('type', 'unknown')}: {ex.get('description', str(ex))}"
                    for ex in hallucination_examples
                ])
            elif hallucination_examples:
                # 문자열 리스트인 경우
                examples_str = '; '.join(hallucination_examples)
            else:
                examples_str = ''

            ai_judge_data.append({
                'query_id': r.get('query_id', ''),
                'query_text': r.get('query_text', '')[:50],
                'quality_score': r.get('quality_score', 0),
                'quality_reasoning': r.get('quality_reasoning', ''),
                'hallucination_count': r.get('hallucination_count', 0),
                'hallucination_reasoning': r.get('hallucination_reasoning', ''),
                'hallucination_examples': examples_str,
            })

        df_ai_judge = pd.DataFrame(ai_judge_data)
        csv_path = self.csv_dir / "03_ai_judge_reasoning.csv"
        df_ai_judge.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"  ✓ AI Judge 평가 근거: {csv_path}")

        # 4. 강점/약점/추천사항 CSV
        feedback_data = []
        for r in results:
            feedback_data.append({
                'query_id': r.get('query_id', ''),
                'query_text': r.get('query_text', '')[:50],
                'strengths': '; '.join(r.get('strengths', [])),
                'weaknesses': '; '.join(r.get('weaknesses', [])),
                'recommendations': '; '.join(r.get('recommendations', [])),
            })

        df_feedback = pd.DataFrame(feedback_data)
        csv_path = self.csv_dir / "04_feedback_detail.csv"
        df_feedback.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"  ✓ 피드백 상세: {csv_path}")

        # 5. 팀별 집계 CSV
        if results:
            df_team = df_scores.groupby('team_type').agg({
                'overall_score': ['mean', 'std', 'min', 'max'],
                'quality_score': ['mean', 'std'],
                'completeness_rate': 'mean',
                'hallucination_count': ['sum', 'mean'],
                'total_time': 'mean',
                'sources_count': 'mean'
            }).round(2)

            csv_path = self.csv_dir / "05_team_summary.csv"
            df_team.to_csv(csv_path, encoding='utf-8-sig')
            print(f"  ✓ 팀별 요약: {csv_path}")

        # 6. 등급 분포 CSV
        grade_dist = df_scores['grade'].value_counts().reset_index()
        grade_dist.columns = ['grade', 'count']
        csv_path = self.csv_dir / "06_grade_distribution.csv"
        grade_dist.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"  ✓ 등급 분포: {csv_path}")

    def _export_json(self, results: List[Dict[str, Any]], summary_stats: Optional[Dict[str, Any]]):
        """JSON 형식으로 전체 raw data 저장"""

        # 1. 전체 결과
        json_path = self.json_dir / "full_results.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  ✓ JSON 전체 결과: {json_path}")

        # 2. 요약 통계
        if summary_stats:
            json_path = self.json_dir / "summary_stats.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(summary_stats, f, ensure_ascii=False, indent=2)
            print(f"  ✓ JSON 요약 통계: {json_path}")

    def _create_all_charts(self, results: List[Dict[str, Any]], summary_stats: Optional[Dict[str, Any]]):
        """모든 시각화 차트 생성"""

        if not results:
            print("  ⚠ 결과가 없어 차트 생성을 건너뜁니다.")
            return

        df = pd.DataFrame(results)

        # 1. 점수 분포 히스토그램
        self._create_score_distribution(df)

        # 2. 등급 분포 파이 차트
        self._create_grade_distribution(df)

        # 3. 팀별 평균 점수 막대 그래프
        self._create_team_comparison(df)

        # 4. 실행 시간 vs 점수 산점도
        self._create_time_vs_score(df)

        # 5. 환각 분석 차트
        self._create_hallucination_analysis(df)

        # 6. 7개 KPI 레이더 차트
        self._create_kpi_radar(df)

        # 7. 출처 활용 분석
        self._create_source_analysis(df)

        # 8. 종합 대시보드
        self._create_dashboard(df, summary_stats)

    def _create_score_distribution(self, df: pd.DataFrame):
        """점수 분포 히스토그램"""
        fig, ax = plt.subplots(figsize=(12, 6))

        # 히스토그램
        ax.hist(df['overall_score'], bins=20, edgecolor='black', alpha=0.7, color='skyblue')
        ax.axvline(df['overall_score'].mean(), color='red', linestyle='--', linewidth=2, label=f'평균: {df["overall_score"].mean():.2f}')
        ax.axvline(df['overall_score'].median(), color='green', linestyle='--', linewidth=2, label=f'중앙값: {df["overall_score"].median():.2f}')

        ax.set_xlabel('종합 점수', fontsize=12)
        ax.set_ylabel('빈도', fontsize=12)
        ax.set_title('평가 점수 분포 (Score Distribution)', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(self.charts_dir / "01_score_distribution.png", dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  ✓ 차트: 점수 분포")

    def _create_grade_distribution(self, df: pd.DataFrame):
        """등급 분포 파이 차트"""
        fig, ax = plt.subplots(figsize=(10, 8))

        grade_counts = df['grade'].value_counts()
        colors = sns.color_palette("Set2", len(grade_counts))

        wedges, texts, autotexts = ax.pie(
            grade_counts.values,
            labels=grade_counts.index,
            autopct='%1.1f%%',
            startangle=90,
            colors=colors,
            textprops={'fontsize': 11}
        )

        # 퍼센트 텍스트 스타일
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')

        ax.set_title('등급 분포 (Grade Distribution)', fontsize=14, fontweight='bold', pad=20)

        plt.tight_layout()
        plt.savefig(self.charts_dir / "02_grade_distribution.png", dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  ✓ 차트: 등급 분포")

    def _create_team_comparison(self, df: pd.DataFrame):
        """팀별 평균 점수 막대 그래프"""
        fig, ax = plt.subplots(figsize=(12, 6))

        team_scores = df.groupby('team_type')['overall_score'].agg(['mean', 'std']).sort_values('mean', ascending=False)

        x = np.arange(len(team_scores))
        bars = ax.bar(x, team_scores['mean'], yerr=team_scores['std'], capsize=5, alpha=0.8, edgecolor='black')

        # 막대 색상 설정
        colors = sns.color_palette("viridis", len(team_scores))
        for bar, color in zip(bars, colors):
            bar.set_color(color)

        ax.set_xlabel('팀 타입', fontsize=12)
        ax.set_ylabel('평균 점수', fontsize=12)
        ax.set_title('팀별 평균 점수 비교 (Team Comparison)', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(team_scores.index, rotation=15, ha='right')
        ax.set_ylim(0, 10)
        ax.grid(True, alpha=0.3, axis='y')

        # 값 표시
        for i, (mean, std) in enumerate(zip(team_scores['mean'], team_scores['std'])):
            ax.text(i, mean + 0.3, f'{mean:.2f}', ha='center', fontweight='bold')

        plt.tight_layout()
        plt.savefig(self.charts_dir / "03_team_comparison.png", dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  ✓ 차트: 팀별 비교")

    def _create_time_vs_score(self, df: pd.DataFrame):
        """실행 시간 vs 점수 산점도"""
        fig, ax = plt.subplots(figsize=(12, 6))

        scatter = ax.scatter(
            df['total_time'],
            df['overall_score'],
            c=df['quality_score'],
            s=100,
            alpha=0.6,
            cmap='RdYlGn',
            edgecolors='black'
        )

        ax.set_xlabel('실행 시간 (초)', fontsize=12)
        ax.set_ylabel('종합 점수', fontsize=12)
        ax.set_title('실행 시간 vs 종합 점수 (Time vs Score)', fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3)

        # 컬러바
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('품질 점수', fontsize=10)

        plt.tight_layout()
        plt.savefig(self.charts_dir / "04_time_vs_score.png", dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  ✓ 차트: 시간 vs 점수")

    def _create_hallucination_analysis(self, df: pd.DataFrame):
        """환각 분석 차트"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # 환각 발생 건수
        hallucination_counts = df['hallucination_count'].value_counts().sort_index()
        ax1.bar(hallucination_counts.index, hallucination_counts.values, color='salmon', edgecolor='black', alpha=0.8)
        ax1.set_xlabel('환각 발생 건수', fontsize=12)
        ax1.set_ylabel('보고서 수', fontsize=12)
        ax1.set_title('환각 발생 건수 분포', fontsize=13, fontweight='bold')
        ax1.grid(True, alpha=0.3, axis='y')

        # 인용 정확도
        citation_accuracy = df['citation_accuracy'].value_counts().sort_index()
        ax2.bar(citation_accuracy.index, citation_accuracy.values, color='lightgreen', edgecolor='black', alpha=0.8)
        ax2.set_xlabel('인용 정확도', fontsize=12)
        ax2.set_ylabel('보고서 수', fontsize=12)
        ax2.set_title('인용 정확도 분포', fontsize=13, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='y')

        plt.suptitle('환각 분석 (Hallucination Analysis)', fontsize=14, fontweight='bold', y=1.02)
        plt.tight_layout()
        plt.savefig(self.charts_dir / "05_hallucination_analysis.png", dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  ✓ 차트: 환각 분석")

    def _create_kpi_radar(self, df: pd.DataFrame):
        """7개 KPI 레이더 차트"""
        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))

        # KPI 평균 계산
        kpis = {
            '작업 성공률': df['success_rate'].mean() * 10,
            '품질 점수': df['quality_score'].mean(),
            '완성도': df['completeness_rate'].mean() * 10,
            '환각 (역점수)': (10 - df['hallucination_count'].mean() * 2),
            '효율성': df['efficiency_score'].mean(),
            '인용 정확도': df['citation_accuracy'].mean() * 10,
        }

        categories = list(kpis.keys())
        values = list(kpis.values())

        # 각도 계산
        angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
        values += values[:1]
        angles += angles[:1]

        ax.plot(angles, values, 'o-', linewidth=2, label='평균 점수', color='blue')
        ax.fill(angles, values, alpha=0.25, color='blue')
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, fontsize=11)
        ax.set_ylim(0, 10)
        ax.set_title('KPI 레이더 차트 (평균)', fontsize=14, fontweight='bold', pad=20)
        ax.grid(True)
        ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))

        plt.tight_layout()
        plt.savefig(self.charts_dir / "06_kpi_radar.png", dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  ✓ 차트: KPI 레이더")

    def _create_source_analysis(self, df: pd.DataFrame):
        """출처 활용 분석"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # 출처 개수 분포
        ax1.hist(df['sources_count'], bins=15, edgecolor='black', alpha=0.7, color='lightblue')
        ax1.axvline(df['sources_count'].mean(), color='red', linestyle='--', linewidth=2, label=f'평균: {df["sources_count"].mean():.1f}')
        ax1.set_xlabel('출처 개수', fontsize=12)
        ax1.set_ylabel('빈도', fontsize=12)
        ax1.set_title('출처 개수 분포', fontsize=13, fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3, axis='y')

        # 출처 개수 vs 점수
        ax2.scatter(df['sources_count'], df['overall_score'], alpha=0.6, s=100, edgecolors='black')
        ax2.set_xlabel('출처 개수', fontsize=12)
        ax2.set_ylabel('종합 점수', fontsize=12)
        ax2.set_title('출처 개수 vs 종합 점수', fontsize=13, fontweight='bold')
        ax2.grid(True, alpha=0.3)

        plt.suptitle('출처 활용 분석 (Source Analysis)', fontsize=14, fontweight='bold', y=1.02)
        plt.tight_layout()
        plt.savefig(self.charts_dir / "07_source_analysis.png", dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  ✓ 차트: 출처 분석")

    def _create_dashboard(self, df: pd.DataFrame, summary_stats: Optional[Dict[str, Any]]):
        """종합 대시보드"""
        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

        # 1. 점수 분포
        ax1 = fig.add_subplot(gs[0, :2])
        ax1.hist(df['overall_score'], bins=20, edgecolor='black', alpha=0.7, color='skyblue')
        ax1.axvline(df['overall_score'].mean(), color='red', linestyle='--', linewidth=2)
        ax1.set_title('점수 분포', fontweight='bold')
        ax1.set_xlabel('종합 점수')
        ax1.set_ylabel('빈도')
        ax1.grid(True, alpha=0.3)

        # 2. 등급 분포
        ax2 = fig.add_subplot(gs[0, 2])
        grade_counts = df['grade'].value_counts()
        ax2.pie(grade_counts.values, labels=grade_counts.index, autopct='%1.1f%%', startangle=90)
        ax2.set_title('등급 분포', fontweight='bold')

        # 3. 팀별 비교
        ax3 = fig.add_subplot(gs[1, :])
        team_scores = df.groupby('team_type')['overall_score'].mean().sort_values(ascending=False)
        ax3.barh(range(len(team_scores)), team_scores.values, color=sns.color_palette("viridis", len(team_scores)))
        ax3.set_yticks(range(len(team_scores)))
        ax3.set_yticklabels(team_scores.index)
        ax3.set_title('팀별 평균 점수', fontweight='bold')
        ax3.set_xlabel('평균 점수')
        ax3.grid(True, alpha=0.3, axis='x')

        # 4. 통계 텍스트
        ax4 = fig.add_subplot(gs[2, 0])
        ax4.axis('off')
        stats_text = f"""
        종합 통계
        ────────────
        평균 점수: {df['overall_score'].mean():.2f}
        중앙값: {df['overall_score'].median():.2f}
        표준편차: {df['overall_score'].std():.2f}
        최소: {df['overall_score'].min():.2f}
        최대: {df['overall_score'].max():.2f}
        """
        ax4.text(0.1, 0.5, stats_text, fontsize=11, verticalalignment='center', family='monospace')

        # 5. 환각 통계
        ax5 = fig.add_subplot(gs[2, 1])
        ax5.axis('off')
        hallucination_text = f"""
        환각 분석
        ────────────
        평균 환각: {df['hallucination_count'].mean():.2f}건
        환각 0건: {(df['hallucination_count'] == 0).sum()}개
        인용 정확도: {df['citation_accuracy'].mean():.2%}
        """
        ax5.text(0.1, 0.5, hallucination_text, fontsize=11, verticalalignment='center', family='monospace')

        # 6. 효율성 통계
        ax6 = fig.add_subplot(gs[2, 2])
        ax6.axis('off')
        efficiency_text = f"""
        효율성 분석
        ────────────
        평균 시간: {df['total_time'].mean():.1f}초
        평균 출처: {df['sources_count'].mean():.1f}개
        완성도: {df['completeness_rate'].mean():.1%}
        """
        ax6.text(0.1, 0.5, efficiency_text, fontsize=11, verticalalignment='center', family='monospace')

        plt.suptitle('평가 결과 종합 대시보드 (Evaluation Dashboard)', fontsize=16, fontweight='bold', y=0.98)
        plt.savefig(self.charts_dir / "08_dashboard.png", dpi=300, bbox_inches='tight')
        plt.close()
        print(f"  ✓ 차트: 종합 대시보드")

    def _create_summary_report(self, results: List[Dict[str, Any]], summary_stats: Optional[Dict[str, Any]]):
        """요약 보고서 (Markdown) 생성"""

        df = pd.DataFrame(results)

        report = f"""# 평가 결과 요약 보고서

**평가 일시:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**평가 대상:** {len(results)}개 보고서

## 종합 통계

| 메트릭 | 값 |
|--------|-----|
| 평균 점수 | {df['overall_score'].mean():.2f}/10 |
| 중앙값 | {df['overall_score'].median():.2f}/10 |
| 표준편차 | {df['overall_score'].std():.2f} |
| 최소 점수 | {df['overall_score'].min():.2f}/10 |
| 최대 점수 | {df['overall_score'].max():.2f}/10 |
| 평균 실행 시간 | {df['total_time'].mean():.1f}초 |
| 평균 출처 개수 | {df['sources_count'].mean():.1f}개 |
| 평균 환각 건수 | {df['hallucination_count'].mean():.2f}건 |
| 인용 정확도 | {df['citation_accuracy'].mean():.2%} |

## 등급 분포

{df['grade'].value_counts().to_markdown()}

## 팀별 평균 점수

{df.groupby('team_type')['overall_score'].agg(['mean', 'std', 'count']).round(2).to_markdown()}

## 파일 구조

```
{self.session_dir.name}/
├── charts/         # 시각화 차트 (8개)
├── csv/            # 상세 CSV (6개)
├── json/           # JSON 결과 (2개)
└── SUMMARY.md      # 본 요약 보고서
```

## 주요 발견 사항

- **최고 점수 보고서:** {df.loc[df['overall_score'].idxmax(), 'query_text'][:50]}... ({df['overall_score'].max():.2f}점)
- **환각 제로 비율:** {(df['hallucination_count'] == 0).sum() / len(df) * 100:.1f}%
- **A등급 이상 비율:** {(df['grade'].isin(['A+', 'A'])).sum() / len(df) * 100:.1f}%

---
*Generated by DetailedResultsExporter*
"""

        report_path = self.session_dir / "SUMMARY.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"  ✓ 요약 보고서: {report_path}")


# 사용 예시
if __name__ == "__main__":
    # 테스트 데이터
    test_results = [
        {
            'query_id': 'q1',
            'query_text': '테스트 쿼리 1',
            'team_type': 'marketing',
            'overall_score': 8.5,
            'grade': 'B+',
            'success_rate': 0.9,
            'quality_score': 8.0,
            'completeness_rate': 0.95,
            'hallucination_count': 0,
            'efficiency_score': 9.0,
            'citation_accuracy': 1.0,
            'total_time': 65.0,
            'sources_count': 25,
            'quality_reasoning': 'Good quality',
            'hallucination_reasoning': 'No hallucination detected',
            'hallucination_examples': [],
            'strengths': ['Good analysis'],
            'weaknesses': ['Could be better'],
            'recommendations': ['Add more data']
        }
    ]

    exporter = DetailedResultsExporter()
    exporter.export_detailed_results(test_results)
