using UnityEngine;
using UnityEngine.Networking;
using System;
using System.Collections;

/// <summary>
/// Sends scene change notifications from Unity to Python via POST /unity/scene_change
/// Used when Unity controls scene transitions:
/// - Scene 2 → Scene 3: After ChatSystem completes all 3 questions (scene=3)
/// - Scene 1 start: Notifies Python when Scene 1 begins (scene=1)
/// - Scene 2 start: Notifies Python when Scene 2 begins (scene=2)
/// </summary>
public class SceneChangeSender : MonoBehaviour
{
    [Header("Python Server Configuration")]
    public string pythonServerUrl = "http://127.0.0.1:9100/unity/scene_change";
    
    [Header("Retry Configuration")]
    [Tooltip("Maximum number of retry attempts if Python server is unavailable")]
    public int maxRetries = 5;
    
    [Tooltip("Delay between retry attempts (seconds)")]
    public float retryDelay = 2f;
    
    [Header("Debug")]
    public bool enableDebugLogs = true;

    [Header("Scene4 Plan Request")]
    public string scene4PlanUrl = "http://127.0.0.1:9100/unity/scene4_request";
    [Tooltip("Reference to Scene4 compositor to apply returned plan JSON")]
    public CompositedFace compositedFace;

    // Notify listeners (e.g., MiniScene34Manager) when plan arrives via HTTP
    public Action<string> OnScene4PlanReceived;

    /// <summary>
    /// Send scene change notification to Python
    /// </summary>
    /// <param name="sceneNumber">Scene number (1=walkby, 2=dialogue, 3=face_analysis)</param>
    public void SendSceneChange(int sceneNumber)
    {
        StartCoroutine(SendSceneChangeCoroutine(sceneNumber));
    }

    /// <summary>
    /// Request Python to generate Scene4 plan (uses latest Scene3 frame/result).
    /// </summary>
    public void SendScene4PlanRequest()
    {
        StartCoroutine(SendScene4PlanRequestCoroutine());
    }

    IEnumerator SendSceneChangeCoroutine(int sceneNumber)
    {
        // Build JSON payload
        string json = $"{{\"scene\": {sceneNumber}}}";
        
        #if UNITY_EDITOR
        Debug.Log($"[SCENE_CHANGE] 🚨 SCENE_CHANGE → Unity sending scene={sceneNumber} to Python via HTTP");
        Debug.Log($"[SCENE_CHANGE] Stack trace: {System.Environment.StackTrace}");
        #endif

        int attemptCount = 0;
        bool success = false;

        while (attemptCount < maxRetries && !success)
        {
            attemptCount++;

            // Create POST request
            using (UnityWebRequest request = new UnityWebRequest(pythonServerUrl, "POST"))
            {
                byte[] bodyRaw = System.Text.Encoding.UTF8.GetBytes(json);
                request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");

                // Send request
                yield return request.SendWebRequest();

                // Handle response
                if (request.result == UnityWebRequest.Result.Success)
                {
                    success = true;
                    if (enableDebugLogs)
                    {
                        #if UNITY_EDITOR
                        Debug.Log($"[SceneChangeSender] ✅ Python acknowledged scene={sceneNumber} (attempt {attemptCount})");
                        #endif
                    }
                }
                else
                {
                    if (attemptCount < maxRetries)
                    {
                        Debug.LogWarning($"[SceneChangeSender] ⚠️ Attempt {attemptCount}/{maxRetries} failed: {request.error}. Retrying in {retryDelay}s...");
                        yield return new WaitForSeconds(retryDelay);
                    }
                    else
                    {
                        Debug.LogError($"[SceneChangeSender] ❌ Failed to send scene change after {maxRetries} attempts: {request.error}");
                    }
                }
            }
        }
    }

    IEnumerator SendScene4PlanRequestCoroutine()
    {
        if (enableDebugLogs)
            Debug.Log("[SceneChangeSender] 📤 Requesting Scene4 plan from Python");

        using (UnityWebRequest request = new UnityWebRequest(scene4PlanUrl, "POST"))
        {
            request.uploadHandler = new UploadHandlerRaw(new byte[0]); // empty body
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");

            yield return request.SendWebRequest();

            if (request.result == UnityWebRequest.Result.Success)
            {
                string planJson = request.downloadHandler.text;
                if (enableDebugLogs)
                    Debug.Log($"[SceneChangeSender] ✅ Scene4 plan received via HTTP (len={planJson.Length})");

                if (compositedFace != null)
                {
                    compositedFace.ApplyPlan(planJson);
                }
                else
                {
                    Debug.LogWarning("[SceneChangeSender] ⚠️ compositedFace not assigned; cannot apply plan");
                }

                // Signal listeners that plan is ready
                OnScene4PlanReceived?.Invoke(planJson);
            }
            else
            {
                Debug.LogError($"[SceneChangeSender] ❌ Scene4 plan request failed: {request.error}");
            }
        }
    }
}

