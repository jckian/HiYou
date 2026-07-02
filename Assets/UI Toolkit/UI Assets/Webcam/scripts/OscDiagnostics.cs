using UnityEngine;
using System;

/// <summary>
/// OSC Diagnostics - Helps debug why OSC messages are not being received by Unity.
/// Attach to any GameObject and check the console for diagnostic information.
/// </summary>
public class OscDiagnostics : MonoBehaviour
{
    public int testOscPort = 8992;
    
    void Start()
    {
        Debug.Log("===== OSC DIAGNOSTICS START =====");
        
        // 1. Check if PythonEventRouter exists
        PythonEventRouter router = FindObjectOfType<PythonEventRouter>();
        if (router == null)
        {
            Debug.LogError("❌ PythonEventRouter NOT FOUND in scene!");
        }
        else
        {
            Debug.Log("✅ PythonEventRouter found");
            Debug.Log($"   - Port: {router.oscListenPort}");
            Debug.Log($"   - Script enabled: {router.enabled}");
            Debug.Log($"   - GameObject active: {router.gameObject.activeInHierarchy}");
        }
        
        // 2. Check Python config
        CheckPythonConfig();
        
        // 3. Check if OscJack library is working
        CheckOscJackLibrary();
        
        // 4. Port binding check
        CheckPortBinding();
        
        Debug.Log("===== OSC DIAGNOSTICS END =====");
    }
    
    void CheckPythonConfig()
    {
        Debug.Log("\n[Python Configuration]");
        Debug.Log("Expected Python config:");
        Debug.Log("  - IP: 127.0.0.1");
        Debug.Log("  - Port: 8992");
        Debug.Log("  - OSC Address: /vision/update");
        Debug.Log("  - Payload format: {\"trigger\": bool, \"trigger_id\": int, \"persons\": [...]}");
    }
    
    void CheckOscJackLibrary()
    {
        Debug.Log("\n[OscJack Library Status]");
        try
        {
            // Try to create a test server
            var testServer = new OscJack.OscServer(19999);
            Debug.Log("✅ OscJack library is working");
            testServer.Dispose();
        }
        catch (Exception e)
        {
            Debug.LogError($"❌ OscJack library error: {e.Message}");
        }
    }
    
    void CheckPortBinding()
    {
        Debug.Log("\n[Port Binding Status]");
        try
        {
            using (var socket = new System.Net.Sockets.UdpClient(testOscPort))
            {
                Debug.LogError($"❌ Port {testOscPort} is available (NOT listening for OSC!)");
                socket.Close();
            }
        }
        catch (System.Net.Sockets.SocketException)
        {
            Debug.Log($"✅ Port {testOscPort} is in use (OSC server likely listening)");
        }
    }
    
    void Update()
    {
        // Show per-frame diagnostic
        if (Input.GetKeyDown(KeyCode.D))
        {
            Debug.Log("\n===== REAL-TIME DIAGNOSTICS =====");
            var router = FindObjectOfType<PythonEventRouter>();
            if (router != null)
            {
                Debug.Log($"[Frame {Time.frameCount}] PythonEventRouter active: {router.enabled}");
                Debug.Log("Press 'P' to check Python OSC client connection");
            }
            Debug.Log("===== END DIAGNOSTICS =====\n");
        }
    }
}
