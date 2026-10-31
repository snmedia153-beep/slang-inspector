"""Create a cited Korean comparison report without changing application/model configuration."""

import argparse
import csv
import json
import math
import os
import random
import statistics
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SOURCES = [
    (
        "S1",
        "KoCulture 원본 모델 카드",
        "https://huggingface.co/huggingface-KREW/EXAONE-3.5-7.8B-Instruct-KoCulture",
    ),
    (
        "S2",
        "한국어 Slang LoRA 원본 카드",
        "https://huggingface.co/DevJeongDaeRi/Qwen3-4B-Korean-Slang-2026-LoRA",
    ),
    (
        "S3",
        "다국어 완곡어법 분류기 원본 카드",
        "https://huggingface.co/hasancanbiyik/euphemism-detector-multilingual",
    ),
    ("S4", "SlangDIT 논문 v1, 표 1·3·4", "https://arxiv.org/html/2505.14181v1"),
    ("S5", "SlangDIT 저자 공개 저장소", "https://github.com/XL2248/SlangDIT"),
    (
        "S6",
        "MLX 0.32.4 설치·CUDA 공식 문서",
        "https://ml-explore.github.io/mlx/build/html/install.html",
    ),
    ("S7", "MLX-LM 공식 사용법", "https://github.com/ml-explore/mlx-lm"),
    (
        "S8",
        "ONNX Runtime CUDA 실행 제공자",
        "https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html",
    ),
    (
        "S9",
        "ONNX Runtime TensorRT 실행 제공자",
        "https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html",
    ),
    (
        "S10",
        "NVIDIA TensorRT 지원 표",
        "https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/support-matrix.html",
    ),
    ("S11", "Ollama GPU 배치·병렬 실행 FAQ", "https://docs.ollama.com/faq"),
    ("S12", "Ollama 응답 시간·토큰 지표", "https://docs.ollama.com/api/usage"),
    (
        "S13",
        "KoCulture GGUF 변환 배포자",
        "https://huggingface.co/mradermacher/EXAONE-3.5-7.8B-Instruct-KoCulture-GGUF",
    ),
    ("S14", "Qwen2.5-14B 원본 사양", "https://huggingface.co/Qwen/Qwen2.5-14B-Instruct"),
    ("S15", "Qwen3-4B-2507 원본 사양", "https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507"),
]

SLANGDIT = [
    ("Qwen2.5-7B 기본", 74.72, 52.04, 56.94),
    ("Qwen2.5-14B 기본", 66.77, 75.60, 70.46),
    ("SFT-14B", 86.74, 74.15, 78.21),
    ("SlangOWL-7B", 82.59, 86.49, 84.02),
    ("SlangOWL-8B", 84.35, 87.30, 85.33),
    ("SlangOWL-14B", 85.17, 88.78, 86.47),
]


def bootstrap_median(values, seed=42):
    rng = random.Random(seed)
    estimates = sorted(statistics.median(rng.choices(values, k=len(values))) for _ in range(10000))
    return [round(estimates[249], 3), round(estimates[9749], 3)]


def wilson(successes, n, z=1.959963984540054):
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0, center - half), min(1, center + half)


