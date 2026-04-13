import os
import shutil
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _prepare_fake_home(home_dir: Path) -> Path:
    nvm_dir = home_dir / ".nvm"
    nvm_dir.mkdir(parents=True, exist_ok=True)
    nvm_sh = nvm_dir / "nvm.sh"
    nvm_sh.write_text(
        textwrap.dedent(
            """\
            nvm() {
              echo "$@" >> "$NVM_LOG"
              return 0
            }
            """
        )
    )
    return nvm_sh


def test_build_admin_ui_builds_default_dashboard_without_enterprise_overrides(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    docker_dir = repo / "docker"
    dashboard_dir = repo / "ui" / "litellm-dashboard"
    docker_dir.mkdir(parents=True)
    dashboard_dir.mkdir(parents=True)

    shutil.copy(REPO_ROOT / "docker" / "build_admin_ui.sh", docker_dir / "build_admin_ui.sh")

    (dashboard_dir / "ui_colors.json").write_text('{"theme": "default"}')
    _write_executable(
        dashboard_dir / "build_ui.sh",
        "#!/bin/sh\n" "echo called > build_ui_invoked.txt\n",
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uname", "#!/bin/sh\necho Linux\n")
    _write_executable(fake_bin / "apk", "#!/bin/sh\nexit 0\n")
    _write_executable(fake_bin / "curl", "#!/bin/sh\nexit 0\n")
    _write_executable(fake_bin / "npm", "#!/bin/sh\nexit 0\n")

    home_dir = tmp_path / "home"
    _prepare_fake_home(home_dir)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["HOME"] = str(home_dir)
    env["NVM_LOG"] = str(tmp_path / "nvm.log")

    result = subprocess.run(
        ["bash", "docker/build_admin_ui.sh"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (dashboard_dir / "build_ui_invoked.txt").exists()


def test_build_ui_installs_and_uses_node_v20_before_building(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    dashboard_dir = repo / "ui" / "litellm-dashboard"
    proxy_out_dir = repo / "litellm" / "proxy" / "_experimental" / "out"
    dashboard_dir.mkdir(parents=True)
    proxy_out_dir.mkdir(parents=True)

    shutil.copy(REPO_ROOT / "ui" / "litellm-dashboard" / "build_ui.sh", dashboard_dir / "build_ui.sh")

    (dashboard_dir / "ui_colors.json").write_text('{"theme": "default"}')
    out_dir = dashboard_dir / "out"
    out_dir.mkdir()
    (out_dir / "index.html").write_text("<html>ok</html>")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "curl", "#!/bin/sh\nexit 0\n")
    _write_executable(fake_bin / "npm", "#!/bin/sh\nexit 0\n")

    home_dir = tmp_path / "home"
    _prepare_fake_home(home_dir)
    nvm_log = tmp_path / "nvm.log"

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["HOME"] = str(home_dir)
    env["NVM_LOG"] = str(nvm_log)
    env["NVM_DIR"] = str(home_dir / ".nvm")

    result = subprocess.run(
        ["bash", "build_ui.sh"],
        cwd=dashboard_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    nvm_commands = nvm_log.read_text()
    assert "install v20" in nvm_commands
    assert (proxy_out_dir / "index.html").exists()
