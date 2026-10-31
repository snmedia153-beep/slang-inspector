"""저장된 실측 JSON과 실제 화면 캡처로 README 그래프·GIF를 생성합니다."""

import argparse
import json
import os
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def find_font(explicit):
    if explicit:
        return Path(explicit)
    windows_font = Path(os.environ.get("WINDIR", "")) / "Fonts" / "malgun.ttf"
    if windows_font.is_file():
        return windows_font
    for name in ("Noto Sans CJK KR", "Noto Sans CJK JP", "NanumGothic", "AppleGothic"):
        try:
            return Path(font_manager.findfont(name, fallback_to_default=False))
        except ValueError:
            continue
    raise SystemExit("한글 글꼴을 찾지 못했습니다. --font에 한글 TTF/OTF 경로를 지정하세요.")


def measured(path):
    rows = json.loads(path.read_text("utf-8"))
    for row in rows:
        actual = statistics.median(run["wall_ms"] for run in row["runs"])
        if round(actual, 2) != row["median_ms"]:
            raise ValueError(f"중앙값 불일치: {path.name} / {row['image']}")
    return rows


def chart(output, font):
    before = measured(ROOT / "docs/benchmarks/ocr-before.json")
    after = measured(ROOT / "docs/benchmarks/ocr-after.json")
    if [r["image"] for r in before] != [r["image"] for r in after]:
        raise ValueError("비교 입력 이미지가 다릅니다.")
    for old, new in zip(before, after, strict=True):
        if len(old["runs"]) != 5 or len(new["runs"]) != 5:
            raise ValueError("비교 회차는 조건별 5회여야 합니다.")
        fingerprints = {r["fingerprint"] for r in old["runs"] + new["runs"]}
        if len(fingerprints) != 1:
            raise ValueError("변경 전후 인식 결과 지문이 다릅니다.")
    font_manager.fontManager.addfont(font)
    plt.rcParams.update({"font.family": font_manager.FontProperties(fname=font).get_name()})
    fg, muted, green, pale = "#123d3b", "#58716d", "#18695f", "#c4d3cb"
    fig = plt.figure(figsize=(14, 6.2), dpi=140, facecolor="#f3f6f1")
    fig.text(0.055, 0.89, "같은 결과, 더 짧은 OCR 대기 시간", fontsize=25, color=fg, weight="bold")
    fig.text(
        0.055,
        0.83,
        "모델 세션 재사용 · 픽셀 파이프 · CPU 스레드 경합 감소",
        fontsize=12,
        color=muted,
    )
    ax = fig.add_axes((0.055, 0.23, 0.65, 0.49), facecolor="#f3f6f1")
    labels = ["검토 표현 이미지\n18단어 · 6표현", "일반 문장 이미지\n4단어 · 표식 없음"]
    for index, (old, new) in enumerate(zip(before, after, strict=True)):
        y = 1 - index
        for offset, record, color in [(0.16, old, pale), (-0.16, new, green)]:
            value = record["median_ms"]
            ax.barh(y + offset, value, height=0.25, color=color, zorder=3)
            ax.text(value + 40, y + offset, f"{value:,.2f} ms", va="center", fontsize=12, color=fg)
    ax.set(yticks=[1, 0], yticklabels=labels, xlim=(0, 2850), ylim=(-0.5, 1.5))
    ax.set_xlabel("HTTP 왕복 지연 중앙값 (ms) · 낮을수록 빠름", fontsize=10, color=muted)
    ax.tick_params(axis="both", labelsize=10, length=0, colors=muted)
    ax.set_xticks([0, 1000, 2000])
    ax.xaxis.grid(True, color="#dce4dc", zorder=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.subplots_adjust(left=0.2)
    # 긴 한글 레이블을 그림 안쪽에 배치합니다.
    ax.set_position((0.19, 0.23, 0.50, 0.49))
    speedup = before[0]["median_ms"] / after[0]["median_ms"]
    reduction = (1 - after[0]["median_ms"] / before[0]["median_ms"]) * 100
    fig.text(0.75, 0.66, f"{reduction:.2f}%", fontsize=34, color=green, weight="bold")
    fig.text(0.75, 0.60, "검토 이미지 지연 감소", fontsize=12, color=muted)
    fig.text(0.75, 0.45, f"{speedup:.2f}배", fontsize=30, color=fg, weight="bold")
    fig.text(0.75, 0.39, "동일 조건 중앙값 기준", fontsize=12, color=muted)
    fig.text(0.19, 0.74, "■ 개선 전", color="#83998d", fontsize=11)
    fig.text(0.31, 0.74, "■ 개선 후", color=green, fontsize=11)
    fig.text(
        0.055,
        0.105,
        "2026-10-29  |  CPU 2개 · RAM 2GiB  |  ONNX Runtime CPU  |  1200×460 PNG  |  조건별 n=5",
        fontsize=10,
        color=muted,
    )
    fig.text(
        0.055,
        0.06,
        "원문·단어 좌표·표식 지문 일치 확인. "
        "모델 준비 후 순차 요청 실측이며 탐지 정확도 점수가 아닙니다.",
        fontsize=10,
        color=muted,
    )
    fig.savefig(output / "performance.png", facecolor=fig.get_facecolor())
    plt.close(fig)


def animation(output, frames_dir):
    files = sorted(frames_dir.glob("[0-9][0-9]-*.png"))
    if not files:
        raise SystemExit("화면 캡처가 없습니다. capture_portfolio.cjs를 먼저 실행하세요.")
    frames = []
    for file in files:
        with Image.open(file) as source:
            image = source.convert("RGB")
            image.thumbnail((1120, 740), Image.Resampling.LANCZOS)
            frames.append(image.quantize(colors=160))
    if len({frame.size for frame in frames}) != 1:
        raise ValueError("GIF 화면 크기는 같아야 합니다.")
    frames[0].save(
        output / "workflow.gif",
        save_all=True,
        append_images=frames[1:],
        duration=[2200] * len(frames),
        loop=0,
        optimize=True,
        disposal=2,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font")
    parser.add_argument("--prepare", action="store_true", help="화면 촬영 전에 그래프만 생성")
    args = parser.parse_args()
    output = ROOT / "docs/media"
    output.mkdir(parents=True, exist_ok=True)
    font = find_font(args.font)
    chart(output, font)
    if not args.prepare:
        animation(output, ROOT / "artifacts/portfolio-frames")
    print("README 미디어 생성 완료:", output.relative_to(ROOT))


if __name__ == "__main__":
    main()
