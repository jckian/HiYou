using UnityEngine;
using System.Diagnostics;
using Debug = UnityEngine.Debug;

public class PythonLauncher : MonoBehaviour
{
    [Header("Python script settings")]
    public string pythonExePath = @"C:\ProgramData\anaconda3\envs\f25\python.exe";

    public string pythonScriptPath = @"D:\School\Fall 2025\AT Studio one\PythonProject\corePipeline_v2.py";

    private Process pythonProcess;

    void Start()
    {
        StartPython();
    }

    void OnApplicationQuit()
    {
        StopPython();
    }

    void OnDestroy()
    {
        StopPython();
    }

    void StartPython()
    {
        Debug.Log($"[PythonLauncher] StartPython() called");
        
        if (pythonProcess != null && !pythonProcess.HasExited)
        {
            Debug.Log("[PythonLauncher] Python process already running");
            return;
        }

        if (string.IsNullOrEmpty(pythonExePath) || string.IsNullOrEmpty(pythonScriptPath))
        {
            Debug.LogError("[PythonLauncher] ❌ Python paths not configured! Set pythonExePath and pythonScriptPath in Inspector.");
            return;
        }

        Debug.Log($"[PythonLauncher] Attempting to launch:");
        Debug.Log($"  Python: {pythonExePath}");
        Debug.Log($"  Script: {pythonScriptPath}");

        // Check if files exist
        if (!System.IO.File.Exists(pythonExePath))
        {
            Debug.LogError($"[PythonLauncher] ❌ Python executable not found at: {pythonExePath}");
            return;
        }
        
        if (!System.IO.File.Exists(pythonScriptPath))
        {
            Debug.LogError($"[PythonLauncher] ❌ Python script not found at: {pythonScriptPath}");
            return;
        }

        try
        {
            pythonProcess = new Process();
            pythonProcess.StartInfo.FileName = pythonExePath;
            pythonProcess.StartInfo.Arguments = $"\"{pythonScriptPath}\"";
            pythonProcess.StartInfo.WorkingDirectory = System.IO.Path.GetDirectoryName(pythonScriptPath);
            pythonProcess.StartInfo.UseShellExecute = false;
            pythonProcess.StartInfo.CreateNoWindow = true;
            pythonProcess.StartInfo.RedirectStandardOutput = true;
            pythonProcess.StartInfo.RedirectStandardError = true;

            pythonProcess.OutputDataReceived += (sender, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    Debug.Log($"[Python] {e.Data}");
            };

            pythonProcess.ErrorDataReceived += (sender, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    Debug.LogWarning($"[Python Error] {e.Data}");
            };

            pythonProcess.Start();
            pythonProcess.BeginOutputReadLine();
            pythonProcess.BeginErrorReadLine();

            Debug.Log($"✅ [PythonLauncher] Started Python process: {pythonScriptPath}");
        }
        catch (System.Exception ex)
        {
            Debug.LogError($"❌ [PythonLauncher] Failed to start Python: {ex.Message}");
        }
    }

    void StopPython()
    {
        try
        {
            if (pythonProcess != null && !pythonProcess.HasExited)
            {
                pythonProcess.Kill();
                pythonProcess.Dispose();
                Debug.Log("[PythonLauncher] 🛑 Python process stopped");
            }
        }
        catch (System.Exception ex)
        {
            Debug.LogWarning($"[PythonLauncher] Error stopping Python: {ex.Message}");
        }
    }
}
