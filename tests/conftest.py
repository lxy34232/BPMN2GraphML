from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def fixture_paths() -> list[Path]:
    return [
        FIX / "科技创新平台策划.bpmn",
        FIX / "科技创新平台申报.bpmn",
        FIX / "平台建设运行.bpmn",
    ]