class Bars(Flowable):
    def __init__(self, rows, maximum, width=490, suffix="", precision=2):
        super().__init__()
        self.rows, self.maximum, self.width = rows, maximum, width
        self.suffix, self.precision = suffix, precision
        self.height = 30 * len(rows) + 15

    def draw(self):
        c = self.canv
        for i, (name, value, color) in enumerate(self.rows):
            y = self.height - 28 - i * 30
            c.setFillColor(colors.HexColor("#24354a"))
            c.setFont("Korean", 8.5)
            c.drawString(0, y + 3, name)
            c.setFillColor(colors.HexColor("#e9eef4"))
            c.roundRect(145, y, 270, 15, 3, fill=1, stroke=0)
            c.setFillColor(colors.HexColor(color))
            c.roundRect(145, y, max(2, 270 * value / self.maximum), 15, 3, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#24354a"))
            c.drawString(425, y + 3, f"{value:.{self.precision}f}{self.suffix}")


def derive(measurements):
    if measurements["model"] != "qwen3.5:4b":
        raise ValueError("This fixed report expects the qwen3.5:4b timing control.")
    rows = measurements["runs"]
    assert len(rows) == 17 and all(r["output_tokens"] == 128 for r in rows)
    assert all(r["done_reason"] == "length" for r in rows)
    summary = {}
    for device, expected in [("cpu", 5), ("gpu", 10)]:
        selected = [r for r in rows if r["device"] == device and not r["warmup"]]
        assert len(selected) == expected
        assert all(
            (r["size_vram_bytes"] == 0)
            if device == "cpu"
            else (r["size_vram_bytes"] >= 0.95 * r["size_bytes"])
            for r in selected
        )
        values = [r["wall_ms"] for r in selected]
        summary[device] = {
            "n": len(values),
            "median_ms": statistics.median(values),
            "min_ms": min(values),
            "max_ms": max(values),
            "median_tokens_s": statistics.median(r["tokens_s"] for r in selected),
            "median_bootstrap_95_ms": bootstrap_median(values),
        }
    summary["latency_speedup"] = summary["cpu"]["median_ms"] / summary["gpu"]["median_ms"]
    summary["generation_speedup"] = (
        summary["gpu"]["median_tokens_s"] / summary["cpu"]["median_tokens_s"]
    )
    summary["latency_reduction_pct"] = 100 * (1 - 1 / summary["latency_speedup"])
    summary["precision_example"] = 0.9 * 0.01 / (0.9 * 0.01 + 0.01 * 0.99)
    summary["zero_fp_600_one_sided_95_upper"] = 1 - 0.05 ** (1 / 600)
    summary["example_8_of_10_wilson_95"] = wilson(8, 10)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", default="reports/model-comparison-gpu-control.json")
    parser.add_argument("--previous", default="reports/model-comparison-previous-app.json")
    parser.add_argument("--output-dir", default="output/pdf")
    fonts = Path(os.environ.get("WINDIR", ".")) / "Fonts"
    parser.add_argument("--font", default=str(fonts / "malgun.ttf"))
    parser.add_argument("--font-bold", default=str(fonts / "malgunbd.ttf"))
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    raw = json.loads(Path(args.measurements).read_text("utf-8"))
    old = json.loads(Path(args.previous).read_text("utf-8"))
    stats = derive(raw)
    cpu, gpu = stats["cpu"], stats["gpu"]
    cpu_cold = next(r for r in raw["runs"] if r["device"] == "cpu" and r["warmup"])
    gpu_cold = next(r for r in raw["runs"] if r["device"] == "gpu" and r["warmup"])
    details = raw.get("model_details", {})
    digest = raw.get("model_digest", "unrecorded")[:12]
    pdfmetrics.registerFont(TTFont("Korean", args.font))
    pdfmetrics.registerFont(TTFont("KoreanBold", args.font_bold))
    pdfmetrics.registerFontFamily("Korean", normal="Korean", bold="KoreanBold")
    ink, accent = colors.HexColor("#172b45"), colors.HexColor("#087f8c")
    styles = {
        "title": ParagraphStyle(
            "title",
            fontName="KoreanBold",
            fontSize=23,
            leading=31,
            textColor=ink,
            spaceAfter=18,
            wordWrap="CJK",
        ),
        "h1": ParagraphStyle(
            "h1",
            fontName="KoreanBold",
            fontSize=15,
            leading=22,
            textColor=ink,
            spaceAfter=14,
            wordWrap="CJK",
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName="KoreanBold",
            fontSize=11,
            leading=17,
            textColor=accent,
            spaceBefore=12,
            spaceAfter=7,
            wordWrap="CJK",
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Korean",
            fontSize=9,
            leading=15,
            textColor=ink,
            spaceAfter=8,
            wordWrap="CJK",
            alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "small",
            fontName="Korean",
            fontSize=7.6,
            leading=12,
            textColor=colors.HexColor("#536278"),
            spaceAfter=6,
            wordWrap="CJK",
        ),
        "cell": ParagraphStyle(
            "cell", fontName="Korean", fontSize=8, leading=12, textColor=ink, wordWrap="CJK"
        ),
    }
    story, md = [], []

    def p(text, style="body"):
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), styles[style]))
        md.append(text + "\n")

    def h(text):
        p(text, "h2")

    def table(headers, rows, widths):
        cells = [
            [Paragraph(escape(str(x)), styles["cell"]) for x in row] for row in [headers, *rows]
        ]
        t = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfeaf4")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f4f7fa")],
                    ),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#b6c8d9")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.extend([t, Spacer(1, 10)])
        md.append("| " + " | ".join(headers) + " |\n")
        md.append("| " + " | ".join("---" for _ in headers) + " |\n")
        md.extend("| " + " | ".join(map(str, row)) + " |\n" for row in rows)

    def page(title):
        if story:
            story.append(PageBreak())
        md.append("\n## " + title + "\n")
        p(title, "h1")

    p("모델 4종 GPU 가속 비교", "title")
    p("한국어 초성·은어 탐지 / 공개 통계·RTX 3090 실측 / 2026-10-29", "small")
    h("판정: 한국어 정탐률과 지연의 종합 1위는 아직 입증되지 않았습니다")
    p(
        "네 후보의 공통 한국어 평가셋·GPU 지연 자료가 없습니다. 따라서 서로 다른 논문 F1과 생"
        "성 모델의 사용 예시를 합쳐 종합 순위를 만들지 않았습니다. 공개 숫자, 현재 PC의 대조 "
        "실험, 구조상 예상과 미측정을 분리했습니다."
    )
    table(
        ["후보", "맡길 수 있는 일", "확인한 정량 근거", "선택 판단"],
        [
            [
                "KoCulture 7.8B",
                "한국어 신조어 대화·설명 생성",
                "정성 평가. 한국어 탐지 P/R/F1·RTX 지연 미공개 [S1]",
                "한국어 설명 품질 실험 후보",
            ],
            [
                "Qwen3-4B Slang LoRA",
                "한국어 신조어 생성 어댑터",
                "500회 학습. 정탐률·지연 미공개 [S2]",
                "작은 생성 모델 실험 후보",
            ],
            [
                "Euphemism XLM-R",
                "지정한 구절의 완곡/문자적 의미 분류",
                "전체 Macro-F1 80.8%, 한국어 F1 80.4%·카드 n=10 [S3]",
                "저지연 보조 분류기 후보",
            ],
            [
                "SlangOWL / SlangDIT",
                "영어 슬랭 위치·설명·중국어 번역",
                "14B 일반셋 탐지 F1 86.47%, 한국어 미평가 [S4]",
                "문맥 학습 방법의 연구 참고",
            ],
        ],
        [105, 128, 156, 116],
    )
    h("질문에 대한 실무 답변")
    p(
        "처리량 우선이면 작은 XLM-R 분류기가 유리할 가능성이 큽니다. 다만 완곡어법 점수는 성착"
        "취 여부나 초성 원형의 정답 점수가 아닙니다. 설명 생성까지 필요하면 KoCulture와 Qwen L"
        "oRA를 별도 한국어 평가로 비교해야 합니다. 이 두 후보 중 누가 더 정확한지는 현재 공개 "
        "자료로 확정할 수 없습니다."
    )
    p(
        "현재 서비스에는 CPU 사전·문맥 규칙과 RTX의 기존 생성 모델을 유지하고, 미확인 후보만 "
        "모델에 보내는 구성이 합리적입니다. 네 모델을 모두 동시에 호출하는 방식은 이번 조사에"
        "서 검증된 최적 구성이 아닙니다."
    )

    page("1. 공개 통계: 같은 과제 안에서 비교")
    p(
        "SlangDIT 일반 평가 3,726건(슬랭 없음 1,863 + 비다의적 슬랭 1,863), 어려운 평가 1,165"
        "건. 저자 공개 JSONL 개수를 직접 확인했습니다. 아래 수치는 논문 표 3의 원문 값입니다. "
        "영어 과제이며 한국어 정탐률이 아닙니다. [S4, S5]"
    )
    table(
        ["같은 일반 평가셋", "Precision %", "Recall %", "F1 %"],
        [[r[0], *[f"{v:.2f}" for v in r[1:]]] for r in SLANGDIT],
        [220, 95, 95, 95],
    )
    story.append(
        Bars(
            [(r[0], r[3], "#087f8c" if "OWL" in r[0] else "#8aa0b7") for r in SLANGDIT],
            100,
            suffix="%",
        )
    )
    p(
        "14B SlangOWL의 F1은 SFT-14B보다 8.26%p, 기본 Qwen2.5-14B보다 16.01%p 높습니다. 어려운"
        " 평가의 SlangOWL-14B F1은 89.60%입니다. 학습 자료 수집 단계에서 공격적·비속 문장을 제"
        "외한 점도 현재 성착취 은어 과제와의 차이입니다. RTX 3090 지연은 공개되지 않았습니다. "
        "[S4]",
        "small",
    )
    h("완곡어법 분류기의 80.4%를 위 그래프에 넣지 않은 이유")
    p(
        "XLM-R는 [PET_BOUNDARY]로 지정한 표현을 이진 분류합니다. 학습 자료는 7개 언어 19,490건"
        "이며 한국어는 포함되지 않습니다. 한국어 F1 0.804는 합성 zero-shot 평가이고 카드의 n은"
        " 10입니다. 원시 예측·혼동행렬 없이 이를 정답 8/10 또는 특정 신뢰구간으로 바꿀 수 없습"
        "니다. [S3]"
    )
    p(
        "KoCulture의 신조어 생성 능력과 LoRA의 500회 학습도 탐지 F1이 아닙니다. 이 둘의 빈 점"
        "수를 0점으로 처리하거나 영어 F1과 평균내지 않았습니다. [S1, S2]",
        "small",
    )

    page("2. RTX 3090 실측: 가속의 실제 효과")
    p(
        "현재 PC: Core Ultra 7 258V, RAM 약 31.5GiB, RTX 3090 24GiB(SM 8.6), "
        "드라이버 616.92, Ollama 0.40.8. 새 실험은 qwen3.5:4b "
        f"{details.get('quantization_level', '미기록')} 태그 대조 모델"
        f"(메타데이터 {details.get('parameter_size', '미기록')}, "
        f"digest {digest})을 사용했습니다. "
        "네 후보 중 Qwen3 Slang LoRA와 다른 모델입니다."
    )
    p(
        "같은 한국어 설명 프롬프트, context 2,048, 출력 128토큰 고정, temperature 0, seed 42, "
        "think=false. CPU/GPU 각각 첫 1회 준비를 제외하고 CPU 5회·GPU 10회를 순차 측정했습니다"
        ". CPU VRAM=0, GPU size_vram=size를 API로 확인했습니다. [측정 M1; 지표 정의 S12]"
    )
    table(
        ["준비 후", "n", "HTTP 중앙값", "최소~최대", "생성 tok/s 중앙값"],
        [
            [
                "CPU",
                cpu["n"],
                f"{cpu['median_ms'] / 1000:.3f}초",
                f"{cpu['min_ms'] / 1000:.3f}~{cpu['max_ms'] / 1000:.3f}초",
                f"{cpu['median_tokens_s']:.2f}",
            ],
            [
                "RTX 3090",
                gpu["n"],
                f"{gpu['median_ms'] / 1000:.3f}초",
                f"{gpu['min_ms'] / 1000:.3f}~{gpu['max_ms'] / 1000:.3f}초",
                f"{gpu['median_tokens_s']:.2f}",
            ],
        ],
        [93, 32, 113, 137, 130],
    )
    story.append(
        Bars(
            [
                ("CPU 지연", cpu["median_ms"] / 1000, "#8aa0b7"),
                ("RTX 지연", gpu["median_ms"] / 1000, "#087f8c"),
            ],
            15,
            suffix="초",
            precision=3,
        )
    )
    p(
        f"전체 지연은 {stats['latency_speedup']:.2f}배 개선"
        f"({stats['latency_reduction_pct']:.2f}% 감소), "
        f"생성 구간은 {stats['generation_speedup']:.2f}배입니다. "
        f"첫 준비 포함 호출은 CPU {cpu_cold['wall_ms'] / 1000:.3f}초, "
        f"GPU {gpu_cold['wall_ms'] / 1000:.3f}초였습니다. "
        f"GPU 준비 후 모델 배치는 약 {gpu_cold['size_vram_bytes'] / 2**30:.2f}GiB입니다."
    )
    p(
        "중앙값 bootstrap 95% 구간(10,000회, seed 42): CPU "
        f"{cpu['median_bootstrap_95_ms'][0] / 1000:.3f}~"
        f"{cpu['median_bootstrap_95_ms'][1] / 1000:.3f}초, GPU "
        f"{gpu['median_bootstrap_95_ms'][0] / 1000:.3f}~"
        f"{gpu['median_bootstrap_95_ms'][1] / 1000:.3f}초. "
        "작은 반복 표본의 참고 구간이며, 서로 다른 문서나 시간대에 대한 "
        "일반화 구간이 아닙니다.",
        "small",
    )
    h("기존 프로젝트 프롬프트 실측은 별도 참고")
    previous = []
    for model in ["qwen3.5:9b", "qwen3.5:4b", "qwen2.5:7b-instruct"]:
        selected = [r for r in old["models"] if r["model"] == model]
        warm = [r["wall_ms"] / 1000 for r in selected if not r["first_call_for_model"]]
        previous.append([model, " / ".join(f"{x:.2f}" for x in warm) + "초", "2개 문장, 각 1회"])
    table(["기존 설치 모델 [M2]", "준비 후 개별 지연", "표본"], previous, [185, 180, 140])
    p(
        "M1은 128토큰에서 잘라 품질을 채점하지 않았습니다. CPU→GPU 고정 순서이며 OS/프롬프트 "
        "캐시·클록·다른 앱 부하는 통제하지 않았습니다. M2도 정탐률 평가가 아닙니다. 이전 12.4"
        "배 생성 가속은 다른 프롬프트·2회 결과라 합치지 않았습니다. 네 후보의 GPU 속도·순위는 "
        "미측정입니다.",
        "small",
    )

    page("3. GPU 경로·메모리·동시 경합")
    table(
        ["후보", "우선 검증할 가속 경로", "현재 확인 범위"],
        [
            [
                "KoCulture",
                "CUDA Transformers 또는 별도 GGUF/Ollama",
                "원본 BF16과 제3자 Q4 GGUF 존재. 직접 RTX 실행 미측정 [S1, S13]",
            ],
            [
                "Qwen Slang LoRA",
                "Linux/WSL2 또는 Docker의 MLX CUDA",
                "MLX 공식 CUDA 지원 확인. 이 어댑터 실제 실행·커널 호환은 미검증 [S2, S6, S7]",
            ],
            [
                "XLM-R 분류기",
                "PyTorch CUDA → ONNX CUDA → TensorRT 비교",
                "CPU 대비 batch=1/8/32 지연과 한국어 품질을 함께 검증해야 함 [S8, S9]",
            ],
            [
                "SlangOWL",
                "가중치 확보 후 CUDA/vLLM·양자화 비교",
                "공식 저장소에서 평가 데이터는 확인, 학습 가중치 배포 링크는 확인하지 못함 [S5]",
            ],
        ],
        [105, 177, 223],
    )
    h("앞선 보고서에서 보완할 사항")
    p(
        "MLX 형식이라는 이유만으로 NVIDIA 실행을 배제하면 안 됩니다. 현재 MLX 문서는 Linux CUD"
        "A 12/13 패키지를 안내합니다. 요구 조건(SM 7.5 이상, CUDA 13은 드라이버 580 이상 등)을"
        " 이 PC의 GPU/드라이버는 충족합니다. 다만 완성된 Ollama 모델이 되는 것은 아니며 베이스"
        " 모델과 정확한 어댑터 로딩 검증이 필요합니다. [S6, S7]"
    )
    table(
        ["가중치만 단순 계산", "BF16/FP16", "INT4 하한"],
        [
            ["KoCulture 약 7.818B", "14.56GiB", "3.64GiB"],
            ["Qwen 약 4B 본체", "약 7.45GiB", "약 1.86GiB"],
            ["SlangOWL 14B 계열(약 14.7B)", "약 27.38GiB", "약 6.85GiB"],
            ["XLM-R 약 0.278B", "약 0.52GiB", "위 조합에서는 FP16 유지"],
        ],
        [285, 110, 110],
    )
    p(
        "계산은 파라미터 수 × 2 또는 0.5 byte / 2^30이며 일부 크기는 근사입니다. 세 생성 모델 "
        "BF16+분류기 FP16의 합은 약 50GiB로 24GiB를 넘습니다. 생성 모델 INT4+분류기 FP16은 약 "
        "12.9GiB 하한이지만 KV 캐시·메타데이터·어댑터·실행 공간이 빠져 있어 동시 상주 가능성을"
        " 보장하지 않습니다. [S1, S14, S15]"
    )
    p(
        "권장: 비교 실험은 모델별 단독 실행, 운영은 생성 모델 1개와 CPU 규칙을 우선합니다. 실"
        "제 동시 경합을 평가하려면 고정 입력과 도착률로 동시성 1/2/4를 나눠 QPS, p50/p95, OOM,"
        " 누락률을 기록해야 합니다. 모델 병렬화가 지연을 줄인다고 가정할 수 없습니다. [S11]",
        "small",
    )

    page("4. 정탐률을 통계적으로 판단하는 방법")
    table(
        ["지표", "계산·채점 기준", "현재 네 후보 비교"],
        [
            ["탐지 정밀도", "TP/(TP+FP): 표시한 은어 중 실제 은어", "한국어 공통 결과 없음"],
            ["탐지 재현율", "TP/(TP+FN): 실제 은어 중 찾아낸 비율", "동일 평가셋 필요"],
            [
                "원형 Top-1",
                "정답 원형과 일치한 후보 / 평가 후보",
                "감지 성공 후와 전체 조건을 따로 보고",
            ],
            ["공동 성공률", "위치·문맥 의미·원형이 함께 맞은 비율", "현재 요구에 가장 직접적"],
            [
                "정상 문장 오탐률",
                "FP/(FP+TN), 단어가 아닌 문장 단위도 별도",
                "일상 초성·보도/신고·상호명 포함",
            ],
            [
                "미확인·커버리지",
                "보류 비율, 답한 항목의 정확도",
                "보류를 버려 정확도를 부풀리지 않음",
            ],
        ],
        [105, 245, 155],
    )
    h("가속과 정탐은 별도 축입니다")
    p(
        "CUDA/TensorRT가 은어 지식을 새로 학습시키는 것은 아닙니다. GPU는 지연·처리량을 바꾸고"
        " 더 큰 모델의 사용을 가능하게 합니다. FP16/INT8/INT4는 경계 사례의 출력·점수를 바꿀 "
        "수 있어 양자화 전후를 같은 정답셋으로 재평가해야 합니다. TensorRT 설치 자체를 정탐률 "
        "개선으로 계산하지 않습니다."
    )
    h("숫자를 해석할 때 주의할 두 가지")
    p(
        "가정 예시: 실제 검토 대상 비율 1%, 재현율 90%, 정상 오탐률 "
        f"1%이면 탐지 정밀도는 {stats['precision_example'] * 100:.1f}%입니다. "
        "이는 어느 후보의 실측 점수도 아니며, 낮은 출현율 환경에서 "
        "FPR이 왜 중요한지를 보이는 계산입니다."
    )
    p(
        "표본 부족: 분류기의 한국어 F1=0.804와 n=10만으로는 신뢰구간을 복원할 수 없습니다. 별"
        "도의 이항 예시에서 8/10 정답의 Wilson 95% 구간은 약 49.0~94.3%로 넓습니다. 이 예시는 "
        "분류기 원시 결과를 뜻하지 않습니다."
    )
    p(
        "운영 기준 예시: 독립 정상 문장 600개에서 오탐 0개일 때, "
        "동일 분포·독립 가정의 일측 95% 정확 이항 상한은 "
        f"{stats['zero_fp_600_one_sided_95_upper'] * 100:.3f}%입니다. "
        "같은 문장 반복이나 비슷한 템플릿 600개로 이 조건을 대신할 수 없습니다."
    )
    h("제안하는 한국어 검증 설계")
    p(
        "개발셋 1,000건과 고정 테스트 2,000건(양성/정상 각 1,000)을 표현·출처·시간 단위로 분리"
        "합니다. 초성 다의어, 일반 신조어, 촬영/유포 표현, 난독화, 정상 일상문, 보도/피해지원,"
        " 미확인 신어를 층화합니다. 검토자 2명과 불일치 조정으로 위치·원형·문맥 의미를 라벨링"
        "하고, 반복 표현은 그룹으로 묶어 부트스트랩합니다. 이는 평가 제안이며 수집·완료된 새 "
        "정답셋이 아닙니다.",
        "small",
    )

    page("5. 프로젝트 연동과 최종 선택")
    h("현재 요구에 맞춘 단계별 구성")
    p(
        "이미지 → 현재 OCR → CPU 사전·초성·문맥 후보 → 필요한 후보만 문맥 모델 → 원문 위치/근"
        "거 검증 → WebUI 빨간 표식. OCR 결과와 은어 의미 판정은 분리해 평가합니다. OCR 오인식"
        "이 있으면 모델만 바꿔도 전체 정탐률이 낮아질 수 있습니다."
    )
    table(
        ["우선순위", "실행할 비교", "통과 기준·의미"],
        [
            [
                "1",
                "KoCulture Q4와 Qwen LoRA의 같은 한국어 문맥·원형 평가",
                "현재 용도의 생성 모델 선택. LoRA 베이스는 Qwen3-4B-2507이며 현재 qwen3.5:4b와"
                " 다름",
            ],
            [
                "2",
                "XLM-R CPU/CUDA/TensorRT batch 1/8/32",
                "기존 후보의 보조 분류. 완곡어법=유해성으로 처리하지 않음",
            ],
            [
                "3",
                "모델별 단독·동시성 1/2/4에서 전체 요청 지연",
                "고정 입력·컨텍스트·출력 예산·warmup/첫 호출 구분",
            ],
            [
                "4",
                "SlangOWL 방식의 문맥·다의성 학습",
                "한국어 학습·평가가 준비되면 검토. 영어 체크포인트 점수만으로 교체하지 않음",
            ],
        ],
        [57, 224, 224],
    )
    p(
        "XLM-R가 낮은 완곡 점수를 냈다는 이유로 직접적인 위험 표현을 버리면 안 됩니다. 반대로 "
        "일상적인 완곡 표현은 분류기에서 높은 점수를 받을 수 있습니다. 명시적 사전 신호는 유지"
        "하고 분류기를 보조 증거로만 사용해야 합니다."
    )
    p(
        "현 코드 app/contextual.py는 Ollama /api/tags·/api/chat와 JSON 스키마를 사용합니다. 새"
        " 분류기는 classify 인터페이스, 생성기는 interpret 인터페이스로 분리해야 하며 모델 이"
        "름만 바꾸는 것으로 네 후보가 연결되지는 않습니다. 후보 원문 ID·근거·미확인 처리는 유"
        "지합니다."
    )
    h("선정 기준 제안")
    p(
        "한국어 테스트의 최소 정밀도와 최대 FPR 등 운영 기준을 먼저 정하고, 이를 만족하는 모델"
        " 중 p95 지연과 메모리를 비교합니다. 품질 기준은 목적과 검토 비용에 따라 합의해야 합니"
        "다. 임의 가중치를 준 종합 점수나 서로 다른 과제 F1의 평균으로 우승자를 만들지 않습니"
        "다."
    )
    h("권고 결론")
    p(
        "공개 영어 슬랭 탐지 성적은 SlangOWL-14B가 강합니다. 현재 앱의 저지연 보조 분류 후보는"
        " XLM-R, 한국어 원형·설명 후보는 KoCulture와 Qwen LoRA입니다. GPU 대조 실험은 약 6.84"
        "배 지연 개선을 확인했지만 네 후보의 속도·정탐 종합 순위를 증명하지는 않습니다. 현재 "
        "운영 구성을 유지하며 한국어 공통 평가를 먼저 만드는 것이 근거에 맞습니다."
    )
    p(
        "배포 조건 참고: KoCulture 카드는 비영리 사용을 명시합니다. 실제 채택 시 해당 모델·데"
        "이터의 배포 조건을 확인해야 합니다. [S1]",
        "small",
    )

    page("6. 조사·검증 범위와 재현 자료")
    p(
        "원인: 공통 한국어 정확도와 동일 RTX 지연 자료가 없어 네 모델의 숫자를 직접 순위화할 "
        "수 없었습니다."
    )
    p(
        "작업 내용: 모델 카드·논문 PDF 표·공개 파일·최신 GPU 문서를 대조했고, 설치된 대조 모델"
        "로 새 CPU/GPU 실험을 했습니다. 논문 표는 PDF 3·6쪽을 시각 확인했습니다. 모델 전체 다"
        "운로드, 변환, 추가 서비스 설치는 하지 않았습니다."
    )
    p(
        "검증 결과: M1 CPU 5회/GPU 10회와 준비 2회, 128토큰·장치 배치 확인. 공개 일반/어려운 J"
        "SONL 3,726/1,165개 확인. 생성 수식·CSV·원문 참조와 PDF 렌더 검증을 수행합니다. 앱·컨"
        "테이너 설정·GitHub 배포는 변경하지 않았습니다."
    )
    p(
        "미검증: 네 후보 직접 RTX 실행·공통 한국어 정탐률, TensorRT 변환 전후, 실제 네 모델 동"
        "시 경합, 전력·발열·장시간 부하. 따라서 이 항목에 속도나 정확도 추정치를 채우지 않았습"
        "니다."
    )
    table(
        ["재현 파일", "역할"],
        [
            [
                "scripts/benchmark_gpu_slang_micro.py",
                "설치된 4B 대조 실험. 기본 CPU 5회/GPU 10회. 모델 자동 다운로드 없음",
            ],
            ["scripts/build_model_comparison_report.py", "원본 측정 → 통계·PDF·Markdown·CSV 생성"],
            ["reports/model-comparison-gpu-control.json", "새 실험의 회차별 시간·토큰·GPU 배치"],
            [
                "reports/model-comparison-previous-app.json",
                "이전 프로젝트 측정. 4개 후보의 평가로 대체하지 않음",
            ],
            ["requirements-report.txt", "선택 보고서 의존성. 프로덕션 requirements와 분리"],
        ],
        [245, 260],
    )
    p(
        "PowerShell: python -X utf8 scripts/benchmark_gpu_slang_micro.py --output artifacts/mo"
        "del-comparison-gpu-control.json",
        "small",
    )
    p("PowerShell: python -X utf8 scripts/build_model_comparison_report.py", "small")
    p(
        "생성기는 reports/의 고정 측정 자료를 읽습니다. 새 측정을 반영하려면 해당 JSON 경로를 "
        "--measurements로 지정하세요. Windows 맑은 고딕을 사용하며 다른 OS에서는 --font와 --fo"
        "nt-bold로 한글 TTF 경로를 전달합니다.",
        "small",
    )
    h("모델 원본 리비전 (조사일 기준)")
    p(
        "KoCulture: 0256994a293737a391ae8bd992db1419db72eb45\nLoRA: 5b79a277f467a47ad54b685af2"
        "02f0d879b6c145\n분류기: e3cf34cc5fcb014c9972e053f6afa2bbc74ca8dc",
        "small",
    )

    page("7. 원본 출처")
    p(
        "모든 인터넷 주장은 아래 저자·모델 배포자·런타임 공식 자료에 근거했습니다. 모델 카드 "
        "평가는 제3자의 독립 재현 결과와 구분했습니다. 확인일 2026-10-29.",
        "small",
    )
    for key, label, url in SOURCES:
        story.append(
            Paragraph(
                f"<b>[{key}]</b> {escape(label)}<br/>"
                f'<link href="{escape(url)}" color="#087f8c">{escape(url)}</link>',
                styles["small"],
            )
        )
        md.append(f"[{key}] [{label}]({url})\n")
    h("로컬 실측 자료")
    p(
        "M1: reports/model-comparison-gpu-control.json. 새 단일 프롬프트 반복 대조.\nM2: repor"
        "ts/model-comparison-previous-app.json. 이전 앱 프롬프트 소규모 실측.\nM3: reports/mod"
        "el-comparison-statistics.json. 계산 수식 결과와 불확실성 예시.",
        "small",
    )

    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor("#d8e2ec"))
        canvas.line(44, 42, 551, 42)
        canvas.setFont("Korean", 7)
        canvas.setFillColor(colors.HexColor("#536278"))
        canvas.drawString(44, 28, "은어 렌즈 | 공개 통계와 실측을 분리한 비교 | 2026-10-29")
        canvas.drawRightString(551, 28, str(doc.page))

    doc = SimpleDocTemplate(
        str(output / "slang-model-gpu-comparison.pdf"),
        pagesize=(595.28, 841.89),
        rightMargin=45,
        leftMargin=45,
        topMargin=46,
        bottomMargin=58,
        title="모델 4종 GPU 가속 비교 통계 보고서",
        author="은어 렌즈",
        pageCompression=1,
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    (output / "slang-model-gpu-comparison.md").write_text("\n".join(md), "utf-8")
    reports = Path("reports")
    reports.mkdir(exist_ok=True)
    (reports / "model-comparison-statistics.json").write_text(
        json.dumps(
            {
                "date": "2026-10-29",
                "control_model": raw["model"],
                "statistics": stats,
                "research_candidates_direct_benchmarked": 0,
                "shared_korean_test_evaluated": False,
                "sources": [{"id": k, "title": t, "url": u} for k, t, u in SOURCES],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "utf-8",
    )
    with (reports / "model-comparison-public-metrics.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.writer(f)
        writer.writerow(
            ["model", "task", "precision_pct", "recall_pct", "f1_pct", "n", "source", "evidence"]
        )
        for name, precision, recall, f1 in SLANGDIT:
            writer.writerow(
                [
                    name,
                    "English slang detection - general",
                    precision,
                    recall,
                    f1,
                    3726,
                    SOURCES[3][2],
                    "author_reported_not_locally_reproduced",
                ]
            )
        writer.writerow(
            [
                "SlangOWL-14B",
                "English slang detection - hard",
                88.86,
                91.50,
                89.60,
                1165,
                SOURCES[3][2],
                "author_reported_not_locally_reproduced",
            ]
        )
        writer.writerow(
            [
                "euphemism-detector-multilingual",
                "Korean synthetic euphemism classification",
                "",
                "",
                80.4,
                10,
                SOURCES[2][2],
                "model_card_n_definition_unverified",
            ]
        )
        for name in ["KoCulture", "Qwen3-4B-Korean-Slang-2026-LoRA"]:
            writer.writerow([name, "Korean slang detection", "", "", "", "", "", "not_reported"])
    with (reports / "model-comparison-control-runs.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(raw["runs"][0]))
        writer.writeheader()
        writer.writerows(raw["runs"])
    print(
        json.dumps(
            {"pdf": str(output / "slang-model-gpu-comparison.pdf"), "statistics": stats},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
