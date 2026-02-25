import json
import os
from pathlib import Path

projects_dir = Path(os.path.expanduser("~/.claude/projects/-Users-jayantdevkar"))

for file_path in projects_dir.glob("*.jsonl"):
    has_edits = False
    try:
        with open(file_path, "r") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    # Check for tool use
                    if "type" in data and data["type"] == "tool_use":
                        tool_name = data.get("name", "")
                        if tool_name in ["write_to_file", "replace_file_content"]:
                            print(f"FOUND: {file_path.name} has {tool_name}")
                            has_edits = True
                            break
                    # Check for older format or different logging style if needed
                except Exception:
                    pass
    except Exception:
        pass
    if has_edits:
        # Just find the first 5
        pass
