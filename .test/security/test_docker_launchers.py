from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_docker_launchers_require_an_explicit_image_before_side_effects() -> None:
    powershell = (PROJECT_ROOT / "start_docker.ps1").read_text(encoding="utf-8")
    shell = (PROJECT_ROOT / "start_docker.sh").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    for content in (powershell, shell, compose):
        assert "deepagent-shell:latest" not in content

    assert powershell.index("IsNullOrWhiteSpace($Image)") < powershell.index(
        "New-Item"
    )
    assert "Docker image is required. Pass -Image" in powershell
    assert shell.index('if [ -z "$image" ]') < shell.index('mkdir -p "$data"')
    assert "Docker image is required. Set AGENT_SHELL_IMAGE" in shell
    assert (
        '${AGENT_SHELL_IMAGE:?Set AGENT_SHELL_IMAGE to an exact tag or digest}'
        in compose
    )


def test_explicit_docker_image_is_forwarded_to_compose_unchanged() -> None:
    powershell = (PROJECT_ROOT / "start_docker.ps1").read_text(encoding="utf-8")
    shell = (PROJECT_ROOT / "start_docker.sh").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "$env:AGENT_SHELL_IMAGE = $Image" in powershell
    assert 'export AGENT_SHELL_IMAGE="$image"' in shell
    assert 'image: "${AGENT_SHELL_IMAGE:?' in compose
