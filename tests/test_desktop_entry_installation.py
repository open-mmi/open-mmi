from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGE_SCRIPT = ROOT / "scripts" / "manage.sh"
DESKTOP_ASSETS = ROOT / "packaging" / "linux-desktop"
DESKTOP_ENTRY = DESKTOP_ASSETS / "open-mmi-status.desktop"
DESKTOP_ICONS = DESKTOP_ASSETS / "icons"


class DesktopEntryInstallationTests(unittest.TestCase):
    def test_install_and_remove_desktop_entry_and_icons(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            home = temporary / "home"
            applications = home / ".local" / "share" / "applications"
            icons = home / ".local" / "share" / "icons"
            desktop = home / "Desktop"
            installed_application = applications / "open-mmi.desktop"
            installed_shortcut = desktop / "Open MMI.desktop"

            shell = textwrap.dedent(
                f"""\
                set -euo pipefail
                source {str(MANAGE_SCRIPT)!r}

                REAL_USER="$(id -un)"
                REAL_HOME={str(home)!r}
                REPO_ROOT={str(ROOT)!r}
                DESKTOP_ENTRY_SOURCE={str(DESKTOP_ENTRY)!r}
                DESKTOP_ICON_SOURCE={str(DESKTOP_ICONS)!r}
                APPLICATIONS_DIR={str(applications)!r}
                APPLICATION_ENTRY={str(installed_application)!r}
                ICON_THEME_DIR={str(icons)!r}
                DESKTOP_ENTRY_NAME="Open MMI.desktop"

                xdg-user-dir() {{
                    printf '%s\\n' {str(desktop)!r}
                }}

                gio() {{
                    return 0
                }}

                update-desktop-database() {{
                    return 0
                }}

                gtk-update-icon-cache() {{
                    return 0
                }}

                sudo() {{
                    if [[ "${{1:-}}" == "-u" ]]; then
                        shift 2
                    fi
                    if [[ "${{1:-}}" == "env" ]]; then
                        shift
                        while [[ "${{1:-}}" == *=* ]]; do
                            export "$1"
                            shift
                        done
                    fi
                    "$@"
                }}

                install() {{
                    local arguments=()
                    while (($#)); do
                        case "$1" in
                            -o|-g)
                                shift 2
                                ;;
                            *)
                                arguments+=("$1")
                                shift
                                ;;
                        esac
                    done
                    command install "${{arguments[@]}}"
                }}

                install_desktop_entry

                test -f {str(installed_application)!r}
                test -f {str(installed_shortcut)!r}
                test "$(stat -c '%a' {str(installed_application)!r})" = "644"
                test "$(stat -c '%a' {str(installed_shortcut)!r})" = "755"
                cmp {str(DESKTOP_ENTRY)!r} {str(installed_application)!r}
                cmp {str(DESKTOP_ENTRY)!r} {str(installed_shortcut)!r}

                while IFS= read -r -d '' source_icon; do
                    relative_path="${{source_icon#{str(DESKTOP_ICONS)!r}/}}"
                    installed_icon={str(icons)!r}/"$relative_path"
                    test -f "$installed_icon"
                    test "$(stat -c '%a' "$installed_icon")" = "644"
                    cmp "$source_icon" "$installed_icon"
                done < <(find {str(DESKTOP_ICONS)!r} -type f -print0)

                remove_desktop_entry

                test ! -e {str(installed_application)!r}
                test ! -e {str(installed_shortcut)!r}
                while IFS= read -r -d '' source_icon; do
                    relative_path="${{source_icon#{str(DESKTOP_ICONS)!r}/}}"
                    test ! -e {str(icons)!r}/"$relative_path"
                done < <(find {str(DESKTOP_ICONS)!r} -type f -print0)
                """
            )

            result = subprocess.run(
                ["bash", "-c", shell],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
