import json
import urllib.request

# Get all projects
projects_url = "http://localhost:8000/projects"
try:
    with urllib.request.urlopen(projects_url) as response:
        projects = json.loads(response.read().decode())

    print(f"Found {len(projects)} projects")

    found_uuid = None
    found_project = None

    for project in projects:
        encoded_name = project["encoded_name"]
        print(f"Checking project: {encoded_name}")

        # Get project details (limit 5 sessions per project to be fast)
        p_url = f"http://localhost:8000/projects/{encoded_name}?limit=5"
        try:
            with urllib.request.urlopen(p_url) as p_response:
                p_data = json.loads(p_response.read().decode())
                sessions = p_data.get("sessions", [])

                for session in sessions:
                    uuid = session["uuid"]
                    detail_url = f"http://localhost:8000/sessions/{uuid}"
                    try:
                        with urllib.request.urlopen(detail_url) as s_response:
                            s_data = json.loads(s_response.read().decode())
                            tools = s_data.get("tools_used", {})

                            if tools:
                                print(f"FOUND SESSION WITH TOOLS: {uuid} in project {encoded_name}")
                                print(f"Tools: {tools}")
                                found_uuid = uuid
                                found_project = encoded_name
                                break
                    except Exception:
                        pass
                if found_uuid:
                    break
        except Exception:
            pass
        if found_uuid:
            break

    if not found_uuid:
        print("No sessions with explicit file edit tools found.")

except Exception as e:
    print(f"Error: {e}")
