using UnityEngine;
using UnityEngine.Networking;
using System.Collections;
using System.Collections.Generic;

/// <summary>
/// Sends microphone audio data to Python for speech processing
/// HYBRID APPROACH: Sends small chunks continuously for RMS/silence detection
/// AND accumulates full utterance for final Whisper recognition
/// </summary>
public class AudioSender : MonoBehaviour
{
    public string pythonHttpUrl = "http://127.0.0.1:9100/unity/audio";

    private MicrophoneController mic;

    private bool captureFullUtterance = false;
    private bool streamingEnabled = false;

    private List<byte> fullBuffer = new List<byte>(); // final whisper buffer

    public float chunkInterval = 0.2f;  // send chunks every 200ms for continuous RMS monitoring
    private float lastChunkTime = 0f;
    
    private List<byte> chunkAccumulator = new List<byte>(); // accumulate chunks before sending

    void Start()
    {
        mic = MicrophoneController.Instance;
        if (mic == null)
        {
            Debug.LogError("❌ AudioSender: Missing MicrophoneController!");
        }
    }

    // ---------------------------------------------------------
    // Called by ChatSystem when recording starts
    // ---------------------------------------------------------
    public void StartCapture()
    {
        // Start of speech → allow full buffer + chunk streaming
        streamingEnabled = true;
        fullBuffer.Clear();
        captureFullUtterance = true;
        Debug.Log("🎤 AudioSender: StartCapture()");
    }

    // ---------------------------------------------------------
    // Called by ChatSystem when recording ends
    // ---------------------------------------------------------
    public void StopCaptureAndSend()
    {
        captureFullUtterance = false;
        streamingEnabled = false;

        Debug.Log($"🎤 Uploading full utterance: {fullBuffer.Count} bytes");

        if (fullBuffer.Count < 2000)     // too short
        {
            SendEmpty();
            return;
        }

        StartCoroutine(UploadFull(fullBuffer.ToArray()));
        fullBuffer.Clear();
    }

    /// <summary>
    /// Enable/disable streaming chunks to Python (used to avoid sending idle noise).
    /// </summary>
    public void SetStreaming(bool enabled)
    {
        streamingEnabled = enabled;
        if (!enabled)
        {
            chunkAccumulator.Clear();
        }
    }

    // ---------------------------------------------------------
    // Update: send small chunks continuously (for silence detection)
    // ---------------------------------------------------------
    void Update()
    {
        if (mic == null) return;

        if (!streamingEnabled)
            return;

        // Only pull new audio every 0.1 sec (instead of every frame)
        if (Time.time - lastChunkTime < chunkInterval)
            return;

        lastChunkTime = Time.time;

        // Get a larger chunk of PCM
        byte[] newChunk = mic.GetAudioBytesForPython();
        if (newChunk == null || newChunk.Length == 0)
            return;

        // Add chunk to full buffer if recording
        if (captureFullUtterance)
            fullBuffer.AddRange(newChunk);

        // Add chunk to continuous RMS / silence detection
        chunkAccumulator.AddRange(newChunk);

        // If accumulated > 16KB, send it
        if (chunkAccumulator.Count >= 16384)
        {
            StartCoroutine(SendChunk(chunkAccumulator.ToArray()));
            chunkAccumulator.Clear();
        }
    }

    IEnumerator SendChunk(byte[] chunk)
    {
        if (chunk == null || chunk.Length == 0)
            yield break;

        WWWForm form = new WWWForm();
        form.AddBinaryData("audio", chunk, "chunk.pcm", "audio/pcm");
        form.AddField("sample_rate", mic.GetSampleRate());
        form.AddField("channels", 1);
        form.AddField("format", "pcm16");

        using (UnityWebRequest www = UnityWebRequest.Post(pythonHttpUrl, form))
        {
            yield return www.SendWebRequest();
        }
    }

    IEnumerator UploadFull(byte[] finalAudio)
    {
        WWWForm form = new WWWForm();
        form.AddBinaryData("audio", finalAudio, "utterance.pcm", "audio/pcm");
        form.AddField("sample_rate", mic.GetSampleRate());
        form.AddField("channels", 1);
        form.AddField("format", "pcm16");

        using (UnityWebRequest www = UnityWebRequest.Post(pythonHttpUrl, form))
        {
            yield return www.SendWebRequest();

            if (www.result != UnityWebRequest.Result.Success)
                Debug.LogError($"❌ Python error: {www.error}");
            else
                Debug.Log("✅ Uploaded full utterance to Python successfully.");
        }
    }

    void SendEmpty()
    {
        WWWForm form = new WWWForm();
        form.AddBinaryData("audio", new byte[0], "empty.pcm", "audio/pcm");
        form.AddField("sample_rate", mic.GetSampleRate());
        form.AddField("channels", 1);
        form.AddField("format", "pcm16");

        StartCoroutine(SendEmptyCoroutine(form));
    }

    IEnumerator SendEmptyCoroutine(WWWForm form)
    {
        using (UnityWebRequest www = UnityWebRequest.Post(pythonHttpUrl, form))
        {
            yield return www.SendWebRequest();
        }
    }
}
