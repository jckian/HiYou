using UnityEngine;
using System.Collections;
using System;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading.Tasks;
using System.Net;
using System.IO;
using System.Threading;
using OscJack;

public class ImageSender : MonoBehaviour
{
    // refs
    private WebCamTexture webcam;
    private WebCamController controller;

    private Texture2D tempTex;

    private HttpClient http;
    private OscServer osc;

    // HTTP Server for receiving processed frames from Python
    private HttpListener httpListener;
    private Thread listenerThread;
    private bool isListening = false;

    // send
    private float interval = 0f;// 1f / 10f;
    private float lastSend = 0f;

    // receive processed frames queue
    private System.Collections.Generic.Queue<byte[]> processedFrameQueue = new System.Collections.Generic.Queue<byte[]>();


    void Start()
    {
        Debug.LogWarning("[ImageSender] This is an OLD script. Use ImageSender_v2 instead. Disabling...");
        enabled = false;
        return;
        
        // OLD CODE DISABLED - Do not use this script
        /*
        // init HTTP
        http = new HttpClient();
        http.BaseAddress = new Uri("http://127.0.0.1:9100/");

        // init OSC
        osc = new OscServer(9000);  // ← Python OSC sender port
                                    // OSC callbacks removed - UpdateBox method not available in WebCamController

        // Start HTTP listener for receiving processed frames from Python
        StartHttpListener();

        StartCoroutine(WaitAndBind());
        */
    }

    void StartHttpListener()
    {
        try
        {
            httpListener = new HttpListener();
            httpListener.Prefixes.Add("http://127.0.0.1:9101/");
            httpListener.Start();

            isListening = true;
            listenerThread = new Thread(ListenForProcessedFrames);
            listenerThread.IsBackground = true;
            listenerThread.Start();

            Debug.Log("✅ HTTP Listener started on port 9101 for processed frames");
        }
        catch (Exception e)
        {
            Debug.LogError($"❌ Failed to start HTTP listener: {e.Message}");
        }
    }

    void ListenForProcessedFrames()
    {
        while (isListening)
        {
            try
            {
                var context = httpListener.GetContext();
                var request = context.Request;
                var response = context.Response;

                if (request.HttpMethod == "POST" && request.Url.AbsolutePath == "/processed")
                {
                    // Read JPG bytes from Python
                    byte[] jpgBytes;
                    using (var ms = new MemoryStream())
                    {
                        request.InputStream.CopyTo(ms);
                        jpgBytes = ms.ToArray();
                    }

                    Debug.Log($"📥 Received processed frame from Python: {jpgBytes.Length} bytes");

                    // Queue the frame to be applied on main thread
                    if (jpgBytes.Length > 0)
                    {
                        lock (processedFrameQueue)
                        {
                            processedFrameQueue.Enqueue(jpgBytes);
                            Debug.Log($"✅ Queued frame for display. Queue size: {processedFrameQueue.Count}");
                        }
                    }
                    else
                    {
                        Debug.LogWarning("⚠️ Received empty frame from Python");
                    }

                    // Send response
                    response.StatusCode = 200;
                    byte[] buffer = System.Text.Encoding.UTF8.GetBytes("{\"status\":\"ok\"}");
                    response.ContentLength64 = buffer.Length;
                    response.OutputStream.Write(buffer, 0, buffer.Length);
                }

                response.Close();
            }
            catch (Exception e)
            {
                if (isListening)
                {
                    Debug.LogError($"❌ Listener error: {e.Message}");
                }
            }
        }
    }


    IEnumerator WaitAndBind()
    {
        yield return new WaitForSeconds(1f);

        controller = FindAnyObjectByType<WebCamController>();

        if (controller == null)
        {
            Debug.LogError("❌ ImageSender cannot find WebCamController");
            yield break;
        }

        webcam = controller.GetCameraTexture();

        tempTex = new Texture2D(webcam.width, webcam.height, TextureFormat.RGB24, false);

        Debug.Log("📸 ImageSender ready");
    }



    void Update()
    { 
        if (webcam == null || !webcam.isPlaying) return;
        if (Time.time - lastSend >= interval )
        {
            // Apply processed frames from Python
            lock (processedFrameQueue)
            {
                if (processedFrameQueue.Count > 0)
                {
                     byte[] jpgBytes = processedFrameQueue.Dequeue();
                    ApplyProcessedFrame(jpgBytes);
                    Debug.Log($"✅ Applied processed frame");
                }
            }


            lastSend = Time.time;
            StartCoroutine(SendFrame());
        }
    }

    void ApplyProcessedFrame(byte[] jpgBytes)
    {
        Texture2D processedTex = null;
        try
        {
            Debug.Log($"🖼️ Applying processed frame: {jpgBytes.Length} bytes");

            // Create texture from JPG bytes
            processedTex = new Texture2D(2, 2);
            if (processedTex.LoadImage(jpgBytes))
            {
                Debug.Log($"✅ Texture loaded successfully: {processedTex.width}x{processedTex.height}");

                // Send to WebCamController to display
                if (controller != null)
                {
                    controller.SetProcessedFrame(processedTex);
                    Debug.Log("📤 Sent processed frame to WebCamController");
                }
                else
                {
                    Debug.LogError("❌ WebCamController is null, cannot display frame");
                    Destroy(processedTex);
                }
            }
            else
            {
                Debug.LogError("❌ Failed to LoadImage from JPG bytes");
                // Failed to load image, destroy the texture
                if (processedTex != null)
                {
                    Destroy(processedTex);
                }
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"❌ Failed to apply processed frame: {e.Message}");
            // Cleanup on error
            if (processedTex != null)
            {
                Destroy(processedTex);
            }
        }
    }


    IEnumerator SendFrame()
    {
       // if (sending) yield break;
       // sending = true;

        yield return new WaitForEndOfFrame();

        tempTex.SetPixels(webcam.GetPixels());
        tempTex.Apply();

        byte[] jpg = tempTex.EncodeToJPG(60);

        MultipartFormDataContent form = new MultipartFormDataContent();

        var img = new ByteArrayContent(jpg);
        img.Headers.ContentType = new MediaTypeHeaderValue("image/jpeg");

        form.Add(img, "image", $"{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}.jpg");


        Task<HttpResponseMessage> req = null;

        try
        {
            req = http.PostAsync("unity/frame", form);
        }
        catch { yield break; }

        yield return new WaitUntil(() => req.IsCompleted);
    }



    // ========= OSC CALLBACKS =========
    // Removed OnBoxesOSC method - UpdateBox not available in WebCamController


    void OnDestroy()
    {
        // Stop HTTP listener
        isListening = false;

        // Stop and close listener to unblock GetContext()
        if (httpListener != null && httpListener.IsListening)
        {
            httpListener.Stop();
            httpListener.Close();
        }

        // Abort thread immediately to prevent hang on quit
        if (listenerThread != null && listenerThread.IsAlive)
        {
            listenerThread.Abort();
        }

        if (tempTex != null) Destroy(tempTex);
        if (http != null) http.Dispose();
        osc?.Dispose();
    }



    // ===== helper structs =====

    [Serializable]
    public class BoxEntry
    {
        public string key;
        public int x, y, w, h;
    }

    [Serializable]
    public class BoxDict
    {
        public BoxEntry[] entries;
    }
}
