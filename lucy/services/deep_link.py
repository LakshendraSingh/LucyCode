"""
Deep link service for registering cross-platform claude:// protocols.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


class DeepLinkService:
    """Manages claude:// protocol handler registration."""

    PROTOCOL = "claude"
    APP_NAME = "LucyCode"

    def register_darwin(self) -> None:
        """Register protocol on macOS using an applet via osacompile (as a non-packaged app fallback)."""
        # In a fully packaged app, this goes in Info.plist. Here, we build a stub agent.
        applescript_code = f'''
        on open location this_URL
            do shell script "{sys.executable} -m lucy --prompt \\"" & this_URL & "\\""
        end open location
        '''
        script_path = Path("/tmp/lucy_handler.applescript")
        script_path.write_text(applescript_code)
        
        app_path = Path.home() / "Applications" / f"{self.APP_NAME}Handler.app"
        try:
            subprocess.run(["osacompile", "-o", str(app_path), str(script_path)], check=True)
            # Register using defaults
            bundle_id = "com.apple.ScriptEditor.id.LucyCodeHandler"
            subprocess.run(["defaults", "write", "com.apple.LaunchServices/com.apple.launchservices.secure",
                            "LSHandlers", "-array-add",
                            f'<dict><key>LSHandlerURLScheme</key><string>{self.PROTOCOL}</string><key>LSHandlerRoleAll</key><string>{bundle_id}</string></dict>'])
            print(f"Registered {self.PROTOCOL}:// on macOS via {app_path}")
        except Exception as e:
            print(f"macOS registration failed: {e}")

    def register_linux(self) -> None:
        """Register protocol on Linux via xdg-mime and .desktop files."""
        desktop_content = f"""[Desktop Entry]
Name={self.APP_NAME}
Exec={sys.executable} -m lucy --prompt %u
Type=Application
Terminal=true
MimeType=x-scheme-handler/{self.PROTOCOL};
"""
        desktop_dir = Path("~/.local/share/applications").expanduser()
        desktop_dir.mkdir(parents=True, exist_ok=True)
        desktop_file = desktop_dir / f"{self.PROTOCOL}-handler.desktop"
        desktop_file.write_text(desktop_content)
        
        try:
            subprocess.run(["xdg-mime", "default", desktop_file.name, f"x-scheme-handler/{self.PROTOCOL}"], check=True)
            subprocess.run(["update-desktop-database", str(desktop_dir)], check=False)
            print(f"Registered {self.PROTOCOL}:// on Linux via {desktop_file}")
        except Exception as e:
            print(f"Linux registration failed: {e}")

    def register_windows(self) -> None:
        """Register protocol on Windows via Registry."""
        import winreg
        try:
            # HKEY_CURRENT_USER\SOFTWARE\Classes\claude
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Classes\{self.PROTOCOL}")
            winreg.SetValue(key, "", winreg.REG_SZ, f"URL:{self.PROTOCOL} Protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
            
            cmd_key = winreg.CreateKey(key, r"shell\open\command")
            winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{sys.executable}" -m lucy --prompt "%1"')
            
            winreg.CloseKey(cmd_key)
            winreg.CloseKey(key)
            print(f"Registered {self.PROTOCOL}:// on Windows via Registry")
        except Exception as e:
            print(f"Windows registration failed: {e}")

    def register(self) -> None:
        """Main registration dispatcher."""
        sys_name = platform.system()
        if sys_name == "Darwin":
            self.register_darwin()
        elif sys_name == "Linux":
            self.register_linux()
        elif sys_name == "Windows":
            self.register_windows()
        else:
            print(f"Unsupported OS: {sys_name}")


if __name__ == "__main__":
    DeepLinkService().register()
