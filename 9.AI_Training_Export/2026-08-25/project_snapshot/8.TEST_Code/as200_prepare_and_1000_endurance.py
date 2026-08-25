"""先完成模拟器内残留FIFO，再启动1000笔耐久测试。"""

from __future__ import annotations

from pathlib import Path

from as200_1000_order_endurance_test import ThousandOrderEnduranceTest
from as200_resume_fifo_stress_test import main as resume_fifo


def main() -> int:
    resume_result = resume_fifo()
    if resume_result != 0:
        print(f"[FAIL] Residual FIFO resume failed: {resume_result}", flush=True)
        return resume_result

    return ThousandOrderEnduranceTest().run_endurance(
        total_orders=1000,
        queue_window=16,
        log_dir=Path(__file__).resolve().parent / "logs",
    )


if __name__ == "__main__":
    raise SystemExit(main())
