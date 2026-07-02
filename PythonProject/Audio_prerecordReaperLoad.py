import os
import ReaperLoad_mp3

audio_root = os.path.join(os.path.dirname(__file__), "..", "YenhsingDeyingAudio")


def import_to_reaper(mp3_path):
    project_path = os.path.join(audio_root, "YenhsingDeyingReaper.rpp")
    mp3_path_abs = os.path.abspath(mp3_path).replace('\\', '/')

    # Verify the MP3 file exists
    if not os.path.exists(mp3_path):
        print(f"ERROR: MP3 not found at {mp3_path}")
        return None

    print(f"MP3 file: {mp3_path_abs}")

    # Simple track structure
    new_track = f"""  <TRACK
    NAME "dialogue"
    <ITEM
      POSITION 0
      LENGTH 10
      <SOURCE WAVE
        FILE "{mp3_path_abs}"
      >
    >
  >
"""

    # Check if project exists
    if os.path.exists(project_path):
        # Append to existing
        with open(project_path, "r") as f:
            content = f.read()

        # Remove closing >
        content = content.rstrip().rstrip('>')
        # Add new track
        content += '\n' + new_track + '>\n'

        with open(project_path, "w") as f:
            f.write(content)
    else:
        # Create new
        content = f"""<REAPER_PROJECT 0.1
    {new_track}>
    """
        with open(project_path, "w") as f:
            f.write(content)

    print(f"Added to: {project_path}")

    return project_path


def run_complete_workflow(mp3_path):
    """
    🔥 Command Center 要呼叫的函式
    使用方式：
        run_complete_workflow("C:/path/to/file.mp3")
    """
    rm = ReaperLoad_mp3.ReaperManager()

    # 匯入到 Reaper
    import_to_reaper(mp3_path)

    # 載入到 Reaper 播放
    rm.loadTrackToReaper(mp3_path)


# ⛔ 不再自動執行 main（外部控制用）
# if __name__ == "__main__":
#     run_complete_workflow(mp3_path)


