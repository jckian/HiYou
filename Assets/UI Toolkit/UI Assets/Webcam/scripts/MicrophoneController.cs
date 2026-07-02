using UnityEngine;
using System.Collections;

/// <summary>
/// Singleton microphone controller that captures audio and provides it to other Unity scripts and Python
/// Similar architecture to WebCamController_v2
/// </summary>
public class MicrophoneController : MonoBehaviour
{
    // ----------------------------------------------------------------
    // Singleton Pattern
    // ----------------------------------------------------------------
    public static MicrophoneController Instance { get; private set; }

    // ----------------------------------------------------------------
    // Microphone State
    // ----------------------------------------------------------------
    private AudioClip micClip;
    private string selectedMicrophone;
    private int sampleRate = 44100;
    private int recordingLength = 10; // Record in 10-second loops (increased from 1s for better buffering)
    
    // Audio data buffers
    private float[] audioSamples;
    private int lastSamplePosition = 0;
    
    // ----------------------------------------------------------------
    // Public Settings
    // ----------------------------------------------------------------
    [Header("Microphone Settings")]
    public int targetSampleRate = 16000; // 16kHz for speech processing
    public int bufferSize = 32768; // 32k samples ≈ 0.7 sec (allows accumulation across multiple frames)
    
    // ----------------------------------------------------------------
    // Setup
    // ----------------------------------------------------------------
    void Awake()
    {
        // Singleton pattern
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }
        Instance = this;
        DontDestroyOnLoad(gameObject);
    }

    void OnEnable()
    {
        StartCoroutine(InitMicrophoneDelayed());
    }

    IEnumerator InitMicrophoneDelayed()
    {
        yield return new WaitForSeconds(0.5f);
        InitMicrophone();
    }

    void InitMicrophone()
    {
        if (Microphone.devices.Length == 0)
        {
            Debug.LogError("❌ No microphone devices found! Check audio input settings.");
            StartCoroutine(RetryInitMicrophone());
            return;
        }

        // Select first available microphone
        selectedMicrophone = Microphone.devices[0];
        
        // Start recording
        micClip = Microphone.Start(selectedMicrophone, true, recordingLength, sampleRate);
        
        if (micClip == null)
        {
            Debug.LogError("❌ Failed to start microphone recording!");
            return;
        }

        // Wait for microphone to start
        StartCoroutine(CheckMicrophoneStatus());
    }

    IEnumerator RetryInitMicrophone()
    {
        yield return new WaitForSeconds(3f);
        InitMicrophone();
    }

    IEnumerator CheckMicrophoneStatus()
    {
        int maxWaitFrames = 100;
        for (int i = 0; i < maxWaitFrames; i++)
        {
            if (Microphone.IsRecording(selectedMicrophone))
            {
                // Initialize buffer
                audioSamples = new float[bufferSize];
                yield break;
            }
            yield return null;
        }

        Debug.LogError($"❌ Microphone failed to start! Device: {selectedMicrophone}");
    }

    void OnDisable()
    {
        StopMicrophone();
    }

    void OnDestroy()
    {
        StopMicrophone();
    }

    void StopMicrophone()
    {
        if (selectedMicrophone != null && Microphone.IsRecording(selectedMicrophone))
        {
            Microphone.End(selectedMicrophone);
        }
    }

    // ----------------------------------------------------------------
    // Public API - Get Audio Data
    // ----------------------------------------------------------------

    /// <summary>
    /// Get the raw AudioClip from the microphone
    /// </summary>
    public AudioClip GetAudioClip()
    {
        return micClip;
    }

    /// <summary>
    /// Get latest audio samples (non-blocking)
    /// Returns new audio data since last call
    /// </summary>
    public float[] GetLatestAudioSamples()
    {
        if (micClip == null || !Microphone.IsRecording(selectedMicrophone))
            return null;

        int cur = Microphone.GetPosition(selectedMicrophone);

        if (cur == lastSamplePosition)
            return null;

        int diff;
        if (cur > lastSamplePosition)
            diff = cur - lastSamplePosition;
        else
            diff = (micClip.samples - lastSamplePosition) + cur;

        diff = Mathf.Min(diff, bufferSize); // ensure large blocks

        float[] data = new float[diff * micClip.channels];

        // -------------------------
        // FIXED: handle wrap-around
        // -------------------------
        if (cur > lastSamplePosition)
        {
            // simple case - no wrap
            micClip.GetData(data, lastSamplePosition);
            lastSamplePosition = cur;
        }
        else
        {
            // wrap-around case
            int samplesToEnd = micClip.samples - lastSamplePosition;
            
            // Check if we're reading more than available to end
            if (diff <= samplesToEnd)
            {
                // All samples fit before wrap point
                micClip.GetData(data, lastSamplePosition);
                lastSamplePosition += diff;
            }
            else
            {
                // Need to read from end + beginning
                int samplesFromStart = diff - samplesToEnd;

                float[] seg1 = new float[samplesToEnd * micClip.channels];
                float[] seg2 = new float[samplesFromStart * micClip.channels];

                micClip.GetData(seg1, lastSamplePosition);
                micClip.GetData(seg2, 0);

                seg1.CopyTo(data, 0);
                seg2.CopyTo(data, seg1.Length);
                
                lastSamplePosition = samplesFromStart;
            }
        }

        return data;
    }

    /// <summary>
    /// Get audio samples as byte array (PCM16) for Python
    /// </summary>
    public byte[] GetAudioBytesForPython()
    {
        float[] samples = GetLatestAudioSamples();
        if (samples == null || samples.Length == 0)
            return null;

        // Ensure sample count is even to maintain 2-byte (int16) alignment
        int sampleCount = samples.Length;
        if (sampleCount % 2 != 0)
        {
            // Trim one sample to make it even
            sampleCount--;
            Debug.LogWarning($"[MicrophoneController] Trimmed 1 sample for alignment (was {samples.Length}, now {sampleCount})");
        }

        if (sampleCount == 0)
            return null;

        // Convert float samples to 16-bit PCM (2 bytes per sample)
        byte[] bytes = new byte[sampleCount * 2];
        for (int i = 0; i < sampleCount; i++)
        {
            short sample = (short)(samples[i] * short.MaxValue);
            bytes[i * 2] = (byte)(sample & 0xFF);
            bytes[i * 2 + 1] = (byte)((sample >> 8) & 0xFF);
        }

        return bytes;
    }

    /// <summary>
    /// Get current audio level (RMS) for visualization
    /// </summary>
    public float GetAudioLevel()
    {
        float[] samples = GetLatestAudioSamples();
        if (samples == null || samples.Length == 0)
            return 0f;

        // Calculate RMS (Root Mean Square)
        float sum = 0f;
        for (int i = 0; i < samples.Length; i++)
        {
            sum += samples[i] * samples[i];
        }
        return Mathf.Sqrt(sum / samples.Length);
    }

    /// <summary>
    /// Check if microphone is currently recording
    /// </summary>
    public bool IsRecording()
    {
        return selectedMicrophone != null && Microphone.IsRecording(selectedMicrophone);
    }

    /// <summary>
    /// Get microphone sample rate
    /// </summary>
    public int GetSampleRate()
    {
        return sampleRate;
    }

    /// <summary>
    /// Get selected microphone device name
    /// </summary>
    public string GetMicrophoneName()
    {
        return selectedMicrophone;
    }
}
